"""On-Call Follow-The-Sun Engine (Batch 39 - Skill 1358).

Orchestrates 24/7 continuous global on-call coverage across APAC, EMEA, and AMER
regions with audited shift transfers, active incident handovers, watch item tracking,
and acknowledgment verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    FollowTheSunSchedule,
    HandoverBriefing,
    HandoverStatus,
    SunRegion,
)


class OncallFollowTheSunEngine:
    """Industrial engine for 24/7 Follow-the-Sun on-call operations (B39)."""

    HANDOVER_ROTATION = {
        SunRegion.APAC: SunRegion.EMEA,
        SunRegion.EMEA: SunRegion.AMER,
        SunRegion.AMER: SunRegion.APAC,
    }

    def __init__(self):
        self._schedules: Dict[str, FollowTheSunSchedule] = {}
        self._handovers: Dict[str, HandoverBriefing] = {}

    def get_active_region_for_utc_hour(self, utc_hour: int) -> SunRegion:
        """Determine the primary on-call operating region for a given UTC hour (0-23)."""
        if not 0 <= utc_hour <= 23:
            raise ValueError(f"Invalid UTC hour '{utc_hour}', must be between 0 and 23")

        if 0 <= utc_hour < 8:
            return SunRegion.APAC
        elif 8 <= utc_hour < 16:
            return SunRegion.EMEA
        else:
            return SunRegion.AMER

    def create_schedule(
        self,
        date: str,
        apac_engineer: str,
        emea_engineer: str,
        amer_engineer: str,
    ) -> FollowTheSunSchedule:
        """Create a full 24-hour schedule assigning engineers to each sun region."""
        for name, eng in [("APAC", apac_engineer), ("EMEA", emea_engineer), ("AMER", amer_engineer)]:
            if not eng.strip():
                raise ValueError(f"{name} engineer must be specified")

        schedule_id = f"fts-{date}-{uuid.uuid4().hex[:4]}"
        schedule = FollowTheSunSchedule(
            schedule_id=schedule_id,
            date=date,
            region_shifts={
                SunRegion.APAC.value: apac_engineer,
                SunRegion.EMEA.value: emea_engineer,
                SunRegion.AMER.value: amer_engineer,
            },
        )
        self._schedules[schedule_id] = schedule
        return schedule

    def initiate_handover(
        self,
        schedule_id: str,
        outgoing_region: SunRegion,
        active_incidents: List[str],
        watch_items: List[str],
        notes: str = "",
    ) -> HandoverBriefing:
        """Initiate formal shift handover from current region to next incoming region."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule '{schedule_id}' not found")

        incoming_region = self.HANDOVER_ROTATION[outgoing_region]
        outgoing_eng = schedule.region_shifts[outgoing_region.value]
        incoming_eng = schedule.region_shifts[incoming_region.value]

        handover_id = f"hnd-{outgoing_region.value[:2]}-{incoming_region.value[:2]}-{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        briefing = HandoverBriefing(
            handover_id=handover_id,
            outgoing_region=outgoing_region,
            incoming_region=incoming_region,
            outgoing_engineer=outgoing_eng,
            incoming_engineer=incoming_eng,
            active_incidents=list(active_incidents),
            watch_items=list(watch_items),
            status=HandoverStatus.SCHEDULED,
            handover_time=now_iso,
            acknowledged_at="",
            notes=notes,
        )
        self._handovers[handover_id] = briefing
        return briefing

    def start_handover(self, handover_id: str) -> HandoverBriefing:
        """Transition handover status to IN_PROGRESS as shift briefing begins."""
        briefing = self._handovers.get(handover_id)
        if not briefing:
            raise ValueError(f"Handover '{handover_id}' not found")

        briefing.status = HandoverStatus.IN_PROGRESS
        return briefing

    def acknowledge_and_complete_handover(
        self,
        handover_id: str,
        incoming_engineer: str,
    ) -> HandoverBriefing:
        """Incoming on-call engineer acknowledges briefing and completes shift transfer."""
        briefing = self._handovers.get(handover_id)
        if not briefing:
            raise ValueError(f"Handover '{handover_id}' not found")

        if briefing.status not in (HandoverStatus.SCHEDULED, HandoverStatus.IN_PROGRESS):
            raise ValueError(f"Cannot complete handover in status '{briefing.status.value}'")

        if incoming_engineer != briefing.incoming_engineer:
            raise ValueError(
                f"Handover acknowledgement mismatch: expected '{briefing.incoming_engineer}', got '{incoming_engineer}'"
            )

        briefing.status = HandoverStatus.COMPLETED
        briefing.acknowledged_at = datetime.now(timezone.utc).isoformat()
        return briefing

    def mark_missed(self, handover_id: str, reason: str = "") -> HandoverBriefing:
        """Mark handover as MISSED if unacknowledged within SLA threshold."""
        briefing = self._handovers.get(handover_id)
        if not briefing:
            raise ValueError(f"Handover '{handover_id}' not found")

        briefing.status = HandoverStatus.MISSED
        if reason:
            briefing.notes = f"{briefing.notes} | MISSED: {reason}".strip(" |")
        return briefing

    def get_current_oncall(self, schedule_id: str, utc_hour: int) -> Dict[str, Any]:
        """Look up the active region and responsible engineer for a given hour."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule '{schedule_id}' not found")

        active_region = self.get_active_region_for_utc_hour(utc_hour)
        engineer = schedule.region_shifts[active_region.value]

        return {
            "schedule_id": schedule_id,
            "utc_hour": utc_hour,
            "active_region": active_region.value,
            "oncall_engineer": engineer,
        }

    def get_handover_report(self, schedule_id: str) -> Dict[str, Any]:
        """Summarize all shift handovers and active incidents for a schedule."""
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule '{schedule_id}' not found")

        handovers = [
            h for h in self._handovers.values()
            if any(h.outgoing_engineer == eng for eng in schedule.region_shifts.values())
        ]

        total_active_incidents = sum(len(h.active_incidents) for h in handovers)
        total_watch_items = sum(len(h.watch_items) for h in handovers)
        completed = sum(1 for h in handovers if h.status == HandoverStatus.COMPLETED)
        missed = sum(1 for h in handovers if h.status == HandoverStatus.MISSED)

        return {
            "schedule_id": schedule.schedule_id,
            "date": schedule.date,
            "total_handovers": len(handovers),
            "completed_handovers": completed,
            "missed_handovers": missed,
            "cumulative_active_incidents": total_active_incidents,
            "cumulative_watch_items": total_watch_items,
        }

    def get_handover(self, handover_id: str) -> Optional[HandoverBriefing]:
        """Retrieve handover by ID."""
        return self._handovers.get(handover_id)

    def list_handovers(
        self,
        status: Optional[HandoverStatus] = None,
    ) -> List[HandoverBriefing]:
        """List handovers, optionally filtered by status."""
        if status:
            return [h for h in self._handovers.values() if h.status == status]
        return list(self._handovers.values())
