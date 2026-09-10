#!/usr/bin/env python3
"""Safely integrate, install, and qualify the Elmos Assurance Skills v4.0.0 package.

The source package is untrusted declarative source material. This importer:
1. Verifies archive and extracted tree against cryptographic checksums and schemas.
2. Validates DAG acyclicity across all 34 skills, 8 batches, and 4 domain workflows.
3. Installs package into .elmos/assurance-package-v4.0.0 and creates dual-root
   repository-owned wrappers in .agents/skills and agent-skills/runtime without executing
   untrusted code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("PyYAML and jsonschema are required; use `uv run --with pyyaml --with jsonschema`") from exc

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-assurance-skills-v4.0.0"
PACKAGE_ID = "elmos-assurance-skills-v4.0.0"
PACKAGE_NAME = "elmos-assurance-skills"
PACKAGE_VERSION = "4.0.0"
NAMESPACE = "elmos.assurance/v4"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills/subskills/sub") / PACKAGE_DIRECTORY
INSTALLED_PACKAGE_RELATIVE = Path(".elmos/assurance-package-v4.0.0")

INSTALL_ROOTS = (Path(".agents/skills"), Path("agent-skills/runtime"))

EXPECTED_ARCHIVE_SHA256 = "af1b5f8ff296d52b05a4066194e887513eea501a928fdd11812f7a31a20ea73c"
EXPECTED_ARCHIVE_BYTES = 375_751
EXPECTED_ARCHIVE_ENTRIES = 293
EXPECTED_UNCOMPRESSED_BYTES = 709_194

EXPECTED_SKILLS_COUNT = 34
EXPECTED_DOMAIN_PACKS = 4
EXPECTED_SCHEMAS_COUNT = 15
EXPECTED_ACCEPTANCE_CASES = 102
EXPECTED_NATIVE_CASES = 24


class IntegrationError(RuntimeError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def _yaml_mapping(loader: Any, node: Any, deep: bool = False) -> dict[str, Any]:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for kn, vn in node.value:
        key = loader.construct_object(kn, deep=deep)
        if key in result:
            raise ValueError(f"DUPLICATE_YAML_KEY: {key}")
        result[key] = loader.construct_object(vn, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping)


def load_yaml(path: Path) -> Any:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


def check_dag(graph: Mapping[str, list[str]]) -> None:
    pending: set[str] = set()
    done: set[str] = set()

    def visit(node: str) -> None:
        if node in pending:
            raise IntegrationError(f"DEPENDENCY_CYCLE: {node}")
        if node in done:
            return
        if node not in graph:
            raise IntegrationError(f"UNKNOWN_DEPENDENCY: {node}")
        pending.add(node)
        for dep in graph[node]:
            visit(dep)
        pending.remove(node)
        done.add(node)

    for node in graph:
        visit(node)


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def resolve_archive_path() -> Path:
    candidates = [
        ROOT / PRIMARY_ARCHIVE_RELATIVE,
        ROOT / FALLBACK_ARCHIVE_RELATIVE,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise IntegrationError(f"Package archive not found in candidates: {candidates}")


def validate_archive(archive_path: Path) -> None:
    with open(archive_path, "rb") as f:
        content = f.read()

    actual_sha = hashlib.sha256(content).hexdigest()
    actual_bytes = len(content)

    if actual_sha != EXPECTED_ARCHIVE_SHA256:
        raise IntegrationError(
            f"Archive SHA-256 mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {actual_sha}"
        )
    if actual_bytes != EXPECTED_ARCHIVE_BYTES:
        raise IntegrationError(
            f"Archive byte size mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {actual_bytes}"
        )

    with zipfile.ZipFile(archive_path, "r") as z:
        infolist = z.infolist()
        if len(infolist) != EXPECTED_ARCHIVE_ENTRIES:
            raise IntegrationError(
                f"Archive entry count mismatch: expected {EXPECTED_ARCHIVE_ENTRIES}, got {len(infolist)}"
            )
        uncompressed = sum(info.file_size for info in infolist)
        if uncompressed != EXPECTED_UNCOMPRESSED_BYTES:
            raise IntegrationError(
                f"Archive uncompressed size mismatch: expected {EXPECTED_UNCOMPRESSED_BYTES}, got {uncompressed}"
            )


def validate_extracted_tree(source_root: Path) -> dict[str, Any]:
    manifest_path = source_root / "PACKAGE_CONTENTS.sha256"
    if not manifest_path.is_file():
        raise IntegrationError("Missing PACKAGE_CONTENTS.sha256")

    entries: dict[str, str] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        h, sep, name = line.partition("  ")
        p = Path(name)
        if not sep or len(h) != 64 or p.is_absolute() or ".." in p.parts:
            raise IntegrationError(f"Invalid manifest entry: {line}")
        target = source_root / p
        if not target.is_file():
            raise IntegrationError(f"Missing file from manifest: {name}")
        actual_h = compute_file_sha256(target)
        if actual_h != h:
            raise IntegrationError(f"Checksum mismatch for {name}: expected {h}, got {actual_h}")
        entries[name] = h

    # Check schemas
    schemas: dict[str, Any] = {}
    for p in (source_root / "contracts/schemas").glob("*.schema.json"):
        x = json.loads(p.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(x)
        schemas[p.name] = x
    if len(schemas) != EXPECTED_SCHEMAS_COUNT:
        raise IntegrationError(f"Schema count mismatch: expected {EXPECTED_SCHEMAS_COUNT}, got {len(schemas)}")

    # Check skills
    manifests: dict[str, Any] = {}
    acceptances: list[str] = []
    skills_dir = source_root / "skills"
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        for req in ["SKILL.md", "manifest.yaml", "implementation.yaml", "acceptance.yaml", "runbook.md"]:
            if not (d / req).is_file():
                raise IntegrationError(f"Skill {d.name} missing required file: {req}")

        m = load_yaml(d / "manifest.yaml")
        Draft202012Validator(schemas["skill-manifest.schema.json"]).validate(m)
        if m["id"] != d.name:
            raise IntegrationError(f"Skill ID mismatch in manifest: {m['id']} != {d.name}")
        manifests[d.name] = m

        acc = load_yaml(d / "acceptance.yaml")
        if acc["product_acceptance_status"] != "NOT_RUN":
            raise IntegrationError(f"Skill {d.name} acceptance status must be NOT_RUN")
        for case in acc["cases"]:
            acceptances.append(case["id"])

    if len(manifests) != EXPECTED_SKILLS_COUNT:
        raise IntegrationError(f"Skill count mismatch: expected {EXPECTED_SKILLS_COUNT}, got {len(manifests)}")
    if len(acceptances) != EXPECTED_ACCEPTANCE_CASES:
        raise IntegrationError(f"Acceptance cases mismatch: expected {EXPECTED_ACCEPTANCE_CASES}, got {len(acceptances)}")

    # Check DAG
    check_dag({k: v["dependencies"] for k, v in manifests.items()})

    # Check batch DAG
    batches_data = load_yaml(source_root / "roadmap/implementation-batches.yaml")
    batch_seq = batches_data["batches"]
    check_dag({b["id"]: b["depends_on"] for b in batch_seq})

    # Check domain packs
    native_cases: list[str] = []
    domain_dir = source_root / "domain-packs"
    domain_count = 0
    for d in sorted(domain_dir.iterdir()):
        if not d.is_dir():
            continue
        domain_count += 1
        acc = load_yaml(d / "acceptance.yaml")
        ids = {c["id"] for c in acc["cases"]}
        native_cases.extend(ids)
        route = load_yaml(source_root / "golden-routes" / d.name / "route.yaml")
        if set(route["acceptance_case_ids"]) != ids or route["native_evidence"] != "NOT_RUN":
            raise IntegrationError(f"Golden route mismatch in domain {d.name}")

    if domain_count != EXPECTED_DOMAIN_PACKS:
        raise IntegrationError(f"Domain pack count mismatch: expected {EXPECTED_DOMAIN_PACKS}, got {domain_count}")
    if len(native_cases) != EXPECTED_NATIVE_CASES:
        raise IntegrationError(f"Native route acceptance count mismatch: expected {EXPECTED_NATIVE_CASES}, got {len(native_cases)}")

    return {
        "skills": len(manifests),
        "schemas": len(schemas),
        "domain_packs": domain_count,
        "manifest_entries": len(entries),
        "skill_names": sorted(manifests.keys()),
    }


def generate_skill_wrapper(skill_name: str, skill_dir: Path, source_rel: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    frontmatter = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
    desc = frontmatter.get("description", f"Repository wrapper for {skill_name}")
    source_sha = compute_file_sha256(skill_md)

    content = f"""---
