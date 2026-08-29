from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from elmos_proof_harness.canonical import digest_object
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.errors import AuthorizationError, ConflictError, StoreError
from elmos_proof_harness.postgres import PostgresStore, postgres_driver_readiness
from elmos_proof_harness.storage import ControlPlaneStore, StorageStatus
from elmos_proof_harness.store import SQLiteStore


class StorageProtocolTests(unittest.TestCase):
    def test_sqlite_implements_shared_protocol_and_receipt_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore(Path(directory) / "local-engineering.sqlite3")
            self.addCleanup(store.close)
            self.assertIsInstance(store, ControlPlaneStore)
            context = SecurityContext("tenant-a", "project-a", "actor-a")
            store.register_scope(context)
            request = {"requestId": "request-1"}
            request_sha256 = digest_object(request, domain="test-control-plane-request")
            claimed, receipt = store.claim_control_plane_receipt(
                context,
                operation="invoke",
                idempotency_key="key-1",
                request_sha256=request_sha256,
                run_id="run-1",
                request=request,
            )
            self.assertTrue(claimed)
            replay, replay_receipt = store.claim_control_plane_receipt(
                context,
                operation="invoke",
                idempotency_key="key-1",
                request_sha256=request_sha256,
                run_id="run-1",
                request=request,
            )
            self.assertFalse(replay)
            self.assertEqual(receipt, replay_receipt)
            completed = store.complete_control_plane_receipt(
                context,
                operation="invoke",
                idempotency_key="key-1",
                request_sha256=request_sha256,
                response={"status": "SUCCEEDED"},
            )
            self.assertEqual(completed.response, {"status": "SUCCEEDED"})
            with self.assertRaises(ConflictError):
                store.claim_control_plane_receipt(
                    context,
                    operation="invoke",
                    idempotency_key="key-1",
                    request_sha256=digest_object({"different": True}, domain="test-control-plane-request"),
                    run_id="run-2",
                    request={"different": True},
                )
            other_actor = SecurityContext("tenant-a", "project-a", "actor-b")
            store.register_scope(other_actor)
            with self.assertRaises(AuthorizationError):
                store.get_control_plane_receipt(
                    other_actor,
                    operation="invoke",
                    idempotency_key="key-1",
                    request_sha256=request_sha256,
                )

    def test_postgres_backend_is_lazy_and_missing_dsn_fails_closed(self) -> None:
        readiness = postgres_driver_readiness()
        self.assertIn(readiness.status, {StorageStatus.READY, StorageStatus.NOT_CONFIGURED, StorageStatus.NOT_READY})
        with self.assertRaises(StoreError) as captured:
            PostgresStore.from_environment(environment={})
        self.assertEqual(captured.exception.code, "POSTGRES_NOT_CONFIGURED")

    def test_migration_contains_production_guards(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "V001__proof_harness_core.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("FORCE ROW LEVEL SECURITY", migration)
        self.assertIn("proof_harness.current_tenant_key()", migration)
        self.assertIn("proof_harness.current_project_key()", migration)
        self.assertIn("content_bytes bytea NOT NULL", migration)
        self.assertIn("runtime_evidence_immutable", migration)
        self.assertIn("external_signature_receipts", migration)
        self.assertIn("attested_status <> 'CERTIFIED' OR certification_authority", migration)
        self.assertNotIn("object_uri text NOT NULL", migration)


if __name__ == "__main__":
    unittest.main()
