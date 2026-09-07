#!/usr/bin/env python3
"""Validate tracked Product Closure and Convergence installed artifacts.

The two original import bundles are not part of an ordinary repository
checkout.  Their normalized Skill and asset byte identities remain pinned in
the installed manifest.  This gate validates those tracked outputs without
claiming that an absent source bundle, external evidence, or certification was
validated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("docs/product-closure-convergence/installed-manifest.json")
BATCH56_PACKAGE = "elmos-codex-skills-batch56a-product-closure"
CONVERGENCE_PACKAGE = "elmos-product-convergence-reference-skills"
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
NAME_PATTERN = re.compile(r"[a-z0-9-]{1,64}")


class ValidationError(ValueError):
    """Raised when a tracked installed artifact differs from the manifest."""


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


def _safe_path(root: Path, relative: str, label: str, *, required: bool = True) -> Path:
    _require(isinstance(relative, str) and relative != "", f"{label} path is invalid")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValidationError(f"{label} path escapes repository root: {relative}") from exc
    if required:
        _require(candidate.is_file(), f"{label} is missing: {relative}")
        _require(not candidate.is_symlink(), f"{label} must not be a symlink: {relative}")
    return candidate


def _validate_family(
    root: Path,
    family: dict[str, Any],
    *,
    package: str,
    expected_ids: list[str],
    installed_prefix: str,
    maturity: str | None = None,
) -> tuple[set[str], int]:
    _require(family.get("package") == package, f"package identity mismatch: {package}")
    _require(family.get("skill_count") == len(expected_ids), f"Skill count mismatch: {package}")
    _require(family.get("external_evidence") == "NOT_RUN", f"external evidence must remain NOT_RUN: {package}")
    _require(family.get("maximum_local_decision") == "READY_FOR_EXTERNAL_GATE", f"local decision ceiling mismatch: {package}")
    entries = family.get("skills")
    _require(isinstance(entries, list) and len(entries) == len(expected_ids), f"Skill inventory mismatch: {package}")
    _require([entry.get("id") for entry in entries] == expected_ids, f"Skill ids are not exact: {package}")

    names: set[str] = set()
    source_files_present = 0
    for entry in entries:
        name = entry.get("name")
        _require(isinstance(name, str) and NAME_PATTERN.fullmatch(name) is not None, f"invalid Skill name: {name}")
        _require(name not in names, f"duplicate Skill name: {name}")
        names.add(name)
        if maturity is not None:
            _require(entry.get("maturity") == maturity, f"maturity mismatch: {name}")

        installed_relative = f"{installed_prefix}/{name}/SKILL.md"
        _require(entry.get("installed_path") == installed_relative, f"installed path mismatch: {name}")
        installed = _safe_path(root, installed_relative, "installed Skill")
        interface = _safe_path(root, f"{installed_prefix}/{name}/agents/openai.yaml", "Codex interface")
        _require(DIGEST_PATTERN.fullmatch(str(entry.get("source_sha256"))) is not None, f"source digest is invalid: {name}")
        _require(entry.get("installed_sha256") == _sha256(installed), f"installed Skill digest mismatch: {name}")
        _require(entry.get("interface_sha256") == _sha256(interface), f"Codex interface digest mismatch: {name}")
        _require(f"${name}" in interface.read_text(encoding="utf-8"), f"Codex interface alias mismatch: {name}")

        source_relative = entry.get("source_path")
        _require(isinstance(source_relative, str) and source_relative.startswith(package + "/"), f"source path mismatch: {name}")
        source = _safe_path(root, source_relative, "source Skill", required=False)
        if source.is_file():
            _require(entry.get("source_sha256") == _sha256(source), f"source Skill digest mismatch: {name}")
            source_files_present += 1
    return names, source_files_present


def validate(root: Path = ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    root = root.resolve()
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    manifest = _load_json(path)
    _require(manifest.get("schema_version") == "1.0", "installed manifest Schema version is invalid")
    namespace = manifest.get("namespace_policy")
    _require(isinstance(namespace, dict) and set(namespace) == {"batch56a", "convergence"}, "namespace policy is invalid")

    batch_names, batch_sources = _validate_family(
        root,
        manifest.get("batch56a", {}),
        package=BATCH56_PACKAGE,
        expected_ids=[f"CLO56A{number:03d}" for number in range(1, 17)],
        installed_prefix="agent-skills/runtime",
        maturity="reviewed-design",
    )
    convergence_names, convergence_sources = _validate_family(
        root,
        manifest.get("convergence", {}),
        package=CONVERGENCE_PACKAGE,
        expected_ids=[f"CONV-{number:03d}" for number in range(1, 33)],
        installed_prefix=".agents/skills",
    )

    normalized_batch_names = {
        path.parent.name
        for path in (root / "agent-skills/runtime").glob("*/SKILL.md")
        if f"source_package: {BATCH56_PACKAGE}" in path.read_text(encoding="utf-8")
    }
    _require(normalized_batch_names == batch_names, "Batch 56A normalized Runtime Skill inventory differs from manifest")
    _require(all(name.startswith("conv-") for name in convergence_names), "convergence aliases must use conv-* namespace")

    assets = manifest.get("integrated_assets")
    _require(isinstance(assets, list) and len(assets) == 69, "integrated asset inventory must contain exactly 69 records")
    installed_paths: set[str] = set()
    source_paths: set[str] = set()
    present_asset_sources = 0
    for entry in assets:
        _require(isinstance(entry, dict), "integrated asset record is invalid")
        installed_relative = entry.get("installed_path")
        source_relative = entry.get("source_path")
        _require(isinstance(installed_relative, str) and installed_relative not in installed_paths, "integrated installed path is invalid or duplicated")
        _require(isinstance(source_relative, str) and source_relative not in source_paths, "integrated source path is invalid or duplicated")
        _require(source_relative.startswith((BATCH56_PACKAGE + "/", CONVERGENCE_PACKAGE + "/")), "integrated source package is invalid")
        installed_paths.add(installed_relative)
        source_paths.add(source_relative)
        installed = _safe_path(root, installed_relative, "integrated artifact")
        digest = _sha256(installed)
        _require(entry.get("sha256") == digest, f"integrated artifact digest mismatch: {installed_relative}")
        source = _safe_path(root, source_relative, "integrated source", required=False)
        if source.is_file():
            _require(_sha256(source) == digest, f"integrated source/target mismatch: {source_relative}")
            present_asset_sources += 1

    return {
        "decision": "INSTALLED_ARTIFACTS_VERIFIED",
        "batch56a_skills": len(batch_names),
        "convergence_skills": len(convergence_names),
        "integrated_assets": len(assets),
        "source_skill_files_present": batch_sources + convergence_sources,
        "source_asset_files_present": present_asset_sources,
        "source_packages_validated": False,
        "external_evidence": "NOT_RUN",
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
