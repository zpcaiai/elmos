from __future__ import annotations

import base64
from dataclasses import replace
import unittest
from datetime import UTC, datetime, timedelta

from elmos_proof_harness.canonical import digest_bytes
from elmos_proof_harness.certification import (
    CertificationService,
    ExternalSignatureReceipt,
    TrustedVerifierRegistration,
)
from elmos_proof_harness.contracts import (
    CertificationStatus,
    EvidenceProducer,
    GateDecision,
    GateResult,
    ProofObligation,
    ProofResult,
    ProofStatus,
    RevisionSet,
    SecurityContext,
    Severity,
    ToolIdentity,
)
from elmos_proof_harness.errors import (
    AuthorizationError,
    CertificationError,
    ConflictError,
    ValidationError,
    WorkflowError,
)
from elmos_proof_harness.evidence import EvidenceService
from elmos_proof_harness.proof_graph import ProofObligationGraph
from elmos_proof_harness.store import SQLiteStore
from elmos_proof_harness.workflow import RunState, WorkflowEngine


NOW = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)


def d(value: str, domain: str = "test") -> str:
    return digest_bytes(value.encode(), domain=domain)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore(":memory:")
        self.base = SecurityContext("tenant-a", "project-a", "actor-a")
        self.store.register_scope(self.base, now=NOW)
        self.engine = WorkflowEngine(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_checkpoint_recovery_increments_epoch_and_fence(self) -> None:
        created = self.engine.create(self.base, run_id="run-1", revision_set_id="revision-set-1", now=NOW)
        self.assertEqual(NOW, self.store.get_run(self.base, "run-1").updated_at)
        run_context = self.base.for_run("run-1")
        with self.assertRaises(ConflictError) as stale_acquire:
            self.engine.acquire(
                run_context.for_run("run-1", fencing_generation=2),
                owner_id="worker-stale",
                expected_sequence=created.sequence,
                ttl_seconds=10,
                now=NOW,
            )
        self.assertEqual("STALE_FENCE", stale_acquire.exception.code)
        lease = self.engine.acquire(run_context, owner_id="worker-1", expected_sequence=created.sequence, ttl_seconds=10, now=NOW)
        active = run_context.for_run(
            "run-1", execution_epoch=lease.execution_epoch, fencing_generation=lease.fencing_generation
        )
        admitted = self.engine.transition(active, RunState.ADMITTED, expected_sequence=lease.sequence, lease_token=lease.token, now=NOW)
        planning = self.engine.transition(active, RunState.PLANNING, expected_sequence=admitted.sequence, lease_token=lease.token, now=NOW)
        executing = self.engine.transition(active, RunState.EXECUTING, expected_sequence=planning.sequence, lease_token=lease.token, now=NOW)
        checkpoint = self.engine.checkpoint(
            active,
            b'{"cursor":42}',
            expected_sequence=executing.sequence,
            lease_token=lease.token,
            checkpoint_id="checkpoint-1",
            now=NOW,
        )
        other = SecurityContext("tenant-a", "project-a", "actor-b")
        self.store.register_scope(other, now=NOW)
        with self.assertRaises(AuthorizationError) as private_checkpoint:
            self.store.get_checkpoint(other, "checkpoint-1")
        self.assertEqual("RUN_ACTOR_MISMATCH", private_checkpoint.exception.code)
        recovered = self.engine.recover(
            active,
            owner_id="worker-2",
            expected_sequence=checkpoint.sequence,
            ttl_seconds=60,
            now=NOW + timedelta(seconds=11),
        )
        self.assertEqual(b'{"cursor":42}', recovered.checkpoint_payload)
        self.assertEqual(active.execution_epoch + 1, recovered.context.execution_epoch)
        self.assertEqual(active.fencing_generation + 1, recovered.context.fencing_generation)
        self.assertEqual(RunState.RESUMING, recovered.run.state)
        with self.assertRaises(ConflictError) as stale:
            self.engine.transition(
                active,
                RunState.EXECUTING,
                expected_sequence=recovered.run.sequence,
                lease_token=lease.token,
                now=NOW + timedelta(seconds=12),
            )
        self.assertIn(stale.exception.code, {"STALE_EPOCH", "STALE_FENCE"})

    def test_run_actor_binding_is_fail_closed(self) -> None:
        created = self.engine.create(self.base, run_id="run-private", revision_set_id="revision-set-1", now=NOW)
        other = SecurityContext("tenant-a", "project-a", "actor-b")
        self.store.register_scope(other, now=NOW)
        with self.assertRaises(AuthorizationError) as raised:
            self.store.get_run(other, "run-private")
        self.assertEqual("RUN_ACTOR_MISMATCH", raised.exception.code)
        with self.assertRaises(AuthorizationError):
            self.engine.acquire(
                other.for_run("run-private"),
                owner_id="worker-b",
                expected_sequence=created.sequence,
                now=NOW,
            )

    def test_external_effect_is_lease_fenced_and_idempotent(self) -> None:
        created = self.engine.create(self.base, run_id="run-effect", revision_set_id="revision-set-1", now=NOW)
        run_context = self.base.for_run("run-effect")
        lease = self.engine.acquire(run_context, owner_id="worker-1", expected_sequence=created.sequence, now=NOW)
        active = run_context.for_run(
            "run-effect", execution_epoch=lease.execution_epoch, fencing_generation=lease.fencing_generation
        )
        admitted = self.engine.transition(
            active, RunState.ADMITTED, expected_sequence=lease.sequence, lease_token=lease.token, now=NOW
        )
        planning = self.engine.transition(
            active, RunState.PLANNING, expected_sequence=admitted.sequence, lease_token=lease.token, now=NOW
        )
        executing = self.engine.transition(
            active, RunState.EXECUTING, expected_sequence=planning.sequence, lease_token=lease.token, now=NOW
        )
        effect = self.store.start_external_effect(
            active,
            effect_id="effect-1",
            provider="scm",
            operation="create-review",
            idempotency_key="effect-key-1",
            request={"revision": "abc123"},
            reconciliation_strategy="provider-status",
            lease_token=lease.token,
            now=NOW,
        )
        replay = self.store.start_external_effect(
            active,
            effect_id="effect-ignored-on-replay",
            provider="scm",
            operation="create-review",
            idempotency_key="effect-key-1",
            request={"revision": "abc123"},
            reconciliation_strategy="provider-status",
            lease_token=lease.token,
            now=NOW,
        )
        self.assertEqual(effect, replay)
        self.assertEqual(active.execution_epoch, effect.execution_epoch)
        self.assertEqual(active.fencing_generation, effect.fencing_generation)
        with self.assertRaises(ConflictError) as reused:
            self.store.start_external_effect(
                active,
                effect_id="effect-2",
                provider="scm",
                operation="create-review",
                idempotency_key="effect-key-1",
                request={"revision": "different"},
                reconciliation_strategy="provider-status",
                lease_token=lease.token,
                now=NOW,
            )
        self.assertEqual("IDEMPOTENCY_CONFLICT", reused.exception.code)
        stale = active.for_run("run-effect", fencing_generation=active.fencing_generation - 1)
        with self.assertRaises(ConflictError) as stale_reconcile:
            self.store.reconcile_external_effect(
                stale,
                effect_id="effect-1",
                target_state="UNKNOWN_RESULT",
                expected_version=0,
                detail={"reason": "provider timed out"},
                lease_token=lease.token,
                now=NOW,
            )
        self.assertEqual("STALE_FENCE", stale_reconcile.exception.code)
        reconciled = self.store.reconcile_external_effect(
            active,
            effect_id="effect-1",
            target_state="UNKNOWN_RESULT",
            expected_version=0,
            detail={"reason": "provider timed out"},
            lease_token=lease.token,
            now=NOW,
        )
        self.assertEqual("UNKNOWN_RESULT", reconciled.state)
        self.assertEqual(1, reconciled.version)
        with self.assertRaises(ConflictError) as premature_close:
            self.store.reconcile_external_effect(
                active,
                effect_id="effect-1",
                target_state="RECONCILED",
                expected_version=reconciled.version,
                detail={"reason": "outcome is still unknown"},
                lease_token=lease.token,
                now=NOW,
            )
        self.assertEqual("RECONCILIATION_TRANSITION_INVALID", premature_close.exception.code)
        verifying = self.engine.transition(
            active, RunState.VERIFYING, expected_sequence=executing.sequence, lease_token=lease.token, now=NOW
        )
        certifying = self.engine.transition(
            active, RunState.CERTIFYING, expected_sequence=verifying.sequence, lease_token=lease.token, now=NOW
        )
        with self.assertRaises(WorkflowError) as unsettled:
            self.engine.transition(
                active, RunState.COMPLETED, expected_sequence=certifying.sequence, lease_token=lease.token, now=NOW
            )
        self.assertEqual("SIDE_EFFECTS_UNSETTLED", unsettled.exception.code)

    def test_terminal_run_cannot_reacquire_a_lease(self) -> None:
        created = self.engine.create(self.base, run_id="run-terminal", revision_set_id="revision-set-1", now=NOW)
        run_context = self.base.for_run("run-terminal")
        lease = self.engine.acquire(run_context, owner_id="worker-1", expected_sequence=created.sequence, now=NOW)
        active = run_context.for_run(
            "run-terminal", execution_epoch=lease.execution_epoch, fencing_generation=lease.fencing_generation
        )
        cancelled = self.engine.cancel(active, expected_sequence=lease.sequence, lease_token=lease.token, now=NOW)
        with self.assertRaises(ConflictError) as terminal:
            self.engine.acquire(
                active,
                owner_id="worker-1",
                expected_sequence=cancelled.sequence,
                now=NOW,
            )
        self.assertEqual("RUN_TERMINAL", terminal.exception.code)


class CertificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore(":memory:")
        self.context = SecurityContext("tenant-a", "project-a", "builder-a")
        self.reviewer = SecurityContext("tenant-a", "project-a", "reviewer-a")
        self.store.register_scope(self.context, now=NOW)
        self.store.register_scope(self.reviewer, now=NOW)
        self.evidence = EvidenceService(self.store)
        self.subject = d("subject", "repository-revision")
        self.environment = d("environment", "environment")
        self.tool_digest = d("tool", "tool-binary")
        self.tool = ToolIdentity("checker", "1", self.tool_digest, "1", d("encoder", "encoder"))
        producer = EvidenceProducer(
            "execution-verifier", "VERIFIER", "checker", self.tool_digest, self.environment, independent=True
        )
        self.evidence.record_bytes(
            self.reviewer,
            subject_revision=self.subject,
            kind="proof",
            evidence_class="solver-model-result",
            scope="repository",
            content=b"verified",
            media_type="application/octet-stream",
            producer=producer,
            evidence_id="proof-evidence",
            artifact_id="proof-artifact",
            created_at=NOW,
        )
        obligation = ProofObligation(
            obligation_id="po-1",
            tenant_id="tenant-a",
            project_id="project-a",
            graph_id="graph-1",
            goal_id="goal-1",
            subject_revision=self.subject,
            family="correctness",
            relation="equivalent",
            scope="repository",
            severity=Severity.CRITICAL,
            required_minimum_status=ProofStatus.PROVED_SOLVER_TRUSTED,
            accepted_evidence_classes=frozenset({"solver-model-result"}),
            accepted_tool_digests=frozenset({self.tool_digest}),
            accepted_environment_revisions=frozenset({self.environment}),
        )
        self.graph = ProofObligationGraph([obligation])
        self.graph.apply_result(
            ProofResult(
                result_id="result-1",
                obligation_id="po-1",
                tenant_id="tenant-a",
                project_id="project-a",
                actor_id="reviewer-a",
                status=ProofStatus.PROVED_SOLVER_TRUSTED,
                subject_revision=self.subject,
                scope="repository",
                assumptions=(),
                tool=self.tool,
                environment_revision=self.environment,
                inputs_sha256=d("inputs", "proof-inputs"),
                evidence_ids=("proof-evidence",),
                evidence_classes=frozenset({"solver-model-result"}),
                created_at=NOW,
                independent_verifier=True,
            ),
            self.evidence,
            self.reviewer,
            now=NOW,
        )
        revisions = {name: d(name, "revision-component") for name in (
            "source_repository", "baseline_repository", "requirements", "policy", "workflow",
            "model_route", "toolchain", "environment", "domain_pack"
        )}
        self.revision_set = RevisionSet(
            revision_set_id="revision-set-1",
            tenant_id="tenant-a",
            project_id="project-a",
            goal_id="goal-1",
            created_at=NOW,
            **revisions,
        )
        self.gates = tuple(
            GateResult(gate, GateDecision.PASS, evidence_ids=("proof-evidence",))
            for gate in ("E0", "E1", "E2", "E3", "E4")
        )
        self.service = CertificationService(self.evidence)

    def tearDown(self) -> None:
        self.store.close()

    def test_local_result_is_never_certified_and_fake_external_receipt_fails(self) -> None:
        local = self.service.evaluate_local(
            self.context,
            goal_id="goal-1",
            revision_set=self.revision_set,
            graph=self.graph,
            gates=self.gates,
            evidence_ids=("proof-evidence",),
            certified_envelope={"name": "route", "version": "1", "scope": ["repository"], "assumptions": []},
            independent_verifier_identity="reviewer-a",
            now=NOW,
        )
        self.assertEqual(CertificationStatus.READY_FOR_EXTERNAL_GATE, local.status)
        self.assertNotEqual(CertificationStatus.CERTIFIED, local.status)
        with self.assertRaises(TypeError):
            local.certified_envelope["version"] = "mutated"  # type: ignore[index]
        with self.assertRaises(ValidationError):
            replace(local, status=CertificationStatus.CERTIFIED)
        receipt = ExternalSignatureReceipt(
            receipt_id="receipt-1",
            tenant_id="tenant-a",
            project_id="project-a",
            payload_sha256=local.payload_digest,
            signer_identity="external-ca",
            key_id="key-1",
            provider_id="fake-provider",
            algorithm="Ed25519",
            signature_base64=base64.b64encode(b"x" * 64).decode(),
            verification_evidence_id="proof-evidence",
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            independent=True,
            certification_authority=True,
            attested_status=CertificationStatus.CERTIFIED,
        )

        class FakeVerifier:
            provider_id = "fake-provider"
            trust_anchor_sha256 = d("trust", "trust-anchor")
            external = False
            asymmetric = True

            def verify(self, *args: object, **kwargs: object) -> bool:
                return True

        class SelfDeclaredExternalVerifier(FakeVerifier):
            external = True

        with self.assertRaises(ValidationError):
            TrustedVerifierRegistration(
                provider_id="fake-provider",
                trust_anchor_sha256=FakeVerifier.trust_anchor_sha256,
                allowed_key_ids=frozenset({"key-1"}),
                allowed_signer_identities=frozenset({"external-ca"}),
                verifier=FakeVerifier(),
            )
        # A request cannot inject an object that merely self-declares itself as
        # external; verifiers are accepted only through application startup
        # trust configuration.
        with self.assertRaises(TypeError):
            self.service.finalize_external(  # type: ignore[call-arg]
                self.context,
                local,
                receipt,
                SelfDeclaredExternalVerifier(),
                requested_status=CertificationStatus.CERTIFIED,
                now=NOW,
            )
        with self.assertRaises(CertificationError) as raised:
            self.service.finalize_external(
                self.context,
                local,
                receipt,
                requested_status=CertificationStatus.CERTIFIED,
                now=NOW,
            )
        self.assertEqual("PRODUCTION_ASSESSMENT_REQUIRED", raised.exception.code)
        with self.assertRaises(CertificationError) as missing_verifier:
            self.service.finalize_external(
                self.context,
                local,
                replace(
                    receipt,
                    attested_status=CertificationStatus.EXTERNALLY_VERIFIED,
                    certification_authority=False,
                ),
                requested_status=CertificationStatus.EXTERNALLY_VERIFIED,
                now=NOW,
            )
        self.assertEqual("EXTERNAL_VERIFIER_REQUIRED", missing_verifier.exception.code)
        with self.assertRaises(CertificationError) as tampered:
            self.service.finalize_external(
                self.context,
                replace(local, certified_envelope={**local.certified_envelope, "version": "forged"}),
                receipt,
                requested_status=CertificationStatus.CERTIFIED,
                now=NOW,
            )
        self.assertEqual("LOCAL_ASSESSMENT_TAMPERED", tampered.exception.code)

    def test_passing_gate_requires_evidence(self) -> None:
        with self.assertRaises(ValidationError) as raised:
            GateResult("E0", GateDecision.PASS)
        self.assertEqual("GATE_EVIDENCE_REQUIRED", raised.exception.code)

    def test_not_run_gate_remains_explicit_and_blocks_readiness(self) -> None:
        gates = list(self.gates)
        gates[-1] = GateResult("E4", GateDecision.NOT_RUN)
        local = self.service.evaluate_local(
            self.context,
            goal_id="goal-1",
            revision_set=self.revision_set,
            graph=self.graph,
            gates=gates,
            evidence_ids=("proof-evidence",),
            certified_envelope={"name": "route", "version": "1", "scope": ["repository"], "assumptions": []},
            independent_verifier_identity="reviewer-a",
            now=NOW,
        )
        self.assertEqual(CertificationStatus.BLOCKED, local.status)
        self.assertIn("gate E4 is NOT_RUN", local.unresolved_risks)

    def test_production_assessment_requires_p05_and_e5(self) -> None:
        missing_production_gates = self.service.evaluate_local(
            self.context,
            goal_id="goal-1",
            revision_set=self.revision_set,
            graph=self.graph,
            gates=self.gates,
            evidence_ids=("proof-evidence",),
            certified_envelope={"name": "route", "version": "1", "scope": ["repository"], "assumptions": []},
            independent_verifier_identity="reviewer-a",
            production=True,
            run_id="run-production-assessment",
            now=NOW,
        )
        self.assertEqual(CertificationStatus.BLOCKED, missing_production_gates.status)
        self.assertTrue(missing_production_gates.production_assessment)
        self.assertIn("gate P05 is NOT_RUN", missing_production_gates.unresolved_risks)
        self.assertIn("gate E5 is NOT_RUN", missing_production_gates.unresolved_risks)

        all_production_gates = self.gates + (
            GateResult("P05", GateDecision.PASS, evidence_ids=("proof-evidence",)),
            GateResult("E5", GateDecision.PASS, evidence_ids=("proof-evidence",)),
        )
        ready = self.service.evaluate_local(
            self.context,
            goal_id="goal-1",
            revision_set=self.revision_set,
            graph=self.graph,
            gates=all_production_gates,
            evidence_ids=("proof-evidence",),
            certified_envelope={"name": "route", "version": "1", "scope": ["repository"], "assumptions": []},
            independent_verifier_identity="reviewer-a",
            production=True,
            run_id="run-production-assessment",
            now=NOW,
        )
        self.assertEqual(CertificationStatus.READY_FOR_EXTERNAL_GATE, ready.status)
        self.assertTrue(ready.production_assessment)
        self.assertFalse(ready.unresolved_risks)

        forged_duplicate = ready.gate_results + (
            GateResult("P05", GateDecision.FAIL, reasons=("forged conflict",)),
        )
        with self.assertRaisesRegex(
            ValidationError, "certificate gate ids must be unique"
        ):
            replace(
                ready,
                status=CertificationStatus.CERTIFIED,
                gate_results=forged_duplicate,
                signer_identity="independent-ca",
                signer_key_id="ca-key",
                signer_independent=True,
                signature_receipt_id="receipt-certified",
                signature_receipt_sha256=d("receipt-certified", "receipt"),
            )

        failed_gate = tuple(
            GateResult("P05", GateDecision.FAIL, reasons=("counterexample",))
            if result.gate == "P05"
            else result
            for result in ready.gate_results
        )
        with self.assertRaisesRegex(
            ValidationError, "exactly one passing result"
        ):
            replace(
                ready,
                status=CertificationStatus.CERTIFIED,
                gate_results=failed_gate,
                signer_identity="independent-ca",
                signer_key_id="ca-key",
                signer_independent=True,
                signature_receipt_id="receipt-certified",
                signature_receipt_sha256=d("receipt-certified", "receipt"),
            )


if __name__ == "__main__":
    unittest.main()
