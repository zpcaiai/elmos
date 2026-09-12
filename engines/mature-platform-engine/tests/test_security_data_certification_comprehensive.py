import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.types import (
    SecurityControl,
    SecurityControlStatus,
    DataClassification,
    DataProtectionLevel
)
from elmos_mature_platform.security_data_certification_engine import SecurityDataCertificationEngine


class TestSecurityDataCertificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SecurityDataCertificationEngine()

    def test_register_control_success(self):
        ctrl = SecurityControl(control_id="C1", framework="SOC2", control_name="Access Control")
        res = self.engine.register_control(ctrl)
        self.assertEqual(res, "C1")
        self.assertIn("C1", self.engine._controls)

    def test_verify_control_success(self):
        ctrl = SecurityControl(control_id="C2", framework="SOC2", control_name="Auth")
        self.engine.register_control(ctrl)
        verified = self.engine.verify_control("C2", "Alice", ["EVID-1"])
        self.assertEqual(verified.status, SecurityControlStatus.VERIFIED)
        self.assertEqual(verified.verified_by, "Alice")
        self.assertEqual(verified.evidence_ids, ["EVID-1"])
        self.assertTrue(verified.verified_at)

    def test_verify_control_not_found(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.engine.verify_control("MISSING", "Alice", ["EVID-1"])

    def test_verify_control_no_evidence(self):
        ctrl = SecurityControl(control_id="C3", framework="SOC2", control_name="Auth")
        self.engine.register_control(ctrl)
        with self.assertRaisesRegex(ValueError, "Cannot verify without evidence"):
            self.engine.verify_control("C3", "Alice", [])

    def test_fail_control_success(self):
        ctrl = SecurityControl(control_id="C4", framework="SOC2", control_name="Auth", description="Desc")
        self.engine.register_control(ctrl)
        failed = self.engine.fail_control("C4", "Missing MFA")
        self.assertEqual(failed.status, SecurityControlStatus.FAILED)
        self.assertIn("Missing MFA", failed.description)

    def test_fail_control_not_found(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.engine.fail_control("MISSING", "Reason")

    def test_classify_data_success(self):
        dc = DataClassification(
            classification_id="D1",
            data_type="PII",
            protection_level=DataProtectionLevel.INTERNAL
        )
        res = self.engine.classify_data(dc)
        self.assertEqual(res, "D1")

    def test_assess_data_compliance_compliant(self):
        dc = DataClassification(
            classification_id="D2",
            data_type="general",
            protection_level=DataProtectionLevel.INTERNAL,
            retention_days=100
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D2")
        self.assertTrue(res["compliant"])
        self.assertEqual(len(res["issues"]), 0)

    def test_assess_data_compliance_confidential_unencrypted(self):
        dc = DataClassification(
            classification_id="D3",
            data_type="financial",
            protection_level=DataProtectionLevel.CONFIDENTIAL,
            encrypted_at_rest=True,
            encrypted_in_transit=False
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D3")
        self.assertFalse(res["compliant"])
        self.assertIn("CONFIDENTIAL+ data must be encrypted", res["issues"][0])

    def test_assess_data_compliance_restricted_cross_border(self):
        dc = DataClassification(
            classification_id="D4",
            data_type="HR",
            protection_level=DataProtectionLevel.RESTRICTED,
            encrypted_at_rest=True,
            encrypted_in_transit=True,
            cross_border=True
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D4")
        self.assertFalse(res["compliant"])
        self.assertIn("RESTRICTED+ data cannot be cross_border", res["issues"][0])

    def test_assess_data_compliance_pci_retention_fail(self):
        dc = DataClassification(
            classification_id="D5",
            data_type="PCI",
            protection_level=DataProtectionLevel.CONFIDENTIAL,
            encrypted_at_rest=True,
            encrypted_in_transit=True,
            retention_days=400
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D5")
        self.assertFalse(res["compliant"])
        self.assertIn("PCI/PHI data requires <= 365 day retention", res["issues"][0])

    def test_assess_data_compliance_pci_retention_pass(self):
        dc = DataClassification(
            classification_id="D6",
            data_type="PCI",
            protection_level=DataProtectionLevel.CONFIDENTIAL,
            encrypted_at_rest=True,
            encrypted_in_transit=True,
            retention_days=300
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D6")
        self.assertTrue(res["compliant"])

    def test_assess_data_compliance_phi_retention_fail(self):
        dc = DataClassification(
            classification_id="D7",
            data_type="PHI",
            protection_level=DataProtectionLevel.RESTRICTED,
            encrypted_at_rest=True,
            encrypted_in_transit=True,
            retention_days=500
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D7")
        self.assertFalse(res["compliant"])
        self.assertIn("PCI/PHI data requires <= 365 day retention", res["issues"][0])

    def test_assess_data_compliance_not_found(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.engine.assess_data_compliance("MISSING")

    def test_get_framework_coverage_empty(self):
        res = self.engine.get_framework_coverage("SOC2")
        self.assertEqual(res["total_controls"], 0)
        self.assertEqual(res["status_counts"][SecurityControlStatus.VERIFIED.value], 0)

    def test_get_framework_coverage_populated(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1"))
        self.engine.register_control(SecurityControl("C2", "SOC2", "C2", status=SecurityControlStatus.PARTIAL))
        self.engine.register_control(SecurityControl("C3", "ISO", "C3"))
        
        res = self.engine.get_framework_coverage("SOC2")
        self.assertEqual(res["total_controls"], 2)
        self.assertEqual(res["status_counts"][SecurityControlStatus.NOT_IMPLEMENTED.value], 1)
        self.assertEqual(res["status_counts"][SecurityControlStatus.PARTIAL.value], 1)

    def test_get_unverified_controls(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", status=SecurityControlStatus.VERIFIED))
        self.engine.register_control(SecurityControl("C2", "SOC2", "C2", status=SecurityControlStatus.PARTIAL))
        
        unverified = self.engine.get_unverified_controls()
        self.assertEqual(len(unverified), 1)
        self.assertEqual(unverified[0].control_id, "C2")

    def test_get_overdue_controls_no_date(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1"))
        overdue = self.engine.get_overdue_controls()
        self.assertEqual(len(overdue), 1)

    def test_get_overdue_controls_past_due(self):
        past = (datetime.utcnow() - timedelta(days=100)).isoformat()
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", last_tested=past, test_frequency_days=90))
        overdue = self.engine.get_overdue_controls()
        self.assertEqual(len(overdue), 1)

    def test_get_overdue_controls_not_due(self):
        recent = (datetime.utcnow() - timedelta(days=10)).isoformat()
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", last_tested=recent, test_frequency_days=90))
        overdue = self.engine.get_overdue_controls()
        self.assertEqual(len(overdue), 0)

    def test_get_overdue_controls_custom_max_age(self):
        recent = (datetime.utcnow() - timedelta(days=10)).isoformat()
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", last_tested=recent, test_frequency_days=90))
        # Custom max age is 5 days, so it's overdue
        overdue = self.engine.get_overdue_controls(max_age_days=5)
        self.assertEqual(len(overdue), 1)

    def test_get_certification_readiness_empty(self):
        res = self.engine.get_certification_readiness("SOC2")
        self.assertFalse(res["ready"])
        self.assertEqual(res["percent_verified"], 0.0)

    def test_get_certification_readiness_not_ready(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", status=SecurityControlStatus.VERIFIED))
        self.engine.register_control(SecurityControl("C2", "SOC2", "C2", status=SecurityControlStatus.FAILED))
        res = self.engine.get_certification_readiness("SOC2")
        self.assertFalse(res["ready"])
        self.assertEqual(res["percent_verified"], 50.0)
        self.assertIn("C2", res["blockers"])
        self.assertEqual(len(res["gaps"]), 0)

    def test_get_certification_readiness_ready(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", status=SecurityControlStatus.VERIFIED))
        self.engine.register_control(SecurityControl("C2", "SOC2", "C2", status=SecurityControlStatus.VERIFIED))
        res = self.engine.get_certification_readiness("SOC2")
        self.assertTrue(res["ready"])
        self.assertEqual(res["percent_verified"], 100.0)

    def test_get_certification_readiness_with_gaps(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", status=SecurityControlStatus.NOT_IMPLEMENTED))
        res = self.engine.get_certification_readiness("SOC2")
        self.assertFalse(res["ready"])
        self.assertIn("C1", res["gaps"])

    def test_get_data_protection_report(self):
        self.engine.classify_data(DataClassification("D1", "PII", DataProtectionLevel.PUBLIC))
        self.engine.classify_data(DataClassification("D2", "PHI", DataProtectionLevel.RESTRICTED, encrypted_at_rest=True, encrypted_in_transit=True, cross_border=True))
        
        report = self.engine.get_data_protection_report()
        self.assertEqual(report[DataProtectionLevel.PUBLIC.value]["total"], 1)
        self.assertEqual(report[DataProtectionLevel.RESTRICTED.value]["total"], 1)
        self.assertEqual(report[DataProtectionLevel.RESTRICTED.value]["fully_encrypted"], 1)
        self.assertEqual(report[DataProtectionLevel.RESTRICTED.value]["cross_border"], 1)

    def test_get_security_posture_empty(self):
        res = self.engine.get_security_posture()
        self.assertEqual(len(res["frameworks"]), 0)
        self.assertEqual(len(res["critical_gaps"]), 0)

    def test_get_security_posture_populated(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", status=SecurityControlStatus.VERIFIED))
        self.engine.register_control(SecurityControl("C2", "ISO", "C2", status=SecurityControlStatus.FAILED))
        
        res = self.engine.get_security_posture()
        self.assertIn("SOC2", res["frameworks"])
        self.assertEqual(res["frameworks"]["SOC2"]["coverage_percent"], 100.0)
        self.assertIn("ISO", res["frameworks"])
        self.assertEqual(res["frameworks"]["ISO"]["coverage_percent"], 0.0)
        self.assertIn("C2", res["critical_gaps"])

    def test_verify_control_already_verified(self):
        # Even if already verified, verify updates timestamp and evidence
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", status=SecurityControlStatus.VERIFIED))
        verified = self.engine.verify_control("C1", "Bob", ["NEW_EVID"])
        self.assertEqual(verified.evidence_ids, ["NEW_EVID"])
        self.assertEqual(verified.verified_by, "Bob")

    def test_assess_data_compliance_top_secret(self):
        dc = DataClassification(
            classification_id="D1",
            data_type="military",
            protection_level=DataProtectionLevel.TOP_SECRET,
            encrypted_at_rest=True,
            encrypted_in_transit=True,
            cross_border=False
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D1")
        self.assertTrue(res["compliant"])

    def test_assess_data_compliance_top_secret_fail(self):
        dc = DataClassification(
            classification_id="D1",
            data_type="military",
            protection_level=DataProtectionLevel.TOP_SECRET,
            encrypted_at_rest=True,
            encrypted_in_transit=True,
            cross_border=True # Should fail
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D1")
        self.assertFalse(res["compliant"])

    def test_assess_data_compliance_pci_no_retention_fail(self):
        # if retention is 0, it passes
        dc = DataClassification(
            classification_id="D1",
            data_type="PCI",
            protection_level=DataProtectionLevel.PUBLIC,
            retention_days=0
        )
        self.engine.classify_data(dc)
        res = self.engine.assess_data_compliance("D1")
        self.assertTrue(res["compliant"])

    def test_invalid_date_in_overdue(self):
        self.engine.register_control(SecurityControl("C1", "SOC2", "C1", last_tested="INVALID_DATE"))
        overdue = self.engine.get_overdue_controls()
        self.assertEqual(len(overdue), 1)

if __name__ == "__main__":
    unittest.main()
