"""Target Stack Recommendation Engine (Batch 41 - Skill 1418).

Analyzes legacy or modern project technology stacks and generates target stack
recommendations, feasibility scores, modernization strategies, risk registers,
and effort estimates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    ComprehensiveStackRecommendation,
    ModernizationStrategy,
    StackArchitectureTier,
    StackFeasibilityScore,
    TargetStackRecommendation,
)

# Standard target routes with baseline feasibility heuristics
KNOWN_ROUTES: Dict[str, Dict[str, Any]] = {
    "java_struts_oracle": {
        "primary_target": "spring_boot_3_postgresql",
        "syntactic_overlap": 78.0,
        "library_parity": 85.0,
        "complexity_discount": 0.85,
        "alternatives": ["quarkus_postgresql", "micronaut_postgresql"],
        "tier": StackArchitectureTier.MODULAR_MONOLITH,
        "strategy": ModernizationStrategy.REFACTOR,
    },
    "dotnet_framework_wcf_sqlserver": {
        "primary_target": "dotnet_8_grpc_sqlserver",
        "syntactic_overlap": 92.0,
        "library_parity": 88.0,
        "complexity_discount": 0.90,
        "alternatives": ["aspnet_core_webapi_sqlserver", "go_service_sqlserver"],
        "tier": StackArchitectureTier.MODULAR_MONOLITH,
        "strategy": ModernizationStrategy.REPLATFORM,
    },
    "python_django_mysql": {
        "primary_target": "fastapi_asyncpg_postgresql",
        "syntactic_overlap": 82.0,
        "library_parity": 80.0,
        "complexity_discount": 0.80,
        "alternatives": ["django_4_postgresql", "go_fiber_postgresql"],
        "tier": StackArchitectureTier.MICROSERVICES,
        "strategy": ModernizationStrategy.REFACTOR,
    },
    "php_laravel_mysql": {
        "primary_target": "laravel_11_mysql",
        "syntactic_overlap": 95.0,
        "library_parity": 92.0,
        "complexity_discount": 0.95,
        "alternatives": ["symfony_7_mysql", "go_echo_mysql"],
        "tier": StackArchitectureTier.MODULAR_MONOLITH,
        "strategy": ModernizationStrategy.REPLATFORM,
    },
}


class TargetStackRecommendationEngine:
    """Industrial engine for automated target stack modernization recommendations (B41)."""

    def __init__(self):
        self._recommendations: Dict[str, ComprehensiveStackRecommendation] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def calculate_stack_feasibility(
        self,
        source_tech: str,
        target_tech: str,
    ) -> StackFeasibilityScore:
        """Calculate feasibility score based on syntax overlap and library parity."""
        score_id = f"feas-{uuid.uuid4().hex[:6]}"
        s_key = source_tech.lower().replace(" ", "_")
        route_meta = KNOWN_ROUTES.get(s_key, {})

        if route_meta and target_tech == route_meta["primary_target"]:
            syn = route_meta["syntactic_overlap"]
            lib = route_meta["library_parity"]
            disc = route_meta["complexity_discount"]
        elif source_tech.split("_")[0] == target_tech.split("_")[0]:
            # Same language family
            syn = 85.0
            lib = 80.0
            disc = 0.90
        else:
            # Cross language migration
            syn = 55.0
            lib = 60.0
            disc = 0.70

        total = round((syn * 0.5 + lib * 0.5) * disc, 2)

        return StackFeasibilityScore(
            score_id=score_id,
            source_tech=source_tech,
            target_tech=target_tech,
            syntactic_overlap_pct=syn,
            library_parity_pct=lib,
            complexity_discount_factor=disc,
            total_score=total,
        )

    def recommend_target_stack(
        self,
        project_name: str,
        source_stack: List[str],
        preferred_target: Optional[str] = None,
        code_size_kloc: float = 50.0,
    ) -> ComprehensiveStackRecommendation:
        """Generate comprehensive stack recommendation for a given project."""
        norm_source = "_".join(s.lower().strip() for s in source_stack)
        route_meta = KNOWN_ROUTES.get(norm_source)

        if route_meta:
            primary_target = preferred_target or route_meta["primary_target"]
            alts = route_meta["alternatives"]
            tier = route_meta["tier"]
            strat = route_meta["strategy"]
            conf = 0.92
        else:
            primary_target = preferred_target or f"modern_{source_stack[0]}_standard"
            alts = [f"cloud_native_{source_stack[0]}"]
            tier = StackArchitectureTier.MODULAR_MONOLITH
            strat = ModernizationStrategy.REFACTOR
            conf = 0.75

        feasibility = self.calculate_stack_feasibility(norm_source, primary_target)
        effort = self.estimate_effort_months(strat, code_size_kloc, feasibility.total_score)

        target_rec = TargetStackRecommendation(
            recommendation_id=f"rec-{uuid.uuid4().hex[:6]}",
            source_framework=source_stack[0] if source_stack else "unknown",
            recommended_target_framework=primary_target,
            confidence_score=conf,
            rationale=f"High syntactic overlap ({feasibility.syntactic_overlap_pct}%) and library parity ({feasibility.library_parity_pct}%)",
            alternatives=alts,
        )

        risk_factors: List[str] = []
        if feasibility.total_score < 70.0:
            risk_factors.append("Cross-paradigm semantic divergence requires comprehensive regression harness")
        if code_size_kloc > 200.0:
            risk_factors.append("Large code base (>200 KLOC) necessitates phased wave-based cutover")

        comp_rec = ComprehensiveStackRecommendation(
            recommendation_id=f"comp-rec-{uuid.uuid4().hex[:8]}",
            project_name=project_name,
            source_stack=source_stack,
            recommended_target=target_rec,
            architecture_tier=tier,
            strategy=strat,
            estimated_effort_months=round(effort, 1),
            risk_factors=risk_factors,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        self._recommendations[comp_rec.recommendation_id] = comp_rec
        self._record_audit("recommendation_generated", comp_rec.recommendation_id, {
            "project": project_name,
            "target": primary_target,
            "effort": effort,
        })
        return comp_rec

    def compare_candidates(
        self,
        source_stack: List[str],
        candidates: List[str],
    ) -> List[StackFeasibilityScore]:
        """Rank multiple target stack options by feasibility score descending."""
        norm_source = "_".join(s.lower().strip() for s in source_stack)
        scores = [self.calculate_stack_feasibility(norm_source, c) for c in candidates]
        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores

    def estimate_effort_months(
        self,
        strategy: ModernizationStrategy,
        code_size_kloc: float,
        feasibility_score: float,
    ) -> float:
        """Estimate calendar delivery duration in months."""
        base_rate_kloc_per_month = 25.0  # 25 KLOC/month automated
        strategy_multipliers = {
            ModernizationStrategy.REHOST: 0.3,
            ModernizationStrategy.REPLATFORM: 0.6,
            ModernizationStrategy.REFACTOR: 1.0,
            ModernizationStrategy.REARCHITECT: 1.8,
            ModernizationStrategy.RETIRE: 0.1,
        }
        mult = strategy_multipliers.get(strategy, 1.0)
        feas_discount = max(0.5, (100.0 - feasibility_score) / 100.0 + 0.5)
        raw_months = (code_size_kloc / base_rate_kloc_per_month) * mult * feas_discount
        return max(0.5, raw_months)

    def get_recommendation(self, recommendation_id: str) -> Optional[ComprehensiveStackRecommendation]:
        """Fetch recommendation by ID."""
        return self._recommendations.get(recommendation_id)

    def list_recommendations(self) -> List[ComprehensiveStackRecommendation]:
        """Return all historical recommendations."""
        return list(self._recommendations.values())

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
