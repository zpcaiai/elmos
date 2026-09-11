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
    double_entry_zero_sum_verified: bool = True
    tx_history_recorded: int = 0
    audit_entries_recorded: int = 0


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
        record_ledger: bool = True,
    ) -> StressTestReceipt:
        """Run multi-threaded financial transfer benchmark against target with double-entry conservation."""
        # 1. Setup schema: accounts, tx_history, and audit_log
        self.orchestrator.execute_query(target_id, "DROP TABLE IF EXISTS accounts;")
        self.orchestrator.execute_query(target_id, "DROP TABLE IF EXISTS tx_history;")
        self.orchestrator.execute_query(target_id, "DROP TABLE IF EXISTS audit_log;")

        create_accounts_sql = (
            "CREATE TABLE accounts (acc_id VARCHAR(32) PRIMARY KEY, "
            "balance NUMERIC(14, 2) NOT NULL);"
        )
        self.orchestrator.execute_query(target_id, create_accounts_sql)

        if record_ledger:
            create_tx_sql = (
                "CREATE TABLE tx_history (tx_id VARCHAR(48) PRIMARY KEY, "
                "from_acc VARCHAR(32) NOT NULL, to_acc VARCHAR(32) NOT NULL, "
                "amount NUMERIC(14, 2) NOT NULL, created_at TIMESTAMP);"
            )
            self.orchestrator.execute_query(target_id, create_tx_sql)

            create_audit_sql = (
                "CREATE TABLE audit_log (log_id VARCHAR(48) PRIMARY KEY, "
                "acc_no VARCHAR(32) NOT NULL, delta NUMERIC(14, 2) NOT NULL, "
                "op_type VARCHAR(16) NOT NULL);"
            )
            self.orchestrator.execute_query(target_id, create_audit_sql)

        initial_total = num_accounts * initial_balance_per_acc
        for i in range(num_accounts):
            acc_id = f"ACC_{i:04d}"
            insert_sql = (
                f"INSERT INTO accounts (acc_id, balance) "
                f"VALUES ('{acc_id}', {initial_balance_per_acc});"
            )
            self.orchestrator.execute_query(target_id, insert_sql)

        total_tx = concurrency * transactions_per_worker
        latencies: list[float] = []
        lock = threading.Lock()
        successes = 0
        failures = 0
        tx_counter = 0

        def _worker_task(worker_id: int) -> list[float]:
            nonlocal successes, failures, tx_counter
            local_latencies: list[float] = []
            for item_idx in range(transactions_per_worker):
                from_idx = random.randint(0, num_accounts - 1)
                to_idx = random.randint(0, num_accounts - 1)
                while to_idx == from_idx:
                    to_idx = random.randint(0, num_accounts - 1)

                from_acc = f"ACC_{from_idx:04d}"
                to_acc = f"ACC_{to_idx:04d}"
                amount = round(random.uniform(1.0, 50.0), 2)

                with lock:
                    tx_counter += 1
                    current_tx_id = f"TX_{worker_id:02d}_{item_idx:04d}_{tx_counter}"

                t_start = time.perf_counter()
                try:
                    # Execute atomic multi-table transfer
                    debit_sql = (
                        f"UPDATE accounts SET balance = balance - {amount} "
                        f"WHERE acc_id = '{from_acc}';"
                    )
                    self.orchestrator.execute_query(target_id, debit_sql)
                    credit_sql = (
                        f"UPDATE accounts SET balance = balance + {amount} "
                        f"WHERE acc_id = '{to_acc}';"
                    )
                    self.orchestrator.execute_query(target_id, credit_sql)

                    if record_ledger:
                        tx_sql = (
                            f"INSERT INTO tx_history (tx_id, from_acc, to_acc, amount, created_at) "
                            f"VALUES ('{current_tx_id}', '{from_acc}', '{to_acc}', {amount}, CURRENT_TIMESTAMP);"
                        )
                        self.orchestrator.execute_query(target_id, tx_sql)

                        log_d_sql = (
                            f"INSERT INTO audit_log (log_id, acc_no, delta, op_type) "
                            f"VALUES ('{current_tx_id}_D', '{from_acc}', -{amount}, 'DEBIT');"
                        )
                        self.orchestrator.execute_query(target_id, log_d_sql)

                        log_c_sql = (
                            f"INSERT INTO audit_log (log_id, acc_no, delta, op_type) "
                            f"VALUES ('{current_tx_id}_C', '{to_acc}', {amount}, 'CREDIT');"
                        )
                        self.orchestrator.execute_query(target_id, log_c_sql)

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

        # Verify Conservation Invariants
        db = self.orchestrator.get_database(target_id)
        tbl = db.tables.get("accounts")
        final_total = 0.0
        if tbl:
            for r in tbl.rows:
                final_total += float(r.get("balance", 0.0))

        balance_conserved = abs(final_total - initial_total) < 1e-4

        # Verify Double-Entry Zero-Sum Accounting Invariant
        double_entry_holds = True
        tx_recorded = 0
        audit_recorded = 0
        if record_ledger:
            tx_tbl = db.tables.get("tx_history")
            audit_tbl = db.tables.get("audit_log")
            tx_recorded = len(tx_tbl.rows) if tx_tbl else 0
            audit_recorded = len(audit_tbl.rows) if audit_tbl else 0

            audit_delta_sum = 0.0
            if audit_tbl:
                for r in audit_tbl.rows:
                    audit_delta_sum += float(r.get("delta", 0.0))
            double_entry_holds = abs(audit_delta_sum) < 1e-4

        conservation_holds = balance_conserved and double_entry_holds
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
            double_entry_zero_sum_verified=double_entry_holds,
            tx_history_recorded=tx_recorded,
            audit_entries_recorded=audit_recorded,
        )
