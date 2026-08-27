"""Immutable release-candidate validation and freezing."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import yaml

from .canonical import digest_json


_MUTABLE = re.compile(r"(?i)(^|[-_/])(latest|main|master|head|stable|current)([-_/]|$)|:latest$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_spec(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix.lower() in {".yaml", ".yml"} else __import__("json").loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("candidate specification must be an object")
    return value


def validate_candidate(spec: dict[str, Any]) -> list[str]:
    required = ("candidate_id", "source_commit", "model", "model_revision", "prompt_digest", "skill_manifest_digest", "rule_bundle_digest", "toolchain_image_digest", "oracle_version", "normalization_version")
    errors = [f"missing {key}" for key in required if not spec.get(key)]
    for field in ("source_commit", "model_revision", "toolchain_image_digest", "oracle_version", "normalization_version"):
        value = str(spec.get(field, ""))
        if value and _MUTABLE.search(value):
            errors.append(f"mutable alias is not allowed in {field}: {value}")
    if spec.get("source_commit") and not re.fullmatch(r"[0-9a-f]{40}", str(spec["source_commit"])):
        errors.append("source_commit must be a 40-character lowercase Git SHA")
    for field in ("prompt_digest", "skill_manifest_digest", "rule_bundle_digest", "toolchain_image_digest"):
        if spec.get(field) and not _DIGEST.fullmatch(str(spec[field])):
            errors.append(f"{field} must be sha256:<64 hex>")
    return errors


def freeze_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    errors = validate_candidate(spec)
    if errors:
        raise ValueError("; ".join(errors))
    material = {key: value for key, value in spec.items() if key not in {"candidate_digest", "frozen_at"}}
    frozen = dict(material)
    frozen.update({"schema_version": "1.1", "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(), "candidate_digest": "sha256:" + digest_json(material)})
    return frozen


def freeze_candidate_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    frozen = freeze_candidate(load_spec(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(__import__("json").dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return frozen


def verify_frozen_candidate(spec: dict[str, Any]) -> list[str]:
    """Verify both the immutable field contract and its content digest."""

    errors = validate_candidate(spec)
    candidate_digest = str(spec.get("candidate_digest", ""))
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest):
        errors.append("candidate_digest must be sha256:<64 hex>")
    material = {key: value for key, value in spec.items() if key not in {"candidate_digest", "frozen_at"}}
    if candidate_digest and candidate_digest != "sha256:" + digest_json(material):
        errors.append("candidate_digest does not match frozen candidate fields")
    return errors
