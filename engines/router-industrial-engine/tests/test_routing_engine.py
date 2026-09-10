"""Tests for the 4-Phase Deterministic Routing Engine and Shadow Router."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from elmos_router_industrial.domain.contracts import (
    BudgetEnvelope,
    DataClassification,
    ExecutionLane,
    RouteRequest,
    TaskClass,
    VerifiedSecurityContext,
)
from elmos_router_industrial.policy.engine import PolicyEngine
from elmos_router_industrial.registry.registry import DeploymentRegistry
from elmos_router_industrial.router.engine import RoutingEngine, ShadowRouter

CONFIGS_DIR = Path(__file__).resolve().parents[4] / "skills/subskills/elmos-router-industrial-skillpack/configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path("/Users/stephen/.gemini/antigravity/brain/28d35f92-a69f-4629-8da0-fdda5777b2c7/scratch/elmos-router-industrial-skillpack/configs")


class TestRoutingEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DeploymentRegistry()
        with open(CONFIGS_DIR / "model-registry.example.yaml", "r", encoding="utf-8") as f:
            self.registry.load_from_yaml(f.read())

        with open(CONFIGS_DIR / "policy.example.yaml", "r", encoding="utf-8") as f:
            self.policy_engine = PolicyEngine.from_yaml(f.read())

        self.routing_engine = RoutingEngine(self.registry, self.policy_engine)
        self.shadow_router = ShadowRouter(self.routing_engine)

        self.fixed_time = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
        self.request = RouteRequest(
            tenantId="tenant_engineering",
            taskId="task_refactor_01",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.LARGE_REFACTOR,
            dataClassification=(DataClassification.INTERNAL, DataClassification.SOURCE_CODE),
            securityContextRef="sec_01",
            capabilityLeaseRef="lease_01",
            budgetEnvelope=BudgetEnvelope("USD", 5.00),
            deadline=self.fixed_time + timedelta(minutes=10),
            idempotencyKey="idem_refactor_01",
            maxInputTokens=8192,
            expectedOutputTokens=2048,
        )

    def test_deterministic_routing_selection(self) -> None:
        sec = VerifiedSecurityContext(
            tenantId="tenant_engineering",
            actorId="architect_alice",
            noTrainingRequired=True,
        )

        plan1, decision1 = self.routing_engine.route(
            self.request, security_context=sec, now=self.fixed_time
        )
        plan2, decision2 = self.routing_engine.route(
            self.request, security_context=sec, now=self.fixed_time
        )

        # Must be 100% deterministic
        self.assertEqual(decision1.selectedDeploymentId, decision2.selectedDeploymentId)
        self.assertEqual(decision1.selectedLane, decision2.selectedLane)
        self.assertEqual(plan1.modelAlias, plan2.modelAlias)
        self.assertEqual(plan1.deploymentId, plan2.deploymentId)
        self.assertEqual(decision1.fallbackDeploymentIds, decision2.fallbackDeploymentIds)

    def test_fallback_graph_generation(self) -> None:
        plan, decision = self.routing_engine.route(
            self.request, now=self.fixed_time
        )
        self.assertTrue(len(decision.candidates) >= 2)
        # Verify selected candidate has score breakdown
        selected_cand = next(
            c for c in decision.candidates if c.deploymentId == decision.selectedDeploymentId
        )
        self.assertTrue(selected_cand.eligible)
        self.assertIsNotNone(selected_cand.score)
        self.assertIsNotNone(selected_cand.scoreBreakdown)

    def test_shadow_router_evaluation(self) -> None:
        diff = self.shadow_router.evaluate_shadow(
            request=self.request,
            baseline_deployment_id="strategic-coding-high-openai-native",
        )
        self.assertIsNotNone(diff.routeDecisionId)
        self.assertEqual(diff.baselineDeploymentId, "strategic-coding-high-openai-native")
        self.assertIsInstance(diff.isDifferent, bool)
        self.assertIsInstance(diff.costDelta, float)


if __name__ == "__main__":
    unittest.main()
