from __future__ import annotations

from elmos_sql_transpiler.plan_analyzer import (
    ExecutionPlanProfile,
    analyze_plan,
    compare_plan_structural_intent,
)


def test_sqlite_plan_analysis() -> None:
    raw_sqlite_plan = [
        [2, 0, 55, "SEARCH orders USING COVERING INDEX orders_tenant_created_id_idx (tenant_id=?)"],
        [4, 0, 0, "USE TEMP B-TREE FOR ORDER BY"],
    ]
    profile = analyze_plan("sqlite-3.53.3", raw_sqlite_plan)
    assert profile.dialect == "sqlite"
    assert profile.has_index_scan is True
    assert profile.has_seq_scan is False
    assert profile.has_sort is True
    assert "INDEX" in profile.scan_types[0]


def test_duckdb_plan_analysis() -> None:
    raw_duckdb_plan = [
        [
            "physical_plan",
            (
                "┌───────────────────────────┐\n"
                "│          SEQ_SCAN         │\n"
                "│    ────────────────────   │\n"
                "│   Type: Sequential Scan   │\n"
                "│   Filters: tenant_id = 't1'│\n"
                "└───────────────────────────┘\n"
            ),
        ]
    ]
    profile = analyze_plan("duckdb-1.5.4", raw_duckdb_plan)
    assert profile.dialect == "duckdb"
    assert profile.has_seq_scan is True
    assert profile.has_index_scan is False
    assert profile.has_aggregate is False


def test_postgres_json_plan_analysis() -> None:
    raw_pg_plan = [
        {
            "Plan": {
                "Node Type": "Aggregate",
                "Strategy": "Hashed",
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Index Name": "orders_tenant_idx",
                        "Relation Name": "orders",
                    }
                ],
            }
        }
    ]
    profile = analyze_plan("postgresql-17.5", raw_pg_plan)
    assert profile.dialect == "postgresql"
    assert profile.has_index_scan is True
    assert profile.has_aggregate is True
    assert profile.has_sort is False


def test_plan_structural_equivalence_comparison() -> None:
    # 1. Parity between two plans preserving aggregation
    src = ExecutionPlanProfile(
        dialect="postgresql",
        scan_types=("INDEX_SCAN",),
        has_index_scan=True,
        has_seq_scan=False,
        join_types=(),
        has_aggregate=True,
        has_sort=False,
        raw_summary="Aggregate -> Index Scan",
    )
    tgt = ExecutionPlanProfile(
        dialect="sqlite",
        scan_types=("INDEX_SCAN",),
        has_index_scan=True,
        has_seq_scan=False,
        join_types=(),
        has_aggregate=True,
        has_sort=True,
        raw_summary="SEARCH orders USING INDEX",
    )
    comp = compare_plan_structural_intent(src, tgt)
    assert comp["equivalent"] is True
    assert comp["aggregationPreserved"] is True

    # 2. Imparity when source had aggregation but target lost it
    tgt_no_agg = ExecutionPlanProfile(
        dialect="duckdb",
        scan_types=("SEQ_SCAN",),
        has_index_scan=False,
        has_seq_scan=True,
        join_types=(),
        has_aggregate=False,
        has_sort=False,
        raw_summary="SEQ_SCAN",
    )
    comp_fail = compare_plan_structural_intent(src, tgt_no_agg)
    assert comp_fail["equivalent"] is False
    assert comp_fail["aggregationPreserved"] is False
