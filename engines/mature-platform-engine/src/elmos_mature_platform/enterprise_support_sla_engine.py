"""Enterprise Support SLA Engine (Batch 39 - Skill 1360).

Governs enterprise support tiering, P1-P4 SLA tracking, first response and
resolution time verification, breach detection, and service credit eligibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    SupportSlaTarget,
    SupportTicket,
    SupportTierLevel,
    TicketPriority,
    TicketStatus,
)


class EnterpriseSupportSlaEngine:
    """Industrial engine for enterprise support tiering and SLA compliance (B39)."""

    def __init__(self):
        self._targets: Dict[str, SupportSlaTarget] = {}
        self._tickets: Dict[str, SupportTicket] = {}
        self._seed_default_targets()

    def _seed_default_targets(self) -> None:
        """Seed enterprise default SLA targets by tier and priority."""
        defaults = [
            # Mission Critical: 15 min response for P1, 2 hr resolution
            SupportSlaTarget(tier=SupportTierLevel.MISSION_CRITICAL, priority=TicketPriority.P1_CRITICAL, response_time_minutes=15, resolution_time_minutes=120, dedicated_tam=True),
            SupportSlaTarget(tier=SupportTierLevel.MISSION_CRITICAL, priority=TicketPriority.P2_HIGH, response_time_minutes=60, resolution_time_minutes=480, dedicated_tam=True),
            SupportSlaTarget(tier=SupportTierLevel.MISSION_CRITICAL, priority=TicketPriority.P3_MEDIUM, response_time_minutes=240, resolution_time_minutes=1440, dedicated_tam=True),
            # Premier: 30 min response for P1, 4 hr resolution
            SupportSlaTarget(tier=SupportTierLevel.PREMIER, priority=TicketPriority.P1_CRITICAL, response_time_minutes=30, resolution_time_minutes=240, dedicated_tam=False),
            SupportSlaTarget(tier=SupportTierLevel.PREMIER, priority=TicketPriority.P2_HIGH, response_time_minutes=120, resolution_time_minutes=960, dedicated_tam=False),
            # Standard: 2 hr response for P1, 8 hr resolution
            SupportSlaTarget(tier=SupportTierLevel.STANDARD, priority=TicketPriority.P1_CRITICAL, response_time_minutes=120, resolution_time_minutes=480, dedicated_tam=False, twenty_four_seven=False),
            SupportSlaTarget(tier=SupportTierLevel.STANDARD, priority=TicketPriority.P2_HIGH, response_time_minutes=480, resolution_time_minutes=2880, dedicated_tam=False, twenty_four_seven=False),
            # Community: best effort (1440 min response)
            SupportSlaTarget(tier=SupportTierLevel.COMMUNITY, priority=TicketPriority.P1_CRITICAL, response_time_minutes=1440, resolution_time_minutes=10080, dedicated_tam=False, twenty_four_seven=False),
        ]
        for t in defaults:
            self.set_sla_target(t)

    def set_sla_target(self, target: SupportSlaTarget) -> None:
        """Set or update SLA target parameters for tier and priority."""
        key = f"{target.tier.value}:{target.priority.value}"
        self._targets[key] = target

    def get_sla_target(self, tier: SupportTierLevel, priority: TicketPriority) -> Optional[SupportSlaTarget]:
        """Retrieve SLA target for a specific tier and priority."""
        key = f"{tier.value}:{priority.value}"
        return self._targets.get(key)

    def create_ticket(self, ticket: SupportTicket) -> str:
        """Create and record a new enterprise support ticket."""
        if not ticket.ticket_id:
            ticket.ticket_id = f"tkt-{uuid.uuid4().hex[:8]}"
        if not ticket.created_at:
            ticket.created_at = datetime.now(timezone.utc).isoformat()
        ticket.status = TicketStatus.OPEN

        self._tickets[ticket.ticket_id] = ticket
        return ticket.ticket_id

    def record_response(
        self,
        ticket_id: str,
        engineer: str,
        timestamp: str = "",
    ) -> SupportTicket:
        """Record the first engineer response and evaluate response SLA breach."""
        ticket = self._get_ticket_or_raise(ticket_id)
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
        ticket.first_response_at = timestamp
        ticket.assigned_engineer = engineer
        ticket.status = TicketStatus.IN_PROGRESS

        # SLA evaluation
        target = self.get_sla_target(ticket.support_tier, ticket.priority)
        if target:
            created_dt = datetime.fromisoformat(ticket.created_at.replace("Z", "+00:00"))
            resp_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elapsed_min = (resp_dt - created_dt).total_seconds() / 60.0
            if elapsed_min > target.response_time_minutes:
                ticket.response_breached = True
                if ticket.priority == TicketPriority.P1_CRITICAL:
                    ticket.service_credit_eligible = True

        return ticket

    def record_resolution(
        self,
        ticket_id: str,
        timestamp: str = "",
    ) -> SupportTicket:
        """Record resolution and evaluate resolution SLA breach."""
        ticket = self._get_ticket_or_raise(ticket_id)
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
        ticket.resolved_at = timestamp
        ticket.status = TicketStatus.RESOLVED

        target = self.get_sla_target(ticket.support_tier, ticket.priority)
        if target:
            created_dt = datetime.fromisoformat(ticket.created_at.replace("Z", "+00:00"))
            res_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elapsed_min = (res_dt - created_dt).total_seconds() / 60.0
            if elapsed_min > target.resolution_time_minutes:
                ticket.resolution_breached = True
                ticket.service_credit_eligible = True

        return ticket

    def calculate_sla_compliance(self, customer_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculate overall and per-tier response and resolution SLA compliance."""
        tickets = list(self._tickets.values())
        if customer_id:
            tickets = [t for t in tickets if t.customer_id == customer_id]

        if not tickets:
            return {
                "total_tickets": 0,
                "response_compliance_pct": 100.0,
                "resolution_compliance_pct": 100.0,
                "total_breaches": 0,
                "service_credit_eligible_count": 0,
            }

        responded = [t for t in tickets if t.first_response_at]
        resolved = [t for t in tickets if t.resolved_at]

        resp_met = sum(1 for t in responded if not t.response_breached)
        res_met = sum(1 for t in resolved if not t.resolution_breached)

        resp_pct = (resp_met / len(responded) * 100.0) if responded else 100.0
        res_pct = (res_met / len(resolved) * 100.0) if resolved else 100.0
        credits_count = sum(1 for t in tickets if t.service_credit_eligible)

        return {
            "total_tickets": len(tickets),
            "tickets_responded": len(responded),
            "tickets_resolved": len(resolved),
            "response_compliance_pct": round(resp_pct, 2),
            "resolution_compliance_pct": round(res_pct, 2),
            "total_response_breaches": len(responded) - resp_met,
            "total_resolution_breaches": len(resolved) - res_met,
            "service_credit_eligible_count": credits_count,
        }

    def get_eligible_service_credits(self, customer_id: Optional[str] = None) -> List[SupportTicket]:
        """Return tickets that qualify for customer service credits due to SLA breaches."""
        tickets = [t for t in self._tickets.values() if t.service_credit_eligible]
        if customer_id:
            tickets = [t for t in tickets if t.customer_id == customer_id]
        return tickets

    def get_tier_features(self, tier: SupportTierLevel) -> Dict[str, Any]:
        """Retrieve features and entitlements for a given support tier."""
        features = {
            SupportTierLevel.MISSION_CRITICAL: {
                "tam": True,
                "availability": "24x7x365",
                "p1_response_min": 15,
                "channels": ["phone", "slack", "web", "email"],
                "service_credit_pct": 10.0,
            },
            SupportTierLevel.PREMIER: {
                "tam": False,
                "availability": "24x7x365",
                "p1_response_min": 30,
                "channels": ["slack", "web", "email"],
                "service_credit_pct": 5.0,
            },
            SupportTierLevel.STANDARD: {
                "tam": False,
                "availability": "8x5 Business Hours",
                "p1_response_min": 120,
                "channels": ["web", "email"],
                "service_credit_pct": 2.5,
            },
            SupportTierLevel.COMMUNITY: {
                "tam": False,
                "availability": "Best Effort",
                "p1_response_min": 1440,
                "channels": ["forum", "community-discord"],
                "service_credit_pct": 0.0,
            },
        }
        return features.get(tier, {})

    def _get_ticket_or_raise(self, ticket_id: str) -> SupportTicket:
        if ticket_id not in self._tickets:
            raise ValueError(f"Support ticket {ticket_id} not found")
        return self._tickets[ticket_id]
