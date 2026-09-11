"""Comprehensive test suite for IndependentSecurityAssessmentEngine (B40 - Skill 1391)."""

import unittest

from elmos_mature_platform.independent_security_assessment_engine import (
    IndependentSecurityAssessmentEngine,
)
from elmos_mature_platform.types import (
    AssessmentStatus,
    AssessmentType,
    AssessorType,
    IndependentAssessmentRecord,
    IndependentAuditFinding,
)


class TestIndependentSecurityAssessmentComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = IndependentSecurityAssessmentEngine()

    def test_initiate_assessment(self):
        record = IndependentAssessmentRecord(
            assessment_id="sec-pen-2026",
            target_release="v4.5.0",
            assessment_type=AssessmentType.PENETRATION_TEST,
            assessor_firm="NCC Group",
            assessor_type=AssessorType.EXTERNAL_ACCREDITED,
        )
        aid = self.engine.initiate_assessment(record)
        self.assertEqual(aid, "sec-pen-2026")
        self.assertEqual(record.status, AssessmentStatus.SCOPING)
        self.assertEqual(record.total_findings, 0)
        self.assertFalse(record.passed_gate)

    def test_record_findings_increments_blockers(self):
        record = IndependentAssessmentRecord(
            assessment_id="sec-audit-1",
            target_release="v4.5.0",
            assessment_type=AssessmentType.THIRD_PARTY_CODE_AUDIT,
            assessor_firm="Trail of Bits",
        )
        self.engine.initiate_assessment(record)

        # Record High severity finding
        f1 = IndependentAuditFinding(
            finding_id="fnd-1",
            assessment_id="sec-audit-1",
            title="Insecure deserialization in queue listener",
            severity="high",
            cwe_id="CWE-502",
        )
        self.engine.record_finding(f1)
        self.assertEqual(record.open_blockers, 1)

        # Record Low severity finding (should not increment blockers)
        f2 = IndependentAuditFinding(
            finding_id="fnd-2",
            assessment_id="sec-audit-1",
            title="Verbose server header in error response",
            severity="low",
            cwe_id="CWE-200",
        )
        self.engine.record_finding(f2)
        self.assertEqual(record.open_blockers, 1)
        self.assertEqual(record.total_findings, 2)

    def test_remediate_and_verify_finding_closure(self):
        record = IndependentAssessmentRecord(
            assessment_id="sec-audit-2",
            target_release="v4.5.0",
            assessment_type=AssessmentType.PENETRATION_TEST,
            assessor_firm="Bishop Fox",
        )
        self.engine.initiate_assessment(record)

        f = IndependentAuditFinding(
            finding_id="fnd-crit",
            assessment_id="sec-audit-2",
            title="SSRF in webhook dispatcher",
            severity="critical",
            cwe_id="CWE-918",
        )
        self.engine.record_finding(f)
        self.assertEqual(record.open_blockers, 1)

        # Engineering remediates
        self.engine.remediate_finding("fnd-crit", "Implemented strict egress IP filtering and DNS pinning")
        self.assertFalse(f.verified_closed)

        # External assessor re-tests and closes
        self.engine.verify_finding_closure("fnd-crit", "lead-pen-tester@bishopfox.com")
        self.assertTrue(f.verified_closed)
        self.assertEqual(record.open_blockers, 0)

    def test_conclude_assessment_fails_when_open_blockers_exist(self):
        record = IndependentAssessmentRecord(
            assessment_id="sec-audit-fail",
            target_release="v4.5.0",
            assessment_type=AssessmentType.THIRD_PARTY_CODE_AUDIT,
            assessor_firm="Cure53",
        )
        self.engine.initiate_assessment(record)
        f = IndependentAuditFinding(
            finding_id="fnd-unresolved",
            assessment_id="sec-audit-fail",
            title="SQL injection risk in legacy adapter",
            severity="critical",
        )
        self.engine.record_finding(f)

        concluded = self.engine.conclude_assessment(
            assessment_id="sec-audit-fail",
            sign_off_attestation="Findings remaining",
            lead_assessor="auditor@cure53.de",
        )
        self.assertFalse(concluded.passed_gate)
        self.assertEqual(concluded.status, AssessmentStatus.REMEDIATION)
        self.assertEqual(concluded.open_blockers, 1)

    def test_conclude_assessment_passes_gate_when_clean(self):
        record = IndependentAssessmentRecord(
            assessment_id="sec-audit-clean",
            target_release="v4.5.0",
            assessment_type=AssessmentType.CRYPTO_REVIEW,
            assessor_firm="Kudelski Security",
        )
        self.engine.initiate_assessment(record)
        # Low finding only
        f = IndependentAuditFinding(
            finding_id="fnd-info",
            assessment_id="sec-audit-clean",
            title="Cipher suite ordering recommendation",
            severity="low",
        )
        self.engine.record_finding(f)

        concluded = self.engine.conclude_assessment(
            assessment_id="sec-audit-clean",
            sign_off_attestation="Platform cryptographic layer verified safe and compliant with FIPS 140-3",
            lead_assessor="crypto-auditor@kudelski.com",
        )
        self.assertTrue(concluded.passed_gate)
        self.assertEqual(concluded.status, AssessmentStatus.CERTIFIED_CLOSED)

    def test_get_assessment_report(self):
        record = IndependentAssessmentRecord(
            assessment_id="sec-rep",
            target_release="v4.5.0",
            assessment_type=AssessmentType.RED_TEAM_ENGAGEMENT,
            assessor_firm="Mandiant",
        )
        self.engine.initiate_assessment(record)
        self.engine.record_finding(IndependentAuditFinding("f1", "sec-rep", "T1", "critical"))
        self.engine.record_finding(IndependentAuditFinding("f2", "sec-rep", "T2", "medium"))
        self.engine.verify_finding_closure("f1", "mandiant-lead")

        report = self.engine.get_assessment_report("sec-rep")
        self.assertEqual(report["total_findings"], 2)
        self.assertEqual(report["closed_findings"], 1)
        self.assertEqual(report["severity_breakdown"]["critical"], 1)
        self.assertEqual(report["severity_breakdown"]["medium"], 1)


if __name__ == "__main__":
    unittest.main()
