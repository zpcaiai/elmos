"""Comprehensive tests for ProductionReadinessReviewEngine (Batch 39 - Skill 1364)."""

import unittest

from elmos_mature_platform.production_readiness_review_engine import (
    ProductionReadinessReviewEngine,
)
from elmos_mature_platform.types import (
    PrrCategory,
    PrrChecklistItem,
    PrrItemStatus,
)


class TestProductionReadinessReviewComprehensive(unittest.TestCase):
    """Test suite verifying SRE Production Readiness Review lifecycle and gates."""

    def setUp(self):
        self.engine = ProductionReadinessReviewEngine(passing_score_threshold=80.0)

    def test_create_review_auto_seeds_checklist(self):
        """Verify new PRR initializes with standard checklist covering all categories."""
        review = self.engine.create_review(service_name="payment-gateway", target_environment="production")
        self.assertTrue(review.review_id.startswith("prr-"))
        self.assertEqual(review.service_name, "payment-gateway")
        self.assertEqual(review.target_environment, "production")
        self.assertFalse(review.approved)
        self.assertGreaterEqual(len(review.checklist), 14)

        categories_present = {item.category for item in review.checklist}
        for cat in PrrCategory:
            self.assertIn(cat, categories_present)

    def test_record_checklist_item(self):
        """Verify updating checklist item status and remediation."""
        review = self.engine.create_review("order-service")
        item = review.checklist[0]

        updated = self.engine.record_checklist_item(
            review.review_id,
            item.item_id,
            status=PrrItemStatus.PASS,
            owner="alice@elmos.io",
            remediation="Prometheus alerts active",
        )
        self.assertEqual(updated.status, PrrItemStatus.PASS)
        self.assertEqual(updated.owner, "alice@elmos.io")

    def test_waive_checklist_item(self):
        """Verify granting audited waiver for a checklist item."""
        review = self.engine.create_review("reporting-service")
        item = review.checklist[0]

        waived = self.engine.waive_checklist_item(
            review.review_id,
            item.item_id,
            waiver_justification="Temporary deferral until Q4",
            approver="Director SRE",
        )
        self.assertEqual(waived.status, PrrItemStatus.WAIVED)
        self.assertIn("Director SRE", waived.remediation)

    def test_waiver_requires_justification_and_approver(self):
        """Verify invalid waiver requests raise ValueError."""
        review = self.engine.create_review("analytics-service")
        item = review.checklist[0]

        with self.assertRaises(ValueError):
            self.engine.waive_checklist_item(review.review_id, item.item_id, "", "SRE Lead")

        with self.assertRaises(ValueError):
            self.engine.waive_checklist_item(review.review_id, item.item_id, "Valid reason", "")

    def test_evaluate_approval_blocked_by_open_failures(self):
        """Verify review is rejected if blocking checklist items are in FAIL status."""
        review = self.engine.create_review("auth-service")
        eval_review = self.engine.evaluate_approval(review.review_id, sign_off_sre="Bob")
        self.assertFalse(eval_review.approved)
        self.assertEqual(eval_review.sign_off_sre, "")
        self.assertGreater(len(self.engine.get_open_blockers(review.review_id)), 0)

    def test_evaluate_approval_succeeds_when_all_pass_or_waived(self):
        """Verify approval succeeds when all items are PASS or WAIVED."""
        review = self.engine.create_review("checkout-service")
        for item in review.checklist:
            self.engine.record_checklist_item(review.review_id, item.item_id, PrrItemStatus.PASS)

        eval_review = self.engine.evaluate_approval(review.review_id, sign_off_sre="Lead SRE")
        self.assertTrue(eval_review.approved)
        self.assertEqual(eval_review.readiness_score, 100.0)
        self.assertEqual(eval_review.sign_off_sre, "Lead SRE")
        self.assertEqual(len(self.engine.get_open_blockers(review.review_id)), 0)

    def test_get_review_scorecard(self):
        """Verify scorecard aggregates category metrics accurately."""
        review = self.engine.create_review("inventory-service")
        scorecard = self.engine.get_review_scorecard(review.review_id)
        self.assertEqual(scorecard["review_id"], review.review_id)
        self.assertEqual(scorecard["service_name"], "inventory-service")
        self.assertIn("by_category", scorecard)
        self.assertIn(PrrCategory.MONITORING_ALERTS.value, scorecard["by_category"])


if __name__ == "__main__":
    unittest.main()
