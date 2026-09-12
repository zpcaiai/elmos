"""Comprehensive unit tests for TenantProjectMigrationHealthEngine (Batch 39 Skill 1351)."""

import unittest

from elmos_mature_platform.tenant_project_migration_health_engine import TenantProjectMigrationHealthEngine
from elmos_mature_platform.types import (
    MigrationHealthState,
    MigrationHealthMetric,
    TenantMigrationHealthRecord,
)


class TestTenantProjectMigrationHealthComprehensive(unittest.TestCase):
    """Test suite for tenant and project migration health monitoring."""

    def setUp(self) -> None:
        self.engine = TenantProjectMigrationHealthEngine()
        self.sample_record = TenantMigrationHealthRecord(
            record_id="rec-mig-001",
            tenant_id="tenant-fintech",
            project_id="proj-oracle-to-postgres",
            state=MigrationHealthState.HEALTHY,
            replication_lag_seconds=12.5,
            error_rate_pct=0.05,
            throughput_items_per_sec=1450.0,
        )

    def test_record_health_and_retrieval(self) -> None:
        rec_id = self.engine.record_health(self.sample_record)
        self.assertEqual(rec_id, "rec-mig-001")
        retrieved = self.engine.get_record("rec-mig-001")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.tenant_id, "tenant-fintech")
        self.assertTrue(retrieved.last_health_check)

    def test_evaluate_health_warning_due_to_lag(self) -> None:
        self.sample_record.replication_lag_seconds = 75.0  # >= 60.0s triggers warning
        self.engine.record_health(self.sample_record)
        evaluated = self.engine.evaluate_health("rec-mig-001")
        self.assertEqual(evaluated.state, MigrationHealthState.WARNING)
        self.assertIn("Warning", evaluated.health_summary)

    def test_evaluate_health_critical_due_to_error_rate(self) -> None:
        self.sample_record.error_rate_pct = 6.2  # >= 5.0% triggers critical
        self.engine.record_health(self.sample_record)
        evaluated = self.engine.evaluate_health("rec-mig-001")
        self.assertEqual(evaluated.state, MigrationHealthState.CRITICAL)
        self.assertIn("Critical alert", evaluated.health_summary)

    def test_add_custom_metric_triggers_critical(self) -> None:
        self.engine.record_health(self.sample_record)
        metric = MigrationHealthMetric(
            metric_name="memory_utilization_pct",
            current_value=96.5,
            warning_threshold=80.0,
            critical_threshold=95.0,
        )
        updated = self.engine.add_metric("rec-mig-001", metric)
        self.assertEqual(updated.state, MigrationHealthState.CRITICAL)
        self.assertEqual(len(updated.metrics), 1)

    def test_pause_and_resume_migration(self) -> None:
        self.engine.record_health(self.sample_record)
        paused = self.engine.pause_migration("rec-mig-001", "Manual checkpoint before schema alter")
        self.assertEqual(paused.state, MigrationHealthState.PAUSED)
        self.assertIn("paused", paused.health_summary)

        # Resuming restores health status calculation
        resumed = self.engine.resume_migration("rec-mig-001")
        self.assertEqual(resumed.state, MigrationHealthState.HEALTHY)

    def test_get_critical_records(self) -> None:
        self.sample_record.replication_lag_seconds = 450.0  # Critical
        self.engine.record_health(self.sample_record)
        crits = self.engine.get_critical_records()
        self.assertEqual(len(crits), 1)
        self.assertEqual(crits[0].record_id, "rec-mig-001")

    def test_fleet_migration_health_summary(self) -> None:
        self.engine.record_health(self.sample_record)
        summary = self.engine.get_fleet_migration_health_summary()
        self.assertEqual(summary["total_tracked_migrations"], 1)
        self.assertEqual(summary["total_throughput_items_per_sec"], 1450.0)
        self.assertEqual(summary["unhealthy_count"], 0)


if __name__ == "__main__":
    unittest.main()
