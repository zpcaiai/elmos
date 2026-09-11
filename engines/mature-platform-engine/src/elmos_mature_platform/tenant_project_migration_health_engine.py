"""Tenant Project Migration Health Engine - Batch 39 Skill 1351.

Monitors real-time migration health, data lag, error rates, metric thresholds,
and supports automated/manual pause and resume for multi-tenant migration pipelines.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import uuid

from .types import (
    MigrationHealthState,
    MigrationHealthMetric,
    TenantMigrationHealthRecord,
)


class TenantProjectMigrationHealthEngine:
    """Evaluates and tracks tenant and project migration health status."""

    def __init__(self) -> None:
        self._records: Dict[str, TenantMigrationHealthRecord] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_health(self, record: TenantMigrationHealthRecord) -> str:
        """Register or update a tenant project migration health record."""
        if not record.record_id or not record.tenant_id or not record.project_id:
            raise ValueError("record_id, tenant_id, and project_id must not be empty")

        if not record.last_health_check:
            record.last_health_check = self._now_iso()

        self._records[record.record_id] = record
        self.evaluate_health(record.record_id)
        return record.record_id

    def add_metric(self, record_id: str, metric: MigrationHealthMetric) -> TenantMigrationHealthRecord:
        """Add a custom health metric and evaluate its health."""
        if record_id not in self._records:
            raise ValueError(f"Health record {record_id} not found")

        metric.is_healthy = metric.current_value < metric.warning_threshold
        record = self._records[record_id]
        record.metrics.append(metric)
        record.last_health_check = self._now_iso()
        return self.evaluate_health(record_id)

    def evaluate_health(self, record_id: str) -> TenantMigrationHealthRecord:
        """Evaluate overall migration health state based on lag, errors, and custom metrics."""
        if record_id not in self._records:
            raise ValueError(f"Health record {record_id} not found")

        record = self._records[record_id]

        # If currently paused manually, maintain PAUSED unless explicitly resumed
        if record.state == MigrationHealthState.PAUSED:
            return record

        is_critical = (
            record.replication_lag_seconds >= 300.0  # >= 5 minutes lag
            or record.error_rate_pct >= 5.0  # >= 5% error rate
            or any(m.current_value >= m.critical_threshold for m in record.metrics)
        )

        is_warning = (
            record.replication_lag_seconds >= 60.0  # >= 1 minute lag
            or record.error_rate_pct >= 1.0  # >= 1% error rate
            or any(m.current_value >= m.warning_threshold for m in record.metrics)
        )

        if is_critical:
            record.state = MigrationHealthState.CRITICAL
            record.health_summary = (
                f"Critical alert: Lag {record.replication_lag_seconds}s, "
                f"Errors {record.error_rate_pct}%, critical metrics triggered."
            )
        elif is_warning:
            record.state = MigrationHealthState.WARNING
            record.health_summary = (
                f"Warning: Lag {record.replication_lag_seconds}s, "
                f"Errors {record.error_rate_pct}%."
            )
        else:
            record.state = MigrationHealthState.HEALTHY
            record.health_summary = (
                f"Healthy: Lag {record.replication_lag_seconds}s, "
                f"Errors {record.error_rate_pct}%, Throughput {record.throughput_items_per_sec} items/s."
            )

        record.last_health_check = self._now_iso()
        return record

    def pause_migration(self, record_id: str, reason: str) -> TenantMigrationHealthRecord:
        """Explicitly pause migration due to critical drift or manual intervention."""
        if record_id not in self._records:
            raise ValueError(f"Health record {record_id} not found")

        record = self._records[record_id]
        record.state = MigrationHealthState.PAUSED
        record.health_summary = f"Migration paused: {reason}"
        record.last_health_check = self._now_iso()
        return record

    def resume_migration(self, record_id: str) -> TenantMigrationHealthRecord:
        """Resume a paused migration and re-evaluate health."""
        if record_id not in self._records:
            raise ValueError(f"Health record {record_id} not found")

        record = self._records[record_id]
        record.state = MigrationHealthState.HEALTHY
        return self.evaluate_health(record_id)

    def get_record(self, record_id: str) -> Optional[TenantMigrationHealthRecord]:
        """Retrieve health record by ID."""
        return self._records.get(record_id)

    def get_records_for_tenant(self, tenant_id: str) -> List[TenantMigrationHealthRecord]:
        """List all health records for a given tenant."""
        return [r for r in self._records.values() if r.tenant_id == tenant_id]

    def get_critical_records(self) -> List[TenantMigrationHealthRecord]:
        """Retrieve all migration records in CRITICAL state."""
        return [r for r in self._records.values() if r.state == MigrationHealthState.CRITICAL]

    def get_fleet_migration_health_summary(self) -> Dict[str, Any]:
        """Generate fleet-wide migration health summary."""
        total = len(self._records)
        by_state = {s.value: 0 for s in MigrationHealthState}
        total_lag = 0.0
        total_error_rate = 0.0
        total_throughput = 0.0

        for r in self._records.values():
            by_state[r.state.value] = by_state.get(r.state.value, 0) + 1
            total_lag += r.replication_lag_seconds
            total_error_rate += r.error_rate_pct
            total_throughput += r.throughput_items_per_sec

        return {
            "total_tracked_migrations": total,
            "by_state": by_state,
            "avg_replication_lag_seconds": round(total_lag / total, 2) if total > 0 else 0.0,
            "avg_error_rate_pct": round(total_error_rate / total, 2) if total > 0 else 0.0,
            "total_throughput_items_per_sec": round(total_throughput, 2),
            "unhealthy_count": by_state.get("critical", 0) + by_state.get("warning", 0),
        }
