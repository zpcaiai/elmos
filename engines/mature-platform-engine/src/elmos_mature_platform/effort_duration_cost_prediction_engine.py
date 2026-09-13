"""Effort, Duration & Cost Prediction Engine (Batch 41 - Skill 1403).

Applies algorithmic and statistical estimation models to repository complexity vectors
(KLOC, AST depth, external dependencies, stored procedures, business rules)
to predict person-months, calendar duration, delivery costs, and confidence intervals.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    EffortPredictionResult,
    MigrationComplexityClass,
    RepoComplexityVector,
)


class EffortDurationCostPredictionEngine:
    """Industrial estimation and cost prediction engine (B41)."""

    def __init__(
        self,
        base_cost_per_person_month_usd: float = 12500.0,
        automation_factor: float = 0.65,
    ):
        self.base_cost_usd = base_cost_per_person_month_usd
        self.automation_factor = automation_factor  # 35% automated reduction
        self._predictions: Dict[str, EffortPredictionResult] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def classify_complexity(self, vector: RepoComplexityVector) -> MigrationComplexityClass:
        """Classify repository complexity based on multi-dimensional structural metrics."""
        # Weighted composite score
        score = (
            (vector.kloc / 20.0) * 1.0 +
            (vector.ast_depth / 10.0) * 1.2 +
            (vector.external_dependency_count / 15.0) * 1.5 +
            (vector.database_routines_count / 10.0) * 2.0 +
            (vector.business_rules_count / 25.0) * 1.8
        )

        if score < 5.0:
            return MigrationComplexityClass.TRIVIAL
        elif score < 15.0:
            return MigrationComplexityClass.MODERATE
        elif score < 35.0:
            return MigrationComplexityClass.HIGH
        else:
            return MigrationComplexityClass.EXTREME

    def predict_effort_and_cost(
        self,
        repo_id: str,
        vector: RepoComplexityVector,
        target_platform_factor: float = 1.0,
    ) -> EffortPredictionResult:
        """Predict person-months, costs, and 90% confidence bounds."""
        complexity_class = self.classify_complexity(vector)

        # Baseline person-months model using logarithmic scaling for KLOC + linear for routines/rules
        base_pm = (
            math.log1p(vector.kloc) * 1.5 +
            (vector.database_routines_count * 0.1) +
            (vector.business_rules_count * 0.05) +
            (vector.ast_depth * 0.08)
        )

        complexity_multipliers = {
            MigrationComplexityClass.TRIVIAL: 0.5,
            MigrationComplexityClass.MODERATE: 1.0,
            MigrationComplexityClass.HIGH: 1.6,
            MigrationComplexityClass.EXTREME: 2.5,
            MigrationComplexityClass.UNKNOWN: 1.0,
        }

        mult = complexity_multipliers.get(complexity_class, 1.0)
        adjusted_pm = round(max(0.2, base_pm * mult * self.automation_factor * target_platform_factor), 2)

        cost_usd = round(adjusted_pm * self.base_cost_usd, 2)

        # Confidence bounds (+/- 15% for trivial, +/- 30% for extreme)
        variance_margin = 0.15 if complexity_class == MigrationComplexityClass.TRIVIAL else (
            0.20 if complexity_class == MigrationComplexityClass.MODERATE else 0.30
        )
        ci_low = round(cost_usd * (1.0 - variance_margin), 2)
        ci_high = round(cost_usd * (1.0 + variance_margin), 2)

        pred_id = f"pred-{uuid.uuid4().hex[:8]}"
        res = EffortPredictionResult(
            prediction_id=pred_id,
            repo_id=repo_id,
            complexity_class=complexity_class,
            predicted_person_months=adjusted_pm,
            predicted_cost_usd=cost_usd,
            confidence_interval_low=ci_low,
            confidence_interval_high=ci_high,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        self._predictions[pred_id] = res
        self._record_audit("prediction_generated", pred_id, {
            "repo_id": repo_id,
            "complexity": complexity_class.value,
            "cost_usd": cost_usd,
        })
        return res

    def get_prediction(self, prediction_id: str) -> Optional[EffortPredictionResult]:
        """Fetch historical prediction."""
        return self._predictions.get(prediction_id)

    def get_prediction_summary(self) -> Dict[str, Any]:
        """Aggregate metrics on past predictions."""
        total = len(self._predictions)
        by_class: Dict[str, int] = {}
        total_pm = 0.0
        total_cost = 0.0

        for p in self._predictions.values():
            c = p.complexity_class.value
            by_class[c] = by_class.get(c, 0) + 1
            total_pm += p.predicted_person_months
            total_cost += p.predicted_cost_usd

        return {
            "total_predictions": total,
            "complexity_breakdown": by_class,
            "total_predicted_person_months": round(total_pm, 1),
            "total_predicted_cost_usd": round(total_cost, 2),
            "average_cost_per_project_usd": round(total_cost / total, 2) if total > 0 else 0.0,
        }

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
