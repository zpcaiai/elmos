"""Comprehensive test suite for MatureProductEvidencePackEngine (B45 - Skill 1459)."""

import unittest

from elmos_mature_platform.mature_product_evidence_pack_engine import (
    MatureProductEvidencePackEngine,
)
from elmos_mature_platform.types import (
    ComprehensiveEvidencePack,
    EvidenceArtifactEntry,
    EvidenceBundleStatus,
)


class TestMatureProductEvidencePackComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MatureProductEvidencePackEngine()

    def test_create_evidence_pack_initial_state(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        self.assertTrue(pack.pack_id.startswith("evp-"))
        self.assertEqual(pack.product_name, "ElmosPlatform")
        self.assertEqual(pack.version, "v4.5.0")
        self.assertEqual(pack.status, EvidenceBundleStatus.DRAFT)
        self.assertEqual(pack.total_artifacts, 0)
        self.assertFalse(pack.release_gate_passed)

    def test_add_artifact_entry(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        entry = self.engine.add_artifact_entry(
            pack_id=pack.pack_id,
            category="unit-test-results",
            content_bytes=b'{"passed": 3320, "failed": 0}',
            attestation_signer="ci-attestor",
        )
        self.assertTrue(entry.entry_id.startswith("art-"))
        self.assertEqual(entry.category, "unit-test-results")
        self.assertTrue(entry.verified)
        self.assertEqual(entry.size_bytes, len(b'{"passed": 3320, "failed": 0}'))
        self.assertEqual(pack.total_artifacts, 1)

    def test_compute_merkle_root_deterministic(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        self.engine.add_artifact_entry(pack.pack_id, "sbom", b"CycloneDX-SBOM-v1.4")
        self.engine.add_artifact_entry(pack.pack_id, "sre-slos", b"SLO-Report-99.99")
        self.engine.add_artifact_entry(pack.pack_id, "security-scan", b"VEX-Zero-Highs")

        root1 = self.engine.compute_merkle_root(pack.pack_id)
        root2 = self.engine.compute_merkle_root(pack.pack_id)
        self.assertEqual(root1, root2)
        self.assertEqual(len(root1), 64)  # Valid SHA-256 hex string

    def test_seal_evidence_pack(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        self.engine.add_artifact_entry(pack.pack_id, "audit-log", b"Audit-Signed-Receipt")
        sealed = self.engine.seal_evidence_pack(
            pack_id=pack.pack_id,
            certifier="lead-auditor@example.com",
            release_gate_passed=True,
        )
        self.assertEqual(sealed.status, EvidenceBundleStatus.SEALED)
        self.assertTrue(sealed.release_gate_passed)
        self.assertEqual(sealed.certified_by, "lead-auditor@example.com")
        self.assertTrue(sealed.sealed_at)

        # Cannot add artifacts to sealed pack
        with self.assertRaises(ValueError):
            self.engine.add_artifact_entry(pack.pack_id, "late-artifact", b"fail")

    def test_seal_empty_pack_raises_error(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        with self.assertRaises(ValueError):
            self.engine.seal_evidence_pack(pack.pack_id, "certifier")

    def test_verify_pack_integrity_and_tamper_detection(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        self.engine.add_artifact_entry(pack.pack_id, "attestation-1", b"Data-1")
        self.engine.add_artifact_entry(pack.pack_id, "attestation-2", b"Data-2")
        root = self.engine.compute_merkle_root(pack.pack_id)

        # Valid verification
        self.assertTrue(self.engine.verify_pack_integrity(pack.pack_id, root))

        # Tampered / mismatched root detection
        fake_root = "0" * 64
        self.assertFalse(self.engine.verify_pack_integrity(pack.pack_id, fake_root))
        self.assertEqual(pack.status, EvidenceBundleStatus.TAMPERED)

    def test_get_evidence_pack_report(self):
        pack = self.engine.create_evidence_pack("ElmosPlatform", "v4.5.0")
        self.engine.add_artifact_entry(pack.pack_id, "tests", b"Test-Results")
        self.engine.add_artifact_entry(pack.pack_id, "tests", b"More-Tests")
        self.engine.add_artifact_entry(pack.pack_id, "security", b"Trivy-Scan")
        self.engine.seal_evidence_pack(pack.pack_id, "cert-officer", release_gate_passed=True)

        report = self.engine.get_evidence_pack_report(pack.pack_id)
        self.assertEqual(report["total_artifacts"], 3)
        self.assertEqual(report["category_breakdown"]["tests"], 2)
        self.assertEqual(report["category_breakdown"]["security"], 1)
        self.assertEqual(report["status"], EvidenceBundleStatus.SEALED.value)

    def test_audit_logging(self):
        pack = self.engine.create_evidence_pack("AuditTest", "v1.0")
        self.engine.add_artifact_entry(pack.pack_id, "data", b"bytes")
        logs = self.engine.get_audit_log()
        self.assertGreaterEqual(len(logs), 2)
        actions = [log["action"] for log in logs]
        self.assertIn("evidence_pack_created", actions)
        self.assertIn("artifact_added", actions)


if __name__ == "__main__":
    unittest.main()
