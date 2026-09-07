from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


def normalize(value: Any, *, unordered_lists: bool = False, float_digits: int = 12) -> Any:
    if isinstance(value, dict):
        return {str(k): normalize(v, unordered_lists=unordered_lists, float_digits=float_digits) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, list):
        items = [normalize(v, unordered_lists=unordered_lists, float_digits=float_digits) for v in value]
        if unordered_lists:
            return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False))
        return items
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
    import copy
    out = copy.deepcopy(value)
    for path in paths:
        if not path.startswith("$."):
            continue
        parts = path[2:].split(".")
        current = out
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(current, dict):
            current.pop(parts[-1], None)
    return out


def first_difference(left: Any, right: Any, path: str = "$") -> dict[str, Any] | None:
    if type(left) is not type(right):
        return {"path": path, "left": left, "right": right, "reason": "type-mismatch"}
    if isinstance(left, dict):
        if set(left) != set(right):
            return {"path": path, "left_keys": sorted(left), "right_keys": sorted(right), "reason": "key-mismatch"}
        for key in sorted(left):
            found = first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return {"path": path, "left_length": len(left), "right_length": len(right), "reason": "length-mismatch"}
        for i, (a, b) in enumerate(zip(left, right)):
            found = first_difference(a, b, f"{path}[{i}]")
            if found:
                return found
        return None
    if left != right:
        return {"path": path, "left": left, "right": right, "reason": "value-mismatch"}
    return None
