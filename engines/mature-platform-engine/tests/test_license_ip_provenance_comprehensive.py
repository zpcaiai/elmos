"""Comprehensive unit tests for LicenseIpProvenanceEngine (Batch 40 Skill 1381)."""

import hashlib
import unittest

from elmos_mature_platform.license_ip_provenance_engine import LicenseIpProvenanceEngine
from elmos_mature_platform.types import (
    LicenseType,
    IpContaminationRisk,
    CodeArtifactLicenseRecord,
)


class TestLicenseIpProvenanceComprehensive(unittest.TestCase):
    """Test suite for license governance, copyleft risk, and IP provenance."""

    def setUp(self) -> None:
        self.engine = LicenseIpProvenanceEngine()
        self.license_text = "Apache License Version 2.0, January 2004..."
        self.digest = hashlib.sha256(self.license_text.encode("utf-8")).hexdigest()
        self.permissive_artifact = CodeArtifactLicenseRecord(
            record_id="art-001",
            artifact_name="fast-json-parser",
            spdx_identifier="Apache-2.0",
            license_type=LicenseType.UNKNOWN,
            contamination_risk=IpContaminationRisk.NONE,
            copyright_holder="Open Source Foundation",
            license_file_digest=self.digest,
        )

    def test_scan_permissive_artifact(self) -> None:
        rec_id = self.engine.scan_artifact(self.permissive_artifact)
        self.assertEqual(rec_id, "art-001")
        rec = self.engine.get_record("art-001")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.license_type, LicenseType.PERMISSIVE)
        self.assertEqual(rec.contamination_risk, IpContaminationRisk.NONE)
        self.assertTrue(rec.is_approved_for_commercial_use)

    def test_scan_copyleft_gpl_contamination(self) -> None:
        gpl_art = CodeArtifactLicenseRecord(
            record_id="art-gpl-002",
            artifact_name="kernel-module-helper",
            spdx_identifier="GPL-3.0",
            license_type=LicenseType.UNKNOWN,
            contamination_risk=IpContaminationRisk.NONE,
            copyright_holder="Free Software Hackers",
        )
        self.engine.scan_artifact(gpl_art)
        rec = self.engine.get_record("art-gpl-002")
        self.assertEqual(rec.license_type, LicenseType.STRONG_COPYLEFT)
        self.assertEqual(rec.contamination_risk, IpContaminationRisk.CRITICAL)
        self.assertFalse(rec.is_approved_for_commercial_use)

    def test_scan_weak_copyleft_mpl(self) -> None:
        mpl_art = CodeArtifactLicenseRecord(
            record_id="art-mpl-003",
            artifact_name="mozilla-cert-store",
            spdx_identifier="MPL-2.0",
            license_type=LicenseType.UNKNOWN,
            contamination_risk=IpContaminationRisk.NONE,
            copyright_holder="Mozilla",
        )
        self.engine.scan_artifact(mpl_art)
        rec = self.engine.get_record("art-mpl-003")
        self.assertEqual(rec.license_type, LicenseType.WEAK_COPYLEFT)
        self.assertEqual(rec.contamination_risk, IpContaminationRisk.MEDIUM)
        self.assertFalse(rec.is_approved_for_commercial_use)

    def test_approve_commercial_use_with_waiver(self) -> None:
        mpl_art = CodeArtifactLicenseRecord(
            record_id="art-mpl-004",
            artifact_name="mozilla-cert-store",
            spdx_identifier="MPL-2.0",
            license_type=LicenseType.WEAK_COPYLEFT,
            contamination_risk=IpContaminationRisk.MEDIUM,
            copyright_holder="Mozilla",
        )
        self.engine.scan_artifact(mpl_art)
        approved = self.engine.approve_commercial_use(
            "art-mpl-004",
            "Dynamic linking with unmodified upstream library; isolated in separate process."
        )
        self.assertTrue(approved.is_approved_for_commercial_use)

    def test_strong_copyleft_requires_dual_license(self) -> None:
        gpl_art = CodeArtifactLicenseRecord(
            record_id="art-gpl-005",
            artifact_name="gpl-tool",
            spdx_identifier="GPL-3.0",
            license_type=LicenseType.STRONG_COPYLEFT,
            contamination_risk=IpContaminationRisk.CRITICAL,
            copyright_holder="Author",
        )
        self.engine.scan_artifact(gpl_art)
        with self.assertRaises(ValueError):
            self.engine.approve_commercial_use("art-gpl-005", "Standard commercial waiver requested.")

        # With dual-licensing proof, it succeeds
        approved = self.engine.approve_commercial_use(
            "art-gpl-005",
            "Enterprise commercial subscription purchased under dual-licensed vendor agreement."
        )
        self.assertTrue(approved.is_approved_for_commercial_use)

    def test_verify_license_digest(self) -> None:
        self.engine.scan_artifact(self.permissive_artifact)
        self.assertTrue(self.engine.verify_license_digest("art-001", self.license_text))
        self.assertFalse(self.engine.verify_license_digest("art-001", "tampered license file text"))

    def test_governance_reporting(self) -> None:
        self.engine.scan_artifact(self.permissive_artifact)
        report = self.engine.get_license_governance_report()
        self.assertEqual(report["total_artifacts"], 1)
        self.assertEqual(report["approved_count"], 1)
        self.assertEqual(report["compliance_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
