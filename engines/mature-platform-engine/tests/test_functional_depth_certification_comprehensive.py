"""Comprehensive unit tests for FunctionalDepthCertificationEngine (Batch 45 Skill 1477)."""

import unittest

from elmos_mature_platform.functional_depth_certification_engine import (
    FunctionalDepthCertificationEngine,
)
from elmos_mature_platform.types import (
    FunctionalCategory,
    FunctionalTestCaseResult,
    FunctionalDepthCertificationRecord,
)


class TestFunctionalDepthCertificationComprehensive(unittest.TestCase):
    """Test suite for functional depth certification and multi-category coverage."""

    def setUp(self) -> None:
        self.engine = FunctionalDepthCertificationEngine()
        self.cert_record = self.engine.create_certification_record(
            application_id="app-billing-core",
            version="2.5.0",
            min_depth_threshold=95.0,
        )

    def _populate_all_categories(self, pass_all: bool = True) -> None:
        """Helper to inject test results across all 10 FunctionalCategory values."""
        for idx, cat in enumerate(FunctionalCategory):
            test = FunctionalTestCaseResult(
                test_id=f"tst-{cat.value}-{idx}",
                category=cat,
                name=f"Verify {cat.value} requirements",
                passed=pass_all,
                depth_weight=1.0,
            )
            self.engine.record_test_result(self.cert_record.cert_id, test)

    def test_create_certification_record(self) -> None:
        rec = self.engine.get_record(self.cert_record.cert_id)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.application_id, "app-billing-core")
        self.assertFalse(rec.is_certified)
        self.assertEqual(rec.min_depth_threshold, 95.0)

    def test_evaluate_depth_uncovered_categories_fails(self) -> None:
        # Add tests for only 2 categories
        t1 = FunctionalTestCaseResult(
            test_id="t1",
            category=FunctionalCategory.AUTH_SECURITY,
            name="Auth Token Test",
            passed=True,
            depth_weight=2.0,
        )
        t2 = FunctionalTestCaseResult(
            test_id="t2",
            category=FunctionalCategory.BUSINESS_LOGIC,
            name="Ledger Invariant Test",
            passed=True,
            depth_weight=3.0,
        )
        self.engine.record_test_result(self.cert_record.cert_id, t1)
        self.engine.record_test_result(self.cert_record.cert_id, t2)

        evaluated = self.engine.evaluate_depth(self.cert_record.cert_id)
        self.assertEqual(evaluated.depth_score, 100.0)
        # Even with 100% score, is_certified must be False because 8 categories are missing
        self.assertFalse(evaluated.is_certified)
        uncovered = self.engine.get_uncovered_categories(self.cert_record.cert_id)
        self.assertEqual(len(uncovered), 8)

    def test_evaluate_depth_full_coverage_passes(self) -> None:
        self._populate_all_categories(pass_all=True)
        evaluated = self.engine.evaluate_depth(self.cert_record.cert_id)
        self.assertEqual(evaluated.depth_score, 100.0)
        self.assertTrue(evaluated.is_certified)
        uncovered = self.engine.get_uncovered_categories(self.cert_record.cert_id)
        self.assertEqual(len(uncovered), 0)

    def test_evaluate_depth_below_threshold(self) -> None:
        # Populate all 10 categories, but fail 2 tests (weight 2 of 10 fails -> 80% score < 95%)
        for idx, cat in enumerate(FunctionalCategory):
            passed = idx >= 2  # first 2 fail
            test = FunctionalTestCaseResult(
                test_id=f"tst-{cat.value}-{idx}",
                category=cat,
                name=f"Verify {cat.value}",
                passed=passed,
                depth_weight=1.0,
            )
            self.engine.record_test_result(self.cert_record.cert_id, test)

        evaluated = self.engine.evaluate_depth(self.cert_record.cert_id)
        self.assertEqual(evaluated.depth_score, 80.0)
        self.assertFalse(evaluated.is_certified)

    def test_issue_certification_success_and_failure(self) -> None:
        # Fails when requirements not met
        with self.assertRaises(ValueError):
            self.engine.issue_certification(self.cert_record.cert_id, "auditor-john")

        # Now pass all and certify
        self._populate_all_categories(pass_all=True)
        issued = self.engine.issue_certification(self.cert_record.cert_id, "auditor-john")
        self.assertTrue(issued.is_certified)
        self.assertEqual(issued.certified_by, "auditor-john")
        self.assertTrue(issued.certified_at)

    def test_category_breakdown_and_summary(self) -> None:
        self._populate_all_categories(pass_all=True)
        breakdown = self.engine.get_category_breakdown(self.cert_record.cert_id)
        self.assertEqual(len(breakdown), 10)
        self.assertEqual(breakdown["auth_security"]["passed_tests"], 1)

        summary = self.engine.get_certification_summary()
        self.assertEqual(summary["total_certifications"], 1)


if __name__ == "__main__":
    unittest.main()
