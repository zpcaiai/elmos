"""Canonical JSON and digest primitives for the legacy-web engine."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Encode only interoperable JSON values with one stable representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_digest(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ValueError("digest must be sha256:<64 lowercase hex characters>")
    if any(ch not in "0123456789abcdef" for ch in value[7:]):
        raise ValueError("digest must be sha256:<64 lowercase hex characters>")
    return value


def finite_json(value: Any, *, depth: int = 0, max_depth: int = 32) -> Any:
    """Copy bounded JSON data and reject values that cannot be persisted safely."""

    if depth > max_depth:
        raise ValueError("JSON exceeds the maximum nesting depth")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if isinstance(value, list):
        return [finite_json(item, depth=depth + 1, max_depth=max_depth) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or "\x00" in key:
                raise ValueError("JSON object keys must be non-empty strings")
            result[key] = finite_json(item, depth=depth + 1, max_depth=max_depth)
        return result
    raise ValueError(f"unsupported JSON value: {type(value).__name__}")


def redact_text(value: str) -> str:
    """Remove secret-looking values while retaining stable shape for evidence."""

    patterns = (
        re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)?\s*)[^\s,;]+"),
        re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key|client[_-]?secret|credential)\s*[:=]\s*)[^\s,;]+"),
        re.compile(r"-----BEGIN [^-]+ PRIVATE KEY-----.*?-----END [^-]+ PRIVATE KEY-----", re.S),
    )
    result = value
    for pattern in patterns:
        result = pattern.sub(lambda match: match.group(1) + "<redacted>" if match.lastindex else "<redacted>", result)
    quoted_key = re.compile(r'''(?i)(["']?[A-Za-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret|credential)[A-Za-z0-9_.-]*["']?\s*:\s*["'])([^"']*)(["'])''')
    result = quoted_key.sub(lambda match: match.group(1) + "<redacted>" + match.group(3), result)
    return result


def redact_json(value: Any, *, key: str | None = None) -> Any:
    """Redact secret-shaped structured data before it becomes an artifact."""

    if key is not None and re.fullmatch(r"(?i).*?(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret|credential).*", key):
        return "<redacted>"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, dict):
        return {item_key: redact_json(item, key=item_key) for item_key, item in value.items()}
    return value
