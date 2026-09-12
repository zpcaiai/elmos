"""OpenRouter Provider Adapter for Elmos Router Industrial.

Enables long-tail models, evaluation tasks, and disaster recovery failover
under strict Elmos policy governance (ZDR, data retention, provider pinning).
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator, Mapping
import urllib.error
import urllib.request

from ..domain.contracts import (
    ExecutionLane,
    InferenceResponse,
    InferenceStreamChunk,
    ModelExecutionPlan,
    ProviderDeployment,
    RouteRequest,
    UsageReport,
    VerifiedSecurityContext,
)
from ..domain.errors import ErrorTaxonomyClass, ProviderError, map_http_status_to_taxonomy
from ..registry.registry import HealthSnapshot
from ..spi.adapter import ProviderAdapter


class OpenRouterAdapter(ProviderAdapter):
    """Provider adapter communicating with OpenRouter API."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key_resolver: Callable[[str], str] | None = None,
        transport: Callable[[urllib.request.Request, float], tuple[int, Mapping[str, str], bytes]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_resolver = api_key_resolver or (lambda ref: "mock-openrouter-key")
        self._transport = transport or self._default_transport

    @property
    def adapter_id(self) -> str:
        return "openrouter"

    @property
    def supported_lanes(self) -> tuple[ExecutionLane, ...]:
        return (ExecutionLane.OPENROUTER,)

    def supports(self, plan: ModelExecutionPlan) -> bool:
        return plan.lane == ExecutionLane.OPENROUTER

    def validate(self, plan: ModelExecutionPlan) -> None:
        if not self.supports(plan):
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.UNSUPPORTED_CAPABILITY,
                message=f"OpenRouterAdapter does not support plan {plan.planId} (lane={plan.lane.value})",
                deploymentId=plan.deploymentId,
            )

    def estimate_cost(self, request: RouteRequest, plan: ModelExecutionPlan) -> float:
        return (request.maxInputTokens / 1000.0) * 0.0025 + (request.expectedOutputTokens / 1000.0) * 0.010

    def execute(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> InferenceResponse:
        self.validate(plan)
        url = f"{self.base_url}/chat/completions"

        # Construct OpenRouter provider routing constraints
        provider_routing: dict[str, Any] = {}
        allowed_providers = plan.extensions.get("allowed_openrouter_providers", ())
        if allowed_providers:
            provider_routing["order"] = list(allowed_providers)
            provider_routing["allow_fallbacks"] = False

        require_zdr = plan.extensions.get("require_zdr", False)
        if require_zdr:
            provider_routing["data_collection"] = "deny"

        payload: dict[str, Any] = {
            "model": plan.extensions.get("actual_model", plan.modelAlias),
            "messages": [m.to_dict() for m in request.messages] or [{"role": "user", "content": "hello"}],
            "max_tokens": request.expectedOutputTokens,
        }
        if provider_routing:
            payload["provider"] = provider_routing

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key_resolver(plan.providerId)}",
                "HTTP-Referer": "https://elmos.dev",
                "X-Title": "Elmos Industrial Agentic Platform",
            },
            method="POST",
        )

        start_time = time.time()
        status_code, headers, body_bytes = self._transport(req, 60.0)
        latency_ms = (time.time() - start_time) * 1000.0

        if status_code >= 400:
            self._handle_error_response(status_code, headers, body_bytes, plan)

        data = json.loads(body_bytes.decode("utf-8"))
        choice = data["choices"][0]
        msg = choice.get("message", {})

        raw_usage = data.get("usage", {})
        usage = UsageReport(
            promptTokens=raw_usage.get("prompt_tokens", 0),
            completionTokens=raw_usage.get("completion_tokens", 0),
            totalTokens=raw_usage.get("total_tokens", 0),
        )

        return InferenceResponse(
            id=str(data.get("id", f"openrouter_{int(time.time())}")),
            model=str(data.get("model", plan.modelAlias)),
            content=msg.get("content"),
            toolCalls=tuple(msg["tool_calls"]) if "tool_calls" in msg else None,
            finishReason=choice.get("finish_reason", "stop"),
            usage=usage,
            rawProviderResponseId=data.get("id"),
            rateLimitHeaders={k: v for k, v in headers.items() if "ratelimit" in k.lower()},
            executionLatencyMs=round(latency_ms, 2),
        )

    def stream(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> Iterator[InferenceStreamChunk]:
        self.validate(plan)
        response = self.execute(request, plan, security_context)
        content = response.content or ""
        parts = content.split(" ")
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            yield InferenceStreamChunk(
                chunkId=f"chunk_{i}",
                deltaContent=part + ("" if is_last else " "),
                finishReason=response.finishReason if is_last else None,
                isTerminal=is_last,
            )

    def cancel(self, execution_id: str) -> bool:
        return True

    def health_probe(self, deployment: ProviderDeployment) -> HealthSnapshot:
        return HealthSnapshot(
            deploymentId=deployment.id,
            availability=0.99,
            p95LatencyMs=600.0,
            rateLimitPressure=0.0,
            timeoutRate=0.0,
            successRate=0.99,
        )

    def _handle_error_response(
        self,
        status_code: int,
        headers: Mapping[str, str],
        body_bytes: bytes,
        plan: ModelExecutionPlan,
    ) -> None:
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = {"error": {"message": body_bytes.decode("utf-8", errors="replace")}}

        err_msg = body.get("error", {}).get("message", "OpenRouter call failed")
        taxonomy = map_http_status_to_taxonomy(status_code, body, err_msg)

        raise ProviderError(
            taxonomyClass=taxonomy,
            message=err_msg,
            statusCode=status_code,
            providerId=plan.providerId,
            deploymentId=plan.deploymentId,
            rawErrorPayload=body,
        )

    def _default_transport(
        self, req: urllib.request.Request, timeout: float
    ) -> tuple[int, Mapping[str, str], bytes]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, headers, resp.read()
        except urllib.error.HTTPError as e:
            headers = {k.lower(): v for k, v in e.headers.items()}
            return e.code, headers, e.read()
        except Exception as e:
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.NETWORK,
                message=f"Network error connecting to OpenRouter: {e}",
            ) from e
