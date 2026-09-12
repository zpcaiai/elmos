#!/usr/bin/env python3
"""Canonical JSON, content addressing, stable sorting and idempotency keys."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def digest(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = canonical_bytes(value)
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def idempotency_key(*parts: Any) -> str:
    return digest([list(parts) if isinstance(parts, tuple) else parts])


def format_instant(dt: datetime | None = None) -> str:
    target = dt or datetime.now(timezone.utc)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    else:
        target = target.astimezone(timezone.utc)
    return target.strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_sort(items: Iterable[T], key: Callable[[T], Any] | None = None) -> list[T]:
    result = list(items)
    if key is None:
        result.sort(key=lambda item: canonical_bytes(item))
    else:
        result.sort(key=lambda item: (key(item), canonical_bytes(item)))
    return result
