from __future__ import annotations
import hashlib
import json
from typing import Any

def canonical_json(value: Any) -> bytes:
    """Stable JSON for package contracts (UTF-8, sorted keys, no NaN)."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False
    ).encode("utf-8")

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_json(value))
