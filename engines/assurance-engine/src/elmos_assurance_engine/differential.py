"""Implementation of B03: Typed differential comparison and state reconciliation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import GateDecision


class TypedDifferentialComparator:
    """Strict typed comparison of runtime rows/states without permissive lossy coercion."""

    @classmethod
    def compare_rows(
        cls,
        left_rows: Sequence[Mapping[str, Any]],
        right_rows: Sequence[Mapping[str, Any]],
        key_column: str,
    ) -> tuple[GateDecision, list[str]]:
        reasons: list[str] = []

        if len(left_rows) != len(right_rows):
            reasons.append(f"ROW_COUNT_MISMATCH: left={len(left_rows)}, right={len(right_rows)}")
            return GateDecision.FAIL, reasons

        left_by_key = {r[key_column]: r for r in left_rows if key_column in r}
        right_by_key = {r[key_column]: r for r in right_rows if key_column in r}

        if set(left_by_key.keys()) != set(right_by_key.keys()):
            missing_left = set(right_by_key.keys()) - set(left_by_key.keys())
            missing_right = set(left_by_key.keys()) - set(right_by_key.keys())
            reasons.append(f"KEY_SET_MISMATCH: missing_left={missing_left}, missing_right={missing_right}")
            return GateDecision.FAIL, reasons

        for k, left_row in left_by_key.items():
            right_row = right_by_key[k]
            # Check fields
            for col, left_val in left_row.items():
                if col not in right_row:
                    reasons.append(f"COLUMN_MISSING_IN_RIGHT: row_key={k}, col={col}")
                    continue
                right_val = right_row[col]
                # Type strictness: floats prohibited
                if isinstance(left_val, float) or isinstance(right_val, float):
                    reasons.append(f"FLOAT_PROHIBITED_IN_TYPED_COMPARISON: col={col}")
                    return GateDecision.FAIL, reasons
                if left_val != right_val:
                    reasons.append(
                        f"VALUE_MISMATCH: row_key={k}, col={col}: left={left_val!r} != right={right_val!r}"
                    )

        if reasons:
            return GateDecision.FAIL, reasons
        return GateDecision.PASS, ["TYPED_DIFFERENTIAL_MATCH_EXACT"]
