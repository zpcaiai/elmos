"""Comprehensive tests for CertificationDatabase SQLite persistence layer."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from elmos_functional_assurance.domain import (
    AssuranceLevel,
    CertificateRecord,
    CertificateStatus,
    ConformityDecision,
    ProductAssuranceLevel,
    SectorType,
)
from elmos_functional_assurance.database import CertificationDatabase


class TestDatabasePersistence(unittest.TestCase):
    """Unit tests for SQLite database operations in CertificationDatabase."""

    def test_in_memory_save_and_retrieve(self) -> None:
        db = CertificationDatabase(":memory:")
        cert = CertificateRecord(
            certificate_id="CERT-MEM-001",
            subject_candidate_digest="sha256:" + "1" * 64,
            tenant_id="TENANT_ALPHA",
            project_id="PROJ_PILOT",
            assurance_level=AssuranceLevel.E3,
            product_level=ProductAssuranceLevel.P02,
            sector=SectorType.AUTOMOTIVE,
            decision=ConformityDecision.CONFORMING,
            status=CertificateStatus.ISSUED,
            scope_description="Autonomous Braking Verification",
            merkle_root_digest="root_" + "a" * 59,
            issued_at="2026-09-01T10:00:00Z",
            expires_at="2027-09-01T10:00:00Z",
            evaluator_id="AUDITOR_01",
            independent_reviewer_id="REVIEWER_02",
            hsm_key_id="KEY_HSM_P384",
            signature_receipt="SIG_REC_ALPHA",
            metadata={"sample_rate": 1000},
        )
        db.save_certificate(cert)

        retrieved = db.get_certificate("CERT-MEM-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.certificate_id, "CERT-MEM-001")
        self.assertEqual(retrieved.tenant_id, "TENANT_ALPHA")
        self.assertEqual(retrieved.project_id, "PROJ_PILOT")
        self.assertEqual(retrieved.assurance_level, AssuranceLevel.E3)
        self.assertEqual(retrieved.product_level, ProductAssuranceLevel.P02)
        self.assertEqual(retrieved.sector, SectorType.AUTOMOTIVE)
        self.assertEqual(retrieved.decision, ConformityDecision.CONFORMING)
        self.assertEqual(retrieved.status, CertificateStatus.ISSUED)
        self.assertEqual(retrieved.metadata, {"sample_rate": 1000})

        db.close()

    def test_get_nonexistent_certificate_returns_none(self) -> None:
        db = CertificationDatabase(":memory:")
        self.assertIsNone(db.get_certificate("CERT-NONEXISTENT"))
        db.close()

    def test_save_certificate_with_none_sector(self) -> None:
        db = CertificationDatabase(":memory:")
        cert = CertificateRecord(
            certificate_id="CERT-NOSECTOR",
            subject_candidate_digest="sha256:" + "2" * 64,
            tenant_id="TENANT_BETA",
            project_id="PROJ_GENERIC",
            assurance_level=AssuranceLevel.E2,
            product_level=ProductAssuranceLevel.P01,
            sector=None,
            decision=ConformityDecision.CONFORMING,
            status=CertificateStatus.DRAFT,
            scope_description="Generic Component Verification",
            merkle_root_digest="root_" + "b" * 59,
            issued_at="2026-09-01T12:00:00Z",
            expires_at="2027-09-01T12:00:00Z",
            evaluator_id="AUDITOR_02",
            independent_reviewer_id="REVIEWER_03",
            hsm_key_id="KEY_HSM_P384",
            signature_receipt="SIG_REC_BETA",
            metadata={},
        )
        db.save_certificate(cert)

        retrieved = db.get_certificate("CERT-NOSECTOR")
        self.assertIsNotNone(retrieved)
        self.assertIsNone(retrieved.sector)
        self.assertEqual(retrieved.status, CertificateStatus.DRAFT)
        db.close()

    def test_update_existing_certificate(self) -> None:
        db = CertificationDatabase(":memory:")
        cert = CertificateRecord(
            certificate_id="CERT-UPDATE",
            subject_candidate_digest="sha256:" + "3" * 64,
            tenant_id="TENANT_GAMMA",
            project_id="PROJ_UPDATE",
            assurance_level=AssuranceLevel.E4,
            product_level=ProductAssuranceLevel.P04,
            sector=SectorType.FINANCIAL,
            decision=ConformityDecision.CONFORMING,
            status=CertificateStatus.ISSUED,
            scope_description="Initial Issue",
            merkle_root_digest="root_" + "c" * 59,
            issued_at="2026-09-01T12:00:00Z",
            expires_at="2027-09-01T12:00:00Z",
            evaluator_id="AUDITOR_01",
            independent_reviewer_id="REVIEWER_01",
            hsm_key_id="KEY_HSM_P384",
            signature_receipt="SIG_ORIG",
            metadata={"version": 1},
        )
        db.save_certificate(cert)

        # Update status to REVOKED and bump version
        cert.status = CertificateStatus.REVOKED
        cert.metadata = {"version": 2, "revocation_reason": "Policy drift"}
        db.save_certificate(cert)

        updated = db.get_certificate("CERT-UPDATE")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, CertificateStatus.REVOKED)
        self.assertEqual(updated.metadata["version"], 2)
        self.assertEqual(updated.metadata["revocation_reason"], "Policy drift")
        db.close()

    def test_disk_database_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_file = Path(tmp_dir).resolve() / "certs.db"
            db = CertificationDatabase(db_file)

            cert = CertificateRecord(
                certificate_id="CERT-DISK-001",
                subject_candidate_digest="sha256:" + "4" * 64,
                tenant_id="TENANT_DISK",
                project_id="PROJ_PERSIST",
                assurance_level=AssuranceLevel.E5,
                product_level=ProductAssuranceLevel.P05,
                sector=SectorType.AVIATION,
                decision=ConformityDecision.CONFORMING,
                status=CertificateStatus.ISSUED,
                scope_description="Flight Control Certification",
                merkle_root_digest="root_" + "d" * 59,
                issued_at="2026-09-01T14:00:00Z",
                expires_at="2027-09-01T14:00:00Z",
                evaluator_id="AUDITOR_AV",
                independent_reviewer_id="REVIEWER_AV",
                hsm_key_id="KEY_HSM_P384",
                signature_receipt="SIG_DISK",
                metadata={"level": "DAL_A"},
            )
            db.save_certificate(cert)
            db.close()

            # Re-open database from disk and check record
            db2 = CertificationDatabase(db_file)
            loaded = db2.get_certificate("CERT-DISK-001")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.certificate_id, "CERT-DISK-001")
            self.assertEqual(loaded.assurance_level, AssuranceLevel.E5)
            self.assertEqual(loaded.product_level, ProductAssuranceLevel.P05)
            self.assertEqual(loaded.sector, SectorType.AVIATION)
            self.assertEqual(loaded.metadata["level"], "DAL_A")
            db2.close()

    def test_schema_tables_exist(self) -> None:
        db = CertificationDatabase(":memory:")
        cursor = db.connection.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        self.assertIn("certificates", tables)
        self.assertIn("worm_merkle_leaves", tables)
        self.assertIn("audit_events", tables)
        db.close()


if __name__ == "__main__":
    unittest.main()
