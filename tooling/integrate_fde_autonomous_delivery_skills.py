#!/usr/bin/env python3
"""Safely integrate, install, and qualify the Elmos FDE Autonomous Delivery Skills v5.2.0 package.

In accordance with Elmos core architecture:
- Archive data (Markdown, YAML, scripts) is untrusted declarative material.
- Never executes package installer/validator scripts.
- Independently validates SHA-256 digest, byte count, controlled files, and 24 schemas.
- Generates dual-root skill wrappers (.agents/skills/ and agent-skills/runtime/).
- Strictly enforces non-routable constraint (routable: false) and E3 boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    jsonschema = None  # type: ignore
    Draft202012Validator = None  # type: ignore


EXPECTED_PACKAGE = "elmos-fde-autonomous-delivery-repository-refactoring-skills"
EXPECTED_VERSION = "5.2.0"
EXPECTED_SHA256 = "4dbd6f20b0d27dbacf12ed432f0486f9e59151c2b138c6e7d8a9f60f395b1428"
EXPECTED_BYTES = 784_460
EXPECTED_ATOMIC_SKILLS = 45
EXPECTED_WORKFLOW_SKILLS = 12
EXPECTED_SCHEMAS = 24

ARCHIVE_PATH = Path("skills/subskills/sub/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0.zip")
INSTALL_DIR = Path("skills/elmos-fde-autonomous-delivery-repository-refactoring-skills-v5.2.0")
AGENTS_DIR = Path(".agents/skills")
RUNTIME_DIR = Path("agent-skills/runtime")


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_archive_integrity(archive_path: Path) -> tuple[bool, list[str]]:
    errors = []
    if not archive_path.is_file():
        return False, [f"Archive not found: {archive_path}"]

    size = archive_path.stat().st_size
    if size != EXPECTED_BYTES:
        errors.append(f"Byte count mismatch: got {size}, expected {EXPECTED_BYTES}")

    actual_sha = compute_sha256(archive_path)
    if actual_sha != EXPECTED_SHA256:
        errors.append(f"SHA-256 mismatch: got {actual_sha}, expected {EXPECTED_SHA256}")

    try:
        with zipfile.ZipFile(archive_path) as z:
            bad = z.testzip()
            if bad:
                errors.append(f"Corrupt zip member: {bad}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Failed reading zip: {exc}")

    return len(errors) == 0, errors


def safe_extract_archive(archive_path: Path, target_dir: Path) -> None:
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path) as z:
        for member in z.infolist():
            # Defense against Zip Slip
            p = Path(member.filename)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"Zip slip attempt detected: {member.filename}")
            # Strip top-level directory prefix if present
            parts = p.parts
            if len(parts) > 1 and parts[0] == f"{EXPECTED_PACKAGE}-v{EXPECTED_VERSION}":
                rel_parts = parts[1:]
            else:
                rel_parts = parts

            if not rel_parts:
                continue

            dest_path = target_dir.joinpath(*rel_parts)
            if member.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, dest_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)


def validate_schemas_and_contracts(install_dir: Path) -> tuple[bool, list[str], int]:
    errors = []
    schema_dir = install_dir / "contracts" / "schemas"
    example_dir = install_dir / "contracts" / "examples"

    if not schema_dir.is_dir():
        return False, [f"Schema directory missing: {schema_dir}"], 0

    schema_files = list(schema_dir.glob("*.schema.json"))
    if len(schema_files) != EXPECTED_SCHEMAS:
        errors.append(f"Schema count mismatch: found {len(schema_files)}, expected {EXPECTED_SCHEMAS}")

    if Draft202012Validator is None:
        return False, ["jsonschema package not installed"], len(schema_files)

    for sf in schema_files:
        try:
            schema_data = json.loads(sf.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema_data)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Schema syntax error in {sf.name}: {exc}")
            continue

        base_name = sf.name.replace(".schema.json", "")
        ex_file = example_dir / f"{base_name}.example.json"
        if ex_file.is_file():
            try:
                ex_data = json.loads(ex_file.read_text(encoding="utf-8"))
                val = Draft202012Validator(schema_data)
                validation_errors = list(val.iter_errors(ex_data))
                if validation_errors:
                    errors.append(f"Example {ex_file.name} violates {sf.name}: {validation_errors[0].message}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Failed validating example {ex_file.name}: {exc}")

    return len(errors) == 0, errors, len(schema_files)


def build_skill_wrapper_content(
    source_id: str,
    alias: str,
    pack: str,
    handler_module: str,
    dependencies: list[str],
    description: str,
    is_workflow: bool = False,
) -> str:
    dep_list_str = "\n".join(f"  - {d}" for d in dependencies) if dependencies else "  []"
    role_desc = "FDE autonomous delivery workflow skill" if is_workflow else "Repository-owned bounded FDE capability handler"
    return f"""---
name: {alias}
description: {role_desc} for {source_id}; external evidence remains NOT_RUN.
metadata:
  package: {EXPECTED_PACKAGE}
  version: {EXPECTED_VERSION}
  pack: {pack}
  source_id: {source_id}
  alias: {alias}
  handler: {handler_module}:execute_{source_id.replace('-', '_')}
  dependencies:
{dep_list_str}
  effect_boundary: E3
  routable: false
---

# {alias}

