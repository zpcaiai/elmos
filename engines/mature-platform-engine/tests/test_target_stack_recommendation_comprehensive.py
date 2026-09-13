"""Comprehensive test suite for TargetStackRecommendationEngine (B41 - Skill 1418)."""

import unittest

from elmos_mature_platform.target_stack_recommendation_engine import (
    TargetStackRecommendationEngine,
)
from elmos_mature_platform.types import (
    ModernizationStrategy,
    StackArchitectureTier,
)


class TestTargetStackRecommendationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = TargetStackRecommendationEngine()

    def test_recommend_known_java_struts_route(self):
        rec = self.engine.recommend_target_stack(
            project_name="legacy-banking-portal",
            source_stack=["java", "struts", "oracle"],
            code_size_kloc=80.0,
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec.project_name, "legacy-banking-portal")
        self.assertEqual(rec.architecture_tier, StackArchitectureTier.MODULAR_MONOLITH)
        self.assertEqual(rec.strategy, ModernizationStrategy.REFACTOR)
        self.assertIsNotNone(rec.recommended_target)
        self.assertEqual(rec.recommended_target.recommended_target_framework, "spring_boot_3_postgresql")
        self.assertGreater(rec.recommended_target.confidence_score, 0.8)
        self.assertGreater(rec.estimated_effort_months, 0.0)

    def test_recommend_known_dotnet_wcf_route(self):
        rec = self.engine.recommend_target_stack(
            project_name="legacy-wcf-service",
            source_stack=["dotnet", "framework", "wcf", "sqlserver"],
            code_size_kloc=120.0,
        )
        self.assertEqual(rec.strategy, ModernizationStrategy.REPLATFORM)
        self.assertEqual(rec.recommended_target.recommended_target_framework, "dotnet_8_grpc_sqlserver")
        self.assertIn("aspnet_core_webapi_sqlserver", rec.recommended_target.alternatives)

    def test_recommend_python_django_route(self):
        rec = self.engine.recommend_target_stack(
            project_name="legacy-django-app",
            source_stack=["python", "django", "mysql"],
            code_size_kloc=30.0,
        )
        self.assertEqual(rec.architecture_tier, StackArchitectureTier.MICROSERVICES)
        self.assertEqual(rec.recommended_target.recommended_target_framework, "fastapi_asyncpg_postgresql")

    def test_recommend_unknown_source_stack(self):
        rec = self.engine.recommend_target_stack(
            project_name="exotic-cobol-app",
            source_stack=["cobol", "cics", "db2"],
            code_size_kloc=50.0,
        )
        self.assertIsNotNone(rec)
        self.assertIn("modern_cobol_standard", rec.recommended_target.recommended_target_framework)
        self.assertEqual(rec.recommended_target.confidence_score, 0.75)

    def test_calculate_stack_feasibility_same_language(self):
        score = self.engine.calculate_stack_feasibility("python_flask", "python_fastapi")
        self.assertGreaterEqual(score.total_score, 70.0)
        self.assertEqual(score.syntactic_overlap_pct, 85.0)

    def test_calculate_stack_feasibility_cross_language(self):
        score = self.engine.calculate_stack_feasibility("php_legacy", "go_standard")
        self.assertLess(score.total_score, 70.0)
        self.assertEqual(score.syntactic_overlap_pct, 55.0)

    def test_compare_candidates_ranks_descending(self):
        source = ["java", "struts", "oracle"]
        candidates = [
            "spring_boot_3_postgresql",
            "go_gin_postgresql",
            "quarkus_postgresql",
        ]
        ranked = self.engine.compare_candidates(source, candidates)
        self.assertEqual(len(ranked), 3)
        # Verify descending order
        self.assertGreaterEqual(ranked[0].total_score, ranked[1].total_score)
        self.assertGreaterEqual(ranked[1].total_score, ranked[2].total_score)

    def test_large_code_base_risk_factor(self):
        rec = self.engine.recommend_target_stack(
            project_name="massive-enterprise",
            source_stack=["java", "struts", "oracle"],
            code_size_kloc=350.0,
        )
        self.assertTrue(any("Large code base" in r for r in rec.risk_factors))

    def test_get_recommendation_and_list(self):
        rec = self.engine.recommend_target_stack("app-1", ["java", "struts", "oracle"])
        fetched = self.engine.get_recommendation(rec.recommendation_id)
        self.assertIsNotNone(fetched)
        all_recs = self.engine.list_recommendations()
        self.assertEqual(len(all_recs), 1)


if __name__ == "__main__":
    unittest.main()
