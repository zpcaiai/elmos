"""Tests for Rust-accelerated CDC Event Stream Comparator.

Validates that cdc-engine-rust compare-events correctly executes through
EventComparator(use_rust=True) and accurately identifies consistent replay,
out-of-order LSN sequences, duplicate event IDs, and state divergences.
"""

from __future__ import annotations

import pytest

from elmos_sql_dialect.cdc.event_comparator import (
    CdcEvent,
    CdcOpType,
    EventComparator,
)


def test_rust_event_comparator_consistent_replay():
    """Verify clean CDC event stream correctly replicates and matches target state via Rust."""
    comparator = EventComparator(pk_col="id", use_rust=True)
    assert comparator.rust_binary_path is not None, "cdc-engine-rust binary must be compiled"

    initial_state = [
        {"id": 1, "name": "Alice", "score": 100},
        {"id": 2, "name": "Bob", "score": 200},
        {"id": 3, "name": "Charlie", "score": 300},
    ]

    events = [
        CdcEvent(
            event_id="ev-001",
            table="users",
            op=CdcOpType.INSERT,
            primary_key=4,
            lsn=1001,
            after={"id": 4, "name": "Diana", "score": 400},
        ),
        CdcEvent(
            event_id="ev-002",
            table="users",
            op=CdcOpType.UPDATE,
            primary_key=2,
            lsn=1002,
            before={"id": 2, "name": "Bob", "score": 200},
            after={"id": 2, "name": "Bob", "score": 250},
        ),
        CdcEvent(
            event_id="ev-003",
            table="users",
            op=CdcOpType.DELETE,
            primary_key=1,
            lsn=1003,
            before={"id": 1, "name": "Alice", "score": 100},
        ),
    ]

    final_target_state = [
        {"id": 2, "name": "Bob", "score": 250},
        {"id": 3, "name": "Charlie", "score": 300},
        {"id": 4, "name": "Diana", "score": 400},
    ]

    report = comparator.replay_and_verify(
        initial_state=initial_state,
        events=events,
        final_target_state=final_target_state,
        table_name="users",
    )

    assert report.execution_engine == "RUST_CDC_CORE"
    assert report.state_consistent is True
    assert report.status == "CONSISTENT"
    assert report.total_events == 3
    assert report.inserts == 1
    assert report.updates == 1
    assert report.deletes == 1
    assert report.out_of_order_count == 0
    assert report.duplicate_count == 0
    assert len(report.anomalies) == 0
    assert len(report.mismatched_pks) == 0


def test_rust_event_comparator_detects_out_of_order():
    """Verify Rust CDC detects non-monotonic LSN stream."""
    comparator = EventComparator(pk_col="id", use_rust=True)

    initial_state = [{"id": 1, "status": "PENDING"}]

    events = [
        CdcEvent(
            event_id="ev-001",
            table="orders",
            op=CdcOpType.UPDATE,
            primary_key=1,
            lsn=500,
            after={"id": 1, "status": "PROCESSING"},
        ),
        # Out-of-order LSN (450 < 500)
        CdcEvent(
            event_id="ev-002",
            table="orders",
            op=CdcOpType.UPDATE,
            primary_key=1,
            lsn=450,
            after={"id": 1, "status": "SHIPPED"},
        ),
    ]

    final_target_state = [{"id": 1, "status": "SHIPPED"}]

    report = comparator.replay_and_verify(
        initial_state=initial_state,
        events=events,
        final_target_state=final_target_state,
        table_name="orders",
    )

    assert report.execution_engine == "RUST_CDC_CORE"
    assert report.out_of_order_count >= 1
    assert report.status == "EVENT_DISORDER"
    assert any(a.anomaly_type == "OUT_OF_ORDER" for a in report.anomalies)


def test_rust_event_comparator_detects_duplicates():
    """Verify Rust CDC detects duplicate event IDs."""
    comparator = EventComparator(pk_col="id", use_rust=True)

    initial_state = [{"id": 10, "val": 100}]

    events = [
        CdcEvent(
            event_id="ev-dup-01",
            table="metrics",
            op=CdcOpType.UPDATE,
            primary_key=10,
            lsn=100,
            after={"id": 10, "val": 101},
        ),
        # Duplicate event ID
        CdcEvent(
            event_id="ev-dup-01",
            table="metrics",
            op=CdcOpType.UPDATE,
            primary_key=10,
            lsn=101,
            after={"id": 10, "val": 102},
        ),
    ]

    final_target_state = [{"id": 10, "val": 102}]

    report = comparator.replay_and_verify(
        initial_state=initial_state,
        events=events,
        final_target_state=final_target_state,
        table_name="metrics",
    )

    assert report.execution_engine == "RUST_CDC_CORE"
    assert report.duplicate_count >= 1
    assert any(a.anomaly_type == "DUPLICATE_EVENT" for a in report.anomalies)


def test_rust_event_comparator_detects_state_mismatch():
    """Verify Rust CDC detects divergence between replayed stream and target table."""
    comparator = EventComparator(pk_col="id", use_rust=True)

    initial_state = [{"id": 100, "balance": 50.0}]

    events = [
        CdcEvent(
            event_id="ev-tx-01",
            table="accounts",
            op=CdcOpType.UPDATE,
            primary_key=100,
            lsn=2001,
            after={"id": 100, "balance": 75.0},
        )
    ]

    # Target table has 999.0 instead of 75.0 (drift)
    final_target_state = [{"id": 100, "balance": 999.0}]

    report = comparator.replay_and_verify(
        initial_state=initial_state,
        events=events,
        final_target_state=final_target_state,
        table_name="accounts",
    )

    assert report.execution_engine == "RUST_CDC_CORE"
    assert report.state_consistent is False
    assert report.status == "STATE_MISMATCH"
    assert 100 in report.mismatched_pks or "100" in report.mismatched_pks
