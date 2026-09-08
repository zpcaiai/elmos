#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pack_contract import canonical_side, evidence_ref_errors, load_json, schema_errors

REQUIRED_DIRS = (
    "source-fingerprint",
    "source-snapshots",
    "canonical-ir",
    "target-profile",
    "transformations",
    "compatibility",
    "migration",
    "corpus/development",
    "corpus/holdout",
    "corpus/representative-workloads",
    "certification",
)
BAD = {"", "UNSET", "UNASSIGNED", "latest", "*", "x", None}


def _side_errors(label: str, side: object) -> list[str]:
    if not isinstance(side, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    for field in ("engine", "edition", "dialect", "charset", "collation", "timezone"):
        if side.get(field) in BAD:
            errors.append(f"{label} has unset {field}")
    for field in ("versions", "driver_versions"):
        values = side.get(field)
        if not isinstance(values, list) or not values:
            errors.append(f"{label} {field} empty")
            continue
        for value in values:
            if str(value).strip().lower() in {"latest", "*", "x", "unset", ""}:
                errors.append(f"{label} uses floating/unset {field}: {value}")
    return errors


def _load_required(pack: Path, relative_path: str, errors: list[str]) -> dict[str, Any]:
    try:
        return load_json(pack / relative_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return {}


def validate_pack(pack: Path) -> list[str]:
    errors: list[str] = []
    if not pack.is_dir():
        return [f"missing pack dir: {pack}"]
    for relative_path in REQUIRED_DIRS:
        if not (pack / relative_path).is_dir():
            errors.append(f"missing directory: {relative_path}")

    errors.extend(schema_errors(pack))
    manifest = _load_required(pack, "pack.json", errors)
    support = _load_required(pack, "support-matrix.json", errors)
    route = _load_required(pack, "route-matrix.json", errors)
    fingerprint = _load_required(pack, "source-fingerprint/manifest.json", errors)
    ir = _load_required(pack, "canonical-ir/model.json", errors)
    profile = _load_required(pack, "target-profile/profile.json", errors)
    plan = _load_required(pack, "migration/data-migration-plan.json", errors)
    evidence = _load_required(pack, "certification/evidence.json", errors)
    certification = _load_required(pack, "certification/certification.json", errors)

    expected_pack_key = manifest.get("pack_key")
    if expected_pack_key != pack.name:
        errors.append("pack.json pack_key must equal directory name")
    for label, value in (
        ("support matrix", support),
        ("route matrix", route),
        ("fingerprint", fingerprint),
        ("canonical IR", ir),
        ("migration plan", plan),
        ("evidence", evidence),
        ("certification", certification),
    ):
        if value.get("pack_key") != expected_pack_key:
            errors.append(f"{label} pack_key mismatch")

    for owner_field in ("owner", "maintenance_owner", "data_owner"):
        if manifest.get(owner_field) in BAD:
            errors.append(f"{owner_field} is unassigned")
    errors.extend(_side_errors("source", manifest.get("source")))
    errors.extend(_side_errors("target", manifest.get("target")))
    errors.extend(_side_errors("target profile", profile))

    source = canonical_side(manifest.get("source"))
    target = canonical_side(manifest.get("target"))
    exact_tuple = certification.get("exact_tuple")
    if not isinstance(exact_tuple, dict):
        errors.append("certification exact_tuple must be an object")
    else:
        if canonical_side(exact_tuple.get("source")) != source:
            errors.append("certification source exact tuple mismatch")
        if canonical_side(exact_tuple.get("target")) != target:
            errors.append("certification target exact tuple mismatch")
    tuples = route.get("tuples")
    if not isinstance(tuples, list) or len(tuples) != 1:
        errors.append("route matrix must contain exactly one directional tuple")
    else:
        route_tuple = tuples[0]
        if canonical_side(route_tuple.get("source")) != source:
            errors.append("route matrix source exact tuple mismatch")
        if canonical_side(route_tuple.get("target")) != target:
            errors.append("route matrix target exact tuple mismatch")
    if canonical_side(plan.get("source")) != source:
        errors.append("migration plan source exact tuple mismatch")
    if canonical_side(plan.get("target")) != target:
        errors.append("migration plan target exact tuple mismatch")
    if canonical_side(profile) != target:
        errors.append("target profile exact tuple mismatch")

    capability_ids: set[object] = set()
    for capability in support.get("capabilities", []):
        identifier = capability.get("id")
        if identifier in capability_ids:
            errors.append(f"duplicate capability id: {identifier}")
        capability_ids.add(identifier)

    fingerprint_digest = str(fingerprint.get("snapshot_digest", ""))
    if fingerprint_digest.upper() in BAD or not fingerprint_digest.startswith(
        "sha256:"
    ):
        errors.append("fingerprint snapshot digest must be an immutable sha256 digest")
    if ir.get("source_snapshot_digest") != fingerprint_digest:
        errors.append("canonical IR source snapshot digest mismatch")

    evidence_refs = evidence.get("evidence_refs", [])
    certification_refs = certification.get("evidence_refs", [])
    if isinstance(evidence_refs, list):
        errors.extend(
            evidence_ref_errors(
                pack,
                evidence_refs,
                evidence.get("evidence_digests"),
                label="certification/evidence.json",
            )
        )
    if isinstance(certification_refs, list):
        errors.extend(
            evidence_ref_errors(
                pack,
                certification_refs,
                certification.get("evidence_digests"),
                label="certification/certification.json",
            )
        )
    if evidence_refs != certification_refs:
        errors.append("evidence and certification references must match exactly")

    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    args = parser.parse_args()
    pack = Path(args.pack_dir).resolve()
    errors = validate_pack(pack)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: {pack}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
