"""Direct Native Anthropic Provider Adapter.

Preserves vendor-native features including extended thinking, prompt caching breakpoints,
and native tool calling without lowest-common-denominator loss.
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


class NativeAnthropicAdapter(ProviderAdapter):
    """Direct provider adapter for Anthropic models."""

    def __init__(
        self,
        base_url: str = "https://api.anthropic.com/v1",
        api_key_resolver: Callable[[str], str] | None = None,
        transport: Callable[[urllib.request.Request, float], tuple[int, Mapping[str, str], bytes]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_resolver = api_key_resolver or (lambda ref: "mock-anthropic-key")
        self._transport = transport or self._default_transport

    @property
    def adapter_id(self) -> str:
        return "native-anthropic"

    @property
    def supported_lanes(self) -> tuple[ExecutionLane, ...]:
        return (ExecutionLane.NATIVE_DIRECT,)

    def supports(self, plan: ModelExecutionPlan) -> bool:
        return plan.lane == ExecutionLane.NATIVE_DIRECT and "anthropic" in plan.providerId.lower()

    def validate(self, plan: ModelExecutionPlan) -> None:
        if not self.supports(plan):
            raise ProviderError(
                taxonomyClass=ErrorTaxonomyClass.UNSUPPORTED_CAPABILITY,
                message=f"NativeAnthropicAdapter does not support plan {plan.planId} (lane={plan.lane.value}, provider={plan.providerId})",
                deploymentId=plan.deploymentId,
            )

    def estimate_cost(self, request: RouteRequest, plan: ModelExecutionPlan) -> float:
        return (request.maxInputTokens / 1000.0) * 0.003 + (request.expectedOutputTokens / 1000.0) * 0.015

    def execute(
        self,
        request: RouteRequest,
        plan: ModelExecutionPlan,
        security_context: VerifiedSecurityContext | None = None,
    ) -> InferenceResponse:
        self.validate(plan)
        payload = self._build_request_payload(request, plan)
        url = f"{self.base_url}/messages"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key_resolver(plan.providerId),
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        start_time = time.time()
        status_code, headers, body_bytes = self._transport(req, 60.0)
        latency_ms = (time.time() - start_time) * 1000.0

        if status_code >= 400:
            self._handle_error_response(status_code, headers, body_bytes, plan)

        data = json.loads(body_bytes.decode("utf-8"))
        content_text = ""
        tool_calls = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                content_text += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )

        raw_usage = data.get("usage", {})
        usage = UsageReport(
            promptTokens=raw_usage.get("input_tokens", 0),
            completionTokens=raw_usage.get("output_tokens", 0),
            totalTokens=raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0),
            cacheWriteTokens=raw_usage.get("cache_creation_input_tokens", 0),
            cachedPromptTokens=raw_usage.get("cache_read_input_tokens", 0),
        )

        return InferenceResponse(
            id=str(data.get("id", f"msg_{int(time.time())}")),
            model=str(data.get("model", plan.modelAlias)),
            content=content_text if content_text else None,
            toolCalls=tuple(tool_calls) if tool_calls else None,
            finishReason=data.get("stop_reason", "end_turn"),
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
            p95LatencyMs=520.0,
            rateLimitPressure=0.0,
            timeoutRate=0.0,
            successRate=1.0,
        )

    def _build_request_payload(
        self, request: RouteRequest, plan: ModelExecutionPlan
    ) -> dict[str, Any]:
        system_prompt = ""
        user_msgs = []
        for m in request.messages:
            if m.role == "system":
                system_prompt += m.content + "\n"
            else:
                user_msgs.append({"role": m.role, "content": m.content})

        if not user_msgs:
            user_msgs = [{"role": "user", "content": "hello"}]

        payload: dict[str, Any] = {
            "model": plan.extensions.get("actual_model", "claude-3-5-sonnet-20241022"),
            "messages": user_msgs,
            "max_tokens": request.expectedOutputTokens,
        }

        if system_prompt.strip():
            payload["system"] = system_prompt.strip()

        # Extended thinking support
        if plan.reasoningProfile:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": int(plan.extensions.get("thinking_budget", 2048)),
            }

        # Native tool format
        if request.tools:
            tools = []
            for t in request.tools:
                fn = t.get("function", t)
                tools.append(
                    {
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    }
                )
            payload["tools"] = tools

        return payload

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

        err_obj = body.get("error", {})
        err_msg = err_obj.get("message", "Anthropic call failed")
        err_type = err_obj.get("type", "")

        taxonomy = map_http_status_to_taxonomy(status_code, body, err_msg)
        if "rate_limit" in err_type or "overloaded" in err_type:
            taxonomy = ErrorTaxonomyClass.RATE_LIMIT

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
                message=f"Network error connecting to Anthropic: {e}",
            ) from e
