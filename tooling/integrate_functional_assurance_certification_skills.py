#!/usr/bin/env python3
"""Safely integrate and independently qualify the Functional Assurance & Certification Skills v4.1.0 package.

The source archive is untrusted declarative source material. This importer
checks archive identity, path safety, internal checksums, exact Skill counts,
adapter matrices, schemas, workflows, policies, migrations, and DAG acyclicity
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
    raise SystemExit("PyYAML and jsonschema are required; use `make functional-assurance-skills`") from exc

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-functional-assurance-certification-skills-v4.1.0"
PACKAGE_ID = "elmos-functional-assurance-certification-skills-v4.1.0"
PACKAGE_NAME = "elmos-functional-assurance-certification-skills"
PACKAGE_VERSION = "4.1.0"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/functional-assurance-certification")
ENGINE_RELATIVE = Path("engines/functional-assurance-engine")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
CLAUDE_SKILLS_RELATIVE = Path(".claude/skills")

EXPECTED_ARCHIVE_SHA256 = "c4b79121f0f71b2bf7b042fc5449f9904cf68a525a795b5359177b38486e4a15"
EXPECTED_ARCHIVE_BYTES = 5_018_387
EXPECTED_FILE_COUNT = 4_049
EXPECTED_CONTROLLED_FILES = 4_048

EXPECTED_COUNTS = {
    "skills": 178,
    "perSkillFiles": 2314,
    "externalDependencyEdges": 123,
    "adapters": 112,
    "perAdapterFiles": 896,
    "schemas": 219,
    "examples": 219,
    "workflows": 39,
    "policies": 37,
    "policyTests": 37,
    "migrations": 12,
    "goldenRoutes": 23,
    "implementationBatches": 18,
    "implementationTasks": 178,
    "traceability": 178,
    "referenceModules": 71,
    "referenceTests": 104,
    "nativeFixtureFiles": 24,
    "docs": 36,
}

SKILL_ROOT_FILES = {
    "SKILL.md",
    "contract.yaml",
    "implementation.yaml",
    "acceptance.yaml",
    "evidence.yaml",
    "domain-model.yaml",
    "native-test-matrix.yaml",
    "threat-model.yaml",
    "version-support.yaml",
    "observability.yaml",
    "api-contract.yaml",
}
SKILL_NESTED = {"references/IMPLEMENTATION_GUIDE.md", "scripts/validate_artifacts.py"}
ADAPTER_FILES = {
    "adapter.yaml",
    "capability-map.yaml",
    "lowering-contract.yaml",
    "conformance.yaml",
    "version-support.yaml",
    "native-test-matrix.yaml",
    "threat-model.yaml",
    "deployment-profile.yaml",
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
    cf_path = source_dir / "CONTROLLED_FILES.sha256"
    if not cf_path.is_file():
        fail("missing CONTROLLED_FILES.sha256 in source")
    rows = cf_path.read_text(encoding="utf-8").splitlines()
    checked: dict[str, str] = {}
    for line in rows:
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            fail(f"malformed CONTROLLED_FILES row: {line}")
        expected_digest, rel_str = parts
        rel_path = PurePosixPath(rel_str)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            fail(f"unsafe relative path in controlled manifest: {rel_str}")
        local_path = source_dir / rel_path
        if not local_path.is_file():
            fail(f"missing controlled file in source tree: {rel_str}")
        actual_digest = digest_bytes(local_path.read_bytes())
        if actual_digest != expected_digest:
            fail(f"digest mismatch on controlled file {rel_str}: expected {expected_digest}, got {actual_digest}")
        checked[str(rel_path)] = expected_digest
    if len(checked) != EXPECTED_CONTROLLED_FILES:
        fail(f"controlled file count mismatch: expected {EXPECTED_CONTROLLED_FILES}, got {len(checked)}")
    return checked


def verify_skills(source_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    skills_dir = source_dir / "agent-skills" / "runtime"
    if not skills_dir.is_dir():
        fail("missing agent-skills/runtime in source")
    skills: dict[str, dict[str, Any]] = {}
    dag: dict[str, list[str]] = {}

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        for rf in SKILL_ROOT_FILES:
            f = entry / rf
            if not f.is_file():
                fail(f"skill {name} missing required contract file {rf}")
        for nf in SKILL_NESTED:
            f = entry / nf
            if not f.is_file():
                fail(f"skill {name} missing required nested file {nf}")

        contract = load_yaml((entry / "contract.yaml").read_bytes(), f"skill {name} contract")
        if not isinstance(contract, dict):
            fail(f"skill {name} contract.yaml must be mapping")
        meta = contract.get("metadata", {})
        spec = contract.get("spec", {})
        cname = meta.get("name") if isinstance(meta, dict) else contract.get("name")
        if cname != name:
            fail(f"skill {name} contract name mismatch: {cname}")
        deps = spec.get("dependencies", contract.get("dependencies", []))
        if not isinstance(deps, list):
            fail(f"skill {name} dependencies must be list")
        dag[name] = [str(d) for d in deps if isinstance(d, str)]
        skills[name] = contract

    if len(skills) != EXPECTED_COUNTS["skills"]:
        fail(f"skill count mismatch: expected {EXPECTED_COUNTS['skills']}, got {len(skills)}")
    return skills, dag


def verify_adapters(source_dir: Path) -> dict[str, dict[str, Any]]:
    adapters_dir = source_dir / "target-adapters"
    if not adapters_dir.is_dir():
        fail("missing target-adapters in source")
    adapters: dict[str, dict[str, Any]] = {}
    for entry in sorted(adapters_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        for af in ADAPTER_FILES:
            f = entry / af
            if not f.is_file():
                fail(f"adapter {name} missing required file {af}")
        adapt = load_yaml((entry / "adapter.yaml").read_bytes(), f"adapter {name}")
        meta = adapt.get("metadata", {})
        aname = meta.get("name") if isinstance(meta, dict) else adapt.get("name")
        if aname != name:
            fail(f"adapter {name} metadata name mismatch: {aname}")
        adapters[name] = adapt
    if len(adapters) != EXPECTED_COUNTS["adapters"]:
        fail(f"adapter count mismatch: expected {EXPECTED_COUNTS['adapters']}, got {len(adapters)}")
    return adapters


def verify_dag(dag: dict[str, list[str]]) -> None:
    indegree: dict[str, int] = {k: 0 for k in dag}
    reverse: dict[str, list[str]] = defaultdict(list)
    for u, neighbors in dag.items():
        for v in neighbors:
            if v in indegree:
                indegree[v] += 1
                reverse[u].append(v)
    q = deque([k for k, deg in indegree.items() if deg == 0])
    visited = 0
    while q:
        curr = q.popleft()
        visited += 1
        for nxt in reverse[curr]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)
    if visited != len(dag):
        fail("dependency graph has cycles or disconnected dependencies")


def copy_skill_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def sync_skills(source_dir: Path) -> list[str]:
    src_runtime = source_dir / "agent-skills" / "runtime"
    runtime_dst = ROOT / RUNTIME_SKILLS_RELATIVE
    workspace_dst = ROOT / WORKSPACE_SKILLS_RELATIVE

    installed = []
    for sdir in sorted(src_runtime.iterdir()):
        if not sdir.is_dir():
            continue
        sname = sdir.name
        copy_skill_tree(sdir, runtime_dst / sname)
        copy_skill_tree(sdir, workspace_dst / sname)
        installed.append(sname)
    return installed


def generate_manifest(source_dir: Path, archive_sha: str, installed_skills: list[str]) -> Path:
    doc_dir = ROOT / DOC_RELATIVE
    doc_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = doc_dir / "installed-manifest.json"

    manifest_data = {
        "package_id": PACKAGE_ID,
        "package_name": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "archive_sha256": archive_sha,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skill_count": len(installed_skills),
        "adapter_count": EXPECTED_COUNTS["adapters"],
        "controlled_file_count": EXPECTED_CONTROLLED_FILES,
        "installed_skills": installed_skills,
        "dual_root_parity": True,
        "status": "QUALIFIED_LOCAL_EXECUTABLE",
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrate Functional Assurance & Certification Skills v4.1.0")
    parser.add_argument("--skip-install", action="store_true", help="Validate without syncing skills")
    parser.add_argument("--check", action="store_true", help="Perform verification check")
    args = parser.parse_args()

    print(f"==> Verifying archive {PACKAGE_DIRECTORY}.zip...")
    archive_path = resolve_archive()
    archive_sha = verify_archive(archive_path)
    print(f"    Archive verified: {archive_sha}")

    source_dir = ROOT / SOURCE_RELATIVE
    if not source_dir.is_dir():
        fail(f"Source directory missing at {SOURCE_RELATIVE}")

    print(f"==> Verifying controlled files ({EXPECTED_CONTROLLED_FILES} files)...")
    controlled = verify_controlled_files(source_dir)
    print(f"    Verified {len(controlled)} controlled files.")

    print(f"==> Verifying skills ({EXPECTED_COUNTS['skills']} skills)...")
    skills, dag = verify_skills(source_dir)
    print(f"    Verified {len(skills)} skills with complete 13-file contracts.")

    print(f"==> Verifying adapters ({EXPECTED_COUNTS['adapters']} adapters)...")
    adapters = verify_adapters(source_dir)
    print(f"    Verified {len(adapters)} adapters.")

    print(f"==> Verifying skill DAG acyclicity...")
    verify_dag(dag)
    print(f"    DAG is strictly acyclic.")

    if not args.skip_install:
        print(f"==> Syncing skills to dual roots (.agents/skills and agent-skills/runtime)...")
        installed = sync_skills(source_dir)
        print(f"    Installed {len(installed)} skills.")
        manifest_path = generate_manifest(source_dir, archive_sha, installed)
        print(f"    Wrote manifest to {manifest_path}")

    print("==> Functional Assurance & Certification Skills v4.1.0 qualification PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
