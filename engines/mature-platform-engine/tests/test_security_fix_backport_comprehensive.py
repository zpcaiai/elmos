import unittest
from datetime import datetime, timezone, timedelta
from typing import List

from elmos_mature_platform.types import (
    SecurityFix,
    BackportRecord,
    BackportPriority,
    BackportStatus,
)
from elmos_mature_platform.security_fix_backport_engine import SecurityFixBackportEngine

class TestSecurityFixBackportComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SecurityFixBackportEngine()

    def test_register_fix_basic(self):
        fix = SecurityFix(
            fix_id="f1",
            cve_id="CVE-2024-1000",
            title="SQLi in user sync",
            priority=BackportPriority.HIGH,
            original_version="1.5.0",
        )
        self.assertEqual(self.engine.register_fix(fix), "f1")
        self.assertIn("f1", self.engine._fixes)

    def test_register_fix_sets_created_at(self):
        fix = SecurityFix(
            fix_id="f2",
            cve_id="CVE-2024-1001",
            title="XSS",
            priority=BackportPriority.LOW,
            original_version="1.2.0"
        )
        self.engine.register_fix(fix)
        self.assertTrue(bool(self.engine._fixes["f2"].created_at))

    def test_create_backport_success(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        rec = BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1")
        res = self.engine.create_backport(rec)
        self.assertEqual(res, "b1")
        self.assertEqual(self.engine._backports["b1"].status, BackportStatus.PENDING)

    def test_create_backport_missing_fix(self):
        rec = BackportRecord(backport_id="b1", fix_id="nonexistent", target_version="1.1")
        with self.assertRaises(ValueError):
            self.engine.create_backport(rec)

    def test_create_backport_duplicate(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        with self.assertRaises(ValueError):
            self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.2"))

    def test_start_backport_success(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        bp = self.engine.start_backport("b1")
        self.assertEqual(bp.status, BackportStatus.IN_PROGRESS)

    def test_start_backport_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.start_backport("nonexistent")

    def test_start_backport_wrong_status(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        with self.assertRaises(ValueError):
            self.engine.start_backport("b1")

    def test_apply_backport_success(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        bp = self.engine.apply_backport("b1")
        self.assertEqual(bp.status, BackportStatus.APPLIED)
        self.assertTrue(bool(bp.applied_at))

    def test_apply_backport_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.apply_backport("b1")

    def test_apply_backport_wrong_status(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        with self.assertRaises(ValueError):
            self.engine.apply_backport("b1")

    def test_verify_backport_success(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        self.engine.apply_backport("b1")
        bp = self.engine.verify_backport("b1", "user1", True)
        self.assertEqual(bp.status, BackportStatus.VERIFIED)
        self.assertTrue(bp.test_passed)
        self.assertEqual(bp.verified_by, "user1")
        self.assertTrue(bool(bp.verified_at))

    def test_verify_backport_failed(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        self.engine.apply_backport("b1")
        bp = self.engine.verify_backport("b1", "user1", False)
        self.assertEqual(bp.status, BackportStatus.FAILED)
        self.assertFalse(bp.test_passed)
        self.assertEqual(bp.failure_reason, "Test failed during verification")

    def test_verify_backport_wrong_status(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        with self.assertRaises(ValueError):
            self.engine.verify_backport("b1", "user1", True)

    def test_verify_backport_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.verify_backport("b1", "user1", True)

    def test_skip_backport_success(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        bp = self.engine.skip_backport("b1", "Not applicable")
        self.assertEqual(bp.status, BackportStatus.SKIPPED)
        self.assertEqual(bp.skip_reason, "Not applicable")

    def test_skip_backport_already_finished(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        self.engine.apply_backport("b1")
        self.engine.verify_backport("b1", "user", True)
        with self.assertRaises(ValueError):
            self.engine.skip_backport("b1", "Reason")

    def test_skip_backport_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.skip_backport("b1", "Reason")

    def test_get_pending_backports_all(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.create_backport(BackportRecord(backport_id="b2", fix_id="f1", target_version="1.2"))
        
        self.engine.start_backport("b2")
        
        pending = self.engine.get_pending_backports()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].backport_id, "b1")

    def test_get_pending_backports_filtered(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.register_fix(SecurityFix(fix_id="f2", cve_id="C", title="T", priority=BackportPriority.LOW, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.create_backport(BackportRecord(backport_id="b2", fix_id="f2", target_version="1.1"))
        
        pending = self.engine.get_pending_backports(priority=BackportPriority.HIGH)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].backport_id, "b1")

    def test_get_fix_coverage_success(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.create_backport(BackportRecord(backport_id="b2", fix_id="f1", target_version="1.2"))
        self.engine.start_backport("b1")
        self.engine.apply_backport("b1")
        self.engine.verify_backport("b1", "user", True)
        
        cov = self.engine.get_fix_coverage("f1")
        self.assertEqual(cov["versions"]["1.1"], "verified")
        self.assertEqual(cov["versions"]["1.2"], "pending")
        self.assertEqual(cov["verified_percentage"], 50.0)

    def test_get_fix_coverage_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_fix_coverage("f1")

    def test_get_overdue_backports(self):
        fix = SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0")
        fix.created_at = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        self.engine.register_fix(fix)
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        
        overdue = self.engine.get_overdue_backports(max_age_hours=48)
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].backport_id, "b1")

    def test_get_overdue_backports_not_overdue(self):
        fix = SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0")
        fix.created_at = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        self.engine.register_fix(fix)
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        
        overdue = self.engine.get_overdue_backports(max_age_hours=48)
        self.assertEqual(len(overdue), 0)

    def test_get_version_security_status(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.create_backport(BackportRecord(backport_id="b2", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        
        stat = self.engine.get_version_security_status("1.1")
        self.assertEqual(stat["version"], "1.1")
        self.assertEqual(len(stat["backports"]), 2)
        self.assertEqual(stat["status_counts"]["pending"], 1)
        self.assertEqual(stat["status_counts"]["in_progress"], 1)
        self.assertEqual(stat["status_counts"]["verified"], 0)

    def test_get_backport_report(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        self.engine.apply_backport("b1")
        # Manipulate applied_at to simulate time passing
        bp = self.engine._backports["b1"]
        bp.applied_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        
        self.engine.verify_backport("b1", "user", True)
        
        rep = self.engine.get_backport_report()
        self.assertEqual(rep["by_priority"]["high"], 1)
        self.assertEqual(rep["by_status"]["verified"], 1)
        self.assertTrue(rep["avg_time_to_verify_hours"] >= 2.0)
        self.assertEqual(rep["verified_coverage_percentage"], 100.0)

    def test_get_backport_report_empty(self):
        rep = self.engine.get_backport_report()
        self.assertEqual(rep["verified_coverage_percentage"], 0.0)
        self.assertEqual(rep["avg_time_to_verify_hours"], 0.0)

    def test_get_fix_coverage_empty(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        cov = self.engine.get_fix_coverage("f1")
        self.assertEqual(cov["verified_percentage"], 0.0)

    def test_invalid_date_in_overdue(self):
        fix = SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0")
        fix.created_at = "invalid date"
        self.engine.register_fix(fix)
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        overdue = self.engine.get_overdue_backports()
        self.assertEqual(len(overdue), 0)

    def test_invalid_date_in_report(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        bp = self.engine.apply_backport("b1")
        bp.applied_at = "invalid"
        self.engine.verify_backport("b1", "u", True)
        
        rep = self.engine.get_backport_report()
        self.assertEqual(rep["avg_time_to_verify_hours"], 0.0)

    def test_skip_failed_backport(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.start_backport("b1")
        self.engine.apply_backport("b1")
        self.engine.verify_backport("b1", "user", False)
        
        with self.assertRaises(ValueError):
            self.engine.skip_backport("b1", "Reason")

    def test_skip_skipped_backport(self):
        self.engine.register_fix(SecurityFix(fix_id="f1", cve_id="C", title="T", priority=BackportPriority.HIGH, original_version="1.0"))
        self.engine.create_backport(BackportRecord(backport_id="b1", fix_id="f1", target_version="1.1"))
        self.engine.skip_backport("b1", "First skip")
        
        with self.assertRaises(ValueError):
            self.engine.skip_backport("b1", "Second skip")

if __name__ == '__main__':
    unittest.main()
