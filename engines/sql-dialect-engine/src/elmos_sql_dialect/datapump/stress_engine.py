"""Real physical database concurrent stress and transaction benchmarking engine.

Executes concurrent multi-threaded workloads directly against real database instances
(e.g. PostgreSQL 16), measuring true transactional throughput (TPS), row-lock contention
(SELECT ... FOR UPDATE), serialization/deadlock failure handling, and latency percentiles (P50/P95/P99).
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class TransactionResult:
    latency_ms: float
    success: bool
    retries: int = 0
    error_msg: str | None = None


@dataclass
class PhysicalStressReport:
    target_database: str
    concurrency_workers: int
    total_transactions: int
    successful_transactions: int
    failed_transactions: int
    total_retries: int
    duration_seconds: float
    tps: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetDatabase": self.target_database,
            "concurrencyWorkers": self.concurrency_workers,
            "totalTransactions": self.total_transactions,
            "successfulTransactions": self.successful_transactions,
            "failedTransactions": self.failed_transactions,
            "totalRetries": self.total_retries,
            "durationSeconds": round(self.duration_seconds, 4),
            "tps": round(self.tps, 2),
            "p50LatencyMs": round(self.p50_latency_ms, 3),
            "p90LatencyMs": round(self.p90_latency_ms, 3),
            "p95LatencyMs": round(self.p95_latency_ms, 3),
            "p99LatencyMs": round(self.p99_latency_ms, 3),
            "minLatencyMs": round(self.min_latency_ms, 3),
            "maxLatencyMs": round(self.max_latency_ms, 3),
        }


class PhysicalStressEngine:
    """Orchestrates real multi-threaded transaction stress testing."""

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        target_name: str = "PostgreSQL-16",
        concurrency: int = 10,
        transactions_per_worker: int = 50,
        max_retries: int = 3,
    ) -> None:
        self.connection_factory = connection_factory
        self.target_name = target_name
        self.concurrency = concurrency
        self.tx_per_worker = transactions_per_worker
        self.max_retries = max_retries

    def setup_stress_table(self, schema: str = "public", table_name: str = "stress_accounts", num_accounts: int = 50) -> None:
        """Initializes the stress test table with initial balance rows."""
        conn = self.connection_factory()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
                cur.execute(f"DROP TABLE IF EXISTS {schema}.{table_name} CASCADE;")
                cur.execute(f"""
                    CREATE TABLE {schema}.{table_name} (
                        account_id INT PRIMARY KEY,
                        balance NUMERIC(14, 2) NOT NULL,
                        version INT NOT NULL DEFAULT 1,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # Pre-populate accounts
                rows = [(i, 10000.00, 1) for i in range(1, num_accounts + 1)]
                import psycopg2.extras
                psycopg2.extras.execute_values(
                    cur,
                    f"INSERT INTO {schema}.{table_name} (account_id, balance, version) VALUES %s",
                    rows,
                )
        finally:
            conn.close()

    def teardown_stress_table(self, schema: str = "public", table_name: str = "stress_accounts") -> None:
        """Drops the stress test table and schema."""
        conn = self.connection_factory()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {schema}.{table_name} CASCADE;")
        finally:
            conn.close()

    def run_benchmark(
        self,
        schema: str = "public",
        table_name: str = "stress_accounts",
        num_accounts: int = 50,
    ) -> PhysicalStressReport:
        """Runs the concurrent stress test and computes latency percentiles."""
        all_results: list[TransactionResult] = []
        results_lock = threading.Lock()

        def _worker_task(worker_id: int) -> None:
            conn = self.connection_factory()
            worker_results: list[TransactionResult] = []

            for i in range(self.tx_per_worker):
                # Pick two random accounts to transfer money
                import random
                acc_from = (worker_id + i) % num_accounts + 1
                acc_to = (worker_id + i + 1) % num_accounts + 1
                if acc_from == acc_to:
                    acc_to = (acc_to % num_accounts) + 1

                amount = round(random.uniform(1.0, 50.0), 2)

                # Execute transaction with deadlock/serialization retry loop
                retries = 0
                success = False
                t0 = time.perf_counter()
                err_msg = None

                while retries <= self.max_retries and not success:
                    try:
                        conn.autocommit = False
                        with conn.cursor() as cur:
                            # Order lock acquisition to minimize, but test, row lock contention
                            first_acc, second_acc = (
                                (acc_from, acc_to) if acc_from < acc_to else (acc_to, acc_from)
                            )

                            cur.execute(
                                f"SELECT balance FROM {schema}.{table_name} WHERE account_id = %s FOR UPDATE;",
                                (first_acc,),
                            )
                            cur.execute(
                                f"SELECT balance FROM {schema}.{table_name} WHERE account_id = %s FOR UPDATE;",
                                (second_acc,),
                            )

                            # Transfer balance
                            cur.execute(
                                f"UPDATE {schema}.{table_name} SET balance = balance - %s, version = version + 1 WHERE account_id = %s;",
                                (amount, acc_from),
                            )
                            cur.execute(
                                f"UPDATE {schema}.{table_name} SET balance = balance + %s, version = version + 1 WHERE account_id = %s;",
                                (amount, acc_to),
                            )

                        conn.commit()
                        success = True
                    except Exception as e:
                        conn.rollback()
                        retries += 1
                        err_msg = str(e)
                        # Backoff jitter
                        time.sleep(0.005 * retries)

                lat_ms = (time.perf_counter() - t0) * 1000.0
                worker_results.append(
                    TransactionResult(
                        latency_ms=lat_ms,
                        success=success,
                        retries=max(0, retries - 1) if success else retries,
                        error_msg=None if success else err_msg,
                    )
                )

            conn.close()

            with results_lock:
                all_results.extend(worker_results)

        start_time = time.perf_counter()
        threads: list[threading.Thread] = []

        for w in range(self.concurrency):
            t = threading.Thread(target=_worker_task, args=(w,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        total_wall_time = time.perf_counter() - start_time

        latencies = [r.latency_ms for r in all_results]
        latencies.sort()

        succ_count = sum(1 for r in all_results if r.success)
        fail_count = len(all_results) - succ_count
        total_retries = sum(r.retries for r in all_results)

        p50 = statistics.median(latencies) if latencies else 0.0
        p90 = latencies[int(len(latencies) * 0.90)] if latencies else 0.0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0.0
        min_lat = latencies[0] if latencies else 0.0
        max_lat = latencies[-1] if latencies else 0.0

        tps = (succ_count / total_wall_time) if total_wall_time > 0 else 0.0

        return PhysicalStressReport(
            target_database=self.target_name,
            concurrency_workers=self.concurrency,
            total_transactions=len(all_results),
            successful_transactions=succ_count,
            failed_transactions=fail_count,
            total_retries=total_retries,
            duration_seconds=total_wall_time,
            tps=tps,
            p50_latency_ms=p50,
            p90_latency_ms=p90,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            min_latency_ms=min_lat,
            max_latency_ms=max_lat,
        )
