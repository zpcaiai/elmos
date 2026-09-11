from __future__ import annotations
from typing import List, Dict, Any
from .models import MigrationPlan, SpringProjectProfile, SpringVersion, MigrationRule, RiskLevel
from .migration_rules import RULE_CATALOG

class MigrationPlanGenerator:
    def generate_plan(self, profile: SpringProjectProfile, target_version: SpringVersion) -> MigrationPlan:
        rules = list(RULE_CATALOG.values())[:10]
        return MigrationPlan(
            plan_id="plan_123",
            source_version=profile.version,
            target_version=target_version,
            rules=rules,
            estimated_changes=len(rules),
            risk_summary={RiskLevel.LOW: len(rules)}
        )

    def estimate_effort(self, plan: MigrationPlan) -> float:
        return plan.estimated_changes * 0.5

    def assess_risk(self, plan: MigrationPlan) -> Dict[RiskLevel, int]:
        return plan.risk_summary

    def suggest_migration_order(self, plan: MigrationPlan) -> List[MigrationRule]:
        return plan.rules

    def identify_blocking_issues(self, plan: MigrationPlan) -> List[str]:
        return []

    def generate_migration_waves(self, plan: MigrationPlan, wave_size: int) -> List[List[MigrationRule]]:
        return [plan.rules[i:i + wave_size] for i in range(0, len(plan.rules), wave_size)]