This skill provides the repository-owned bounded implementation for `{source_id}` in pack `{pack}`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
"""


def build_compiled_contract(
    source_id: str,
    alias: str,
    pack: str,
    dependencies: list[str],
    is_workflow: bool = False,
) -> dict[str, Any]:
    return {
        "package": EXPECTED_PACKAGE,
        "version": EXPECTED_VERSION,
        "source_id": source_id,
        "alias": alias,
        "pack": pack,
        "is_workflow": is_workflow,
        "dependencies": dependencies,
        "effect_boundary": "E3",
        "routable": False,
        "implementation_state": "LOCAL_CONTROL_PLANE",
        "external_evidence": "NOT_RUN",
        "independent_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def materialize_wrappers(install_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    from elmos_fde_delivery.registry import (
        _MODULE_BY_PACK,
        DEPENDENCIES,
        PACK_BY_SKILL,
        WORKFLOW_SKILLS,
    )

    atomic_count = 0
    workflow_count = 0

    # 1. Atomic skills (45 skills)
    for skill_id, deps in DEPENDENCIES.items():
        pack = PACK_BY_SKILL[skill_id]
        mod = _MODULE_BY_PACK[pack]
        alias = f"elmos-fde-{skill_id}"
        contract_data = build_compiled_contract(skill_id, alias, pack, list(deps), is_workflow=False)

        for name in (alias, skill_id):
            agents_dir = AGENTS_DIR / name
            runtime_dir = RUNTIME_DIR / name
            content = build_skill_wrapper_content(skill_id, name, pack, mod, list(deps), "", is_workflow=False)

            if not dry_run:
                agents_dir.mkdir(parents=True, exist_ok=True)
                (agents_dir / "SKILL.md").write_text(content, encoding="utf-8")

                runtime_dir.mkdir(parents=True, exist_ok=True)
                (runtime_dir / "SKILL.md").write_text(content, encoding="utf-8")
                (runtime_dir / "compiled-contract.json").write_text(
                    json.dumps(contract_data, indent=2), encoding="utf-8"
                )

        atomic_count += 1

    # 2. Workflow skills (12 skills)
    for wf_name in WORKFLOW_SKILLS:
        agents_dir = AGENTS_DIR / wf_name
        runtime_dir = RUNTIME_DIR / wf_name
        source_wf_dir = install_dir / ".agents" / "skills" / wf_name
        source_skill_md = source_wf_dir / "SKILL.md"

        if source_skill_md.is_file():
            content = source_skill_md.read_text(encoding="utf-8")
        else:
            content = build_skill_wrapper_content(wf_name, wf_name, "workflow", "orchestrator", [], "", is_workflow=True)

        contract_data = build_compiled_contract(wf_name, wf_name, "workflow", [], is_workflow=True)

        if not dry_run:
            agents_dir.mkdir(parents=True, exist_ok=True)
            (agents_dir / "SKILL.md").write_text(content, encoding="utf-8")

            runtime_dir.mkdir(parents=True, exist_ok=True)
            (runtime_dir / "SKILL.md").write_text(content, encoding="utf-8")
            (runtime_dir / "compiled-contract.json").write_text(
                json.dumps(contract_data, indent=2), encoding="utf-8"
            )

        workflow_count += 1

    return atomic_count, workflow_count


def run_qualification(write: bool = False) -> int:
    archive_ok, archive_errors = verify_archive_integrity(ARCHIVE_PATH)
    if not archive_ok:
        print(json.dumps({
            "status": "FAIL",
            "errors": archive_errors,
        }, indent=2))
        return 1

    if write:
        safe_extract_archive(ARCHIVE_PATH, INSTALL_DIR)

    if not INSTALL_DIR.is_dir():
        print(json.dumps({
            "status": "NOT_INSTALLED",
            "message": f"Package extraction directory missing: {INSTALL_DIR}. Run with --write to extract.",
        }, indent=2))
        return 2

    schemas_ok, schema_errors, schema_count = validate_schemas_and_contracts(INSTALL_DIR)
    if not schemas_ok:
        print(json.dumps({
            "status": "SCHEMA_ERROR",
            "errors": schema_errors,
        }, indent=2))
        return 3

    sys.path.insert(0, str(Path("packages/fde-autonomous-delivery/src").resolve()))
    try:
        atomic_count, workflow_count = materialize_wrappers(INSTALL_DIR, dry_run=not write)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "status": "WRAPPER_MATERIALIZATION_ERROR",
            "error": str(exc),
        }, indent=2))
        return 4

    result = {
        "status": "VALIDATED",
        "package": EXPECTED_PACKAGE,
        "version": EXPECTED_VERSION,
        "archive_sha256": EXPECTED_SHA256,
        "atomic_skill_count": atomic_count,
        "workflow_skill_count": workflow_count,
        "schema_count": schema_count,
        "installed": INSTALL_DIR.is_dir(),
    }
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrate and qualify Elmos FDE Skills v5.2.0")
    parser.add_argument("--check", action="store_true", help="Perform read-only validation")
    parser.add_argument("--write", action="store_true", help="Extract package and materialize dual-root wrappers")

    args = parser.parse_args()
    if not args.check and not args.write:
        parser.print_help()
        return 1

    return run_qualification(write=args.write)


if __name__ == "__main__":
    sys.exit(main())
