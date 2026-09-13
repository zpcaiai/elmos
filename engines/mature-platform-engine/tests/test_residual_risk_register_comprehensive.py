import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.residual_risk_register_engine import ResidualRiskRegisterEngine
from elmos_mature_platform.types import (
    RiskSeverity, RiskTreatment, RiskStatus, ResidualRiskEntry, RiskAssessment, RiskWaiver
)

class TestResidualRiskRegisterComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = ResidualRiskRegisterEngine()

    def test_register_risk_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-001", title="DB Risk", description="Unencrypted DB",
            category="security", severity=RiskSeverity.HIGH, likelihood=0.8, impact_score=8.0
        )
        self.engine.register_risk(risk)
        self.assertEqual(risk.risk_score, 6.4)
        
    def test_register_duplicate_risk_fails(self):
        risk = ResidualRiskEntry(
            risk_id="R-001", title="DB Risk", description="Unencrypted DB",
            category="security", severity=RiskSeverity.HIGH, likelihood=0.8, impact_score=8.0
        )
        self.engine.register_risk(risk)
        with self.assertRaises(ValueError):
            self.engine.register_risk(risk)
            
    def test_update_risk_fields(self):
        risk = ResidualRiskEntry(
            risk_id="R-001", title="DB Risk", description="Unencrypted DB",
            category="security", severity=RiskSeverity.HIGH, likelihood=0.8, impact_score=8.0
        )
        self.engine.register_risk(risk)
        self.engine.update_risk("R-001", title="DB Risk Updated", likelihood=0.5)
        updated = self.engine.get_risks_by_severity(RiskSeverity.HIGH)[0]
        self.assertEqual(updated.title, "DB Risk Updated")
        self.assertEqual(updated.likelihood, 0.5)
        self.assertEqual(updated.risk_score, 4.0)

    def test_update_nonexistent_risk_fails(self):
        with self.assertRaises(ValueError):
            self.engine.update_risk("R-999", title="Fake")
            
    def test_accept_risk_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-002", title="Minor Risk", description="Minor issue",
            category="reliability", severity=RiskSeverity.LOW, likelihood=0.1, impact_score=2.0
        )
        self.engine.register_risk(risk)
        accepted = self.engine.accept_risk("R-002", accepted_by="Alice", justification="Low priority")
        self.assertEqual(accepted.status, RiskStatus.ACCEPTED)
        self.assertEqual(accepted.treatment, RiskTreatment.ACCEPT)
        
    def test_accept_risk_no_justification_fails(self):
        risk = ResidualRiskEntry(
            risk_id="R-002", title="Minor Risk", description="Minor issue",
            category="reliability", severity=RiskSeverity.LOW, likelihood=0.1, impact_score=2.0
        )
        self.engine.register_risk(risk)
        with self.assertRaises(ValueError):
            self.engine.accept_risk("R-002", accepted_by="Alice", justification="")
            
    def test_accept_critical_risk_without_waiver_fails(self):
        risk = ResidualRiskEntry(
            risk_id="R-003", title="Critical Risk", description="Major issue",
            category="security", severity=RiskSeverity.CRITICAL, likelihood=0.9, impact_score=10.0
        )
        self.engine.register_risk(risk)
        with self.assertRaises(PermissionError):
            self.engine.accept_risk("R-003", accepted_by="Alice", justification="Too hard to fix")

    def test_accept_critical_risk_with_expired_waiver_fails(self):
        risk = ResidualRiskEntry(
            risk_id="R-003", title="Critical Risk", description="Major issue",
            category="security", severity=RiskSeverity.CRITICAL, likelihood=0.9, impact_score=10.0
        )
        self.engine.register_risk(risk)
        expired_date = (datetime.now() - timedelta(days=1)).isoformat()
        waiver = RiskWaiver(waiver_id="W-001", risk_id="R-003", approved_by="Bob", reason="Exp", expires_at=expired_date)
        self.engine.grant_waiver(waiver)
        with self.assertRaises(PermissionError):
            self.engine.accept_risk("R-003", accepted_by="Alice", justification="Too hard to fix")

    def test_accept_critical_risk_with_active_waiver_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-003", title="Critical Risk", description="Major issue",
            category="security", severity=RiskSeverity.CRITICAL, likelihood=0.9, impact_score=10.0
        )
        self.engine.register_risk(risk)
        active_date = (datetime.now() + timedelta(days=10)).isoformat()
        waiver = RiskWaiver(waiver_id="W-001", risk_id="R-003", approved_by="Bob", reason="Active", expires_at=active_date)
        self.engine.grant_waiver(waiver)
        accepted = self.engine.accept_risk("R-003", accepted_by="Alice", justification="Too hard to fix")
        self.assertEqual(accepted.status, RiskStatus.ACCEPTED)

    def test_escalate_risk_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-004", title="Escalated Risk", description="Need help",
            category="performance", severity=RiskSeverity.MEDIUM, likelihood=0.5, impact_score=5.0
        )
        self.engine.register_risk(risk)
        escalated = self.engine.escalate_risk("R-004", reason="No progress")
        self.assertEqual(escalated.status, RiskStatus.ESCALATED)
        
    def test_escalate_nonexistent_risk_fails(self):
        with self.assertRaises(ValueError):
            self.engine.escalate_risk("R-999", reason="Fail")
            
    def test_close_risk_mitigated_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-005", title="Fixed", description="Done",
            category="data", severity=RiskSeverity.LOW, likelihood=0.1, impact_score=1.0,
            status=RiskStatus.MITIGATING, treatment=RiskTreatment.MITIGATE
        )
        self.engine.register_risk(risk)
        closed = self.engine.close_risk("R-005")
        self.assertEqual(closed.status, RiskStatus.CLOSED)

    def test_close_risk_accepted_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-005", title="Fixed", description="Done",
            category="data", severity=RiskSeverity.LOW, likelihood=0.1, impact_score=1.0,
            status=RiskStatus.ACCEPTED, treatment=RiskTreatment.ACCEPT
        )
        self.engine.register_risk(risk)
        closed = self.engine.close_risk("R-005")
        self.assertEqual(closed.status, RiskStatus.CLOSED)

    def test_close_risk_open_fails(self):
        risk = ResidualRiskEntry(
            risk_id="R-006", title="Open", description="Still open",
            category="data", severity=RiskSeverity.LOW, likelihood=0.1, impact_score=1.0,
            status=RiskStatus.OPEN, treatment=RiskTreatment.MITIGATE
        )
        self.engine.register_risk(risk)
        with self.assertRaises(ValueError):
            self.engine.close_risk("R-006")
            
    def test_close_nonexistent_risk_fails(self):
        with self.assertRaises(ValueError):
            self.engine.close_risk("R-999")

    def test_grant_waiver_success(self):
        risk = ResidualRiskEntry(
            risk_id="R-007", title="Risk for waiver", description="...",
            category="compliance", severity=RiskSeverity.HIGH, likelihood=0.5, impact_score=6.0
        )
        self.engine.register_risk(risk)
        active_date = (datetime.now() + timedelta(days=5)).isoformat()
        waiver = RiskWaiver(waiver_id="W-002", risk_id="R-007", approved_by="Charlie", reason="Time needed", expires_at=active_date)
        wid = self.engine.grant_waiver(waiver)
        self.assertEqual(wid, "W-002")
        
    def test_grant_waiver_missing_risk_fails(self):
        waiver = RiskWaiver(waiver_id="W-003", risk_id="R-999", approved_by="Charlie", reason="None", expires_at="")
        with self.assertRaises(ValueError):
            self.engine.grant_waiver(waiver)
            
    def test_grant_duplicate_waiver_fails(self):
        risk = ResidualRiskEntry(
            risk_id="R-007", title="Risk", description="...",
            category="compliance", severity=RiskSeverity.HIGH, likelihood=0.5, impact_score=6.0
        )
        self.engine.register_risk(risk)
        waiver = RiskWaiver(waiver_id="W-002", risk_id="R-007", approved_by="Charlie", reason="Time", expires_at="2030-01-01")
        self.engine.grant_waiver(waiver)
        with self.assertRaises(ValueError):
            self.engine.grant_waiver(waiver)

    def test_assess_release_readiness_clean(self):
        assessment = self.engine.assess_release_readiness("A-001")
        self.assertTrue(assessment.release_recommended)
        self.assertEqual(assessment.total_risks, 0)
        self.assertEqual(len(assessment.blockers), 0)

    def test_assess_release_readiness_with_low_risk(self):
        risk = ResidualRiskEntry(
            risk_id="R-008", title="Low Risk", description="...",
            category="performance", severity=RiskSeverity.LOW, likelihood=0.1, impact_score=1.0
        )
        self.engine.register_risk(risk)
        assessment = self.engine.assess_release_readiness("A-002")
        self.assertTrue(assessment.release_recommended)
        
    def test_assess_release_readiness_blocked_by_high_risk(self):
        risk = ResidualRiskEntry(
            risk_id="R-009", title="High Risk", description="...",
            category="security", severity=RiskSeverity.HIGH, likelihood=0.8, impact_score=8.0, status=RiskStatus.OPEN
        )
        self.engine.register_risk(risk)
        assessment = self.engine.assess_release_readiness("A-003")
        self.assertFalse(assessment.release_recommended)
        self.assertEqual(len(assessment.blockers), 1)

    def test_assess_release_readiness_allowed_with_waiver(self):
        risk = ResidualRiskEntry(
            risk_id="R-009", title="High Risk", description="...",
            category="security", severity=RiskSeverity.HIGH, likelihood=0.8, impact_score=8.0, status=RiskStatus.OPEN
        )
        self.engine.register_risk(risk)
        active_date = (datetime.now() + timedelta(days=1)).isoformat()
        waiver = RiskWaiver(waiver_id="W-004", risk_id="R-009", approved_by="Dave", reason="Fix next sprint", expires_at=active_date)
        self.engine.grant_waiver(waiver)
        assessment = self.engine.assess_release_readiness("A-004")
        self.assertTrue(assessment.release_recommended)

    def test_assess_release_readiness_blocked_by_expired_waiver(self):
        risk = ResidualRiskEntry(
            risk_id="R-009", title="High Risk", description="...",
            category="security", severity=RiskSeverity.HIGH, likelihood=0.8, impact_score=8.0, status=RiskStatus.OPEN
        )
        self.engine.register_risk(risk)
        expired_date = (datetime.now() - timedelta(days=1)).isoformat()
        waiver = RiskWaiver(waiver_id="W-004", risk_id="R-009", approved_by="Dave", reason="Fix next sprint", expires_at=expired_date)
        self.engine.grant_waiver(waiver)
        assessment = self.engine.assess_release_readiness("A-005")
        self.assertFalse(assessment.release_recommended)

    def test_get_risks_by_category(self):
        self.engine.register_risk(ResidualRiskEntry("R-1", "A", "A", "cat1", RiskSeverity.LOW, 0.1, 1.0))
        self.engine.register_risk(ResidualRiskEntry("R-2", "B", "B", "cat2", RiskSeverity.LOW, 0.1, 1.0))
        self.engine.register_risk(ResidualRiskEntry("R-3", "C", "C", "cat1", RiskSeverity.LOW, 0.1, 1.0))
        res = self.engine.get_risks_by_category("cat1")
        self.assertEqual(len(res), 2)
        
    def test_get_risks_by_severity(self):
        self.engine.register_risk(ResidualRiskEntry("R-1", "A", "A", "cat1", RiskSeverity.LOW, 0.1, 1.0))
        self.engine.register_risk(ResidualRiskEntry("R-2", "B", "B", "cat2", RiskSeverity.HIGH, 0.1, 1.0))
        res = self.engine.get_risks_by_severity(RiskSeverity.HIGH)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].risk_id, "R-2")

    def test_get_risk_heatmap(self):
        self.engine.register_risk(ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.HIGH, 0.1, 1.0))
        self.engine.register_risk(ResidualRiskEntry("R-2", "B", "B", "sec", RiskSeverity.HIGH, 0.1, 1.0))
        self.engine.register_risk(ResidualRiskEntry("R-3", "C", "C", "perf", RiskSeverity.LOW, 0.1, 1.0))
        heatmap = self.engine.get_risk_heatmap()
        self.assertEqual(heatmap[RiskSeverity.HIGH.value]["sec"], 2)
        self.assertEqual(heatmap[RiskSeverity.LOW.value]["perf"], 1)

    def test_get_overdue_reviews(self):
        self.engine.register_risk(ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.LOW, 0.1, 1.0, review_date="2020-01-01"))
        self.engine.register_risk(ResidualRiskEntry("R-2", "B", "B", "sec", RiskSeverity.LOW, 0.1, 1.0, review_date="2030-01-01"))
        overdue = self.engine.get_overdue_reviews("2025-01-01")
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].risk_id, "R-1")

    def test_get_risk_register_report(self):
        self.engine.register_risk(ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.LOW, 0.5, 2.0))
        self.engine.register_risk(ResidualRiskEntry("R-2", "B", "B", "sec", RiskSeverity.HIGH, 0.5, 8.0, status=RiskStatus.ACCEPTED))
        report = self.engine.get_risk_register_report()
        self.assertEqual(report["total_risks"], 2)
        self.assertEqual(report["status_counts"][RiskStatus.OPEN.value], 1)
        self.assertEqual(report["status_counts"][RiskStatus.ACCEPTED.value], 1)
        self.assertEqual(report["total_risk_score"], 5.0) # 1.0 + 4.0
        self.assertEqual(report["average_risk_score"], 2.5)

    def test_recompute_risk_score_on_update(self):
        risk = ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.LOW, 0.5, 2.0)
        self.engine.register_risk(risk)
        self.assertEqual(risk.risk_score, 1.0)
        self.engine.update_risk("R-1", likelihood=1.0)
        self.assertEqual(risk.risk_score, 2.0)
        self.engine.update_risk("R-1", impact_score=5.0)
        self.assertEqual(risk.risk_score, 5.0)

    def test_close_already_closed_risk(self):
        risk = ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.LOW, 0.5, 2.0, status=RiskStatus.CLOSED)
        self.engine.register_risk(risk)
        self.engine.close_risk("R-1") # Should just succeed as it's already closed/allowed
        self.assertEqual(risk.status, RiskStatus.CLOSED)

    def test_assess_release_readiness_counts(self):
        self.engine.register_risk(ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.CRITICAL, 1.0, 10.0))
        self.engine.register_risk(ResidualRiskEntry("R-2", "B", "B", "sec", RiskSeverity.HIGH, 0.5, 8.0))
        self.engine.register_risk(ResidualRiskEntry("R-3", "C", "C", "sec", RiskSeverity.LOW, 0.1, 1.0, status=RiskStatus.ACCEPTED))
        assessment = self.engine.assess_release_readiness("A-999")
        self.assertEqual(assessment.critical_count, 1)
        self.assertEqual(assessment.high_count, 1)
        self.assertEqual(assessment.accepted_count, 1)
        self.assertEqual(assessment.total_risks, 3)
        self.assertEqual(assessment.overall_risk_score, 14.1)

    def test_empty_engine_report(self):
        report = self.engine.get_risk_register_report()
        self.assertEqual(report["total_risks"], 0)
        self.assertEqual(report["average_risk_score"], 0.0)
        
    def test_escalated_risk_blocking_release(self):
        risk = ResidualRiskEntry("R-1", "A", "A", "sec", RiskSeverity.HIGH, 0.8, 8.0)
        self.engine.register_risk(risk)
        self.engine.escalate_risk("R-1", "Need manager")
        assessment = self.engine.assess_release_readiness("A-001")
        self.assertFalse(assessment.release_recommended)
        self.assertEqual(len(assessment.blockers), 1)

if __name__ == '__main__':
    unittest.main()
