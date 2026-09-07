"""Conservative policy decisions and non-certifying gate behavior."""

from __future__ import annotations

import time
import unittest

from elmos_foundry.domain import (
    ConsentStatus,
    DatasetItem,
    GateLevel,
    LifecycleState,
    RightsClass,
    SkillContract,
)
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.policies import PolicyEngine


def digest(character: str) -> str:
    return "sha256:" + character * 64


class PoliciesAndGatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-01",
            project_id="project-01",
            actor_id="requester",
            environment_id="test",
            workspace_digest=digest("a"),
            revision_set_id=digest("b"),
            purpose="test-purpose",
            capabilities=(
                "foundry.skill.execute",
                "foundry.training.conditional",
                "foundry.training.use",
            ),
            ttl_seconds=600,
        )

    def test_training_eligibility_is_consent_and_context_bound(self) -> None:
        engine = PolicyEngine(self.kernel.require_context)
        item = DatasetItem(
            item_id="item-01",
            dataset_id="dataset-01",
            tenant_id="tenant-01",
            project_id="project-01",
            split="train",
            input_text="prompt",
            target_text="response",
            metadata={},
            rights_class=RightsClass.INTERNAL,
            consent_status=ConsentStatus.CONDITIONAL,
            quality_score=0.9,
        )
        denied = engine.evaluate_training_eligibility(item, purpose="test-purpose")
        self.assertEqual(denied["decision"], "DENY")
        allowed = engine.evaluate_training_eligibility(
            item, security_context=self.scope, purpose="test-purpose"
        )
        self.assertEqual(allowed["decision"], "ALLOW")

        foreign_scope = self.kernel.mint_context(
            tenant_id="tenant-02",
            project_id="project-02",
            actor_id="requester",
            environment_id="test",
            workspace_digest=digest("c"),
            revision_set_id=digest("d"),
            purpose="test-purpose",
            capabilities=("foundry.training.conditional", "foundry.training.use"),
            ttl_seconds=600,
        )
        foreign = engine.evaluate_training_eligibility(
            item, security_context=foreign_scope, purpose="test-purpose"
        )
        self.assertEqual(foreign["decision"], "DENY")
        self.assertTrue(any("tenant/project" in item for item in foreign["violations"]))

    def test_allow_consent_still_requires_matching_training_lease(self) -> None:
        engine = PolicyEngine(self.kernel.require_context)
        item = DatasetItem(
            item_id="item-allow",
            dataset_id="dataset-01",
            tenant_id="tenant-01",
            project_id="project-01",
            split="train",
            input_text="prompt",
            target_text="response",
            metadata={},
            rights_class=RightsClass.INTERNAL,
            consent_status=ConsentStatus.ALLOW,
            quality_score=0.9,
        )
        self.assertEqual(
            engine.evaluate_training_eligibility(item, purpose="test-purpose")["decision"],
            "DENY",
        )
        self.assertEqual(
            engine.evaluate_training_eligibility(
                item, security_context=self.scope, purpose="test-purpose"
            )["decision"],
            "ALLOW",
        )

    def test_critical_skill_rejects_boolean_self_approval(self) -> None:
        contract = SkillContract(
            skill_name="critical-skill",
            pack="pack-00",
            owner="elmos",
            risk_class="critical",
            status=LifecycleState.PLANNED,
            version="1.0.0",
            content_hash="source-hash",
        )
        engine = PolicyEngine(self.kernel.require_context)
        decision = engine.evaluate_skill_execution(
            contract,
            {
                "security_context": self.scope,
                "purpose": "test-purpose",
                "human_approved": True,
            },
        )
        self.assertEqual(decision["decision"], "DENY")
        self.assertTrue(any("verifier-backed" in item for item in decision["violations"]))

    def test_external_gate_is_readiness_not_local_approval(self) -> None:
        decision = PolicyEngine().evaluate_model_promotion(
            GateLevel.E4_PRODUCTION_CERTIFIED,
            {"regression_count": 0},
            proof_obligations_satisfied=True,
        )
        self.assertFalse(decision["approved"])
        self.assertTrue(decision["ready_for_external_gate"])
        self.assertEqual(decision["decision"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(decision["external_evidence_status"], "NOT_RUN")
        self.assertEqual(decision["certification_status"], "NOT_CERTIFIED")

    def test_trusted_approval_requires_separate_actor_and_verifier(self) -> None:
        contract = SkillContract(
            "critical-skill",
            "pack-00",
            "elmos",
            "critical",
            LifecycleState.PLANNED,
            "1.0.0",
            "source-hash",
        )
        engine = PolicyEngine(
            self.kernel.require_context,
            approval_verifier=lambda approval, scope, target: (
                approval["skill_name"] == target.skill_name and scope.actor_id == "requester"
            ),
        )
        decision = engine.evaluate_skill_execution(
            contract,
            {
                "security_context": self.scope,
                "purpose": "test-purpose",
                "human_approval": {
                    "approver_actor_id": "reviewer",
                    "skill_name": "critical-skill",
                    "approval_digest": digest("c"),
                    "expires_at": int(time.time()) + 300,
                    "authorized": True,
                },
            },
        )
        self.assertEqual(decision["decision"], "ALLOW")


if __name__ == "__main__":
    unittest.main()
