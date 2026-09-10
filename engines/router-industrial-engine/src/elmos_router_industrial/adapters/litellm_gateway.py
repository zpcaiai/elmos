"""LiteLLM Replaceable Gateway Adapter.

Provides protocol normalization and gateway defense-in-depth without allowing
LiteLLM to become the source of semantic routing truth or policy evaluation.
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


class LiteLLMGatewayAdapter(ProviderAdapter):
    """Gateway adapter interacting with LiteLLM Proxy."""

    def __init__(
        self,
        gateway_url: str = "http://localhost:4000",
        master_key_resolver: Callable[[], str] | None = None,
        transport: Callable[[urllib.request.Request, float], tuple[int, Mapping[str, str], bytes]] | None = None,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.master_key_resolver = master_key_resolver or (lambda: "sk-litellm-master-key")
        self._transport = transport or self._default_transport

    @property
    def adapter_id(self) -> str:
        return "litellm-gateway"

    @property
    def supported_lanes(self) -> tuple[ExecutionLane, ...]:
        return (ExecutionLane.LITELLM,)

    def supports(self, plan: ModelExecutionPlan) -> bool:
        return plan.lane == ExecutionLane.LITELLM

    def validate(self, plan: ModelExecutionPlan) -> None:
        if not self.supports(plan):
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.UNSUPPORTED_CAPABILITY,
                message=f"LiteLLMGatewayAdapter does not support plan {plan.planId} (lane={plan.lane.value})",
                deploymentId=plan.deploymentId,
            )

    def estimate_cost(self, request: RouteRequest, plan: ModelExecutionPlan) -> float:
        return (request.maxInputTokens / 1000.0) * 0.002 + (request.expectedOutputTokens / 1000.0) * 0.008

    def execute(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> InferenceResponse:
        self.validate(plan)
        url = f"{self.gateway_url}/chat/completions"

        # LiteLLM receives the exact model alias resolved by Elmos
        payload = {
            "model": plan.modelAlias,
            "messages": [m.to_dict() for m in request.messages] or [{"role": "user", "content": "hello"}],
            "max_tokens": request.expectedOutputTokens,
            "user": request.tenantId,
            "metadata": {
                "elmos_plan_id": plan.planId,
                "elmos_task_id": plan.taskId,
                "elmos_deployment_id": plan.deploymentId,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.master_key_resolver()}",
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
            id=str(data.get("id", f"gw_{int(time.time())}")),
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
            availability=1.0,
            p95LatencyMs=350.0,
            rateLimitPressure=0.0,
            timeoutRate=0.0,
            successRate=1.0,
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

        err_msg = body.get("error", {}).get("message", "LiteLLM Gateway call failed")
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
                message=f"Network error connecting to LiteLLM Gateway: {e}",
            ) from e
