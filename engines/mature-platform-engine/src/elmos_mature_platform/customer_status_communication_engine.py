"""Customer Status Communication Engine (Batch 39 - Skill 1357).

Manages SRE customer-facing incident communications, public status page updates,
multi-channel notifications (Webhook, Email, Slack, SMS), and historical uptime reporting.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    CustomerStatusReport,
    IncidentImpactLevel,
    NotificationChannel,
    StatusCommunicationMessage,
)


class CustomerStatusCommunicationEngine:
    """Industrial engine for incident communications and customer status reporting (B39)."""

    def __init__(self, initial_uptime_pct: float = 99.99):
        self._messages: Dict[str, StatusCommunicationMessage] = {}
        self._incident_timelines: Dict[str, List[str]] = {}  # incident_id -> list of msg_ids
        self._active_incident_impacts: Dict[str, IncidentImpactLevel] = {}  # incident_id -> impact
        self._uptime_30d = initial_uptime_pct
        self._audit_log: List[Dict[str, Any]] = []

    def update_30_day_uptime(self, uptime_pct: float) -> None:
        """Update 30-day trailing availability metric."""
        if not (0.0 <= uptime_pct <= 100.0):
            raise ValueError(f"Invalid uptime percentage: {uptime_pct}")
        self._uptime_30d = uptime_pct

    def broadcast_incident_update(
        self,
        incident_id: str,
        impact_level: IncidentImpactLevel,
        title: str,
        body: str,
        affected_components: List[str],
        channels: Optional[List[NotificationChannel]] = None,
        posted_by: str = "incident-commander",
    ) -> StatusCommunicationMessage:
        """Publish an incident status communication update across designated channels."""
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        selected_channels = channels or [NotificationChannel.STATUS_PAGE, NotificationChannel.SLACK_COMMUNITY]

        msg = StatusCommunicationMessage(
            message_id=msg_id,
            incident_id=incident_id,
            impact_level=impact_level,
            title=title,
            body=body,
            affected_components=affected_components,
            channels=selected_channels,
            posted_at=datetime.now(timezone.utc).isoformat(),
            posted_by=posted_by,
        )

        self._messages[msg_id] = msg
        self._incident_timelines.setdefault(incident_id, []).append(msg_id)

        if impact_level != IncidentImpactLevel.NONE:
            self._active_incident_impacts[incident_id] = impact_level
        else:
            self._active_incident_impacts.pop(incident_id, None)

        self._record_audit("message_broadcasted", msg_id, {
            "incident_id": incident_id,
            "impact": impact_level.value,
            "channels": [c.value for c in selected_channels],
        })
        return msg

    def resolve_incident_communication(
        self,
        incident_id: str,
        resolution_notes: str,
        affected_components: Optional[List[str]] = None,
        posted_by: str = "incident-commander",
    ) -> StatusCommunicationMessage:
        """Mark an incident communication resolved and post all-clear notification."""
        components = affected_components or []
        msg = self.broadcast_incident_update(
            incident_id=incident_id,
            impact_level=IncidentImpactLevel.NONE,
            title=f"Resolved: Incident {incident_id}",
            body=resolution_notes,
            affected_components=components,
            channels=[NotificationChannel.STATUS_PAGE, NotificationChannel.WEBHOOK],
            posted_by=posted_by,
        )
        self._active_incident_impacts.pop(incident_id, None)
        return msg

    def get_incident_timeline(self, incident_id: str) -> List[StatusCommunicationMessage]:
        """Fetch all chronological communication updates for an incident."""
        msg_ids = self._incident_timelines.get(incident_id, [])
        return [self._messages[mid] for mid in msg_ids if mid in self._messages]

    def get_status_page_report(self) -> CustomerStatusReport:
        """Generate structured status page report with global health status."""
        active_count = len(self._active_incident_impacts)

        # Derive global status from highest severity active incident
        if any(imp == IncidentImpactLevel.CRITICAL for imp in self._active_incident_impacts.values()):
            global_status = IncidentImpactLevel.CRITICAL
        elif any(imp == IncidentImpactLevel.MAJOR for imp in self._active_incident_impacts.values()):
            global_status = IncidentImpactLevel.MAJOR
        elif any(imp == IncidentImpactLevel.MINOR for imp in self._active_incident_impacts.values()):
            global_status = IncidentImpactLevel.MINOR
        elif any(imp == IncidentImpactLevel.SCHEDULED_MAINTENANCE for imp in self._active_incident_impacts.values()):
            global_status = IncidentImpactLevel.SCHEDULED_MAINTENANCE
        else:
            global_status = IncidentImpactLevel.NONE

        recent_messages = list(self._messages.values())[-10:]

        return CustomerStatusReport(
            report_id=f"stat-rpt-{uuid.uuid4().hex[:6]}",
            active_incidents_count=active_count,
            current_global_status=global_status,
            past_30_days_uptime_pct=self._uptime_30d,
            messages=recent_messages,
        )

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
