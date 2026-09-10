import unittest
from datetime import datetime
from typing import List, Dict

from elmos_mature_platform.types import (
    MigrationCompatLevel,
    MigrationSchemaChangeType,
    MigrationSchemaChange,
    DbMigrationScript,
)
from elmos_mature_platform.database_migration_compatibility_engine import DatabaseMigrationCompatibilityEngine

class TestDatabaseMigrationCompatibilityComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = DatabaseMigrationCompatibilityEngine()

    def test_01_register_change(self):
        c = MigrationSchemaChange(
            change_id="c1",
            change_type=MigrationSchemaChangeType.ADD_COLUMN,
            table_name="users",
            column_name="age",
            nullable=True
        )
        cid = self.engine.register_change(c)
        self.assertEqual(cid, "c1")
        self.assertIn("c1", self.engine.changes)

    def test_02_classify_change_add_column_nullable(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.ADD_COLUMN, table_name="users", column_name="age", nullable=True)
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.FULLY_COMPATIBLE)

    def test_03_classify_change_add_column_with_default(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.ADD_COLUMN, table_name="users", column_name="age", nullable=False, has_default=True)
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.FULLY_COMPATIBLE)

    def test_04_classify_change_add_column_not_nullable(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.ADD_COLUMN, table_name="users", column_name="age", nullable=False, has_default=False)
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BREAKING)

    def test_05_classify_change_drop_column(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_COLUMN, table_name="users", column_name="age")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BREAKING)

    def test_06_classify_change_add_table(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.ADD_TABLE, table_name="logs")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.FULLY_COMPATIBLE)

    def test_07_classify_change_drop_table(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_TABLE, table_name="logs")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BREAKING)

    def test_08_classify_change_add_index(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.ADD_INDEX, table_name="users")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.FULLY_COMPATIBLE)

    def test_09_classify_change_drop_index(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_INDEX, table_name="users")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BACKWARD_COMPATIBLE)

    def test_10_classify_change_modify_column_compatible(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.MODIFY_COLUMN, table_name="users", column_name="age", old_type="int", new_type="int")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BACKWARD_COMPATIBLE)

    def test_11_classify_change_modify_column_breaking(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.MODIFY_COLUMN, table_name="users", column_name="age", old_type="int", new_type="string")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BREAKING)

    def test_12_classify_change_rename(self):
        c = MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.RENAME, table_name="users", column_name="age")
        self.engine.register_change(c)
        level = self.engine.classify_change("c1")
        self.assertEqual(level, MigrationCompatLevel.BREAKING)

    def test_13_create_migration(self):
        s = DbMigrationScript(script_id="s1", version="1.0.0", description="Init")
        sid = self.engine.create_migration(s)
        self.assertEqual(sid, "s1")
        self.assertIn("s1", self.engine.scripts)

    def test_14_validate_migration_order_valid(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        self.engine.create_migration(DbMigrationScript(script_id="s2", version="1.1.0", description="Update"))
        res = self.engine.validate_migration_order(["s1", "s2"])
        self.assertTrue(res["valid"])

    def test_15_validate_migration_order_invalid(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.1.0", description="Update"))
        self.engine.create_migration(DbMigrationScript(script_id="s2", version="1.0.0", description="Init"))
        res = self.engine.validate_migration_order(["s1", "s2"])
        self.assertFalse(res["valid"])
        self.assertTrue(any("ordering issue" in err for err in res["errors"]))

    def test_16_validate_migration_order_missing_change(self):
        s = DbMigrationScript(script_id="s1", version="1.0.0", description="Init", changes=["c_missing"])
        self.engine.create_migration(s)
        res = self.engine.validate_migration_order(["s1"])
        self.assertFalse(res["valid"])

    def test_17_check_compatibility_compatible(self):
        self.engine.register_change(MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.ADD_TABLE, table_name="t"))
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="T", changes=["c1"]))
        res = self.engine.check_compatibility("s1")
        self.assertTrue(res["compatible"])
        self.assertFalse(res["has_breaking"])

    def test_18_check_compatibility_breaking_without_downtime(self):
        self.engine.register_change(MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_TABLE, table_name="t"))
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="T", changes=["c1"], requires_downtime=False))
        res = self.engine.check_compatibility("s1")
        self.assertFalse(res["compatible"])
        self.assertTrue(res["has_breaking"])
        self.assertIn("Migration has breaking changes but requires_downtime is False", res["error"])

    def test_19_check_compatibility_breaking_with_downtime(self):
        self.engine.register_change(MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_TABLE, table_name="t"))
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="T", changes=["c1"], requires_downtime=True))
        res = self.engine.check_compatibility("s1")
        self.assertFalse(res["compatible"])  # still has_breaking, so it returns compatible=False conceptually?
        # wait, the logic: "compatible: not has_breaking"
        self.assertFalse(res["compatible"])
        self.assertTrue(res["has_breaking"])

    def test_20_mark_reviewed(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        s = self.engine.mark_reviewed("s1", "bob")
        self.assertTrue(s.reviewed)

    def test_21_apply_migration_unreviewed(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        with self.assertRaises(ValueError):
            self.engine.apply_migration("s1")

    def test_22_apply_migration_success(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        self.engine.mark_reviewed("s1", "bob")
        s = self.engine.apply_migration("s1")
        self.assertTrue(s.applied)
        self.assertTrue(s.applied_at != "")

    def test_23_rollback_migration_unapplied(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        with self.assertRaises(ValueError):
            self.engine.rollback_migration("s1")

    def test_24_rollback_migration_no_down_sql(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        self.engine.mark_reviewed("s1", "bob")
        self.engine.apply_migration("s1")
        with self.assertRaises(ValueError):
            self.engine.rollback_migration("s1")

    def test_25_rollback_migration_success(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init", down_sql="DROP"))
        self.engine.mark_reviewed("s1", "bob")
        self.engine.apply_migration("s1")
        s = self.engine.rollback_migration("s1")
        self.assertFalse(s.applied)
        self.assertEqual(s.applied_at, "")

    def test_26_test_rollback_no_down_sql(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init"))
        with self.assertRaises(ValueError):
            self.engine.test_rollback("s1")

    def test_27_test_rollback_success(self):
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init", down_sql="DROP"))
        res = self.engine.test_rollback("s1")
        self.assertTrue(res)
        self.assertTrue(self.engine.scripts["s1"].rollback_tested)

    def test_28_get_migration_plan(self):
        self.engine.register_change(MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_TABLE, table_name="t"))
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init", estimated_duration_seconds=10, changes=["c1"], requires_downtime=True))
        plan = self.engine.get_migration_plan(["s1"])
        self.assertEqual(plan["total_estimated_duration_seconds"], 10)
        self.assertTrue(plan["requires_downtime"])
        self.assertEqual(plan["total_breaking_changes"], 1)

    def test_29_get_compatibility_report(self):
        self.engine.register_change(MigrationSchemaChange(change_id="c1", change_type=MigrationSchemaChangeType.DROP_TABLE, table_name="t"))
        self.engine.create_migration(DbMigrationScript(script_id="s1", version="1.0.0", description="Init", changes=["c1"]))
        report = self.engine.get_compatibility_report()
        self.assertEqual(report["total_changes"], 1)
        self.assertEqual(report["compatibility_counts"]["breaking"], 1)
        self.assertEqual(report["coverage_percentage"], 100.0)
        self.assertIn("c1", report["breaking_changes"])

    def test_30_classify_change_invalid_id(self):
        with self.assertRaises(ValueError):
            self.engine.classify_change("fake")

    def test_31_check_compatibility_invalid_script(self):
        with self.assertRaises(ValueError):
            self.engine.check_compatibility("fake")

    def test_32_validate_migration_order_empty(self):
        res = self.engine.validate_migration_order([])
        self.assertTrue(res["valid"])
        self.assertEqual(res["errors"], [])

if __name__ == '__main__':
    unittest.main()
