from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from elmos_foundry.artifacts import ContentAddressedArtifactStore
from elmos_foundry.canonical import canonical_digest
from elmos_foundry.domain import (
    CertificationStatus,
    EvidenceState,
    GateLevel,
    LifecycleState,
    SkillContract,
)
from elmos_foundry.evidence import EvidenceBoundaryError, EvidenceLedger
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.policies import PolicyEngine
from elmos_foundry.store import FoundryStore


class PolicyEvidenceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.now = 2_000_000_000.0
        self.kernel = ExecutionKernel(clock=lambda: self.now)
        capabilities = (
            "foundry.artifact.read",
            "foundry.artifact.write",
            "foundry.evidence.read",
            "foundry.evidence.write",
            "foundry.skill.execute",
            "foundry.store.read",
            "foundry.store.write",
        )
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-a",
            project_id="project-a",
            actor_id="requester-a",
            environment_id="test-local",
            workspace_digest=canonical_digest({"workspace": "a"}),
            revision_set_id=canonical_digest({"revision": "abc"}),
            purpose="evaluate-foundry",
            capabilities=capabilities,
            ttl_seconds=300,
        )
        self.other_scope = self.kernel.mint_context(
            tenant_id="tenant-b",
            project_id="project-b",
            actor_id="requester-b",
            environment_id="test-local",
            workspace_digest=canonical_digest({"workspace": "b"}),
            revision_set_id=canonical_digest({"revision": "xyz"}),
            purpose="evaluate-foundry",
            capabilities=capabilities,
            ttl_seconds=300,
        )
        self.store = FoundryStore(
            root / "foundry.sqlite3",
            context_verifier=self.kernel.require_context,
            clock=lambda: self.now,
        )
        self.artifacts = ContentAddressedArtifactStore(
            root / "artifacts", context_verifier=self.kernel.require_context
        )
        self.ledger = EvidenceLedger(
            self.kernel, store=self.store, artifact_store=self.artifacts, clock=lambda: self.now
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_skill_policy_requires_host_context_and_real_approval_verifier(self) -> None:
        contract = SkillContract(
            "critical-skill",
            "core",
            "elmos",
            "critical",
            LifecycleState.EVIDENCE_SEALED,
            "1.0.0",
            "sha256:" + "1" * 64,
        )
        policies = PolicyEngine(self.kernel.require_context, clock=lambda: self.now)
        self.assertFalse(
            policies.evaluate_skill_execution(contract, {"human_approved": True})["allowed"]
        )
        approval = {
            "authorized": True,
            "approver_actor_id": "reviewer-b",
            "skill_name": contract.skill_name,
            "approval_digest": "sha256:" + "2" * 64,
            "expires_at": int(self.now) + 60,
        }
        self.assertFalse(
            policies.evaluate_skill_execution(
                contract, {"security_context": self.scope, "human_approval": approval}
            )["allowed"]
        )

    def test_external_model_gate_is_readiness_only(self) -> None:
        decision = PolicyEngine().evaluate_model_promotion(
            GateLevel.E4_PRODUCTION_CERTIFIED, {"regression_count": 0}, True
        )
        self.assertFalse(decision["approved"])
        self.assertTrue(decision["ready_for_external_gate"])
        self.assertEqual(decision["certification_status"], "NOT_CERTIFIED")

    def test_evidence_is_durable_self_attested_unsigned_and_tenant_scoped(self) -> None:
        bundle = self.ledger.seal_evidence_bundle(
            "model-release-1",
            "model_release",
            GateLevel.E1_UNIT_EVAL,
            "PASS",
            [{"name": "unit-eval", "status": "SATISFIED_LOCAL"}],
            {"unit_eval_score": 0.93},
            self.scope,
        )
        self.assertEqual(tuple(bundle.signatures), ())
        self.assertEqual(bundle.evidence_state, EvidenceState.COLLECTED_SELF_ATTESTED)
        self.assertEqual(bundle.certification_status, CertificationStatus.NOT_CERTIFIED)
        self.assertTrue(self.ledger.verify_bundle_integrity(bundle))
        self.assertEqual(self.ledger.get_bundle(bundle.bundle_id, self.scope), bundle)
        self.assertIsNone(self.ledger.get_bundle(bundle.bundle_id, self.other_scope))

    def test_local_ledger_cannot_pass_production_or_run_without_durability(self) -> None:
        with self.assertRaises(EvidenceBoundaryError):
            self.ledger.seal_evidence_bundle(
                "model-release-2",
                "model_release",
                GateLevel.E4_PRODUCTION_CERTIFIED,
                "PASS",
                [],
                {"regression_count": 0},
                self.scope,
            )
        with self.assertRaises(EvidenceBoundaryError):
            EvidenceLedger(self.kernel, clock=lambda: self.now).seal_evidence_bundle(
                "model-release-3",
                "model_release",
                GateLevel.E1_UNIT_EVAL,
                "PASS",
                [],
                {"unit_eval_score": 1.0},
                self.scope,
            )


if __name__ == "__main__":
    unittest.main()
