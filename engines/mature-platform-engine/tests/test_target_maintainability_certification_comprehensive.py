import unittest
from elmos_mature_platform.target_maintainability_certification_engine import (
    TargetMaintainabilityCertificationEngine,
)
from elmos_mature_platform.types import (
    MaintainabilityMetricType,
    MaintainabilityRating,
    MaintainabilitySmellFinding,
    TargetCodeMetric,
)


class TestTargetMaintainabilityCertificationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = TargetMaintainabilityCertificationEngine()

    def test_create_certification_assessment(self):
        cert_id = self.engine.create_certification_assessment("proj-101", "payment-service", "typescript")
        self.assertTrue(bool(cert_id))
        self.assertTrue(cert_id.startswith("maint-"))
        with self.assertRaises(ValueError):
            self.engine.create_certification_assessment("", "payment-service", "typescript")

    def test_record_code_metric_thresholds(self):
        cert_id = self.engine.create_certification_assessment("proj-102", "order-service", "java")
        # Cyclomatic complexity: lower is better
        m1 = TargetCodeMetric(
            metric_id="m1",
            metric_type=MaintainabilityMetricType.CYCLOMATIC_COMPLEXITY,
            target_file_or_module="OrderController.java",
            value=8.0,
            acceptable_limit=10.0,
            weight=1.0,
        )
        cert = self.engine.record_code_metric(cert_id, m1)
        self.assertTrue(m1.passed)

        # Maintainability Index: higher is better
        m2 = TargetCodeMetric(
            metric_id="m2",
            metric_type=MaintainabilityMetricType.MAINTAINABILITY_INDEX,
            target_file_or_module="OrderController.java",
            value=88.0,
            acceptable_limit=70.0,
            weight=2.0,
        )
        self.engine.record_code_metric(cert_id, m2)
        self.assertTrue(m2.passed)

    def test_compute_grade_and_certification(self):
        cert_id = self.engine.create_certification_assessment("proj-103", "auth-service", "go")
        m1 = TargetCodeMetric(
            metric_id="m1",
            metric_type=MaintainabilityMetricType.CYCLOMATIC_COMPLEXITY,
            target_file_or_module="auth.go",
            value=4.0,
            acceptable_limit=10.0,
            weight=1.0,
        )
        m2 = TargetCodeMetric(
            metric_id="m2",
            metric_type=MaintainabilityMetricType.MAINTAINABILITY_INDEX,
            target_file_or_module="auth.go",
            value=92.0,
            acceptable_limit=75.0,
            weight=1.0,
        )
        self.engine.record_code_metric(cert_id, m1)
        self.engine.record_code_metric(cert_id, m2)

        cert = self.engine.compute_maintainability_grade(cert_id)
        self.assertEqual(cert.overall_grade, MaintainabilityRating.GRADE_A)

        # Certify with minimum grade B
        certified = self.engine.certify_maintainability(cert_id, certifier="qa-audit-team")
        self.assertTrue(certified.is_certified)
        self.assertEqual(certified.certifier, "qa-audit-team")

    def test_certify_failure_due_to_critical_smell(self):
        cert_id = self.engine.create_certification_assessment("proj-104", "legacy-crm", "csharp")
        m1 = TargetCodeMetric(
            metric_id="m1",
            metric_type=MaintainabilityMetricType.MAINTAINABILITY_INDEX,
            target_file_or_module="CustomerRepo.cs",
            value=88.0,
            acceptable_limit=70.0,
            weight=1.0,
        )
        self.engine.record_code_metric(cert_id, m1)
        s1 = MaintainabilitySmellFinding(
            finding_id="s1",
            category="ARCHITECTURAL_CYCLE",
            severity="critical",
            location="CustomerRepo.cs:42",
            remediation_effort_minutes=120,
        )
        self.engine.record_smell_finding(cert_id, s1)

        cert = self.engine.compute_maintainability_grade(cert_id)
        certified = self.engine.certify_maintainability(cert_id, certifier="qa-lead")
        self.assertFalse(certified.is_certified)

    def test_debt_remediation_estimate_and_quick_wins(self):
        cert_id = self.engine.create_certification_assessment("proj-105", "billing", "python")
        s1 = MaintainabilitySmellFinding(
            finding_id="s1",
            category="LONG_METHOD",
            severity="minor",
            location="billing.py:100",
            remediation_effort_minutes=10,
        )
        s2 = MaintainabilitySmellFinding(
            finding_id="s2",
            category="GOD_CLASS",
            severity="major",
            location="billing.py:1",
            remediation_effort_minutes=180,
        )
        self.engine.record_smell_finding(cert_id, s1)
        self.engine.record_smell_finding(cert_id, s2)

        estimate = self.engine.get_debt_remediation_estimate(cert_id)
        self.assertEqual(estimate["total_effort_minutes"], 190)
        self.assertEqual(estimate["quick_wins_count"], 1)

    def test_compare_and_benchmarks(self):
        c_a = self.engine.create_certification_assessment("p-a", "repo-a", "go")
        c_b = self.engine.create_certification_assessment("p-b", "repo-b", "go")

        m_a = TargetCodeMetric(
            metric_id="ma",
            metric_type=MaintainabilityMetricType.MAINTAINABILITY_INDEX,
            target_file_or_module="a.go",
            value=95.0,
            acceptable_limit=70.0,
            weight=1.0,
        )
        m_b = TargetCodeMetric(
            metric_id="mb",
            metric_type=MaintainabilityMetricType.MAINTAINABILITY_INDEX,
            target_file_or_module="b.go",
            value=60.0,
            acceptable_limit=70.0,
            weight=1.0,
        )
        self.engine.record_code_metric(c_a, m_a)
        self.engine.record_code_metric(c_b, m_b)

        self.engine.certify_maintainability(c_a, "lead")
        self.engine.compute_maintainability_grade(c_b)

        cmp_res = self.engine.compare_maintainability(c_a, c_b)
        self.assertEqual(cmp_res["higher_grade"], MaintainabilityRating.GRADE_A.value)

        bench = self.engine.get_language_maintainability_benchmark("go")
        self.assertEqual(bench["total_assessed"], 2)
        self.assertEqual(bench["certification_rate"], 0.5)

        fleet = self.engine.get_fleet_maintainability_report()
        self.assertEqual(fleet["total_assessments"], 2)
        self.assertEqual(fleet["certified_assessments"], 1)


if __name__ == "__main__":
    unittest.main()
