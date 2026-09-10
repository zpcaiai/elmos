import unittest
from elmos_mature_platform.types import (
    DbMigrationPhase,
    SchemaChangeType,
    SchemaChange,
    ExpandContractPlan,
    SchemaValidation
)
from elmos_mature_platform.database_expand_contract_engine import DatabaseExpandContractEngine

class TestDatabaseExpandContractEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DatabaseExpandContractEngine()

    def _create_valid_plan(self, plan_id="p1"):
        return ExpandContractPlan(
            plan_id=plan_id,
            description="Test plan",
            expand_changes=[
                SchemaChange(
                    change_id="c1",
                    change_type=SchemaChangeType.ADD_COLUMN,
                    table_name="users",
                    column_name="age",
                    data_type="int",
                    nullable=True
                )
            ],
            contract_changes=[
                SchemaChange(
                    change_id="c2",
                    change_type=SchemaChangeType.DROP_COLUMN,
                    table_name="users",
                    column_name="old_age"
                )
            ]
        )

    def test_create_plan_success(self):
        plan = self._create_valid_plan()
        plan_id = self.engine.create_plan(plan)
        self.assertEqual(plan_id, "p1")
        saved_plan = self.engine.get_plan("p1")
        self.assertEqual(saved_plan.phase, DbMigrationPhase.PENDING)
        self.assertTrue(saved_plan.created_at)

    def test_create_plan_duplicate(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.engine.create_plan(self._create_valid_plan())

    def test_get_plan_not_found(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.engine.get_plan("missing")

    def test_validate_plan_valid(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        val = self.engine.validate_plan("p1")
        self.assertTrue(val.valid)
        self.assertEqual(len(val.breaking_changes), 0)

    def test_validate_plan_drop_in_expand(self):
        plan = self._create_valid_plan()
        plan.expand_changes.append(
            SchemaChange(change_id="c3", change_type=SchemaChangeType.DROP_TABLE, table_name="temp")
        )
        self.engine.create_plan(plan)
        val = self.engine.validate_plan("p1")
        self.assertFalse(val.valid)
        self.assertEqual(len(val.breaking_changes), 1)

    def test_validate_plan_non_nullable_no_default(self):
        plan = self._create_valid_plan()
        plan.expand_changes.append(
            SchemaChange(change_id="c3", change_type=SchemaChangeType.ADD_COLUMN, table_name="users", column_name="req", nullable=False, default_value="")
        )
        self.engine.create_plan(plan)
        val = self.engine.validate_plan("p1")
        self.assertFalse(val.valid)

    def test_validate_plan_non_nullable_with_default(self):
        plan = self._create_valid_plan()
        plan.expand_changes.append(
            SchemaChange(change_id="c3", change_type=SchemaChangeType.ADD_COLUMN, table_name="users", column_name="req", nullable=False, default_value="0")
        )
        self.engine.create_plan(plan)
        val = self.engine.validate_plan("p1")
        self.assertTrue(val.valid)

    def test_validate_plan_contract_warnings(self):
        plan = self._create_valid_plan()
        plan.contract_changes.append(
            SchemaChange(change_id="c3", change_type=SchemaChangeType.ADD_TABLE, table_name="new_tbl")
        )
        self.engine.create_plan(plan)
        val = self.engine.validate_plan("p1")
        self.assertTrue(val.valid)
        self.assertEqual(len(val.warnings), 1)

    def test_check_phase_transition_pending_to_expand(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.assertTrue(self.engine.check_phase_transition("p1", DbMigrationPhase.EXPAND))

    def test_check_phase_transition_pending_to_migrate_invalid(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.assertFalse(self.engine.check_phase_transition("p1", DbMigrationPhase.MIGRATE))

    def test_start_expand_success(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        updated_plan = self.engine.start_expand("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.EXPAND)
        self.assertTrue(updated_plan.started_at)

    def test_start_expand_blocks_breaking_changes(self):
        plan = self._create_valid_plan()
        plan.expand_changes.append(
            SchemaChange(change_id="c3", change_type=SchemaChangeType.DROP_TABLE, table_name="temp")
        )
        self.engine.create_plan(plan)
        with self.assertRaisesRegex(ValueError, "breaking changes"):
            self.engine.start_expand("p1")

    def test_start_migrate_success(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        updated_plan = self.engine.start_migrate("p1", 100)
        self.assertEqual(updated_plan.phase, DbMigrationPhase.MIGRATE)
        self.assertEqual(updated_plan.rows_migrated, 100)

    def test_start_migrate_invalid_transition(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        with self.assertRaisesRegex(ValueError, "Invalid transition"):
            self.engine.start_migrate("p1", 100)

    def test_start_contract_success(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        updated_plan = self.engine.start_contract("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.CONTRACT)

    def test_start_contract_invalid_transition(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        with self.assertRaisesRegex(ValueError, "Invalid transition"):
            self.engine.start_contract("p1")

    def test_complete_plan_success(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        self.engine.start_contract("p1")
        updated_plan = self.engine.complete_plan("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.COMPLETED)
        self.assertTrue(updated_plan.completed_at)

    def test_complete_plan_invalid_transition(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        with self.assertRaisesRegex(ValueError, "Invalid transition"):
            self.engine.complete_plan("p1")

    def test_rollback_from_pending(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        updated_plan = self.engine.rollback_plan("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.ROLLED_BACK)

    def test_rollback_from_expand(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        updated_plan = self.engine.rollback_plan("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.ROLLED_BACK)

    def test_rollback_from_migrate(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        updated_plan = self.engine.rollback_plan("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.ROLLED_BACK)

    def test_rollback_from_contract(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        self.engine.start_contract("p1")
        updated_plan = self.engine.rollback_plan("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.ROLLED_BACK)

    def test_rollback_already_rolled_back(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.rollback_plan("p1")
        updated_plan = self.engine.rollback_plan("p1")
        self.assertEqual(updated_plan.phase, DbMigrationPhase.ROLLED_BACK)

    def test_rollback_completed_plan_fails(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        self.engine.start_contract("p1")
        self.engine.complete_plan("p1")
        with self.assertRaisesRegex(ValueError, "Cannot rollback a completed plan"):
            self.engine.rollback_plan("p1")

    def test_list_plans_all(self):
        self.engine.create_plan(self._create_valid_plan("p1"))
        self.engine.create_plan(self._create_valid_plan("p2"))
        plans = self.engine.list_plans()
        self.assertEqual(len(plans), 2)

    def test_list_plans_by_phase(self):
        self.engine.create_plan(self._create_valid_plan("p1"))
        self.engine.create_plan(self._create_valid_plan("p2"))
        self.engine.start_expand("p1")
        pending = self.engine.list_plans(DbMigrationPhase.PENDING)
        expand = self.engine.list_plans(DbMigrationPhase.EXPAND)
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(expand), 1)

    def test_get_migration_report(self):
        plan1 = self._create_valid_plan("p1")
        self.engine.create_plan(plan1)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 50)

        plan2 = self._create_valid_plan("p2")
        self.engine.create_plan(plan2)
        
        plan3 = self._create_valid_plan("p3")
        plan3.expand_changes.append(
            SchemaChange(change_id="c3", change_type=SchemaChangeType.DROP_TABLE, table_name="temp")
        )
        self.engine.create_plan(plan3)
        
        report = self.engine.get_migration_report()
        self.assertEqual(report["total_plans"], 3)
        self.assertEqual(report["total_rows_migrated"], 50)
        self.assertEqual(report["total_breaking_changes_detected"], 1)
        self.assertEqual(report["plans_by_phase"]["pending"], 2)
        self.assertEqual(report["plans_by_phase"]["migrate"], 1)

    def test_start_migrate_accumulates_rows(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        self.engine.start_migrate("p1", 50)
        self.assertEqual(self.engine.get_plan("p1").rows_migrated, 150)

    def test_start_migrate_from_contract_fails(self):
        plan = self._create_valid_plan()
        self.engine.create_plan(plan)
        self.engine.start_expand("p1")
        self.engine.start_migrate("p1", 100)
        self.engine.start_contract("p1")
        with self.assertRaisesRegex(ValueError, "Invalid transition"):
            self.engine.start_migrate("p1", 50)

if __name__ == '__main__':
    unittest.main()
