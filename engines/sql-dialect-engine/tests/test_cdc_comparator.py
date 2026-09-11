"""Comprehensive test suite for CDC Schema, Snapshot Data, and Event Comparators."""

from __future__ import annotations

import json
from pathlib import Path

from elmos_sql_dialect.cdc import (
    CdcEvent,
    CdcOpType,
    CdcReconciliationReport,
    ColumnSchema,
    DataComparator,
    DiffStatus,
    EventComparator,
    SchemaComparator,
    TableSchema,
    normalize_cell_value,
    normalize_row_dict,
)
from elmos_sql_dialect.cdc.reporter import main as reporter_main
from elmos_sql_dialect.models import CanonicalType


def test_schema_comparator_identical_and_mismatched() -> None:
    comparator = SchemaComparator()

    src = TableSchema(
        table_name="orders",
        columns={
            "id": ColumnSchema("id", CanonicalType.INT64, nullable=False, is_primary_key=True),
            "order_no": ColumnSchema("order_no", CanonicalType.VARCHAR, length=64, nullable=False),
            "amount": ColumnSchema("amount", CanonicalType.DECIMAL, precision=12, scale=2, nullable=False),
            "status": ColumnSchema("status", CanonicalType.VARCHAR, length=20, nullable=False),
        },
        primary_key=("id",),
    )

    # Identical target
    tgt_identical = TableSchema(
        table_name="orders",
        columns={
            "id": ColumnSchema("id", CanonicalType.INT64, nullable=False, is_primary_key=True),
            "order_no": ColumnSchema("order_no", CanonicalType.VARCHAR, length=64, nullable=False),
            "amount": ColumnSchema("amount", CanonicalType.DECIMAL, precision=12, scale=2, nullable=False),
            "status": ColumnSchema("status", CanonicalType.VARCHAR, length=20, nullable=False),
        },
        primary_key=("id",),
    )

    report = comparator.compare_tables(src, tgt_identical)
    assert report.is_identical
    assert report.is_compatible
    assert report.divergence_count == 0

    # Diverged target: mismatched type on amount and missing status column
    tgt_diverged = TableSchema(
        table_name="orders",
        columns={
            "id": ColumnSchema("id", CanonicalType.INT64, nullable=False, is_primary_key=True),
            "order_no": ColumnSchema("order_no", CanonicalType.VARCHAR, length=32, nullable=False),  # too short
            "amount": ColumnSchema("amount", CanonicalType.INT32, nullable=False),  # type mismatch
        },
        primary_key=("id",),
    )

    report_div = comparator.compare_tables(src, tgt_diverged)
    assert not report_div.is_identical
    assert not report_div.is_compatible
    assert report_div.divergence_count > 0
    diff_map = {d.column_name: d.status for d in report_div.column_diffs}
    assert diff_map["order_no"] == DiffStatus.TYPE_MISMATCH
    assert diff_map["amount"] == DiffStatus.TYPE_MISMATCH
    assert diff_map["status"] == DiffStatus.MISSING_IN_TARGET


def test_schema_comparator_compatible_types() -> None:
    comparator = SchemaComparator()

    src = TableSchema(
        table_name="users",
        columns={
            "id": ColumnSchema("id", CanonicalType.INT32, nullable=False, is_primary_key=True),
            "bio": ColumnSchema("bio", CanonicalType.VARCHAR, length=255, nullable=True),
        },
        primary_key=("id",),
    )

    # Target uses larger INT64 for id and TEXT for bio -> safe compatible
    tgt = TableSchema(
        table_name="users",
        columns={
            "id": ColumnSchema("id", CanonicalType.INT64, nullable=False, is_primary_key=True),
            "bio": ColumnSchema("bio", CanonicalType.TEXT, nullable=True),
        },
        primary_key=("id",),
    )

    report = comparator.compare_tables(src, tgt)
    assert not report.is_identical
    assert report.is_compatible
    assert all(d.status in (DiffStatus.MATCH, DiffStatus.TYPE_COMPATIBLE) for d in report.column_diffs)


