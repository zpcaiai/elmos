import unittest
from typing import Dict, Any

from elmos_mature_platform.types import (
    WorkflowState,
    CheckpointType,
    WorkflowExecution,
    RecoveryPlan
)
from elmos_mature_platform.workflow_version_recovery_engine import WorkflowVersionRecoveryEngine

class TestWorkflowVersionRecoveryEngine(unittest.TestCase):
    def setUp(self):
        self.engine = WorkflowVersionRecoveryEngine()

    def _create_basic_workflow(self, workflow_id="wf-1", total_steps=10, idempotency_key="") -> str:
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_name="test_workflow",
            version="1.0.0",
            total_steps=total_steps,
            idempotency_key=idempotency_key
        )
        return self.engine.create_workflow(execution)

    def test_create_workflow_basic(self):
        wf_id = self._create_basic_workflow()
        self.assertIsNotNone(wf_id)
        wf = self.engine._workflows[wf_id]
        self.assertEqual(wf.state, WorkflowState.RUNNING)
        self.assertEqual(wf.current_step, 0)
        self.assertNotEqual(wf.started_at, "")

    def test_create_workflow_idempotent(self):
        key = "idem-key-1"
        wf_id1 = self._create_basic_workflow(workflow_id="wf-1", idempotency_key=key)
        wf_id2 = self._create_basic_workflow(workflow_id="wf-2", idempotency_key=key)
        self.assertEqual(wf_id1, wf_id2)
        self.assertEqual(len(self.engine._workflows), 1)

    def test_check_idempotency_found(self):
        key = "idem-key-2"
        wf_id = self._create_basic_workflow(idempotency_key=key)
        wf = self.engine.check_idempotency(key)
        self.assertIsNotNone(wf)
        self.assertEqual(wf.workflow_id, wf_id)

    def test_check_idempotency_not_found(self):
        wf = self.engine.check_idempotency("missing-key")
        self.assertIsNone(wf)

    def test_advance_step_basic(self):
        wf_id = self._create_basic_workflow()
        wf = self.engine.advance_step(wf_id)
        self.assertEqual(wf.current_step, 1)
        self.assertEqual(wf.state, WorkflowState.RUNNING)

    def test_advance_step_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.advance_step("invalid-id")

    def test_advance_step_not_running(self):
        wf_id = self._create_basic_workflow()
        self.engine.pause_workflow(wf_id)
        with self.assertRaises(ValueError):
            self.engine.advance_step(wf_id)

    def test_advance_step_completion(self):
        wf_id = self._create_basic_workflow(total_steps=1)
        wf = self.engine.advance_step(wf_id)
        self.assertEqual(wf.current_step, 1)
        self.assertEqual(wf.state, WorkflowState.COMPLETED)
        self.assertNotEqual(wf.completed_at, "")

    def test_advance_step_auto_checkpoint(self):
        wf_id = self._create_basic_workflow(total_steps=10)
        for _ in range(5):
            wf = self.engine.advance_step(wf_id)
        self.assertEqual(wf.current_step, 5)
        self.assertEqual(len(wf.checkpoints), 1)
        cp_id = wf.checkpoints[0]
        cp = self.engine._checkpoints[cp_id]
        self.assertEqual(cp.checkpoint_type, CheckpointType.AUTOMATIC)
        self.assertEqual(cp.step_index, 5)

    def test_advance_step_beyond_completion(self):
        wf_id = self._create_basic_workflow(total_steps=1)
        self.engine.advance_step(wf_id)
        # advance again
        with self.assertRaises(ValueError):
             self.engine.advance_step(wf_id)

    def test_create_checkpoint_manual(self):
        wf_id = self._create_basic_workflow()
        self.engine.advance_step(wf_id)
        cp = self.engine.create_checkpoint(
            workflow_id=wf_id,
            checkpoint_type=CheckpointType.MANUAL,
            state={"data": "val"}
        )
        self.assertEqual(cp.workflow_id, wf_id)
        self.assertEqual(cp.step_index, 1)
        self.assertNotEqual(cp.checksum, "")
        self.assertEqual(cp.state_snapshot["data"], "val")
        wf = self.engine._workflows[wf_id]
        self.assertIn(cp.checkpoint_id, wf.checkpoints)

    def test_create_checkpoint_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.create_checkpoint("invalid", CheckpointType.MANUAL, {})

    def test_create_checkpoint_not_running(self):
        wf_id = self._create_basic_workflow()
        self.engine.pause_workflow(wf_id)
        with self.assertRaises(ValueError):
            self.engine.create_checkpoint(wf_id, CheckpointType.MANUAL, {})

    def test_pause_workflow_basic(self):
        wf_id = self._create_basic_workflow()
        wf = self.engine.pause_workflow(wf_id)
        self.assertEqual(wf.state, WorkflowState.PAUSED)

    def test_pause_workflow_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.pause_workflow("invalid")

    def test_pause_workflow_not_running(self):
        wf_id = self._create_basic_workflow()
        self.engine.fail_workflow(wf_id, "err")
        with self.assertRaises(ValueError):
            self.engine.pause_workflow(wf_id)

    def test_resume_workflow_basic(self):
        wf_id = self._create_basic_workflow()
        self.engine.pause_workflow(wf_id)
        wf = self.engine.resume_workflow(wf_id)
        self.assertEqual(wf.state, WorkflowState.RUNNING)

    def test_resume_workflow_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.resume_workflow("invalid")

    def test_resume_workflow_not_paused(self):
        wf_id = self._create_basic_workflow()
        with self.assertRaises(ValueError):
            self.engine.resume_workflow(wf_id)

    def test_fail_workflow_basic(self):
        wf_id = self._create_basic_workflow()
        wf = self.engine.fail_workflow(wf_id, "Disk full")
        self.assertEqual(wf.state, WorkflowState.FAILED)
        self.assertEqual(wf.error_message, "Disk full")
        self.assertNotEqual(wf.completed_at, "")

    def test_fail_workflow_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.fail_workflow("invalid", "err")

    def test_plan_recovery_basic(self):
        wf_id = self._create_basic_workflow(total_steps=10)
        for _ in range(5):
            self.engine.advance_step(wf_id)
        plan = self.engine.plan_recovery(wf_id)
        self.assertEqual(plan.workflow_id, wf_id)
        self.assertEqual(plan.resume_step, 5)
        self.assertEqual(plan.estimated_steps_remaining, 5)

    def test_plan_recovery_no_checkpoints(self):
        wf_id = self._create_basic_workflow(total_steps=10)
        with self.assertRaises(ValueError):
            self.engine.plan_recovery(wf_id)

    def test_recover_workflow_basic(self):
        wf_id = self._create_basic_workflow(total_steps=10)
        for _ in range(5):
            self.engine.advance_step(wf_id)
        # step 6 fails
        self.engine.fail_workflow(wf_id, "Network timeout")
        wf = self.engine.recover_workflow(wf_id)
        self.assertEqual(wf.state, WorkflowState.RUNNING)
        self.assertEqual(wf.current_step, 5)
        self.assertEqual(wf.retry_count, 1)
        self.assertEqual(wf.error_message, "")
        self.assertEqual(wf.completed_at, "")

    def test_recover_workflow_not_failed(self):
        wf_id = self._create_basic_workflow(total_steps=10)
        with self.assertRaises(ValueError):
            self.engine.recover_workflow(wf_id)

    def test_recover_workflow_max_retries(self):
        wf_id = self._create_basic_workflow(total_steps=10)
        for _ in range(5):
            self.engine.advance_step(wf_id)
            
        wf = self.engine._workflows[wf_id]
        wf.max_retries = 2
        
        self.engine.fail_workflow(wf_id, "Err1")
        self.engine.recover_workflow(wf_id)
        self.engine.fail_workflow(wf_id, "Err2")
        self.engine.recover_workflow(wf_id)
        
        self.engine.fail_workflow(wf_id, "Err3")
        with self.assertRaises(RuntimeError):
            self.engine.recover_workflow(wf_id)

    def test_cancel_workflow(self):
        wf_id = self._create_basic_workflow()
        wf = self.engine.cancel_workflow(wf_id)
        self.assertEqual(wf.state, WorkflowState.CANCELLED)
        self.assertNotEqual(wf.completed_at, "")

    def test_check_version_compatibility(self):
        wf_id = self._create_basic_workflow()
        self.assertTrue(self.engine.check_version_compatibility(wf_id, "1.1.0"))
        self.assertFalse(self.engine.check_version_compatibility(wf_id, "2.0.0"))

    def test_get_workflow_report(self):
        # Create a few workflows
        self._create_basic_workflow(workflow_id="wf-1", total_steps=10) # RUNNING
        
        wf2_id = self._create_basic_workflow(workflow_id="wf-2", total_steps=10)
        self.engine.advance_step(wf2_id)
        self.engine.pause_workflow(wf2_id) # PAUSED
        
        wf3_id = self._create_basic_workflow(workflow_id="wf-3", total_steps=10)
        for _ in range(5):
             self.engine.advance_step(wf3_id) # 1 auto checkpoint
        self.engine.fail_workflow(wf3_id, "err")
        self.engine.recover_workflow(wf3_id)
        self.engine.fail_workflow(wf3_id, "err2")
        self.engine.recover_workflow(wf3_id)
        self.engine.fail_workflow(wf3_id, "err3")
        self.engine.recover_workflow(wf3_id)
        self.engine.fail_workflow(wf3_id, "err4") # FAILED permanently
        
        report = self.engine.get_workflow_report()
        self.assertEqual(report["total_workflows"], 3)
        self.assertEqual(report["by_state"][WorkflowState.RUNNING.value], 1)
        self.assertEqual(report["by_state"][WorkflowState.PAUSED.value], 1)
        self.assertEqual(report["by_state"][WorkflowState.FAILED.value], 1)
        self.assertEqual(report["total_checkpoints"], 1)
        self.assertEqual(report["total_retries"], 3)
        self.assertEqual(report["failed_permanently"], 1)

if __name__ == '__main__':
    unittest.main()
