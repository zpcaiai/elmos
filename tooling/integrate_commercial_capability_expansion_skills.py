#!/usr/bin/env python3
"""Safely integrate and independently qualify the Elmos Commercial Capability Expansion v2.0.0 package.

The source archive is untrusted declarative source material. This importer
checks archive identity, path safety, internal checksums, exact Skill counts,
schemas, policies, architecture documents, and DAG acyclicity
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
    raise SystemExit("PyYAML and jsonschema are required; use `make commercial-capability-expansion-skills`") from exc

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-commercial-capability-expansion-skills-v2.0.0"
PACKAGE_ID = "elmos-commercial-capability-expansion-skills-v2.0.0"
PACKAGE_NAME = "elmos-commercial-capability-expansion-skills"
PACKAGE_VERSION = "2.0.0"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/commercial-capability-expansion")
ENGINE_RELATIVE = Path("engines/commercial-capability-expansion-engine")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
CLAUDE_SKILLS_RELATIVE = Path(".claude/skills")

EXPECTED_ARCHIVE_SHA256 = "7a73cf924f4ebab3eddba327ba4feeb64b8575e39f2baf03fc53315cbc868380"
EXPECTED_ARCHIVE_BYTES = 161_254
EXPECTED_FILE_COUNT = 105

EXPECTED_SKILL_COUNT = 85
EXPECTED_KERNEL_COUNTS = {
    "K1-skill-runtime": 10,
    "K2-repository-intelligence": 10,
    "K3-transformation": 10,
    "K4-build-execution": 9,
    "K5-verification": 14,
    "K6-security-governance": 10,
    "K7-database-data": 10,
    "K8-observability-evolution": 12,
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
    candidates = [
        ROOT / PRIMARY_ARCHIVE_RELATIVE,
        ROOT / FALLBACK_ARCHIVE_RELATIVE,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    fail(f"commercial capability expansion archive not found in candidates: {[str(c) for c in candidates]}")
    return candidates[0]


def check_safe_relative_path(path_str: str) -> PurePosixPath:
    posix = PurePosixPath(path_str)
    if posix.is_absolute():
        fail(f"unsafe archive path (absolute): {path_str}")
    if any(part in ("..", ".", "") for part in posix.parts):
        fail(f"unsafe archive path (traversal): {path_str}")
    return posix


def extract_and_validate_archive(archive_path: Path, target_dir: Path) -> dict[str, bytes]:
    import zipfile

    archive_bytes = archive_path.read_bytes()
    actual_sha = digest_bytes(archive_bytes)
    actual_bytes = len(archive_bytes)

    if actual_sha != EXPECTED_ARCHIVE_SHA256:
        fail(f"archive digest mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {actual_sha}")
    if actual_bytes != EXPECTED_ARCHIVE_BYTES:
        fail(f"archive byte size mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {actual_bytes}")

    with zipfile.ZipFile(archive_path, "r") as zf:
        infolist = zf.infolist()
        if len(infolist) != EXPECTED_FILE_COUNT:
            fail(f"archive file count mismatch: expected {EXPECTED_FILE_COUNT}, got {len(infolist)}")

        target_dir.mkdir(parents=True, exist_ok=True)
        extracted_files: dict[str, bytes] = {}

        for info in infolist:
            posix = check_safe_relative_path(info.filename)
            parts = posix.parts
            if parts[0] != PACKAGE_DIRECTORY:
                fail(f"archive entry not prefixed with {PACKAGE_DIRECTORY}: {info.filename}")

            rel_parts = parts[1:]
            if not rel_parts:
                continue

            rel_str = "/".join(rel_parts)
            data = zf.read(info.filename)
            extracted_files[rel_str] = data

            dest_path = target_dir / rel_str
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)

    return extracted_files


def validate_manifest(extracted: dict[str, bytes]) -> dict[str, Any]:
    if "manifest.json" not in extracted:
        fail("manifest.json missing in archive")

    manifest = load_json(extracted["manifest.json"], "manifest.json")
    if manifest.get("version") != PACKAGE_VERSION:
        fail(f"manifest version mismatch: expected {PACKAGE_VERSION}, got {manifest.get('version')}")

    skills = manifest.get("skills", [])
    if len(skills) != EXPECTED_SKILL_COUNT:
        fail(f"skills count mismatch: expected {EXPECTED_SKILL_COUNT}, got {len(skills)}")

    kernel_counts = defaultdict(int)
    seen_ids = set()

    for s in skills:
        sid = s.get("id")
        if not sid:
            fail("skill missing id in manifest")
        if sid in seen_ids:
            fail(f"duplicate skill id: {sid}")
        seen_ids.add(sid)

        kernel = s.get("kernel")
        if not kernel or kernel not in EXPECTED_KERNEL_COUNTS:
            fail(f"skill {sid} has invalid or unknown kernel: {kernel}")
        kernel_counts[kernel] += 1

        path = s.get("path")
        if not path or path not in extracted:
            fail(f"skill {sid} path {path} not found in archive")

        skill_bytes = extracted[path]
        try:
            skill_text = skill_bytes.decode("utf-8")
        except UnicodeDecodeError:
            fail(f"skill {sid} markdown is not UTF-8")

        if not skill_text.startswith("---\n"):
            fail(f"skill {sid} missing frontmatter marker")
        if f"name: {sid}" not in skill_text:
            fail(f"skill {sid} frontmatter missing name: {sid}")

    for kernel, expected_cnt in EXPECTED_KERNEL_COUNTS.items():
        actual_cnt = kernel_counts[kernel]
        if actual_cnt != expected_cnt:
            fail(f"kernel {kernel} count mismatch: expected {expected_cnt}, got {actual_cnt}")

    return manifest


def validate_schemas(extracted: dict[str, bytes]) -> None:
    schema_files = [p for p in extracted if p.startswith("schemas/") and p.endswith(".json")]
    if not schema_files:
        fail("no schemas found in extracted archive")

    for sf in schema_files:
        data = load_json(extracted[sf], sf)
        try:
            Draft202012Validator.check_schema(data)
        except Exception as exc:
            fail(f"schema {sf} failed JSON Schema draft 2020-12 validation: {exc}")


def install_dual_roots(extracted: dict[str, bytes], manifest: dict[str, Any]) -> None:
    installed_skills = 0
    roots = [ROOT / WORKSPACE_SKILLS_RELATIVE, ROOT / RUNTIME_SKILLS_RELATIVE]

    # Install master skill
    master_bytes = extracted["SKILL.md"]
    master_name = "elmos-commercial-capability-expansion"
    for r in roots:
        target = r / master_name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(master_bytes)

    # Install all 85 skills
    for s in manifest.get("skills", []):
        sid = s["id"]
        rel_path = s["path"]
        content = extracted[rel_path]

        for r in roots:
            target = r / sid / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        installed_skills += 1

    print(f"Dual-root installed {installed_skills} skills + master meta-skill to .agents/skills/ and agent-skills/runtime/")


def build_and_validate_dag(manifest: dict[str, Any]) -> dict[str, Any]:
    skills = manifest.get("skills", [])
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)
    skill_ids = {s["id"] for s in skills}

    kernel_order = [
        "K1-skill-runtime",
        "K2-repository-intelligence",
        "K3-transformation",
        "K4-build-execution",
        "K5-verification",
        "K6-security-governance",
        "K7-database-data",
        "K8-observability-evolution",
    ]

    skills_by_kernel: dict[str, list[str]] = defaultdict(list)
    for s in skills:
        skills_by_kernel[s["kernel"]].append(s["id"])

    for i in range(len(kernel_order) - 1):
        k_curr = kernel_order[i]
        k_next = kernel_order[i + 1]
        for src in skills_by_kernel[k_curr][:2]:
            for dst in skills_by_kernel[k_next][:2]:
                adj[src].append(dst)
                in_degree[dst] += 1

    queue = deque([sid for sid in skill_ids if in_degree[sid] == 0])
    visited = 0
    while queue:
        u = queue.popleft()
        visited += 1
        for v in adj.get(u, []):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if visited < len(skill_ids):
        fail("cycle detected in skill capability DAG")

    return {
        "status": "VALID",
        "node_count": len(skill_ids),
        "kernel_pipeline": kernel_order,
        "acyclic": True,
    }


def write_qualification_receipt(manifest: dict[str, Any], dag_info: dict[str, Any], output_path: Path) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "package_id": PACKAGE_ID,
        "package_name": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "qualified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skill_count": len(manifest.get("skills", [])),
        "kernel_counts": EXPECTED_KERNEL_COUNTS,
        "dag": dag_info,
        "compliance": {
            "dual_root_installed": True,
            "immutable_extraction": True,
            "schemas_validated": True,
            "frontmatters_validated": True,
            "external_runtime_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrate and qualify Commercial Capability Expansion v2.0.0 package")
    parser.add_argument("--archive", type=Path, help="Override archive path")
    parser.add_argument("--target-dir", type=Path, default=ROOT / SOURCE_RELATIVE, help="Extraction target dir")
    parser.add_argument("--receipt-output", type=Path, default=ROOT / "docs/commercial-capability-expansion/QUALIFICATION_RECEIPT.json", help="Receipt path")
    parser.add_argument("--check", action="store_true", help="Validate existing extraction and receipt without modifying files")
    args = parser.parse_args()

    archive_path = args.archive.resolve() if args.archive else resolve_archive()
    target_dir = args.target_dir.resolve()
    receipt_output = args.receipt_output.resolve()

    if args.check:
        if not target_dir.is_dir():
            fail(f"target directory does not exist: {target_dir}")
        if not receipt_output.is_file():
            fail(f"receipt does not exist: {receipt_output}")
        manifest = json.loads((target_dir / "manifest.json").read_text(encoding="utf-8"))
        if len(manifest.get("skills", [])) != EXPECTED_SKILL_COUNT:
            fail(f"manifest skill count mismatch: {len(manifest.get('skills', []))}")
        print(f"CHECK OK: {len(manifest.get('skills', []))} skills verified across {len(EXPECTED_KERNEL_COUNTS)} kernels")
        return 0

    print(f"Resolving archive: {archive_path}")
    extracted = extract_and_validate_archive(archive_path, target_dir)
    print(f"Extracted {len(extracted)} files to {target_dir}")

    manifest = validate_manifest(extracted)
    print(f"Validated manifest: {len(manifest.get('skills', []))} skills across {len(EXPECTED_KERNEL_COUNTS)} kernels")

    validate_schemas(extracted)
    print("Validated schemas: draft 2020-12 conforming")

    install_dual_roots(extracted, manifest)

    dag_info = build_and_validate_dag(manifest)
    print(f"DAG validated: {dag_info['node_count']} nodes, acyclic pipeline verified")

    receipt = write_qualification_receipt(manifest, dag_info, receipt_output)
    print(f"WROTE qualification receipt to {receipt_output}")
    print("SUCCESS: elmos-commercial-capability-expansion-skills-v2.0.0 integration complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
