from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from elmos_foundry.artifacts import ArtifactNotFound, ContentAddressedArtifactStore
from elmos_foundry.canonical import CanonicalError, canonical_digest, strict_json_loads
from elmos_foundry.domain import TenantScope
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.store import (
    FoundryStore,
    IdempotencyConflict,
    RecordNotFound,
    StoreIntegrityError,
    StoreSecurityError,
)


class StoreSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.now = [2_000_000_000.0]
        self.kernel = ExecutionKernel(clock=lambda: self.now[0])
        self.capabilities = (
            "foundry.artifact.read",
            "foundry.artifact.write",
            "foundry.evidence.read",
            "foundry.evidence.write",
            "foundry.outbox.reconcile",
            "foundry.store.read",
            "foundry.store.write",
        )
        self.scope = self._scope("tenant-a", "project-a", "actor-a")
        self.other_scope = self._scope("tenant-b", "project-b", "actor-b")
        self.database_path = self.root / "state" / "foundry.sqlite3"
        self.store = FoundryStore(
            self.database_path,
            context_verifier=self.kernel.require_context,
            clock=lambda: self.now[0],
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _scope(self, tenant: str, project: str, actor: str) -> TenantScope:
        return self.kernel.mint_context(
            tenant_id=tenant,
            project_id=project,
            actor_id=actor,
            environment_id="test-local",
            workspace_digest=canonical_digest({"workspace": project}),
            revision_set_id=canonical_digest({"revision": "abc"}),
            purpose="foundry-core-test",
            capabilities=self.capabilities,
            ttl_seconds=300,
        )

    def test_private_file_idempotency_scope_and_immutable_logs(self) -> None:
        self.assertEqual(stat.S_IMODE(os.stat(self.database_path).st_mode), 0o600)
        first = self.store.begin_run(self.scope, "compile-knowledge", "idem-1", {"input": "alpha"})
        replay = self.store.begin_run(self.scope, "compile-knowledge", "idem-1", {"input": "alpha"})
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.record.run_id, replay.record.run_id)
        with self.assertRaises(IdempotencyConflict):
            self.store.begin_run(self.scope, "compile-knowledge", "idem-1", {"input": "beta"})
        with self.assertRaises(RecordNotFound):
            self.store.get_run(self.other_scope, first.record.run_id)
        event = self.store.append_event(
            self.scope, first.record.run_id, "run.started", {"attempt": 1}
        )
        self.assertTrue(self.store.verify_event_chain(self.scope, first.record.run_id))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(
                "UPDATE foundry_events SET event_type='tampered' WHERE event_id=?",
                (event.event_id,),
            )
        with self.assertRaises(StoreSecurityError):
            self.store.get_run(TenantScope("tenant-a", "project-a", "actor-a"), first.record.run_id)

    def test_schema_attestation_and_lease_revocation(self) -> None:
        self.kernel.revoke_lease(self.scope.lease_id)
        with self.assertRaises(StoreSecurityError):
            self.store.begin_run(self.scope, "op", "idem", {"x": 1})
        self.store.close()
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("CREATE TABLE injected_table(value TEXT)")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(StoreIntegrityError):
            FoundryStore(self.database_path, context_verifier=self.kernel.require_context)

    def test_private_cas_is_tenant_scoped_and_tamper_evident(self) -> None:
        artifacts = ContentAddressedArtifactStore(
            self.root / "artifacts", context_verifier=self.kernel.require_context
        )
        digest = artifacts.put(self.scope, b"immutable evidence")
        self.assertEqual(artifacts.read(self.scope, digest), b"immutable evidence")
        with self.assertRaises(ArtifactNotFound):
            artifacts.read(self.other_scope, digest)

    def test_canonical_json_rejects_duplicate_and_ambiguous_inputs(self) -> None:
        self.assertEqual(strict_json_loads('{"text":"line1\\nline2"}')["text"], "line1\nline2")
        with self.assertRaises(CanonicalError):
            strict_json_loads('{"x":1,"x":2}')
        with self.assertRaises(CanonicalError):
            canonical_digest({"A": 1, "a": 2})

    def test_outbox_reconciliation_requires_exact_provider_receipt_verification(self) -> None:
        unverified, _ = self.store.enqueue_outbox(
            self.scope,
            "provider.effects",
            "effect-1",
            {"request_digest": canonical_digest({"request": 1})},
        )
        with self.assertRaises(StoreSecurityError):
            self.store.record_outbox_attempt(
                self.scope,
                unverified.outbox_id,
                "attempt-1",
                "DELIVERED",
                {},
            )

        def verify_receipt(scope, record, attempt_id, outcome, receipt):
            return receipt == {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "outbox_payload_digest": record.payload_digest,
                "attempt_id": attempt_id,
                "outcome": outcome,
            }

        verified_store = FoundryStore(
            self.root / "state" / "verified-outbox.sqlite3",
            context_verifier=self.kernel.require_context,
            outbox_receipt_verifier=verify_receipt,
            clock=lambda: self.now[0],
        )
        try:
            outbox, replayed = verified_store.enqueue_outbox(
                self.scope,
                "provider.effects",
                "effect-2",
                {"request_digest": canonical_digest({"request": 2})},
            )
            self.assertFalse(replayed)
            with self.assertRaises(StoreSecurityError):
                verified_store.record_outbox_attempt(
                    self.scope,
                    outbox.outbox_id,
                    "attempt-2",
                    "DELIVERED",
                    {"forged": True},
                )
            receipt = {
                "tenant_id": self.scope.tenant_id,
                "project_id": self.scope.project_id,
                "outbox_payload_digest": outbox.payload_digest,
                "attempt_id": "attempt-2",
                "outcome": "DELIVERED",
            }
            attempt, attempt_replayed = verified_store.record_outbox_attempt(
                self.scope,
                outbox.outbox_id,
                "attempt-2",
                "DELIVERED",
                receipt,
            )
            self.assertFalse(attempt_replayed)
            self.assertEqual(attempt.outcome, "DELIVERED")
            self.assertEqual(verified_store.pending_outbox(self.scope), ())
        finally:
            verified_store.close()


if __name__ == "__main__":
    unittest.main()
