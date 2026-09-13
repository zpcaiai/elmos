import unittest
import datetime
from elmos_mature_platform.psirt_security_incident_engine import PsirtSecurityIncidentEngine
from elmos_mature_platform.types import SecurityVulnerability, PsirtSeverity, PsirtStatus, PsirtAdvisory

class TestPsirtSecurityIncidentComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = PsirtSecurityIncidentEngine()
        self.vuln = SecurityVulnerability(
            vuln_id="VULN-001",
            title="SQL Injection",
            description="SQL Injection in auth",
            severity=PsirtSeverity.HIGH,
            cve_id="CVE-2023-1234"
        )
        self.advisory = PsirtAdvisory(
            advisory_id="ADV-001",
            vuln_id="VULN-001",
            title="Security Advisory: SQL Injection",
            summary="Please update to latest version",
            affected_products=["Auth-Service"]
        )

    def test_report_vulnerability(self):
        v_id = self.engine.report_vulnerability(self.vuln)
        self.assertEqual(v_id, "VULN-001")
        self.assertEqual(self.engine.vulnerabilities["VULN-001"].status, PsirtStatus.REPORTED)
        self.assertIsNotNone(self.engine.vulnerabilities["VULN-001"].reported_at)

    def test_exploited_in_wild_forces_critical_on_report(self):
        vuln = SecurityVulnerability(
            vuln_id="VULN-002",
            title="0-day",
            description="Active exploitation",
            severity=PsirtSeverity.LOW,
            exploited_in_wild=True
        )
        self.engine.report_vulnerability(vuln)
        self.assertEqual(self.engine.vulnerabilities["VULN-002"].severity, PsirtSeverity.CRITICAL)

    def test_triage_vulnerability(self):
        self.engine.report_vulnerability(self.vuln)
        v = self.engine.triage("VULN-001", "sec_engineer", PsirtSeverity.MEDIUM)
        self.assertEqual(v.assignee, "sec_engineer")
        self.assertEqual(v.severity, PsirtSeverity.MEDIUM)
        self.assertEqual(v.status, PsirtStatus.TRIAGED)

    def test_triage_exploited_in_wild_forces_critical(self):
        self.vuln.exploited_in_wild = True
        self.engine.report_vulnerability(self.vuln)
        v = self.engine.triage("VULN-001", "sec_engineer", PsirtSeverity.LOW)
        self.assertEqual(v.severity, PsirtSeverity.CRITICAL)

    def test_triage_invalid_vuln_id(self):
        with self.assertRaises(ValueError):
            self.engine.triage("INVALID", "sec_engineer", PsirtSeverity.HIGH)

    def test_triage_invalid_status(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec_engineer", PsirtSeverity.HIGH)
        with self.assertRaises(ValueError):
            self.engine.triage("VULN-001", "sec_engineer", PsirtSeverity.HIGH)

    def test_start_investigation(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec_engineer", PsirtSeverity.HIGH)
        v = self.engine.start_investigation("VULN-001")
        self.assertEqual(v.status, PsirtStatus.INVESTIGATING)

    def test_start_investigation_invalid_status(self):
        self.engine.report_vulnerability(self.vuln)
        with self.assertRaises(ValueError):
            self.engine.start_investigation("VULN-001")

    def test_start_investigation_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.start_investigation("INVALID")

    def test_develop_fix(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec", PsirtSeverity.HIGH)
        self.engine.start_investigation("VULN-001")
        v = self.engine.develop_fix("VULN-001", "1.0.1", "https://patch")
        self.assertEqual(v.status, PsirtStatus.FIX_DEVELOPING)
        self.assertEqual(v.fixed_version, "1.0.1")

    def test_develop_fix_invalid_status(self):
        self.engine.report_vulnerability(self.vuln)
        with self.assertRaises(ValueError):
            self.engine.develop_fix("VULN-001", "1.0.1", "url")

    def test_develop_fix_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.develop_fix("INVALID", "1.0.1", "url")

    def test_release_fix(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec", PsirtSeverity.HIGH)
        self.engine.start_investigation("VULN-001")
        self.engine.develop_fix("VULN-001", "1.0.1", "https://patch")
        v = self.engine.release_fix("VULN-001")
        self.assertEqual(v.status, PsirtStatus.FIX_AVAILABLE)

    def test_release_fix_without_fixed_version(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec", PsirtSeverity.HIGH)
        self.engine.start_investigation("VULN-001")
        self.engine.vulnerabilities["VULN-001"].status = PsirtStatus.FIX_DEVELOPING
        with self.assertRaises(ValueError):
            self.engine.release_fix("VULN-001")

    def test_release_fix_invalid_status(self):
        self.engine.report_vulnerability(self.vuln)
        with self.assertRaises(ValueError):
            self.engine.release_fix("VULN-001")

    def test_release_fix_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.release_fix("INVALID")

    def test_disclose(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec", PsirtSeverity.HIGH)
        self.engine.start_investigation("VULN-001")
        self.engine.develop_fix("VULN-001", "1.0.1", "https://patch")
        self.engine.release_fix("VULN-001")
        v = self.engine.disclose("VULN-001")
        self.assertEqual(v.status, PsirtStatus.DISCLOSED)
        self.assertIsNotNone(v.disclosed_at)

    def test_disclose_without_fix(self):
        self.engine.report_vulnerability(self.vuln)
        with self.assertRaises(ValueError):
            self.engine.disclose("VULN-001")

    def test_disclose_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.disclose("INVALID")

    def test_close(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.triage("VULN-001", "sec", PsirtSeverity.HIGH)
        self.engine.start_investigation("VULN-001")
        self.engine.develop_fix("VULN-001", "1.0.1", "https://patch")
        self.engine.release_fix("VULN-001")
        self.engine.disclose("VULN-001")
        v = self.engine.close("VULN-001")
        self.assertEqual(v.status, PsirtStatus.CLOSED)

    def test_close_before_disclose(self):
        self.engine.report_vulnerability(self.vuln)
        with self.assertRaises(ValueError):
            self.engine.close("VULN-001")

    def test_close_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.close("INVALID")

    def test_create_advisory(self):
        self.engine.report_vulnerability(self.vuln)
        a_id = self.engine.create_advisory(self.advisory)
        self.assertEqual(a_id, "ADV-001")
        self.assertIn("ADV-001", self.engine.advisories)

    def test_create_advisory_invalid_vuln(self):
        with self.assertRaises(ValueError):
            self.engine.create_advisory(self.advisory)

    def test_publish_advisory(self):
        self.engine.report_vulnerability(self.vuln)
        self.engine.create_advisory(self.advisory)
        a = self.engine.publish_advisory("ADV-001")
        self.assertTrue(a.published)
        self.assertIsNotNone(a.published_at)

    def test_publish_advisory_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.publish_advisory("INVALID")

    def test_check_sla_violations(self):
        self.vuln.reported_at = (datetime.datetime.utcnow() - datetime.timedelta(hours=100)).isoformat()
        self.engine.report_vulnerability(self.vuln)
        violations = self.engine.check_sla_violations()
        self.assertEqual(len(violations), 1)

    def test_check_sla_violations_none(self):
        self.vuln.reported_at = datetime.datetime.utcnow().isoformat()
        self.engine.report_vulnerability(self.vuln)
        violations = self.engine.check_sla_violations()
        self.assertEqual(len(violations), 0)

    def test_get_active_vulnerabilities(self):
        self.engine.report_vulnerability(self.vuln)
        vuln2 = SecurityVulnerability(
            vuln_id="VULN-002",
            title="Second",
            description="desc",
            severity=PsirtSeverity.LOW
        )
        self.engine.report_vulnerability(vuln2)
        
        # Close one
        self.engine.triage("VULN-001", "sec", PsirtSeverity.HIGH)
        self.engine.start_investigation("VULN-001")
        self.engine.develop_fix("VULN-001", "1.0.1", "https://patch")
        self.engine.release_fix("VULN-001")
        self.engine.disclose("VULN-001")
        self.engine.close("VULN-001")
        
        active = self.engine.get_active_vulnerabilities()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].vuln_id, "VULN-002")

    def test_get_psirt_report(self):
        self.engine.report_vulnerability(self.vuln)
        report = self.engine.get_psirt_report()
        self.assertEqual(report["total_vulnerabilities"], 1)
        self.assertEqual(report["by_severity"][PsirtSeverity.HIGH.value], 1)
        self.assertEqual(report["by_status"][PsirtStatus.REPORTED.value], 1)

    def test_get_psirt_report_multiple(self):
        self.engine.report_vulnerability(self.vuln)
        vuln2 = SecurityVulnerability(
            vuln_id="VULN-002",
            title="Second",
            description="desc",
            severity=PsirtSeverity.CRITICAL
        )
        self.engine.report_vulnerability(vuln2)
        self.engine.triage("VULN-002", "sec", PsirtSeverity.CRITICAL)
        
        report = self.engine.get_psirt_report()
        self.assertEqual(report["total_vulnerabilities"], 2)
        self.assertEqual(report["by_severity"][PsirtSeverity.HIGH.value], 1)
        self.assertEqual(report["by_severity"][PsirtSeverity.CRITICAL.value], 1)
        self.assertEqual(report["by_status"][PsirtStatus.REPORTED.value], 1)
        self.assertEqual(report["by_status"][PsirtStatus.TRIAGED.value], 1)

if __name__ == "__main__":
    unittest.main()
