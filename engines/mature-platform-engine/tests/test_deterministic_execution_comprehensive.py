import unittest
import uuid
from elmos_mature_platform.types import (
    ExecutionMode,
    StepOutcome,
    ExecutionStep,
    DeterministicExecution
)
from elmos_mature_platform.deterministic_execution_engine import DeterministicExecutionEngine

class TestDeterministicExecutionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DeterministicExecutionEngine()

    def test_create_execution(self):
        exec_id = "test-exec-1"
        exe = DeterministicExecution(execution_id=exec_id, agent_id="agent-1")
        res = self.engine.create_execution(exe)
        self.assertEqual(res, exec_id)

    def test_create_execution_no_id(self):
        exe = DeterministicExecution(execution_id="", agent_id="agent-1")
        res = self.engine.create_execution(exe)
        self.assertTrue(len(res) > 0)

    def test_record_step(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        step = ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="run", input_hash="h1", output_hash="h2")
        self.engine.record_step(step)
        steps = self.engine.get_steps(exec_id)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].step_id, "s1")

    def test_record_step_invalid_execution(self):
        step = ExecutionStep(step_id="s1", execution_id="invalid", step_index=0, action="run")
        with self.assertRaises(ValueError):
            self.engine.record_step(step)

    def test_record_step_non_sequential(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        step1 = ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="run")
        self.engine.record_step(step1)
        step2 = ExecutionStep(step_id="s2", execution_id=exec_id, step_index=2, action="run")
        with self.assertRaises(ValueError):
            self.engine.record_step(step2)

    def test_get_steps(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.assertEqual(self.engine.get_steps(exec_id), [])

    def test_get_steps_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_steps("invalid")

    def test_compute_determinism_score_empty(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.assertEqual(self.engine.compute_determinism_score(exec_id), 1.0)

    def test_compute_determinism_score_all_deterministic(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a", deterministic=True))
        self.assertEqual(self.engine.compute_determinism_score(exec_id), 1.0)

    def test_compute_determinism_score_mixed(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a", deterministic=True))
        self.engine.record_step(ExecutionStep(step_id="s2", execution_id=exec_id, step_index=1, action="b", deterministic=False))
        self.assertEqual(self.engine.compute_determinism_score(exec_id), 0.5)

    def test_start_replay(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1", seed=10))
        replay = self.engine.start_replay(exec_id)
        self.assertEqual(replay.mode, ExecutionMode.REPLAY)
        self.assertEqual(replay.seed, 10)
        self.assertEqual(replay.replay_source_id, exec_id)

    def test_start_replay_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.start_replay("invalid")

    def test_verify_replay_matched(self):
        orig_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=orig_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=orig_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        replay = self.engine.start_replay(orig_id)
        self.engine.record_step(ExecutionStep(step_id="s2", execution_id=replay.execution_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        ver = self.engine.verify_replay(orig_id, replay.execution_id)
        self.assertTrue(ver.fully_deterministic)
        self.assertEqual(ver.steps_matched, 1)

    def test_verify_replay_diverged(self):
        orig_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=orig_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=orig_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        replay = self.engine.start_replay(orig_id)
        self.engine.record_step(ExecutionStep(step_id="s2", execution_id=replay.execution_id, step_index=0, action="a", input_hash="i", output_hash="diff"))
        ver = self.engine.verify_replay(orig_id, replay.execution_id)
        self.assertFalse(ver.fully_deterministic)
        self.assertEqual(ver.steps_diverged, 1)

    def test_verify_replay_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.verify_replay("a", "b")

    def test_get_divergence_report(self):
        orig_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=orig_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=orig_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        replay = self.engine.start_replay(orig_id)
        self.engine.record_step(ExecutionStep(step_id="s2", execution_id=replay.execution_id, step_index=0, action="a", input_hash="i", output_hash="diff"))
        report = self.engine.get_divergence_report(orig_id, replay.execution_id)
        self.assertFalse(report["fully_deterministic"])
        self.assertEqual(len(report["divergence_details"]), 1)

    def test_set_deterministic_seed(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.engine.set_deterministic_seed(exec_id, 99)
        self.assertEqual(self.engine._executions[exec_id].seed, 99)

    def test_set_deterministic_seed_after_step(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a"))
        with self.assertRaises(ValueError):
            self.engine.set_deterministic_seed(exec_id, 99)

    def test_set_deterministic_seed_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.set_deterministic_seed("invalid", 99)

    def test_mark_step_nondeterministic(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a", deterministic=True))
        self.engine.mark_step_nondeterministic("s1")
        self.assertEqual(self.engine.compute_determinism_score(exec_id), 0.0)

    def test_mark_step_nondeterministic_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.mark_step_nondeterministic("invalid")

    def test_get_execution_trace(self):
        exec_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=exec_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a"))
        trace = self.engine.get_execution_trace(exec_id)
        self.assertEqual(trace["execution_id"], exec_id)
        self.assertEqual(len(trace["steps"]), 1)

    def test_get_execution_trace_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.get_execution_trace("invalid")

    def test_get_execution_report_empty(self):
        rep = self.engine.get_execution_report()
        self.assertEqual(rep["total_executions"], 0)

    def test_get_execution_report_full(self):
        orig_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=orig_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=orig_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        replay = self.engine.start_replay(orig_id)
        self.engine.record_step(ExecutionStep(step_id="s2", execution_id=replay.execution_id, step_index=0, action="a", input_hash="i", output_hash="diff"))
        rep = self.engine.get_execution_report()
        self.assertEqual(rep["total_executions"], 2)
        self.assertEqual(rep["total_replays"], 1)
        self.assertEqual(rep["overall_divergence_rate"], 1.0)
        
    def test_get_execution_report_no_divergence(self):
        orig_id = "exec-1"
        self.engine.create_execution(DeterministicExecution(execution_id=orig_id, agent_id="a1"))
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=orig_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        replay = self.engine.start_replay(orig_id)
        self.engine.record_step(ExecutionStep(step_id="s2", execution_id=replay.execution_id, step_index=0, action="a", input_hash="i", output_hash="o"))
        rep = self.engine.get_execution_report()
        self.assertEqual(rep["total_executions"], 2)
        self.assertEqual(rep["overall_divergence_rate"], 0.0)

    def test_successful_step_increments_completed(self):
        exec_id = "exec-1"
        exe = DeterministicExecution(execution_id=exec_id, agent_id="a1")
        self.engine.create_execution(exe)
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a", outcome=StepOutcome.SUCCESS))
        self.assertEqual(exe.completed_steps, 1)

    def test_failed_step_no_increment(self):
        exec_id = "exec-1"
        exe = DeterministicExecution(execution_id=exec_id, agent_id="a1")
        self.engine.create_execution(exe)
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a", outcome=StepOutcome.FAILURE))
        self.assertEqual(exe.completed_steps, 0)

    def test_skipped_step_no_increment(self):
        exec_id = "exec-1"
        exe = DeterministicExecution(execution_id=exec_id, agent_id="a1")
        self.engine.create_execution(exe)
        self.engine.record_step(ExecutionStep(step_id="s1", execution_id=exec_id, step_index=0, action="a", outcome=StepOutcome.SKIPPED))
        self.assertEqual(exe.completed_steps, 0)

if __name__ == '__main__':
    unittest.main()
