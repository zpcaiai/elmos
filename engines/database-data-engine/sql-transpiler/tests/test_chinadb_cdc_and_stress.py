"""Tests for ChinaDB CDC Data Synchronization and High-Concurrency Stress Testing."""

from __future__ import annotations

from decimal import Decimal

import pytest

from elmos_sql_transpiler.chinadb_cdc_engine import (
    CdcCheckpointStore,
    CdcOpType,
    ChangeEvent,
    ChinaDbCdcEngine,
)
from elmos_sql_transpiler.chinadb_container_orchestrator import ChinaDbContainerOrchestrator
from elmos_sql_transpiler.chinadb_stress_engine import ChinaDbStressEngine


@pytest.fixture
def orchestrator():
    value = ChinaDbContainerOrchestrator()
    yield value
    value.stop_all()


def test_cdc_event_application_and_row_hash_reconciliation(orchestrator):
    cdc = ChinaDbCdcEngine(orchestrator)
    target = "tidb"

    # Setup initial table
    orchestrator.execute_query(target, "DROP TABLE IF EXISTS customers;")
    orchestrator.execute_query(
        target,
        (
            "CREATE TABLE customers (cust_id VARCHAR(32) PRIMARY KEY, "
            "name VARCHAR(100), balance NUMERIC(12, 2));"
        ),
    )

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


def test_high_concurrency_stress_engine_slo_and_conservation(orchestrator):
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


def test_stress_engine_across_multiple_domestic_targets(orchestrator):
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


def test_cdc_checkpoint_is_durable_idempotent_and_rejects_out_of_order(orchestrator, tmp_path):
    target = "dm8"
    orchestrator.execute_query(target, "CREATE TABLE events (id INT PRIMARY KEY, value INT);")
    checkpoint_path = tmp_path / "dm8-checkpoint.json"
    first = ChangeEvent(
        table_name="events",
        op_type=CdcOpType.INSERT,
        after_state={"id": 1, "value": 10},
        lsn=10,
        tx_id="tx-10",
        commit_ts=100.0,
    )
    engine = ChinaDbCdcEngine(orchestrator, CdcCheckpointStore(checkpoint_path))
    assert engine.apply_event(target, first) is True

    resumed = ChinaDbCdcEngine(orchestrator, CdcCheckpointStore(checkpoint_path))
    assert resumed.apply_event(target, first) is False
    checkpoint = resumed.checkpoints.get(target, "events")
    assert checkpoint is not None
    assert checkpoint.lsn == 10
    assert checkpoint.applied_count == 1

    older = ChangeEvent(
        table_name="events",
        op_type=CdcOpType.UPDATE,
        before_state={"id": 1},
        after_state={"id": 1, "value": 11},
        lsn=9,
        tx_id="tx-9",
        commit_ts=99.0,
    )
    with pytest.raises(ValueError, match="CDC_OUT_OF_ORDER_EVENT"):
        resumed.apply_event(target, older)


def test_cdc_recovers_target_commit_before_external_checkpoint_without_duplicate(
    orchestrator, tmp_path
):
    class CrashAfterCommit(ChinaDbCdcEngine):
        def _after_target_commit(self, target_id, committed_events):
            del target_id, committed_events
            raise RuntimeError("injected-after-target-commit")

    target = "dm8"
    orchestrator.execute_query(target, "CREATE TABLE crash_events (id INT PRIMARY KEY);")
    checkpoint_path = tmp_path / "crash-checkpoint.json"
    event = ChangeEvent(
        table_name="crash_events",
        op_type=CdcOpType.INSERT,
        after_state={"id": 1},
        lsn=20,
        tx_id="tx-20",
        commit_ts=200.0,
    )

    crashing = CrashAfterCommit(orchestrator, CdcCheckpointStore(checkpoint_path))
    with pytest.raises(RuntimeError, match="injected-after-target-commit"):
        crashing.apply_event(target, event)
    assert not checkpoint_path.exists()

    resumed = ChinaDbCdcEngine(orchestrator, CdcCheckpointStore(checkpoint_path))
    assert resumed.apply_event(target, event) is False
    _, rows, _ = orchestrator.execute_query(target, "SELECT id FROM crash_events;")
    assert rows == [(1,)]
    checkpoint = resumed.checkpoints.get(target, "crash_events")
    assert checkpoint is not None
    assert checkpoint.lsn == 20


def test_reconciliation_preserves_money_precision_and_scale(orchestrator):
    cdc = ChinaDbCdcEngine(orchestrator)
    exact = cdc._hash_row(
        {"id": 1, "amount": Decimal("1234567890.1200")},
        money_scales={"amount": 4},
        money_precisions={"amount": 19},
    )
    changed = cdc._hash_row(
        {"id": 1, "amount": Decimal("1234567890.1201")},
        money_scales={"amount": 4},
        money_precisions={"amount": 19},
    )
    assert exact != changed
    with pytest.raises(ValueError, match="RECONCILIATION_MONEY_SCALE_MISMATCH"):
        cdc._hash_row(
            {"id": 1, "amount": Decimal("1234567890.12")},
            money_scales={"amount": 4},
            money_precisions={"amount": 19},
        )
    with pytest.raises(ValueError, match="RECONCILIATION_MONEY_FLOAT_PROHIBITED"):
        cdc._hash_row(
            {"id": 1, "amount": 123.12},
            money_scales={"amount": 2},
            money_precisions={"amount": 19},
        )

    with pytest.raises(ValueError, match="RECONCILIATION_MONEY_PRECISION_OVERFLOW"):
        cdc._hash_row(
            {"id": 1, "amount": Decimal("1234567890123456.0000")},
            money_scales={"amount": 4},
            money_precisions={"amount": 19},
        )

    with pytest.raises(ValueError, match="RECONCILIATION_MONEY_PRECISION_SCALE_PAIR_REQUIRED"):
        cdc._hash_row({"id": 1, "amount": Decimal("1.0000")}, money_scales={"amount": 4})


def test_cdc_requires_real_primary_key_metadata_and_safe_identifiers(orchestrator):
    engine = ChinaDbCdcEngine(orchestrator)
    with pytest.raises(ValueError, match="CDC_INVALID_IDENTIFIER"):
        engine.apply_event(
            "dm8",
            ChangeEvent(
                table_name="events; DROP TABLE accounts",
                op_type=CdcOpType.INSERT,
                after_state={"id": 1},
                lsn=1,
            ),
        )

    orchestrator.execute_query("dm8", "CREATE TABLE no_key (value INT);")
    with pytest.raises(ValueError, match="CDC_PRIMARY_KEY_METADATA_REQUIRED"):
        engine.apply_event(
            "dm8",
            ChangeEvent(
                table_name="no_key",
                op_type=CdcOpType.UPDATE,
                before_state={"value": 1},
                after_state={"value": 2},
                lsn=2,
            ),
        )
