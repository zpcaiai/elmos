import unittest
from elmos_mature_platform.types import (
    CertificationDecision,
    MaturityDimension,
    MaturityLevel,
    ResidualRisk,
    SeverityLevel,
)
from elmos_mature_platform.maturity_certification_engine import MaturityCertificationEngine

class TestMaturityCertificationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MaturityCertificationEngine()

    def test_assess_dimension_high_score(self):
        assessment = self.engine.assess_dimension(
            MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10
        )
        self.assertEqual(assessment.level, MaturityLevel.L5_OPTIMIZING)
        self.assertEqual(assessment.score, 100.0)

    def test_assess_dimension_low_score(self):
        assessment = self.engine.assess_dimension(
            MaturityDimension.SECURITY_DATA, 10, 1, 10
        )
        self.assertEqual(assessment.level, MaturityLevel.L0_ABSENT)
        self.assertEqual(assessment.score, 10.0)

    def test_assess_dimension_with_blockers(self):
        assessment = self.engine.assess_dimension(
            MaturityDimension.SRE_RELIABILITY, 10, 10, 10, blockers=["No on-call rotation"]
        )
        self.assertEqual(assessment.level, MaturityLevel.L4_MEASURED)
        self.assertEqual(assessment.score, 80.0)

    def test_assess_dimension_zero_tests(self):
        assessment = self.engine.assess_dimension(
            MaturityDimension.CUSTOMER_VALUE, 0, 0, 0
        )
        self.assertEqual(assessment.level, MaturityLevel.L0_ABSENT)
        self.assertEqual(assessment.score, 0.0)

    def test_generate_maturity_report_strong(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10),
            self.engine.assess_dimension(MaturityDimension.SECURITY_DATA, 10, 9, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        self.assertEqual(report.overall_level, MaturityLevel.L5_OPTIMIZING)
        self.assertGreaterEqual(report.overall_score, 95.0)

    def test_generate_maturity_report_mixed(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10),
            self.engine.assess_dimension(MaturityDimension.SECURITY_DATA, 10, 2, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        self.assertEqual(report.overall_level, MaturityLevel.L3_DEFINED)
        self.assertEqual(report.overall_score, 60.0)

    def test_generate_maturity_report_blocking_dimensions(self):
        assessments = [
            self.engine.assess_dimension(
                MaturityDimension.SECURITY_DATA, 10, 10, 10, blockers=["Critical Vuln"]
            ),
            self.engine.assess_dimension(MaturityDimension.SRE_RELIABILITY, 10, 5, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        self.assertIn(MaturityDimension.SECURITY_DATA, report.blocking_dimensions)
        self.assertIn(MaturityDimension.SRE_RELIABILITY, report.blocking_dimensions)

    def test_residual_risk_registration(self):
        risk = ResidualRisk(
            risk_id="R-001",
            dimension=MaturityDimension.SECURITY_DATA,
            title="Data in transit",
            description="Not all internal traffic is encrypted",
            severity=SeverityLevel.HIGH,
            probability="medium",
            impact="high",
            mitigation="VPC boundaries"
        )
        self.engine.register_residual_risk(risk)
        self.assertIn("R-001", self.engine._risks)

    def test_accept_residual_risk(self):
        risk = ResidualRisk(
            risk_id="R-001",
            dimension=MaturityDimension.SECURITY_DATA,
            title="Data in transit",
            description="Not all internal traffic is encrypted",
            severity=SeverityLevel.HIGH,
            probability="medium",
            impact="high",
            mitigation="VPC boundaries"
        )
        self.engine.register_residual_risk(risk)
        accepted = self.engine.accept_residual_risk("R-001", "CISO")
        self.assertEqual(accepted.accepted_by, "CISO")
        self.assertIsNotNone(accepted.accepted_at)

    def test_unaccepted_risks_listing(self):
        risk = ResidualRisk(
            risk_id="R-001",
            dimension=MaturityDimension.SECURITY_DATA,
            title="Data in transit",
            description="Not all internal traffic is encrypted",
            severity=SeverityLevel.HIGH,
            probability="medium",
            impact="high",
            mitigation="VPC boundaries"
        )
        self.engine.register_residual_risk(risk)
        unaccepted = self.engine.get_unaccepted_risks()
        self.assertEqual(len(unaccepted), 1)

    def test_certification_gate_approved(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10),
            self.engine.assess_dimension(MaturityDimension.SECURITY_DATA, 10, 8, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        decision = self.engine.evaluate_certification_gate(report)
        self.assertEqual(decision, CertificationDecision.APPROVED)

    def test_certification_gate_conditionally_approved(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 7, 10),
            self.engine.assess_dimension(MaturityDimension.SECURITY_DATA, 10, 7, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        decision = self.engine.evaluate_certification_gate(report)
        self.assertEqual(decision, CertificationDecision.CONDITIONALLY_APPROVED)

    def test_certification_gate_blocked_by_risk(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        risk = ResidualRisk(
            risk_id="R-002",
            dimension=MaturityDimension.SECURITY_DATA,
            title="DB open",
            description="DB port open",
            severity=SeverityLevel.CRITICAL,
            probability="high",
            impact="critical",
            mitigation="None"
        )
        self.engine.register_residual_risk(risk)
        decision = self.engine.evaluate_certification_gate(report)
        self.assertEqual(decision, CertificationDecision.BLOCKED)

    def test_certification_gate_rejected_score(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 2, 10),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        decision = self.engine.evaluate_certification_gate(report)
        self.assertEqual(decision, CertificationDecision.REJECTED)

    def test_certification_gate_rejected_critical_blocker(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10, blockers=["Critical flaw"]),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        decision = self.engine.evaluate_certification_gate(report)
        self.assertEqual(decision, CertificationDecision.REJECTED)

    def test_readiness_checklist_all_passed(self):
        chk = self.engine.create_readiness_checklist("auth-service")
        for item in chk.items:
            self.engine.update_checklist_item(chk.checklist_id, item, True)
        eval_result = self.engine.evaluate_readiness(chk.checklist_id)
        self.assertTrue(eval_result["overall_ready"])
        self.assertEqual(eval_result["ready_percentage"], 100.0)

    def test_readiness_checklist_partial(self):
        chk = self.engine.create_readiness_checklist("auth-service")
        self.engine.update_checklist_item(chk.checklist_id, "has_monitoring", True)
        eval_result = self.engine.evaluate_readiness(chk.checklist_id)
        self.assertFalse(eval_result["overall_ready"])
        self.assertLess(eval_result["ready_percentage"], 100.0)

    def test_readiness_evaluation_statistics(self):
        chk = self.engine.create_readiness_checklist("stats-service")
        self.engine.update_checklist_item(chk.checklist_id, "has_monitoring", True)
        res = self.engine.evaluate_readiness(chk.checklist_id)
        self.assertEqual(res["total_items"], 12)
        self.assertEqual(res["passed_items"], 1)
        self.assertEqual(len(res["missing_items"]), 11)

    def test_dimension_gap_report(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.SRE_RELIABILITY, 10, 5, 10, gaps=["No runbook"], blockers=["No alerts"]),
        ]
        self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        report = self.engine.get_dimension_gap_report(MaturityDimension.SRE_RELIABILITY)
        self.assertIn("No runbook", report["unique_gaps"])
        self.assertIn("No alerts", report["unique_blockers"])

    def test_compare_reports_improvement(self):
        ass1 = [self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 5, 10)]
        r1 = self.engine.generate_maturity_report("v1.0", "assessor", ass1)
        ass2 = [self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10)]
        r2 = self.engine.generate_maturity_report("v2.0", "assessor", ass2)
        
        comp = self.engine.compare_assessments(r1.report_id, r2.report_id)
        self.assertGreater(comp["overall_score_delta"], 0)
        self.assertIn(MaturityDimension.FUNCTIONAL_DEPTH, comp["improved_dimensions"])

    def test_compare_reports_regression(self):
        ass1 = [self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10)]
        r1 = self.engine.generate_maturity_report("v1.0", "assessor", ass1)
        ass2 = [self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 5, 10)]
        r2 = self.engine.generate_maturity_report("v2.0", "assessor", ass2)
        
        comp = self.engine.compare_assessments(r1.report_id, r2.report_id)
        self.assertLess(comp["overall_score_delta"], 0)
        self.assertIn(MaturityDimension.FUNCTIONAL_DEPTH, comp["regressed_dimensions"])

    def test_certification_summary(self):
        ass1 = [self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10)]
        r1 = self.engine.generate_maturity_report("v1.0", "assessor", ass1)
        self.engine.evaluate_certification_gate(r1)
        
        ass2 = [self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 2, 10, blockers=["Auth block"])]
        r2 = self.engine.generate_maturity_report("v2.0", "assessor", ass2)
        self.engine.evaluate_certification_gate(r2)
        
        summary = self.engine.get_certification_summary()
        self.assertEqual(summary["total_reports"], 2)
        self.assertIn(CertificationDecision.APPROVED.value, summary["by_decision"])
        self.assertIn(CertificationDecision.REJECTED.value, summary["by_decision"])
        self.assertIn(("Auth block", 1), summary["most_common_blockers"])

    def test_multiple_reports_tracking(self):
        for i in range(5):
            self.engine.generate_maturity_report(f"v{i}.0", "assessor", [])
        self.assertEqual(len(self.engine._reports), 5)

    def test_all_12_dimensions(self):
        assessments = [
            self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.SEMANTIC_BEHAVIOR, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.ROUTE_BREADTH, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.SCALE_PERFORMANCE, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.SECURITY_DATA, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.SRE_RELIABILITY, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.DEVELOPER_EXPERIENCE, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.ECONOMICS_PROFITABILITY, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.DEPLOYMENT_MATRIX, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.ECOSYSTEM_MARKETPLACE, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.TARGET_MAINTAINABILITY, 1, 1, 1),
            self.engine.assess_dimension(MaturityDimension.CUSTOMER_VALUE, 1, 1, 1),
        ]
        report = self.engine.generate_maturity_report("v1.0", "assessor", assessments)
        self.assertEqual(len(report.dimensions), 12)
        self.assertEqual(report.overall_score, 100.0)

    def test_level_boundaries(self):
        l0 = self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 1, 10) # 10%
        l1 = self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 2, 10) # 20%
        l2 = self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 4, 10) # 40%
        l3 = self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 6, 10) # 60%
        l4 = self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 8, 10) # 80%
        l5 = self.engine.assess_dimension(MaturityDimension.FUNCTIONAL_DEPTH, 10, 10, 10) # 100%

        self.assertEqual(l0.level, MaturityLevel.L0_ABSENT)
        self.assertEqual(l1.level, MaturityLevel.L1_INITIAL)
        self.assertEqual(l2.level, MaturityLevel.L2_DEVELOPING)
        self.assertEqual(l3.level, MaturityLevel.L3_DEFINED)
        self.assertEqual(l4.level, MaturityLevel.L4_MEASURED)
        self.assertEqual(l5.level, MaturityLevel.L5_OPTIMIZING)

if __name__ == "__main__":
    unittest.main()
