"""Strict canonical JSON helpers used for every runtime identity."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any


class CanonicalValueError(ValueError):
    """Raised when a value cannot be represented as bounded canonical JSON."""


MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000
MAX_JSON_BYTES = 8 * 1024 * 1024


def strict_json_copy(value: Any, *, field: str = "value") -> Any:
    """Return a JSON-only copy while rejecting aliases and pathological input."""

    remaining = [MAX_JSON_NODES]

    def visit(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise CanonicalValueError(f"{field} exceeds the JSON node limit")
        if depth > MAX_JSON_DEPTH:
            raise CanonicalValueError(f"{field} exceeds the JSON depth limit")
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise CanonicalValueError(f"{field} contains a non-finite number")
            return item
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise CanonicalValueError(f"{field} contains invalid Unicode") from exc
            return item
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, Mapping):
            copied: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    raise CanonicalValueError(f"{field} contains a non-string or empty object key")
                if key in copied:
                    raise CanonicalValueError(f"{field} contains a duplicate key")
                copied[key] = visit(child, depth + 1)
            return copied
        raise CanonicalValueError(f"{field} contains non-JSON type {type(item).__name__}")

    copied = visit(value, 0)
    encoded = json.dumps(
        copied,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise CanonicalValueError(f"{field} exceeds the canonical JSON byte limit")
    return copied


def canonical_json(value: Any) -> str:
    copied = strict_json_copy(value)
    return json.dumps(
        copied,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def is_sha256_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        return False
    return all(character in "0123456789abcdef" for character in value[7:])
