from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .models import SUPPORTED_LANGUAGES, Language, RouteError

_EXTENSIONS: dict[str, Language] = {
    ".java": "java",
    ".py": "python",
    ".cs": "csharp",
    ".ts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".m": "objc",
    ".swift": "swift",
}
_IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "target",
    "vendor",
}
_SAFE_REPOSITORY_REF = re.compile(r"^local:[A-Za-z0-9][A-Za-z0-9._/-]{2,170}$")
_SAFE_WORKSPACE_REF = re.compile(
    r"^repository-workspace:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}@[0-9a-f]{40}$"
)
_MAX_FILES = 5_000
_MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_FILE_BYTES = 2 * 1024 * 1024


def _repository_scale(file_count: int, byte_count: int) -> str:
    """Classify the bounded repository size without widening the hard limits.

    The repository runner is deliberately scoped to small and medium source
    estates.  The label is evidence about the inventory size, not a claim that
    every construct in those files is supported by the active semantic
    profile.
    """

    if file_count <= 500 and byte_count <= 8 * 1024 * 1024:
        return "small"
    return "medium"


def _repository_ref(value: str) -> str:
    repository_ref = value.strip()
    if _SAFE_REPOSITORY_REF.fullmatch(repository_ref) or _SAFE_WORKSPACE_REF.fullmatch(repository_ref):
        return repository_ref
    if (
        repository_ref.startswith("https://")
        and len(repository_ref) <= 180
        and not any(character in repository_ref for character in (" ", "\\", "?", "#", "@"))
    ):
        return repository_ref
    raise RouteError("REPOSITORY_REF_INVALID")


def _read_stable(path: Path) -> bytes:
    before = path.stat(follow_symlinks=False)
    if before.st_size > _MAX_FILE_BYTES:
        raise RouteError(f"REPOSITORY_SOURCE_FILE_TOO_LARGE:{path.name}")
    content = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or len(content) != before.st_size:
        raise RouteError(f"REPOSITORY_CHANGED_DURING_INVENTORY:{path.name}")
    return content


def plan_repository(
    repository: Path,
    repository_ref: str,
    source_language: Language,
    target_language: Language,
) -> dict[str, Any]:
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if repository.is_symlink() or not repository.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    root = repository.resolve(strict=True)
    safe_ref = _repository_ref(repository_ref)
    inventory: list[dict[str, Any]] = []
    language_counts = {language: 0 for language in SUPPORTED_LANGUAGES}
    ignored_symlink_count = 0
    total_bytes = 0

    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_directories: list[str] = []
        for directory in sorted(directories):
            candidate = current_path / directory
            if directory in _IGNORED_DIRECTORIES:
                continue
            if candidate.is_symlink():
                ignored_symlink_count += 1
                continue
            safe_directories.append(directory)
        directories[:] = safe_directories
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                ignored_symlink_count += 1
                continue
            language = _EXTENSIONS.get(path.suffix.lower())
            if language is None:
                continue
            relative = path.relative_to(root).as_posix()
            content = _read_stable(path)
            total_bytes += len(content)
            if len(inventory) >= _MAX_FILES:
                raise RouteError("REPOSITORY_FILE_LIMIT_EXCEEDED")
            if total_bytes > _MAX_SOURCE_BYTES:
                raise RouteError("REPOSITORY_SOURCE_BYTES_LIMIT_EXCEEDED")
            language_counts[language] += 1
            inventory.append(
                {
                    "path": relative,
                    "language": language,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                    "lines": content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0),
                }
            )

    source_files = [entry for entry in inventory if entry["language"] == source_language]
    if not source_files:
        raise RouteError(f"NO_SOURCE_FILES:{source_language}")
    inventory.sort(key=lambda entry: str(entry["path"]))
    snapshot_payload = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in inventory)
    snapshot_sha256 = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
    route_id = f"{source_language}-to-{target_language}"
    work_units = [
        {
            "id": f"WU-{index:05d}",
            "route_id": route_id,
            "source_path": entry["path"],
            "source_sha256": entry["sha256"],
            "source_bytes": entry["bytes"],
            "status": "DISCOVERY_REQUIRED",
            "execution_status": "NOT_RUN",
            "required_inputs": ["behavior_cases_json_per_discovered_function"],
            "declared_profile": "typed-pure-function-v1",
            "unsupported_until_discovered": [
                "object_graph",
                "exceptions",
                "async_io",
                "framework",
                "database",
                "concurrency",
            ],
        }
        for index, entry in enumerate(source_files, start=1)
    ]
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.repository-route-plan",
        "status": "PLANNED",
        "repository_ref": safe_ref,
        "snapshot_sha256": snapshot_sha256,
        "snapshot_consistency": "STABLE_READ_ONLY_SCAN",
        "route_id": route_id,
        "source_language": source_language,
        "target_language": target_language,
        "file_count": len(inventory),
        "source_file_count": len(source_files),
        "source_bytes": total_bytes,
        "repository_scale": _repository_scale(len(inventory), total_bytes),
        "repository_limits": {
            "maximum_source_files": _MAX_FILES,
            "maximum_source_bytes": _MAX_SOURCE_BYTES,
            "maximum_bytes_per_file": _MAX_FILE_BYTES,
        },
        "language_counts": language_counts,
        "ignored_symlink_count": ignored_symlink_count,
        "work_units": work_units,
        "execution_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Inventory and work-unit decomposition do not execute source code.",
            "Every discovered function requires an independent behavior-case corpus.",
            "Repository-wide success cannot be inferred from typed-pure-function-v1 evidence.",
        ],
    }
