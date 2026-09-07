from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


MUTABLE_ALIAS_PATTERNS = [
    re.compile(r"(?i)(^|[-_/])(latest|main|master|head|stable|current)([-_/]|$)"),
    re.compile(r"(?i):latest$"),
]


def canonical_digest(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def load_spec(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)


def _mutable(value: str) -> bool:
    return any(pattern.search(value) for pattern in MUTABLE_ALIAS_PATTERNS)


def validate_candidate(spec: dict[str, Any]) -> list[str]:
    required = [
        "candidate_id",
        "source_commit",
        "model",
        "model_revision",
        "prompt_digest",
        "skill_manifest_digest",
        "rule_bundle_digest",
        "toolchain_image_digest",
        "oracle_version",
        "normalization_version",
    ]
    errors = [f"missing {key}" for key in required if not spec.get(key)]
    for field in ["source_commit", "model_revision", "toolchain_image_digest", "oracle_version", "normalization_version"]:
        value = str(spec.get(field, ""))
        if value and _mutable(value):
            errors.append(f"mutable alias is not allowed in {field}: {value}")
    source_commit = str(spec.get("source_commit", ""))
    if source_commit and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        errors.append("source_commit must be a 40-character lowercase Git SHA")
    for field in ["prompt_digest", "skill_manifest_digest", "rule_bundle_digest", "toolchain_image_digest"]:
        value = str(spec.get(field, ""))
        if value and not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            errors.append(f"{field} must be sha256:<64 hex>")
    return errors


def freeze_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    errors = validate_candidate(spec)
    if errors:
        raise ValueError("; ".join(errors))
    material = {key: value for key, value in spec.items() if key not in {"candidate_digest", "frozen_at"}}
    frozen = dict(material)
    frozen["schema_version"] = "1.1"
    frozen["frozen_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    frozen["candidate_digest"] = canonical_digest(material)
    return frozen


def freeze_candidate_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    frozen = freeze_candidate(load_spec(input_path))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return frozen
