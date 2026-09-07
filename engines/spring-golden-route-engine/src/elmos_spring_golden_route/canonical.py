"""Bounded canonical JSON helpers with duplicate-key rejection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import RequestValidationError

MAX_JSON_BYTES = 65_536
MAX_JSON_DEPTH = 12
MAX_JSON_ITEMS = 2_048


def canonical_json(
    value: object,
    *,
    max_depth: int = MAX_JSON_DEPTH,
    max_items: int = MAX_JSON_ITEMS,
) -> str:
    """Serialize a validated JSON value in a stable UTF-8 representation."""

    validate_json_value(value, max_depth=max_depth, max_items=max_items)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_bytes(
    value: object,
    *,
    max_depth: int = MAX_JSON_DEPTH,
    max_items: int = MAX_JSON_ITEMS,
) -> bytes:
    return canonical_json(value, max_depth=max_depth, max_items=max_items).encode("utf-8")


def sha256_digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RequestValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json_strict(
    raw: str | bytes,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
    max_items: int = MAX_JSON_ITEMS,
) -> object:
    if isinstance(raw, str):
        encoded = raw.encode("utf-8")
    elif isinstance(raw, bytes):
        encoded = raw
    else:
        raise RequestValidationError("JSON input must be str or bytes")
    if not encoded or len(encoded) > max_bytes:
        raise RequestValidationError(
            "JSON input size is outside the allowed range",
            details={"maximum_bytes": max_bytes, "actual_bytes": len(encoded)},
        )
    try:
        text = encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RequestValidationError("JSON input must be valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_no_duplicate_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                RequestValidationError(f"non-finite JSON number is forbidden: {token}")
            ),
        )
    except RequestValidationError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RequestValidationError("invalid JSON", details={"reason": str(exc)}) from exc
    validate_json_value(value, max_depth=max_depth, max_items=max_items)
    return value


def validate_json_value(
    value: object,
    *,
    max_depth: int = MAX_JSON_DEPTH,
    max_items: int = MAX_JSON_ITEMS,
) -> None:
    if type(max_depth) is not int or max_depth < 0:
        raise RequestValidationError("max_depth must be a non-negative integer")
    if type(max_items) is not int or max_items < 1:
        raise RequestValidationError("max_items must be a positive integer")
    item_count = 0

    def visit(current: object, depth: int) -> None:
        nonlocal item_count
        item_count += 1
        if item_count > max_items:
            raise RequestValidationError("JSON value contains too many items")
        if depth > max_depth:
            raise RequestValidationError("JSON value is nested too deeply")
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise RequestValidationError("JSON strings may not contain lone surrogate code points") from exc
            return
        if current is None or isinstance(current, (bool, int)):
            return
        if isinstance(current, float):
            raise RequestValidationError("floating-point JSON values are forbidden")
        if isinstance(current, Mapping):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise RequestValidationError("JSON object keys must be strings")
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise RequestValidationError(
                        "JSON object keys may not contain lone surrogate code points"
                    ) from exc
                visit(child, depth + 1)
            return
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            for child in current:
                visit(child, depth + 1)
            return
        raise RequestValidationError(f"unsupported JSON value type: {type(current).__name__}")

    visit(value, 0)
