#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_BINDINGS: tuple[tuple[str, str], ...] = (
    ("pack.json", "database-pack.schema.json"),
    ("support-matrix.json", "database-support-matrix.schema.json"),
    ("route-matrix.json", "database-route-matrix.schema.json"),
    ("source-fingerprint/manifest.json", "workload-fingerprint.schema.json"),
    ("canonical-ir/model.json", "canonical-db-ir.schema.json"),
    ("target-profile/profile.json", "database-target-profile.schema.json"),
    ("migration/data-migration-plan.json", "data-migration-plan.schema.json"),
    ("certification/evidence.json", "database-evidence.schema.json"),
    ("certification/certification.json", "database-certification.schema.json"),
)

SIDE_FIELDS = (
    "engine",
    "versions",
    "edition",
    "dialect",
    "driver_versions",
    "charset",
    "collation",
    "timezone",
    "extensions",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return value


def schema_errors(pack: Path) -> list[str]:
    errors: list[str] = []
    for relative_path, schema_name in SCHEMA_BINDINGS:
        instance_path = pack / relative_path
        schema_path = ROOT / "schemas" / "batch31" / schema_name
        try:
            instance = load_json(instance_path)
            schema = load_json(schema_path)
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            for failure in sorted(
                validator.iter_errors(instance),
                key=lambda item: list(item.absolute_path),
            ):
                location = "/".join(str(part) for part in failure.absolute_path) or "$"
                errors.append(f"{relative_path}:{location}: {failure.message}")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    return errors


def canonical_side(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {field: value.get(field) for field in SIDE_FIELDS}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def resolve_evidence_ref(pack: Path, reference: object) -> Path | None:
    if not isinstance(reference, str) or not reference:
        return None
    pure = PurePosixPath(reference)
    if pure.is_absolute() or ".." in pure.parts or pure.parts[0] in {".", ""}:
        return None
    candidate = pack.joinpath(*pure.parts)
    try:
        candidate.relative_to(pack)
    except ValueError:
        return None
    if candidate.is_symlink() or not candidate.is_file():
        return None
    return candidate


def evidence_ref_errors(
    pack: Path,
    references: list[object],
    digests: object,
    *,
    label: str,
) -> list[str]:
    errors: list[str] = []
    digest_map = digests if isinstance(digests, dict) else {}
    if set(digest_map) != {ref for ref in references if isinstance(ref, str)}:
        errors.append(f"{label} evidence_refs and evidence_digests keys differ")
    for reference in references:
        path = resolve_evidence_ref(pack, reference)
        if path is None:
            errors.append(f"{label} invalid or missing evidence ref: {reference!r}")
            continue
        expected = digest_map.get(reference)
        actual = sha256_file(path)
        if expected != actual:
            errors.append(f"{label} evidence digest mismatch: {reference}")
        try:
            value = load_json(path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            continue
        if value.get("pack_key") != pack.name:
            errors.append(f"{label} evidence pack_key mismatch: {reference}")
    return errors
