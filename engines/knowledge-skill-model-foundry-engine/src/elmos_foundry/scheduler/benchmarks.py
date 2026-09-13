from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass
from typing import List

from .lease_manager import DistributedLeaseManager
from .persistent_queue import PersistentTaskQueue


@dataclass
class BenchmarkReport:
    total_tasks: int
    concurrency: int
    duration_seconds: float
    throughput_tps: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    reaped_stale_leases: int


class SchedulerBenchmarkHarness:
    """Evaluates task queue throughput and lease contention under concurrent multi-threaded workloads."""

    def __init__(self, task_count: int = 1000, concurrency: int = 10):
        self.task_count = task_count
        self.concurrency = concurrency
        self.queue = PersistentTaskQueue(":memory:")
        self.lease_mgr = DistributedLeaseManager(default_ttl=5.0)

    def run_benchmark(self) -> BenchmarkReport:
        # Prepopulate queue
        for i in range(self.task_count):
            self.queue.enqueue(
                msg_id=f"msg-{i}",
                tenant_id=f"tenant-{i % 5}",
                task_id=f"task-{i}",
                payload={"index": i, "command": "eval"},
                priority=(i % 3) * 5 + 1,
            )

        latencies_ms: List[float] = []
        start_time = time.time()

        def worker_loop(worker_idx: int) -> List[float]:
            worker_id = f"worker-{worker_idx}"
            local_lats: List[float] = []
            while True:
                t0 = time.time()
                msgs = self.queue.poll(worker_id=worker_id, lease_duration=10.0, limit=5)
                if not msgs:
                    break
                for m in msgs:
                    # Simulate lease acquisition and task processing
                    acquired, token = self.lease_mgr.acquire(m.task_id, worker_id, ttl=2.0)
                    if acquired:
                        # Validate fencing
                        valid = self.lease_mgr.validate_fencing_token(m.task_id, token)
                        if valid:
                            self.queue.ack(m.msg_id, worker_id)
                            self.lease_mgr.release(m.task_id, worker_id, token)
                    lat = (time.time() - t0) * 1000.0
                    local_lats.append(lat)
            return local_lats

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(worker_loop, w) for w in range(self.concurrency)]
            for f in concurrent.futures.as_completed(futures):
                latencies_ms.extend(f.result())

        total_duration = time.time() - start_time
        latencies_ms.sort()

        p50 = latencies_ms[int(len(latencies_ms) * 0.50)] if latencies_ms else 0.0
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)] if latencies_ms else 0.0
        tps = len(latencies_ms) / total_duration if total_duration > 0 else 0.0

        return BenchmarkReport(
            total_tasks=len(latencies_ms),
            concurrency=self.concurrency,
            duration_seconds=round(total_duration, 4),
            throughput_tps=round(tps, 2),
            p50_latency_ms=round(p50, 3),
            p95_latency_ms=round(p95, 3),
            p99_latency_ms=round(p99, 3),
            reaped_stale_leases=self.lease_mgr.reap_stale(),
        )
