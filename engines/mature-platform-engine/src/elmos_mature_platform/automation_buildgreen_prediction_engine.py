"""Automation Buildgreen Prediction Engine (Batch 41 - Skill 1404).

Predicts CI/CD build green probability prior to execution using multi-factor
commit risk evaluation (churn, test ratio, dependency modifications, historical author rates),
enabling smart test selection, preflight gating, and queue prioritization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    BuildPredictionVerdict,
    BuildgreenPrediction,
    CommitRiskFactor,
)


class AutomationBuildgreenPredictionEngine:
    """Industrial engine for pre-build failure risk modeling and green build forecasting (B41)."""

    def __init__(self, default_green_threshold: float = 0.70):
        self.default_green_threshold = default_green_threshold
        self._predictions: Dict[str, BuildgreenPrediction] = {}

    def _calculate_verdict(self, green_prob: float) -> BuildPredictionVerdict:
        """Categorize continuous green probability into operational decision tiers."""
        if green_prob >= 0.90:
            return BuildPredictionVerdict.HIGH_CONFIDENCE_GREEN
        elif green_prob >= 0.70:
            return BuildPredictionVerdict.PROBABLE_GREEN
        elif green_prob >= 0.40:
            return BuildPredictionVerdict.RISKY_RED
        else:
            return BuildPredictionVerdict.HIGH_RISK_RED

    def predict_commit_build(
        self,
        commit_sha: str,
        branch: str,
        author: str,
        lines_changed: int,
        test_files_changed: int,
        dependency_files_changed: int,
        author_historical_pass_rate: float = 0.85,
    ) -> BuildgreenPrediction:
        """Evaluate commit metrics and compute composite buildgreen probability and risk factors."""
        if not commit_sha.strip():
            raise ValueError("commit_sha cannot be empty")
        if lines_changed < 0 or test_files_changed < 0 or dependency_files_changed < 0:
            raise ValueError("Change counts cannot be negative")

        risk_factors: List[CommitRiskFactor] = []

        # 1. Churn Factor
        churn_risk = min(1.0, lines_changed / 1000.0)
        risk_factors.append(
            CommitRiskFactor(
                factor_name="code_churn",
                weight=0.25,
                score=round(churn_risk, 3),
                detail=f"{lines_changed} lines modified",
            )
        )

        # 2. Test Ratio Factor (Low test coverage increases risk)
        test_ratio = test_files_changed / (test_files_changed + max(1, dependency_files_changed) + (lines_changed // 100))
        test_risk = max(0.0, 1.0 - min(1.0, test_ratio * 2.0))
        risk_factors.append(
            CommitRiskFactor(
                factor_name="test_absence",
                weight=0.25,
                score=round(test_risk, 3),
                detail=f"{test_files_changed} test files modified",
            )
        )

        # 3. Dependency modifications (high risk)
        dep_risk = min(1.0, dependency_files_changed * 0.4)
        risk_factors.append(
            CommitRiskFactor(
                factor_name="dependency_mutation",
                weight=0.30,
                score=round(dep_risk, 3),
                detail=f"{dependency_files_changed} lockfile/dependency descriptors changed",
            )
        )

        # 4. Author historical failure rate
        author_risk = max(0.0, 1.0 - min(1.0, author_historical_pass_rate))
        risk_factors.append(
            CommitRiskFactor(
                factor_name="author_historical_risk",
                weight=0.20,
                score=round(author_risk, 3),
                detail=f"Historical pass rate: {author_historical_pass_rate:.1%}",
            )
        )

        # Aggregate weighted risk score
        composite_risk = sum(f.weight * f.score for f in risk_factors)
        green_prob = round(max(0.05, min(0.98, 1.0 - composite_risk)), 4)
        verdict = self._calculate_verdict(green_prob)

        prediction_id = f"pred-{uuid.uuid4().hex[:8]}"
        prediction = BuildgreenPrediction(
            prediction_id=prediction_id,
            commit_sha=commit_sha,
            branch=branch,
            author=author,
            predicted_verdict=verdict,
            green_probability=green_prob,
            risk_factors=risk_factors,
            actual_build_passed=None,
            predicted_at=datetime.now(timezone.utc).isoformat(),
        )

        self._predictions[prediction_id] = prediction
        return prediction

    def record_actual_outcome(
        self,
        prediction_id: str,
        build_passed: bool,
    ) -> BuildgreenPrediction:
        """Record the actual build pass/fail ground truth to evaluate calibration."""
        prediction = self._predictions.get(prediction_id)
        if not prediction:
            raise ValueError(f"Prediction '{prediction_id}' not found")

        prediction.actual_build_passed = build_passed
        return prediction

    def get_model_calibration_metrics(self) -> Dict[str, Any]:
        """Compute calibration and predictive accuracy across completed builds."""
        evaluated = [p for p in self._predictions.values() if p.actual_build_passed is not None]
        if not evaluated:
            return {
                "evaluated_predictions_count": 0,
                "accuracy_pct": 0.0,
                "brier_score": 0.0,
                "true_positives": 0,
                "false_positives": 0,
                "true_negatives": 0,
                "false_negatives": 0,
            }

        tp = fp = tn = fn = 0
        brier_sum = 0.0

        for p in evaluated:
            actual_binary = 1.0 if p.actual_build_passed else 0.0
            brier_sum += (p.green_probability - actual_binary) ** 2

            pred_green = p.green_probability >= self.default_green_threshold
            if pred_green and p.actual_build_passed:
                tp += 1
            elif pred_green and not p.actual_build_passed:
                fp += 1
            elif not pred_green and not p.actual_build_passed:
                tn += 1
            else:
                fn += 1

        total = len(evaluated)
        accuracy = round(((tp + tn) / total) * 100.0, 2)
        brier_score = round(brier_sum / total, 4)

        return {
            "evaluated_predictions_count": total,
            "accuracy_pct": accuracy,
            "brier_score": brier_score,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        }

    def get_prediction(self, prediction_id: str) -> Optional[BuildgreenPrediction]:
        """Retrieve prediction by ID."""
        return self._predictions.get(prediction_id)

    def list_predictions(
        self,
        verdict: Optional[BuildPredictionVerdict] = None,
    ) -> List[BuildgreenPrediction]:
        """List predictions, optionally filtered by verdict tier."""
        if verdict:
            return [p for p in self._predictions.values() if p.predicted_verdict == verdict]
        return list(self._predictions.values())
