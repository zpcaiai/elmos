"""Comprehensive tests for AutomationBuildgreenPredictionEngine (Batch 41 - Skill 1404)."""

import unittest

from elmos_mature_platform.automation_buildgreen_prediction_engine import (
    AutomationBuildgreenPredictionEngine,
)
from elmos_mature_platform.types import (
    BuildPredictionVerdict,
)


class TestAutomationBuildgreenPredictionComprehensive(unittest.TestCase):
    """Test suite verifying commit risk scoring, buildgreen forecasting, and calibration metrics."""

    def setUp(self):
        self.engine = AutomationBuildgreenPredictionEngine(default_green_threshold=0.70)

    def test_predict_commit_build_low_risk(self):
        """Verify low-churn commit with test coverage yields HIGH_CONFIDENCE_GREEN."""
        pred = self.engine.predict_commit_build(
            commit_sha="a1b2c3d4e5f6",
            branch="main",
            author="senior-dev",
            lines_changed=25,
            test_files_changed=4,
            dependency_files_changed=0,
            author_historical_pass_rate=0.98,
        )
        self.assertTrue(pred.prediction_id.startswith("pred-"))
        self.assertEqual(pred.predicted_verdict, BuildPredictionVerdict.HIGH_CONFIDENCE_GREEN)
        self.assertGreaterEqual(pred.green_probability, 0.90)
        self.assertEqual(len(pred.risk_factors), 4)

    def test_predict_commit_build_high_risk(self):
        """Verify massive churn with dependency mutations and zero tests yields risky/red verdict."""
        pred = self.engine.predict_commit_build(
            commit_sha="f6e5d4c3b2a1",
            branch="feature-refactor",
            author="intern",
            lines_changed=4000,
            test_files_changed=0,
            dependency_files_changed=3,
            author_historical_pass_rate=0.50,
        )
        self.assertIn(pred.predicted_verdict, (BuildPredictionVerdict.RISKY_RED, BuildPredictionVerdict.HIGH_RISK_RED))
        self.assertLess(pred.green_probability, 0.50)

    def test_input_validation(self):
        """Verify invalid input parameters raise ValueError."""
        with self.assertRaises(ValueError):
            self.engine.predict_commit_build("", "main", "alice", 10, 1, 0)

        with self.assertRaises(ValueError):
            self.engine.predict_commit_build("abc1234", "main", "alice", -5, 1, 0)

    def test_record_actual_outcome_and_calibration_metrics(self):
        """Verify calibration accuracy, confusion matrix counts, and Brier score."""
        # 1. High confidence prediction that passed
        p1 = self.engine.predict_commit_build("sha1", "main", "dev1", 10, 5, 0, 0.95)
        self.engine.record_actual_outcome(p1.prediction_id, build_passed=True)

        # 2. High risk prediction that failed
        p2 = self.engine.predict_commit_build("sha2", "main", "dev2", 5000, 0, 2, 0.40)
        self.engine.record_actual_outcome(p2.prediction_id, build_passed=False)

        metrics = self.engine.get_model_calibration_metrics()
        self.assertEqual(metrics["evaluated_predictions_count"], 2)
        self.assertEqual(metrics["accuracy_pct"], 100.0)
        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["true_negatives"], 1)
        self.assertEqual(metrics["false_positives"], 0)
        self.assertEqual(metrics["false_negatives"], 0)
        self.assertLess(metrics["brier_score"], 0.15)

    def test_list_predictions_filter(self):
        """Verify filtering predictions by verdict tier."""
        self.engine.predict_commit_build("s1", "main", "a1", 10, 5, 0, 0.99)
        self.engine.predict_commit_build("s2", "main", "a2", 5000, 0, 3, 0.30)

        greens = self.engine.list_predictions(verdict=BuildPredictionVerdict.HIGH_CONFIDENCE_GREEN)
        self.assertEqual(len(greens), 1)
        self.assertEqual(greens[0].commit_sha, "s1")


if __name__ == "__main__":
    unittest.main()