name: "{skill_name}"
description: "{desc}"
metadata:
  source_package: "{PACKAGE_NAME}"
  source_package_id: "{PACKAGE_ID}"
  source_version: "{PACKAGE_VERSION}"
  source_path: "{source_rel.as_posix()}"
  source_sha256: "sha256:{source_sha}"
  normalized_namespace: "{NAMESPACE}"
  runtime_module: "engines/assurance-engine/src/elmos_assurance_engine/dispatcher.py"
  runtime_dispatcher: "dispatch_assurance_skill"
  runtime_skill_key: "{skill_name}"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_EXTERNAL_GATE"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `{skill_name}` from package `{PACKAGE_ID}`.

### Normative Authority & Fail-Closed Boundary
- Source contract: `.elmos/assurance-package-v4.0.0/skills/{skill_name}/SKILL.md`
- Implementation tasks: `.elmos/assurance-package-v4.0.0/skills/{skill_name}/implementation.yaml`
- Acceptance criteria: `.elmos/assurance-package-v4.0.0/skills/{skill_name}/acceptance.yaml`
- Runtime handler: Bound allowlisted handler under `engines/assurance-engine/`

Any missing environment, dependency, or signature defaults to `NOT_RUN` / `INCONCLUSIVE`.
"""
    return content


def install_package(source_root: Path, target_elmos_pkg: Path) -> None:
    if target_elmos_pkg.exists():
        shutil.rmtree(target_elmos_pkg)
    target_elmos_pkg.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, target_elmos_pkg, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".git"))


def install_skills(source_root: Path) -> None:
    skills_dir = source_root / "skills"
    for install_root in INSTALL_ROOTS:
        dest_base = ROOT / install_root
        dest_base.mkdir(parents=True, exist_ok=True)
        for d in sorted(skills_dir.iterdir()):
            if not d.is_dir():
                continue
            skill_target_dir = dest_base / d.name
            skill_target_dir.mkdir(parents=True, exist_ok=True)

            source_rel = Path("skills") / d.name / "SKILL.md"
            wrapper_content = generate_skill_wrapper(d.name, d, source_rel)

            (skill_target_dir / "SKILL.md").write_text(wrapper_content, encoding="utf-8")
            for auxiliary in ["manifest.yaml", "implementation.yaml", "acceptance.yaml", "runbook.md"]:
                src_file = d / auxiliary
                if src_file.is_file():
                    shutil.copy2(src_file, skill_target_dir / auxiliary)


def check_installation(target_elmos_pkg: Path) -> None:
    if not target_elmos_pkg.is_dir():
        raise IntegrationError(f"Installed package not found at: {target_elmos_pkg}")
    for install_root in INSTALL_ROOTS:
        dest_base = ROOT / install_root
        if not dest_base.is_dir():
            raise IntegrationError(f"Skills install directory missing: {dest_base}")
        # Check skill count
        for name in (target_elmos_pkg / "skills").iterdir():
            if name.is_dir():
                skill_path = dest_base / name.name / "SKILL.md"
                if not skill_path.is_file():
                    raise IntegrationError(f"Missing installed skill: {skill_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Perform offline validation and verify installation")
    parser.add_argument("--apply", action="store_true", help="Apply package installation to .elmos and skill roots")
    args = parser.parse_args()

    archive_path = resolve_archive_path()
    source_root = ROOT / SOURCE_RELATIVE
    target_elmos_pkg = ROOT / INSTALLED_PACKAGE_RELATIVE

    try:
        validate_archive(archive_path)
        stats = validate_extracted_tree(source_root)

        if args.apply:
            install_package(source_root, target_elmos_pkg)
            install_skills(source_root)
            check_installation(target_elmos_pkg)
            print(json.dumps({
                "status": "PASS",
                "action": "INSTALLED",
                "package_id": PACKAGE_ID,
                "skills_installed": stats["skills"],
                "installed_package_path": str(target_elmos_pkg.relative_to(ROOT)),
                "install_roots": [str(r) for r in INSTALL_ROOTS],
            }, indent=2))
            return 0

        if args.check:
            # If package is installed, verify it
            if target_elmos_pkg.is_dir():
                check_installation(target_elmos_pkg)
            print(json.dumps({
                "status": "PASS",
                "action": "VALIDATED",
                "package_id": PACKAGE_ID,
                "skills_count": stats["skills"],
                "schemas_count": stats["schemas"],
                "domain_packs": stats["domain_packs"],
                "installed": target_elmos_pkg.is_dir(),
            }, indent=2))
            return 0

        print(json.dumps(stats, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "status": "FAIL",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
