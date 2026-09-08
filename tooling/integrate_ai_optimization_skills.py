#!/usr/bin/env python3
"""Safely integrate and validate the Elmos AI Optimization Skills Package v1.0.0.

The pinned ZIP archive is treated as untrusted data. This module performs
deterministic verification of SHA-256 digests, path traversal defenses,
symlink refusals, schema validation, task DAG acyclicity, and extracts
the immutable source mirror while installing the Codex discoverable skill.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    yaml = None
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "elmos-ai-optimization-skills"
PACKAGE_VERSION = "1.0.0"
PACKAGE_ID = "elmos-ai-optimization-skills-v1.0.0"
CODEX_SKILL_NAME = "elmos-ai-optimization"
CONTRACT_NAMESPACE = "ao.v1"

ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_NAME}-v{PACKAGE_VERSION}.zip"
SOURCE_RELATIVE = Path("skills") / f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"
INSTALL_DEST = Path(".agents/skills") / CODEX_SKILL_NAME
RECEIPT_NAME = ".installation-receipt.json"

EXPECTED_ARCHIVE_SHA256 = "79008469de02728d5eaa7133387c03b0686bfcda3efbabdfbeea1a12d77ccdf7"
EXPECTED_ARCHIVE_BYTES = 98081
EXPECTED_ENTRY_COUNT = 87
EXPECTED_UNCOMPRESSED_BYTES = 214272


class IntegrationError(RuntimeError):
    """Raised when package integration or verification fails closed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(path_str: str) -> PurePosixPath:
    p = PurePosixPath(path_str)
    if p.is_absolute() or ".." in p.parts or "\\" in path_str or "\x00" in path_str or str(p) != path_str:
        raise IntegrationError(f"Unsafe path refused: {path_str}")
    return p


def _verify_archive_integrity(archive_path: Path) -> bytes:
    if not archive_path.is_file():
        raise IntegrationError(f"Archive missing: {archive_path}")
    raw_bytes = archive_path.read_bytes()
    if len(raw_bytes) != EXPECTED_ARCHIVE_BYTES:
        raise IntegrationError(
            f"Archive size mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {len(raw_bytes)}"
        )
    actual_hash = _sha256(raw_bytes)
    if actual_hash != EXPECTED_ARCHIVE_SHA256:
        raise IntegrationError(
            f"Archive hash mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {actual_hash}"
        )
    return raw_bytes


def _read_json_strict(content: str) -> Any:
    return json.loads(
        content,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f"Non-finite JSON value {v}")),
    )


@dataclass(frozen=True)
class ArchiveSnapshot:
    archive_sha256: str
    archive_bytes: int
    entry_count: int
    uncompressed_bytes: int
    files: Mapping[str, str]  # relative_path -> sha256
    manifest: Mapping[str, Any]
    tasks: Sequence[Mapping[str, Any]]
    acceptance_cases: Sequence[Mapping[str, Any]]
    schemas: Mapping[str, Any]
    examples: Sequence[Mapping[str, str]]


