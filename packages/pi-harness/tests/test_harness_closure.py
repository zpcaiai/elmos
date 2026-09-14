"""Behavioral regressions for scheduling, cancellation, recovery and fencing."""

from __future__ import annotations

import asyncio
import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

from elmos_pi_harness.agent import AgentLoop, ModelTurn
from elmos_pi_harness.canonical import digest
from elmos_pi_harness.environment import restore_environment, snapshot_environment
from elmos_pi_harness.models import (
    AuthoritySnapshot, ConflictError, EnvironmentRef, ExecutorIdentity,
    LeaseConflictError, NotFoundError, StaleGenerationError, TextContent,
    ToolInvocation, ToolResult, WorkspaceLease,
)
from elmos_pi_harness.multi_agent import AgentAssignment, FanoutCoordinator
from elmos_pi_harness.persistence import DurableStore
from elmos_pi_harness.scheduler import ready_nodes, validate_acyclic
from elmos_pi_harness.temporal import TaskWorkflowInput
from elmos_pi_harness.temporal_activities import TemporalTaskActivity


def uid():
    return str(uuid.uuid4())


class PlanningTests(unittest.TestCase):
    def test_invalid_graphs_are_rejected_by_both_entrypoints(self):
        graphs = [
            [{"id": "a"}, {"id": "a"}],
            [{"id": "a", "depends_on": ["b"]}],
            [{"id": "root"}, {"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": ["a"]}],
            [{"id": "a", "depends_on": ["a"]}],
            [{"id": 1}], [{"id": " "}], [{}], [None],
            [{"id": "a", "depends_on": "a"}],
            [{"id": "a", "depends_on": [None]}],
            [{"id": "a"}, {"id": "b", "depends_on": ["a", "a"]}],
            [{"id": "a"}, {"id": "b", "depends_on": [], "dependencies": ["a"]}],
        ]
        for graph in graphs:
            with self.subTest(graph=graph):
                with self.assertRaises(ValueError):
                    validate_acyclic(iter(graph))
                with self.assertRaises(ValueError):
                    ready_nodes(iter(graph), set())

    def test_completion_must_be_dependency_closed_and_known(self):
        graph = [{"id": "a"}, {"id": "b", "depends_on": ["a"]}, {"id": "c", "dependencies": ["b"]}]
        for completed in ({"unknown"}, {"b"}, {"a", "c"}):
            with self.subTest(completed=completed), self.assertRaises(ValueError):
                ready_nodes(graph, completed)
        self.assertEqual(ready_nodes(iter(graph), {"a", "b"}), ["c"])
        self.assertEqual(ready_nodes(graph, {"a", "b", "c"}), [])
        self.assertEqual(ready_nodes([], set()), [])

    def test_assignments_fail_before_any_worker_is_called(self):
        first = AgentAssignment("a", "w1", "t1")
        for second in (first, AgentAssignment("a", "w2", "t2"), AgentAssignment("b", "w1", "t2"), AgentAssignment("b", "w2", "t1")):
            worker = Mock()
            with self.subTest(second=second), self.assertRaises(ValueError):
                FanoutCoordinator().run([first, second], worker)
            worker.assert_not_called()

    def test_fanout_retains_all_successes_and_failures(self):
        assignments = [AgentAssignment(str(i), f"w{i}", f"t{i}") for i in range(20)]
        def worker(item):
            if item.agent_id == "7":
                raise RuntimeError("branch failed")
            return item.task_id
        result = FanoutCoordinator(max_workers=3).run(assignments, worker)
        self.assertEqual(len(result), 20)
        self.assertIsInstance(result["7"], RuntimeError)
        self.assertEqual(result["19"], "t19")


