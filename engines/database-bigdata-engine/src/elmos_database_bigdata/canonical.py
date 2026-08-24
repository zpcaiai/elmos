"""Bounded canonical JSON utilities used by every runtime surface."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100_000
MAX_SAFE_INTEGER = (1 << 53) - 1


class CanonicalError(ValueError):
    """Raised when a value cannot be represented as bounded canonical JSON."""


def canonical_value(value: Any, *, label: str = "value") -> Any:
    """Copy exact JSON values while rejecting ambiguity and resource abuse."""

    remaining = [MAX_JSON_NODES]

    def visit(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise CanonicalError(f"{label} exceeds the JSON node limit")
        if depth > MAX_JSON_DEPTH:
            raise CanonicalError(f"{label} exceeds the JSON depth limit")
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_INTEGER:
                raise CanonicalError(f"{label} contains an unsafe JSON integer")
            return item
        if isinstance(item, float):
            raise CanonicalError(
                f"{label} contains a binary floating-point value; "
                "use a typed decimal string"
            )
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise CanonicalError(f"{label} contains invalid Unicode") from exc
            return item
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            keys = list(item)
            if not all(isinstance(key, str) and key for key in keys):
                raise CanonicalError(f"{label} object keys must be non-empty strings")
            for key in sorted(keys):
                result[key] = visit(item[key], depth + 1)
            return result
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [visit(child, depth + 1) for child in item]
        raise CanonicalError(
            f"{label} contains a non-JSON value: {type(item).__name__}"
        )

    result = visit(value, 0)
    if len(canonical_bytes(result)) > MAX_JSON_BYTES:
        raise CanonicalError(f"{label} exceeds the canonical JSON byte limit")
    return result


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalError("value is not canonical JSON") from exc


def canonical_digest(value: Any) -> str:
    normalized = canonical_value(value)
    return "sha256:" + hashlib.sha256(canonical_bytes(normalized)).hexdigest()


def strict_json_loads(text: str, *, label: str = "JSON document") -> Any:
    """Parse bounded JSON without duplicate keys or lossy binary floats."""

    if not isinstance(text, str):
        raise CanonicalError(f"{label} must be UTF-8 text")
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CanonicalError(f"{label} contains invalid Unicode") from exc
    if len(encoded) > MAX_JSON_BYTES:
        raise CanonicalError(f"{label} exceeds the JSON byte limit")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CanonicalError(f"{label} contains duplicate object key: {key}")
            result[key] = value
        return result

    def reject_float(token: str) -> Any:
        raise CanonicalError(
            f"{label} contains binary floating-point token {token!r}; "
            "use a typed decimal string"
        )

    def reject_constant(token: str) -> Any:
        raise CanonicalError(f"{label} contains forbidden numeric token: {token}")

    def parse_integer(token: str) -> int:
        digits = token.removeprefix("-")
        if len(digits) > 16:
            raise CanonicalError(f"{label} contains an unsafe JSON integer")
        value = int(token)
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalError(f"{label} contains an unsafe JSON integer")
        return value

    try:
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_float=reject_float,
            parse_int=parse_integer,
            parse_constant=reject_constant,
        )
    except CanonicalError:
        raise
    except (ValueError, RecursionError) as exc:
        raise CanonicalError(f"{label} is not valid bounded JSON: {exc}") from exc
    return canonical_value(value, label=label)


__all__ = [
    "MAX_JSON_BYTES",
    "MAX_JSON_DEPTH",
    "MAX_JSON_NODES",
    "MAX_SAFE_INTEGER",
    "CanonicalError",
    "canonical_bytes",
    "canonical_digest",
    "canonical_value",
    "strict_json_loads",
]
