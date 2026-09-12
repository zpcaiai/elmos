"""Recipe and Mapping Recommendation Engine - Batch 41 Skill 1398.

Indexes transformation recipes, matches modernization queries against known code patterns,
computes confidence scores, and recommends optimal AST/semantic refactoring recipes.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
import uuid

from .types import (
    RecipeMappingTarget,
    RecipeMatchConfidence,
    RecipeCandidateRecommendation,
    RecipeRecommendationQuery,
)


class RecipeMappingRecommendationEngine:
    """Recommends relevant transformation recipes based on tech stack, project type, and code patterns."""

    def __init__(self) -> None:
        self._recipes: Dict[str, RecipeCandidateRecommendation] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._seed_default_recipes()

    def _seed_default_recipes(self) -> None:
        """Seed industrial default transformation recipes."""
        self.register_recipe(
            recipe=RecipeCandidateRecommendation(
                recipe_id="rec-spring-to-boot4",
                name="Spring Framework Legacy XML to Spring Boot 4 AutoConfiguration",
                target=RecipeMappingTarget.FRAMEWORK_MIGRATION,
                confidence=RecipeMatchConfidence.HIGH,
                match_score=0.95,
                applicable_patterns=["applicationContext.xml", "<bean id=", "@Autowired", "@Repository"],
                estimated_automation_pct=92.0,
            ),
            supported_sources=["java-spring-xml", "spring-legacy"],
            supported_targets=["springboot4", "spring6"],
        )
        self.register_recipe(
            recipe=RecipeCandidateRecommendation(
                recipe_id="rec-hibernate-to-jpa",
                name="Hibernate hbm.xml Mappings to Modern Jakarta Persistence Annotations",
                target=RecipeMappingTarget.ORM_CONVERSION,
                confidence=RecipeMatchConfidence.HIGH,
                match_score=0.90,
                applicable_patterns=[".hbm.xml", "hibernate.cfg.xml", "SessionFactory", "session.createCriteria"],
                estimated_automation_pct=88.0,
            ),
            supported_sources=["hibernate3", "hibernate4"],
            supported_targets=["jakarta-jpa3", "spring-data-jpa"],
        )
        self.register_recipe(
            recipe=RecipeCandidateRecommendation(
                recipe_id="rec-struts-to-springmvc",
                name="Struts 1/2 Action to Spring MVC RestController",
                target=RecipeMappingTarget.API_TRANSFORMATION,
                confidence=RecipeMatchConfidence.MEDIUM,
                match_score=0.78,
                applicable_patterns=["ActionForm", "ActionMapping", "struts.xml", "ActionForward"],
                estimated_automation_pct=75.0,
            ),
            supported_sources=["struts1", "struts2"],
            supported_targets=["spring-mvc", "spring-webflux"],
        )

    def register_recipe(
        self,
        recipe: RecipeCandidateRecommendation,
        supported_sources: List[str],
        supported_targets: List[str],
    ) -> str:
        """Register a transformation recipe into the recommendation catalog."""
        if not recipe.recipe_id or not recipe.name:
            raise ValueError("recipe_id and name must not be empty")

        self._recipes[recipe.recipe_id] = recipe
        self._metadata[recipe.recipe_id] = {
            "sources": [s.lower() for s in supported_sources],
            "targets": [t.lower() for t in supported_targets],
        }
        return recipe.recipe_id

    def recommend_recipes(self, query: RecipeRecommendationQuery) -> List[RecipeCandidateRecommendation]:
        """Match query against catalog and return ranked recipe candidates."""
        if not query.source_tech or not query.target_tech:
            raise ValueError("source_tech and target_tech must not be empty")

        q_src = query.source_tech.lower()
        q_tgt = query.target_tech.lower()
        q_patterns = set(query.source_patterns)

        recommendations: List[RecipeCandidateRecommendation] = []

        for r_id, recipe in self._recipes.items():
            meta = self._metadata[r_id]
            src_match = any(q_src in s or s in q_src for s in meta["sources"])
            tgt_match = any(q_tgt in t or t in q_tgt for t in meta["targets"])

            if src_match and tgt_match:
                # Calculate pattern overlap
                if q_patterns and recipe.applicable_patterns:
                    overlap = q_patterns.intersection(set(recipe.applicable_patterns))
                    pattern_score = len(overlap) / len(q_patterns)
                    combined_score = round(0.5 * recipe.match_score + 0.5 * pattern_score, 2)
                else:
                    combined_score = recipe.match_score

                # Adjust confidence tier
                if combined_score >= 0.85:
                    conf = RecipeMatchConfidence.HIGH
                elif combined_score >= 0.60:
                    conf = RecipeMatchConfidence.MEDIUM
                else:
                    conf = RecipeMatchConfidence.LOW

                candidate = RecipeCandidateRecommendation(
                    recipe_id=recipe.recipe_id,
                    name=recipe.name,
                    target=recipe.target,
                    confidence=conf,
                    match_score=combined_score,
                    applicable_patterns=recipe.applicable_patterns,
                    estimated_automation_pct=recipe.estimated_automation_pct,
                )
                recommendations.append(candidate)

        recommendations.sort(key=lambda c: c.match_score, reverse=True)
        return recommendations

    def get_recipe(self, recipe_id: str) -> Optional[RecipeCandidateRecommendation]:
        """Retrieve recipe by ID."""
        return self._recipes.get(recipe_id)

    def list_recipes_by_target(self, target: RecipeMappingTarget) -> List[RecipeCandidateRecommendation]:
        """List recipes matching target migration domain."""
        return [r for r in self._recipes.values() if r.target == target]

    def get_catalog_summary(self) -> Dict[str, Any]:
        """Generate summary of recommendation catalog."""
        total = len(self._recipes)
        by_target = {t.value: 0 for t in RecipeMappingTarget}
        by_conf = {c.value: 0 for c in RecipeMatchConfidence}
        total_auto = sum(r.estimated_automation_pct for r in self._recipes.values())

        for r in self._recipes.values():
            by_target[r.target.value] = by_target.get(r.target.value, 0) + 1
            by_conf[r.confidence.value] = by_conf.get(r.confidence.value, 0) + 1

        return {
            "total_recipes": total,
            "by_target": by_target,
            "by_confidence": by_conf,
            "avg_automation_pct": round(total_auto / total, 2) if total > 0 else 0.0,
        }
