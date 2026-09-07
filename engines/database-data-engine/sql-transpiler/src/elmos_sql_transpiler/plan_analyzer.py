from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionPlanProfile:
    dialect: str
    scan_types: tuple[str, ...]
    has_index_scan: bool
    has_seq_scan: bool
    join_types: tuple[str, ...]
    has_aggregate: bool
    has_sort: bool
    raw_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_postgres_nodes(plan_node: dict[str, Any], nodes: list[str]) -> None:
    node_type = plan_node.get("Node Type", "")
    if node_type:
        nodes.append(node_type)
    for child in plan_node.get("Plans", []):
        if isinstance(child, dict):
            _extract_postgres_nodes(child, nodes)


def analyze_plan(profile_id: str, raw_plan: Any) -> ExecutionPlanProfile:
    """Analyze a raw execution plan from Postgres, SQLite, or DuckDB into canonical structure."""
    dialect = profile_id.split("-")[0].lower()
    scan_types: list[str] = []
    join_types: list[str] = []
    has_agg = False
    has_sort = False
    summary_parts: list[str] = []

    if dialect == "postgresql":
        root_dict: dict[str, Any] = {}
        if isinstance(raw_plan, list) and raw_plan and isinstance(raw_plan[0], dict):
            root_dict = raw_plan[0]
        elif isinstance(raw_plan, dict):
            root_dict = raw_plan

        plan_root = root_dict.get("Plan", {})
        nodes: list[str] = []
        if isinstance(plan_root, dict):
            _extract_postgres_nodes(plan_root, nodes)

        for n in nodes:
            n_upper = n.upper()
            if "INDEX" in n_upper:
                scan_types.append("INDEX_SCAN")
            elif "SCAN" in n_upper:
                scan_types.append("SEQ_SCAN")
            if "JOIN" in n_upper:
                join_types.append(n_upper)
            if "AGGREGATE" in n_upper or "AGG" in n_upper:
                has_agg = True
            if "SORT" in n_upper:
                has_sort = True
        summary_parts = nodes

    elif dialect == "sqlite":
        if isinstance(raw_plan, list):
            for row in raw_plan:
                if isinstance(row, (list, tuple)) and len(row) >= 4:
                    detail = str(row[3]).upper()
                    summary_parts.append(detail)
                    if (
                        "USING INDEX" in detail
                        or "USING COVERING INDEX" in detail
                        or "USING INTEGER PRIMARY KEY" in detail
                    ):
                        scan_types.append("INDEX_SCAN")
                    elif "SCAN" in detail:
                        scan_types.append("SEQ_SCAN")
                    if "JOIN" in detail:
                        join_types.append("JOIN")
                    if "GROUP BY" in detail:
                        has_agg = True
                    if "ORDER BY" in detail or "TEMP B-TREE" in detail:
                        has_sort = True

    elif dialect == "duckdb":
        plan_text = ""
        if (
            isinstance(raw_plan, list)
            and raw_plan
            and isinstance(raw_plan[0], (list, tuple))
            and len(raw_plan[0]) >= 2
        ):
            plan_text = str(raw_plan[0][1]).upper()
        else:
            plan_text = str(raw_plan).upper()

        summary_parts.append(plan_text[:200])
        if "INDEX_SCAN" in plan_text:
            scan_types.append("INDEX_SCAN")
        if "SEQ_SCAN" in plan_text or "SEQUENTIAL SCAN" in plan_text:
            scan_types.append("SEQ_SCAN")
        if "JOIN" in plan_text:
            join_types.append("JOIN")
        if "GROUP_BY" in plan_text or "AGGREGATE" in plan_text:
            has_agg = True
        if "ORDER_BY" in plan_text or "SORT" in plan_text:
            has_sort = True

    else:
        summary_parts.append(f"UNSUPPORTED_PLAN_ANALYSIS_{dialect}")

    has_index = "INDEX_SCAN" in scan_types
    has_seq = "SEQ_SCAN" in scan_types
    raw_summary = " -> ".join(summary_parts[:5])

    return ExecutionPlanProfile(
        dialect=dialect,
        scan_types=tuple(sorted(set(scan_types))),
        has_index_scan=has_index,
        has_seq_scan=has_seq,
        join_types=tuple(sorted(set(join_types))),
        has_aggregate=has_agg,
        has_sort=has_sort,
        raw_summary=raw_summary,
    )


def compare_plan_structural_intent(
    source_plan: ExecutionPlanProfile,
    target_plan: ExecutionPlanProfile,
) -> dict[str, Any]:
    """Compare high-level execution plan intent between source and target engines."""
    agg_parity = source_plan.has_aggregate == target_plan.has_aggregate
    sort_parity = (not source_plan.has_sort) or target_plan.has_sort or target_plan.has_index_scan

    equivalent = agg_parity and sort_parity

    return {
        "equivalent": equivalent,
        "aggregationPreserved": agg_parity,
        "sortPreserved": sort_parity,
        "sourceDialect": source_plan.dialect,
        "targetDialect": target_plan.dialect,
        "sourceScanTypes": list(source_plan.scan_types),
        "targetScanTypes": list(target_plan.scan_types),
        "sourceHasAggregate": source_plan.has_aggregate,
        "targetHasAggregate": target_plan.has_aggregate,
    }
