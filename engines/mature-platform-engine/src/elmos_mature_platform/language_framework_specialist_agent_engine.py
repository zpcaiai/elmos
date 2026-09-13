"""Language and Framework Specialist Agent Engine (Batch 42 - Skill 1417).

Governs specialized agent personas tailored for exact language and framework domains
(e.g., Java/Spring, .NET/C#, Python/FastAPI), routing tasks based on capability ratings,
prompt context limits, and historical domain success rates.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    SpecialistCapabilityRating,
    SpecialistDispatchDecision,
    SpecialistDomain,
    SpecialistAgentProfile,
)


class LanguageFrameworkSpecialistAgentEngine:
    """Capability registry and routing dispatcher for language-specialized agents."""

    def __init__(self) -> None:
        self._specialists: Dict[str, SpecialistAgentProfile] = {}
        self._dispatches: Dict[str, SpecialistDispatchDecision] = {}

    def register_specialist(self, profile: SpecialistAgentProfile) -> str:
        """Register a domain-specialized agent persona."""
        if not profile.name:
            raise ValueError("Specialist name is required")

        if not profile.specialist_id:
            profile.specialist_id = f"spec-{uuid.uuid4().hex[:8]}"

        self._specialists[profile.specialist_id] = profile
        return profile.specialist_id

    def dispatch_task(
        self,
        task_id: str,
        domain: SpecialistDomain,
        required_frameworks: Optional[List[str]] = None,
    ) -> SpecialistDispatchDecision:
        """Dispatch a modernization task to the highest-scoring available domain specialist."""
        if not task_id:
            raise ValueError("task_id is required")

        candidates = [
            s for s in self._specialists.values()
            if s.domain == domain
        ]

        if required_frameworks:
            req_set = set(f.lower() for f in required_frameworks)
            candidates = [
                s for s in candidates
                if req_set.issubset(set(f.lower() for f in s.supported_frameworks))
            ]

        if not candidates:
            raise ValueError(f"No eligible specialist found for domain: {domain.value}")

        rating_scores = {
            SpecialistCapabilityRating.MASTER: 100.0,
            SpecialistCapabilityRating.EXPERT: 80.0,
            SpecialistCapabilityRating.COMPETENT: 60.0,
            SpecialistCapabilityRating.NOVICE: 40.0,
        }

        best_specialist: Optional[SpecialistAgentProfile] = None
        best_score = -1000.0

        for s in candidates:
            base_score = rating_scores.get(s.rating, 50.0)
            load_penalty = s.active_tasks_count * 10.0
            success_bonus = s.success_rate_pct * 0.2
            final_score = base_score + success_bonus - load_penalty

            if final_score > best_score:
                best_score = final_score
                best_specialist = s

        assert best_specialist is not None
        best_specialist.active_tasks_count += 1

        decision = SpecialistDispatchDecision(
            dispatch_id=f"disp-{uuid.uuid4().hex[:8]}",
            task_id=task_id,
            domain=domain,
            selected_specialist_id=best_specialist.specialist_id,
            match_score=best_score,
            rationale=f"Selected {best_specialist.name} (Rating: {best_specialist.rating.value}, Load: {best_specialist.active_tasks_count})",
            dispatched_at=datetime.now(timezone.utc).isoformat(),
        )

        self._dispatches[decision.dispatch_id] = decision
        return decision

    def record_task_completion(
        self, specialist_id: str, success: bool
    ) -> SpecialistAgentProfile:
        """Update specialist statistics and success rate upon task completion."""
        specialist = self._specialists.get(specialist_id)
        if not specialist:
            raise ValueError(f"Specialist not found: {specialist_id}")

        specialist.active_tasks_count = max(0, specialist.active_tasks_count - 1)
        prev_completed = specialist.total_tasks_completed
        specialist.total_tasks_completed += 1

        if prev_completed == 0:
            specialist.success_rate_pct = 100.0 if success else 0.0
        else:
            prev_successes = (specialist.success_rate_pct / 100.0) * prev_completed
            new_successes = prev_successes + (1 if success else 0)
            specialist.success_rate_pct = (new_successes / specialist.total_tasks_completed) * 100.0

        return specialist

    def get_specialist(self, specialist_id: str) -> Optional[SpecialistAgentProfile]:
        """Retrieve specialist by ID."""
        return self._specialists.get(specialist_id)

    def get_specialists_by_domain(
        self, domain: SpecialistDomain
    ) -> List[SpecialistAgentProfile]:
        """Retrieve all registered specialists for a given language domain."""
        return [s for s in self._specialists.values() if s.domain == domain]

    def get_specialist_fleet_report(self) -> Dict[str, Any]:
        """Generate platform specialist fleet utilization and capability metrics."""
        total = len(self._specialists)
        by_domain: Dict[str, int] = {}
        for s in self._specialists.values():
            d = s.domain.value
            by_domain[d] = by_domain.get(d, 0) + 1

        avg_success = (
            sum(s.success_rate_pct for s in self._specialists.values()) / total
            if total > 0 else 0.0
        )
        total_completed = sum(s.total_tasks_completed for s in self._specialists.values())

        return {
            "total_specialists": total,
            "by_domain": by_domain,
            "average_success_rate_pct": avg_success,
            "total_completed_tasks": total_completed,
            "total_dispatches": len(self._dispatches),
        }
