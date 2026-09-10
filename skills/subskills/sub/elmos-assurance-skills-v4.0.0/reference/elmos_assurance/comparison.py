"""Typed result comparison; no implicit deduplication or numeric tolerance."""
from __future__ import annotations
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any


def cell(value: dict[str, Any]) -> tuple[str, Any]:
    if type(value) is not dict or set(value) != {"type", "value"}:
        raise ValueError("INVALID_CELL")
    kind, raw = value["type"], value["value"]
    if kind == "null" and raw is None:
        return ("null", None)
    if kind == "int" and type(raw) is int:
        return ("int", raw)
    if kind == "bool" and type(raw) is bool:
        return ("bool", raw)
    if kind in {"string", "timestamp", "bytes-hex"} and type(raw) is str:
        # Timestamps are exact by default. Explicit time normalization belongs
        # to a separately approved and tested comparator policy.
        return (kind, raw)
    if kind == "decimal" and type(raw) is str:
        try:
            number = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("INVALID_DECIMAL") from exc
        if not number.is_finite():
            raise ValueError("NONFINITE_DECIMAL")
        return (kind, number)
    raise ValueError("UNSUPPORTED_OR_MISTYPED_CELL")


def compare_rows(left: list[list[dict[str, Any]]],
                 right: list[list[dict[str, Any]]], mode: str = "bag") -> bool:
    a = [tuple(cell(v) for v in row) for row in left]
    b = [tuple(cell(v) for v in row) for row in right]
    if mode == "ordered":
        return a == b
    if mode == "bag":
        return Counter(a) == Counter(b)
    if mode == "set":
        return set(a) == set(b)
    raise ValueError("UNSUPPORTED_COMPARISON_MODE")
