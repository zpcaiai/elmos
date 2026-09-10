import unittest
from elmos_mature_platform.sast_integration_engine import SastIntegrationEngine
from elmos_mature_platform.types import (
    SastSeverity,
    SastCategory,
    SastFindingState,
    SastFinding,
    SastScanRun,
    SastPolicy
)

class TestSastIntegrationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SastIntegrationEngine()

    def test_create_policy(self):
        policy = SastPolicy(policy_id="pol-1", max_critical=0)
        self.engine.create_policy(policy)
        self.assertIn("pol-1", self.engine._policies)

    def test_start_scan(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        res = self.engine.start_scan(scan)
        self.assertEqual(res, "scan-1")

    def test_add_finding(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.CRITICAL, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        self.assertIn("f-1", self.engine._findings_global)

    def test_add_finding_invalid_scan(self):
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.CRITICAL, file_path="app.py", line_number=10)
        with self.assertRaises(ValueError):
            self.engine.add_finding(finding, "inv-scan")

    def test_complete_scan(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.CRITICAL, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        res = self.engine.complete_scan("scan-1")
        self.assertEqual(res.total_findings, 1)
        self.assertEqual(res.critical_count, 1)

    def test_complete_scan_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.complete_scan("inv")

    def test_evaluate_policy_pass(self):
        policy = SastPolicy(policy_id="pol-1", max_critical=1, require_cwe_mapping=False)
        self.engine.create_policy(policy)
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        self.engine.complete_scan("scan-1")
        res = self.engine.evaluate_policy("scan-1", "pol-1")
        self.assertTrue(res["passed"])

    def test_evaluate_policy_fail_critical(self):
        policy = SastPolicy(policy_id="pol-1", max_critical=0)
        self.engine.create_policy(policy)
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.CRITICAL, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        self.engine.complete_scan("scan-1")
        res = self.engine.evaluate_policy("scan-1", "pol-1")
        self.assertFalse(res["passed"])

    def test_evaluate_policy_fail_high(self):
        policy = SastPolicy(policy_id="pol-1", max_high=0)
        self.engine.create_policy(policy)
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.HIGH, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        self.engine.complete_scan("scan-1")
        res = self.engine.evaluate_policy("scan-1", "pol-1")
        self.assertFalse(res["passed"])

    def test_evaluate_policy_fail_cwe(self):
        policy = SastPolicy(policy_id="pol-1", require_cwe_mapping=True)
        self.engine.create_policy(policy)
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10, cwe_id="")
        self.engine.add_finding(finding, "scan-1")
        self.engine.complete_scan("scan-1")
        res = self.engine.evaluate_policy("scan-1", "pol-1")
        self.assertFalse(res["passed"])
        
    def test_evaluate_policy_invalid_scan(self):
        policy = SastPolicy(policy_id="pol-1")
        self.engine.create_policy(policy)
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy("scan-1", "pol-1")

    def test_evaluate_policy_invalid_policy(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        with self.assertRaises(ValueError):
            self.engine.evaluate_policy("scan-1", "pol-1")

    def test_triage_finding(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        res = self.engine.triage_finding("f-1", SastFindingState.FALSE_POSITIVE, "FP")
        self.assertEqual(res.state, SastFindingState.FALSE_POSITIVE)

    def test_triage_finding_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.triage_finding("inv", SastFindingState.FIXED, "")

    def test_get_findings_all(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        res = self.engine.get_findings("scan-1")
        self.assertEqual(len(res), 1)

    def test_get_findings_filter_severity(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        self.engine.add_finding(SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10), "scan-1")
        self.engine.add_finding(SastFinding(finding_id="f-2", category=SastCategory.INJECTION, severity=SastSeverity.HIGH, file_path="app.py", line_number=10), "scan-1")
        res = self.engine.get_findings("scan-1", severity=SastSeverity.HIGH)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].finding_id, "f-2")

    def test_get_findings_filter_category(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        self.engine.add_finding(SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10), "scan-1")
        self.engine.add_finding(SastFinding(finding_id="f-2", category=SastCategory.XSS, severity=SastSeverity.HIGH, file_path="app.py", line_number=10), "scan-1")
        res = self.engine.get_findings("scan-1", category=SastCategory.XSS)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].finding_id, "f-2")
        
    def test_get_findings_invalid_scan(self):
        with self.assertRaises(ValueError):
            self.engine.get_findings("inv")

    def test_get_trend(self):
        self.engine.start_scan(SastScanRun(scan_id="s1", project_name="p1", started_at="1"))
        self.engine.add_finding(SastFinding("f1", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.complete_scan("s1")
        
        self.engine.start_scan(SastScanRun(scan_id="s2", project_name="p1", started_at="2"))
        self.engine.complete_scan("s2")
        
        res = self.engine.get_trend("p1")
        self.assertEqual(len(res["trend"]), 2)
        self.assertEqual(res["trend"][0]["high"], 1)
        self.assertEqual(res["trend"][1]["high"], 0)

    def test_get_top_categories(self):
        self.engine.start_scan(SastScanRun(scan_id="s1", project_name="p1"))
        self.engine.add_finding(SastFinding("f1", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f2", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f3", SastCategory.XSS, SastSeverity.HIGH, "a", 1), "s1")
        res = self.engine.get_top_categories()
        self.assertEqual(res[SastCategory.INJECTION.value], 2)
        self.assertEqual(res[SastCategory.XSS.value], 1)
        
    def test_get_fix_rate_zero(self):
        res = self.engine.get_fix_rate()
        self.assertEqual(res["total"], 0)
        self.assertEqual(res["rate"], 0.0)

    def test_get_fix_rate(self):
        self.engine.start_scan(SastScanRun(scan_id="s1", project_name="p1"))
        self.engine.add_finding(SastFinding("f1", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f2", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.triage_finding("f1", SastFindingState.FIXED, "done")
        res = self.engine.get_fix_rate()
        self.assertEqual(res["total"], 2)
        self.assertEqual(res["fixed"], 1)
        self.assertEqual(res["rate"], 0.5)

    def test_get_scanning_report(self):
        self.engine.start_scan(SastScanRun(scan_id="s1", project_name="p1"))
        self.engine.add_finding(SastFinding("f1", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f2", SastCategory.XSS, SastSeverity.CRITICAL, "a", 1), "s1")
        self.engine.complete_scan("s1")
        res = self.engine.get_scanning_report("s1")
        self.assertEqual(res["total_findings"], 2)
        self.assertEqual(res["severities"]["high"], 1)
        self.assertEqual(res["severities"]["critical"], 1)
        self.assertEqual(res["categories"]["injection"], 1)

    def test_get_scanning_report_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_scanning_report("inv")

    def test_complete_scan_counts_correctly(self):
        scan = SastScanRun(scan_id="s1", project_name="p1")
        self.engine.start_scan(scan)
        self.engine.add_finding(SastFinding("f1", SastCategory.INJECTION, SastSeverity.CRITICAL, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f2", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f3", SastCategory.INJECTION, SastSeverity.MEDIUM, "a", 1), "s1")
        res = self.engine.complete_scan("s1")
        self.assertEqual(res.critical_count, 1)
        self.assertEqual(res.high_count, 1)
        self.assertEqual(res.total_findings, 3)
        
    def test_evaluate_policy_multiple_violations(self):
        policy = SastPolicy(policy_id="pol-1", max_critical=0, max_high=0, require_cwe_mapping=True)
        self.engine.create_policy(policy)
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding1 = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.CRITICAL, file_path="app.py", line_number=10, cwe_id="")
        finding2 = SastFinding(finding_id="f-2", category=SastCategory.INJECTION, severity=SastSeverity.HIGH, file_path="app.py", line_number=10, cwe_id="")
        self.engine.add_finding(finding1, "scan-1")
        self.engine.add_finding(finding2, "scan-1")
        self.engine.complete_scan("scan-1")
        res = self.engine.evaluate_policy("scan-1", "pol-1")
        self.assertFalse(res["passed"])
        self.assertEqual(len(res["violations"]), 3)

    def test_triage_finding_sets_resolved_at(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        finding = SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10)
        self.engine.add_finding(finding, "scan-1")
        res = self.engine.triage_finding("f-1", SastFindingState.FIXED, "done")
        self.assertNotEqual(res.resolved_at, "")

    def test_top_categories_ordering(self):
        self.engine.start_scan(SastScanRun(scan_id="s1", project_name="p1"))
        self.engine.add_finding(SastFinding("f1", SastCategory.INJECTION, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f2", SastCategory.XSS, SastSeverity.HIGH, "a", 1), "s1")
        self.engine.add_finding(SastFinding("f3", SastCategory.XSS, SastSeverity.HIGH, "a", 1), "s1")
        res = self.engine.get_top_categories()
        keys = list(res.keys())
        self.assertEqual(keys[0], SastCategory.XSS.value)
        self.assertEqual(keys[1], SastCategory.INJECTION.value)

    def test_get_findings_filter_both(self):
        scan = SastScanRun(scan_id="scan-1", project_name="proj-1")
        self.engine.start_scan(scan)
        self.engine.add_finding(SastFinding(finding_id="f-1", category=SastCategory.INJECTION, severity=SastSeverity.LOW, file_path="app.py", line_number=10), "scan-1")
        self.engine.add_finding(SastFinding(finding_id="f-2", category=SastCategory.XSS, severity=SastSeverity.HIGH, file_path="app.py", line_number=10), "scan-1")
        self.engine.add_finding(SastFinding(finding_id="f-3", category=SastCategory.XSS, severity=SastSeverity.LOW, file_path="app.py", line_number=10), "scan-1")
        res = self.engine.get_findings("scan-1", severity=SastSeverity.LOW, category=SastCategory.XSS)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].finding_id, "f-3")

if __name__ == '__main__':
    unittest.main()
