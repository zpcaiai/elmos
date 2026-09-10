import unittest
from typing import List
from elmos_mature_platform.types import (
    ReadinessLevel,
    UpgradeCheckCategory,
    UpgradeCheck,
    UpgradeReadinessAssessment
)
from elmos_mature_platform.customer_upgrade_readiness_engine import CustomerUpgradeReadinessEngine

class TestCustomerUpgradeReadinessEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CustomerUpgradeReadinessEngine()

    def test_01_create_assessment(self):
        a = UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0")
        aid = self.engine.create_assessment(a)
        self.assertEqual(aid, "a1")

    def test_02_create_assessment_duplicate(self):
        a = UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0")
        self.engine.create_assessment(a)
        with self.assertRaises(ValueError):
            self.engine.create_assessment(a)

    def test_03_add_check(self):
        c = UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test Check")
        cid = self.engine.add_check(c)
        self.assertEqual(cid, "c1")

    def test_04_link_check(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test"))
        self.engine.link_check("a1", "c1")
        a = self.engine.assessments["a1"]
        self.assertIn("c1", a.checks)

    def test_05_link_check_duplicate_is_idempotent(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test"))
        self.engine.link_check("a1", "c1")
        self.engine.link_check("a1", "c1")
        a = self.engine.assessments["a1"]
        self.assertEqual(len(a.checks), 1)

    def test_06_link_check_invalid_assessment(self):
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test"))
        with self.assertRaises(ValueError):
            self.engine.link_check("nonexistent", "c1")

    def test_07_link_check_invalid_check(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        with self.assertRaises(ValueError):
            self.engine.link_check("a1", "nonexistent")

    def test_08_run_check_success(self):
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test"))
        self.engine.run_check("c1", True)
        self.assertTrue(self.engine.checks["c1"].passed)

    def test_09_run_check_failure(self):
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test", passed=True))
        self.engine.run_check("c1", False)
        self.assertFalse(self.engine.checks["c1"].passed)

    def test_10_run_check_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.run_check("nonexistent", True)

    def test_11_evaluate_empty_assessment(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.readiness, ReadinessLevel.NOT_READY)

    def test_12_evaluate_all_passed(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test", passed=True))
        self.engine.link_check("a1", "c1")
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.readiness, ReadinessLevel.READY)
        self.assertEqual(a.overall_score, 100.0)

    def test_13_evaluate_blocked(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test", passed=False, blocking=True))
        self.engine.link_check("a1", "c1")
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.readiness, ReadinessLevel.BLOCKED)

    def test_14_evaluate_ready_with_actions(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "Test", passed=False, blocking=False))
        self.engine.link_check("a1", "c1")
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.readiness, ReadinessLevel.READY_WITH_ACTIONS)

    def test_15_evaluate_mixed_checks(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=True))
        self.engine.add_check(UpgradeCheck("c2", UpgradeCheckCategory.DEPENDENCY, "T2", passed=False, blocking=False))
        self.engine.link_check("a1", "c1")
        self.engine.link_check("a1", "c2")
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.readiness, ReadinessLevel.READY_WITH_ACTIONS)
        self.assertEqual(a.overall_score, 50.0)

    def test_16_evaluate_invalid_assessment(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_readiness("nonexistent")

    def test_17_get_remediation_plan(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=False, remediation="Fix it", effort_hours=2.5))
        self.engine.link_check("a1", "c1")
        plan = self.engine.get_remediation_plan("a1")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["remediation"], "Fix it")

    def test_18_get_remediation_plan_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_remediation_plan("nonexistent")

    def test_19_get_total_effort(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=False, effort_hours=2.5))
        self.engine.add_check(UpgradeCheck("c2", UpgradeCheckCategory.DEPENDENCY, "T2", passed=False, effort_hours=3.5))
        self.engine.link_check("a1", "c1")
        self.engine.link_check("a1", "c2")
        self.assertEqual(self.engine.get_total_effort("a1"), 6.0)

    def test_20_get_total_effort_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_total_effort("nonexistent")

    def test_21_get_blocking_issues(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=False, blocking=True))
        self.engine.add_check(UpgradeCheck("c2", UpgradeCheckCategory.DEPENDENCY, "T2", passed=False, blocking=False))
        self.engine.link_check("a1", "c1")
        self.engine.link_check("a1", "c2")
        issues = self.engine.get_blocking_issues("a1")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].check_id, "c1")

    def test_22_get_blocking_issues_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_blocking_issues("nonexistent")

    def test_23_compare_versions(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.create_assessment(UpgradeReadinessAssessment("a2", "c1", "1.0", "3.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=True))
        self.engine.add_check(UpgradeCheck("c2", UpgradeCheckCategory.DEPENDENCY, "T2", passed=False, effort_hours=5.0))
        self.engine.link_check("a1", "c1")
        self.engine.link_check("a2", "c2")
        comp = self.engine.compare_versions("a1", "a2")
        self.assertEqual(comp["version_a"], "2.0")
        self.assertEqual(comp["version_b"], "3.0")
        self.assertEqual(comp["score_diff"], -100.0)
        self.assertEqual(comp["effort_diff"], 5.0)

    def test_24_compare_versions_invalid(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        with self.assertRaises(ValueError):
            self.engine.compare_versions("a1", "nonexistent")

    def test_25_get_fleet_readiness(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.create_assessment(UpgradeReadinessAssessment("a2", "c2", "1.0", "2.0"))
        self.engine.create_assessment(UpgradeReadinessAssessment("a3", "c3", "1.0", "3.0"))
        
        self.engine.add_check(UpgradeCheck("c_ok", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=True))
        self.engine.add_check(UpgradeCheck("c_blk", UpgradeCheckCategory.COMPATIBILITY, "T2", passed=False, blocking=True))
        
        self.engine.link_check("a1", "c_ok")
        self.engine.link_check("a2", "c_blk")
        
        self.engine.evaluate_readiness("a1")
        self.engine.evaluate_readiness("a2")
        
        fleet = self.engine.get_fleet_readiness("2.0")
        self.assertEqual(fleet["total_assessments"], 2)
        self.assertEqual(fleet["ready"], 1)
        self.assertEqual(fleet["blocked"], 1)

    def test_26_get_fleet_readiness_empty(self):
        fleet = self.engine.get_fleet_readiness("2.0")
        self.assertEqual(fleet["total_assessments"], 0)

    def test_27_get_readiness_report(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.add_check(UpgradeCheck("c1", UpgradeCheckCategory.COMPATIBILITY, "T1", passed=True))
        self.engine.add_check(UpgradeCheck("c2", UpgradeCheckCategory.DEPENDENCY, "T2", passed=False, blocking=True, effort_hours=3.0))
        self.engine.link_check("a1", "c1")
        self.engine.link_check("a1", "c2")
        
        report = self.engine.get_readiness_report("a1")
        self.assertEqual(report["assessment_id"], "a1")
        self.assertEqual(report["blockers_count"], 1)
        self.assertIn("compatibility", report["category_breakdown"])
        self.assertEqual(report["category_breakdown"]["compatibility"]["passed"], 1)
        self.assertEqual(report["category_breakdown"]["dependency"]["effort"], 3.0)

    def test_28_get_readiness_report_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_readiness_report("nonexistent")

    def test_29_evaluate_no_checks(self):
        a = UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0")
        self.engine.create_assessment(a)
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.readiness, ReadinessLevel.NOT_READY)
        self.assertEqual(a.overall_score, 0.0)
        self.assertEqual(a.total_effort_hours, 0.0)

    def test_30_missing_check_in_engine(self):
        self.engine.create_assessment(UpgradeReadinessAssessment("a1", "c1", "1.0", "2.0"))
        self.engine.assessments["a1"].checks.append("missing_check")
        a = self.engine.evaluate_readiness("a1")
        self.assertEqual(a.overall_score, 0.0)

if __name__ == '__main__':
    unittest.main()
