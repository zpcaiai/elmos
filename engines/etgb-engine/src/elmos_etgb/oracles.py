"""Independent comparison oracles for observable ETGB behavior."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Difference:
    path: str
    reason: str
    left: Any = None
    right: Any = None

    def as_dict(self) -> dict[str, Any]:
        value = {"path": self.path, "reason": self.reason}
        if self.left is not None:
            value["left"] = self.left
        if self.right is not None:
            value["right"] = self.right
        return value


def _path_parts(path: str) -> list[str | int]:
    if path in {"", "$"}:
        return []
    if not path.startswith("$"):
        raise ValueError(f"JSON path must start with $: {path}")
    parts: list[str | int] = []
    token = ""
    index = 1
    while index < len(path):
        char = path[index]
        if char == ".":
            if token:
                parts.append(token)
                token = ""
            index += 1
            continue
        if char == "[":
            if token:
                parts.append(token)
                token = ""
            end = path.find("]", index)
            if end == -1:
                raise ValueError(f"unclosed JSON path index: {path}")
            raw = path[index + 1 : end]
            if raw == "*":
                parts.append(raw)
            elif raw.isdigit():
                parts.append(int(raw))
            else:
                raise ValueError(f"unsupported JSON path index: {raw}")
            index = end + 1
            continue
        token += char
        index += 1
    if token:
        parts.append(token)
    return parts


def _ignored(path: str, ignore_paths: Iterable[str]) -> bool:
    for pattern in ignore_paths:
        parts = _path_parts(pattern)
        actual = _path_parts(path)
        if len(parts) != len(actual):
            continue
        if all(expected == "*" or expected == actual_part for expected, actual_part in zip(parts, actual)):
            return True
    return False


def _equal_numbers(left: Any, right: Any, *, absolute: float, relative: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool) or not isinstance(left, (int, float, Decimal)) or not isinstance(right, (int, float, Decimal)):
        return False
    left_nan = isinstance(left, float) and math.isnan(left)
    right_nan = isinstance(right, float) and math.isnan(right)
    if left_nan or right_nan:
        return left_nan and right_nan
    return abs(float(left) - float(right)) <= max(absolute, relative * max(abs(float(left)), abs(float(right))))


def first_difference(left: Any, right: Any, *, path: str = "$", ignore_paths: Iterable[str] = (), unordered_paths: Iterable[str] = (), absolute_tolerance: float = 0.0, relative_tolerance: float = 0.0) -> Difference | None:
    if _ignored(path, ignore_paths):
        return None
    if isinstance(left, (int, float, Decimal)) and not isinstance(left, bool) and isinstance(right, (int, float, Decimal)) and not isinstance(right, bool):
        return None if _equal_numbers(left, right, absolute=absolute_tolerance, relative=relative_tolerance) else Difference(path, "numeric-tolerance-mismatch", left, right)
    if type(left) is not type(right):
        return Difference(path, "type-mismatch", type(left).__name__, type(right).__name__)
    if isinstance(left, Mapping):
        if set(left) != set(right):
            return Difference(path, "key-mismatch", sorted(left), sorted(right))
        for key in sorted(left, key=str):
            difference = first_difference(left[key], right[key], path=f"{path}.{key}", ignore_paths=ignore_paths, unordered_paths=unordered_paths, absolute_tolerance=absolute_tolerance, relative_tolerance=relative_tolerance)
            if difference:
                return difference
        return None
    if isinstance(left, list):
        if _ignored(path, unordered_paths):
            left_items = sorted(left, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str))
            right_items = sorted(right, key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, default=str))
        else:
            left_items, right_items = left, right
        if len(left_items) != len(right_items):
            return Difference(path, "length-mismatch", len(left_items), len(right_items))
        for index, (left_item, right_item) in enumerate(zip(left_items, right_items)):
            difference = first_difference(left_item, right_item, path=f"{path}[{index}]", ignore_paths=ignore_paths, unordered_paths=unordered_paths, absolute_tolerance=absolute_tolerance, relative_tolerance=relative_tolerance)
            if difference:
                return difference
        return None
    if left != right:
        return Difference(path, "value-mismatch", left, right)
    return None


def compare_json(left: Any, right: Any, *, ignore_paths: Iterable[str] = (), unordered_paths: Iterable[str] = (), absolute_tolerance: float = 0.0, relative_tolerance: float = 0.0) -> dict[str, Any]:
    ignored = list(ignore_paths)
    unordered = list(unordered_paths)
    difference = first_difference(left, right, ignore_paths=ignored, unordered_paths=unordered, absolute_tolerance=absolute_tolerance, relative_tolerance=relative_tolerance)
    return {
        "type": "json-equivalence",
        "passed": difference is None,
        "first_difference": difference.as_dict() if difference else None,
        "normalization": {"ignore_paths": ignored, "unordered_paths": unordered, "absolute_tolerance": absolute_tolerance, "relative_tolerance": relative_tolerance},
    }


def compare_trace(left: list[dict[str, Any]], right: list[dict[str, Any]], *, happens_before: Iterable[tuple[str, str]] = ()) -> dict[str, Any]:
    """Compare event identity and declared happens-before constraints."""

    left_names = [str(item.get("event")) for item in left]
    right_names = [str(item.get("event")) for item in right]
    if left_names != right_names:
        return {"type": "trace-equivalence", "passed": False, "first_difference": {"path": "$.events", "reason": "event-sequence-mismatch", "left": left_names, "right": right_names}}
    for before, after in happens_before:
        if before in right_names and after in right_names and right_names.index(before) >= right_names.index(after):
            return {"type": "trace-equivalence", "passed": False, "first_difference": {"path": "$.events", "reason": "happens-before-violation", "before": before, "after": after}}
    return {"type": "trace-equivalence", "passed": True, "first_difference": None}
