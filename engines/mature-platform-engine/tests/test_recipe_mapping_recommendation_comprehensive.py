"""Comprehensive unit tests for RecipeMappingRecommendationEngine (Batch 41 Skill 1398)."""

import unittest

from elmos_mature_platform.recipe_mapping_recommendation_engine import (
    RecipeMappingRecommendationEngine,
)
from elmos_mature_platform.types import (
    RecipeMappingTarget,
    RecipeMatchConfidence,
    RecipeCandidateRecommendation,
    RecipeRecommendationQuery,
)


class TestRecipeMappingRecommendationComprehensive(unittest.TestCase):
    """Test suite for transformation recipe matching, pattern confidence, and catalog governance."""

    def setUp(self) -> None:
        self.engine = RecipeMappingRecommendationEngine()

    def test_default_catalog_seeded(self) -> None:
        summary = self.engine.get_catalog_summary()
        self.assertGreaterEqual(summary["total_recipes"], 3)
        self.assertIn("framework_migration", summary["by_target"])

    def test_recommend_recipes_spring_match(self) -> None:
        query = RecipeRecommendationQuery(
            query_id="q-001",
            source_tech="spring-legacy",
            target_tech="springboot4",
            project_type="enterprise-banking",
            source_patterns=["applicationContext.xml", "<bean id="],
        )
        recommendations = self.engine.recommend_recipes(query)
        self.assertGreaterEqual(len(recommendations), 1)
        top = recommendations[0]
        self.assertEqual(top.recipe_id, "rec-spring-to-boot4")
        self.assertEqual(top.confidence, RecipeMatchConfidence.HIGH)
        self.assertGreaterEqual(top.match_score, 0.8)

    def test_recommend_recipes_hibernate_match(self) -> None:
        query = RecipeRecommendationQuery(
            query_id="q-002",
            source_tech="hibernate3",
            target_tech="jakarta-jpa3",
            project_type="backend",
            source_patterns=[".hbm.xml", "SessionFactory"],
        )
        recommendations = self.engine.recommend_recipes(query)
        self.assertGreaterEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].recipe_id, "rec-hibernate-to-jpa")

    def test_recommend_recipes_no_match(self) -> None:
        query = RecipeRecommendationQuery(
            query_id="q-none",
            source_tech="cobol-cics",
            target_tech="rust-actix",
            project_type="legacy-mainframe",
        )
        recommendations = self.engine.recommend_recipes(query)
        self.assertEqual(len(recommendations), 0)

    def test_register_custom_recipe_and_query(self) -> None:
        custom_recipe = RecipeCandidateRecommendation(
            recipe_id="rec-python2-to-3",
            name="Python 2 Print / Unicode to Modern Python 3.12 Syntax",
            target=RecipeMappingTarget.FRAMEWORK_MIGRATION,
            confidence=RecipeMatchConfidence.HIGH,
            match_score=0.90,
            applicable_patterns=["print ", "basestring", "unicode(", "xrange"],
            estimated_automation_pct=95.0,
        )
        rid = self.engine.register_recipe(
            recipe=custom_recipe,
            supported_sources=["python2.7"],
            supported_targets=["python3.12"],
        )
        self.assertEqual(rid, "rec-python2-to-3")

        query = RecipeRecommendationQuery(
            query_id="q-py",
            source_tech="python2.7",
            target_tech="python3.12",
            project_type="data-science",
            source_patterns=["print ", "xrange"],
        )
        matches = self.engine.recommend_recipes(query)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].recipe_id, "rec-python2-to-3")

    def test_list_recipes_by_target(self) -> None:
        orm_recipes = self.engine.list_recipes_by_target(RecipeMappingTarget.ORM_CONVERSION)
        self.assertEqual(len(orm_recipes), 1)
        self.assertEqual(orm_recipes[0].recipe_id, "rec-hibernate-to-jpa")

    def test_get_catalog_summary(self) -> None:
        summary = self.engine.get_catalog_summary()
        self.assertGreater(summary["total_recipes"], 0)
        self.assertGreater(summary["avg_automation_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