def inspect_archive(archive_path: Path) -> ArchiveSnapshot:
    archive_bytes = _verify_archive_integrity(archive_path)
    with zipfile.ZipFile(archive_path) as zf:
        infolist = zf.infolist()
        if len(infolist) != EXPECTED_ENTRY_COUNT:
            raise IntegrationError(
                f"Entry count mismatch: expected {EXPECTED_ENTRY_COUNT}, got {len(infolist)}"
            )
        total_size = sum(info.file_size for info in infolist)
        if total_size != EXPECTED_UNCOMPRESSED_BYTES:
            raise IntegrationError(
                f"Uncompressed size mismatch: expected {EXPECTED_UNCOMPRESSED_BYTES}, got {total_size}"
            )

        files: dict[str, str] = {}
        prefix = f"{PACKAGE_ID}/"
        for info in infolist:
            if info.is_dir():
                raise IntegrationError(f"Archive should not contain explicit directory entries: {info.filename}")
            if not info.filename.startswith(prefix):
                raise IntegrationError(f"Entry {info.filename} does not start with prefix {prefix}")
            rel_name = info.filename[len(prefix):]
            _safe_relative(rel_name)
            data = zf.read(info.filename)
            h = _sha256(data)
            files[rel_name] = h

        # Check FILES.sha256 seal inside archive
        seal_content = zf.read(f"{prefix}FILES.sha256").decode("utf-8")
        seal_map: dict[str, str] = {}
        for line in seal_content.splitlines():
            if not line.strip():
                continue
            h, rel = line.split("  ", 1)
            seal_map[rel] = h

        for rel, expected_h in seal_map.items():
            if rel not in files:
                raise IntegrationError(f"Sealed file missing from archive: {rel}")
            if files[rel] != expected_h:
                raise IntegrationError(f"Sealed file hash mismatch for {rel}: expected {expected_h}, got {files[rel]}")

        # Check for unlisted files (FILES.sha256 itself is not in FILES.sha256)
        expected_keys = set(seal_map.keys()) | {"FILES.sha256"}
        if set(files.keys()) != expected_keys:
            unlisted = set(files.keys()) - expected_keys
            raise IntegrationError(f"Unlisted files in archive: {unlisted}")

        if yaml is None:
            raise IntegrationError("PyYAML is required to parse manifest and tasks")

        manifest = yaml.safe_load(zf.read(f"{prefix}manifest.yaml").decode("utf-8"))
        tasks_data = yaml.safe_load(zf.read(f"{prefix}tasks/tasks.yaml").decode("utf-8"))
        tasks = tasks_data.get("tasks", [])
        acceptance_data = yaml.safe_load(zf.read(f"{prefix}acceptance.yaml").decode("utf-8"))
        cases = acceptance_data.get("cases", [])

        # Validate DAG
        task_ids = {t["id"] for t in tasks}
        case_ids = {c["id"] for c in cases}
        if len(task_ids) != len(tasks):
            raise IntegrationError("Duplicate task IDs in tasks.yaml")
        if len(case_ids) != len(cases):
            raise IntegrationError("Duplicate case IDs in acceptance.yaml")

        deps = {t["id"]: t.get("depends_on", []) for t in tasks}
        visited = set()
        path = set()

        def dfs(node: str) -> None:
            if node not in task_ids:
                raise IntegrationError(f"Task depends on unknown task: {node}")
            if node in path:
                raise IntegrationError(f"Cycle detected in task DAG at {node}")
            if node in visited:
                return
            path.add(node)
            for dep in deps[node]:
                dfs(dep)
            path.remove(node)
            visited.add(node)

        for tid in task_ids:
            dfs(tid)

        # Validate schemas and examples
        schemas: dict[str, Any] = {}
        for name in files:
            if name.startswith("contracts/schemas/") and name.endswith(".schema.json"):
                s_bytes = zf.read(f"{prefix}{name}").decode("utf-8")
                s_json = _read_json_strict(s_bytes)
                if Draft202012Validator:
                    Draft202012Validator.check_schema(s_json)
                schemas[name] = s_json

        examples_index_bytes = zf.read(f"{prefix}contracts/examples/index.json").decode("utf-8")
        examples_index = _read_json_strict(examples_index_bytes)
        for item in examples_index:
            s_name = item["schema"]
            e_name = item["example"]
            if s_name not in schemas:
                raise IntegrationError(f"Schema not found for example: {s_name}")
            e_bytes = zf.read(f"{prefix}{e_name}").decode("utf-8")
            e_json = _read_json_strict(e_bytes)
            if Draft202012Validator:
                Draft202012Validator(schemas[s_name]).validate(e_json)

        return ArchiveSnapshot(
            archive_sha256=_sha256(archive_bytes),
            archive_bytes=len(archive_bytes),
            entry_count=len(infolist),
            uncompressed_bytes=total_size,
            files=files,
            manifest=manifest,
            tasks=tasks,
            acceptance_cases=cases,
            schemas=schemas,
            examples=examples_index,
        )