class AgentCancellationTests(unittest.TestCase):
    def invocation(self):
        return ToolInvocation(uid(), uid(), uid(), uid(), "read", {}, "call-1", 1000, "read-only")

    def test_cancel_during_model_turn_prevents_tool_and_final_completion(self):
        for decision in (ModelTurn("tool", tool=self.invocation()), ModelTurn("final", text="done")):
            cancelled = [False]
            def model(_context):
                cancelled[0] = True
                return decision
            executor = Mock()
            result = AgentLoop().run([], model, executor, cancelled=lambda: cancelled[0])
            self.assertEqual((result.status, result.turns, result.final_text), ("cancelled", 1, None))
            executor.assert_not_called()

    def test_cancel_during_last_tool_keeps_result_and_reports_cancelled(self):
        invocation = self.invocation()
        cancelled = [False]
        def execute(value):
            cancelled[0] = True
            return ToolResult(value.call_id, (TextContent("saved"),))
        result = AgentLoop(max_turns=1).run([], lambda _: ModelTurn("tool", tool=invocation), execute, cancelled=lambda: cancelled[0])
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.tool_results[0].call_id, invocation.call_id)
        self.assertEqual(result.events[-1]["type"], "tool.result")

    def test_invalid_turns_results_and_budgets_are_rejected(self):
        for budget in (True, 1.5, 0, 10001):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                AgentLoop(max_turns=budget)
        with self.assertRaises(TypeError):
            AgentLoop().run([], lambda _: object(), Mock())
        invocation = self.invocation()
        with self.assertRaises(TypeError):
            AgentLoop().run([], lambda _: ModelTurn("tool", tool=invocation), lambda _: {})
        with self.assertRaises(ValueError):
            ModelTurn("final", text="done", tool=invocation)


class EnvironmentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.ref = EnvironmentRef(uid(), uid(), 2, "local")
        authority = AuthoritySnapshot(uid(), self.ref.environment_id, "p1", frozenset({"read"}), sandbox_overrides={"network": "deny"})
        self.snapshot = snapshot_environment(self.ref, authority, sandbox_overrides={"network": "allow"})

    def restore(self, snapshot=None, current=None, overrides=None):
        return restore_environment(self.snapshot if snapshot is None else snapshot, self.ref if current is None else current, current_sandbox_overrides={} if overrides is None else overrides)

    def test_restore_preserves_authority_restrictions(self):
        self.assertEqual(self.snapshot["sandbox_overrides"], {"network": "deny"})
        restored = self.restore(overrides={"network": "allow", "filesystem": "readonly"})
        self.assertTrue(restored["restored"])
        self.assertEqual(restored["sandbox_overrides"], {"network": "deny", "filesystem": "readonly"})

    def test_owner_type_generation_and_digest_cannot_be_substituted(self):
        for current in (EnvironmentRef(self.ref.environment_id, uid(), 2, "local"), EnvironmentRef(self.ref.environment_id, self.ref.owner_execution_id, 2, "remote"), EnvironmentRef(self.ref.environment_id, self.ref.owner_execution_id, 1, "local")):
            self.assertFalse(self.restore(current=current)["restored"])
        for generation in (-1, True, "2", None):
            changed = copy.deepcopy(self.snapshot)
            changed["environment_ref"]["generation"] = generation
            self.assertFalse(self.restore(snapshot=changed)["restored"])
        changed = copy.deepcopy(self.snapshot)
        changed["authority_snapshot"]["allowed_capabilities"].append("write")
        self.assertFalse(self.restore(snapshot=changed)["restored"])

    def test_unknown_policy_conflicts_fail_closed(self):
        changed = copy.deepcopy(self.snapshot)
        changed["sandbox_overrides"]["custom"] = "old"
        self.assertFalse(self.restore(snapshot=changed, overrides={"custom": "new"})["restored"])


class DurableRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / "harness.sqlite3")
        self.store = DurableStore(self.database, artifact_root=self.temp.name)
        self.addCleanup(self.store.close)
        self.tenant, self.project, self.task = uid(), uid(), uid()
        self.store.create_task(self.tenant, self.project, "recover", idempotency_key="create", task_id=self.task, actor_id="test")
        self.lease = WorkspaceLease("workspace", self.task, 2, "repository", "revision", "BOUND")
        self.store.acquire_workspace(self.tenant, self.lease)
        environment = self.store.create_environment(self.tenant, self.task, "local", config={})
        self.environment = environment["environment_id"]
        self.authority_id = uid()
        self.store.create_authority_snapshot(self.tenant, self.authority_id, AuthoritySnapshot(uid(), self.environment, "p1", frozenset({"read"})))
        self.executor = ExecutorIdentity("executor", 1)
        self.store.register_executor(self.tenant, self.environment, self.executor)
        self.invocation = ToolInvocation(uid(), self.task, self.environment, self.authority_id, "read", {}, "read-1", 1000, "read-only")

    def expire_lease(self):
        with self.store._write():
            self.store._connection.execute("UPDATE workspace_lease SET lease_expires_at='2000-01-01T00:00:00Z' WHERE workspace_id=?", (self.lease.workspace_id,))

    def test_expired_lease_cannot_heartbeat_rebind_or_publish_checkpoint(self):
        self.expire_lease()
        operations = [
            lambda: self.store.heartbeat_workspace(self.tenant, "workspace", self.task, 2),
            lambda: self.store.acquire_workspace(self.tenant, self.lease),
            lambda: self.store.record_checkpoint(self.tenant, self.task, self.task, {}, workspace_id="workspace"),
        ]
        for operation in operations:
            with self.assertRaises(LeaseConflictError):
                operation()

    def test_checkpoint_and_acquisition_bind_the_existing_owner_and_generation(self):
        with self.assertRaises(StaleGenerationError):
            self.store.acquire_workspace(self.tenant, WorkspaceLease("workspace", self.task, 1, "repository", "revision", "BOUND"))
        with self.assertRaises(StaleGenerationError):
            self.store.record_checkpoint(self.tenant, self.task, uid(), {}, workspace_id="workspace")
        with self.assertRaises(NotFoundError):
            self.store.record_checkpoint(self.tenant, self.task, self.task, {}, workspace_id="missing")
        checkpoint = self.store.record_checkpoint(self.tenant, self.task, self.task, {"saved": True}, workspace_id="workspace")
        self.expire_lease()
        replacement = uid()
        receipt = self.store.takeover_workspace(self.tenant, "workspace", replacement, checkpoint["checkpoint_id"])
        self.assertEqual(receipt["lease"]["generation"], 3)
        with self.assertRaises(StaleGenerationError):
            self.store.heartbeat_workspace(self.tenant, "workspace", self.task, 2)

    def test_replacement_cannot_complete_or_start_old_tool_call(self):
        self.store.begin_tool_call(self.tenant, self.invocation, self.executor)
        replacement = ExecutorIdentity("replacement", 2)
        self.store.register_executor(self.tenant, self.environment, replacement)
        with self.assertRaises(StaleGenerationError):
            self.store.mark_tool_executing(self.tenant, self.invocation.call_id, replacement)
        with self.assertRaises(StaleGenerationError):
            self.store.complete_tool_call(self.tenant, self.invocation.call_id, replacement, ToolResult(self.invocation.call_id, ()))

    def test_tool_completion_is_ordered_and_exactly_replayable(self):
        self.store.begin_tool_call(self.tenant, self.invocation, self.executor)
        result = ToolResult(self.invocation.call_id, (TextContent("original"),))
        with self.assertRaises(ConflictError):
            self.store.complete_tool_call(self.tenant, self.invocation.call_id, self.executor, result)
        self.store.mark_tool_executing(self.tenant, self.invocation.call_id, self.executor)
        self.store.complete_tool_call(self.tenant, self.invocation.call_id, self.executor, result)
        self.assertEqual(self.store.complete_tool_call(self.tenant, self.invocation.call_id, self.executor, result), result)
        with self.assertRaises(ConflictError):
            self.store.complete_tool_call(self.tenant, self.invocation.call_id, self.executor, ToolResult(self.invocation.call_id, (TextContent("changed"),)))

    def test_restart_preserves_completed_results_and_blocks_inflight_retry(self):
        self.store.begin_tool_call(self.tenant, self.invocation, self.executor)
        self.store.mark_tool_executing(self.tenant, self.invocation.call_id, self.executor)
        result = ToolResult(self.invocation.call_id, (TextContent("durable"),))
        self.store.complete_tool_call(self.tenant, self.invocation.call_id, self.executor, result)
        inflight = ToolInvocation(uid(), self.task, self.environment, self.authority_id, "read", {}, "inflight", 1000, "read-only")
        self.store.begin_tool_call(self.tenant, inflight, self.executor)
        self.store.mark_tool_executing(self.tenant, inflight.call_id, self.executor)
        self.store.close()
        self.store = DurableStore(self.database, artifact_root=self.temp.name)
        self.addCleanup(self.store.close)
        replay = self.store.begin_tool_call(self.tenant, self.invocation, self.executor)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["result"], result)
        with self.assertRaises(ConflictError):
            self.store.begin_tool_call(self.tenant, inflight, self.executor)
        with self.assertRaises(NotFoundError):
            self.store.get_task(uid(), self.task)

    def test_cancellation_blocks_reserved_and_new_tool_calls(self):
        self.store.begin_tool_call(self.tenant, self.invocation, self.executor)
        self.store.transition_task(self.tenant, self.task, "CANCEL_REQUESTED", idempotency_key="cancel", actor_id="test")
        with self.assertRaises(ConflictError):
            self.store.mark_tool_executing(self.tenant, self.invocation.call_id, self.executor)
        other = ToolInvocation(uid(), self.task, self.environment, self.authority_id, "read", {}, "read-2", 1000, "read-only")
        with self.assertRaises(ConflictError):
            self.store.begin_tool_call(self.tenant, other, self.executor)

    def test_temporal_replay_reaches_result_after_first_thousand_events(self):
        request = self.store.get_task(self.tenant, self.task)["request"]
        value = TaskWorkflowInput(tenant_id=self.tenant, project_id=self.project, task_id=self.task, execution_id=self.task, environment_id=self.environment, authority_snapshot_id=self.authority_id, executor_id=self.executor.executor_id, executor_generation=self.executor.generation, request=request, request_digest=digest(request))
        self.store.transition_task(self.tenant, self.task, "QUEUED", idempotency_key="queue", actor_id="test")
        with self.store._write():
            for index in range(1001):
                self.store._append_event_locked(self.tenant, self.task, "progress", {"index": index}, "test")
        result = {"status": "VERIFYING", "task_id": self.task, "request_digest": value.request_digest, "executor_id": self.executor.executor_id, "executor_generation": self.executor.generation, "evidence_digest": digest({"evidence": "local"})}
        backend = Mock()
        backend.execute.return_value = result
        service = TemporalTaskActivity(self.store, backend, actor_id="test")
        self.assertFalse(asyncio.run(service.execute(value.to_dict()))["replayed"])
        self.assertTrue(asyncio.run(service.execute(value.to_dict()))["replayed"])
        backend.execute.assert_called_once()
        with self.assertRaises(ValueError):
            service._validate_result(value, result | {"evidence_digest": "sha256:" + "z" * 64})

    def verifying(self):
        for state in ("QUEUED", "RUNNING", "VERIFYING"):
            self.store.transition_task(self.tenant, self.task, state, idempotency_key=state, actor_id="test")

    def complete(self):
        return self.store.transition_task(self.tenant, self.task, "SUCCEEDED", idempotency_key="done", actor_id="test", payload={"verification_passed": True})

    def verification(self, gate, passed):
        return self.store.record_verification(self.tenant, self.task, passed, actor_id="verifier", verification_type=gate)

    def test_duplicate_verification_cannot_satisfy_missing_gate(self):
        self.verifying()
        self.store.set_required_verifications(self.tenant, self.task, 2)
        self.verification("unit", True)
        self.assertEqual(self.verification("unit", True)["passed_verifications"], 1)
        with self.assertRaises(ConflictError):
            self.complete()
        with self.assertRaises(ConflictError):
            self.store.set_required_verifications(self.tenant, self.task, 1)
        self.verification("integration", True)
        self.assertEqual(self.complete()["status"], "SUCCEEDED")
        with self.assertRaises(ConflictError):
            self.verification("unit", False)

    def test_failed_latest_gate_and_unrecorded_claim_do_not_complete(self):
        self.verifying()
        with self.assertRaises(ConflictError):
            self.complete()
        self.verification("unit", True)
        self.assertEqual(self.verification("unit", False)["passed_verifications"], 0)
        self.verification("integration", True)
        with self.assertRaises(ConflictError):
            self.complete()
        with self.assertRaises(ValueError):
            self.verification("unit", "false")
        self.verification("unit", True)
        self.assertEqual(self.complete()["status"], "SUCCEEDED")

    def test_retry_invalidates_verification_and_can_be_cancelled(self):
        self.verifying()
        self.verification("unit", True)
        self.store.transition_task(self.tenant, self.task, "RETRY_QUEUED", idempotency_key="retry", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "RUNNING", idempotency_key="run-again", actor_id="test")
        self.assertEqual(self.store.get_task(self.tenant, self.task)["passed_verifications"], 0)
        self.store.transition_task(self.tenant, self.task, "VERIFYING", idempotency_key="verify-again", actor_id="test")
        with self.assertRaises(ConflictError):
            self.complete()
        self.store.transition_task(self.tenant, self.task, "RETRY_QUEUED", idempotency_key="retry-again", actor_id="test")
        self.store.transition_task(self.tenant, self.task, "CANCEL_REQUESTED", idempotency_key="cancel", actor_id="test")
        result = self.store.transition_task(self.tenant, self.task, "CANCELLED", idempotency_key="cancelled", actor_id="test")
        self.assertEqual(result["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
