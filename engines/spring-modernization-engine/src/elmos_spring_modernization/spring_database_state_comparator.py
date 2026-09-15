from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from decimal import Decimal
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class ColumnDiff:
    column_name: str
    baseline_value: Any
    shadow_value: Any
    diff_kind: str  # EXACT_MATCH, SCALE_TRUNCATION, PRECISION_LOSS, TIMEZONE_SHIFT, NULLABILITY_MISMATCH, VALUE_MISMATCH
    severity: str   # NONE, LOW, MEDIUM, HIGH, CRITICAL
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "baseline_value": str(self.baseline_value) if self.baseline_value is not None else None,
            "shadow_value": str(self.shadow_value) if self.shadow_value is not None else None,
            "diff_kind": self.diff_kind,
            "severity": self.severity,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RowDiff:
    table_name: str
    primary_key: dict[str, Any]
    status: str  # MATCH, DIFF, MISSING_IN_SHADOW, EXTRA_IN_SHADOW
    column_diffs: list[ColumnDiff] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "primary_key": self.primary_key,
            "status": self.status,
            "column_diffs": [cd.to_dict() for cd in self.column_diffs],
        }


@dataclass(frozen=True)
class TableDiffSummary:
    table_name: str
    baseline_rows: int
    shadow_rows: int
    matched_rows: int
    diff_rows: int
    missing_rows: int
    extra_rows: int
    detected_anomalies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "baseline_rows": self.baseline_rows,
            "shadow_rows": self.shadow_rows,
            "matched_rows": self.matched_rows,
            "diff_rows": self.diff_rows,
            "missing_rows": self.missing_rows,
            "extra_rows": self.extra_rows,
            "detected_anomalies": self.detected_anomalies,
        }


@dataclass(frozen=True)
class DatabaseStateReport:
    baseline_db_name: str
    shadow_db_name: str
    compared_tables: list[str]
    total_rows_compared: int
    total_diffs: int
    table_summaries: list[TableDiffSummary]
    row_diffs: list[RowDiff]
    verdict: str  # PASS, FLAGGED_ANOMALIES, FAIL_DATA_CORRUPTION
    integrity_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_db_name": self.baseline_db_name,
            "shadow_db_name": self.shadow_db_name,
            "compared_tables": self.compared_tables,
            "total_rows_compared": self.total_rows_compared,
            "total_diffs": self.total_diffs,
            "table_summaries": [ts.to_dict() for ts in self.table_summaries],
            "row_diffs": [rd.to_dict() for rd in self.row_diffs],
            "verdict": self.verdict,
            "integrity_sha256": self.integrity_sha256,
        }