def _safe_extract(archive_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{PACKAGE_ID}/"
    with zipfile.ZipFile(archive_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith(prefix):
                raise IntegrationError(f"Entry {info.filename} does not start with {prefix}")
            rel_path = info.filename[len(prefix):]
            _safe_relative(rel_path)
            target = dest_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(info.filename)
            target.write_bytes(data)
            # Set standard file permissions (0o644) or executable for scripts (0o755)
            is_executable = rel_path.startswith("scripts/") or rel_path.endswith(".sh")
            mode = 0o755 if is_executable else 0o644
            os.chmod(target, mode)


def _install_codex_skill(source_dir: Path, install_dir: Path, files: Mapping[str, str]) -> Mapping[str, Any]:
    install_dir.mkdir(parents=True, exist_ok=True)
    skill_md = source_dir / "SKILL.md"
    if not skill_md.is_file():
        raise IntegrationError("Source SKILL.md missing")

    target_skill_md = install_dir / "SKILL.md"
    target_skill_md.write_bytes(skill_md.read_bytes())
    os.chmod(target_skill_md, 0o444)

    receipt = {
        "package": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "codex_skill": CODEX_SKILL_NAME,
        "source_directory": str(source_dir),
        "files_count": len(files),
    }
    receipt_file = install_dir / RECEIPT_NAME
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def write_integration(repo_root: Path, archive_path: Path) -> Mapping[str, Any]:
    snapshot = inspect_archive(archive_path)
    source_dest = repo_root / SOURCE_RELATIVE
    install_dest = repo_root / INSTALL_DEST

    if not source_dest.exists():
        _safe_extract(archive_path, source_dest)
    else:
        # Verify existing extracted files match
        for rel, expected_h in snapshot.files.items():
            p = source_dest / rel
            if not p.is_file() or _sha256(p.read_bytes()) != expected_h:
                raise IntegrationError(f"Extracted file {rel} is drifted or missing")

    receipt = _install_codex_skill(source_dest, install_dest, snapshot.files)
    return {
        "status": "SOURCE_EXTRACTED_AND_SKILLS_INSTALLED",
        "archive_sha256": snapshot.archive_sha256,
        "extracted_files": len(snapshot.files),
        "installed_skill": str(install_dest),
        "receipt": receipt,
        "tasks_count": len(snapshot.tasks),
        "acceptance_cases_count": len(snapshot.acceptance_cases),
        "schemas_count": len(snapshot.schemas),
    }


def check_integration(repo_root: Path, archive_path: Path) -> Mapping[str, Any]:
    snapshot = inspect_archive(archive_path)
    source_dest = repo_root / SOURCE_RELATIVE
    install_dest = repo_root / INSTALL_DEST

    if not source_dest.is_dir():
        raise IntegrationError(f"Source extraction directory missing: {source_dest}")

    for rel, expected_h in snapshot.files.items():
        p = source_dest / rel
        if not p.is_file():
            raise IntegrationError(f"Extracted source file missing: {rel}")
        actual_h = _sha256(p.read_bytes())
        if actual_h != expected_h:
            raise IntegrationError(f"Extracted source file corrupted/modified: {rel}")

    target_skill_md = install_dest / "SKILL.md"
    if not target_skill_md.is_file():
        raise IntegrationError("Installed SKILL.md missing")
    if _sha256(target_skill_md.read_bytes()) != snapshot.files["SKILL.md"]:
        raise IntegrationError("Installed SKILL.md differs from archive SKILL.md")

    receipt_file = install_dest / RECEIPT_NAME
    if not receipt_file.is_file():
        raise IntegrationError("Installation receipt missing")
    receipt = _read_json_strict(receipt_file.read_text())
    if receipt.get("archive_sha256") != EXPECTED_ARCHIVE_SHA256:
        raise IntegrationError("Installation receipt archive_sha256 mismatch")

    return {
        "status": "INSTALLATION_VERIFIED",
        "archive_sha256": snapshot.archive_sha256,
        "extracted_files": len(snapshot.files),
        "installed_skill": str(install_dest),
        "tasks_count": len(snapshot.tasks),
        "acceptance_cases_count": len(snapshot.acceptance_cases),
        "schemas_count": len(snapshot.schemas),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Extract source mirror and install skill")
    mode.add_argument("--check", action="store_true", help="Verify extraction integrity and drift")
    parser.add_argument("--root", type=Path, default=ROOT, help="Elmos repository root")
    parser.add_argument("--archive", type=Path, help="Override path to package zip")

    args = parser.parse_args(argv)
    repo_root = args.root.resolve()
    archive_path = args.archive.resolve() if args.archive else repo_root / ARCHIVE_RELATIVE

    try:
        if args.write:
            res = write_integration(repo_root, archive_path)
        else:
            res = check_integration(repo_root, archive_path)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    except IntegrationError as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
