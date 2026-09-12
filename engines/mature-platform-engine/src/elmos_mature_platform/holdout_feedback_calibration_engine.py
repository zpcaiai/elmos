"""Holdout Feedback Calibration Engine (Batch 41 - Skill 1409).

Manages holdout dataset prediction vs actual outcome logging, Brier score calculation,
Expected Calibration Error (ECE) quantification, and isotonic confidence calibration.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    CalibrationAssessment,
    CalibrationBucket,
    PredictionOutcomeRecord,
)


class HoldoutFeedbackCalibrationEngine:
    """Quantifies and refines model confidence calibration on independent holdout workloads."""

    def __init__(self) -> None:
        self._outcomes: List[PredictionOutcomeRecord] = []

    def record_prediction_outcome(self, record: PredictionOutcomeRecord) -> str:
        """Record an observed prediction confidence vs actual outcome entry."""
        if not record.model_id or not record.prediction_id:
            raise ValueError("model_id and prediction_id are required")

        if not record.record_id:
            record.record_id = f"poc-{uuid.uuid4().hex[:8]}"

        if not record.recorded_at:
            record.recorded_at = datetime.now(timezone.utc).isoformat()

        # Clamp confidence to [0.0, 1.0]
        record.predicted_confidence = max(0.0, min(1.0, float(record.predicted_confidence)))
        self._outcomes.append(record)
        return record.record_id

    def record_batch_outcomes(self, records: List[PredictionOutcomeRecord]) -> int:
        """Batch ingest outcome records."""
        count = 0
        for r in records:
            self.record_prediction_outcome(r)
            count += 1
        return count

    def calculate_brier_score(self, model_id: Optional[str] = None) -> float:
        """Calculate mean squared error between confidence probabilities and binary outcomes."""
        samples = [r for r in self._outcomes if not model_id or r.model_id == model_id]
        if not samples:
            return 0.0

        total_sq_err = sum(
            (r.predicted_confidence - (1.0 if r.actual_success else 0.0)) ** 2
            for r in samples
        )
        return round(total_sq_err / len(samples), 4)

    def calculate_calibration_curve(
        self, model_id: Optional[str] = None, num_bins: int = 10
    ) -> List[CalibrationBucket]:
        """Bin predictions and calculate accuracy vs average confidence in each bucket."""
        samples = [r for r in self._outcomes if not model_id or r.model_id == model_id]
        if num_bins < 1:
            num_bins = 10

        bin_width = 1.0 / num_bins
        buckets: List[CalibrationBucket] = []

        for i in range(num_bins):
            min_c = i * bin_width
            max_c = (i + 1) * bin_width
            bucket_samples = [
                r
                for r in samples
                if (min_c <= r.predicted_confidence < max_c)
                or (i == num_bins - 1 and r.predicted_confidence == 1.0)
            ]
            count = len(bucket_samples)
            if count > 0:
                acc = sum(1 for r in bucket_samples if r.actual_success) / count
                avg_conf = sum(r.predicted_confidence for r in bucket_samples) / count
            else:
                acc = 0.0
                avg_conf = (min_c + max_c) / 2.0

            buckets.append(
                CalibrationBucket(
                    bucket_id=i,
                    min_conf=round(min_c, 3),
                    max_conf=round(max_c, 3),
                    count=count,
                    accuracy=round(acc, 4),
                    avg_confidence=round(avg_conf, 4),
                )
            )

        return buckets

    def calculate_expected_calibration_error(
        self, model_id: Optional[str] = None, num_bins: int = 10
    ) -> float:
        """Compute weighted average difference between confidence and accuracy across bins."""
        samples = [r for r in self._outcomes if not model_id or r.model_id == model_id]
        total_samples = len(samples)
        if total_samples == 0:
            return 0.0

        buckets = self.calculate_calibration_curve(model_id, num_bins)
        ece = sum(
            (b.count / total_samples) * abs(b.avg_confidence - b.accuracy)
            for b in buckets
            if b.count > 0
        )
        return round(ece, 4)

    def evaluate_calibration(
        self, model_id: str, ece_threshold: float = 0.10
    ) -> CalibrationAssessment:
        """Evaluate whether a model is well-calibrated according to ECE tolerance."""
        if not model_id:
            raise ValueError("model_id is required")

        samples = [r for r in self._outcomes if r.model_id == model_id]
        brier = self.calculate_brier_score(model_id)
        ece = self.calculate_expected_calibration_error(model_id)
        is_calibrated = (len(samples) >= 10) and (ece <= ece_threshold)

        return CalibrationAssessment(
            assessment_id=f"cal-{uuid.uuid4().hex[:8]}",
            model_id=model_id,
            total_samples=len(samples),
            brier_score=brier,
            expected_calibration_error=ece,
            is_well_calibrated=is_calibrated,
            calculated_at=datetime.now(timezone.utc).isoformat(),
        )

    def calibrate_confidence(self, model_id: str, raw_confidence: float) -> float:
        """Map raw confidence to empirically observed accuracy in its calibration bucket."""
        raw_conf = max(0.0, min(1.0, float(raw_confidence)))
        buckets = self.calculate_calibration_curve(model_id, num_bins=10)

        for b in buckets:
            if (b.min_conf <= raw_conf < b.max_conf) or (b.max_conf == 1.0 and raw_conf == 1.0):
                if b.count >= 5:
                    return b.accuracy
                else:
                    return raw_conf

        return raw_conf

    def get_calibration_report(self) -> Dict[str, Any]:
        """Aggregate summary of prediction logs and calibration metrics."""
        total = len(self._outcomes)
        models = sorted(list(set(r.model_id for r in self._outcomes)))
        brier = self.calculate_brier_score()
        ece = self.calculate_expected_calibration_error()

        return {
            "total_outcomes_logged": total,
            "monitored_models": models,
            "overall_brier_score": brier,
            "overall_ece": ece,
        }
