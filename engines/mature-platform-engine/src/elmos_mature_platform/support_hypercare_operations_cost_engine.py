"""Support and Hypercare Operations Cost Engine (Batch 44 - Skill 1464).

Models post-cutover stabilization, 24x7 mission-critical warranty support,
incident escalation economics, and professional services hypercare operations cost.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    HypercarePhase,
    HypercareProjectRecord,
    SupportOperationsCostSummary,
)


class SupportHypercareOperationsCostEngine:
    """Operations support warranty and hypercare cost modeling engine."""

    def __init__(self) -> None:
        self._projects: Dict[str, HypercareProjectRecord] = {}

    def register_project(self, record: HypercareProjectRecord) -> str:
        """Register a modernization project into hypercare warranty support."""
        if record.hourly_rate_usd < 0:
            raise ValueError("hourly_rate_usd cannot be negative")

        if record.hypercare_duration_days <= 0:
            raise ValueError("hypercare_duration_days must be positive")

        if not record.record_id:
            record.record_id = f"hyp-{uuid.uuid4().hex[:8]}"

        if not record.started_at:
            record.started_at = datetime.now(timezone.utc).isoformat()

        record.total_cost_usd = round(record.hours_logged * record.hourly_rate_usd, 2)
        self._projects[record.record_id] = record
        return record.record_id

    def transition_phase(
        self, record_id: str, new_phase: HypercarePhase
    ) -> HypercareProjectRecord:
        """Transition hypercare project to the next operational phase."""
        record = self._projects.get(record_id)
        if not record:
            raise ValueError(f"Hypercare record not found: {record_id}")

        record.phase = new_phase
        if new_phase == HypercarePhase.COMPLETED and not record.concluded_at:
            record.concluded_at = datetime.now(timezone.utc).isoformat()

        return record

    def log_support_hours(
        self, record_id: str, hours: float, escalations: int = 0
    ) -> HypercareProjectRecord:
        """Log active engineering support hours and incident escalations."""
        if hours < 0:
            raise ValueError("hours cannot be negative")
        if escalations < 0:
            raise ValueError("escalations cannot be negative")

        record = self._projects.get(record_id)
        if not record:
            raise ValueError(f"Hypercare record not found: {record_id}")

        if record.phase == HypercarePhase.COMPLETED:
            raise ValueError(f"Project {record_id} hypercare has concluded; cannot log hours")

        record.hours_logged += hours
        record.incident_escalation_count += escalations
        record.total_cost_usd = round(record.hours_logged * record.hourly_rate_usd, 2)
        return record

    def conclude_hypercare(self, record_id: str) -> HypercareProjectRecord:
        """Formally conclude hypercare and transition project to standard support."""
        return self.transition_phase(record_id, HypercarePhase.COMPLETED)

    def get_project(self, record_id: str) -> Optional[HypercareProjectRecord]:
        """Retrieve project hypercare record."""
        return self._projects.get(record_id)

    def get_project_cost(self, record_id: str) -> Dict[str, float]:
        """Calculate detailed cost and escalation metrics for a project."""
        record = self._projects.get(record_id)
        if not record:
            raise ValueError(f"Hypercare record not found: {record_id}")

        return {
            "hours_logged": round(record.hours_logged, 2),
            "hourly_rate_usd": round(record.hourly_rate_usd, 2),
            "total_cost_usd": round(record.total_cost_usd, 2),
            "incident_escalation_count": float(record.incident_escalation_count),
        }

    def get_operations_cost_summary(self) -> SupportOperationsCostSummary:
        """Compute consolidated hypercare support operations cost summary."""
        total_projects = len(self._projects)
        active_projects = sum(
            1 for p in self._projects.values() if p.phase != HypercarePhase.COMPLETED
        )
        total_cost = sum(p.total_cost_usd for p in self._projects.values())
        total_hours = sum(p.hours_logged for p in self._projects.values())
        avg_cost = (total_cost / total_projects) if total_projects > 0 else 0.0

        by_tier: Dict[str, float] = {}
        for p in self._projects.values():
            tier = p.support_tier
            by_tier[tier] = round(by_tier.get(tier, 0.0) + p.total_cost_usd, 2)

        return SupportOperationsCostSummary(
            total_projects_count=total_projects,
            active_hypercare_count=active_projects,
            total_support_cost_usd=round(total_cost, 2),
            total_hours_logged=round(total_hours, 2),
            average_cost_per_project_usd=round(avg_cost, 2),
            by_support_tier=by_tier,
        )

    def get_hypercare_report(self) -> Dict[str, Any]:
        """Generate comprehensive hypercare and warranty support report."""
        summary = self.get_operations_cost_summary()

        by_phase: Dict[str, int] = {phase.value: 0 for phase in HypercarePhase}
        total_escalations = 0
        for p in self._projects.values():
            by_phase[p.phase.value] += 1
            total_escalations += p.incident_escalation_count

        return {
            "total_projects": summary.total_projects_count,
            "active_hypercare": summary.active_hypercare_count,
            "total_support_cost_usd": summary.total_support_cost_usd,
            "total_hours_logged": summary.total_hours_logged,
            "average_cost_per_project_usd": summary.average_cost_per_project_usd,
            "cost_by_tier": summary.by_support_tier,
            "projects_by_phase": by_phase,
            "total_incident_escalations": total_escalations,
        }
