"""Comprehensive test suite for CustomerValueCertificationEngine (B45 - Skill 1450)."""

import unittest

from elmos_mature_platform.customer_value_certification_engine import (
    CustomerValueCertificationEngine,
)
from elmos_mature_platform.types import (
    MilestoneStatus,
    ValueMetricCategory,
    ValueMilestone,
)


class TestCustomerValueCertificationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = CustomerValueCertificationEngine()

    def test_create_certificate(self):
        cert = self.engine.create_certificate(
            customer_id="cust-enterprise-bank",
            project_name="Core Banking Modernization",
            contract_reference="MSA-2026-BANK-009",
        )
        self.assertIsNotNone(cert)
        self.assertEqual(cert.customer_id, "cust-enterprise-bank")
        self.assertEqual(cert.overall_roi_pct, 0.0)
        self.assertFalse(cert.customer_signoff)

    def test_add_and_update_milestone_progress(self):
        cert = self.engine.create_certificate("c1", "Proj1", "REF1")
        m1 = ValueMilestone(
            milestone_id="m-latency",
            category=ValueMetricCategory.LATENCY_IMPROVEMENT,
            name="P99 API Latency Reduction",
            baseline_value=250.0,
            target_value=50.0,
            actual_value=250.0,
            unit="ms",
        )
        self.engine.add_milestone(cert.certificate_id, m1)

        # Update progress: achieve 45 ms (< 50 ms target) -> status ACHIEVED
        updated = self.engine.update_milestone_progress(cert.certificate_id, "m-latency", 45.0)
        self.assertTrue(updated.achieved)
        self.assertEqual(updated.status, MilestoneStatus.ACHIEVED)

        # Overall ROI should be positive ((250 - 45) / 250) * 100 = 82%
        retrieved_cert = self.engine.get_certificate(cert.certificate_id)
        self.assertEqual(retrieved_cert.overall_roi_pct, 82.0)

    def test_milestone_not_achieved_status_in_progress(self):
        cert = self.engine.create_certificate("c2", "Proj2", "REF2")
        m = ValueMilestone(
            milestone_id="m-tco",
            category=ValueMetricCategory.TCO_REDUCTION,
            name="Annual Infrastructure Spend",
            baseline_value=1000000.0,
            target_value=500000.0,
            actual_value=1000000.0,
            unit="USD",
        )
        self.engine.add_milestone(cert.certificate_id, m)

        updated = self.engine.update_milestone_progress(cert.certificate_id, "m-tco", 750000.0)
        self.assertFalse(updated.achieved)
        self.assertEqual(updated.status, MilestoneStatus.IN_PROGRESS)

    def test_certify_value_success(self):
        cert = self.engine.create_certificate("c3", "Proj3", "REF3")
        m = ValueMilestone(
            milestone_id="m-code-quality",
            category=ValueMetricCategory.CODE_QUALITY_SCORE,
            name="Test Coverage Boost",
            baseline_value=40.0,
            target_value=80.0,
            actual_value=40.0,
            unit="pct",
        )
        self.engine.add_milestone(cert.certificate_id, m)
        self.engine.update_milestone_progress(cert.certificate_id, "m-code-quality", 88.0)

        certified = self.engine.certify_value(cert.certificate_id, certifier="lead-assessor@elmos.io")
        self.assertTrue(bool(certified.certified_at))
        self.assertEqual(certified.certifier, "lead-assessor@elmos.io")

    def test_certify_value_unmet_milestones_raises(self):
        cert = self.engine.create_certificate("c4", "Proj4", "REF4")
        m = ValueMilestone(
            milestone_id="m-unmet",
            category=ValueMetricCategory.DEVELOPER_VELOCITY,
            name="Deploy Frequency",
            baseline_value=1.0,
            target_value=10.0,
            actual_value=2.0,
            unit="deploys/week",
        )
        self.engine.add_milestone(cert.certificate_id, m)

        with self.assertRaises(ValueError):
            self.engine.certify_value(cert.certificate_id, certifier="auditor")

    def test_customer_signoff_workflow(self):
        cert = self.engine.create_certificate("c5", "Proj5", "REF5")
        m = ValueMilestone(
            milestone_id="m-lic",
            category=ValueMetricCategory.LICENSING_SAVINGS,
            name="Commercial DB License Elimination",
            baseline_value=300000.0,
            target_value=0.0,
            actual_value=0.0,
            unit="USD",
            status=MilestoneStatus.ACHIEVED,
            achieved=True,
        )
        self.engine.add_milestone(cert.certificate_id, m)
        self.engine.certify_value(cert.certificate_id, "elmos-principal-architect")

        signed = self.engine.record_customer_signoff(
            cert.certificate_id,
            signoff_date="2026-09-11T10:00:00Z",
            notes="Customer CIO confirmed all targeted savings attained with zero production regressions.",
        )
        self.assertTrue(signed.customer_signoff)
        self.assertEqual(signed.customer_signoff_date, "2026-09-11T10:00:00Z")
        self.assertIn("CIO confirmed", signed.notes)

    def test_customer_signoff_on_uncertified_fails(self):
        cert = self.engine.create_certificate("c6", "Proj6", "REF6")
        with self.assertRaises(ValueError):
            self.engine.record_customer_signoff(cert.certificate_id, "2026-09-11")

    def test_customer_report_generation(self):
        cert = self.engine.create_certificate("c-rep", "Reporting App", "CONTRACT-001")
        m = ValueMilestone(
            milestone_id="m1",
            category=ValueMetricCategory.TCO_REDUCTION,
            name="Infrastructure TCO",
            baseline_value=100.0,
            target_value=50.0,
            actual_value=40.0,
            achieved=True,
            status=MilestoneStatus.ACHIEVED,
        )
        self.engine.add_milestone(cert.certificate_id, m)
        self.engine.certify_value(cert.certificate_id, "certifier-1")

        report = self.engine.get_customer_report(cert.certificate_id)
        self.assertEqual(report["customer_id"], "c-rep")
        self.assertTrue(report["certified"])
        self.assertEqual(report["milestone_progress"]["total"], 1)
        self.assertEqual(report["milestone_progress"]["achieved"], 1)
        self.assertEqual(report["milestone_progress"]["achievement_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
