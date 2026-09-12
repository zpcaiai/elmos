"""Tests for Master Orchestrator end-to-end execution flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from elmos_router_industrial.accounting.accounting import BudgetManager
from elmos_router_industrial.adapters.native_openai import NativeOpenAIAdapter
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
from elmos_router_industrial.orchestrator.master import MasterOrchestrator, OrchestratorFeatureFlags
from elmos_router_industrial.policy.engine import PolicyEngine
from elmos_router_industrial.registry.registry import DeploymentRegistry

CONFIGS_DIR = Path(__file__).resolve().parents[4] / "skills/subskills/elmos-router-industrial-skillpack/configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path("/Users/stephen/.gemini/antigravity/brain/28d35f92-a69f-4629-8da0-fdda5777b2c7/scratch/elmos-router-industrial-skillpack/configs")


class TestMasterOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DeploymentRegistry()
        with open(CONFIGS_DIR / "model-registry.example.yaml", "r", encoding="utf-8") as f:
            self.registry.load_from_yaml(f.read())

        with open(CONFIGS_DIR / "policy.example.yaml", "r", encoding="utf-8") as f:
            self.policy_engine = PolicyEngine.from_yaml(f.read())

        self.budget_manager = BudgetManager()
        self.budget_manager.set_budget("tenant:tenant_prod", 100.0)

        self.orchestrator = MasterOrchestrator(
            registry=self.registry,
            policy_engine=self.policy_engine,
            budget_manager=self.budget_manager,
        )

        # Mock adapter transport to avoid external HTTP calls
        def mock_transport(req, timeout):
            body = {
                "id": "chatcmpl-mock-orch",
                "model": "gpt-4o",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Master Orchestrator response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
            import json
            return 200, {}, json.dumps(body).encode()

        self.orchestrator.register_adapter(NativeOpenAIAdapter(transport=mock_transport))

        self.req = RouteRequest(
            tenantId="tenant_prod",
            taskId="task_master_01",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.LARGE_REFACTOR,
            dataClassification=(DataClassification.INTERNAL, DataClassification.SOURCE_CODE),
            securityContextRef="sec_master",
            capabilityLeaseRef="lease_master",
            budgetEnvelope=BudgetEnvelope("USD", 10.0),
            deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotencyKey="idem_master_001",
            messages=(InferenceMessage(role="user", content="Refactor this module"),),
        )

    def test_end_to_end_inference_execution(self) -> None:
        sec = VerifiedSecurityContext(
            tenantId="tenant_prod",
            actorId="actor_lead",
            noTrainingRequired=True,
        )

        record = self.orchestrator.execute_inference(self.req, security_context=sec)
        self.assertIsNotNone(record)
        self.assertEqual(record.taskId, "task_master_01")
        self.assertEqual(record.stepId, "step_01")
        self.assertEqual(record.response.content, "Master Orchestrator response")

        # Verify Cost Ledger
        events = self.orchestrator.cost_ledger.get_events_for_tenant("tenant_prod")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].totalTokens, 150)
        self.assertTrue(events[0].reconciledCost > 0)

        # Verify Metrics
        self.assertTrue(self.orchestrator.metrics.get_counter("router.requests.total") >= 1)
        self.assertTrue(self.orchestrator.metrics.get_counter("router.commits.success") >= 1)

    def test_idempotent_duplicate_call(self) -> None:
        sec = VerifiedSecurityContext(tenantId="tenant_prod", actorId="actor_lead", noTrainingRequired=True)

        rec1 = self.orchestrator.execute_inference(self.req, security_context=sec)
        rec2 = self.orchestrator.execute_inference(self.req, security_context=sec)

        self.assertEqual(rec1.resultHash, rec2.resultHash)
        self.assertEqual(rec1.attemptId, rec2.attemptId)
        self.assertEqual(self.orchestrator.metrics.get_counter("router.commits.idempotent_hit"), 1)

    def test_legacy_fallback_when_router_v2_disabled(self) -> None:
        flags = OrchestratorFeatureFlags(router_v2_enabled=False)

        def mock_legacy(request):
            return InferenceResponse(
                id="legacy_resp",
                model="legacy-model",
                content="Legacy route response",
                usage=UsageReport(50, 25, 75),
            )

        orch = MasterOrchestrator(
            feature_flags=flags,
            legacy_router_fallback=mock_legacy,
        )
        record = orch.execute_inference(self.req)
        self.assertEqual(record.response.content, "Legacy route response")


if __name__ == "__main__":
    unittest.main()
