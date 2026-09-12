"""Tests for Provider Adapters (Native, Gateway, OpenRouter, Self-Hosted)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from elmos_router_industrial.adapters.litellm_gateway import LiteLLMGatewayAdapter
from elmos_router_industrial.adapters.native_anthropic import NativeAnthropicAdapter
from elmos_router_industrial.adapters.native_openai import NativeOpenAIAdapter
from elmos_router_industrial.adapters.openrouter import OpenRouterAdapter
from elmos_router_industrial.adapters.self_hosted import SelfHostedAdapter
from elmos_router_industrial.domain.contracts import (
    BudgetEnvelope,
    DataClassification,
    ExecutionLane,
    InferenceMessage,
    ModelExecutionPlan,
    RouteRequest,
    TaskClass,
)
from elmos_router_industrial.domain.errors import ErrorTaxonomyClass, ProviderError


class TestProviderAdapters(unittest.TestCase):
    def setUp(self) -> None:
        self.req = RouteRequest(
            tenantId="tenant_01",
            taskId="task_01",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(DataClassification.INTERNAL,),
            securityContextRef="sec_01",
            capabilityLeaseRef="lease_01",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc),
            idempotencyKey="idem_01",
            messages=(InferenceMessage(role="user", content="def fib(n):"),),
        )

    def test_native_openai_adapter_execution_and_streaming(self) -> None:
        # Mock transport returning valid OpenAI chat completion
        def mock_transport(req, timeout):
            body = {
                "id": "chatcmpl-123",
                "model": "gpt-4o",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "return fibonacci result"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 8,
                    "total_tokens": 23,
                    "completion_tokens_details": {"reasoning_tokens": 4},
                },
            }
            return 200, {"x-ratelimit-remaining": "100"}, json.dumps(body).encode()

        adapter = NativeOpenAIAdapter(transport=mock_transport)
        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId="p_01",
            tenantId="t_01",
            taskId="tk_01",
            stepId="st_01",
            modelAlias="gpt-4o",
            deploymentId="dep_openai",
            lane=ExecutionLane.NATIVE_DIRECT,
            providerId="openai-direct",
            deadlineAt=datetime.now(timezone.utc).isoformat(),
            policyVersion="1",
            registryVersion="1",
            securityContextHash="sec",
            capabilityLeaseHash="lease",
            budget=BudgetEnvelope("USD", 1.0),
        )

        resp = adapter.execute(self.req, plan)
        self.assertEqual(resp.id, "chatcmpl-123")
        self.assertEqual(resp.content, "return fibonacci result")
        self.assertEqual(resp.usage.reasoningTokens, 4)

        # Stream
        chunks = list(adapter.stream(self.req, plan))
        self.assertTrue(len(chunks) > 0)
        self.assertTrue(chunks[-1].isTerminal)

    def test_native_anthropic_adapter_execution(self) -> None:
        def mock_transport(req, timeout):
            body = {
                "id": "msg_anthropic_456",
                "model": "claude-3-5-sonnet",
                "content": [{"type": "text", "text": "Anthropic response"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 5,
                },
            }
            return 200, {}, json.dumps(body).encode()

        adapter = NativeAnthropicAdapter(transport=mock_transport)
        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId="p_02",
            tenantId="t_01",
            taskId="tk_01",
            stepId="st_01",
            modelAlias="claude-3-5-sonnet",
            deploymentId="dep_anthropic",
            lane=ExecutionLane.NATIVE_DIRECT,
            providerId="anthropic-direct",
            deadlineAt=datetime.now(timezone.utc).isoformat(),
            policyVersion="1",
            registryVersion="1",
            securityContextHash="sec",
            capabilityLeaseHash="lease",
            budget=BudgetEnvelope("USD", 1.0),
        )

        resp = adapter.execute(self.req, plan)
        self.assertEqual(resp.id, "msg_anthropic_456")
        self.assertEqual(resp.content, "Anthropic response")
        self.assertEqual(resp.usage.cachedPromptTokens, 5)

    def test_litellm_gateway_adapter_execution(self) -> None:
        def mock_transport(req, timeout):
            body = {
                "id": "litellm_gw_789",
                "model": "unified-coding",
                "choices": [{"message": {"role": "assistant", "content": "Gateway response"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            return 200, {}, json.dumps(body).encode()

        adapter = LiteLLMGatewayAdapter(transport=mock_transport)
        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId="p_03",
            tenantId="t_01",
            taskId="tk_01",
            stepId="st_01",
            modelAlias="unified-coding",
            deploymentId="dep_litellm",
            lane=ExecutionLane.LITELLM,
            providerId="litellm-proxy",
            deadlineAt=datetime.now(timezone.utc).isoformat(),
            policyVersion="1",
            registryVersion="1",
            securityContextHash="sec",
            capabilityLeaseHash="lease",
            budget=BudgetEnvelope("USD", 1.0),
        )

        resp = adapter.execute(self.req, plan)
        self.assertEqual(resp.id, "litellm_gw_789")
        self.assertEqual(resp.content, "Gateway response")

    def test_openrouter_adapter_zdr_payload(self) -> None:
        recorded_req = None

        def mock_transport(req, timeout):
            nonlocal recorded_req
            recorded_req = req
            body = {
                "id": "openrouter_999",
                "choices": [{"message": {"role": "assistant", "content": "OpenRouter reply"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            }
            return 200, {}, json.dumps(body).encode()

        adapter = OpenRouterAdapter(transport=mock_transport)
        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId="p_04",
            tenantId="t_01",
            taskId="tk_01",
            stepId="st_01",
            modelAlias="deepseek/deepseek-r1",
            deploymentId="dep_openrouter",
            lane=ExecutionLane.OPENROUTER,
            providerId="openrouter",
            deadlineAt=datetime.now(timezone.utc).isoformat(),
            policyVersion="1",
            registryVersion="1",
            securityContextHash="sec",
            capabilityLeaseHash="lease",
            budget=BudgetEnvelope("USD", 1.0),
            extensions={"require_zdr": True, "allowed_openrouter_providers": ("deepinfra",)},
        )

        resp = adapter.execute(self.req, plan)
        self.assertEqual(resp.id, "openrouter_999")
        # Check payload has provider ZDR setting
        sent_body = json.loads(recorded_req.data.decode())
        self.assertEqual(sent_body["provider"]["data_collection"], "deny")
        self.assertEqual(sent_body["provider"]["order"], ["deepinfra"])

    def test_adapter_error_handling(self) -> None:
        def error_transport(req, timeout):
            return 429, {"retry-after": "5"}, b'{"error": {"message": "Rate limit exceeded"}}'

        adapter = NativeOpenAIAdapter(transport=error_transport)
        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId="p_05",
            tenantId="t_01",
            taskId="tk_01",
            stepId="st_01",
            modelAlias="gpt-4o",
            deploymentId="dep_openai",
            lane=ExecutionLane.NATIVE_DIRECT,
            providerId="openai-direct",
            deadlineAt=datetime.now(timezone.utc).isoformat(),
            policyVersion="1",
            registryVersion="1",
            securityContextHash="sec",
            capabilityLeaseHash="lease",
            budget=BudgetEnvelope("USD", 1.0),
        )

        with self.assertRaises(ProviderError) as ctx:
            adapter.execute(self.req, plan)

        self.assertEqual(ctx.exception.taxonomyClass, ErrorTaxonomyClass.RATE_LIMIT)
        self.assertEqual(ctx.exception.statusCode, 429)
        self.assertEqual(ctx.exception.retryAfterSeconds, 5.0)


if __name__ == "__main__":
    unittest.main()
