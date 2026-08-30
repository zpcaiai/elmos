"""Canonical data and identity helpers for the semantic-assurance runtime.

The runtime only accepts bounded JSON values.  Digests are always calculated
over one deterministic UTF-8 representation so evidence, idempotency and
replay identities cannot disagree about whitespace, key ordering or NaN.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value cannot be safely bound to a canonical digest."""


_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SECRET_FIELD = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|apikey|private[_-]?key|privatekey|credential)",
    re.IGNORECASE,
)


def _json_safe(
    value: Any,
    *,
    path: str = "$",
    depth: int = 0,
    max_depth: int = 32,
) -> Any:
    if depth > max_depth:
        raise CanonicalizationError(f"{path}: JSON nesting exceeds {max_depth}")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"{path}: non-finite numbers are forbidden")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"{path}: object keys must be strings")
            if any(ord(character) < 32 or ord(character) == 127 for character in key):
                raise CanonicalizationError(f"{path}: object key contains a control character")
            normalized[key] = _json_safe(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
                max_depth=max_depth,
            )
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _json_safe(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
                max_depth=max_depth,
            )
            for index, item in enumerate(value)
        ]
    raise CanonicalizationError(
        f"{path}: unsupported JSON value {type(value).__name__}"
    )


def canonical_value(value: Any) -> Any:
    """Return a recursively validated JSON-compatible value."""

    return _json_safe(value)


def canonical_json(value: Any) -> bytes:
    """Serialize *value* deterministically as UTF-8 JSON."""

    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_value(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def validate_digest(value: Any, path: str = "digest") -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise CanonicalizationError(f"{path}: expected a lowercase SHA-256 digest")
    return value if value.startswith("sha256:") else "sha256:" + value


def validate_identifier(value: Any, path: str = "id") -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise CanonicalizationError(f"{path}: invalid identifier")
    return value


def require_bounded_json(
    value: Any,
    *,
    path: str = "$",
    max_bytes: int = 2 * 1024 * 1024,
) -> Any:
    normalized = _json_safe(value, path=path)
    encoded = canonical_json(normalized)
    if len(encoded) > max_bytes:
        raise CanonicalizationError(
            f"{path}: canonical request exceeds {max_bytes} bytes"
        )
    return normalized


def reject_inline_secrets(value: Any, path: str = "$.") -> None:
    """Reject likely secret values; callers must pass opaque ``*Ref`` fields.

    This is deliberately conservative.  A key ending in ``Ref`` is permitted
    only when its value is a short identifier, never the secret material.
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"{path}: object keys must be strings")
            lowered = key.lower()
            if _SECRET_FIELD.search(lowered):
                if lowered.endswith("ref") or lowered.endswith("_ref"):
                    validate_identifier(item, f"{path}{key}")
                else:
                    raise CanonicalizationError(
                        f"{path}{key}: inline secret material is forbidden; use a reference"
                    )
            reject_inline_secrets(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_inline_secrets(item, f"{path}[{index}].")


__all__ = [
    "CanonicalizationError",
    "canonical_json",
    "canonical_value",
    "digest_bytes",
    "digest_value",
    "reject_inline_secrets",
    "require_bounded_json",
    "validate_digest",
    "validate_identifier",
]
