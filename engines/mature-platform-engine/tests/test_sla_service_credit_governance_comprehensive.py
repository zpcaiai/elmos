"""Comprehensive unit tests for SlaServiceCreditGovernanceEngine (Batch 39 Skill 1365)."""

import unittest

from elmos_mature_platform.sla_service_credit_governance_engine import (
    SlaServiceCreditGovernanceEngine,
)
from elmos_mature_platform.types import (
    SlaBreachTier,
    ServiceCreditStatus,
    SlaServiceCreditPolicy,
    CustomerSlaBreachRecord,
    ServiceCreditDisbursement,
)


class TestSlaServiceCreditGovernanceComprehensive(unittest.TestCase):
    """Test suite for SLA breaches, service credits, executive approvals, and disbursements."""

    def setUp(self) -> None:
        self.engine = SlaServiceCreditGovernanceEngine()
        self.sample_breach = CustomerSlaBreachRecord(
            breach_id="br-001",
            customer_id="cust-cloud-bank",
            service_name="core-transpiler-cluster",
            monthly_invoice_amount=20000.0,
            actual_availability_pct=98.5,  # Moderate breach -> 25% = $5,000
            target_availability_pct=99.9,
        )

    def test_record_breach_tier_2_moderate(self) -> None:
        bid = self.engine.record_breach(self.sample_breach)
        self.assertEqual(bid, "br-001")
        breach = self.engine.get_breach("br-001")
        self.assertIsNotNone(breach)
        self.assertEqual(breach.breach_tier, SlaBreachTier.TIER_2_MODERATE)
        self.assertEqual(breach.calculated_credit_amount, 5000.0)
        self.assertEqual(breach.status, ServiceCreditStatus.CALCULATED)

    def test_record_breach_tier_3_severe(self) -> None:
        severe_breach = CustomerSlaBreachRecord(
            breach_id="br-002",
            customer_id="cust-telecom",
            service_name="ingestion-gateway",
            monthly_invoice_amount=10000.0,
            actual_availability_pct=92.0,  # Severe -> 50% = $5,000
        )
        self.engine.record_breach(severe_breach)
        breach = self.engine.get_breach("br-002")
        self.assertEqual(breach.breach_tier, SlaBreachTier.TIER_3_SEVERE)
        self.assertEqual(breach.calculated_credit_amount, 5000.0)

    def test_record_breach_no_breach_error(self) -> None:
        no_breach = CustomerSlaBreachRecord(
            breach_id="br-good",
            customer_id="cust-1",
            service_name="api",
            monthly_invoice_amount=1000.0,
            actual_availability_pct=99.95,
            target_availability_pct=99.9,
        )
        with self.assertRaises(ValueError):
            self.engine.record_breach(no_breach)

    def test_approve_credit_under_threshold(self) -> None:
        self.sample_breach.monthly_invoice_amount = 10000.0  # 25% = $2,500 < $5,000 threshold
        self.engine.record_breach(self.sample_breach)
        approved = self.engine.approve_credit("br-001", "service-manager-alice")
        self.assertEqual(approved.status, ServiceCreditStatus.APPROVED)
        self.assertEqual(approved.approved_by, "service-manager-alice")

    def test_approve_credit_exceeding_threshold_requires_executive(self) -> None:
        self.sample_breach.monthly_invoice_amount = 40000.0  # 25% = $10,000 > $5,000 threshold
        self.engine.record_breach(self.sample_breach)

        # Standard manager should fail
        with self.assertRaises(ValueError):
            self.engine.approve_credit("br-001", "billing-coordinator-bob")

        # Executive role succeeds
        approved = self.engine.approve_credit("br-001", "vp-finance-david")
        self.assertEqual(approved.status, ServiceCreditStatus.APPROVED)

    def test_disburse_credit_success(self) -> None:
        self.sample_breach.monthly_invoice_amount = 4000.0  # 25% = $1,000
        self.engine.record_breach(self.sample_breach)
        self.engine.approve_credit("br-001", "manager-dan")

        disb = self.engine.disburse_credit("br-001", "CN-2026-OCT-0992")
        self.assertEqual(disb.amount, 1000.0)
        self.assertEqual(disb.customer_id, "cust-cloud-bank")
        self.assertEqual(self.sample_breach.status, ServiceCreditStatus.DISBURSED)

    def test_disburse_unapproved_credit_fails(self) -> None:
        self.engine.record_breach(self.sample_breach)
        # Attempting disbursement without approval fails
        with self.assertRaises(ValueError):
            self.engine.disburse_credit("br-001", "REF-FAIL")

    def test_governance_report(self) -> None:
        self.engine.record_breach(self.sample_breach)
        report = self.engine.get_governance_report()
        self.assertEqual(report["total_breaches"], 1)
        self.assertEqual(report["total_credit_calculated"], 5000.0)
        self.assertEqual(report["total_credit_disbursed"], 0.0)


if __name__ == "__main__":
    unittest.main()
