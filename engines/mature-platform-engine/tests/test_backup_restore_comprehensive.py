"""Comprehensive tests for BackupRestoreEngine."""

import unittest
from datetime import datetime, timezone, timedelta
from elmos_mature_platform.backup_restore_engine import BackupRestoreEngine
from elmos_mature_platform.types import BackupType, RestoreVerdict, RestoreRequest

class TestBackupRestoreEngine(unittest.TestCase):
    def setUp(self):
        self.engine = BackupRestoreEngine()
        self.source = "db-main-cluster"
        self.region = "us-east-1"
        self.kms_key = "kms-key-123"

    def test_create_full_backup(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"some data", self.kms_key, self.region)
        self.assertIsNotNone(record)
        self.assertEqual(record.backup_type, BackupType.FULL)
        self.assertEqual(record.source_name, self.source)

    def test_create_incremental_without_parent_fails(self):
        with self.assertRaises(ValueError):
            self.engine.create_backup(self.source, BackupType.INCREMENTAL, b"inc data", self.kms_key, self.region)

    def test_create_incremental_with_invalid_parent_fails(self):
        with self.assertRaises(ValueError):
            self.engine.create_backup(self.source, BackupType.INCREMENTAL, b"inc data", self.kms_key, self.region, parent_backup_id="invalid-id")

    def test_create_incremental_with_parent_succeeds(self):
        parent = self.engine.create_backup(self.source, BackupType.FULL, b"full data", self.kms_key, self.region)
        inc = self.engine.create_backup(self.source, BackupType.INCREMENTAL, b"inc data", self.kms_key, self.region, parent_backup_id=parent.backup_id)
        self.assertEqual(inc.parent_backup_id, parent.backup_id)

    def test_list_backups_empty(self):
        self.assertEqual(self.engine.list_backups(self.source), [])

    def test_list_backups_multiple(self):
        self.engine.create_backup(self.source, BackupType.FULL, b"data1", self.kms_key, self.region)
        self.engine.create_backup(self.source, BackupType.FULL, b"data2", self.kms_key, self.region)
        self.assertEqual(len(self.engine.list_backups(self.source)), 2)

    def test_list_backups_filtered_by_source(self):
        self.engine.create_backup("source-a", BackupType.FULL, b"data", self.kms_key, self.region)
        self.engine.create_backup("source-b", BackupType.FULL, b"data", self.kms_key, self.region)
        self.assertEqual(len(self.engine.list_backups("source-a")), 1)

    def test_get_backup_exists(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        fetched = self.engine.get_backup(record.backup_id)
        self.assertEqual(fetched.backup_id, record.backup_id)

    def test_get_backup_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.get_backup("invalid-id")

    def test_verify_backup_integrity_success(self):
        data = b"integrity check data"
        record = self.engine.create_backup(self.source, BackupType.FULL, data, self.kms_key, self.region)
        self.assertTrue(self.engine.verify_backup_integrity(record.backup_id, data))

    def test_verify_backup_integrity_failure(self):
        data = b"integrity check data"
        record = self.engine.create_backup(self.source, BackupType.FULL, data, self.kms_key, self.region)
        self.assertFalse(self.engine.verify_backup_integrity(record.backup_id, b"tampered data"))

    def test_restore_backup_non_isolated_fails(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        req = RestoreRequest(restore_id="r1", backup_id=record.backup_id, target_name="target", isolated_environment=False)
        with self.assertRaises(PermissionError):
            self.engine.restore_backup(req)

    def test_restore_backup_success(self):
        data = b"0" * 1000 # 1000 bytes
        record = self.engine.create_backup(self.source, BackupType.FULL, data, self.kms_key, self.region)
        req = RestoreRequest(restore_id="r1", backup_id=record.backup_id, target_name="target", isolated_environment=True)
        res = self.engine.restore_backup(req)
        self.assertEqual(res.verdict, RestoreVerdict.SUCCESS)
        self.assertEqual(res.restored_rows, 10) # 1000 // 100

    def test_restore_backup_integrity_mismatch(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        # Tamper with internal payload
        self.engine._payloads[record.backup_id] = b"tampered"
        req = RestoreRequest(restore_id="r1", backup_id=record.backup_id, target_name="target", isolated_environment=True)
        res = self.engine.restore_backup(req)
        self.assertEqual(res.verdict, RestoreVerdict.INTEGRITY_MISMATCH)

    def test_dr_drill_rto_met_rpo_met(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        res = self.engine.run_restore_drill("restore_drill", record.backup_id, target_rto=60, target_rpo=300, simulated_restore_time=50, simulated_data_lag=200)
        self.assertTrue(res.rto_met)
        self.assertTrue(res.rpo_met)
        self.assertTrue(res.passed)

    def test_dr_drill_rto_missed(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        res = self.engine.run_restore_drill("restore_drill", record.backup_id, target_rto=60, target_rpo=300, simulated_restore_time=70, simulated_data_lag=200)
        self.assertFalse(res.rto_met)
        self.assertTrue(res.rpo_met)
        self.assertFalse(res.passed)

    def test_dr_drill_rpo_missed(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        res = self.engine.run_restore_drill("restore_drill", record.backup_id, target_rto=60, target_rpo=300, simulated_restore_time=50, simulated_data_lag=400)
        self.assertTrue(res.rto_met)
        self.assertFalse(res.rpo_met)
        self.assertFalse(res.passed)

    def test_dr_drill_both_missed(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        res = self.engine.run_restore_drill("restore_drill", record.backup_id, target_rto=60, target_rpo=300, simulated_restore_time=70, simulated_data_lag=400)
        self.assertFalse(res.rto_met)
        self.assertFalse(res.rpo_met)
        self.assertFalse(res.passed)
        self.assertEqual(len(res.findings), 2)

    def test_dr_drill_invalid_backup(self):
        with self.assertRaises(KeyError):
            self.engine.run_restore_drill("restore_drill", "invalid-id", 60, 300, 50, 200)

    def test_enforce_retention_no_deletion(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region, retention_days=10)
        # Check against today
        cutoff = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        deleted = self.engine.enforce_retention(cutoff)
        self.assertEqual(len(deleted), 0)

    def test_enforce_retention_with_deletion(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region, retention_days=10)
        # Check against future > 10 days
        cutoff = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
        deleted = self.engine.enforce_retention(cutoff)
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0], record.backup_id)
        self.assertNotIn(record.backup_id, self.engine._backups)

    def test_get_backup_chain_single(self):
        full = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        chain = self.engine.get_backup_chain(full.backup_id)
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].backup_id, full.backup_id)

    def test_get_backup_chain_multiple(self):
        full = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        inc1 = self.engine.create_backup(self.source, BackupType.INCREMENTAL, b"data", self.kms_key, self.region, parent_backup_id=full.backup_id)
        inc2 = self.engine.create_backup(self.source, BackupType.INCREMENTAL, b"data", self.kms_key, self.region, parent_backup_id=inc1.backup_id)
        chain = self.engine.get_backup_chain(inc2.backup_id)
        self.assertEqual(len(chain), 3)
        self.assertEqual(chain[0].backup_id, full.backup_id)
        self.assertEqual(chain[1].backup_id, inc1.backup_id)
        self.assertEqual(chain[2].backup_id, inc2.backup_id)

    def test_validate_pitr_range_empty(self):
        self.assertFalse(self.engine.validate_pitr_range(self.source, datetime.now(timezone.utc).isoformat()))

    def test_validate_pitr_range_outside(self):
        record = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        # Outside (before)
        target = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertFalse(self.engine.validate_pitr_range(self.source, target))

    def test_validate_pitr_range_inside(self):
        # We need two backups to create a range
        rec1 = self.engine.create_backup(self.source, BackupType.FULL, b"data", self.kms_key, self.region)
        # Manipulate created_at
        rec1.created_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        
        rec2 = self.engine.create_backup(self.source, BackupType.INCREMENTAL, b"data", self.kms_key, self.region, parent_backup_id=rec1.backup_id)
        rec2.created_at = (datetime.now(timezone.utc)).isoformat()
        
        target = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertTrue(self.engine.validate_pitr_range(self.source, target))

    def test_get_backup_report_empty(self):
        report = self.engine.get_backup_report()
        self.assertEqual(report["total_backups"], 0)
        self.assertEqual(report["total_size_bytes"], 0)

    def test_get_backup_report_populated(self):
        self.engine.create_backup(self.source, BackupType.FULL, b"hello", self.kms_key, self.region) # 5 bytes
        self.engine.create_backup(self.source, BackupType.FULL, b"world", self.kms_key, self.region) # 5 bytes
        report = self.engine.get_backup_report()
        self.assertEqual(report["total_backups"], 2)
        self.assertEqual(report["total_size_bytes"], 10)
        self.assertIsNotNone(report["oldest_backup"])
        self.assertIsNotNone(report["newest_backup"])
        self.assertTrue(report["retention_compliant"])

if __name__ == '__main__':
    unittest.main()
