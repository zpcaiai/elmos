#!/usr/bin/env python3
"""Safely integrate and independently qualify the Elmos Knowledge-Skill-Model Foundry v2.0.0 package.

The source archive is untrusted declarative source material. This importer
checks archive identity, path safety, internal checksums, exact Skill counts,
schemas, policies, pipelines, SQL migrations, and DAG acyclicity
without executing archive scripts or workflows.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("PyYAML and jsonschema are required; use `make knowledge-skill-model-foundry-skills`") from exc

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-knowledge-skill-model-foundry-v2.0.0"
PACKAGE_ID = "elmos-knowledge-skill-model-foundry-v2.0.0"
PACKAGE_NAME = "elmos-knowledge-skill-model-foundry"
PACKAGE_VERSION = "2.0.0"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/knowledge-skill-model-foundry")
ENGINE_RELATIVE = Path("engines/knowledge-skill-model-foundry-engine")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
CLAUDE_SKILLS_RELATIVE = Path(".claude/skills")

EXPECTED_ARCHIVE_SHA256 = "afe529a29d99945f472cacebd479c10ebb802b3c3061c83dfe58659ea8330685"
EXPECTED_ARCHIVE_BYTES = 3_159_877
EXPECTED_FILE_COUNT = 2_353

EXPECTED_COUNTS = {
    "atomicSkills": 458,
    "metaSkills": 17,
    "packs": 17,
    "schemas": 5,
    "policies": 3,
    "pipelines": 4,
    "tables": 25,
}

ATOMIC_SKILL_FILES = {
    "SKILL.md",
    "skill.yaml",
    "evals/contract.yaml",
    "policies/execution.yaml",
    "references/implementation-notes.md",
}

META_SKILL_FILES = {
    "SKILL.md",
    "evals/activation.json",
}


class IntegrationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise IntegrationError(message)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")


def load_yaml(data: bytes, label: str) -> Any:
    try:
        return yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        fail(f"{label}: invalid YAML: {exc}")


def resolve_archive() -> Path:
    p1 = ROOT / PRIMARY_ARCHIVE_RELATIVE
    if p1.is_file():
        return p1
    p2 = ROOT / FALLBACK_ARCHIVE_RELATIVE
    if p2.is_file():
        return p2
    fail(f"Archive missing at {PRIMARY_ARCHIVE_RELATIVE} and {FALLBACK_ARCHIVE_RELATIVE}")


def verify_archive(path: Path) -> str:
    data = path.read_bytes()
    if len(data) != EXPECTED_ARCHIVE_BYTES:
        fail(f"archive byte count mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {len(data)}")
    digest = digest_bytes(data)
    if digest != EXPECTED_ARCHIVE_SHA256:
        fail(f"archive digest mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {digest}")
    return digest


def verify_controlled_files(source_dir: Path) -> dict[str, str]:
    cf_path = source_dir / "SHA256SUMS"
    if not cf_path.is_file():
        fail("missing SHA256SUMS in source")
    rows = cf_path.read_text(encoding="utf-8").splitlines()
    checked: dict[str, str] = {}
    for line in rows:
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            fail(f"malformed checksum line: {line}")
        digest, rel = parts
        target = source_dir / rel
        if not target.is_file():
            fail(f"missing controlled file: {rel}")
        actual = digest_bytes(target.read_bytes())
        if actual != digest:
            fail(f"checksum mismatch for {rel}: expected {digest}, got {actual}")
        checked[rel] = digest
    return checked


def check_dag(nodes: set[str], edges: dict[str, list[str]], label: str) -> None:
    indegree = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, deps in edges.items():
        for dep in deps:
            if dep in nodes:
                indegree[node] += 1
                outgoing[dep].append(node)
    queue = deque(sorted(node for node, deg in indegree.items() if deg == 0))
    visited: list[str] = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for succ in sorted(outgoing[node]):
            indegree[succ] -= 1
            if indegree[succ] == 0:
                queue.append(succ)
    if len(visited) != len(nodes):
        cycle_nodes = sorted(node for node, deg in indegree.items() if deg > 0)
        fail(f"{label}: dependency cycle detected among {cycle_nodes}")


def validate_extracted_source(source_dir: Path) -> dict[str, Any]:
    manifest = yaml.safe_load((source_dir / "manifest.yaml").read_text(encoding="utf-8"))
    metrics: dict[str, Any] = {}

    catalog_data = yaml.safe_load((source_dir / "registry/skill-catalog.yaml").read_text(encoding="utf-8"))
    atomic_skills_list = catalog_data["spec"]["skills"]
    metrics["atomicSkills"] = len(atomic_skills_list)
    if len(atomic_skills_list) != EXPECTED_COUNTS["atomicSkills"]:
        fail(f"atomic skills count mismatch: expected {EXPECTED_COUNTS['atomicSkills']}, got {len(atomic_skills_list)}")

    # Check 17 packs
    packs_dir = source_dir / "skills/atomic"
    pack_dirs = sorted(p for p in packs_dir.iterdir() if p.is_dir())
    metrics["packs"] = len(pack_dirs)
    if len(pack_dirs) != EXPECTED_COUNTS["packs"]:
        fail(f"packs count mismatch: expected {EXPECTED_COUNTS['packs']}, got {len(pack_dirs)}")

    # Check 17 meta skills
    meta_dir = source_dir / "skills/meta"
    meta_dirs = sorted(p for p in meta_dir.iterdir() if p.is_dir())
    metrics["metaSkills"] = len(meta_dirs)
    if len(meta_dirs) != EXPECTED_COUNTS["metaSkills"]:
        fail(f"meta skills count mismatch: expected {EXPECTED_COUNTS['metaSkills']}, got {len(meta_dirs)}")

    for m in meta_dirs:
        files = {p.name for p in m.iterdir() if p.is_file()}
        evals_files = {f"evals/{p.name}" for p in (m / "evals").iterdir() if p.is_file()} if (m / "evals").is_dir() else set()
        if (files | evals_files) != META_SKILL_FILES:
            fail(f"meta skill {m.name}: file inventory mismatch: got {files | evals_files}")

    # Check atomic skills
    all_atomic_ids: set[str] = set()
    dag_edges: dict[str, list[str]] = {}
    for pack_dir in pack_dirs:
        for skill_dir in sorted(p for p in pack_dir.iterdir() if p.is_dir()):
            sid = skill_dir.name
            all_atomic_ids.add(sid)
            files = {p.relative_to(skill_dir).as_posix() for p in skill_dir.rglob("*") if p.is_file()}
            if files != ATOMIC_SKILL_FILES:
                fail(f"atomic skill {pack_dir.name}/{sid}: file inventory mismatch: {files}")

            spec = yaml.safe_load((skill_dir / "skill.yaml").read_text(encoding="utf-8"))["spec"]
            deps = spec.get("dependencies", [])
            dag_edges[sid] = deps

    check_dag(all_atomic_ids, dag_edges, "Foundry Skills DAG")

    # Check schemas
    schemas_dir = source_dir / "schemas"
    schemas = sorted(p for p in schemas_dir.glob("*.json"))
    metrics["schemas"] = len(schemas)
    if len(schemas) != EXPECTED_COUNTS["schemas"]:
        fail(f"schemas count mismatch: expected {EXPECTED_COUNTS['schemas']}, got {len(schemas)}")

    # Check policies
    policies_dir = source_dir / "policies"
    policies = sorted(p for p in policies_dir.glob("*.rego"))
    metrics["policies"] = len(policies)
    if len(policies) != EXPECTED_COUNTS["policies"]:
        fail(f"policies count mismatch: expected {EXPECTED_COUNTS['policies']}, got {len(policies)}")

    # Check pipelines
    pipelines_dir = source_dir / "pipelines"
    pipelines = sorted(p for p in pipelines_dir.glob("*.yaml"))
    metrics["pipelines"] = len(pipelines)
    if len(pipelines) != EXPECTED_COUNTS["pipelines"]:
        fail(f"pipelines count mismatch: expected {EXPECTED_COUNTS['pipelines']}, got {len(pipelines)}")

    # Check database schema
    sql = (source_dir / "database/postgresql-schema.sql").read_text(encoding="utf-8")
    tables = [l for l in sql.splitlines() if l.startswith("CREATE TABLE")]
    metrics["tables"] = len(tables)
    if len(tables) != EXPECTED_COUNTS["tables"]:
        fail(f"tables count mismatch: expected {EXPECTED_COUNTS['tables']}, got {len(tables)}")

    return metrics


def extract_archive_safely(archive_path: Path, target_dir: Path) -> None:
    import zipfile
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            target_path = target_dir / member.filename
            resolved = target_path.resolve()
            if not resolved.is_relative_to(target_dir.resolve()):
                fail(f"Zip extraction path traversal rejected: {member.filename}")
            if member.is_dir():
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_bytes(zf.read(member.filename))


def install_dual_root_skills(source_dir: Path) -> int:
    source_root = source_dir / PACKAGE_DIRECTORY if (source_dir / PACKAGE_DIRECTORY).is_dir() else source_dir
    meta_dir = source_root / "skills/meta"
    atomic_dir = source_root / "skills/atomic"
    
    workspace_skills_root = ROOT / WORKSPACE_SKILLS_RELATIVE
    runtime_skills_root = ROOT / RUNTIME_SKILLS_RELATIVE
    workspace_skills_root.mkdir(parents=True, exist_ok=True)
    runtime_skills_root.mkdir(parents=True, exist_ok=True)
    
    installed_count = 0
    # 1. Install 17 Meta Skills
    for meta_subdir in sorted(meta_dir.iterdir()):
        if not meta_subdir.is_dir():
            continue
        skill_name = f"elmos-{meta_subdir.name}"
        for root_dest in (workspace_skills_root, runtime_skills_root):
            dest = root_dest / skill_name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(meta_subdir, dest)
        installed_count += 1
        
    # 2. Install Atomic Skills
    for pack_subdir in sorted(atomic_dir.iterdir()):
        if not pack_subdir.is_dir():
            continue
        for atomic_subdir in sorted(pack_subdir.iterdir()):
            if not atomic_subdir.is_dir():
                continue
            skill_name = f"elmos-{atomic_subdir.name}" if not atomic_subdir.name.startswith("elmos-") else atomic_subdir.name
            for root_dest in (workspace_skills_root, runtime_skills_root):
                dest = root_dest / skill_name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(atomic_subdir, dest)
            installed_count += 1

    return installed_count


def generate_local_qualification(archive_digest: str, metrics: dict[str, Any]) -> dict[str, Any]:
    qualification_dir = ROOT / ENGINE_RELATIVE / "qualification"
    qualification_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = qualification_dir / "local-qualification.json"

    receipt = {
        "schema_version": "elmos.knowledge-skill-model-foundry.qualification.v1",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "archive_sha256": archive_digest,
        "qualification_state": "QUALIFIED_SELF_ATTESTED",
        "evidence_status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects_authorized": False,
        "qualified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metrics": metrics,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(receipt_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-only", action="store_true", help="Extract archive without installing")
    parser.add_argument("--validate-only", "--check", action="store_true", dest="validate_only", help="Validate extracted source")
    parser.add_argument("--write", action="store_true", help="Extract, validate, install, and generate qualification receipt")
    args = parser.parse_args()

    archive_path = resolve_archive()
    archive_digest = verify_archive(archive_path)
    print(f"Archive verified: {archive_path.name} (SHA-256: {archive_digest})")

    source_dir = ROOT / SOURCE_RELATIVE
    if args.write or args.extract_only or not source_dir.is_dir():
        extract_archive_safely(archive_path, source_dir)
        print(f"Archive extracted to: {source_dir}")

    controlled_source = source_dir / PACKAGE_DIRECTORY if (source_dir / PACKAGE_DIRECTORY).is_dir() else source_dir
    checked_files = verify_controlled_files(controlled_source)
    print(f"SHA256SUMS verified: {len(checked_files)} files checked")

    metrics = validate_extracted_source(controlled_source)
    print(f"Validation passed: {metrics['atomicSkills']} atomic skills, {metrics['metaSkills']} meta skills, {metrics['packs']} packs, {metrics['tables']} DB tables")

    if args.write or not args.validate_only:
        installed = install_dual_root_skills(controlled_source)
        print(f"Dual-root installed: {installed} skills to .agents/skills/ and agent-skills/runtime/")
        receipt = generate_local_qualification(archive_digest, metrics)
        print(f"Qualification receipt generated: {receipt['qualification_state']}")

    print(json.dumps({"status": "PASS", "package": PACKAGE_ID, "skills": metrics["atomicSkills"] + metrics["metaSkills"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
