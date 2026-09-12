"""Tests for domain contracts and schema validation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from elmos_router_industrial.domain.contracts import (
    BudgetEnvelope,
    CandidateEvaluation,
    CapabilityLease,
    DataClassification,
    ExecutionLane,
    InferenceMessage,
    InferenceRequest,
    InferenceResponse,
    ModelExecutionPlan,
    RouteDecision,
    RouteRequest,
    ScoreBreakdown,
    TaskClass,
    UsageReport,
    VerifiedSecurityContext,
    validate_model_execution_plan,
    validate_route_decision,
)

ROOT = Path(__file__).resolve().parents[4]
SCHEMAS_DIR = ROOT / "skills/subskills/elmos-router-industrial-skillpack/contracts"
if not SCHEMAS_DIR.exists():
    SCHEMAS_DIR = Path("/Users/stephen/.gemini/antigravity/brain/28d35f92-a69f-4629-8da0-fdda5777b2c7/scratch/elmos-router-industrial-skillpack/contracts")


class TestDomainContracts(unittest.TestCase):
    def setUp(self) -> None:
        with open(SCHEMAS_DIR / "model-execution-plan.schema.json", "r", encoding="utf-8") as f:
            self.plan_schema = json.load(f)
        with open(SCHEMAS_DIR / "route-decision.schema.json", "r", encoding="utf-8") as f:
            self.decision_schema = json.load(f)

    def test_model_execution_plan_schema_conformance(self) -> None:
        plan = ModelExecutionPlan(
            schemaVersion="1",
            planId="plan_12345",
            tenantId="tenant_alpha",
            taskId="task_001",
            stepId="step_01",
            modelAlias="strategic-coding-high",
            deploymentId="strategic-coding-high-openai-native",
            lane=ExecutionLane.NATIVE_DIRECT,
            providerId="openai-direct",
            deadlineAt=datetime.now(timezone.utc).isoformat(),
            policyVersion="2026-09-09.1",
            registryVersion="2026-09-09.1",
            securityContextHash="a" * 64,
            capabilityLeaseHash="b" * 64,
            budget=BudgetEnvelope(currency="USD", maxCost=1.50),
            fallbacks=("strategic-coding-high-openrouter",),
            requiredCapabilities=("coding", "reasoning"),
        )
        plan_dict = plan.to_dict()
        # Should not raise
        validate_model_execution_plan(plan_dict, self.plan_schema)

        # Roundtrip JSON
        json_str = plan.to_json()
        restored = ModelExecutionPlan.from_dict(json.loads(json_str))
        self.assertEqual(restored.planId, plan.planId)
        self.assertEqual(restored.lane, ExecutionLane.NATIVE_DIRECT)
        self.assertEqual(restored.budget.maxCost, 1.50)

    def test_route_decision_schema_conformance(self) -> None:
        decision = RouteDecision(
            schemaVersion="1",
            decisionId="dec_98765",
            selectedDeploymentId="strategic-coding-high-openai-native",
            selectedLane=ExecutionLane.NATIVE_DIRECT,
            policyVersion="2026-09-09.1",
            registryVersion="2026-09-09.1",
            candidates=(
                CandidateEvaluation(
                    deploymentId="strategic-coding-high-openai-native",
                    eligible=True,
                    score=0.952,
                    scoreBreakdown=ScoreBreakdown(
                        capabilityFit=0.98,
                        taskBenchmarkQuality=0.96,
                        reliabilityHealth=1.0,
                        expectedLatency=0.9,
                        estimatedCost=0.95,
                    ),
                ),
                CandidateEvaluation(
                    deploymentId="strategic-coding-high-openrouter",
                    eligible=False,
                    denialReasons=("Requires Zero Data Retention",),
                ),
            ),
            fallbackDeploymentIds=("strategic-coding-high-openrouter",),
            decidedAt=datetime.now(timezone.utc).isoformat(),
        )
        decision_dict = decision.to_dict()
        # Should not raise
        validate_route_decision(decision_dict, self.decision_schema)

        # Roundtrip JSON
        json_str = decision.to_json()
        restored = RouteDecision.from_dict(json.loads(json_str))
        self.assertEqual(restored.decisionId, decision.decisionId)
        self.assertEqual(len(restored.candidates), 2)
        self.assertFalse(restored.candidates[1].eligible)

    def test_security_context_and_lease_digests(self) -> None:
        sec = VerifiedSecurityContext(
            tenantId="t_001",
            actorId="actor_admin",
            roles=("engineer", "reviewer"),
            dataClassifications=(DataClassification.SOURCE_CODE, DataClassification.CONFIDENTIAL),
            noTrainingRequired=True,
            zeroDataRetentionRequired=True,
        )
        h1 = sec.digest()
        self.assertEqual(len(h1), 64)
        # Deterministic hash
        self.assertEqual(h1, sec.digest())

        lease = CapabilityLease(
            leaseId="lease_abc",
            tenantId="t_001",
            expiresAt=datetime(2028, 1, 1, tzinfo=timezone.utc),
            allowedCapabilities=("coding", "refactoring"),
        )
        lh = lease.digest()
        self.assertEqual(len(lh), 64)
        self.assertTrue(lease.is_valid(datetime(2026, 9, 10, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
