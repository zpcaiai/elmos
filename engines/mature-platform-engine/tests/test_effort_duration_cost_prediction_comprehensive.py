"""Comprehensive test suite for EffortDurationCostPredictionEngine (B41 - Skill 1403)."""

import unittest

from elmos_mature_platform.effort_duration_cost_prediction_engine import (
    EffortDurationCostPredictionEngine,
)
from elmos_mature_platform.types import (
    MigrationComplexityClass,
    RepoComplexityVector,
)


class TestEffortDurationCostPredictionComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = EffortDurationCostPredictionEngine(
            base_cost_per_person_month_usd=12000.0,
            automation_factor=0.6,
        )

    def test_classify_trivial_complexity(self):
        v = RepoComplexityVector(
            vector_id="v-triv",
            kloc=5.0,
            ast_depth=3,
            external_dependency_count=2,
            database_routines_count=0,
            business_rules_count=2,
        )
        c = self.engine.classify_complexity(v)
        self.assertEqual(c, MigrationComplexityClass.TRIVIAL)

    def test_classify_moderate_complexity(self):
        v = RepoComplexityVector(
            vector_id="v-mod",
            kloc=45.0,
            ast_depth=8,
            external_dependency_count=12,
            database_routines_count=5,
            business_rules_count=20,
        )
        c = self.engine.classify_complexity(v)
        self.assertEqual(c, MigrationComplexityClass.MODERATE)

    def test_classify_extreme_complexity(self):
        v = RepoComplexityVector(
            vector_id="v-ext",
            kloc=350.0,
            ast_depth=25,
            external_dependency_count=80,
            database_routines_count=150,
            business_rules_count=300,
        )
        c = self.engine.classify_complexity(v)
        self.assertEqual(c, MigrationComplexityClass.EXTREME)

    def test_predict_effort_and_cost_calculation(self):
        v = RepoComplexityVector(
            vector_id="v-pred",
            kloc=50.0,
            ast_depth=10,
            external_dependency_count=15,
            database_routines_count=10,
            business_rules_count=25,
        )
        res = self.engine.predict_effort_and_cost("repo-enterprise-billing", v)
        self.assertIsNotNone(res)
        self.assertEqual(res.repo_id, "repo-enterprise-billing")
        self.assertGreater(res.predicted_person_months, 0.0)
        self.assertGreater(res.predicted_cost_usd, 0.0)
        # Verify confidence interval order
        self.assertLess(res.confidence_interval_low, res.predicted_cost_usd)
        self.assertGreater(res.confidence_interval_high, res.predicted_cost_usd)

    def test_target_platform_factor_scales_effort(self):
        v = RepoComplexityVector("v-scale", 20.0, 5, 5, 2, 5)
        res_standard = self.engine.predict_effort_and_cost("r1", v, target_platform_factor=1.0)
        res_complex = self.engine.predict_effort_and_cost("r2", v, target_platform_factor=1.5)
        self.assertGreater(res_complex.predicted_person_months, res_standard.predicted_person_months)
        self.assertGreater(res_complex.predicted_cost_usd, res_standard.predicted_cost_usd)

    def test_prediction_summary_dashboard(self):
        v1 = RepoComplexityVector("v1", 10.0, 4, 2, 0, 2)
        v2 = RepoComplexityVector("v2", 100.0, 15, 30, 20, 50)
        self.engine.predict_effort_and_cost("r1", v1)
        self.engine.predict_effort_and_cost("r2", v2)

        summary = self.engine.get_prediction_summary()
        self.assertEqual(summary["total_predictions"], 2)
        self.assertGreater(summary["total_predicted_cost_usd"], 0.0)
        self.assertIn("trivial", summary["complexity_breakdown"])


if __name__ == "__main__":
    unittest.main()
