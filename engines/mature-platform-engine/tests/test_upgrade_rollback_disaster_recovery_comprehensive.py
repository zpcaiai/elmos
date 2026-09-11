import unittest
from elmos_mature_platform.upgrade_rollback_disaster_recovery_engine import (
    UpgradeRollbackDisasterRecoveryEngine,
)
from elmos_mature_platform.types import (
    DisasterRecoveryDrillRecord,
    DisasterRecoveryStrategy,
    RecoveryPlanStatus,
    RollbackExecutionStep,
    RollbackTriggerType,
    UpgradeRollbackPlan,
)


class TestUpgradeRollbackDisasterRecoveryComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = UpgradeRollbackDisasterRecoveryEngine()

    def test_create_rollback_plan_success(self):
        plan = UpgradeRollbackPlan(
            plan_id="p-1",
            deployment_id="dep-prod-1",
            target_version="v2.0.0",
            rollback_version="v1.9.4",
            strategy=DisasterRecoveryStrategy.SNAPSHOT_RESTORE,
        )
        plan_id = self.engine.create_rollback_plan(plan)
        self.assertEqual(plan_id, "p-1")
        self.assertEqual(plan.status, RecoveryPlanStatus.DRAFT)
        self.assertTrue(bool(plan.created_at))

    def test_create_rollback_plan_invalid_identical_versions(self):
        plan = UpgradeRollbackPlan(
            plan_id="p-bad",
            deployment_id="dep-1",
            target_version="v2.0.0",
            rollback_version="v2.0.0",
        )
        with self.assertRaises(ValueError):
            self.engine.create_rollback_plan(plan)

    def test_add_execution_steps_and_order(self):
        plan = UpgradeRollbackPlan(
            plan_id="p-2",
            deployment_id="dep-2",
            target_version="v2.1",
            rollback_version="v2.0",
        )
        self.engine.create_rollback_plan(plan)

        step2 = RollbackExecutionStep(
            step_id="s-2",
            name="Restore database",
            order=2,
            target_component="postgres",
            command_ref="pg_restore_snapshot",
        )
        step1 = RollbackExecutionStep(
            step_id="s-1",
            name="Drain traffic",
            order=1,
            target_component="gateway",
            command_ref="gateway_drain",
        )

        self.engine.add_execution_step("p-2", step2)
        updated = self.engine.add_execution_step("p-2", step1)

        self.assertEqual(len(updated.steps), 2)
        self.assertEqual(updated.steps[0].step_id, "s-1")
        self.assertEqual(updated.steps[1].step_id, "s-2")

    def test_validate_plan_valid_and_invalid(self):
        plan = UpgradeRollbackPlan(
            plan_id="p-3",
            deployment_id="dep-3",
            target_version="v3.0",
            rollback_version="v2.9",
        )
        self.engine.create_rollback_plan(plan)

        # Empty steps -> invalid
        self.assertFalse(self.engine.validate_plan("p-3"))

        step = RollbackExecutionStep(
            step_id="s-valid",
            name="Revert container tag",
            order=1,
            target_component="app-server",
            command_ref="kubectl_rollout_undo",
        )
        self.engine.add_execution_step("p-3", step)
        self.assertTrue(self.engine.validate_plan("p-3"))
        self.assertEqual(plan.status, RecoveryPlanStatus.VALIDATED)

    def test_trigger_rollback_and_step_execution(self):
        plan = UpgradeRollbackPlan(
            plan_id="p-4",
            deployment_id="dep-4",
            target_version="v4.0",
            rollback_version="v3.9",
        )
        self.engine.create_rollback_plan(plan)
        step = RollbackExecutionStep(
            step_id="s-run",
            name="Kill worker pool",
            order=1,
            target_component="worker",
            command_ref="scale_down",
        )
        self.engine.add_execution_step("p-4", step)
        self.engine.validate_plan("p-4")

        self.engine.trigger_rollback("p-4", RollbackTriggerType.ERROR_RATE_EXCEEDED, operator="sre-oncall")
        self.assertEqual(plan.status, RecoveryPlanStatus.EXECUTING)

        step_res = self.engine.execute_step("p-4", "s-run", success=True)
        self.assertEqual(step_res.status, "completed")
        self.assertTrue(bool(step_res.executed_at))

    def test_finalize_rollback_success_and_failure(self):
        # Successful flow
        plan_ok = UpgradeRollbackPlan(
            plan_id="p-ok",
            deployment_id="dep-ok",
            target_version="v1.2",
            rollback_version="v1.1",
        )
        self.engine.create_rollback_plan(plan_ok)
        step_ok = RollbackExecutionStep(
            step_id="s-ok",
            name="Revert DNS",
            order=1,
            target_component="route53",
            command_ref="dns_switch",
        )
        self.engine.add_execution_step("p-ok", step_ok)
        self.engine.validate_plan("p-ok")
        self.engine.trigger_rollback("p-ok", RollbackTriggerType.HEALTH_CHECK_FAILED)
        self.engine.execute_step("p-ok", "s-ok", success=True)
        final_ok = self.engine.finalize_rollback("p-ok", actual_downtime_seconds=45, data_loss_detected=False)

        self.assertEqual(final_ok.status, RecoveryPlanStatus.COMPLETED)
        self.assertEqual(final_ok.actual_downtime_seconds, 45)
        self.assertFalse(final_ok.data_loss_detected)

        # Failure flow
        plan_fail = UpgradeRollbackPlan(
            plan_id="p-fail",
            deployment_id="dep-fail",
            target_version="v1.2",
            rollback_version="v1.1",
        )
        self.engine.create_rollback_plan(plan_fail)
        step_fail = RollbackExecutionStep(
            step_id="s-fail",
            name="Restore S3 bucket",
            order=1,
            target_component="storage",
            command_ref="s3_sync",
        )
        self.engine.add_execution_step("p-fail", step_fail)
        self.engine.validate_plan("p-fail")
        self.engine.trigger_rollback("p-fail", RollbackTriggerType.CORRUPTION_DETECTED)
        self.engine.execute_step("p-fail", "s-fail", success=False, error="Timeout during sync")
        final_fail = self.engine.finalize_rollback("p-fail", actual_downtime_seconds=120, data_loss_detected=True)

        self.assertEqual(final_fail.status, RecoveryPlanStatus.FAILED)
        self.assertTrue(final_fail.data_loss_detected)

    def test_record_and_evaluate_dr_drill(self):
        drill_pass = DisasterRecoveryDrillRecord(
            drill_id="d-pass",
            plan_id="p-drill-1",
            edition_type="sovereign",
            simulated_failure=RollbackTriggerType.LATENCY_SPIKE,
            rto_seconds=120,
            rpo_seconds=30,
            target_rto_seconds=300,
            target_rpo_seconds=60,
        )
        did = self.engine.record_dr_drill(drill_pass)
        self.assertTrue(self.engine.evaluate_drill_compliance(did))

        drill_breach = DisasterRecoveryDrillRecord(
            drill_id="d-breach",
            plan_id="p-drill-2",
            edition_type="air_gapped",
            simulated_failure=RollbackTriggerType.CORRUPTION_DETECTED,
            rto_seconds=600,
            rpo_seconds=120,
            target_rto_seconds=300,
            target_rpo_seconds=60,
        )
        did2 = self.engine.record_dr_drill(drill_breach)
        self.assertFalse(self.engine.evaluate_drill_compliance(did2))

    def test_get_active_recovery_plans_and_metrics(self):
        # Initially 0
        metrics0 = self.engine.get_rollback_metrics()
        self.assertEqual(metrics0["total_plans"], 0)

        plan = UpgradeRollbackPlan(
            plan_id="p-active",
            deployment_id="dep-5",
            target_version="v5.0",
            rollback_version="v4.9",
        )
        self.engine.create_rollback_plan(plan)
        step = RollbackExecutionStep(
            step_id="s-act",
            name="Revert app",
            order=1,
            target_component="app",
            command_ref="revert",
        )
        self.engine.add_execution_step("p-active", step)
        self.engine.validate_plan("p-active")

        active = self.engine.get_active_recovery_plans()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].plan_id, "p-active")


if __name__ == "__main__":
    unittest.main()
