"""Self-Hosted OpenAI-Compatible Provider Adapter.

Enables self-hosted inference clusters (vLLM, SGLang, TGI) without changing
Elmos domain contracts or routing policies.
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


class SelfHostedAdapter(ProviderAdapter):
    """Adapter for self-hosted OpenAI-compatible inference clusters."""

    def __init__(
        self,
        cluster_url: str = "http://localhost:8000/v1",
        api_key: str = "cluster-local-key",
        transport: Callable[[urllib.request.Request, float], tuple[int, Mapping[str, str], bytes]] | None = None,
    ) -> None:
        self.cluster_url = cluster_url.rstrip("/")
        self.api_key = api_key
        self._transport = transport or self._default_transport

    @property
    def adapter_id(self) -> str:
        return "self-hosted"

    @property
    def supported_lanes(self) -> tuple[ExecutionLane, ...]:
        return (ExecutionLane.SELF_HOSTED,)

    def supports(self, plan: ModelExecutionPlan) -> bool:
        return plan.lane == ExecutionLane.SELF_HOSTED

    def validate(self, plan: ModelExecutionPlan) -> None:
        if not self.supports(plan):
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.UNSUPPORTED_CAPABILITY,
                message=f"SelfHostedAdapter does not support plan {plan.planId} (lane={plan.lane.value})",
                deploymentId=plan.deploymentId,
            )

    def estimate_cost(self, request: RouteRequest, plan: ModelExecutionPlan) -> float:
        return 0.0001  # Self-hosted infrastructure cost model

    def execute(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> InferenceResponse:
        self.validate(plan)
        url = f"{self.cluster_url}/chat/completions"

        payload = {
            "model": plan.extensions.get("actual_model", plan.modelAlias),
            "messages": [m.to_dict() for m in request.messages] or [{"role": "user", "content": "hello"}],
            "max_tokens": request.expectedOutputTokens,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
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
            id=str(data.get("id", f"selfhosted_{int(time.time())}")),
            model=str(data.get("model", plan.modelAlias)),
            content=msg.get("content"),
            toolCalls=tuple(msg["tool_calls"]) if "tool_calls" in msg else None,
            finishReason=choice.get("finish_reason", "stop"),
            usage=usage,
            rawProviderResponseId=data.get("id"),
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
            p95LatencyMs=120.0,
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

        err_msg = body.get("error", {}).get("message", "Self-hosted inference cluster error")
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
                message=f"Network error connecting to self-hosted cluster: {e}",
            ) from e
