from __future__ import annotations

import time
import unittest

from elmos_foundry.scheduler.benchmarks import SchedulerBenchmarkHarness
from elmos_foundry.scheduler.fair_scheduler import DeficitWeightedRoundRobinScheduler
from elmos_foundry.scheduler.lease_manager import DistributedLeaseManager
from elmos_foundry.scheduler.persistent_queue import PersistentTaskQueue
from elmos_foundry.scheduler.recovery_manager import RecoveryJournalManager
from elmos_foundry.scheduler.saga_orchestrator import DistributedSagaOrchestrator, SagaStatus


class TestSchedulerExtendedSuite(unittest.TestCase):

    def test_persistent_queue_lifecycle(self) -> None:
        queue = PersistentTaskQueue(":memory:")
        self.assertEqual(queue.size(), 0)

        # 1. Enqueue with priorities
        queue.enqueue("msg-1", "tenant-A", "task-low", {"data": 1}, priority=1)
        queue.enqueue("msg-2", "tenant-A", "task-high", {"data": 2}, priority=10)
        self.assertEqual(queue.size(), 2)

        # 2. Poll should return higher priority first
        leased = queue.poll(worker_id="w-1", lease_duration=5.0, limit=1)
        self.assertEqual(len(leased), 1)
        self.assertEqual(leased[0].task_id, "task-high")

        # 3. Ack the high priority message
        acked = queue.ack("msg-2", "w-1")
        self.assertTrue(acked)
        self.assertEqual(queue.size(), 1)

        # 4. Poll next and nack until DLQ
        leased_low = queue.poll(worker_id="w-2", lease_duration=5.0, limit=1)
        self.assertEqual(len(leased_low), 1)
        self.assertEqual(leased_low[0].task_id, "task-low")

        # Nack up to max_retries (3)
        queue.nack("msg-1", "w-2", reason="transient failure 1")
        p2 = queue.poll(worker_id="w-2", limit=1)
        self.assertEqual(len(p2), 1)
        queue.nack("msg-1", "w-2", reason="transient failure 2")
        p3 = queue.poll(worker_id="w-2", limit=1)
        self.assertEqual(len(p3), 1)
        # 3rd nack exceeds limit -> DLQ
        queue.nack("msg-1", "w-2", reason="permanent failure")

        self.assertEqual(queue.size(), 0)
        self.assertEqual(queue.dlq_size(), 1)

    def test_distributed_lease_manager(self) -> None:
        lm = DistributedLeaseManager(default_ttl=0.2)

        # 1. Worker 1 acquires
        acq, token1 = lm.acquire("res-1", "worker-1", ttl=0.3)
        self.assertTrue(acq)
        self.assertGreater(token1, 1000)

        # 2. Worker 2 attempts while valid -> fails
        acq2, _ = lm.acquire("res-1", "worker-2", ttl=0.3)
        self.assertFalse(acq2)

        # 3. Validate fencing token
        self.assertTrue(lm.validate_fencing_token("res-1", token1))
        self.assertFalse(lm.validate_fencing_token("res-1", 999))

        # 4. Heartbeat
        self.assertTrue(lm.heartbeat("res-1", "worker-1", token1, ttl=0.3))

        # 5. Let expire and worker 2 acquires
        time.sleep(0.35)
        self.assertFalse(lm.validate_fencing_token("res-1", token1))
        acq3, token3 = lm.acquire("res-1", "worker-2", ttl=0.3)
        self.assertTrue(acq3)
        self.assertGreater(token3, token1)

        # 6. Release
        self.assertTrue(lm.release("res-1", "worker-2", token3))

    def test_fair_dwrr_scheduler(self) -> None:
        sched = DeficitWeightedRoundRobinScheduler(default_weight=10, max_active_per_tenant=2)

        sched.register_tenant("tenant-A", weight=20)  # Double weight
        sched.register_tenant("tenant-B", weight=10)

        # Enqueue tasks
        for i in range(4):
            sched.enqueue("tenant-A", f"task-A-{i}", {}, cost=10)
            sched.enqueue("tenant-B", f"task-B-{i}", {}, cost=10)

        # Schedule items
        item1 = sched.schedule_next()
        self.assertIsNotNone(item1)
        self.assertEqual(item1.tenant_id, "tenant-A")

        item2 = sched.schedule_next()
        self.assertIsNotNone(item2)
        # Tenant A has higher weight, gets served multiple quanta
        self.assertEqual(item2.tenant_id, "tenant-A")

        # Concurrency limit hit for A (max 2 active)
        item3 = sched.schedule_next()
        self.assertIsNotNone(item3)
        self.assertEqual(item3.tenant_id, "tenant-B")

        # Release A and re-schedule
        sched.release_task("tenant-A")
        item4 = sched.schedule_next()
        self.assertIsNotNone(item4)

    def test_recovery_journal_manager(self) -> None:
        rjm = RecoveryJournalManager(":memory:")
        gid = "graph-100"

        rjm.append_event(gid, "t-1", "TASK_SCHEDULED", {})
        rjm.append_event(gid, "t-1", "TASK_RUNNING", {"worker_id": "w-10"})
        rjm.append_event(gid, "t-1", "TASK_COMPLETED", {"result": {"loc": 500}})

        rjm.append_event(gid, "t-2", "TASK_SCHEDULED", {})
        rjm.append_event(gid, "t-2", "TASK_RUNNING", {"worker_id": "w-11"})
        rjm.append_event(gid, "t-2", "TASK_FAILED", {"error": "syntax parse failure"})

        # Reconstruct state
        state = rjm.reconstruct_state(gid)
        self.assertIn("t-1", state)
        self.assertEqual(state["t-1"]["state"], "COMPLETED")
        self.assertEqual(state["t-1"]["result"], {"loc": 500})

        self.assertIn("t-2", state)
        self.assertEqual(state["t-2"]["state"], "FAILED")
        self.assertEqual(state["t-2"]["error"], "syntax parse failure")

    def test_saga_orchestrator_success_and_compensation(self) -> None:
        # Case 1: Success
        saga = DistributedSagaOrchestrator("saga-success")
        log = []

        def step1_fwd(ctx):
            log.append("step1_done")
            return {"step1": True}

        def step2_fwd(ctx):
            log.append("step2_done")
            return {"step2": True}

        saga.add_step("step1", step1_fwd)
        saga.add_step("step2", step2_fwd)

        receipt = saga.execute({"init": 1})
        self.assertEqual(receipt.status, SagaStatus.COMPLETED)
        self.assertEqual(receipt.steps_executed, 2)
        self.assertEqual(receipt.steps_compensated, 0)
        self.assertTrue(len(receipt.merkle_root) > 10)
        self.assertEqual(log, ["step1_done", "step2_done"])

        # Case 2: Failure & LIFO Compensation
        comp_log = []
        saga_fail = DistributedSagaOrchestrator("saga-failure")

        def s1_fwd(ctx):
            comp_log.append("s1_fwd")
            return {"allocated": "res_10"}

        def s1_comp(ctx, res):
            comp_log.append("s1_comp:" + res.get("allocated", ""))

        def s2_fwd(ctx):
            comp_log.append("s2_fwd")
            return {"state": "ready"}

        def s2_comp(ctx, res):
            comp_log.append("s2_comp")

        def s3_fwd(ctx):
            raise RuntimeError("Database deadlock")

        saga_fail.add_step("s1", s1_fwd, s1_comp)
        saga_fail.add_step("s2", s2_fwd, s2_comp)
        saga_fail.add_step("s3", s3_fwd)

        receipt_fail = saga_fail.execute({})
        self.assertEqual(receipt_fail.status, SagaStatus.COMPENSATED)
        self.assertEqual(receipt_fail.steps_executed, 2)
        self.assertEqual(receipt_fail.steps_compensated, 2)
        self.assertIn("Database deadlock", receipt_fail.error)
        # Expected LIFO compensation order: s2_comp then s1_comp
        self.assertEqual(comp_log, ["s1_fwd", "s2_fwd", "s2_comp", "s1_comp:res_10"])

    def test_benchmark_harness(self) -> None:
        harness = SchedulerBenchmarkHarness(task_count=100, concurrency=4)
        report = harness.run_benchmark()
        self.assertEqual(report.total_tasks, 100)
        self.assertEqual(report.concurrency, 4)
        self.assertGreater(report.throughput_tps, 0.0)
        self.assertGreaterEqual(report.p50_latency_ms, 0.0)


if __name__ == "__main__":
    unittest.main()
