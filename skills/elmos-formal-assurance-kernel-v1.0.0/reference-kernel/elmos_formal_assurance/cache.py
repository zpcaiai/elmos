from __future__ import annotations
from typing import Any
from .hashing import sha256_value

_REQUIRED = (
    "formula_hash", "semantic_profile_hash", "semantic_model_hash",
    "assumption_hash", "tcb_hash", "engine", "engine_version",
    "engine_digest", "engine_options", "bound", "source_hash", "target_hash",
)

def proof_cache_key(parts: dict[str, Any]) -> str:
    missing = [key for key in _REQUIRED if key not in parts]
    if missing:
        raise ValueError(f"missing proof-cache key parts: {', '.join(missing)}")
    normalized = {key: parts[key] for key in _REQUIRED}
    return sha256_value(normalized)
