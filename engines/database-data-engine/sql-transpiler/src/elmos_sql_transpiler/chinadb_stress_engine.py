"""High-Concurrency Stress Testing Engine for ChinaDB.

Simulates enterprise multi-worker transactional workloads, measures throughput (TPS),
calculates latency percentiles (P50, P90, P95, P99), validates conservation invariants,
and enforces industrial SLO (P95 <= 75ms).
"""

from __future__ import annotations

import concurrent.futures
import random
import threading
import time
from dataclasses import dataclass

from .chinadb_container_orchestrator import ChinaDbContainerOrchestrator


@dataclass
class StressTestReceipt:
    target_id: str
    concurrency: int
    total_transactions: int
    successful_transactions: int
    failed_transactions: int
    duration_seconds: float
    tps: float
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    slo_passed: bool
    conservation_invariant_holds: bool
    initial_total_balance: float
    final_total_balance: float


class ChinaDbStressEngine:
    """Multi-threaded high-concurrency transactional stress test runner."""

    def __init__(self, orchestrator: ChinaDbContainerOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or ChinaDbContainerOrchestrator()

    def run_benchmark(
        self,
        target_id: str,
        concurrency: int = 16,
        transactions_per_worker: int = 50,
        num_accounts: int = 20,
        initial_balance_per_acc: float = 10000.0,
        max_p95_latency_ms: float = 75.0,
    ) -> StressTestReceipt:
        """Run multi-threaded financial transfer benchmark against target."""
        # 1. Setup schema and accounts
        self.orchestrator.execute_query(target_id, "DROP TABLE IF EXISTS accounts;")
        self.orchestrator.execute_query(
            target_id,
            "CREATE TABLE accounts (acc_id VARCHAR(32) PRIMARY KEY, balance NUMERIC(14, 2) NOT NULL);",
        )

        initial_total = num_accounts * initial_balance_per_acc
        for i in range(num_accounts):
            acc_id = f"ACC_{i:04d}"
            self.orchestrator.execute_query(
                target_id,
                f"INSERT INTO accounts (acc_id, balance) VALUES ('{acc_id}', {initial_balance_per_acc});",
            )

        total_tx = concurrency * transactions_per_worker
        latencies: list[float] = []
        lock = threading.Lock()
        successes = 0
        failures = 0

        def _worker_task(worker_id: int) -> list[float]:
            nonlocal successes, failures
            local_latencies: list[float] = []
            for _ in range(transactions_per_worker):
                from_idx = random.randint(0, num_accounts - 1)
                to_idx = random.randint(0, num_accounts - 1)
                while to_idx == from_idx:
                    to_idx = random.randint(0, num_accounts - 1)

                from_acc = f"ACC_{from_idx:04d}"
                to_acc = f"ACC_{to_idx:04d}"
                amount = round(random.uniform(1.0, 50.0), 2)

                t_start = time.perf_counter()
                try:
                    # Execute atomic transfer
                    self.orchestrator.execute_query(
                        target_id,
                        f"UPDATE accounts SET balance = balance - {amount} WHERE acc_id = '{from_acc}';",
                    )
                    self.orchestrator.execute_query(
                        target_id,
                        f"UPDATE accounts SET balance = balance + {amount} WHERE acc_id = '{to_acc}';",
                    )
                    t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
                    local_latencies.append(t_elapsed_ms)
                    with lock:
                        successes += 1
                except Exception:
                    with lock:
                        failures += 1

            return local_latencies

        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_worker_task, w) for w in range(concurrency)]
            for fut in concurrent.futures.as_completed(futures):
                latencies.extend(fut.result())

        total_duration = time.perf_counter() - t0
        tps = total_tx / total_duration if total_duration > 0 else 0.0

        latencies.sort()
        n = len(latencies)
        p50 = latencies[int(n * 0.50)] if n else 0.0
        p90 = latencies[int(n * 0.90)] if n else 0.0
        p95 = latencies[int(n * 0.95)] if n else 0.0
        p99 = latencies[int(n * 0.99)] if n else 0.0

        # Verify Conservation Invariant
        db = self.orchestrator.get_database(target_id)
        tbl = db.tables.get("accounts")
        final_total = 0.0
        if tbl:
            for r in tbl.rows:
                final_total += float(r.get("balance", 0.0))

        conservation_holds = abs(final_total - initial_total) < 1e-4
        slo_passed = (p95 <= max_p95_latency_ms) and (failures == 0) and conservation_holds

        return StressTestReceipt(
            target_id=target_id,
            concurrency=concurrency,
            total_transactions=total_tx,
            successful_transactions=successes,
            failed_transactions=failures,
            duration_seconds=round(total_duration, 3),
            tps=round(tps, 1),
            latency_p50_ms=round(p50, 2),
            latency_p90_ms=round(p90, 2),
            latency_p95_ms=round(p95, 2),
            latency_p99_ms=round(p99, 2),
            slo_passed=slo_passed,
            conservation_invariant_holds=conservation_holds,
            initial_total_balance=initial_total,
            final_total_balance=final_total,
        )