class SpringDatabaseStateComparator:
    """Industrial-grade state comparator between baseline and shadow databases

    after dual-track production replay in Spring Boot 3.x modernizations.
    """

    @classmethod
    def compare_tables(
        cls,
        table_name: str,
        pk_columns: list[str],
        baseline_rows: list[dict[str, Any]],
        shadow_rows: list[dict[str, Any]],
    ) -> tuple[TableDiffSummary, list[RowDiff]]:
        """Compare rows of a single table indexed by pk_columns."""
        baseline_map: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in baseline_rows:
            key = tuple(row.get(pk) for pk in pk_columns)
            baseline_map[key] = row

        shadow_map: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in shadow_rows:
            key = tuple(row.get(pk) for pk in pk_columns)
            shadow_map[key] = row

        all_keys = set(baseline_map.keys()).union(set(shadow_map.keys()))

        row_diffs: list[RowDiff] = []
        matched_count = 0
        diff_count = 0
        missing_count = 0
        extra_count = 0
        anomalies: set[str] = set()

        for key in sorted(all_keys, key=lambda k: str(k)):
            pk_dict = {pk: key[i] for i, pk in enumerate(pk_columns)}
            if key in baseline_map and key not in shadow_map:
                missing_count += 1
                anomalies.add("MISSING_ROWS_IN_SHADOW")
                row_diffs.append(RowDiff(table_name, pk_dict, "MISSING_IN_SHADOW"))
            elif key not in baseline_map and key in shadow_map:
                extra_count += 1
                anomalies.add("UNEXPECTED_EXTRA_ROWS_IN_SHADOW")
                row_diffs.append(RowDiff(table_name, pk_dict, "EXTRA_IN_SHADOW"))
            else:
                base_row = baseline_map[key]
                shad_row = shadow_map[key]
                col_diffs = cls._compare_row_columns(base_row, shad_row)
                has_diff = any(cd.diff_kind != "EXACT_MATCH" for cd in col_diffs)
                if has_diff:
                    diff_count += 1
                    for cd in col_diffs:
                        if cd.diff_kind != "EXACT_MATCH":
                            anomalies.add(cd.diff_kind)
                    row_diffs.append(RowDiff(table_name, pk_dict, "DIFF", col_diffs))
                else:
                    matched_count += 1

        summary = TableDiffSummary(
            table_name=table_name,
            baseline_rows=len(baseline_rows),
            shadow_rows=len(shadow_rows),
            matched_rows=matched_count,
            diff_rows=diff_count,
            missing_rows=missing_count,
            extra_rows=extra_count,
            detected_anomalies=sorted(anomalies),
        )

        return summary, row_diffs

    @classmethod
    def _compare_row_columns(
        cls, base_row: dict[str, Any], shad_row: dict[str, Any]
    ) -> list[ColumnDiff]:
        diffs: list[ColumnDiff] = []
        all_cols = set(base_row.keys()).union(set(shad_row.keys()))

        for col in sorted(all_cols):
            base_val = base_row.get(col)
            shad_val = shad_row.get(col)

            diff = cls._compare_values(col, base_val, shad_val)
            diffs.append(diff)

        return diffs

    @classmethod
    def _compare_values(cls, column_name: str, base_val: Any, shad_val: Any) -> ColumnDiff:
        # Null check
        if base_val is None and shad_val is None:
            return ColumnDiff(column_name, None, None, "EXACT_MATCH", "NONE")
        if base_val is None and shad_val is not None:
            return ColumnDiff(
                column_name, None, shad_val, "NULLABILITY_MISMATCH", "HIGH",
                "Baseline was NULL but shadow is non-null"
            )
        if base_val is not None and shad_val is None:
            return ColumnDiff(
                column_name, base_val, None, "NULLABILITY_MISMATCH", "CRITICAL",
                "Shadow truncated non-null value to NULL"
            )

        # Direct equality check
        if base_val == shad_val:
            return ColumnDiff(column_name, base_val, shad_val, "EXACT_MATCH", "NONE")

        # Decimal / Numeric comparison (e.g., "1000.5000" vs "1000.50", or 10.12345 vs 10.12)
        if not isinstance(base_val, bool) and not isinstance(shad_val, bool):
            try:
                base_dec = Decimal(str(base_val))
                shad_dec = Decimal(str(shad_val))
                if base_dec == shad_dec:
                    b_str = str(base_val)
                    s_str = str(shad_val)
                    base_scale = len(b_str.split(".")[1]) if "." in b_str else 0
                    shad_scale = len(s_str.split(".")[1]) if "." in s_str else 0
                    if base_scale != shad_scale:
                        return ColumnDiff(
                            column_name, base_val, shad_val, "SCALE_TRUNCATION", "LOW",
                            f"Numeric scale changed from {base_scale} to {shad_scale}"
                        )
                    return ColumnDiff(column_name, base_val, shad_val, "EXACT_MATCH", "NONE")
                else:
                    diff_val = abs(base_dec - shad_dec)
                    if diff_val < Decimal("0.01"):
                        return ColumnDiff(
                            column_name, base_val, shad_val, "PRECISION_LOSS", "HIGH",
                            f"Precision loss: delta={diff_val}"
                        )
                    return ColumnDiff(
                        column_name, base_val, shad_val, "VALUE_MISMATCH", "CRITICAL",
                        f"Value mismatch: baseline={base_val}, shadow={shad_val}"
                    )
            except Exception:
                pass

        # Datetime comparison (including ISO strings with timezone offsets)
        b_str = str(base_val)
        s_str = str(shad_val)
        if ("T" in b_str or "-" in b_str) and ("T" in s_str or "-" in s_str):
            try:
                b_dt = datetime.datetime.fromisoformat(b_str.replace("Z", "+00:00"))
                s_dt = datetime.datetime.fromisoformat(s_str.replace("Z", "+00:00"))
                if b_dt.timestamp() == s_dt.timestamp():
                    return ColumnDiff(
                        column_name, base_val, shad_val, "TIMEZONE_SHIFT", "MEDIUM",
                        f"Representational timezone shift representing same instant"
                    )
            except Exception:
                pass

        # String / General fallback
        return ColumnDiff(
            column_name, base_val, shad_val, "VALUE_MISMATCH", "HIGH",
            f"Value mismatch: '{base_val}' != '{shad_val}'"
        )

    @classmethod
    def generate_report(
        cls,
        baseline_db: str,
        shadow_db: str,
        dataset: dict[str, dict[str, Any]],
    ) -> DatabaseStateReport:
        """dataset format: { table_name: { 'pk': ['id'], 'baseline': [...], 'shadow': [...] } }"""
        all_summaries: list[TableDiffSummary] = []
        all_diffs: list[RowDiff] = []
        total_rows = 0
        total_diff_count = 0
        has_critical = False

        for tbl, data in dataset.items():
            pk = data.get("pk", ["id"])
            b_rows = data.get("baseline", [])
            s_rows = data.get("shadow", [])

            summary, r_diffs = cls.compare_tables(tbl, pk, b_rows, s_rows)
            all_summaries.append(summary)
            all_diffs.extend(r_diffs)
            total_rows += summary.baseline_rows
            total_diff_count += summary.diff_rows + summary.missing_rows + summary.extra_rows

            for rd in r_diffs:
                if rd.status in ("MISSING_IN_SHADOW", "EXTRA_IN_SHADOW"):
                    has_critical = True
                for cd in rd.column_diffs:
                    if cd.severity in ("HIGH", "CRITICAL"):
                        has_critical = True

        if total_diff_count == 0:
            verdict = "PASS"
        elif has_critical:
            verdict = "FAIL_DATA_CORRUPTION"
        else:
            verdict = "FLAGGED_ANOMALIES"

        preliminary = {
            "baseline": baseline_db,
            "shadow": shadow_db,
            "total_rows": total_rows,
            "diffs": total_diff_count,
            "verdict": verdict,
            "tables": [s.to_dict() for s in all_summaries],
        }
        digest = hashlib.sha256(json.dumps(preliminary, sort_keys=True).encode("utf-8")).hexdigest()

        return DatabaseStateReport(
            baseline_db_name=baseline_db,
            shadow_db_name=shadow_db,
            compared_tables=sorted(dataset.keys()),
            total_rows_compared=total_rows,
            total_diffs=total_diff_count,
            table_summaries=all_summaries,
            row_diffs=all_diffs,
            verdict=verdict,
            integrity_sha256=digest,
        )
