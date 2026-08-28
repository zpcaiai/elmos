from __future__ import annotations

import sqlite3
import unittest
from datetime import UTC, datetime, timedelta

from elmos_proof_harness.canonical import digest_bytes
from elmos_proof_harness.contracts import ArtifactRef, EvidenceProducer, EvidenceRecord, SecurityContext
from elmos_proof_harness.errors import ConflictError, IntegrityError, NotFoundError
from elmos_proof_harness.evidence import EvidenceService
from elmos_proof_harness.store import SQLiteStore


NOW = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)


class StoreEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore(":memory:")
        self.context = SecurityContext("tenant-a", "project-a", "actor-a")
        self.other = SecurityContext("tenant-b", "project-a", "actor-a")
        self.store.register_scope(self.context, now=NOW)
        self.store.register_scope(self.other, now=NOW)
        self.service = EvidenceService(self.store)
        self.producer = EvidenceProducer(
            execution_id="execution-1",
            source="VERIFIER",
            tool_name="checker",
            tool_digest=digest_bytes(b"checker", domain="tool-binary"),
            environment_revision=digest_bytes(b"environment", domain="environment"),
            independent=True,
        )
        self.subject = digest_bytes(b"subject", domain="repository-revision")

    def tearDown(self) -> None:
        self.store.close()

    def test_exact_bytes_idempotency_and_tenant_isolation(self) -> None:
        content = b"proof-object\x00exact"
        record = self.service.record_bytes(
            self.context,
            subject_revision=self.subject,
            kind="proof-object",
            evidence_class="certified-proof-object",
            scope="module:ledger",
            content=content,
            media_type="application/octet-stream",
            producer=self.producer,
            evidence_id="evidence-1",
            artifact_id="artifact-1",
            created_at=NOW,
            idempotency_key="append-1",
        )
        replay = self.service.record_bytes(
            self.context,
            subject_revision=self.subject,
            kind="proof-object",
            evidence_class="certified-proof-object",
            scope="module:ledger",
            content=content,
            media_type="application/octet-stream",
            producer=self.producer,
            evidence_id="evidence-1",
            artifact_id="artifact-1",
            created_at=NOW,
            idempotency_key="append-1",
        )
        self.assertEqual(record, replay)
        self.assertEqual(1, self.store.count_rows(self.context, "evidence"))
        self.assertEqual(content, self.store.get_evidence(self.context, "evidence-1")[1])
        with self.assertRaises(NotFoundError):
            self.store.get_evidence(self.other, "evidence-1")
        with self.assertRaises(ConflictError):
            self.service.record_bytes(
                self.context,
                subject_revision=self.subject,
                kind="proof-object",
                evidence_class="certified-proof-object",
                scope="module:ledger",
                content=b"different",
                media_type="application/octet-stream",
                producer=self.producer,
                evidence_id="evidence-1",
                artifact_id="artifact-1",
                created_at=NOW,
                idempotency_key="append-1",
            )
        self.assertGreaterEqual(self.store.count_rows(self.context, "audit_events"), 1)
        self.assertEqual(
            self.store.count_rows(self.context, "audit_events"),
            self.store.count_rows(self.context, "outbox_events"),
        )

    def test_digest_mismatch_and_database_append_only_trigger(self) -> None:
        claimed = digest_bytes(b"good", domain="evidence-content")
        record = EvidenceRecord(
            evidence_id="evidence-bad",
            tenant_id=self.context.tenant_id,
            project_id=self.context.project_id,
            actor_id=self.context.actor_id,
            subject_revision=self.subject,
            kind="static",
            evidence_class="compiler-static",
            scope="repository",
            content=ArtifactRef("artifact-bad", claimed, "text/plain", 4),
            producer=self.producer,
            created_at=NOW,
        )
        with self.assertRaises(IntegrityError) as raised:
            self.store.append_evidence(self.context, record, b"evil")
        self.assertEqual("DIGEST_MISMATCH", raised.exception.code)
        self.service.record_bytes(
            self.context,
            subject_revision=self.subject,
            kind="static",
            evidence_class="compiler-static",
            scope="repository",
            content=b"good",
            media_type="text/plain",
            producer=self.producer,
            evidence_id="evidence-good",
            artifact_id="artifact-good",
            created_at=NOW,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(  # deliberate database-boundary negative test
                "UPDATE evidence SET content_bytes=? WHERE tenant_id=? AND project_id=? AND evidence_id=?",
                (b"tamper", self.context.tenant_id, self.context.project_id, "evidence-good"),
            )

    def test_revocation_and_expiry_fail_closed(self) -> None:
        self.service.record_bytes(
            self.context,
            subject_revision=self.subject,
            kind="runtime",
            evidence_class="operational",
            scope="journey:checkout",
            content=b"trace",
            media_type="application/json",
            producer=self.producer,
            evidence_id="evidence-expiring",
            artifact_id="artifact-expiring",
            created_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )
        with self.assertRaises(IntegrityError) as expired:
            self.service.verify(self.context, "evidence-expiring", now=NOW + timedelta(minutes=6))
        self.assertEqual("EVIDENCE_EXPIRED", expired.exception.code)
        self.store.revoke_evidence(self.context, "evidence-expiring", reason="tool compromise", now=NOW)
        with self.assertRaises(IntegrityError) as revoked:
            self.service.verify(self.context, "evidence-expiring", now=NOW)
        self.assertEqual("EVIDENCE_REVOKED", revoked.exception.code)


if __name__ == "__main__":
    unittest.main()
