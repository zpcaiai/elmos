"""Unit tests for training eligibility, skill execution, and model promotion policies."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import (
    ConsentStatus,
    DatasetItem,
    GateLevel,
    LifecycleState,
    RightsClass,
    SkillContract,
    TenantScope,
)
from elmos_foundry.evidence import EvidenceLedger
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.policies import PolicyEngine


class PoliciesAndGatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policies = PolicyEngine()
        self.kernel = ExecutionKernel()
        self.evidence = EvidenceLedger(self.kernel)

    def test_training_eligibility_policy(self) -> None:
        # Eligible item
        eligible_item = DatasetItem(
            item_id="item-01",
            dataset_id="ds-01",
            tenant_id="tenant-01",
            split="train",
            input_text="prompt",
            target_text="response",
            metadata={},
            rights_class=RightsClass.INTERNAL,
            consent_status=ConsentStatus.ALLOW,
            quality_score=0.9,
            quarantine=False,
        )
        res = self.policies.evaluate_training_eligibility(eligible_item)
        self.assertTrue(res["eligible"])
        self.assertEqual(res["decision"], "ALLOW")

        # Ineligible due to denied consent
        denied_item = DatasetItem(
            item_id="item-02",
            dataset_id="ds-01",
            tenant_id="tenant-01",
            split="train",
            input_text="prompt",
            target_text="response",
            metadata={},
            rights_class=RightsClass.INTERNAL,
            consent_status=ConsentStatus.DENY,
            quality_score=0.9,
            quarantine=False,
        )
        res_denied = self.policies.evaluate_training_eligibility(denied_item)
        self.assertFalse(res_denied["eligible"])
        self.assertEqual(res_denied["decision"], "DENY")

    def test_skill_execution_policy(self) -> None:
        contract = SkillContract(
            skill_name="high-risk-skill",
            pack="00-foundation",
            owner="elmos",
            risk_class="critical",
            status=LifecycleState.CERTIFIED,
            version="1.0.0",
            content_hash="hash",
        )
        # Without approval -> DENY
        res1 = self.policies.evaluate_skill_execution(contract, {"human_approved": False})
        self.assertFalse(res1["allowed"])

        # With approval -> ALLOW
        res2 = self.policies.evaluate_skill_execution(contract, {"human_approved": True})
        self.assertTrue(res2["allowed"])

    def test_model_promotion_policy_and_evidence_integrity(self) -> None:
        scope = TenantScope(tenant_id="tenant-t1", project_id="proj-p1")
        
        # E4 production gate evaluation
        eval_metrics = {
            "unit_eval_score": 0.95,
            "integration_pass_rate": 0.99,
            "canary_error_rate": 0.001,
            "regression_count": 0,
        }
        res = self.policies.evaluate_model_promotion(
            target_gate=GateLevel.E4_PRODUCTION_CERTIFIED,
            eval_metrics=eval_metrics,
            proof_obligations_satisfied=True,
        )
        self.assertTrue(res["approved"])

        # Evidence bundle sealing and verification
        bundle = self.evidence.seal_evidence_bundle(
            target_id="model-rel-01",
            target_type="model_release",
            gate_level=GateLevel.E4_PRODUCTION_CERTIFIED,
            verdict="PASS",
            proof_obligations=[{"name": "formal_safety", "status": "SATISFIED"}],
            metrics=eval_metrics,
            tenant_scope=scope,
        )
        self.assertTrue(self.evidence.verify_bundle_integrity(bundle))


if __name__ == "__main__":
    unittest.main()
