from __future__ import annotations

import hashlib
import json
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
    ".cjs": "javascript",
    ".js": "javascript",
    ".mjs": "javascript",
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
    ".php": "php",
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


def _javascript_descriptor_json(content: bytes) -> dict[str, Any]:
    """Parse a package descriptor without accepting duplicate ``type`` keys."""

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_AMBIGUOUS") from error
    if not isinstance(value, dict):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_AMBIGUOUS")
    return value


def javascript_esm_descriptor(source: Path, repository_root: Path | None = None) -> dict[str, Any] | None:
    """Return the exact Node ESM descriptor required by a plain ``.js`` file.

    ``.mjs`` is intrinsically ESM.  A ``.js`` input is only accepted when its
    nearest regular, in-scope package descriptor explicitly establishes the
    Node ESM interpretation.  The descriptor is content addressed here so all
    later repository stages can bind the same semantic input.
    """

    suffix = source.suffix.lower()
    if suffix == ".mjs":
        return None
    if suffix == ".cjs":
        raise RouteError("JAVASCRIPT_CJS_SOURCE_BLOCKED")
    if suffix != ".js":
        raise RouteError("JAVASCRIPT_SOURCE_EXTENSION_UNSUPPORTED")
    try:
        resolved_source = source.resolve(strict=True)
        if source.is_symlink() or not resolved_source.is_file():
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE")
        root = repository_root.resolve(strict=True) if repository_root is not None else None
    except OSError as error:
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE") from error
    if root is not None and (
        repository_root is None or repository_root.is_symlink() or not resolved_source.is_relative_to(root)
    ):
        raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE")

    cursor = resolved_source.parent
    while True:
        if root is not None and not cursor.is_relative_to(root):
            break
        descriptor = cursor / "package.json"
        try:
            metadata = descriptor.lstat()
        except FileNotFoundError:
            metadata = None
        except OSError as error:
            raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE") from error
        if metadata is not None:
            if descriptor.is_symlink() or not descriptor.is_file():
                raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE")
            before = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns)
            if metadata.st_size > _MAX_FILE_BYTES:
                raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_TOO_LARGE")
            try:
                content = descriptor.read_bytes()
                after_metadata = descriptor.lstat()
            except OSError as error:
                raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_PATH_UNSAFE") from error
            after = (
                after_metadata.st_dev,
                after_metadata.st_ino,
                after_metadata.st_size,
                after_metadata.st_mtime_ns,
                after_metadata.st_ctime_ns,
            )
            if before != after or len(content) != metadata.st_size:
                raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_READ")
            package = _javascript_descriptor_json(content)
            if package.get("type") != "module":
                raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_TYPE_MODULE_REQUIRED")
            path = descriptor.relative_to(root).as_posix() if root is not None else str(descriptor)
            return {
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "type": "module",
            }
        if cursor == root or cursor.parent == cursor:
            break
        cursor = cursor.parent
    raise RouteError("JAVASCRIPT_ESM_DESCRIPTOR_REQUIRED")


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
    javascript_esm_descriptors: list[dict[str, Any]] = []
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
                raise RouteError("REPOSITORY_SOURCE_SYMLINK_FORBIDDEN")
            safe_directories.append(directory)
        directories[:] = safe_directories
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                if _EXTENSIONS.get(path.suffix.lower()) is not None:
                    raise RouteError("REPOSITORY_SOURCE_SYMLINK_FORBIDDEN")
                ignored_symlink_count += 1
                continue
            language = _EXTENSIONS.get(path.suffix.lower())
            if language is None:
                continue
            relative = path.relative_to(root).as_posix()
            if len(relative) > 1_024:
                raise RouteError("REPOSITORY_SOURCE_PATH_TOO_LONG")
            if any(ord(character) < 32 or ord(character) == 127 for character in relative):
                raise RouteError("REPOSITORY_SOURCE_PATH_CONTROL_CHARACTER_FORBIDDEN")
            content = _read_stable(path)
            total_bytes += len(content)
            if len(inventory) >= _MAX_FILES:
                raise RouteError("REPOSITORY_FILE_LIMIT_EXCEEDED")
            if total_bytes > _MAX_SOURCE_BYTES:
                raise RouteError("REPOSITORY_SOURCE_BYTES_LIMIT_EXCEEDED")
            language_counts[language] += 1
            entry = {
                "path": relative,
                "language": language,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "lines": content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0),
            }
            if language == "javascript":
                descriptor = javascript_esm_descriptor(path, root)
                if descriptor is not None:
                    entry["javascript_esm_descriptor"] = descriptor
                    javascript_esm_descriptors.append({"source_path": relative, **descriptor})
            inventory.append(entry)

    source_files = [entry for entry in inventory if entry["language"] == source_language]
    if not source_files:
        raise RouteError(f"NO_SOURCE_FILES:{source_language}")
    inventory.sort(key=lambda entry: str(entry["path"]))
    snapshot_payload = "\n".join(
        [f"{entry['path']}:{entry['sha256']}" for entry in inventory]
        + [
            f"descriptor:{entry['source_path']}:{entry['path']}:{entry['sha256']}:{entry['bytes']}"
            for entry in javascript_esm_descriptors
        ]
    )
    snapshot_sha256 = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
    route_id = f"{source_language}-to-{target_language}"
    work_units = [
        {
            "id": f"WU-{index:05d}",
            "route_id": route_id,
            "source_path": entry["path"],
            "source_sha256": entry["sha256"],
            "source_bytes": entry["bytes"],
            **(
                {"javascript_esm_descriptor": entry["javascript_esm_descriptor"]}
                if "javascript_esm_descriptor" in entry
                else {}
            ),
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
        "javascript_esm_descriptors": javascript_esm_descriptors,
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
