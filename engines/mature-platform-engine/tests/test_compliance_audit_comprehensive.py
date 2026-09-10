import unittest
import datetime
import hashlib
from typing import Dict

from elmos_mature_platform.types import (
    ComplianceFramework,
    ControlStatus,
    ComplianceControl,
    AuditEvidence,
    AuditFinding,
    ComplianceReport
)
from elmos_mature_platform.compliance_audit_engine import ComplianceAuditEngine

class TestComplianceAuditEngineComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = ComplianceAuditEngine()
        
    def _create_control(self, cid, fw=ComplianceFramework.SOC2_TYPE2, status=ControlStatus.IMPLEMENTED):
        return ComplianceControl(
            control_id=cid,
            framework=fw,
            title=f"Test {cid}",
            description=f"Desc {cid}",
            status=status,
            owner="admin"
        )
        
    def _create_evidence(self, eid, cid, content=b"data"):
        content_hash = hashlib.sha256(content).hexdigest()
        return AuditEvidence(
            evidence_id=eid,
            control_id=cid,
            evidence_type="document",
            description="test doc",
            content_hash=content_hash,
            collected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            collector="automated"
        )
        
    def _create_finding(self, fid, cid, severity="high", status="open", due_date=""):
        return AuditFinding(
            finding_id=fid,
            control_id=cid,
            severity=severity,
            description="issue",
            due_date=due_date,
            status=status
        )

    # 1. Test register_control basic
    def test_register_control(self):
        c = self._create_control("C1")
        self.engine.register_control(c)
        self.assertIn("C1", self.engine._controls)
        
    # 2. Test attach_evidence basic
    def test_attach_evidence(self):
        c = self._create_control("C1")
        self.engine.register_control(c)
        e = self._create_evidence("E1", "C1")
        self.engine.attach_evidence(e)
        self.assertIn("E1", c.evidence_ids)
        self.assertIn("E1", self.engine._evidence)
        
    # 3. Test attach_evidence missing control
    def test_attach_evidence_missing_control(self):
        e = self._create_evidence("E1", "C_NONEXIST")
        with self.assertRaises(ValueError):
            self.engine.attach_evidence(e)
            
    # 4. Test record_finding basic
    def test_record_finding(self):
        c = self._create_control("C1")
        self.engine.register_control(c)
        f = self._create_finding("F1", "C1")
        self.engine.record_finding(f)
        self.assertIn("F1", self.engine._findings)
        
    # 5. Test record_finding missing control
    def test_record_finding_missing_control(self):
        f = self._create_finding("F1", "C_NONEXIST")
        with self.assertRaises(ValueError):
            self.engine.record_finding(f)
            
    # 6. Test update_finding_status
    def test_update_finding_status(self):
        c = self._create_control("C1")
        self.engine.register_control(c)
        f = self._create_finding("F1", "C1")
        self.engine.record_finding(f)
        self.engine.update_finding_status("F1", "remediated")
        self.assertEqual(self.engine._findings["F1"].status, "remediated")
        
    # 7. Test update_finding_status missing
    def test_update_finding_status_missing(self):
        with self.assertRaises(ValueError):
            self.engine.update_finding_status("F_NONEXIST", "remediated")
            
    # 8. Test assess_control missing
    def test_assess_control_missing(self):
        with self.assertRaises(ValueError):
            self.engine.assess_control("C_NONEXIST")
            
    # 9. Test assess_control with high finding -> failed
    def test_assess_control_fails_on_finding(self):
        c = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        self.engine.register_control(c)
        self.engine.record_finding(self._create_finding("F1", "C1", severity="high"))
        self.engine.assess_control("C1")
        self.assertEqual(c.status, ControlStatus.FAILED)
        
    # 10. Test assess_control without evidence -> partially implemented
    def test_assess_control_partially_implemented_no_evidence(self):
        c = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        self.engine.register_control(c)
        self.engine.assess_control("C1")
        self.assertEqual(c.status, ControlStatus.PARTIALLY_IMPLEMENTED)
        
    # 11. Test assess_control stays implemented with evidence
    def test_assess_control_stays_implemented_with_evidence(self):
        c = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        self.engine.register_control(c)
        self.engine.attach_evidence(self._create_evidence("E1", "C1"))
        self.engine.assess_control("C1")
        self.assertEqual(c.status, ControlStatus.IMPLEMENTED)
        
    # 12. Test assess_control ignore remediated finding
    def test_assess_control_ignore_remediated_finding(self):
        c = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        self.engine.register_control(c)
        self.engine.attach_evidence(self._create_evidence("E1", "C1"))
        f = self._create_finding("F1", "C1", severity="critical", status="remediated")
        self.engine.record_finding(f)
        self.engine.assess_control("C1")
        self.assertEqual(c.status, ControlStatus.IMPLEMENTED)
        
    # 13. Test assess_control sets last_assessed
    def test_assess_control_sets_last_assessed(self):
        c = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        self.engine.register_control(c)
        self.engine.assess_control("C1")
        self.assertTrue(bool(c.last_assessed))
        
    # 14. Test generate_compliance_report empty
    def test_generate_compliance_report_empty(self):
        rep = self.engine.generate_compliance_report(ComplianceFramework.SOC2_TYPE2)
        self.assertEqual(rep.total_controls, 0)
        self.assertEqual(rep.coverage_pct, 0.0)
        
    # 15. Test generate_compliance_report with mixed controls
    def test_generate_compliance_report_mixed(self):
        c1 = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        c2 = self._create_control("C2", status=ControlStatus.NOT_APPLICABLE)
        self.engine.register_control(c1)
        self.engine.register_control(c2)
        self.engine.attach_evidence(self._create_evidence("E1", "C1"))
        
        rep = self.engine.generate_compliance_report(ComplianceFramework.SOC2_TYPE2)
        self.assertEqual(rep.total_controls, 2)
        self.assertEqual(rep.implemented, 1)
        self.assertEqual(rep.not_applicable, 1)
        self.assertEqual(rep.coverage_pct, 100.0) # 1 / 1
        
    # 16. Test get_control_gaps
    def test_get_control_gaps(self):
        c1 = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        c2 = self._create_control("C2", status=ControlStatus.PLANNED)
        c3 = self._create_control("C3", status=ControlStatus.NOT_APPLICABLE)
        self.engine.register_control(c1)
        self.engine.register_control(c2)
        self.engine.register_control(c3)
        self.engine.attach_evidence(self._create_evidence("E1", "C1"))
        
        gaps = self.engine.get_control_gaps(ComplianceFramework.SOC2_TYPE2)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].control_id, "C2")
        
    # 17. Test crosswalk_frameworks
    def test_crosswalk_frameworks(self):
        c1 = self._create_control("C1", fw=ComplianceFramework.SOC2_TYPE2)
        self.engine.register_control(c1)
        res = self.engine.crosswalk_frameworks(
            ComplianceFramework.SOC2_TYPE2,
            ComplianceFramework.ISO27001,
            {"C1": "ISO-1"}
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["target_control_id"], "ISO-1")
        
    # 18. Test crosswalk_frameworks missing control
    def test_crosswalk_frameworks_missing(self):
        res = self.engine.crosswalk_frameworks(
            ComplianceFramework.SOC2_TYPE2,
            ComplianceFramework.ISO27001,
            {"NONEXIST": "ISO-1"}
        )
        self.assertEqual(len(res), 0)
        
    # 19. Test export_audit_package
    def test_export_audit_package(self):
        c1 = self._create_control("C1", fw=ComplianceFramework.SOC2_TYPE2)
        self.engine.register_control(c1)
        self.engine.attach_evidence(self._create_evidence("E1", "C1"))
        self.engine.record_finding(self._create_finding("F1", "C1"))
        
        pkg = self.engine.export_audit_package(ComplianceFramework.SOC2_TYPE2)
        self.assertEqual(len(pkg["controls"]), 1)
        self.assertEqual(len(pkg["evidence"]), 1)
        self.assertEqual(len(pkg["findings"]), 1)
        
    # 20. Test get_overdue_findings none
    def test_get_overdue_findings_none(self):
        c1 = self._create_control("C1")
        self.engine.register_control(c1)
        future_date = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)).isoformat()
        self.engine.record_finding(self._create_finding("F1", "C1", due_date=future_date))
        self.assertEqual(len(self.engine.get_overdue_findings()), 0)
        
    # 21. Test get_overdue_findings some
    def test_get_overdue_findings_some(self):
        c1 = self._create_control("C1")
        self.engine.register_control(c1)
        past_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        self.engine.record_finding(self._create_finding("F1", "C1", due_date=past_date))
        self.assertEqual(len(self.engine.get_overdue_findings()), 1)
        
    # 22. Test get_overdue_findings resolved
    def test_get_overdue_findings_resolved(self):
        c1 = self._create_control("C1")
        self.engine.register_control(c1)
        past_date = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()
        f = self._create_finding("F1", "C1", due_date=past_date, status="remediated")
        self.engine.record_finding(f)
        self.assertEqual(len(self.engine.get_overdue_findings()), 0)
        
    # 23. Test compute_compliance_score basic
    def test_compute_compliance_score(self):
        c1 = self._create_control("C1", status=ControlStatus.IMPLEMENTED)
        c2 = self._create_control("C2", status=ControlStatus.PARTIALLY_IMPLEMENTED)
        self.engine.register_control(c1)
        self.engine.register_control(c2)
        self.assertEqual(self.engine.compute_compliance_score(ComplianceFramework.SOC2_TYPE2), 50.0)
        
    # 24. Test compute_compliance_score no controls
    def test_compute_compliance_score_no_controls(self):
        self.assertEqual(self.engine.compute_compliance_score(ComplianceFramework.SOC2_TYPE2), 0.0)
        
    # 25. Test validate_evidence_integrity pass
    def test_validate_evidence_integrity_pass(self):
        c = self._create_control("C1")
        self.engine.register_control(c)
        e = self._create_evidence("E1", "C1", content=b"test data")
        self.engine.attach_evidence(e)
        self.assertTrue(self.engine.validate_evidence_integrity("E1", b"test data"))
        
    # 26. Test validate_evidence_integrity fail
    def test_validate_evidence_integrity_fail(self):
        c = self._create_control("C1")
        self.engine.register_control(c)
        e = self._create_evidence("E1", "C1", content=b"test data")
        self.engine.attach_evidence(e)
        self.assertFalse(self.engine.validate_evidence_integrity("E1", b"wrong data"))
        
    # 27. Test validate_evidence_integrity missing
    def test_validate_evidence_integrity_missing(self):
        with self.assertRaises(ValueError):
            self.engine.validate_evidence_integrity("E_NONEXIST", b"")

if __name__ == '__main__':
    unittest.main()
