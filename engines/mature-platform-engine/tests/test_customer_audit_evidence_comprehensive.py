"""Comprehensive tests for CustomerAuditEvidenceEngine (Batch 40 - Skill 1390)."""

from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from elmos_mature_platform.customer_audit_evidence_engine import (
    CustomerAuditEvidenceEngine,
)
from elmos_mature_platform.types import (
    AuditEvidenceType,
    ComplianceFramework,
    CustomerAuditArtifact,
)


class TestCustomerAuditEvidenceComprehensive(unittest.TestCase):
    """Test suite verifying customer audit evidence compilation, Merkle sealing, and attestation."""

    def setUp(self):
        self.engine = CustomerAuditEvidenceEngine(default_expiry_hours=48)

    def test_initiate_package(self):
        """Verify new evidence package starts in preparing state with expiry window."""
        pkg = self.engine.initiate_package(
            customer_id="cust-acme-corp",
            framework=ComplianceFramework.SOC2_TYPE2,
            expiry_hours=24,
        )
        self.assertTrue(pkg.package_id.startswith("pkg-"))
        self.assertEqual(pkg.customer_id, "cust-acme-corp")
        self.assertEqual(pkg.framework, ComplianceFramework.SOC2_TYPE2)
        self.assertEqual(pkg.status, "preparing")
        self.assertEqual(len(pkg.artifacts), 0)

    def test_add_artifact_computes_sha256(self):
        """Verify adding artifact hashes payload bytes deterministically."""
        pkg = self.engine.initiate_package("cust-fintech", ComplianceFramework.PCI_DSS)
        payload = b"access_log_2026_09_10: user=alice action=login ip=10.0.0.1"
        expected_hash = hashlib.sha256(payload).hexdigest()

        art = self.engine.add_artifact(
            pkg.package_id,
            evidence_type=AuditEvidenceType.ACCESS_LOGS,
            title="Q3 VPN Access Logs",
            content_bytes=payload,
        )
        self.assertEqual(art.checksum_sha256, expected_hash)
        self.assertEqual(art.file_size_bytes, len(payload))
        self.assertEqual(len(pkg.artifacts), 1)

    def test_seal_and_sign_computes_merkle_root(self):
        """Verify sealing package calculates Merkle root and transitions status to sealed."""
        pkg = self.engine.initiate_package("cust-health", ComplianceFramework.HIPAA)
        self.engine.add_artifact(
            pkg.package_id,
            AuditEvidenceType.ENCRYPTION_CERTS,
            "TLS Cert Bundle",
            b"CERT_DATA_123",
        )
        self.engine.add_artifact(
            pkg.package_id,
            AuditEvidenceType.BACKUP_LOGS,
            "Snapshot PITR Logs",
            b"BACKUP_SUCCESS_456",
        )

        sealed_pkg = self.engine.seal_and_sign(pkg.package_id, notary_key="test-secret")
        self.assertEqual(sealed_pkg.status, "sealed")
        self.assertTrue(len(sealed_pkg.merkle_root) == 64)

        # Adding artifacts after sealing must raise ValueError
        with self.assertRaises(ValueError):
            self.engine.add_artifact(
                pkg.package_id,
                AuditEvidenceType.INCIDENT_REPORTS,
                "Late Log",
                b"LATE_DATA",
            )

    def test_verify_package_integrity_success_and_tamper(self):
        """Verify cryptographic verification catches tampered artifacts."""
        pkg = self.engine.initiate_package("cust-bank", ComplianceFramework.ISO27001)
        self.engine.add_artifact(
            pkg.package_id,
            AuditEvidenceType.VULNERABILITY_SCANS,
            "SonarQube Clean Scan",
            b"CLEAN_VULN_SCAN_REPORT",
        )
        self.engine.seal_and_sign(pkg.package_id, notary_key="bank-secret")

        # Initial verification succeeds
        result = self.engine.verify_package_integrity(pkg.package_id, notary_key="bank-secret")
        self.assertTrue(result["verified"])
        self.assertTrue(result["merkle_match"])
        self.assertTrue(result["signature_valid"])

        # Tampering with an artifact checksum breaks integrity
        pkg.artifacts[0].checksum_sha256 = "0" * 64
        tampered_result = self.engine.verify_package_integrity(pkg.package_id, notary_key="bank-secret")
        self.assertFalse(tampered_result["verified"])
        self.assertFalse(tampered_result["merkle_match"])

    def test_download_validity_expiration(self):
        """Verify expired download packages return False for download validity."""
        pkg = self.engine.initiate_package("cust-test", ComplianceFramework.SOC2_TYPE2)
        self.engine.add_artifact(pkg.package_id, AuditEvidenceType.ACCESS_LOGS, "Log", b"DATA")
        self.engine.seal_and_sign(pkg.package_id)

        # Before expiration: valid
        self.assertTrue(self.engine.check_download_validity(pkg.package_id))

        # Set expiration to past
        pkg.download_expiry = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.assertFalse(self.engine.check_download_validity(pkg.package_id))

    def test_get_package_report(self):
        """Verify summary report of artifacts by evidence type and total bytes."""
        pkg = self.engine.initiate_package("cust-enterprise", ComplianceFramework.FedRAMP)
        self.engine.add_artifact(pkg.package_id, AuditEvidenceType.CHANGE_RECORDS, "PR 101", b"PR_DIFF")
        self.engine.seal_and_sign(pkg.package_id)

        report = self.engine.get_package_report(pkg.package_id)
        self.assertEqual(report["customer_id"], "cust-enterprise")
        self.assertEqual(report["artifact_count"], 1)
        self.assertEqual(report["by_evidence_type"][AuditEvidenceType.CHANGE_RECORDS.value], 1)


if __name__ == "__main__":
    unittest.main()
