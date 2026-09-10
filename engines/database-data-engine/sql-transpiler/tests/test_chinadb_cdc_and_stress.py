"""Tests for ChinaDB CDC Data Synchronization and High-Concurrency Stress Testing."""

from __future__ import annotations

import pytest

from elmos_sql_transpiler.chinadb_cdc_engine import CdcOpType, ChangeEvent, ChinaDbCdcEngine
from elmos_sql_transpiler.chinadb_container_orchestrator import ChinaDbContainerOrchestrator
from elmos_sql_transpiler.chinadb_stress_engine import ChinaDbStressEngine


def test_cdc_event_application_and_row_hash_reconciliation():
    orchestrator = ChinaDbContainerOrchestrator()
    cdc = ChinaDbCdcEngine(orchestrator)
    target = "tidb"

    # Setup initial table
    orchestrator.execute_query(target, "DROP TABLE IF EXISTS customers;")
    orchestrator.execute_query(target, "CREATE TABLE customers (cust_id VARCHAR(32) PRIMARY KEY, name VARCHAR(100), balance NUMERIC(12, 2));")

    # 1. Apply batch of CDC INSERT events
    events = [
        ChangeEvent(
            table_name="customers",
            op_type=CdcOpType.INSERT,
            after_state={"cust_id": "C001", "name": "Company A", "balance": 5000.0},
            lsn=1001,
        ),
        ChangeEvent(
            table_name="customers",
            op_type=CdcOpType.INSERT,
            after_state={"cust_id": "C002", "name": "Company B", "balance": 8000.0},
            lsn=1002,
        ),
        ChangeEvent(
            table_name="customers",
            op_type=CdcOpType.INSERT,
            after_state={"cust_id": "C003", "name": "Company C", "balance": 3000.0},
            lsn=1003,
        ),
    ]
    applied = cdc.apply_batch(target, events)
    assert applied == 3

    # Reconcile against source truth
    source_records = [
        {"cust_id": "C001", "name": "Company A", "balance": 5000.0},
        {"cust_id": "C002", "name": "Company B", "balance": 8000.0},
        {"cust_id": "C003", "name": "Company C", "balance": 3000.0},
    ]
    receipt1 = cdc.reconcile_table_data(source_records, target, "customers", pk_columns=["cust_id"])
    assert receipt1.is_consistent is True
    assert receipt1.matched_count == 3
    assert receipt1.mismatched_count == 0
    assert receipt1.source_table_digest == receipt1.target_table_digest

    # 2. Apply CDC UPDATE event
    update_ev = ChangeEvent(
        table_name="customers",
        op_type=CdcOpType.UPDATE,
        before_state={"cust_id": "C001"},
        after_state={"cust_id": "C001", "name": "Company A+", "balance": 5500.0},
        lsn=1004,
    )
    cdc.apply_event(target, update_ev)

    # 3. Apply CDC DELETE event
    del_ev = ChangeEvent(
        table_name="customers",
        op_type=CdcOpType.DELETE,
        before_state={"cust_id": "C003"},
        lsn=1005,
    )
    cdc.apply_event(target, del_ev)

    # Reconcile again
    new_source = [
        {"cust_id": "C001", "name": "Company A+", "balance": 5500.0},
        {"cust_id": "C002", "name": "Company B", "balance": 8000.0},
    ]
    receipt2 = cdc.reconcile_table_data(new_source, target, "customers", pk_columns=["cust_id"])
    assert receipt2.is_consistent is True
    assert receipt2.matched_count == 2
    assert receipt2.target_row_count == 2


def test_high_concurrency_stress_engine_slo_and_conservation():
    orchestrator = ChinaDbContainerOrchestrator()
    stress = ChinaDbStressEngine(orchestrator)
    target = "goldendb"

    receipt = stress.run_benchmark(
        target_id=target,
        concurrency=16,
        transactions_per_worker=40,
        num_accounts=25,
        initial_balance_per_acc=5000.0,
        max_p95_latency_ms=75.0,
    )

    assert receipt.total_transactions == 640
    assert receipt.successful_transactions == 640
    assert receipt.failed_transactions == 0
    assert receipt.tps > 0.0
    assert receipt.latency_p95_ms <= 75.0
    assert receipt.conservation_invariant_holds is True
    assert abs(receipt.final_total_balance - receipt.initial_total_balance) < 1e-4
    assert receipt.slo_passed is True


def test_stress_engine_across_multiple_domestic_targets():
    orchestrator = ChinaDbContainerOrchestrator()
    stress = ChinaDbStressEngine(orchestrator)

    for target in ("dm8", "opengauss", "kingbasees"):
        receipt = stress.run_benchmark(
            target_id=target,
            concurrency=8,
            transactions_per_worker=25,
            num_accounts=10,
            initial_balance_per_acc=2000.0,
        )
        assert receipt.slo_passed is True
        assert receipt.conservation_invariant_holds is True