def test_data_normalization_and_chunk_hashing() -> None:
    # 1. Test normalization
    assert normalize_cell_value(None) == "§NULL§"
    assert normalize_cell_value(True) == "true"
    assert normalize_cell_value(False) == "false"
    assert normalize_cell_value(123) == "123"
    assert normalize_cell_value(199.50) == "199.5"

    row1 = {"b": 2, "a": 1, "c": None}
    row2 = {"a": 1, "c": None, "b": 2}
    assert normalize_row_dict(row1) == normalize_row_dict(row2)
    assert normalize_row_dict(row1) == "a=1§b=2§c=§NULL§"

    # 2. Test chunk comparison with identical data
    comparator = DataComparator(chunk_size=2)
    src_rows = [
        {"id": 1, "name": "Alice", "score": 95.0},
        {"id": 2, "name": "Bob", "score": 88.5},
        {"id": 3, "name": "Charlie", "score": 72.0},
    ]
    tgt_rows = [
        {"name": "Alice", "id": 1, "score": 95.0},
        {"name": "Bob", "id": 2, "score": 88.5},
        {"name": "Charlie", "id": 3, "score": 72.0},
    ]

    report = comparator.compare_row_sets(src_rows, tgt_rows, pk_col="id", table_name="students")
    assert report.status == "ALIGNED"
    assert report.alignment_rate == 1.0
    assert report.total_chunks == 2  # chunk_size=2 -> 2 chunks for 3 rows
    assert report.matched_chunks == 2
    assert report.mismatched_chunks == 0
    assert report.aligned_rows == 3

    # 3. Test chunk comparison with divergence
    tgt_diverged = [
        {"name": "Alice", "id": 1, "score": 95.0},
        {"name": "Bob", "id": 2, "score": 99.0},  # modified score!
        {"name": "Charlie", "id": 3, "score": 72.0},
        {"name": "David", "id": 4, "score": 60.0},  # extra row!
    ]

    report_div = comparator.compare_row_sets(src_rows, tgt_diverged, pk_col="id", table_name="students")
    assert report_div.status == "DIVERGED"
    assert report_div.alignment_rate < 1.0
    assert report_div.mismatched_chunks > 0
    # Mismatched rows should identify id=2 and id=4
    all_mismatched = []
    for c in report_div.chunk_results:
        all_mismatched.extend(c.mismatched_pks)
    assert 2 in all_mismatched
    assert 4 in all_mismatched


def test_event_comparator_reconciliation() -> None:
    event_comp = EventComparator(pk_col="id")

    initial_state = [
        {"id": 1, "name": "item_1", "qty": 10},
        {"id": 2, "name": "item_2", "qty": 20},
    ]

    events = [
        CdcEvent(
            event_id="evt-001",
            table="inventory",
            op=CdcOpType.UPDATE,
            primary_key=1,
            lsn=1001,
            after={"id": 1, "name": "item_1", "qty": 15},
        ),
        CdcEvent(
            event_id="evt-002",
            table="inventory",
            op=CdcOpType.INSERT,
            primary_key=3,
            lsn=1002,
            after={"id": 3, "name": "item_3", "qty": 50},
        ),
        CdcEvent(
            event_id="evt-003",
            table="inventory",
            op=CdcOpType.DELETE,
            primary_key=2,
            lsn=1003,
        ),
    ]

    # Target correctly reflects final state
    expected_final_target = [
        {"id": 1, "name": "item_1", "qty": 15},
        {"id": 3, "name": "item_3", "qty": 50},
    ]

    report = event_comp.replay_and_verify(
        initial_state=initial_state,
        events=events,
        final_target_state=expected_final_target,
        table_name="inventory",
    )
    assert report.state_consistent
    assert report.status == "CONSISTENT"
    assert report.total_events == 3
    assert report.inserts == 1
    assert report.updates == 1
    assert report.deletes == 1
    assert report.out_of_order_count == 0
    assert report.duplicate_count == 0

    # Test out-of-order detection
    out_of_order_events = [
        CdcEvent(
            event_id="evt-010",
            table="inventory",
            op=CdcOpType.UPDATE,
            primary_key=1,
            lsn=2000,
            after={"id": 1, "name": "item_1", "qty": 25},
        ),
        CdcEvent(
            event_id="evt-011",
            table="inventory",
            op=CdcOpType.UPDATE,
            primary_key=1,
            lsn=1999,  # out of order!
            after={"id": 1, "name": "item_1", "qty": 20},
        ),
    ]
    report_disorder = event_comp.replay_and_verify(
        initial_state=[{"id": 1, "name": "item_1", "qty": 10}],
        events=out_of_order_events,
        final_target_state=[{"id": 1, "name": "item_1", "qty": 20}],
        table_name="inventory",
    )
    assert report_disorder.out_of_order_count == 1
    assert any(a.anomaly_type == "OUT_OF_ORDER" for a in report_disorder.anomalies)


