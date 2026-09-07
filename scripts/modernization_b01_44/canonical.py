#!/usr/bin/env python3
"""Canonicalisation, content addressing and stable ordering primitives.

Every deterministic guarantee in this runtime reduces to the functions in this
module: two executions are identical exactly when their canonical bytes are
identical.  Nothing here reads mutable process state (clock, PID, locale,
hash seed), so the same value always produces the same digest.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
PREFIXED_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


class CanonicalError(ValueError):
    """Raised when a value cannot be canonicalised deterministically."""


def _assert_canonicalisable(value: Any, path: str) -> None:
    if isinstance(value, float):
        # Floats have platform dependent repr edge cases; the contract requires
        # callers to pass decimal strings so a digest can never drift.
        raise CanonicalError(f"float is not canonicalisable at {path}; use a decimal string")
    if isinstance(value, (set, frozenset)):
        raise CanonicalError(f"set has no deterministic order at {path}; use a sorted list")
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalError(f"non-string mapping key at {path}: {key!r}")
            _assert_canonicalisable(value[key], f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_canonicalisable(item, f"{path}[{index}]")
    elif not isinstance(value, (str, int, bool, type(None))):
        raise CanonicalError(f"unsupported type {type(value).__name__} at {path}")


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 encoding of ``value``.

    Mapping keys are sorted, separators are fixed and non-ASCII characters are
    preserved verbatim so that the encoding is locale independent.
    """

    _assert_canonicalisable(value, "$")
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def digest(value: Any) -> str:
    """Content address for any canonicalisable value (bare hex, no prefix)."""

    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def is_digest(value: Any) -> bool:
    return isinstance(value, str) and DIGEST_RE.match(value) is not None


def stable_sort(items: Iterable[Any], *, key: str | None = None) -> list[Any]:
    """Order ``items`` by canonical bytes so concurrency cannot change output."""

    materialised = list(items)
    if key is None:
        return sorted(materialised, key=canonical_bytes)
    return sorted(materialised, key=lambda item: (canonical_bytes(item[key]), canonical_bytes(item)))


def idempotency_key(*parts: Any) -> str:
    """Derive a stable idempotency key from the caller supplied parts."""

    if not parts:
        raise CanonicalError("idempotency key requires at least one part")
    return digest({"idempotency_parts": list(parts)})


def parse_instant(value: Any, field: str = "timestamp") -> datetime:
    if not isinstance(value, str):
        raise CanonicalError(f"{field} must be an RFC 3339 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:  # pragma: no cover - message passthrough
        raise CanonicalError(f"{field} is not a valid RFC 3339 instant: {value}") from exc
    if parsed.tzinfo is None:
        raise CanonicalError(f"{field} must carry an explicit UTC offset: {value}")
    return parsed.astimezone(timezone.utc)


def format_instant(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
