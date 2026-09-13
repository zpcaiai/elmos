"""Support and EOL Policy Engine (Batch 43 - Skill 1445).

Manages long-term support (LTS) release lifecycles, active support, maintenance support,
extended support windows, end-of-life (EOL) phase transitions, and patch eligibility rules.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    EolLifecyclePhase,
    ProductReleaseLifecycle,
)


class SupportEolPolicyEngine:
    """LTS release lifecycle governor and support tier state machine."""

    def __init__(self) -> None:
        self._lifecycles: Dict[str, ProductReleaseLifecycle] = {}

    def register_release_lifecycle(self, lifecycle: ProductReleaseLifecycle) -> str:
        """Register product release lifecycle dates and determine initial phase."""
        if not lifecycle.product_name or not lifecycle.version:
            raise ValueError("product_name and version are required")
        if not lifecycle.ga_date or not lifecycle.eol_date:
            raise ValueError("ga_date and eol_date are required")

        if not lifecycle.release_id:
            lifecycle.release_id = f"rel-life-{uuid.uuid4().hex[:8]}"

        self._update_phase(lifecycle)
        self._lifecycles[lifecycle.release_id] = lifecycle
        return lifecycle.release_id

    def evaluate_phase(
        self, release_id: str, as_of_date: Optional[str] = None
    ) -> EolLifecyclePhase:
        """Evaluate support phase as of a given date (default current UTC date)."""
        lifecycle = self._lifecycles.get(release_id)
        if not lifecycle:
            raise ValueError(f"Release lifecycle not found: {release_id}")

        self._update_phase(lifecycle, as_of_date)
        return lifecycle.current_phase

    def _update_phase(
        self, lifecycle: ProductReleaseLifecycle, as_of_date: Optional[str] = None
    ) -> None:
        now_date = as_of_date or datetime.now(timezone.utc).isoformat()[:10]

        if now_date >= lifecycle.eol_date:
            lifecycle.current_phase = EolLifecyclePhase.END_OF_LIFE
            lifecycle.critical_security_fixes_only = False
        elif lifecycle.maintenance_support_end_date and now_date >= lifecycle.maintenance_support_end_date:
            if lifecycle.extended_support_available:
                lifecycle.current_phase = EolLifecyclePhase.EXTENDED_SUPPORT
                lifecycle.critical_security_fixes_only = True
            else:
                lifecycle.current_phase = EolLifecyclePhase.END_OF_LIFE
                lifecycle.critical_security_fixes_only = False
        elif lifecycle.active_support_end_date and now_date >= lifecycle.active_support_end_date:
            lifecycle.current_phase = EolLifecyclePhase.MAINTENANCE_SUPPORT
            lifecycle.critical_security_fixes_only = True
        else:
            lifecycle.current_phase = EolLifecyclePhase.ACTIVE_SUPPORT
            lifecycle.critical_security_fixes_only = False

    def can_receive_feature_update(
        self, release_id: str, as_of_date: Optional[str] = None
    ) -> bool:
        """Check if release is eligible for regular minor/feature updates."""
        phase = self.evaluate_phase(release_id, as_of_date)
        return phase in (
            EolLifecyclePhase.GENERAL_AVAILABILITY,
            EolLifecyclePhase.ACTIVE_SUPPORT,
        )

    def can_receive_security_patch(
        self, release_id: str, as_of_date: Optional[str] = None
    ) -> bool:
        """Check if release is eligible for critical security fixes."""
        phase = self.evaluate_phase(release_id, as_of_date)
        return phase in (
            EolLifecyclePhase.GENERAL_AVAILABILITY,
            EolLifecyclePhase.ACTIVE_SUPPORT,
            EolLifecyclePhase.MAINTENANCE_SUPPORT,
            EolLifecyclePhase.EXTENDED_SUPPORT,
        )

    def get_eol_roadmap(
        self, product_name: Optional[str] = None
    ) -> List[ProductReleaseLifecycle]:
        """Query product lifecycle records ordered by EOL milestone date."""
        records = list(self._lifecycles.values())
        if product_name:
            records = [r for r in records if r.product_name == product_name]
        records.sort(key=lambda r: r.eol_date)
        return records

    def get_lifecycle_report(self) -> Dict[str, Any]:
        """Generate platform release support lifecycle health report."""
        total = len(self._lifecycles)
        by_phase: Dict[str, int] = {}
        for r in self._lifecycles.values():
            self._update_phase(r)
            p = r.current_phase.value
            by_phase[p] = by_phase.get(p, 0) + 1

        return {
            "total_tracked_releases": total,
            "by_support_phase": by_phase,
            "eol_releases_count": by_phase.get(EolLifecyclePhase.END_OF_LIFE.value, 0),
        }