def test_cdc_reconciliation_reporter_non_self_certification(tmp_path: Path) -> None:
    report = CdcReconciliationReport(
        source_dialect="postgres",
        target_dialect="opengauss",
        target_id="opengauss",
        execution_timestamp="2026-09-11T14:00:00Z",
        execution_mode="LOCAL_SIMULATION",
    )

    summary = report.generate_summary()
    assert summary["schemaVersion"] == "1.0"
    assert summary["reportType"] == "elmos.cdc-reconciliation-evidence"
    # Strict Non-Self-Certification checks
    assert summary["implementationStatus"] == "LOCAL_ADAPTER"
    assert summary["externalExecution"] == "NOT_RUN"
    assert summary["certification"] == "NOT_CERTIFIED"
    assert "evidenceDigest" in summary
    assert summary["evidenceDigest"].startswith("sha256:")

    # Test CLI invocation of reporter
    out_file = tmp_path / "test_report.json"
    ret = reporter_main([
        "--source-dialect", "postgres",
        "--target-dialect", "dm8",
        "--target-id", "dm8",
        "--output", str(out_file),
    ])
    assert ret == 0
    assert out_file.exists()
    loaded = json.loads(out_file.read_text())
    assert loaded["targetId"] == "dm8"
    assert loaded["certification"] == "NOT_CERTIFIED"


def test_rust_cdc_core_integration(tmp_path: Path) -> None:
    comparator = DataComparator(use_rust=True, chunk_size=2)
    assert comparator.rust_binary_path is not None
    assert Path(comparator.rust_binary_path).exists()

    src_rows = [
        {"id": 1, "name": "Alice", "score": 95.0},
        {"id": 2, "name": "Bob", "score": 88.5},
        {"id": 3, "name": "Charlie", "score": 72.0},
    ]
    tgt_rows = [
        {"id": 1, "name": "Alice", "score": 95.0},
        {"id": 2, "name": "Bob", "score": 88.5},
        {"id": 3, "name": "Charlie", "score": 72.0},
    ]

    report = comparator.compare_row_sets(src_rows, tgt_rows, pk_col="id", table_name="students")
    assert report.execution_engine == "RUST_CDC_CORE"
    assert report.status == "ALIGNED"
    assert report.alignment_rate == 1.0
    assert report.matched_chunks == 2

    # Diverged test
    tgt_diverged = [
        {"id": 1, "name": "Alice", "score": 95.0},
        {"id": 2, "name": "Bob", "score": 99.0},
        {"id": 3, "name": "Charlie", "score": 72.0},
    ]
    report_div = comparator.compare_row_sets(src_rows, tgt_diverged, pk_col="id", table_name="students")
    assert report_div.execution_engine == "RUST_CDC_CORE"
    assert report_div.status == "DIVERGED"
    assert report_div.mismatched_chunks > 0

    # Direct subcommands verification
    import subprocess

    rust_bin = comparator.rust_binary_path
    chunk_file = tmp_path / "chunk.json"
    chunk_file.write_text(json.dumps(src_rows), encoding="utf-8")

    # 1. hash-chunk
    res_hash = subprocess.run(
        [rust_bin, "hash-chunk", "--input", str(chunk_file)],
        capture_output=True,
        text=True,
        check=True,
    )
    hash_output = json.loads(res_hash.stdout)
    assert "chunk_hash" in hash_output
    assert len(hash_output["chunk_hash"]) == 64
    assert hash_output["row_count"] == 3

    # 2. compare-chunks
    tgt_file = tmp_path / "tgt_chunk.json"
    tgt_file.write_text(json.dumps(tgt_diverged), encoding="utf-8")
    res_comp = subprocess.run(
        [rust_bin, "compare-chunks", "--source", str(chunk_file), "--target", str(tgt_file), "--pk", "id"],
        capture_output=True,
        text=True,
        check=True,
    )
    comp_output = json.loads(res_comp.stdout)
    assert not comp_output["matched"]
    assert 2 in comp_output["mismatched_pks"]

    # 3. compare-events
    events_file = tmp_path / "events.json"
    events_data = [
        {
            "event_id": "e1",
            "table": "users",
            "op": "INSERT",
            "primary_key": 1,
            "lsn": 100,
            "after": {"id": 1, "name": "U1"},
        },
        {
            "event_id": "e2",
            "table": "users",
            "op": "UPDATE",
            "primary_key": 1,
            "lsn": 105,
            "after": {"id": 1, "name": "U1_updated"},
        },
    ]
    events_file.write_text(json.dumps(events_data), encoding="utf-8")
    events_tgt = tmp_path / "events_tgt.json"
    events_tgt.write_text(json.dumps([{"id": 1, "name": "U1_updated"}]), encoding="utf-8")
    res_ev = subprocess.run(
        [rust_bin, "compare-events", "--events", str(events_file), "--target", str(events_tgt), "--pk", "id"],
        capture_output=True,
        text=True,
        check=True,
    )
    ev_output = json.loads(res_ev.stdout)
    assert ev_output["total_events"] == 2
    assert ev_output["out_of_order_count"] == 0
    assert ev_output["duplicate_count"] == 0
    assert ev_output["state_consistent"]
