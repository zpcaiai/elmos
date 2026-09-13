import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.types import (
    SecurityPolicy, SecurityScan, SecurityFinding, SecurityScanType, 
    FindingSeverity, FindingStatus
)
from elmos_mature_platform.dast_iast_security_engine import DastIastSecurityEngine

class TestDastIastSecurityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DastIastSecurityEngine()
        
    def _create_base_policy(self, pid="pol-1") -> SecurityPolicy:
        policy = SecurityPolicy(
            policy_id=pid,
            name="Base Security Policy",
            max_critical=0,
            max_high=2,
            sla_critical_hours=24,
            sla_high_hours=72,
            sla_medium_hours=168,
            block_on_critical=True,
            require_scan_types=[SecurityScanType.DAST.value]
        )
        self.engine.create_policy(policy)
        return policy
        
    def _create_base_scan(self, sid="scan-1", pid="pol-1", stype=SecurityScanType.DAST) -> SecurityScan:
        scan = SecurityScan(
            scan_id=sid,
            scan_type=stype,
            target="https://example.com",
            policy_id=pid
        )
        self.engine.start_scan(scan)
        return scan

    # 1
    def test_create_policy(self):
        policy = self._create_base_policy()
        self.assertIn(policy.policy_id, self.engine.policies)
        self.assertEqual(self.engine.policies[policy.policy_id].name, "Base Security Policy")
        
    # 2
    def test_start_scan_updates_time(self):
        scan = self._create_base_scan()
        self.assertTrue(scan.started_at)
        
    # 3
    def test_complete_scan_updates_time_and_duration(self):
        scan = self._create_base_scan()
        self.engine.complete_scan(scan.scan_id, 120.5)
        self.assertTrue(scan.completed_at)
        self.assertEqual(scan.duration_seconds, 120.5)

    # 4
    def test_complete_scan_counts_findings(self):
        scan = self._create_base_scan()
        f1 = SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.HIGH)
        f2 = SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.MEDIUM)
        self.engine.add_finding(f1)
        self.engine.add_finding(f2)
        
        self.engine.complete_scan(scan.scan_id, 30.0)
        self.assertEqual(scan.findings_count, 2)
        
    # 5
    def test_complete_scan_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_scan("missing", 10.0)

    # 6
    def test_add_finding_calculates_sla(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        now = datetime.utcnow()
        f1 = SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.CRITICAL, first_seen=now.isoformat())
        self.engine.add_finding(f1)
        
        expected_deadline = (now + timedelta(hours=24)).isoformat()
        self.assertEqual(self.engine.findings["f1"].sla_deadline, expected_deadline)
        
    # 7
    def test_add_finding_no_policy_no_sla(self):
        scan = SecurityScan(scan_id="scan-2", scan_type=SecurityScanType.IAST, target="app")
        self.engine.start_scan(scan)
        f1 = SecurityFinding(finding_id="f2", scan_id="scan-2", severity=FindingSeverity.CRITICAL)
        self.engine.add_finding(f1)
        self.assertEqual(self.engine.findings["f2"].sla_deadline, "")

    # 8
    def test_triage_finding_status_update(self):
        scan = self._create_base_scan()
        f1 = SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.LOW)
        self.engine.add_finding(f1)
        
        self.engine.triage_finding("f1", FindingStatus.ACCEPTED_RISK, "")
        self.assertEqual(self.engine.findings["f1"].status, FindingStatus.ACCEPTED_RISK)

    # 9
    def test_triage_finding_false_positive(self):
        scan = self._create_base_scan()
        f1 = SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.LOW)
        self.engine.add_finding(f1)
        
        self.engine.triage_finding("f1", FindingStatus.FALSE_POSITIVE, "Test FP")
        self.assertEqual(self.engine.findings["f1"].status, FindingStatus.FALSE_POSITIVE)
        self.assertEqual(self.engine.findings["f1"].false_positive_reason, "Test FP")

    # 10
    def test_triage_missing_finding(self):
        with self.assertRaises(ValueError):
            self.engine.triage_finding("missing", FindingStatus.NEW, "")

    # 11
    def test_evaluate_gate_pass(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        self.engine.complete_scan("scan-1", 10.0)
        
        # Policy max critical=0, max high=2
        f1 = SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.HIGH)
        f2 = SecurityFinding(finding_id="f2", scan_id="scan-1", severity=FindingSeverity.HIGH)
        self.engine.add_finding(f1)
        self.engine.add_finding(f2)
        
        result = self.engine.evaluate_gate("pol-1")
        self.assertTrue(result["pass"])
        self.assertEqual(result["critical_count"], 0)
        self.assertEqual(result["high_count"], 2)

    # 12
    def test_evaluate_gate_fail_critical(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        self.engine.complete_scan("scan-1", 10.0)
        
        f1 = SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.CRITICAL)
        self.engine.add_finding(f1)
        
        result = self.engine.evaluate_gate("pol-1")
        self.assertFalse(result["pass"])
        self.assertIn("Critical findings (1) exceed maximum allowed (0)", result["violations"])

    # 13
    def test_evaluate_gate_fail_high(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        self.engine.complete_scan("scan-1", 10.0)
        
        # Max high is 2, add 3
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.HIGH))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id="scan-1", severity=FindingSeverity.HIGH))
        self.engine.add_finding(SecurityFinding(finding_id="f3", scan_id="scan-1", severity=FindingSeverity.HIGH))
        
        result = self.engine.evaluate_gate("pol-1")
        self.assertFalse(result["pass"])
        self.assertIn("High findings (3) exceed maximum allowed (2)", result["violations"])

    # 14
    def test_evaluate_gate_ignores_remediated(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        self.engine.complete_scan("scan-1", 10.0)
        
        f1 = SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.CRITICAL, status=FindingStatus.REMEDIATED)
        self.engine.add_finding(f1)
        
        result = self.engine.evaluate_gate("pol-1")
        self.assertTrue(result["pass"])

    # 15
    def test_evaluate_gate_missing_required_scan(self):
        self._create_base_policy("pol-1") # Requires DAST
        # Run IAST scan instead
        self._create_base_scan("scan-1", "pol-1", stype=SecurityScanType.IAST)
        self.engine.complete_scan("scan-1", 10.0)
        
        result = self.engine.evaluate_gate("pol-1")
        self.assertFalse(result["pass"])
        self.assertIn("Required scan type 'dast' has not been completed", result["violations"])

    # 16
    def test_evaluate_gate_missing_policy(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_gate("missing")

    # 17
    def test_get_findings_all(self):
        scan = self._create_base_scan()
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.LOW))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.HIGH))
        
        findings = self.engine.get_findings()
        self.assertEqual(len(findings), 2)

    # 18
    def test_get_findings_filter_scan(self):
        scan1 = self._create_base_scan("scan-1")
        scan2 = self._create_base_scan("scan-2")
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id=scan1.scan_id, severity=FindingSeverity.LOW))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id=scan2.scan_id, severity=FindingSeverity.HIGH))
        
        findings = self.engine.get_findings(scan_id="scan-2")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_id, "f2")

    # 19
    def test_get_findings_filter_severity(self):
        scan = self._create_base_scan()
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.LOW))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.HIGH))
        
        findings = self.engine.get_findings(severity=FindingSeverity.HIGH)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_id, "f2")

    # 20
    def test_get_findings_filter_status(self):
        scan = self._create_base_scan()
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.LOW, status=FindingStatus.REMEDIATED))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.HIGH))
        
        findings = self.engine.get_findings(status=FindingStatus.REMEDIATED)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].finding_id, "f1")

    # 21
    def test_get_sla_violations(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        
        now = datetime.utcnow()
        past = now - timedelta(hours=48)
        
        # 24h SLA for critical, seen 48h ago -> violated
        f1 = SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.CRITICAL, first_seen=past.isoformat())
        self.engine.add_finding(f1)
        
        # 72h SLA for high, seen 48h ago -> not violated
        f2 = SecurityFinding(finding_id="f2", scan_id="scan-1", severity=FindingSeverity.HIGH, first_seen=past.isoformat())
        self.engine.add_finding(f2)
        
        violations = self.engine.get_sla_violations(now.isoformat())
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].finding_id, "f1")

    # 22
    def test_get_sla_violations_ignores_remediated(self):
        self._create_base_policy("pol-1")
        self._create_base_scan("scan-1", "pol-1")
        
        now = datetime.utcnow()
        past = now - timedelta(hours=48)
        
        # 24h SLA for critical, seen 48h ago -> normally violated, but remediated
        f1 = SecurityFinding(finding_id="f1", scan_id="scan-1", severity=FindingSeverity.CRITICAL, first_seen=past.isoformat(), status=FindingStatus.REMEDIATED)
        self.engine.add_finding(f1)
        
        violations = self.engine.get_sla_violations(now.isoformat())
        self.assertEqual(len(violations), 0)

    # 23
    def test_get_finding_trends(self):
        scan = self._create_base_scan()
        d1 = "2026-09-01T10:00:00Z"
        d2 = "2026-09-02T10:00:00Z"
        
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.LOW, first_seen=d1))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.LOW, first_seen=d1, last_seen=d2, status=FindingStatus.REMEDIATED))
        
        trends = self.engine.get_finding_trends()
        self.assertEqual(trends["dates"], ["2026-09-01", "2026-09-02"])
        self.assertEqual(trends["new"], [2, 0])
        self.assertEqual(trends["remediated"], [0, 1])

    # 24
    def test_get_scan_history(self):
        self._create_base_scan("scan-1")
        self._create_base_scan("scan-2", stype=SecurityScanType.IAST)
        
        history = self.engine.get_scan_history()
        self.assertEqual(len(history), 2)
        
        dast_history = self.engine.get_scan_history(scan_type=SecurityScanType.DAST)
        self.assertEqual(len(dast_history), 1)
        self.assertEqual(dast_history[0].scan_id, "scan-1")

    # 25
    def test_deduplicate_findings_same_cwe_location(self):
        scan = self._create_base_scan()
        f1 = SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, cwe_id="CWE-79", location="/src/app.py:10")
        f2 = SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, cwe_id="CWE-79", location="/src/app.py:10")
        self.engine.add_finding(f1)
        self.engine.add_finding(f2)
        
        merged = self.engine.deduplicate_findings()
        self.assertEqual(merged, 1)
        self.assertEqual(len(self.engine.findings), 1)

    # 26
    def test_deduplicate_findings_different_cwe(self):
        scan = self._create_base_scan()
        f1 = SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, cwe_id="CWE-79", location="/src/app.py:10")
        f2 = SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, cwe_id="CWE-89", location="/src/app.py:10")
        self.engine.add_finding(f1)
        self.engine.add_finding(f2)
        
        merged = self.engine.deduplicate_findings()
        self.assertEqual(merged, 0)
        self.assertEqual(len(self.engine.findings), 2)

    # 27
    def test_deduplicate_reopens_remediated(self):
        scan = self._create_base_scan()
        f1 = SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, cwe_id="CWE-79", location="/src/app.py:10", status=FindingStatus.REMEDIATED, first_seen="2026-09-01T10:00:00Z")
        f2 = SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, cwe_id="CWE-79", location="/src/app.py:10", status=FindingStatus.NEW, first_seen="2026-09-02T10:00:00Z")
        self.engine.add_finding(f1)
        self.engine.add_finding(f2)
        
        merged = self.engine.deduplicate_findings()
        self.assertEqual(merged, 1)
        
        # Primary is f1 because it was seen first
        remaining_f = self.engine.findings.get("f1")
        self.assertIsNotNone(remaining_f)
        self.assertEqual(remaining_f.status, FindingStatus.REOPENED)

    # 28
    def test_get_security_report(self):
        scan = self._create_base_scan()
        self.engine.add_finding(SecurityFinding(finding_id="f1", scan_id=scan.scan_id, severity=FindingSeverity.HIGH, status=FindingStatus.NEW))
        self.engine.add_finding(SecurityFinding(finding_id="f2", scan_id=scan.scan_id, severity=FindingSeverity.CRITICAL, status=FindingStatus.REMEDIATED))
        
        report = self.engine.get_security_report()
        self.assertEqual(report["total_findings"], 2)
        self.assertEqual(report["total_scans"], 1)
        self.assertEqual(report["findings_by_severity"][FindingSeverity.HIGH.value], 1)
        self.assertEqual(report["findings_by_severity"][FindingSeverity.CRITICAL.value], 1)
        self.assertEqual(report["findings_by_status"][FindingStatus.NEW.value], 1)
        self.assertEqual(report["findings_by_status"][FindingStatus.REMEDIATED.value], 1)
        self.assertEqual(report["scans_by_type"][SecurityScanType.DAST.value], 1)
        self.assertEqual(report["sla_compliance_rate"], 1.0) # No SLAs added since no policy applied properly or first_seen is None

if __name__ == '__main__':
    unittest.main()
