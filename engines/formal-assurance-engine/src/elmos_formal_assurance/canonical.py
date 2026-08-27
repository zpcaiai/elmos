from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value cannot be safely bound to a digest."""


_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _json_safe(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"{path}: non-finite numbers are forbidden")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"{path}: object keys must be strings")
            result[key] = _json_safe(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)
        ]
    raise CanonicalizationError(
        f"{path}: unsupported JSON value {type(value).__name__}"
    )


def canonical_json(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON with NaN and custom values rejected."""

    return json.dumps(
        _json_safe(value),
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
        raise CanonicalizationError(f"{path}: expected lowercase sha256 digest")
    return value if value.startswith("sha256:") else "sha256:" + value


def validate_identifier(value: Any, path: str = "id") -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CanonicalizationError(f"{path}: invalid identifier")
    return value


def normalized_text(value: Any, path: str = "text") -> str:
    if not isinstance(value, str):
        raise CanonicalizationError(f"{path}: expected string")
    return " ".join(value.split())
