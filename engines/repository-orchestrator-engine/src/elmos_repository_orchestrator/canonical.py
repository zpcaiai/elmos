from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


class CanonicalValueError(ValueError):
    pass


def canonical_value(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 64:
        raise CanonicalValueError("value exceeds maximum nesting depth")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalValueError("non-finite numbers are not supported")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalValueError("mapping keys must be strings")
        return {
            key: canonical_value(value[key], _depth=_depth + 1)
            for key in sorted(value)
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        return [canonical_value(item, _depth=_depth + 1) for item in value]
    raise CanonicalValueError(f"unsupported value type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
