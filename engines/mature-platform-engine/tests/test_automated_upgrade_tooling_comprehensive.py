import unittest
from datetime import datetime
from elmos_mature_platform.types import (
    UpgradePlaybook,
    UpgradeStep,
    UpgradeToolStatus,
    UpgradeToolAction
)
from elmos_mature_platform.automated_upgrade_tooling_engine import AutomatedUpgradeToolingEngine

class TestAutomatedUpgradeToolingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AutomatedUpgradeToolingEngine()
        self.pb = UpgradePlaybook(
            playbook_id="pb1",
            name="Test PB",
            from_version="1.0",
            to_version="2.0"
        )
        self.engine.create_playbook(self.pb)

    def test_create_playbook_success(self):
        pb2 = UpgradePlaybook(playbook_id="pb2", name="PB2", from_version="1.0", to_version="2.0")
        pid = self.engine.create_playbook(pb2)
        self.assertEqual(pid, "pb2")

    def test_create_playbook_duplicate(self):
        with self.assertRaises(ValueError):
            self.engine.create_playbook(self.pb)

    def test_add_step_success(self):
        step = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="Desc")
        pb = self.engine.add_step("pb1", step)
        self.assertIn("s1", pb.steps)

    def test_add_step_ordering(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=2)
        s2 = UpgradeStep(step_id="s2", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        pb = self.engine.add_step("pb1", s2)
        self.assertEqual(pb.steps, ["s2", "s1"])

    def test_add_step_duplicate(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="")
        self.engine.add_step("pb1", s1)
        with self.assertRaises(ValueError):
            self.engine.add_step("pb1", s1)

    def test_add_step_not_pending(self):
        self.engine.start_playbook("pb1")
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="")
        with self.assertRaises(ValueError):
            self.engine.add_step("pb1", s1)

    def test_validate_playbook_valid(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        s2 = UpgradeStep(step_id="s2", action=UpgradeToolAction.BACKUP, description="", order=2, preconditions=["s1"])
        self.engine.add_step("pb1", s1)
        self.engine.add_step("pb1", s2)
        res = self.engine.validate_playbook("pb1")
        self.assertTrue(res["valid"])

    def test_validate_playbook_invalid_precondition_not_exist(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", preconditions=["s99"])
        self.engine.add_step("pb1", s1)
        res = self.engine.validate_playbook("pb1")
        self.assertFalse(res["valid"])

    def test_validate_playbook_invalid_rollback_not_exist(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", rollback_step_id="r1")
        self.engine.add_step("pb1", s1)
        res = self.engine.validate_playbook("pb1")
        self.assertFalse(res["valid"])

    def test_validate_playbook_invalid_precondition_order(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=2, preconditions=["s2"])
        s2 = UpgradeStep(step_id="s2", action=UpgradeToolAction.BACKUP, description="", order=3)
        self.engine.add_step("pb1", s1)
        self.engine.add_step("pb1", s2)
        res = self.engine.validate_playbook("pb1")
        self.assertFalse(res["valid"])

    def test_start_playbook_success(self):
        pb = self.engine.start_playbook("pb1")
        self.assertEqual(pb.status, UpgradeToolStatus.RUNNING)

    def test_start_playbook_already_started(self):
        self.engine.start_playbook("pb1")
        with self.assertRaises(ValueError):
            self.engine.start_playbook("pb1")

    def test_start_playbook_invalid(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", rollback_step_id="r1")
        self.engine.add_step("pb1", s1)
        with self.assertRaises(ValueError):
            self.engine.start_playbook("pb1")

    def test_execute_step_success(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        step = self.engine.execute_step("pb1", "s1")
        self.assertEqual(step.status, UpgradeToolStatus.SUCCESS)

    def test_execute_step_not_running(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        with self.assertRaises(ValueError):
            self.engine.execute_step("pb1", "s1")

    def test_execute_step_precondition_failed(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        s2 = UpgradeStep(step_id="s2", action=UpgradeToolAction.BACKUP, description="", order=2, preconditions=["s1"])
        self.engine.add_step("pb1", s1)
        self.engine.add_step("pb1", s2)
        self.engine.start_playbook("pb1")
        with self.assertRaises(ValueError):
            self.engine.execute_step("pb1", "s2")

    def test_execute_step_idempotent(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        self.engine.execute_step("pb1", "s1")
        step2 = self.engine.execute_step("pb1", "s1")
        self.assertEqual(step2.status, UpgradeToolStatus.SUCCESS)

    def test_fail_step(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        step = self.engine.fail_step("pb1", "s1", "err")
        self.assertEqual(step.status, UpgradeToolStatus.FAILED)

    def test_auto_rollback_triggered_on_fail(self):
        r1 = UpgradeStep(step_id="r1", action=UpgradeToolAction.ROLLBACK, description="", order=9)
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1, rollback_step_id="r1")
        s2 = UpgradeStep(step_id="s2", action=UpgradeToolAction.BACKUP, description="", order=2)
        self.engine.add_step("pb1", r1)
        self.engine.add_step("pb1", s1)
        self.engine.add_step("pb1", s2)
        self.engine.start_playbook("pb1")
        self.engine.execute_step("pb1", "s1")
        self.engine.fail_step("pb1", "s2", "err")
        pb = self.engine.get_playbook_progress("pb1")
        self.assertEqual(pb["status"], UpgradeToolStatus.ROLLED_BACK.value)

    def test_auto_rollback_manual(self):
        r1 = UpgradeStep(step_id="r1", action=UpgradeToolAction.ROLLBACK, description="", order=9)
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1, rollback_step_id="r1")
        self.engine.add_step("pb1", r1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        self.engine.execute_step("pb1", "s1")
        res = self.engine.auto_rollback_playbook("pb1")
        self.assertIn("r1", res["actions_executed"])
        pb = self.engine.get_playbook_progress("pb1")
        self.assertEqual(pb["status"], UpgradeToolStatus.ROLLED_BACK.value)

    def test_skip_step(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        step = self.engine.skip_step("pb1", "s1", "not needed")
        self.assertEqual(step.status, UpgradeToolStatus.SKIPPED)

    def test_get_playbook_progress(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        self.engine.execute_step("pb1", "s1")
        prog = self.engine.get_playbook_progress("pb1")
        self.assertEqual(prog["completed_steps"], 1)
        self.assertEqual(prog["total_steps"], 1)

    def test_complete_playbook_success(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        self.engine.execute_step("pb1", "s1")
        pb = self.engine.complete_playbook("pb1")
        self.assertEqual(pb.status, UpgradeToolStatus.SUCCESS)

    def test_complete_playbook_failure_due_to_uncompleted_steps(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        with self.assertRaises(ValueError):
            self.engine.complete_playbook("pb1")

    def test_dry_run_success(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        res = self.engine.dry_run("pb1")
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(res["timeline"]), 1)

    def test_dry_run_invalid_pb(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", preconditions=["s99"])
        self.engine.add_step("pb1", s1)
        res = self.engine.dry_run("pb1")
        self.assertEqual(res["status"], "error")

    def test_get_upgrade_report(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        self.engine.start_playbook("pb1")
        self.engine.execute_step("pb1", "s1")
        self.engine.complete_playbook("pb1")
        rep = self.engine.get_upgrade_report()
        self.assertEqual(rep["total_playbooks"], 1)
        self.assertEqual(rep["success_rate_percentage"], 100.0)

    def test_fail_step_not_running(self):
        s1 = UpgradeStep(step_id="s1", action=UpgradeToolAction.PRE_CHECK, description="", order=1)
        self.engine.add_step("pb1", s1)
        with self.assertRaises(ValueError):
            self.engine.fail_step("pb1", "s1", "err")
            
    def test_get_playbook_progress_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_playbook_progress("pb99")

    def test_complete_playbook_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_playbook("pb99")

    def test_dry_run_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.dry_run("pb99")

    def test_skip_step_not_found_playbook(self):
        with self.assertRaises(ValueError):
            self.engine.skip_step("pb99", "s1", "reason")

    def test_skip_step_not_found_step(self):
        with self.assertRaises(ValueError):
            self.engine.skip_step("pb1", "s99", "reason")

    def test_auto_rollback_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.auto_rollback_playbook("pb99")

    def test_execute_step_not_found(self):
        self.engine.start_playbook("pb1")
        with self.assertRaises(ValueError):
            self.engine.execute_step("pb1", "s99")

if __name__ == '__main__':
    unittest.main()
