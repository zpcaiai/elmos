"""Human Expert Cost Engine (Batch 44 - Skill 1463).

Tracks human review, domain specialist, architect, and expert engineering hours,
measuring hourly cost rates, billable vs non-billable ratios, and task-level manual intervention expense.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    ExpertRoleTier,
    HumanCostSummary,
    HumanExpertEngagement,
)


class HumanExpertCostEngine:
    """Human engineering time and expert specialist intervention cost engine."""

    def __init__(self) -> None:
        self._engagements: Dict[str, HumanExpertEngagement] = {}

    def register_engagement(self, engagement: HumanExpertEngagement) -> str:
        """Register an expert engineer engagement for a project."""
        if not engagement.project_id:
            raise ValueError("project_id is required")
        if engagement.hourly_rate_usd < 0:
            raise ValueError("hourly_rate_usd cannot be negative")

        if not engagement.engagement_id:
            engagement.engagement_id = f"eng-{uuid.uuid4().hex[:8]}"

        if not engagement.assigned_at:
            engagement.assigned_at = datetime.now(timezone.utc).isoformat()

        self._engagements[engagement.engagement_id] = engagement
        return engagement.engagement_id

    def log_hours(
        self,
        engagement_id: str,
        hours: float,
        is_billable: bool = True,
        task_id: str = "",
    ) -> float:
        """Log expert hours spent on modernization or review tasks."""
        if hours <= 0:
            raise ValueError("hours must be greater than zero")

        eng = self._engagements.get(engagement_id)
        if not eng:
            raise ValueError(f"Engagement not found: {engagement_id}")

        if not eng.active:
            raise ValueError(f"Engagement {engagement_id} is closed; cannot log hours")

        eng.hours_logged += hours
        if is_billable:
            eng.billable_hours += hours

        if task_id and task_id not in eng.tasks_addressed:
            eng.tasks_addressed.append(task_id)

        return round(eng.hours_logged, 2)

    def calculate_engagement_cost(self, engagement_id: str) -> Dict[str, float]:
        """Calculate total and billable cost for a specific engagement."""
        eng = self._engagements.get(engagement_id)
        if not eng:
            raise ValueError(f"Engagement not found: {engagement_id}")

        total_cost = eng.hours_logged * eng.hourly_rate_usd
        billable_cost = eng.billable_hours * eng.hourly_rate_usd

        return {
            "hours_logged": round(eng.hours_logged, 2),
            "billable_hours": round(eng.billable_hours, 2),
            "hourly_rate_usd": eng.hourly_rate_usd,
            "total_cost_usd": round(total_cost, 2),
            "billable_cost_usd": round(billable_cost, 2),
        }

    def get_cost_by_role(self, role_tier: ExpertRoleTier) -> float:
        """Calculate total incurred cost across all engagements for a specific role tier."""
        matching = [e for e in self._engagements.values() if e.role_tier == role_tier]
        cost = sum(e.hours_logged * e.hourly_rate_usd for e in matching)
        return round(cost, 2)

    def get_total_human_cost(self) -> HumanCostSummary:
        """Calculate portfolio-level human engineering cost and hours breakdown."""
        total_hours = sum(e.hours_logged for e in self._engagements.values())
        total_billable = sum(e.billable_hours for e in self._engagements.values())
        total_cost = sum(e.hours_logged * e.hourly_rate_usd for e in self._engagements.values())

        by_role: Dict[str, float] = {tier.value: 0.0 for tier in ExpertRoleTier}
        for tier in ExpertRoleTier:
            by_role[tier.value] = self.get_cost_by_role(tier)

        active_count = sum(1 for e in self._engagements.values() if e.active)

        return HumanCostSummary(
            total_hours=round(total_hours, 2),
            total_billable_hours=round(total_billable, 2),
            total_cost_usd=round(total_cost, 2),
            by_role=by_role,
            active_engagements_count=active_count,
        )

    def get_engagement(self, engagement_id: str) -> Optional[HumanExpertEngagement]:
        """Retrieve engagement record."""
        return self._engagements.get(engagement_id)

    def get_human_expert_report(self) -> Dict[str, Any]:
        """Generate human engineering utilization and cost metrics."""
        summary = self.get_total_human_cost()
        billable_ratio = (
            (summary.total_billable_hours / summary.total_hours * 100.0)
            if summary.total_hours > 0
            else 0.0
        )

        return {
            "total_engagements": len(self._engagements),
            "active_engagements": summary.active_engagements_count,
            "total_hours_logged": summary.total_hours,
            "total_billable_hours": summary.total_billable_hours,
            "billable_ratio_pct": round(billable_ratio, 2),
            "total_human_cost_usd": summary.total_cost_usd,
            "cost_by_role_tier": summary.by_role,
        }
