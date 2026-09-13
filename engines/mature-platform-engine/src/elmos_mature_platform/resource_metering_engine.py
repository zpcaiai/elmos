"""Resource Metering Engine (Batch 44 - Skill 1457).

Performs fine-grained real-time metering of runner execution durations, LLM token consumption,
storage volume hours, and network egress across multi-tenant modernization workloads.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    MeteredResourceType,
    ResourceMeterEvent,
    TenantUsageRollup,
)


class ResourceMeteringEngine:
    """Multi-tenant usage metering and quota verification telemetry engine."""

    def __init__(self) -> None:
        self._events: List[ResourceMeterEvent] = []
        self._tenant_usage: Dict[str, Dict[str, float]] = {}
        self._tenant_event_counts: Dict[str, int] = {}
        self._tenant_last_event: Dict[str, str] = {}

    def record_meter_event(self, event: ResourceMeterEvent) -> str:
        """Ingest a discrete resource consumption telemetry event."""
        if not event.tenant_id:
            raise ValueError("tenant_id is required")
        if event.units < 0:
            raise ValueError("units cannot be negative")

        if not event.event_id:
            event.event_id = f"meter-{uuid.uuid4().hex[:8]}"

        if not event.recorded_at:
            event.recorded_at = datetime.now(timezone.utc).isoformat()

        self._events.append(event)

        # Update tenant aggregation
        t_id = event.tenant_id
        if t_id not in self._tenant_usage:
            self._tenant_usage[t_id] = {rt.value: 0.0 for rt in MeteredResourceType}
            self._tenant_event_counts[t_id] = 0

        rt_key = event.resource_type.value
        self._tenant_usage[t_id][rt_key] = round(
            self._tenant_usage[t_id].get(rt_key, 0.0) + event.units, 4
        )
        self._tenant_event_counts[t_id] += 1
        self._tenant_last_event[t_id] = event.recorded_at

        return event.event_id

    def get_tenant_usage(
        self, tenant_id: str, resource_type: Optional[MeteredResourceType] = None
    ) -> TenantUsageRollup:
        """Query aggregated consumption metrics for a specific tenant."""
        if tenant_id not in self._tenant_usage:
            return TenantUsageRollup(
                tenant_id=tenant_id,
                total_units_by_type={},
                last_event_at="",
                total_events_count=0,
            )

        usage = dict(self._tenant_usage[tenant_id])
        if resource_type:
            usage = {resource_type.value: usage.get(resource_type.value, 0.0)}

        return TenantUsageRollup(
            tenant_id=tenant_id,
            total_units_by_type=usage,
            last_event_at=self._tenant_last_event.get(tenant_id, ""),
            total_events_count=self._tenant_event_counts.get(tenant_id, 0),
        )

    def check_quota(
        self, tenant_id: str, resource_type: MeteredResourceType, limit: float
    ) -> bool:
        """Verify if tenant's consumed units for resource_type are strictly within limit."""
        if limit < 0:
            raise ValueError("limit cannot be negative")

        usage = self._tenant_usage.get(tenant_id, {})
        current = usage.get(resource_type.value, 0.0)
        return current <= limit

    def get_total_metered_units(self, resource_type: MeteredResourceType) -> float:
        """Calculate platform-wide consumed units for a specific resource type."""
        total = 0.0
        for tenant_dict in self._tenant_usage.values():
            total += tenant_dict.get(resource_type.value, 0.0)
        return round(total, 4)

    def get_metering_report(self) -> Dict[str, Any]:
        """Generate platform usage metering summary report."""
        by_resource: Dict[str, float] = {}
        for rt in MeteredResourceType:
            by_resource[rt.value] = self.get_total_metered_units(rt)

        return {
            "total_metering_events": len(self._events),
            "total_tenants_metered": len(self._tenant_usage),
            "units_by_resource_type": by_resource,
        }
