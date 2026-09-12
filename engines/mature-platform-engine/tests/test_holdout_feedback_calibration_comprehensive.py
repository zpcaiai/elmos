import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    CalibrationAssessment,
    CalibrationBucket,
    PredictionOutcomeRecord,
)
from elmos_mature_platform.holdout_feedback_calibration_engine import HoldoutFeedbackCalibrationEngine


class TestHoldoutFeedbackCalibrationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = HoldoutFeedbackCalibrationEngine()

    def test_record_prediction_outcome(self):
        rec = PredictionOutcomeRecord(
            record_id="poc-1",
            prediction_id="pred-1",
            predicted_confidence=0.85,
            actual_success=True,
            task_type="code_refactor",
            model_id="gemini-1.5-pro",
        )
        rid = self.engine.record_prediction_outcome(rec)
        self.assertEqual(rid, "poc-1")
        self.assertEqual(rec.predicted_confidence, 0.85)

    def test_record_prediction_outcome_clamping(self):
        rec1 = PredictionOutcomeRecord(record_id="p1", prediction_id="p1", predicted_confidence=1.5, actual_success=True, task_type="t", model_id="m")
        rec2 = PredictionOutcomeRecord(record_id="p2", prediction_id="p2", predicted_confidence=-0.2, actual_success=False, task_type="t", model_id="m")
        self.engine.record_prediction_outcome(rec1)
        self.engine.record_prediction_outcome(rec2)
        self.assertEqual(rec1.predicted_confidence, 1.0)
        self.assertEqual(rec2.predicted_confidence, 0.0)

    def test_record_prediction_missing_required(self):
        rec = PredictionOutcomeRecord(record_id="p", prediction_id="", predicted_confidence=0.5, actual_success=True, task_type="t", model_id="")
        with self.assertRaises(ValueError):
            self.engine.record_prediction_outcome(rec)

    def test_record_batch_outcomes(self):
        records = [
            PredictionOutcomeRecord(record_id=f"p-{i}", prediction_id=f"pr-{i}", predicted_confidence=0.8, actual_success=True, task_type="t", model_id="m1")
            for i in range(5)
        ]
        count = self.engine.record_batch_outcomes(records)
        self.assertEqual(count, 5)

    def test_calculate_brier_score(self):
        self.assertEqual(self.engine.calculate_brier_score(), 0.0)

        # Perfect predictions: confidence 1.0 -> actual True, confidence 0.0 -> actual False
        self.engine.record_prediction_outcome(PredictionOutcomeRecord(record_id="1", prediction_id="1", predicted_confidence=1.0, actual_success=True, task_type="t", model_id="m1"))
        self.engine.record_prediction_outcome(PredictionOutcomeRecord(record_id="2", prediction_id="2", predicted_confidence=0.0, actual_success=False, task_type="t", model_id="m1"))
        self.assertEqual(self.engine.calculate_brier_score("m1"), 0.0)

        # Imperfect: confidence 0.8 -> actual False, error = (0.8 - 0)^2 = 0.64
        self.engine.record_prediction_outcome(PredictionOutcomeRecord(record_id="3", prediction_id="3", predicted_confidence=0.8, actual_success=False, task_type="t", model_id="m2"))
        self.assertEqual(self.engine.calculate_brier_score("m2"), 0.64)

    def test_calibration_curve_and_ece(self):
        # Ingest 10 records for model-calib
        for i in range(10):
            conf = (i + 0.5) / 10.0
            success = i >= 4  # top 6 succeed
            self.engine.record_prediction_outcome(
                PredictionOutcomeRecord(
                    record_id=f"rc-{i}",
                    prediction_id=f"pr-{i}",
                    predicted_confidence=conf,
                    actual_success=success,
                    task_type="t",
                    model_id="model-calib",
                )
            )

        buckets = self.engine.calculate_calibration_curve("model-calib", num_bins=10)
        self.assertEqual(len(buckets), 10)
        ece = self.engine.calculate_expected_calibration_error("model-calib", num_bins=10)
        self.assertGreaterEqual(ece, 0.0)
        self.assertLessEqual(ece, 1.0)

    def test_evaluate_calibration_well_calibrated(self):
        # 12 well-calibrated outcomes: 0.9 confidence, 11/12 success ~ 0.916 accuracy -> low ECE
        for i in range(12):
            self.engine.record_prediction_outcome(
                PredictionOutcomeRecord(
                    record_id=f"w-{i}",
                    prediction_id=f"w-{i}",
                    predicted_confidence=0.9,
                    actual_success=(i != 0),
                    task_type="t",
                    model_id="well-calib-model",
                )
            )

        assessment = self.engine.evaluate_calibration("well-calib-model", ece_threshold=0.15)
        self.assertEqual(assessment.model_id, "well-calib-model")
        self.assertEqual(assessment.total_samples, 12)
        self.assertTrue(assessment.is_well_calibrated)

    def test_evaluate_calibration_under_threshold_samples(self):
        # Only 5 samples -> not enough samples, is_well_calibrated is False
        for i in range(5):
            self.engine.record_prediction_outcome(
                PredictionOutcomeRecord(
                    record_id=f"u-{i}",
                    prediction_id=f"u-{i}",
                    predicted_confidence=0.9,
                    actual_success=True,
                    task_type="t",
                    model_id="few-samples-model",
                )
            )
        assessment = self.engine.evaluate_calibration("few-samples-model")
        self.assertFalse(assessment.is_well_calibrated)

    def test_calibrate_confidence(self):
        # 6 samples in bucket [0.8, 0.9) with 3 successes -> empirical accuracy 0.5
        for i in range(6):
            self.engine.record_prediction_outcome(
                PredictionOutcomeRecord(
                    record_id=f"cal-{i}",
                    prediction_id=f"cal-{i}",
                    predicted_confidence=0.85,
                    actual_success=(i % 2 == 0),
                    task_type="t",
                    model_id="calib-map-model",
                )
            )
        calibrated = self.engine.calibrate_confidence("calib-map-model", 0.85)
        self.assertEqual(calibrated, 0.5)

        # Raw confidence returned when samples < 5
        cal_low = self.engine.calibrate_confidence("calib-map-model", 0.15)
        self.assertEqual(cal_low, 0.15)

    def test_get_calibration_report(self):
        self.engine.record_prediction_outcome(
            PredictionOutcomeRecord(
                record_id="rep-1",
                prediction_id="pr-1",
                predicted_confidence=0.8,
                actual_success=True,
                task_type="t",
                model_id="model-alpha",
            )
        )
        self.engine.record_prediction_outcome(
            PredictionOutcomeRecord(
                record_id="rep-2",
                prediction_id="pr-2",
                predicted_confidence=0.7,
                actual_success=False,
                task_type="t",
                model_id="model-beta",
            )
        )
        rep = self.engine.get_calibration_report()
        self.assertEqual(rep["total_outcomes_logged"], 2)
        self.assertIn("model-alpha", rep["monitored_models"])
        self.assertIn("model-beta", rep["monitored_models"])
        self.assertGreater(rep["overall_brier_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
