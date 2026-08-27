"""Canonical serialization and input validation shared by every boundary."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


class CanonicalizationError(ValueError):
    """The value cannot be represented as deterministic JSON."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError("value is not canonical JSON") from exc


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_after(seconds: int) -> str:
    if seconds < 1:
        raise ValueError("seconds must be positive")
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def require_nonempty(value: Any, field: str, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    result = value.strip()
    if len(result) > max_length:
        raise ValueError(f"{field} exceeds maximum length {max_length}")
    return result


def require_uuid(value: Any, field: str) -> str:
    text = require_nonempty(value, field, 64)
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc


def json_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be a JSON object")
    try:
        canonical_bytes(value)
    except CanonicalizationError as exc:
        raise ValueError(f"{field} contains unsupported JSON values") from exc
    return value
