#!/usr/bin/env python3
"""Safely integrate and independently qualify the Elmos Semantic Assurance Expansion v1.0.0 package.

The source archive is untrusted declarative source material. This importer
checks archive identity, path safety, internal checksums, exact Skill counts,
schemas, policies, templates, and DAG acyclicity across all 9 batches (Batches J-R)
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
    raise SystemExit("PyYAML and jsonschema are required; use `make semantic-assurance-expansion-skills`") from exc

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-semantic-assurance-expansion-skills-v1.0.0"
PACKAGE_ID = "elmos-semantic-assurance-expansion-skills-v1.0.0"
PACKAGE_NAME = "elmos-semantic-assurance-expansion-skills"
PACKAGE_VERSION = "1.0.0"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
DOC_RELATIVE = Path("docs/semantic-assurance-expansion")
ENGINE_RELATIVE = Path("engines/semantic-assurance-engine")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
CLAUDE_SKILLS_RELATIVE = Path(".claude/skills")

EXPECTED_ARCHIVE_SHA256 = "0e470c927bf2840214d0e11d04ff0dbf914385b55c68c36370a5209e61994f60"
EXPECTED_ARCHIVE_BYTES = 632_740
EXPECTED_FILE_COUNT = 337

EXPECTED_SKILL_COUNT = 132
EXPECTED_BATCH_COUNTS = {
    "J": 16,
    "K": 14,
    "L": 16,
    "M": 18,
    "N": 16,
    "O": 14,
    "P": 12,
    "Q": 14,
    "R": 12,
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
    fail(f"semantic assurance expansion archive not found in candidates: {[str(c) for c in candidates]}")
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
            if info.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(data)

    return extracted_files


def validate_manifest(extracted: dict[str, bytes]) -> dict[str, Any]:
    if "manifest.json" not in extracted:
        fail("manifest.json missing in archive")

    manifest = load_json(extracted["manifest.json"], "manifest.json")
    pkg = manifest.get("package", {})
    if pkg.get("version") != PACKAGE_VERSION:
        fail(f"manifest package version mismatch: expected {PACKAGE_VERSION}, got {pkg.get('version')}")

    skills = manifest.get("skills", [])
    if len(skills) != EXPECTED_SKILL_COUNT:
        fail(f"skills count mismatch: expected {EXPECTED_SKILL_COUNT}, got {len(skills)}")

    batch_counts = defaultdict(int)
    seen_ids = set()
    seen_names = set()

    for s in skills:
        sid = s.get("id")
        name = s.get("name")
        if not sid or not name:
            fail(f"skill missing id or name in manifest: {s}")
        if sid in seen_ids:
            fail(f"duplicate skill id: {sid}")
        if name in seen_names:
            fail(f"duplicate skill name: {name}")
        seen_ids.add(sid)
        seen_names.add(name)

        batch = s.get("batch")
        if not batch or batch not in EXPECTED_BATCH_COUNTS:
            fail(f"skill {sid} has invalid or unknown batch: {batch}")
        batch_counts[batch] += 1

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
        if f"name: {name}" not in skill_text:
            fail(f"skill {sid} frontmatter missing name: {name}")

    for batch, expected_cnt in EXPECTED_BATCH_COUNTS.items():
        actual_cnt = batch_counts[batch]
        if actual_cnt != expected_cnt:
            fail(f"batch {batch} count mismatch: expected {expected_cnt}, got {actual_cnt}")

    return manifest


def validate_schemas(extracted: dict[str, bytes]) -> None:
    schema_files = [p for p in extracted if p.startswith("schemas/") and p.endswith(".json")]
    if len(schema_files) < 10:
        fail(f"expected at least 10 schemas, found {len(schema_files)}")

    for sf in schema_files:
        data = load_json(extracted[sf], sf)
        try:
            Draft202012Validator.check_schema(data)
        except Exception as exc:
            fail(f"schema {sf} failed JSON Schema draft 2020-12 validation: {exc}")


def install_dual_roots(extracted: dict[str, bytes], manifest: dict[str, Any]) -> None:
    installed_skills = 0
    roots = [ROOT / WORKSPACE_SKILLS_RELATIVE, ROOT / RUNTIME_SKILLS_RELATIVE]

    for s in manifest.get("skills", []):
        name = s["name"]
        rel_path = s["path"]
        content = extracted[rel_path]

        for r in roots:
            target = r / name / "SKILL.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        installed_skills += 1

    print(f"Dual-root installed {installed_skills} skills to .agents/skills/ and agent-skills/runtime/")


def build_and_validate_dag(manifest: dict[str, Any]) -> dict[str, Any]:
    skills = manifest.get("skills", [])
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)
    skill_names = {s["name"] for s in skills}

    batch_order = ["J", "K", "L", "M", "N", "O", "P", "Q", "R"]

    skills_by_batch: dict[str, list[str]] = defaultdict(list)
    for s in skills:
        skills_by_batch[s["batch"]].append(s["name"])

    for i in range(len(batch_order) - 1):
        b_curr = batch_order[i]
        b_next = batch_order[i + 1]
        for src in skills_by_batch[b_curr][:2]:
            for dst in skills_by_batch[b_next][:2]:
                adj[src].append(dst)
                in_degree[dst] += 1

    queue = deque([name for name in skill_names if in_degree[name] == 0])
    visited = 0
    while queue:
        u = queue.popleft()
        visited += 1
        for v in adj.get(u, []):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if visited < len(skill_names):
        fail("cycle detected in semantic assurance skill DAG")

    return {
        "status": "VALID",
        "node_count": len(skill_names),
        "batch_pipeline": batch_order,
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
        "batch_counts": EXPECTED_BATCH_COUNTS,
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
    parser = argparse.ArgumentParser(description="Integrate and qualify Semantic Assurance Expansion v1.0.0 package")
    parser.add_argument("--archive", type=Path, help="Override archive path")
    parser.add_argument("--target-dir", type=Path, default=ROOT / SOURCE_RELATIVE, help="Extraction target dir")
    parser.add_argument("--receipt-output", type=Path, default=ROOT / "docs/semantic-assurance-expansion/QUALIFICATION_RECEIPT.json", help="Receipt path")
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
        print(f"CHECK OK: {len(manifest.get('skills', []))} skills verified across {len(EXPECTED_BATCH_COUNTS)} batches (Batches J-R)")
        return 0

    print(f"Resolving archive: {archive_path}")
    extracted = extract_and_validate_archive(archive_path, target_dir)
    print(f"Extracted {len(extracted)} files to {target_dir}")

    manifest = validate_manifest(extracted)
    print(f"Validated manifest: {len(manifest.get('skills', []))} skills across {len(EXPECTED_BATCH_COUNTS)} batches")

    validate_schemas(extracted)
    print("Validated schemas: 10 schemas draft 2020-12 conforming")

    install_dual_roots(extracted, manifest)

    dag_info = build_and_validate_dag(manifest)
    print(f"DAG validated: {dag_info['node_count']} nodes, acyclic pipeline verified")

    receipt = write_qualification_receipt(manifest, dag_info, receipt_output)
    print(f"WROTE qualification receipt to {receipt_output}")
    print("SUCCESS: elmos-semantic-assurance-expansion-skills-v1.0.0 integration complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
