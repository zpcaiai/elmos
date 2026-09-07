from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Difference:
    path: str
    before: Any
    after: Any


def first_difference(before: Any, after: Any, path: str = "$") -> Difference | None:
    if type(before) is not type(after):
        return Difference(path, before, after)
    if isinstance(before, dict):
        keys = sorted(set(before) | set(after))
        for key in keys:
            child = f"{path}.{key}"
            if key not in before:
                return Difference(child, None, after[key])
            if key not in after:
                return Difference(child, before[key], None)
            difference = first_difference(before[key], after[key], child)
            if difference is not None:
                return difference
        return None
    if isinstance(before, (list, tuple)):
        if len(before) != len(after):
            return Difference(f"{path}.length", len(before), len(after))
        for index, (left, right) in enumerate(zip(before, after)):
            difference = first_difference(left, right, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if before != after:
        return Difference(path, before, after)
    return None


_DIMENSION_REASON = {
    "provider": "PROVIDER_CHANGED",
    "model": "MODEL_CHANGED",
    "effort": "EFFORT_CHANGED",
    "tool_schema_digest": "TOOL_SCHEMA_CHANGED",
    "stable_prefix_digest": "PROMPT_SEGMENT_CHANGED",
    "repository_snapshot_digest": "PROJECT_SNAPSHOT_CHANGED",
    "public_interface_digest": "PUBLIC_INTERFACE_CHANGED",
    "rule_pack_digest": "RULE_PACK_CHANGED",
    "lockfile_digest": "LOCKFILE_CHANGED",
    "environment_snapshot_key": "ENVIRONMENT_CHANGED",
}


def classify_identity_change(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, Difference | None]:
    for key in _DIMENSION_REASON:
        if before.get(key) != after.get(key):
            return _DIMENSION_REASON[key], Difference(f"$.{key}", before.get(key), after.get(key))
    difference = first_difference(before, after)
    if difference is None:
        return "NO_IDENTITY_CHANGE", None
    return "UNKNOWN_IDENTITY_CHANGE", difference
