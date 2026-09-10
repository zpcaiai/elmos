"""Chaos and fault injection tests for resilience and fallback verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from elmos_router_industrial.accounting.accounting import BudgetManager
from elmos_router_industrial.adapters.native_openai import NativeOpenAIAdapter
from elmos_router_industrial.adapters.openrouter import OpenRouterAdapter
from elmos_router_industrial.domain.contracts import (
    BudgetEnvelope,
    DataClassification,
    InferenceMessage,
    InferenceResponse,
    RouteRequest,
    TaskClass,
    UsageReport,
    VerifiedSecurityContext,
)
from elmos_router_industrial.domain.errors import ErrorTaxonomyClass, ProviderError
from elmos_router_industrial.orchestrator.master import MasterOrchestrator
from elmos_router_industrial.policy.engine import PolicyEngine
from elmos_router_industrial.registry.registry import DeploymentRegistry

CONFIGS_DIR = Path(__file__).resolve().parents[4] / "skills/subskills/elmos-router-industrial-skillpack/configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path("/Users/stephen/.gemini/antigravity/brain/28d35f92-a69f-4629-8da0-fdda5777b2c7/scratch/elmos-router-industrial-skillpack/configs")


class TestChaosAndFaultInjection(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DeploymentRegistry()
        with open(CONFIGS_DIR / "model-registry.example.yaml", "r", encoding="utf-8") as f:
            self.registry.load_from_yaml(f.read())

        with open(CONFIGS_DIR / "policy.example.yaml", "r", encoding="utf-8") as f:
            self.policy_engine = PolicyEngine.from_yaml(f.read())

        self.budget_manager = BudgetManager()
        self.budget_manager.set_budget("tenant:chaos_tenant", 50.0)

        self.orchestrator = MasterOrchestrator(
            registry=self.registry,
            policy_engine=self.policy_engine,
            budget_manager=self.budget_manager,
        )

        self.req = RouteRequest(
            tenantId="chaos_tenant",
            taskId="task_chaos_01",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.LARGE_REFACTOR,
            dataClassification=(DataClassification.PUBLIC,),
            securityContextRef="sec_chaos",
            capabilityLeaseRef="lease_chaos",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_chaos_001",
            messages=(InferenceMessage(role="user", content="Chaos request test"),),
        )

    def test_injected_429_retry_success(self) -> None:
        call_count = 0

        def flaky_transport(req, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return 429, {"retry-after": "0.01"}, b'{"error": {"message": "Rate limit exceeded"}}'
            body = {
                "id": "chatcmpl-flaky-recovered",
                "model": "gpt-4o",
                "choices": [{"message": {"role": "assistant", "content": "Recovered after retry"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
            return 200, {}, json.dumps(body).encode()

        self.orchestrator.register_adapter(NativeOpenAIAdapter(transport=flaky_transport))

        record = self.orchestrator.execute_inference(self.req)
        self.assertEqual(call_count, 2)
        self.assertEqual(record.response.content, "Recovered after retry")

    def test_injected_500_fallback_to_secondary_deployment(self) -> None:
        # Primary deployment (OpenAI) fails with 500 error permanently
        def broken_openai_transport(req, timeout):
            return 500, {}, b'{"error": {"message": "Internal server outage"}}'

        # Secondary fallback deployment (OpenRouter) succeeds
        def working_openrouter_transport(req, timeout):
            body = {
                "id": "openrouter-fallback-ok",
                "model": "deepseek/deepseek-r1",
                "choices": [{"message": {"role": "assistant", "content": "OpenRouter fallback succeeded"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
            }
            return 200, {}, json.dumps(body).encode()

        self.orchestrator.register_adapter(NativeOpenAIAdapter(transport=broken_openai_transport))
        self.orchestrator.register_adapter(OpenRouterAdapter(transport=working_openrouter_transport))

        record = self.orchestrator.execute_inference(self.req)
        self.assertEqual(record.response.content, "OpenRouter fallback succeeded")


if __name__ == "__main__":
    unittest.main()
