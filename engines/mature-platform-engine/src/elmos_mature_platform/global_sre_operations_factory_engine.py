"""Global SRE Operations Factory Engine (Batch 39 - Skill 1347).

Orchestrates follow-the-sun oncall rotations, incident escalation trees,
automated SRE runbook lookups, SLA dispatch, and operational governance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    EscalationTier,
    GlobalSreIncidentEscalation,
    SreOncallShift,
    SrePlaybook,
    SreShiftRegion,
)


class GlobalSreOperationsFactoryEngine:
    """Operational orchestrator for global multi-region SRE and incident command."""

    TIER_SEQUENCE = [
        EscalationTier.TIER_1_ONCALL,
        EscalationTier.TIER_2_TECH_LEAD,
        EscalationTier.TIER_3_DOMAIN_EXPERT,
        EscalationTier.INCIDENT_COMMANDER,
    ]

    def __init__(self) -> None:
        self._shifts: Dict[str, SreOncallShift] = {}
        self._playbooks: Dict[str, SrePlaybook] = {}
        self._escalations: Dict[str, GlobalSreIncidentEscalation] = {}

    def schedule_oncall_shift(self, shift: SreOncallShift) -> str:
        """Schedule a regional follow-the-sun oncall shift."""
        if not shift.shift_id:
            shift.shift_id = f"shift-{uuid.uuid4().hex[:8]}"
        if not shift.primary_engineer:
            raise ValueError("primary_engineer is required")

        self._shifts[shift.shift_id] = shift
        return shift.shift_id

    def activate_shift(self, shift_id: str) -> SreOncallShift:
        """Activate an oncall shift and deactivate conflicting active shifts in the region."""
        shift = self._shifts.get(shift_id)
        if not shift:
            raise ValueError(f"Shift not found: {shift_id}")

        for s in self._shifts.values():
            if s.region == shift.region:
                s.is_active = False

        shift.is_active = True
        return shift

    def register_playbook(self, playbook: SrePlaybook) -> str:
        """Register an automated operational remediation playbook."""
        if not playbook.playbook_id:
            playbook.playbook_id = f"pb-{uuid.uuid4().hex[:8]}"
        if not playbook.verified_at:
            playbook.verified_at = datetime.now(timezone.utc).isoformat()

        self._playbooks[playbook.playbook_id] = playbook
        return playbook.playbook_id

    def trigger_incident_escalation(
        self,
        incident_ref: str,
        severity: str,
        region: SreShiftRegion = SreShiftRegion.AMER,
    ) -> GlobalSreIncidentEscalation:
        """Dispatch an incident escalation to the oncall tier and active regional engineer."""
        if not incident_ref:
            raise ValueError("incident_ref is required")

        escalation_id = f"esc-{uuid.uuid4().hex[:8]}"
        active_shift = self.get_active_shift(region)
        assigned_eng = active_shift.primary_engineer if active_shift else "unassigned"

        # SLA calculation based on severity
        sla = 15 if severity.upper() == "P1" else 30 if severity.upper() == "P2" else 60

        esc = GlobalSreIncidentEscalation(
            escalation_id=escalation_id,
            incident_ref=incident_ref,
            severity=severity.upper(),
            current_tier=EscalationTier.TIER_1_ONCALL,
            assigned_shift=region,
            assigned_engineer=assigned_eng,
            escalated_at=datetime.now(timezone.utc).isoformat(),
            response_sla_minutes=sla,
        )
        self._escalations[escalation_id] = esc
        return esc

    def acknowledge_incident(
        self, escalation_id: str, engineer: str
    ) -> GlobalSreIncidentEscalation:
        """Acknowledge an incident escalation, stopping SLA timer."""
        esc = self._escalations.get(escalation_id)
        if not esc:
            raise ValueError(f"Escalation not found: {escalation_id}")

        esc.acknowledged = True
        esc.acknowledged_at = datetime.now(timezone.utc).isoformat()
        esc.assigned_engineer = engineer
        return esc

    def escalate_to_next_tier(
        self, escalation_id: str, new_tier: EscalationTier, notes: str = ""
    ) -> GlobalSreIncidentEscalation:
        """Escalate an incident to a higher support tier."""
        esc = self._escalations.get(escalation_id)
        if not esc:
            raise ValueError(f"Escalation not found: {escalation_id}")

        esc.current_tier = new_tier
        esc.acknowledged = False  # requires new tier acknowledgement
        esc.acknowledged_at = ""
        return esc

    def get_active_shift(self, region: SreShiftRegion) -> Optional[SreOncallShift]:
        """Look up active oncall shift for a specific region."""
        return next((s for s in self._shifts.values() if s.region == region and s.is_active), None)

    def get_unacknowledged_escalations(self) -> List[GlobalSreIncidentEscalation]:
        """Return open escalations waiting for responder acknowledgement."""
        return [e for e in self._escalations.values() if not e.acknowledged]

    def get_global_sre_operations_report(self) -> Dict[str, Any]:
        """Generate operations scorecard across shifts, playbooks, and escalations."""
        total_esc = len(self._escalations)
        ack_count = sum(1 for e in self._escalations.values() if e.acknowledged)
        p1_count = sum(1 for e in self._escalations.values() if e.severity == "P1")

        return {
            "total_escalations": total_esc,
            "acknowledged_count": ack_count,
            "unacknowledged_count": total_esc - ack_count,
            "p1_incident_count": p1_count,
            "total_playbooks": len(self._playbooks),
            "registered_shifts": len(self._shifts),
        }
