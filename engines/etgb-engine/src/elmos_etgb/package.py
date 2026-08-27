"""Read-only validation of the attached ETGB source package."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


EXPECTED_ARCHIVE_SHA256 = "fcd4fbdadea0498a6f9598ce592627a936d70467f884052319a11ee7e9dad202"
PACKAGE_ROOT_NAME = "elmos-etgb-sota-skills-package-v1.0.0"
SKILL_NAMES = (
    "etgb-orchestrator",
    "test-case-authoring",
    "spring-modernization-validation",
    "repository-translation-validation",
    "project-generation-validation",
    "sql-dialect-routine-validation",
    "differential-oracle-engine",
    "metamorphic-fuzz-mutation",
    "corpus-governance",
    "release-certification",
)
_CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and "" not in path.parts and all(part not in {".", ".."} for part in path.parts)


def _checksum_rows(content: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        match = _CHECKSUM_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"invalid SHA256SUMS row {number}")
        if match.group(2) in rows:
            raise ValueError(f"duplicate SHA256SUMS path: {match.group(2)}")
        rows[match.group(2)] = match.group(1)
    return rows


def verify_source_package(archive: Path, *, extracted: Path | None = None, expected_archive_sha256: str = EXPECTED_ARCHIVE_SHA256) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    archive = archive.resolve(strict=True)
    actual_digest = file_sha256(archive)
    if expected_archive_sha256 and actual_digest != expected_archive_sha256:
        errors.append(f"archive digest mismatch: expected {expected_archive_sha256}, got {actual_digest}")
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        names = [info.filename for info in infos]
        duplicate_names = sorted({name for name in names if names.count(name) > 1})
        errors.extend(f"duplicate archive member: {name}" for name in duplicate_names)
        for info in infos:
            if not _safe_member(info.filename):
                errors.append(f"unsafe archive member: {info.filename}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                errors.append(f"symlink archive member is forbidden: {info.filename}")
        prefix = PACKAGE_ROOT_NAME + "/"
        if not all(name.startswith(prefix) for name in names):
            errors.append("archive contains a member outside the pinned package root")
        relative = {name[len(prefix):]: name for name in names if name.startswith(prefix) and name != prefix}
        required = {"PACKAGE_MANIFEST.json", "SHA256SUMS", "skills/manifest.yaml", "suites/suite.yaml", "schemas/test-case.schema.json"}
        errors.extend(f"missing package member: {path}" for path in sorted(required - relative.keys()))
        checksums: dict[str, str] = {}
        if "SHA256SUMS" in relative:
            try:
                checksums = _checksum_rows(package.read(relative["SHA256SUMS"]).decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                errors.append(str(exc))
        for path, expected in checksums.items():
            if path not in relative:
                errors.append(f"checksum references missing member: {path}")
                continue
            actual = hashlib.sha256(package.read(relative[path])).hexdigest()
            if actual != expected:
                errors.append(f"package checksum mismatch: {path}")
        manifest: dict[str, Any] = {}
        try:
            manifest = json.loads(package.read(relative["PACKAGE_MANIFEST.json"]))
        except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"invalid PACKAGE_MANIFEST.json: {exc}")
        if manifest:
            if manifest.get("package") != PACKAGE_ROOT_NAME:
                errors.append("package manifest identity mismatch")
            checksum_file_count = len(checksums) - (1 if "PACKAGE_MANIFEST.json" in checksums else 0)
            if manifest.get("file_count") != checksum_file_count:
                errors.append("package manifest file_count does not match SHA256SUMS")
        try:
            skill_manifest = yaml.safe_load(package.read(relative["skills/manifest.yaml"]))
            declared = [item.get("name") for item in skill_manifest.get("skills", [])]
            if tuple(declared) != SKILL_NAMES:
                errors.append(f"skill registry mismatch: {declared}")
            declared_names = set(declared)
            edges = [(item.get("name"), dependency) for item in skill_manifest.get("skills", []) for dependency in item.get("depends_on", [])]
            errors.extend(f"skill dependency references unknown skill: {owner}->{dependency}" for owner, dependency in edges if dependency not in declared_names)
            graph = {name: [] for name in declared_names}
            for owner, dependency in edges:
                graph[owner].append(dependency)
            visiting: set[str] = set()
            visited: set[str] = set()
            def visit(name: str) -> None:
                if name in visiting:
                    raise ValueError(f"skill dependency cycle at {name}")
                if name in visited:
                    return
                visiting.add(name)
                for dependency in graph[name]:
                    visit(dependency)
                visiting.remove(name)
                visited.add(name)
            for name in graph:
                visit(name)
        except (KeyError, TypeError, AttributeError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"invalid skill manifest: {exc}")
        if extracted:
            extracted = extracted.resolve(strict=True)
            for path in checksums:
                local = extracted / path
                if not local.is_file():
                    errors.append(f"extracted source missing: {path}")
                    continue
                if file_sha256(local) != checksums[path]:
                    errors.append(f"extracted source drift: {path}")
            extra = [path.relative_to(extracted).as_posix() for path in extracted.rglob("*") if path.is_file() and not any(part in {".venv", ".pytest_cache", "__pycache__"} or part.endswith(".egg-info") for part in path.relative_to(extracted).parts) and path.relative_to(extracted).as_posix() not in checksums]
            if extra:
                warnings.append(f"extracted tree has {len(extra)} generated or unmanifested files")
    return {
        "valid": not errors,
        "archive": str(archive),
        "archive_sha256": actual_digest,
        "archive_matches_pin": actual_digest == expected_archive_sha256,
        "archive_entries": len(names) if 'names' in locals() else 0,
        "checksum_entries": len(checksums) if 'checksums' in locals() else 0,
        "skills": list(SKILL_NAMES),
        "errors": errors,
        "warnings": warnings,
    }
