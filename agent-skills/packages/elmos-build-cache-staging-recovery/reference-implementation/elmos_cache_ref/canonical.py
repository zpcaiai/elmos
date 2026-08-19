from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(value[k]) for k in sorted(value, key=lambda x: str(x))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).replace("\\", "/")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not canonical")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _normalize(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def action_key(document: dict[str, Any]) -> str:
    clean = dict(document)
    clean.pop("action_key", None)
    clean.pop("explanation", None)
    return sha256_digest(canonical_json_bytes(clean))
