"""Explicit normalization utilities for independent differential oracles."""

from __future__ import annotations

import copy
import json
import math
from decimal import Decimal
from typing import Any


def normalize(value: Any, *, unordered_lists: bool = False, float_digits: int = 12) -> Any:
    if isinstance(value, dict):
        return {str(key): normalize(item, unordered_lists=unordered_lists, float_digits=float_digits) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, list):
        items = [normalize(item, unordered_lists=unordered_lists, float_digits=float_digits) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False)) if unordered_lists else items
    if isinstance(value, tuple):
        return normalize(list(value), unordered_lists=unordered_lists, float_digits=float_digits)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if value == 0.0 and math.copysign(1.0, value) < 0:
            return "-0.0"
        return round(value, float_digits)
    return value


def remove_json_paths(value: Any, paths: list[str]) -> Any:
    result = copy.deepcopy(value)
    for path in paths:
        if not path.startswith("$."):
            continue
        current: Any = result
        parts = path[2:].split(".")
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(current, dict):
            current.pop(parts[-1], None)
    return result


def first_difference(left: Any, right: Any, path: str = "$") -> dict[str, Any] | None:
    if type(left) is not type(right):
        return {"path": path, "left": left, "right": right, "reason": "type-mismatch"}
    if isinstance(left, dict):
        if set(left) != set(right):
            return {"path": path, "left_keys": sorted(left), "right_keys": sorted(right), "reason": "key-mismatch"}
        for key in sorted(left):
            difference = first_difference(left[key], right[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path, "left_length": len(left), "right_length": len(right), "reason": "length-mismatch"}
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]")
            if difference:
                return difference
        return None
    return None if left == right else {"path": path, "left": left, "right": right, "reason": "value-mismatch"}
