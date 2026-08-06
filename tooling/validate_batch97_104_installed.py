#!/usr/bin/env python3
"""Validate the tracked Batch 97-104 Runtime Skill distribution.

The canonical import package is intentionally not required for a normal source
checkout.  Its byte identities are retained in the installed manifest, so this
validator proves that every tracked Runtime Skill and Codex interface still
matches that immutable inventory.  It does not validate the absent package and
never upgrades external evidence or certification state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("docs/batch97-104/installed-manifest.json")
PACKAGE = "elmos-codex-skills-batch97-104-complete"
EXPECTED_IDS = [
    f"B{batch}-S{sequence:02d}"
    for batch in range(97, 105)
    for sequence in range(1, 17)
]
NAME_PATTERN = re.compile(r"b(?P<batch>9[7-9]|10[0-4])-[a-z0-9-]+")


class ValidationError(ValueError):
    """Raised when the installed distribution does not match its manifest."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read installed manifest: {path}: {exc}") from exc
    _require(isinstance(value, dict), "installed manifest must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _resolve_file(root: Path, relative: str, label: str) -> Path:
    _require(isinstance(relative, str) and relative != "", f"{label} path is invalid")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValidationError(f"{label} path escapes repository root: {relative}") from exc
    _require(candidate.is_file(), f"{label} file is missing: {relative}")
    _require(not candidate.is_symlink(), f"{label} file must not be a symlink: {relative}")
    return candidate


def validate(root: Path = ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    root = root.resolve()
    manifest_file = manifest_path if manifest_path.is_absolute() else root / manifest_path
    manifest = _load_json(manifest_file)

    _require(manifest.get("package") == PACKAGE, "installed package identity is invalid")
    _require(manifest.get("source_id_namespace") == "batch-local-product-closure", "source namespace is invalid")
    _require(manifest.get("source_id_range") == ["B97-S01", "B104-S16"], "source id range is invalid")
    _require(manifest.get("global_id_assignment") == "UNASSIGNED", "global ids must remain unassigned")
    _require(manifest.get("skill_count") == 128, "installed manifest must declare 128 Skills")
    _require(manifest.get("external_evidence_status") == "NOT_RUN", "external evidence must remain NOT_RUN")

    entries = manifest.get("skills")
    _require(isinstance(entries, list) and len(entries) == 128, "installed manifest must contain 128 Skill entries")
    _require([entry.get("source_id") for entry in entries] == EXPECTED_IDS, "Skill ids must be exactly B97-S01 through B104-S16")

    names: set[str] = set()
    declared_files: set[Path] = set()
    for expected_id, entry in zip(EXPECTED_IDS, entries, strict=True):
        _require(isinstance(entry, dict), f"Skill entry is invalid: {expected_id}")
        batch = int(expected_id[1:expected_id.index("-")])
        name = entry.get("installed_name")
        _require(isinstance(name, str) and NAME_PATTERN.fullmatch(name) is not None, f"installed name is invalid: {expected_id}")
        _require(len(name) <= 64 and name not in names, f"installed name is duplicated or too long: {name}")
        names.add(name)

        _require(entry.get("source_key") == f"PRODUCT-CLOSURE-{expected_id}", f"source key mismatch: {expected_id}")
        _require(entry.get("global_id") is None, f"global id must be null: {expected_id}")
        _require(entry.get("batch") == batch, f"Batch mismatch: {expected_id}")
        _require(entry.get("source_name") == name, f"source name mismatch: {expected_id}")

        expected_source = f"{PACKAGE}/agent-skills/runtime/{name}/SKILL.md"
        expected_installed = f"agent-skills/runtime/{name}/SKILL.md"
        expected_interface = f"agent-skills/runtime/{name}/agents/openai.yaml"
        _require(entry.get("source_path") == expected_source, f"source path mismatch: {expected_id}")
        _require(entry.get("installed_path") == expected_installed, f"installed path mismatch: {expected_id}")
        _require(entry.get("interface_path") == expected_interface, f"interface path mismatch: {expected_id}")

        skill = _resolve_file(root, expected_installed, "installed Skill")
        interface = _resolve_file(root, expected_interface, "Codex interface")
        declared_files.update({skill, interface})
        installed_digest = _sha256(skill)
        _require(entry.get("installed_sha256") == installed_digest, f"installed Skill digest mismatch: {name}")
        _require(entry.get("source_sha256") == installed_digest, f"source/installed digest binding mismatch: {name}")
        _require(entry.get("interface_sha256") == _sha256(interface), f"Codex interface digest mismatch: {name}")
        _require(f"${name}" in interface.read_text(encoding="utf-8"), f"Codex interface does not invoke exact alias: {name}")

    actual_files: set[Path] = set()
    runtime = root / "agent-skills" / "runtime"
    for batch in range(97, 105):
        for skill in runtime.glob(f"b{batch}-*/SKILL.md"):
            actual_files.add(skill.resolve())
            interface = skill.parent / "agents" / "openai.yaml"
            _require(interface.is_file(), f"Codex interface is missing: {skill.parent.name}")
            actual_files.add(interface.resolve())
    _require(actual_files == declared_files, "tracked Batch 97-104 Runtime Skill inventory differs from installed manifest")

    source_present = (root / PACKAGE / "manifest.json").is_file()
    return {
        "decision": "INSTALLED_ARTIFACTS_VERIFIED",
        "skills": len(entries),
        "interfaces": len(entries),
        "source_package_present": source_present,
        "source_package_validated": False,
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.manifest)
    except ValidationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
