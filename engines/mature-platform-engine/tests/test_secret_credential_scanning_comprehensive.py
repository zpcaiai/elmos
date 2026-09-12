import unittest
from datetime import datetime, timezone, timedelta
from typing import Any

from elmos_mature_platform.types import (
    SecretType,
    SecretFindingStatus,
    SecretScanFinding,
    SecretScanPolicy
)
from elmos_mature_platform.secret_credential_scanning_engine import SecretCredentialScanningEngine

class TestSecretCredentialScanningEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SecretCredentialScanningEngine()

    def test_01_create_policy_success(self):
        policy = SecretScanPolicy(policy_id="pol-1")
        self.engine.create_policy(policy)
        self.assertIn("pol-1", self.engine.policies)

    def test_02_create_policy_overwrite(self):
        policy1 = SecretScanPolicy(policy_id="pol-1", block_on_active_secrets=True)
        self.engine.create_policy(policy1)
        policy2 = SecretScanPolicy(policy_id="pol-1", block_on_active_secrets=False)
        self.engine.create_policy(policy2)
        self.assertFalse(self.engine.policies["pol-1"].block_on_active_secrets)

    def test_03_report_finding_success(self):
        finding = SecretScanFinding(
            finding_id="f-1",
            secret_type=SecretType.API_KEY,
            file_path="src/main.py"
        )
        res = self.engine.report_finding(finding)
        self.assertEqual(res, "f-1")
        self.assertIn("f-1", self.engine.findings)

    def test_04_report_finding_auto_detected_at(self):
        finding = SecretScanFinding(
            finding_id="f-1",
            secret_type=SecretType.API_KEY,
            file_path="src/main.py"
        )
        self.engine.report_finding(finding)
        self.assertNotEqual(self.engine.findings["f-1"].detected_at, "")

    def test_05_get_findings_no_filter(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        self.engine.report_finding(SecretScanFinding("f-2", SecretType.PASSWORD, "p2"))
        findings = self.engine.get_findings()
        self.assertEqual(len(findings), 2)

    def test_06_get_findings_filter_status(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        finding2 = SecretScanFinding("f-2", SecretType.PASSWORD, "p2")
        finding2.status = SecretFindingStatus.REVOKED
        self.engine.report_finding(finding2)
        
        findings = self.engine.get_findings(status=SecretFindingStatus.ACTIVE)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_id, "f-1")

    def test_07_get_findings_filter_type(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        self.engine.report_finding(SecretScanFinding("f-2", SecretType.PASSWORD, "p2"))
        
        findings = self.engine.get_findings(secret_type=SecretType.PASSWORD)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_id, "f-2")

    def test_08_get_findings_filter_both(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", status=SecretFindingStatus.ACTIVE))
        self.engine.report_finding(SecretScanFinding("f-2", SecretType.API_KEY, "p2", status=SecretFindingStatus.REVOKED))
        self.engine.report_finding(SecretScanFinding("f-3", SecretType.PASSWORD, "p3", status=SecretFindingStatus.ACTIVE))
        
        findings = self.engine.get_findings(status=SecretFindingStatus.ACTIVE, secret_type=SecretType.API_KEY)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_id, "f-1")

    def test_09_get_findings_no_match(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        findings = self.engine.get_findings(secret_type=SecretType.CERTIFICATE)
        self.assertEqual(len(findings), 0)

    def test_10_mark_rotated_success(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        f = self.engine.mark_rotated("f-1")
        self.assertEqual(f.status, SecretFindingStatus.ROTATED)
        self.assertNotEqual(f.rotated_at, "")

    def test_11_mark_rotated_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.mark_rotated("f-missing")

    def test_12_mark_revoked_success(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        f = self.engine.mark_revoked("f-1")
        self.assertEqual(f.status, SecretFindingStatus.REVOKED)

    def test_13_mark_revoked_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.mark_revoked("f-missing")

    def test_14_mark_false_positive_success(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1"))
        f = self.engine.mark_false_positive("f-1", "test reason")
        self.assertEqual(f.status, SecretFindingStatus.FALSE_POSITIVE)

    def test_15_mark_false_positive_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.mark_false_positive("f-missing", "test reason")

    def test_16_evaluate_policy_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy("pol-missing")

    def test_17_evaluate_policy_pass(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", block_on_active_secrets=True, max_allowed_findings=5))
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", status=SecretFindingStatus.REVOKED))
        res = self.engine.evaluate_policy("pol-1")
        self.assertTrue(res["passed"])

    def test_18_evaluate_policy_fail_active(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", block_on_active_secrets=True))
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", status=SecretFindingStatus.ACTIVE))
        res = self.engine.evaluate_policy("pol-1")
        self.assertFalse(res["passed"])
        self.assertIn("Active secrets found", res["violations"])

    def test_19_evaluate_policy_fail_max_findings(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", block_on_active_secrets=False, max_allowed_findings=1))
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", status=SecretFindingStatus.REVOKED))
        self.engine.report_finding(SecretScanFinding("f-2", SecretType.PASSWORD, "p2", status=SecretFindingStatus.REVOKED))
        res = self.engine.evaluate_policy("pol-1")
        self.assertFalse(res["passed"])

    def test_20_evaluate_policy_excluded_paths(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", block_on_active_secrets=True, excluded_paths=["tests/mock.py"]))
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "tests/mock.py", status=SecretFindingStatus.ACTIVE))
        res = self.engine.evaluate_policy("pol-1")
        self.assertTrue(res["passed"])

    def test_21_evaluate_policy_excluded_types(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", block_on_active_secrets=True, excluded_types=[SecretType.GENERIC]))
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.GENERIC, "src/main.py", status=SecretFindingStatus.ACTIVE))
        res = self.engine.evaluate_policy("pol-1")
        self.assertTrue(res["passed"])

    def test_22_get_overdue_rotations_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_overdue_rotations("pol-missing", datetime.now(timezone.utc).isoformat())

    def test_23_get_overdue_rotations_none(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", require_rotation_within_hours=24))
        now = datetime.now(timezone.utc)
        f = SecretScanFinding("f-1", SecretType.API_KEY, "p1", detected_at=now.isoformat())
        self.engine.report_finding(f)
        
        overdue = self.engine.get_overdue_rotations("pol-1", (now + timedelta(hours=10)).isoformat())
        self.assertEqual(len(overdue), 0)

    def test_24_get_overdue_rotations_found(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", require_rotation_within_hours=24))
        now = datetime.now(timezone.utc)
        f = SecretScanFinding("f-1", SecretType.API_KEY, "p1", detected_at=now.isoformat())
        self.engine.report_finding(f)
        
        overdue = self.engine.get_overdue_rotations("pol-1", (now + timedelta(hours=25)).isoformat())
        self.assertEqual(len(overdue), 1)

    def test_25_get_overdue_rotations_ignore_inactive(self):
        self.engine.create_policy(SecretScanPolicy("pol-1", require_rotation_within_hours=24))
        now = datetime.now(timezone.utc)
        f = SecretScanFinding("f-1", SecretType.API_KEY, "p1", status=SecretFindingStatus.REVOKED, detected_at=now.isoformat())
        self.engine.report_finding(f)
        
        overdue = self.engine.get_overdue_rotations("pol-1", (now + timedelta(hours=25)).isoformat())
        self.assertEqual(len(overdue), 0)

    def test_26_get_findings_by_author_match(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", author="alice"))
        self.engine.report_finding(SecretScanFinding("f-2", SecretType.PASSWORD, "p2", author="bob"))
        res = self.engine.get_findings_by_author("alice")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].finding_id, "f-1")

    def test_27_get_findings_by_author_no_match(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", author="alice"))
        res = self.engine.get_findings_by_author("charlie")
        self.assertEqual(len(res), 0)

    def test_28_compute_entropy_empty(self):
        self.assertEqual(self.engine.compute_entropy(""), 0.0)

    def test_29_compute_entropy_single_char(self):
        self.assertEqual(self.engine.compute_entropy("aaaaa"), 0.0)

    def test_30_compute_entropy_high(self):
        # random string with all different characters has log2(len) entropy
        s = "abcdefgh"
        self.assertAlmostEqual(self.engine.compute_entropy(s), 3.0)

    def test_31_get_scanning_report_empty(self):
        report = self.engine.get_scanning_report()
        self.assertEqual(report["total_findings"], 0)
        self.assertEqual(report["by_type"], {})
        self.assertEqual(report["by_status"], {})

    def test_32_get_scanning_report_mixed(self):
        self.engine.report_finding(SecretScanFinding("f-1", SecretType.API_KEY, "p1", status=SecretFindingStatus.ACTIVE, severity="high"))
        self.engine.report_finding(SecretScanFinding("f-2", SecretType.API_KEY, "p2", status=SecretFindingStatus.REVOKED, severity="medium"))
        self.engine.report_finding(SecretScanFinding("f-3", SecretType.PASSWORD, "p3", status=SecretFindingStatus.ACTIVE, severity="high"))
        
        report = self.engine.get_scanning_report()
        self.assertEqual(report["total_findings"], 3)
        self.assertEqual(report["by_type"][SecretType.API_KEY.value], 2)
        self.assertEqual(report["by_type"][SecretType.PASSWORD.value], 1)
        self.assertEqual(report["by_status"][SecretFindingStatus.ACTIVE.value], 2)
        self.assertEqual(report["by_status"][SecretFindingStatus.REVOKED.value], 1)
        self.assertEqual(report["by_severity"]["high"], 2)
        self.assertEqual(report["by_severity"]["medium"], 1)

if __name__ == '__main__':
    unittest.main()
