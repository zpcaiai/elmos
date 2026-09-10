import unittest
from datetime import datetime, timedelta, timezone
from elmos_mature_platform.types import (
    TenantEditionMapping,
    MigrationPrecheck,
    MigrationWave,
    TenantMigrationStatus,
)
from elmos_mature_platform.tenant_edition_migration_engine import TenantEditionMigrationEngine


class TestTenantEditionMigrationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = TenantEditionMigrationEngine()

    def _now(self):
        return datetime.now(timezone.utc)

    def test_create_mapping_success(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        res = self.engine.create_mapping(mapping)
        self.assertEqual(res, "map-1")
        status = self.engine.get_migration_status("map-1")
        self.assertEqual(status.status, TenantMigrationStatus.PLANNED)

    def test_create_mapping_duplicate(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        with self.assertRaises(ValueError):
            self.engine.create_mapping(mapping)

    def test_create_mapping_same_edition(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="standard"
        )
        with self.assertRaises(ValueError):
            self.engine.create_mapping(mapping)

    def test_precheck_success(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise",
            data_size_gb=500.0,
            feature_gaps=[]
        )
        self.engine.create_mapping(mapping)
        precheck = self.engine.precheck("map-1")
        self.assertTrue(precheck.overall_ready)
        status = self.engine.get_migration_status("map-1")
        self.assertEqual(status.status, TenantMigrationStatus.VALIDATING)
        self.assertTrue(status.validation_passed)

    def test_precheck_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.precheck("nonexistent")

    def test_precheck_failure_feature_gap(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise",
            feature_gaps=["custom_branding"]
        )
        self.engine.create_mapping(mapping)
        precheck = self.engine.precheck("map-1")
        self.assertFalse(precheck.overall_ready)
        self.assertIn("Feature gaps exist: custom_branding", precheck.blockers)
        status = self.engine.get_migration_status("map-1")
        self.assertEqual(status.status, TenantMigrationStatus.PLANNED)

    def test_precheck_failure_capacity(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise",
            data_size_gb=1500.0
        )
        self.engine.create_mapping(mapping)
        precheck = self.engine.precheck("map-1")
        self.assertFalse(precheck.overall_ready)
        self.assertIn("Data size 1500.0GB exceeds capacity.", precheck.blockers)

    def test_start_migration_success(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        res = self.engine.start_migration("map-1")
        self.assertEqual(res.status, TenantMigrationStatus.MIGRATING)
        self.assertNotEqual(res.started_at, "")

    def test_start_migration_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.start_migration("nonexistent")

    def test_start_migration_no_precheck(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        with self.assertRaises(ValueError):
            self.engine.start_migration("map-1")

    def test_start_migration_feature_gaps(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise",
            feature_gaps=["gap"]
        )
        self.engine.create_mapping(mapping)
        with self.assertRaises(ValueError):
            self.engine.start_migration("map-1")

    def test_start_migration_invalid_status(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        # Already migrating
        with self.assertRaises(ValueError):
            self.engine.start_migration("map-1")

    def test_complete_migration_success(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        res = self.engine.complete_migration("map-1")
        self.assertEqual(res.status, TenantMigrationStatus.COMPLETED)
        self.assertNotEqual(res.completed_at, "")

    def test_complete_migration_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.complete_migration("nonexistent")

    def test_complete_migration_invalid_status(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        # PLANNED -> cannot complete
        with self.assertRaises(ValueError):
            self.engine.complete_migration("map-1")

    def test_complete_migration_from_verifying(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        # Manually transition to VERIFYING for testing
        mapping = self.engine.get_migration_status("map-1")
        mapping.status = TenantMigrationStatus.VERIFYING
        res = self.engine.complete_migration("map-1")
        self.assertEqual(res.status, TenantMigrationStatus.COMPLETED)

    def test_rollback_migration_success_no_deadline(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        res = self.engine.rollback_migration("map-1")
        self.assertEqual(res.status, TenantMigrationStatus.ROLLED_BACK)

    def test_rollback_migration_success_with_deadline(self):
        deadline = (self._now() + timedelta(hours=1)).isoformat()
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise",
            rollback_deadline=deadline
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        res = self.engine.rollback_migration("map-1")
        self.assertEqual(res.status, TenantMigrationStatus.ROLLED_BACK)

    def test_rollback_migration_deadline_exceeded(self):
        deadline = (self._now() - timedelta(hours=1)).isoformat()
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise",
            rollback_deadline=deadline
        )
        self.engine.create_mapping(mapping)
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        with self.assertRaises(ValueError):
            self.engine.rollback_migration("map-1")

    def test_rollback_migration_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.rollback_migration("nonexistent")

    def test_rollback_migration_invalid_status(self):
        mapping = TenantEditionMapping(
            mapping_id="map-1",
            tenant_id="t-1",
            source_edition="standard",
            target_edition="enterprise"
        )
        self.engine.create_mapping(mapping)
        with self.assertRaises(ValueError):
            self.engine.rollback_migration("map-1")

    def test_create_wave_success(self):
        mapping = TenantEditionMapping(mapping_id="map-1", tenant_id="t-1", source_edition="s", target_edition="e")
        self.engine.create_mapping(mapping)
        wave = MigrationWave(wave_id="w-1", wave_name="Wave 1", mappings=["map-1"])
        res = self.engine.create_wave(wave)
        self.assertEqual(res, "w-1")

    def test_create_wave_duplicate(self):
        wave = MigrationWave(wave_id="w-1", wave_name="Wave 1", mappings=[])
        self.engine.create_wave(wave)
        with self.assertRaises(ValueError):
            self.engine.create_wave(wave)

    def test_create_wave_missing_mapping(self):
        wave = MigrationWave(wave_id="w-1", wave_name="Wave 1", mappings=["nonexistent"])
        with self.assertRaises(ValueError):
            self.engine.create_wave(wave)

    def test_execute_wave_success(self):
        m1 = TenantEditionMapping(mapping_id="map-1", tenant_id="t-1", source_edition="s", target_edition="e")
        m2 = TenantEditionMapping(mapping_id="map-2", tenant_id="t-2", source_edition="s", target_edition="e")
        self.engine.create_mapping(m1)
        self.engine.create_mapping(m2)
        self.engine.precheck("map-1")
        self.engine.precheck("map-2")

        wave = MigrationWave(wave_id="w-1", wave_name="Wave 1", mappings=["map-1", "map-2"], max_parallel=2)
        self.engine.create_wave(wave)
        self.engine.execute_wave("w-1")

        self.assertEqual(self.engine.get_migration_status("map-1").status, TenantMigrationStatus.MIGRATING)
        self.assertEqual(self.engine.get_migration_status("map-2").status, TenantMigrationStatus.MIGRATING)

    def test_execute_wave_max_parallel(self):
        m1 = TenantEditionMapping(mapping_id="map-1", tenant_id="t-1", source_edition="s", target_edition="e")
        m2 = TenantEditionMapping(mapping_id="map-2", tenant_id="t-2", source_edition="s", target_edition="e")
        self.engine.create_mapping(m1)
        self.engine.create_mapping(m2)
        self.engine.precheck("map-1")
        self.engine.precheck("map-2")

        wave = MigrationWave(wave_id="w-1", wave_name="Wave 1", mappings=["map-1", "map-2"], max_parallel=1)
        self.engine.create_wave(wave)
        self.engine.execute_wave("w-1")

        s1 = self.engine.get_migration_status("map-1").status
        s2 = self.engine.get_migration_status("map-2").status
        
        # Only one should be migrating
        statuses = [s1, s2]
        self.assertEqual(statuses.count(TenantMigrationStatus.MIGRATING), 1)
        self.assertEqual(statuses.count(TenantMigrationStatus.VALIDATING), 1)

    def test_execute_wave_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.execute_wave("nonexistent")

    def test_get_wave_progress(self):
        m1 = TenantEditionMapping(mapping_id="map-1", tenant_id="t-1", source_edition="s", target_edition="e")
        m2 = TenantEditionMapping(mapping_id="map-2", tenant_id="t-2", source_edition="s", target_edition="e")
        m3 = TenantEditionMapping(mapping_id="map-3", tenant_id="t-3", source_edition="s", target_edition="e")
        self.engine.create_mapping(m1)
        self.engine.create_mapping(m2)
        self.engine.create_mapping(m3)

        self.engine.precheck("map-1")
        self.engine.precheck("map-2")
        self.engine.start_migration("map-1")
        self.engine.complete_migration("map-1")
        self.engine.start_migration("map-2")

        wave = MigrationWave(wave_id="w-1", wave_name="W", mappings=["map-1", "map-2", "map-3"])
        self.engine.create_wave(wave)

        progress = self.engine.get_wave_progress("w-1")
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["in_progress"], 1)
        self.assertEqual(progress["remaining"], 1)
        self.assertEqual(progress["total"], 3)

    def test_get_wave_progress_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.get_wave_progress("nonexistent")

    def test_get_wave_progress_with_failures(self):
        m1 = TenantEditionMapping(mapping_id="map-1", tenant_id="t-1", source_edition="s", target_edition="e")
        self.engine.create_mapping(m1)
        self.engine.fail_migration("map-1", "error")
        wave = MigrationWave(wave_id="w-1", wave_name="W", mappings=["map-1"])
        self.engine.create_wave(wave)
        progress = self.engine.get_wave_progress("w-1")
        self.assertEqual(progress["completed"], 1)

    def test_get_migration_report_empty(self):
        report = self.engine.get_migration_report()
        self.assertEqual(report, {})

    def test_get_migration_report_populated(self):
        m1 = TenantEditionMapping(mapping_id="map-1", tenant_id="t-1", source_edition="standard", target_edition="enterprise")
        m2 = TenantEditionMapping(mapping_id="map-2", tenant_id="t-2", source_edition="standard", target_edition="enterprise")
        self.engine.create_mapping(m1)
        self.engine.create_mapping(m2)
        
        self.engine.precheck("map-1")
        self.engine.start_migration("map-1")
        self.engine.complete_migration("map-1")

        report = self.engine.get_migration_report()
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["by_status"]["completed"], 1)
        self.assertEqual(report["by_status"]["planned"], 1)
        self.assertEqual(report["by_edition_pair"]["standard->enterprise"], 2)
        self.assertEqual(report["completion_rate"], 0.5)

if __name__ == "__main__":
    unittest.main()
