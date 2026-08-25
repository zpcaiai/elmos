from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_autonomous_qa.canonical import canonical_json_bytes  # noqa: E402
import elmos_autonomous_qa.control_plane as control_plane_module  # noqa: E402
from elmos_autonomous_qa.control_plane import (  # noqa: E402
    ControlPlaneError,
    EvidenceReceiptInvalid,
    IdempotencyConflict,
    IllegalTransition,
    QaControlPlane,
    ResourceQuotaExceeded,
    RunNotFound,
    RunStatus,
)


def invalid_bounded_json_factories():
    def deep():
        value: object = None
        for _ in range(40):
            value = {"child": value}
        return {"deep": value}

    return (
        ("deep", deep),
        ("nodes", lambda: {"nodes": [None] * 200_001}),
        ("bytes", lambda: {"bytes": "x" * (16 * 1024 * 1024)}),
        ("non-string-key", lambda: {1: "not-json"}),
    )


class QaControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "qa.sqlite3"
        self.control = QaControlPlane(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create(self, tenant: str = "tenant-a", run_id: str = "run-1"):
        return self.control.create_run(
            tenant_id=tenant,
            run_id=run_id,
            project_id="project-a",
            mode="verify",
            payload={"snapshot": "abc", "budget": 30},
            idempotency_key=f"create-{tenant}-{run_id}",
            actor="owner-a",
        )

    def transition(self, run_id: str, action: str, key: str, **details):
        return self.control.transition(
            tenant_id="tenant-a",
            run_id=run_id,
            action=action,
            idempotency_key=key,
            actor=details.pop("actor", "owner-a"),
            details=details,
        )

    def test_persistence_restart_and_event_chain(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        reopened = QaControlPlane(self.database)
        recovered = reopened.recover_active_runs(tenant_id="tenant-a")
        self.assertEqual([(run.run_id, run.status) for run in recovered], [("run-1", RunStatus.RUNNING)])
        events = reopened.list_events(tenant_id="tenant-a", run_id="run-1")
        self.assertEqual([event.sequence for event in events], [1, 2])
        self.assertEqual(events[1].previous_digest, events[0].event_digest)

    def test_idempotency_replay_and_conflict(self) -> None:
        first = self.create()
        replay = self.create()
        self.assertEqual(first, replay)
        with self.assertRaises(IdempotencyConflict):
            self.control.create_run(
                tenant_id="tenant-a",
                run_id="run-2",
                project_id="project-a",
                mode="verify",
                payload={"snapshot": "different"},
                idempotency_key="create-tenant-a-run-1",
                actor="owner-a",
            )

    def test_worker_progress_observation_is_durable_idempotent_and_self_attested(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-observation")
        first = self.control.record_observation(
            tenant_id="tenant-a",
            run_id="run-1",
            kind="worker-heartbeat",
            payload={"worker_id": "worker-1", "lease_epoch": 2},
            idempotency_key="heartbeat-1",
            actor="worker-1",
        )
        replay = self.control.record_observation(
            tenant_id="tenant-a",
            run_id="run-1",
            kind="worker-heartbeat",
            payload={"worker_id": "worker-1", "lease_epoch": 2},
            idempotency_key="heartbeat-1",
            actor="worker-1",
        )
        self.assertEqual(first, replay)
        reopened = QaControlPlane(self.database)
        events = reopened.list_events(tenant_id="tenant-a", run_id="run-1")
        observations = [
            event for event in events if event.kind == "run.observation.worker-heartbeat"
        ]
        self.assertEqual(1, len(observations))
        self.assertEqual(
            "SELF_ATTESTED_NOT_INDEPENDENTLY_VERIFIED",
            observations[0].payload["verification"],
        )
        with self.assertRaises(IdempotencyConflict):
            self.control.record_observation(
                tenant_id="tenant-a",
                run_id="run-1",
                kind="worker-heartbeat",
                payload={"worker_id": "worker-1", "lease_epoch": 3},
                idempotency_key="heartbeat-1",
                actor="worker-1",
            )

    def test_non_plan_run_cannot_complete_without_a_durable_output_reference(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-completion")
        with self.assertRaises(IllegalTransition):
            self.transition("run-1", "complete", "complete-without-output")
        with self.assertRaises(IllegalTransition):
            self.transition(
                "run-1",
                "complete",
                "complete-unknown-durability",
                output_ref="out-1",
                output_manifest_digest="a" * 64,
                publication_durability="COMMITTED_DURABILITY_UNKNOWN",
            )
        completed = self.transition(
            "run-1",
            "complete",
            "complete-durable",
            output_ref="out-1",
            output_manifest_digest="a" * 64,
            publication_durability="DURABLE",
        )
        self.assertEqual(RunStatus.COMPLETED, completed.status)

    def test_tenant_isolation(self) -> None:
        self.create("tenant-a", "shared-run")
        self.create("tenant-b", "shared-run")
        self.assertEqual(
            self.control.get_run(tenant_id="tenant-a", run_id="shared-run").tenant_id,
            "tenant-a",
        )
        with self.assertRaises(RunNotFound):
            self.control.get_run(tenant_id="tenant-c", run_id="shared-run")
        self.assertEqual(len(self.control.recover_active_runs(tenant_id="tenant-b")), 1)

    def test_create_run_bounds_direct_payloads_before_storage_access(self) -> None:
        for index, (name, factory) in enumerate(invalid_bounded_json_factories()):
            with self.subTest(name=name), patch.object(
                self.control,
                "_connect",
                side_effect=AssertionError("invalid payload reached storage"),
            ), patch.object(
                control_plane_module,
                "canonical_digest",
                side_effect=AssertionError("invalid payload reached digesting"),
            ):
                with self.assertRaises(ValueError):
                    self.control.create_run(
                        tenant_id="tenant-a",
                        run_id=f"run-invalid-{index}",
                        project_id="project-a",
                        mode="verify",
                        payload=factory(),
                        idempotency_key=f"invalid-payload-{index}",
                        actor="owner-a",
                    )
        with self.control._connect() as connection:
            counts = tuple(
                int(value)
                for value in connection.execute(
                    "SELECT (SELECT COUNT(*) FROM qa_runs), "
                    "(SELECT COUNT(*) FROM qa_events), "
                    "(SELECT COUNT(*) FROM qa_audit), "
                    "(SELECT COUNT(*) FROM qa_idempotency)"
                ).fetchone()
            )
        self.assertEqual((0, 0, 0, 0), counts)

    def test_transition_bounds_direct_details_before_storage_access(self) -> None:
        self.create()
        for index, (name, factory) in enumerate(invalid_bounded_json_factories()):
            with self.subTest(name=name), patch.object(
                self.control,
                "_connect",
                side_effect=AssertionError("invalid details reached storage"),
            ), patch.object(
                control_plane_module,
                "canonical_digest",
                side_effect=AssertionError("invalid details reached digesting"),
            ):
                with self.assertRaises(ValueError):
                    self.control.transition(
                        tenant_id="tenant-a",
                        run_id="run-1",
                        action="start",
                        idempotency_key=f"invalid-details-{index}",
                        actor="owner-a",
                        details=factory(),
                    )
        run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
        self.assertEqual(RunStatus.CREATED, run.status)
        self.assertEqual(
            1,
            len(self.control.list_events(tenant_id="tenant-a", run_id="run-1")),
        )
        self.assertEqual(
            1,
            len(self.control.list_audit(tenant_id="tenant-a", run_id="run-1")),
        )
        with self.control._connect() as connection:
            key_count = int(
                connection.execute("SELECT COUNT(*) FROM qa_idempotency").fetchone()[0]
            )
        self.assertEqual(1, key_count)

    def test_run_lookup_rechecks_returned_row_identity(self) -> None:
        stored = self.create(tenant="Tenant-A", run_id="run-case")
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE qa_runs ("
            "tenant_id TEXT COLLATE NOCASE NOT NULL, run_id TEXT NOT NULL, "
            "project_id TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, "
            "input_digest TEXT NOT NULL, payload_json BLOB NOT NULL, "
            "attempt INTEGER NOT NULL, retry_of TEXT, version INTEGER NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "PRIMARY KEY (tenant_id, run_id))"
        )
        connection.execute(
            "INSERT INTO qa_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                stored.tenant_id,
                stored.run_id,
                stored.project_id,
                stored.mode,
                stored.status.value,
                stored.input_digest,
                canonical_json_bytes(dict(stored.payload)),
                stored.attempt,
                stored.retry_of,
                stored.version,
                stored.created_at,
                stored.updated_at,
            ),
        )
        with self.assertRaisesRegex(ControlPlaneError, "resource boundary"):
            self.control.get_run(
                tenant_id="tenant-a", run_id="run-case", connection=connection
            )

    def test_illegal_transition_fails_closed_and_is_audited(self) -> None:
        self.create()
        with self.assertRaises(IllegalTransition):
            self.transition("run-1", "pause", "pause-created")
        first_audit_count = len(
            self.control.list_audit(tenant_id="tenant-a", run_id="run-1")
        )
        with self.assertRaises(IllegalTransition):
            self.transition("run-1", "pause", "pause-created")
        run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
        self.assertEqual(run.status, RunStatus.CREATED)
        audit = self.control.list_audit(tenant_id="tenant-a", run_id="run-1")
        self.assertEqual(audit[-1].outcome, "denied")
        self.assertEqual(first_audit_count, len(audit))

    def test_pause_resume_cancel_and_retry_use_new_identity(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        self.transition("run-1", "pause", "pause-1")
        resumed = self.transition("run-1", "resume", "resume-1")
        self.assertEqual(resumed.status, RunStatus.RUNNING)
        self.transition("run-1", "cancel", "cancel-1")
        retry = self.control.retry_run(
            tenant_id="tenant-a",
            source_run_id="run-1",
            new_run_id="run-2",
            idempotency_key="retry-1",
            actor="owner-a",
        )
        self.assertEqual(retry.status, RunStatus.CREATED)
        self.assertEqual(retry.retry_of, "run-1")
        self.assertEqual(retry.attempt, 2)

    def test_approval_requires_exact_evidence(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        subject_digest = "a" * 64
        self.transition(
            "run-1",
            "request_approval",
            "request-approval",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            authorization_ref="authorization-1",
        )
        with self.assertRaises(IllegalTransition):
            self.transition("run-1", "approve", "approve-bad", decision="approved")
        with self.assertRaises(IllegalTransition):
            self.transition(
                "run-1",
                "approve",
                "approve-self",
                approver_id="owner-a",
                decision="approved",
                scope="run-1:repair-plan-7",
                subject_digest=subject_digest,
                authorization_ref="authorization-1",
                evidence_receipt_id="receipt-1",
                executor_id="executor-a",
                verifier_id="verifier-b",
            )
        receipt = self.control.register_verified_evidence(
            tenant_id="tenant-a",
            receipt_id="receipt-1",
            run_id="run-1",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            evidence_digest="b" * 64,
            artifact_digest="c" * 64,
            authorization_ref="authorization-1",
            executor_id="executor-a",
            verifier_id="verifier-b",
            valid_until="2099-01-01T00:00:00Z",
            registered_by="verifier-b",
        )
        self.assertFalse(receipt.revoked)
        with self.assertRaises(IllegalTransition):
            self.transition(
                "run-1",
                "approve",
                "approve-wrong-authorization",
                actor="reviewer-a",
                approver_id="reviewer-a",
                decision="approved",
                scope="run-1:repair-plan-7",
                subject_digest=subject_digest,
                authorization_ref="authorization-other",
                evidence_receipt_id="receipt-1",
                executor_id="executor-a",
                verifier_id="verifier-b",
            )
        approved = self.transition(
            "run-1",
            "approve",
            "approve-good",
            actor="reviewer-a",
            approver_id="reviewer-a",
            decision="approved",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            authorization_ref="authorization-1",
            evidence_receipt_id="receipt-1",
            executor_id="executor-a",
            verifier_id="verifier-b",
        )
        self.assertEqual(approved.status, RunStatus.RUNNING)
        consumed = self.control.get_verified_evidence(
            tenant_id="tenant-a", receipt_id="receipt-1"
        )
        self.assertEqual(consumed.consumed_by, "reviewer-a")
        self.assertIsNotNone(consumed.consumed_at)
        self.assertIsNotNone(consumed.consumption_digest)

    def test_evidence_receipt_is_exact_request_bound_and_single_use(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        subject_digest = "a" * 64
        request_details = {
            "scope": "run-1:repair-plan-7",
            "subject_digest": subject_digest,
            "authorization_ref": "authorization-1",
        }
        requested = self.transition(
            "run-1", "request_approval", "request-approval-1", **request_details
        )
        receipt = self.control.register_verified_evidence(
            tenant_id="tenant-a",
            receipt_id="receipt-1",
            run_id="run-1",
            scope=request_details["scope"],
            subject_digest=subject_digest,
            evidence_digest="b" * 64,
            artifact_digest="c" * 64,
            authorization_ref=request_details["authorization_ref"],
            executor_id="executor-a",
            verifier_id="verifier-b",
            valid_until="2099-01-01T00:00:00Z",
            registered_by="verifier-b",
        )
        self.assertEqual(receipt.approval_run_version, requested.version)
        request_audit = self.control.list_audit(
            tenant_id="tenant-a", run_id="run-1"
        )[-2]
        self.assertEqual(receipt.approval_request_digest, request_audit.record_digest)
        approval = {
            "approver_id": "reviewer-a",
            "decision": "approved",
            **request_details,
            "evidence_receipt_id": "receipt-1",
            "executor_id": "executor-a",
            "verifier_id": "verifier-b",
        }
        self.transition(
            "run-1", "approve", "approve-1", actor="reviewer-a", **approval
        )
        self.control = QaControlPlane(self.database)
        consumed = self.control.get_verified_evidence(
            tenant_id="tenant-a", receipt_id="receipt-1"
        )
        self.assertIsNotNone(consumed.consumption_digest)

        self.transition(
            "run-1", "request_approval", "request-approval-2", **request_details
        )
        with self.assertRaisesRegex(
            IllegalTransition, "VERIFIED_EVIDENCE_RECEIPT_CONSUMED"
        ):
            self.transition(
                "run-1",
                "approve",
                "approve-reuse",
                actor="reviewer-c",
                **{**approval, "approver_id": "reviewer-c"},
            )
        self.assertEqual(
            self.control.get_run(tenant_id="tenant-a", run_id="run-1").status,
            RunStatus.WAITING_APPROVAL,
        )

    def test_event_and_audit_reads_recompute_digest_chains(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_events SET previous_digest = ? "
                "WHERE tenant_id = ? AND run_id = ? AND sequence = 2",
                ("f" * 64, "tenant-a", "run-1"),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.list_events(tenant_id="tenant-a", run_id="run-1")

        self.create(run_id="run-2")
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_audit SET details_json = ? "
                "WHERE tenant_id = ? AND run_id = ?",
                (b'{}\n', "tenant-a", "run-2"),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.list_audit(tenant_id="tenant-a", run_id="run-2")

    def test_event_and_audit_chains_require_canonical_storage_bytes(self) -> None:
        self.create(run_id="run-event-canonical")
        self.create(run_id="run-audit-canonical")
        with self.control._connect() as connection:
            event = connection.execute(
                "SELECT payload_json FROM qa_events WHERE tenant_id = ? AND run_id = ?",
                ("tenant-a", "run-event-canonical"),
            ).fetchone()
            audit = connection.execute(
                "SELECT details_json FROM qa_audit WHERE tenant_id = ? AND run_id = ?",
                ("tenant-a", "run-audit-canonical"),
            ).fetchone()
            assert event is not None and audit is not None
            event_bytes = bytes(event["payload_json"])
            audit_bytes = bytes(audit["details_json"])
            self.assertTrue(event_bytes.endswith(b"\n"))
            self.assertTrue(audit_bytes.endswith(b"\n"))
            connection.execute(
                "UPDATE qa_events SET payload_json = ? WHERE tenant_id = ? AND run_id = ?",
                (event_bytes[:-1], "tenant-a", "run-event-canonical"),
            )
            connection.execute(
                "UPDATE qa_audit SET details_json = ? WHERE tenant_id = ? AND run_id = ?",
                (audit_bytes[:-1], "tenant-a", "run-audit-canonical"),
            )
        with self.assertRaisesRegex(ControlPlaneError, "canonical JSON"):
            self.control.list_events(
                tenant_id="tenant-a", run_id="run-event-canonical"
            )
        with self.assertRaisesRegex(ControlPlaneError, "canonical JSON"):
            self.control.list_audit(
                tenant_id="tenant-a", run_id="run-audit-canonical"
            )

    def test_approval_revalidates_audit_chain_before_consuming_evidence(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        subject_digest = "a" * 64
        self.transition(
            "run-1",
            "request_approval",
            "request-approval",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            authorization_ref="authorization-1",
        )
        self.control.register_verified_evidence(
            tenant_id="tenant-a",
            receipt_id="receipt-1",
            run_id="run-1",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            evidence_digest="b" * 64,
            artifact_digest="c" * 64,
            authorization_ref="authorization-1",
            executor_id="executor-a",
            verifier_id="verifier-b",
            valid_until="2099-01-01T00:00:00Z",
            registered_by="verifier-b",
        )
        with self.control._connect() as connection:
            connection.execute(
                "DELETE FROM qa_audit "
                "WHERE tenant_id = ? AND run_id = ? "
                "AND action = 'register_verified_evidence'",
                ("tenant-a", "run-1"),
            )
        with self.assertRaises(ControlPlaneError):
            self.transition(
                "run-1",
                "approve",
                "approve-tampered",
                actor="reviewer-a",
                approver_id="reviewer-a",
                decision="approved",
                scope="run-1:repair-plan-7",
                subject_digest=subject_digest,
                authorization_ref="authorization-1",
                evidence_receipt_id="receipt-1",
                executor_id="executor-a",
                verifier_id="verifier-b",
            )
        self.assertEqual(
            self.control.get_run(tenant_id="tenant-a", run_id="run-1").status,
            RunStatus.WAITING_APPROVAL,
        )

    def test_revoked_receipt_denial_and_replay_are_idempotent(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        subject_digest = "a" * 64
        self.transition(
            "run-1",
            "request_approval",
            "request-approval",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            authorization_ref="authorization-1",
        )
        self.control.register_verified_evidence(
            tenant_id="tenant-a",
            receipt_id="receipt-1",
            run_id="run-1",
            scope="run-1:repair-plan-7",
            subject_digest=subject_digest,
            evidence_digest="b" * 64,
            artifact_digest="c" * 64,
            authorization_ref="authorization-1",
            executor_id="executor-a",
            verifier_id="verifier-b",
            valid_until="2099-01-01T00:00:00Z",
            registered_by="verifier-b",
        )
        first = self.control.revoke_verified_evidence(
            tenant_id="tenant-a", receipt_id="receipt-1", actor="security-a"
        )
        replay = self.control.revoke_verified_evidence(
            tenant_id="tenant-a", receipt_id="receipt-1", actor="security-a"
        )
        self.assertTrue(first.revoked)
        self.assertEqual(first, replay)
        details = {
            "actor": "reviewer-a",
            "approver_id": "reviewer-a",
            "decision": "approved",
            "scope": "run-1:repair-plan-7",
            "subject_digest": subject_digest,
            "authorization_ref": "authorization-1",
            "evidence_receipt_id": "receipt-1",
            "executor_id": "executor-a",
            "verifier_id": "verifier-b",
        }
        with self.assertRaises(IllegalTransition):
            self.transition("run-1", "approve", "approve-revoked", **details)
        audit_count = len(
            self.control.list_audit(tenant_id="tenant-a", run_id="run-1")
        )
        with self.assertRaises(IllegalTransition):
            self.transition("run-1", "approve", "approve-revoked", **details)
        self.assertEqual(
            audit_count,
            len(self.control.list_audit(tenant_id="tenant-a", run_id="run-1")),
        )

    def test_evidence_registration_requires_verifier_identity(self) -> None:
        self.create()
        with self.assertRaises(EvidenceReceiptInvalid):
            self.control.register_verified_evidence(
                tenant_id="tenant-a",
                receipt_id="receipt-1",
                run_id="run-1",
                scope="scope-1",
                subject_digest="a" * 64,
                evidence_digest="b" * 64,
                artifact_digest="c" * 64,
                authorization_ref="authorization-1",
                executor_id="executor-a",
                verifier_id="verifier-b",
                valid_until="2099-01-01T00:00:00Z",
                registered_by="not-verifier",
            )
        with self.assertRaises(EvidenceReceiptInvalid):
            self.control.register_verified_evidence(
                tenant_id="tenant-a",
                receipt_id="receipt-expired",
                run_id="run-1",
                scope="scope-1",
                subject_digest="a" * 64,
                evidence_digest="b" * 64,
                artifact_digest="c" * 64,
                authorization_ref="authorization-1",
                executor_id="executor-a",
                verifier_id="verifier-b",
                valid_until="2000-01-01T00:00:00Z",
                registered_by="verifier-b",
            )
        with self.assertRaisesRegex(EvidenceReceiptInvalid, "waiting for exact approval"):
            self.control.register_verified_evidence(
                tenant_id="tenant-a",
                receipt_id="receipt-no-request",
                run_id="run-1",
                scope="scope-1",
                subject_digest="a" * 64,
                evidence_digest="b" * 64,
                artifact_digest="c" * 64,
                authorization_ref="authorization-1",
                executor_id="executor-a",
                verifier_id="verifier-b",
                valid_until="2099-01-01T00:00:00Z",
                registered_by="verifier-b",
            )

    def test_evidence_registration_rejects_requester_as_verifier(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        self.transition(
            "run-1",
            "request_approval",
            "request-approval",
            scope="scope-1",
            subject_digest="a" * 64,
            authorization_ref="authorization-1",
        )
        with self.assertRaisesRegex(
            EvidenceReceiptInvalid, "requester and evidence verifier"
        ):
            self.control.register_verified_evidence(
                tenant_id="tenant-a",
                receipt_id="receipt-requester-verifier",
                run_id="run-1",
                scope="scope-1",
                subject_digest="a" * 64,
                evidence_digest="b" * 64,
                artifact_digest="c" * 64,
                authorization_ref="authorization-1",
                executor_id="executor-a",
                verifier_id="owner-a",
                valid_until="2099-01-01T00:00:00Z",
                registered_by="owner-a",
            )

    def test_idempotency_response_digest_rejects_tampering(self) -> None:
        self.create()
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_idempotency SET response_json = ? "
                "WHERE tenant_id = ? AND idempotency_key = ?",
                (
                    canonical_json_bytes({"tampered": True}),
                    "tenant-a",
                    "create-tenant-a-run-1",
                ),
            )
        with self.assertRaises(ControlPlaneError):
            self.create()

        self.create(run_id="run-2")
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_idempotency SET response_digest = ? "
                "WHERE tenant_id = ? AND idempotency_key = ?",
                ("f" * 64, "tenant-a", "create-tenant-a-run-2"),
            )
        with self.assertRaises(ControlPlaneError):
            self.create(run_id="run-2")

        self.create(run_id="run-3")
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_idempotency SET created_at = ? "
                "WHERE tenant_id = ? AND idempotency_key = ?",
                (
                    "2026-01-01T00:00:00Z",
                    "tenant-a",
                    "create-tenant-a-run-3",
                ),
            )
        with self.assertRaises(ControlPlaneError):
            self.create(run_id="run-3")

    def test_idempotency_response_is_bound_to_tenant_and_expected_run(self) -> None:
        self.create(run_id="run-1")
        other_tenant_run = self.create(tenant="tenant-b", run_id="run-b")
        same_tenant_other_run = self.create(run_id="run-2")

        def replace_response(run) -> None:
            response = self.control._run_response(run)
            with self.control._connect() as connection:
                row = connection.execute(
                    "SELECT command, request_digest, created_at FROM qa_idempotency "
                    "WHERE tenant_id = ? AND idempotency_key = ?",
                    ("tenant-a", "create-tenant-a-run-1"),
                ).fetchone()
                assert row is not None
                digest = self.control._idempotency_record_digest(
                    tenant_id="tenant-a",
                    idempotency_key="create-tenant-a-run-1",
                    command=row["command"],
                    request_digest=row["request_digest"],
                    response=response,
                    created_at=row["created_at"],
                )
                connection.execute(
                    "UPDATE qa_idempotency SET response_json = ?, response_digest = ? "
                    "WHERE tenant_id = ? AND idempotency_key = ?",
                    (
                        canonical_json_bytes(response),
                        digest,
                        "tenant-a",
                        "create-tenant-a-run-1",
                    ),
                )

        replace_response(other_tenant_run)
        with self.assertRaises(ControlPlaneError):
            self.create(run_id="run-1")
        replace_response(same_tenant_other_run)
        with self.assertRaises(ControlPlaneError):
            self.create(run_id="run-1")

    def test_mutation_rejects_earlier_chain_corruption_before_writing(self) -> None:
        for run_id, table, column in (
            ("run-event-corrupt", "qa_events", "payload_json"),
            ("run-audit-corrupt", "qa_audit", "details_json"),
        ):
            with self.subTest(table=table):
                self.create(run_id=run_id)
                self.transition(run_id, "start", f"start-{run_id}")
                with self.control._connect() as connection:
                    before_events = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM qa_events "
                            "WHERE tenant_id = ? AND run_id = ?",
                            ("tenant-a", run_id),
                        ).fetchone()[0]
                    )
                    before_audit = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM qa_audit "
                            "WHERE tenant_id = ? AND run_id = ?",
                            ("tenant-a", run_id),
                        ).fetchone()[0]
                    )
                    connection.execute(
                        f"UPDATE {table} SET {column} = ? WHERE tenant_id = ? "
                        "AND run_id = ? AND rowid = (SELECT MIN(rowid) FROM "
                        f"{table} WHERE tenant_id = ? AND run_id = ?)",
                        (
                            canonical_json_bytes({"tampered": True}),
                            "tenant-a",
                            run_id,
                            "tenant-a",
                            run_id,
                        ),
                    )
                with self.assertRaises(ControlPlaneError):
                    self.transition(run_id, "pause", f"pause-{run_id}")
                with self.control._connect() as connection:
                    after_events = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM qa_events "
                            "WHERE tenant_id = ? AND run_id = ?",
                            ("tenant-a", run_id),
                        ).fetchone()[0]
                    )
                    after_audit = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM qa_audit "
                            "WHERE tenant_id = ? AND run_id = ?",
                            ("tenant-a", run_id),
                        ).fetchone()[0]
                    )
                self.assertEqual((after_events, after_audit), (before_events, before_audit))
                self.assertEqual(
                    self.control.get_run(tenant_id="tenant-a", run_id=run_id).status,
                    RunStatus.RUNNING,
                )

    def test_retry_and_evidence_registration_validate_history_first(self) -> None:
        self.create(run_id="run-retry-corrupt")
        self.transition("run-retry-corrupt", "start", "start-retry-corrupt")
        self.transition("run-retry-corrupt", "cancel", "cancel-retry-corrupt")
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_audit SET details_json = ? WHERE tenant_id = ? "
                "AND run_id = ? AND audit_id = (SELECT MIN(audit_id) FROM qa_audit "
                "WHERE tenant_id = ? AND run_id = ?)",
                (
                    canonical_json_bytes({"tampered": True}),
                    "tenant-a",
                    "run-retry-corrupt",
                    "tenant-a",
                    "run-retry-corrupt",
                ),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.retry_run(
                tenant_id="tenant-a",
                source_run_id="run-retry-corrupt",
                new_run_id="run-retry-blocked",
                idempotency_key="retry-corrupt",
                actor="owner-a",
            )
        with self.assertRaises(RunNotFound):
            self.control.get_run(
                tenant_id="tenant-a", run_id="run-retry-blocked"
            )

        self.create(run_id="run-evidence-corrupt")
        self.transition("run-evidence-corrupt", "start", "start-evidence-corrupt")
        self.transition(
            "run-evidence-corrupt",
            "request_approval",
            "request-evidence-corrupt",
            scope="scope-corrupt",
            subject_digest="a" * 64,
            authorization_ref="authorization-corrupt",
        )
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE qa_events SET payload_json = ? WHERE tenant_id = ? "
                "AND run_id = ? AND sequence = 1",
                (
                    canonical_json_bytes({"tampered": True}),
                    "tenant-a",
                    "run-evidence-corrupt",
                ),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.register_verified_evidence(
                tenant_id="tenant-a",
                receipt_id="receipt-corrupt",
                run_id="run-evidence-corrupt",
                scope="scope-corrupt",
                subject_digest="a" * 64,
                evidence_digest="b" * 64,
                artifact_digest="c" * 64,
                authorization_ref="authorization-corrupt",
                executor_id="executor-a",
                verifier_id="verifier-b",
                valid_until="2099-01-01T00:00:00Z",
                registered_by="verifier-b",
            )
        with self.control._connect() as connection:
            receipt_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM qa_verified_evidence "
                    "WHERE tenant_id = ? AND receipt_id = ?",
                    ("tenant-a", "receipt-corrupt"),
                ).fetchone()[0]
            )
        self.assertEqual(receipt_count, 0)

    def test_evidence_revocation_validates_history_before_mutation(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        self.transition(
            "run-1",
            "request_approval",
            "request-approval",
            scope="scope-1",
            subject_digest="a" * 64,
            authorization_ref="authorization-1",
        )
        self.control.register_verified_evidence(
            tenant_id="tenant-a",
            receipt_id="receipt-1",
            run_id="run-1",
            scope="scope-1",
            subject_digest="a" * 64,
            evidence_digest="b" * 64,
            artifact_digest="c" * 64,
            authorization_ref="authorization-1",
            executor_id="executor-a",
            verifier_id="verifier-b",
            valid_until="2099-01-01T00:00:00Z",
            registered_by="verifier-b",
        )
        with self.control._connect() as connection:
            before_audit = int(
                connection.execute(
                    "SELECT COUNT(*) FROM qa_audit WHERE tenant_id = ? AND run_id = ?",
                    ("tenant-a", "run-1"),
                ).fetchone()[0]
            )
            connection.execute(
                "UPDATE qa_events SET payload_json = ? "
                "WHERE tenant_id = ? AND run_id = ? AND sequence = 1",
                (
                    canonical_json_bytes({"tampered": True}),
                    "tenant-a",
                    "run-1",
                ),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.revoke_verified_evidence(
                tenant_id="tenant-a", receipt_id="receipt-1", actor="security-a"
            )
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT revoked FROM qa_verified_evidence "
                "WHERE tenant_id = ? AND receipt_id = ?",
                ("tenant-a", "receipt-1"),
            ).fetchone()
            after_audit = int(
                connection.execute(
                    "SELECT COUNT(*) FROM qa_audit WHERE tenant_id = ? AND run_id = ?",
                    ("tenant-a", "run-1"),
                ).fetchone()[0]
            )
        assert row is not None
        self.assertEqual(row["revoked"], 0)
        self.assertEqual(after_audit, before_audit)

    def test_run_rows_validate_payload_digest_types_status_and_time(self) -> None:
        mutations = (
            ("run-digest", "input_digest", "f" * 64),
            ("run-status", "status", "invented-success"),
            ("run-version", "version", "not-an-integer"),
            ("run-time", "updated_at", "not-a-timestamp"),
        )
        for run_id, column, value in mutations:
            with self.subTest(column=column):
                self.create(run_id=run_id)
                with self.control._connect() as connection:
                    connection.execute(
                        f"UPDATE qa_runs SET {column} = ? "
                        "WHERE tenant_id = ? AND run_id = ?",
                        (value, "tenant-a", run_id),
                    )
                with self.assertRaises(ControlPlaneError):
                    self.control.get_run(tenant_id="tenant-a", run_id=run_id)

    def test_persisted_chain_heads_detect_tail_truncation(self) -> None:
        self.create(run_id="run-events")
        self.transition("run-events", "start", "start-events")
        with self.control._connect() as connection:
            head = connection.execute(
                "SELECT event_sequence, audit_id, external_anchor_state "
                "FROM qa_chain_heads WHERE tenant_id = ? AND run_id = ?",
                ("tenant-a", "run-events"),
            ).fetchone()
            self.assertIsNotNone(head)
            self.assertEqual(head["event_sequence"], 2)
            self.assertEqual(head["audit_id"], 2)
            self.assertEqual(head["external_anchor_state"], "NOT_RUN")
            connection.execute(
                "DELETE FROM qa_events WHERE tenant_id = ? AND run_id = ? "
                "AND sequence = 2",
                ("tenant-a", "run-events"),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.list_events(tenant_id="tenant-a", run_id="run-events")
        with self.assertRaises(ControlPlaneError):
            QaControlPlane(self.database)

        self.create(run_id="run-audit")
        self.transition("run-audit", "start", "start-audit")
        with self.control._connect() as connection:
            connection.execute(
                "DELETE FROM qa_audit WHERE audit_id = ("
                "SELECT MAX(audit_id) FROM qa_audit "
                "WHERE tenant_id = ? AND run_id = ?)",
                ("tenant-a", "run-audit"),
            )
        with self.assertRaises(ControlPlaneError):
            self.control.list_audit(tenant_id="tenant-a", run_id="run-audit")

    def test_legacy_head_table_is_backfilled_but_missing_current_head_fails(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        with self.control._connect() as connection:
            connection.execute("DROP TABLE qa_chain_heads")
            connection.execute("PRAGMA user_version = 0")
        reopened = QaControlPlane(self.database)
        self.assertEqual(
            len(reopened.list_events(tenant_id="tenant-a", run_id="run-1")), 2
        )
        with reopened._connect() as connection:
            connection.execute(
                "DELETE FROM qa_chain_heads WHERE tenant_id = ? AND run_id = ?",
                ("tenant-a", "run-1"),
            )
        with self.assertRaises(ControlPlaneError):
            QaControlPlane(self.database)

    def test_old_idempotency_schema_is_safely_digest_backfilled(self) -> None:
        database = Path(self.temporary.name) / "old-idempotency.sqlite3"
        response = {
            "_error_type": "IllegalTransition",
            "error_code": "ILLEGAL_RUN_STATE",
        }
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE qa_idempotency ("
                "tenant_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
                "command TEXT NOT NULL, request_digest TEXT NOT NULL, "
                "response_json BLOB NOT NULL, created_at TEXT NOT NULL, "
                "PRIMARY KEY (tenant_id, idempotency_key))"
            )
            connection.execute(
                "INSERT INTO qa_idempotency "
                "(tenant_id, idempotency_key, command, request_digest, "
                "response_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "tenant-a",
                    "old-key",
                    "transition:pause",
                    "a" * 64,
                    canonical_json_bytes(response),
                    "2026-01-01T00:00:00Z",
                ),
            )
        QaControlPlane(database)
        with sqlite3.connect(database) as connection:
            observed = connection.execute(
                "SELECT response_digest, created_at FROM qa_idempotency "
                "WHERE tenant_id = ? AND idempotency_key = ?",
                ("tenant-a", "old-key"),
            ).fetchone()
        assert observed is not None
        expected_digest = QaControlPlane._idempotency_record_digest(
            tenant_id="tenant-a",
            idempotency_key="old-key",
            command="transition:pause",
            request_digest="a" * 64,
            response=response,
            created_at="2026-01-01T00:00:00Z",
        )
        self.assertEqual(observed[0], expected_digest)

    def test_old_idempotency_schema_refuses_noncanonical_backfill(self) -> None:
        database = Path(self.temporary.name) / "unsafe-idempotency.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE qa_idempotency ("
                "tenant_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, "
                "command TEXT NOT NULL, request_digest TEXT NOT NULL, "
                "response_json BLOB NOT NULL, created_at TEXT NOT NULL, "
                "PRIMARY KEY (tenant_id, idempotency_key))"
            )
            connection.execute(
                "INSERT INTO qa_idempotency "
                "(tenant_id, idempotency_key, command, request_digest, "
                "response_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "tenant-a",
                    "old-key",
                    "transition:pause",
                    "a" * 64,
                    b'{"error_code": "ILLEGAL_RUN_STATE"}',
                    "2026-01-01T00:00:00Z",
                ),
            )
        with self.assertRaises(ControlPlaneError):
            QaControlPlane(database)
        with sqlite3.connect(database) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(qa_idempotency)")
            }
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        self.assertNotIn("response_digest", columns)
        self.assertEqual(tables, {"qa_idempotency"})
        self.assertEqual(schema_version, 0)

    def test_nonempty_legacy_audit_without_chain_link_fails_before_migration(self) -> None:
        database = Path(self.temporary.name) / "legacy-audit.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE qa_audit ("
                "audit_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, actor TEXT NOT NULL, "
                "action TEXT NOT NULL, outcome TEXT NOT NULL, details_json BLOB NOT NULL, "
                "record_digest TEXT NOT NULL, occurred_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO qa_audit "
                "(tenant_id, run_id, actor, action, outcome, details_json, "
                "record_digest, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "tenant-a",
                    "run-1",
                    "actor-a",
                    "create",
                    "accepted",
                    canonical_json_bytes({}),
                    "a" * 64,
                    "2026-01-01T00:00:00Z",
                ),
            )
        with self.assertRaisesRegex(
            ControlPlaneError, "cannot be safely re-chained"
        ):
            QaControlPlane(database)
        with sqlite3.connect(database) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(qa_audit)")
            }
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        self.assertNotIn("previous_digest", columns)
        self.assertEqual(schema_version, 0)

    def test_legacy_schema_migration_rejects_inexact_layout_atomically(self) -> None:
        database = Path(self.temporary.name) / "legacy-inexact.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE qa_runs ("
                "tenant_id TEXT NOT NULL, run_id TEXT NOT NULL, "
                "project_id TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, "
                "input_digest TEXT NOT NULL, payload_json BLOB NOT NULL, "
                "attempt INTEGER NOT NULL, retry_of TEXT, version INTEGER NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "legacy_extra TEXT, PRIMARY KEY (tenant_id, run_id))"
            )
        with self.assertRaisesRegex(ControlPlaneError, "schema is not exact"):
            QaControlPlane(database)
        with sqlite3.connect(database) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(tables, {"qa_runs"})
        self.assertEqual(schema_version, 0)

    def test_fresh_audit_schema_has_composite_run_foreign_key(self) -> None:
        with self.control._connect() as connection:
            rows = connection.execute("PRAGMA foreign_key_list(qa_audit)").fetchall()
        groups: dict[int, set[tuple[str, str, str]]] = {}
        for row in rows:
            groups.setdefault(int(row["id"]), set()).add(
                (str(row["table"]), str(row["from"]), str(row["to"]))
            )
        self.assertIn(
            {
                ("qa_runs", "tenant_id", "tenant_id"),
                ("qa_runs", "run_id", "run_id"),
            },
            groups.values(),
        )

    def test_versioned_schema_rejects_inexact_sql_semantics(self) -> None:
        with sqlite3.connect(self.database) as connection:
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'qa_runs'"
            ).fetchone()[0]
            modified = str(sql).replace(
                "tenant_id TEXT NOT NULL",
                "tenant_id TEXT COLLATE NOCASE NOT NULL",
                1,
            )
            self.assertNotEqual(sql, modified)
            connection.execute("PRAGMA writable_schema = ON")
            connection.execute(
                "UPDATE sqlite_master SET sql = ? WHERE type = 'table' AND name = 'qa_runs'",
                (modified,),
            )
            schema_version = int(
                connection.execute("PRAGMA schema_version").fetchone()[0]
            )
            connection.execute(f"PRAGMA schema_version = {schema_version + 1}")
            connection.execute("PRAGMA writable_schema = OFF")
        with self.assertRaisesRegex(ControlPlaneError, "SQL definitions are not exact"):
            QaControlPlane(self.database)

    def test_event_quota_accepts_boundary_and_rejects_one_over_atomically(self) -> None:
        with patch.object(control_plane_module, "MAX_EVENTS_PER_RUN", 2):
            self.create()
            self.transition("run-1", "start", "start-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.transition("run-1", "pause", "pause-over-event-quota")
            run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
            self.assertEqual(RunStatus.RUNNING, run.status)
            self.assertEqual(
                2,
                len(
                    self.control.list_events(
                        tenant_id="tenant-a", run_id="run-1", limit=2
                    )
                ),
            )

    def test_audit_quota_accepts_boundary_and_rejects_one_over_atomically(self) -> None:
        with patch.object(control_plane_module, "MAX_AUDIT_RECORDS_PER_RUN", 2):
            self.create()
            self.transition("run-1", "start", "start-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.transition("run-1", "pause", "pause-over-audit-quota")
            run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
            self.assertEqual(RunStatus.RUNNING, run.status)
            self.assertEqual(
                2,
                len(
                    self.control.list_audit(
                        tenant_id="tenant-a", run_id="run-1", limit=2
                    )
                ),
            )

    def test_idempotency_quota_rejects_one_over_and_rolls_back_mutation(self) -> None:
        with patch.object(
            control_plane_module, "MAX_IDEMPOTENCY_RECORDS_PER_TENANT", 2
        ):
            self.create()
            self.transition("run-1", "start", "start-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.transition("run-1", "pause", "pause-over-key-quota")
            run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
            self.assertEqual(RunStatus.RUNNING, run.status)
            with self.control._connect() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM qa_idempotency WHERE tenant_id = ?",
                    ("tenant-a",),
                ).fetchone()[0]
            self.assertEqual(2, count)
            self.assertEqual(
                [1, 2],
                [
                    event.sequence
                    for event in self.control.list_events(
                        tenant_id="tenant-a", run_id="run-1", limit=2
                    )
                ],
            )

    def test_per_run_idempotency_quota_uses_the_bound_audit_ledger(self) -> None:
        with patch.object(
            control_plane_module, "MAX_IDEMPOTENCY_RECORDS_PER_RUN", 2
        ):
            self.create()
            self.transition("run-1", "start", "start-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.transition("run-1", "pause", "pause-over-run-key-quota")
            run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
            self.assertEqual(RunStatus.RUNNING, run.status)
            with self.control._connect() as connection:
                key_count = connection.execute(
                    "SELECT COUNT(*) FROM qa_idempotency WHERE tenant_id = ?",
                    ("tenant-a",),
                ).fetchone()[0]
            self.assertEqual(2, key_count)

    def test_total_idempotency_quota_is_enforced_in_the_mutation_transaction(self) -> None:
        with patch.object(
            control_plane_module, "MAX_IDEMPOTENCY_RECORDS_TOTAL", 2
        ):
            self.create()
            self.transition("run-1", "start", "start-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.transition("run-1", "pause", "pause-over-total-key-quota")
            run = self.control.get_run(tenant_id="tenant-a", run_id="run-1")
            self.assertEqual(RunStatus.RUNNING, run.status)
            with self.control._connect() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) FROM qa_idempotency"
                ).fetchone()[0]
            self.assertEqual(2, count)

    def test_run_quotas_reject_one_over_without_a_partial_run(self) -> None:
        with patch.object(control_plane_module, "MAX_RUNS_TOTAL", 1):
            self.create(run_id="run-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.create(run_id="run-2")
            with self.assertRaises(RunNotFound):
                self.control.get_run(tenant_id="tenant-a", run_id="run-2")
            with self.control._connect() as connection:
                run_count = connection.execute(
                    "SELECT COUNT(*) FROM qa_runs"
                ).fetchone()[0]
                key_count = connection.execute(
                    "SELECT COUNT(*) FROM qa_idempotency"
                ).fetchone()[0]
            self.assertEqual(1, run_count)
            self.assertEqual(1, key_count)

    def test_active_run_quota_matches_the_default_recovery_bound(self) -> None:
        with patch.object(control_plane_module, "MAX_ACTIVE_RUNS_PER_TENANT", 1):
            self.create(run_id="run-1")
            with self.assertRaises(ResourceQuotaExceeded):
                self.create(run_id="run-2")
            recovered = self.control.recover_active_runs(
                tenant_id="tenant-a", limit=1
            )
        self.assertEqual(["run-1"], [run.run_id for run in recovered])

    def test_evidence_quota_rejects_one_over_without_a_partial_receipt(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        self.transition(
            "run-1",
            "request_approval",
            "request-evidence-quota",
            scope="run-1:repair-plan",
            subject_digest="a" * 64,
            authorization_ref="authorization-1",
        )

        def register(receipt_id: str, verifier: str) -> None:
            self.control.register_verified_evidence(
                tenant_id="tenant-a",
                receipt_id=receipt_id,
                run_id="run-1",
                scope="run-1:repair-plan",
                subject_digest="a" * 64,
                evidence_digest="b" * 64,
                artifact_digest="c" * 64,
                authorization_ref="authorization-1",
                executor_id="executor-a",
                verifier_id=verifier,
                valid_until="2099-01-01T00:00:00Z",
                registered_by=verifier,
            )

        with patch.object(control_plane_module, "MAX_EVIDENCE_RECEIPTS_TOTAL", 1):
            register("receipt-1", "verifier-b")
            with self.assertRaises(ResourceQuotaExceeded):
                register("receipt-2", "verifier-c")
        with self.control._connect() as connection:
            receipts = connection.execute(
                "SELECT receipt_id FROM qa_verified_evidence ORDER BY receipt_id"
            ).fetchall()
        self.assertEqual(["receipt-1"], [row[0] for row in receipts])
        self.assertEqual(
            4,
            len(self.control.list_audit(tenant_id="tenant-a", run_id="run-1")),
        )

    def test_active_run_recovery_has_a_hard_page_bound(self) -> None:
        self.create(run_id="run-1")
        self.create(run_id="run-2")
        with self.assertRaises(ResourceQuotaExceeded):
            self.control.recover_active_runs(tenant_id="tenant-a", limit=1)
        recovered = self.control.recover_active_runs(tenant_id="tenant-a", limit=2)
        self.assertEqual(2, len(recovered))
        with self.assertRaises(ValueError):
            self.control.recover_active_runs(tenant_id="tenant-a", limit=501)

    def test_history_reads_are_cursor_paginated_with_bounded_pages(self) -> None:
        self.create()
        self.transition("run-1", "start", "start-1")
        self.transition("run-1", "pause", "pause-1")
        self.transition("run-1", "resume", "resume-1")
        first = self.control.list_events(
            tenant_id="tenant-a", run_id="run-1", limit=2
        )
        second = self.control.list_events(
            tenant_id="tenant-a",
            run_id="run-1",
            after_sequence=first[-1].sequence,
            limit=2,
        )
        self.assertEqual([1, 2], [event.sequence for event in first])
        self.assertEqual([3, 4], [event.sequence for event in second])
        audit_first = self.control.list_audit(
            tenant_id="tenant-a", run_id="run-1", limit=2
        )
        audit_second = self.control.list_audit(
            tenant_id="tenant-a",
            run_id="run-1",
            after_audit_id=audit_first[-1].audit_id,
            limit=2,
        )
        self.assertEqual(2, len(audit_first))
        self.assertEqual(2, len(audit_second))
        with self.assertRaises(ValueError):
            self.control.list_events(
                tenant_id="tenant-a", run_id="run-1", limit=501
            )


if __name__ == "__main__":
    unittest.main()
