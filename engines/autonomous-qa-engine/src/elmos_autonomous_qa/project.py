"""Bounded, read-only project snapshot discovery.

Repository contents are untrusted input.  Discovery never follows symlinks,
executes hooks, resolves dependencies, or invokes build tools.  The resulting
snapshot is deterministic for the same bytes and policy version.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

from .canonical import normalize_relative_path, path_collision_key
from .contracts import ContractError, digest_json


DEFAULT_EXCLUDED_DIRS: Final = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
    }
)
MAX_SNAPSHOT_FILES: Final = 50_000
MAX_SNAPSHOT_TOTAL_BYTES: Final = 512 * 1024 * 1024
MAX_SNAPSHOT_SINGLE_FILE_BYTES: Final = 32 * 1024 * 1024
MAX_SNAPSHOT_ENTRIES: Final = 100_000
MAX_SNAPSHOT_DIRECTORIES: Final = 20_000
MAX_SNAPSHOT_DIAGNOSTICS: Final = 20_000
MAX_SNAPSHOT_DEPTH: Final = 64
SENSITIVE_NAMES: Final = frozenset(
    {".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials", "credentials.json"}
)
LANGUAGE_EXTENSIONS: Final[dict[str, str]] = {
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".py": "Python",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C/C++",
    ".cc": "C++",
    ".cpp": "C++",
    ".php": "PHP",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".m": "Objective-C",
    ".mm": "Objective-C++",
    ".swift": "Swift",
    ".dart": "Dart",
    ".sql": "SQL",
}
FRAMEWORK_MARKERS: Final[dict[str, tuple[str, ...]]] = {
    "Maven": ("pom.xml",),
    "Gradle": ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    "Python": ("pyproject.toml", "setup.py", "requirements.txt"),
    ".NET": ("global.json",),
    "Go modules": ("go.mod",),
    "Cargo": ("Cargo.toml",),
    "Node": ("package.json",),
    "Flutter": ("pubspec.yaml",),
    "SwiftPM": ("Package.swift",),
    "CMake": ("CMakeLists.txt",),
}


@dataclass(frozen=True)
class SnapshotPolicy:
    version: str = "autonomous-qa-snapshot-v1"
    max_files: int = MAX_SNAPSHOT_FILES
    max_total_bytes: int = MAX_SNAPSHOT_TOTAL_BYTES
    max_single_file_bytes: int = MAX_SNAPSHOT_SINGLE_FILE_BYTES
    max_entries: int = MAX_SNAPSHOT_ENTRIES
    max_directories: int = MAX_SNAPSHOT_DIRECTORIES
    max_diagnostics: int = MAX_SNAPSHOT_DIAGNOSTICS
    max_depth: int = MAX_SNAPSHOT_DEPTH
    excluded_dirs: frozenset[str] = DEFAULT_EXCLUDED_DIRS

    def __post_init__(self) -> None:
        numeric_limits = (
            self.max_files,
            self.max_total_bytes,
            self.max_single_file_bytes,
            self.max_entries,
            self.max_directories,
            self.max_diagnostics,
            self.max_depth,
        )
        if any(type(value) is not int or value < 1 for value in numeric_limits):
            raise ContractError("snapshot limits must be positive")
        maximum_limits = (
            MAX_SNAPSHOT_FILES,
            MAX_SNAPSHOT_TOTAL_BYTES,
            MAX_SNAPSHOT_SINGLE_FILE_BYTES,
            MAX_SNAPSHOT_ENTRIES,
            MAX_SNAPSHOT_DIRECTORIES,
            MAX_SNAPSHOT_DIAGNOSTICS,
            MAX_SNAPSHOT_DEPTH,
        )
        if any(
            value > maximum
            for value, maximum in zip(numeric_limits, maximum_limits, strict=True)
        ):
            raise ContractError("snapshot limits may be tightened but not broadened")
        if self.version != "autonomous-qa-snapshot-v1":
            raise ContractError("snapshot policy version is repository controlled")
        if (
            not isinstance(self.excluded_dirs, frozenset)
            or self.excluded_dirs != DEFAULT_EXCLUDED_DIRS
        ):
            raise ContractError("snapshot exclusions are repository controlled")


def _open_flags(*, directory: bool) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ContractError("secure snapshot discovery requires O_NOFOLLOW")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if directory_flag is None:
            raise ContractError("secure snapshot discovery requires O_DIRECTORY")
        flags |= directory_flag
    else:
        flags |= getattr(os, "O_NONBLOCK", 0)
    return flags


def _identity(value: os.stat_result, *, content: bool) -> tuple[int, ...]:
    identity = (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
    )
    if not content:
        return identity
    return (
        *identity,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _snapshot_regular_file(
    directory_fd: int,
    name: str,
    relative: str,
    listed: os.stat_result,
    *,
    max_bytes: int,
) -> tuple[int, str | None]:
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            _open_flags(directory=False),
            dir_fd=directory_fd,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError(f"project file changed type during snapshot: {relative}")
        if _identity(listed, content=True) != _identity(before, content=True):
            raise ContractError(f"project file changed before snapshot read: {relative}")
        if before.st_size > max_bytes:
            after = os.fstat(descriptor)
            if _identity(before, content=True) != _identity(after, content=True):
                raise ContractError(f"project file changed during snapshot: {relative}")
            return before.st_size, None

        digest = hashlib.sha256()
        observed = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed += len(chunk)
            if observed > max_bytes:
                raise ContractError(f"project file exceeded snapshot limit while read: {relative}")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            _identity(before, content=True) != _identity(after, content=True)
            or observed != before.st_size
        ):
            raise ContractError(f"project file changed during snapshot read: {relative}")
        return before.st_size, "sha256:" + digest.hexdigest()
    except OSError as exc:
        raise ContractError(f"cannot safely read project file: {relative}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _kind(relative: str) -> str:
    lowered = relative.casefold()
    name = PurePosixPath(relative).name.casefold()
    if "requirement" in lowered or name in {"readme.md", "agents.md"}:
        return "requirement"
    if name.endswith(("openapi.yaml", "openapi.yml", "openapi.json")) or "swagger" in name:
        return "api_schema"
    if name.endswith(".sql") or "migration" in lowered:
        return "database_schema"
    if "/test" in "/" + lowered or name.startswith("test_") or ".spec." in name or ".test." in name:
        return "test"
    if "/.github/workflows/" in "/" + lowered or name in {"jenkinsfile", ".gitlab-ci.yml"}:
        return "ci"
    if name in {"dockerfile", "docker-compose.yml", "compose.yml"} or "deploy" in lowered:
        return "deployment"
    if name.endswith((".java", ".kt", ".py", ".cs", ".go", ".rs", ".c", ".cpp", ".php", ".js", ".ts", ".swift", ".dart")):
        return "code"
    return "other"


def build_project_snapshot(
    root: Path,
    *,
    required_paths: tuple[str, ...] = (),
    policy: SnapshotPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or SnapshotPolicy()
    try:
        required = {normalize_relative_path(item) for item in required_paths}
    except (TypeError, ValueError) as exc:
        raise ContractError("required path is unsafe") from exc
    root = Path(os.path.abspath(root))
    if root.is_symlink():
        raise ContractError("project root may not be a symlink")
    root_descriptor = -1
    try:
        root_descriptor = os.open(root, _open_flags(directory=True))
        root_metadata = os.fstat(root_descriptor)
    except OSError as exc:
        if root_descriptor >= 0:
            os.close(root_descriptor)
        raise ContractError(f"project root must be a real directory: {exc}") from exc
    if not stat.S_ISDIR(root_metadata.st_mode):
        os.close(root_descriptor)
        raise ContractError("project root must be a directory")
    files: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    casefold_paths: dict[str, str] = {}
    total_bytes = 0
    entry_count = 0
    regular_file_count = 0
    directory_count = 1
    inventory_omissions = 0
    language_counts: dict[str, int] = {}
    marker_names: set[str] = set()

    # Each frame retains its directory descriptor until every child has been
    # opened relative to it.  This prevents a renamed or symlink-swapped parent
    # from redirecting traversal after enumeration.
    frames: list[dict[str, Any]] = [
        {
            "fd": root_descriptor,
            "parts": (),
            "directories": None,
            "index": 0,
            "directory_identity": None,
            "entry_identities": None,
        }
    ]
    root_descriptor = -1

    def add_diagnostic(value: str) -> None:
        if len(diagnostics) >= policy.max_diagnostics:
            raise ContractError("project snapshot exceeds diagnostic limit")
        diagnostics.append(value)

    try:
        while frames:
            frame = frames[-1]
            directory_fd = int(frame["fd"])
            parts = tuple(frame["parts"])
            if frame["directories"] is None:
                try:
                    directory_before = os.fstat(directory_fd)
                    if not stat.S_ISDIR(directory_before.st_mode):
                        raise ContractError(
                            "project directory changed type during enumeration"
                        )
                    with os.scandir(directory_fd) as entries:
                        names: list[str] = []
                        for entry in entries:
                            # Bound allocation while iterating.  Checking only
                            # after ``sorted(...)`` would allow one hostile
                            # directory to consume unbounded memory first.
                            entry_count += 1
                            if entry_count > policy.max_entries:
                                raise ContractError("project snapshot exceeds entry limit")
                            names.append(entry.name)
                        names.sort()
                except OSError as exc:
                    relative_directory = PurePosixPath(*parts).as_posix() if parts else "."
                    raise ContractError(
                        f"cannot safely enumerate project directory: {relative_directory}: {exc}"
                    ) from exc

                directories: list[tuple[str, os.stat_result]] = []
                entry_identities: dict[str, tuple[int, ...]] = {}
                for filename in names:
                    raw_relative = PurePosixPath(*parts, filename).as_posix()
                    try:
                        relative = normalize_relative_path(raw_relative)
                    except (TypeError, ValueError) as exc:
                        raise ContractError(
                            f"project entry has a non-portable path: {raw_relative!r}"
                        ) from exc
                    try:
                        listed = os.stat(
                            filename,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise ContractError(
                            f"project entry changed during enumeration: {relative}: {exc}"
                        ) from exc
                    entry_identities[filename] = _identity(listed, content=True)
                    if stat.S_ISLNK(listed.st_mode):
                        inventory_omissions += 1
                        add_diagnostic(f"SYMLINK_FILE_SKIPPED:{relative}")
                        continue
                    if stat.S_ISDIR(listed.st_mode):
                        if filename not in policy.excluded_dirs:
                            if len(parts) + 1 > policy.max_depth:
                                raise ContractError("project snapshot exceeds directory depth limit")
                            directory_count += 1
                            if directory_count > policy.max_directories:
                                raise ContractError("project snapshot exceeds directory limit")
                            directories.append((filename, listed))
                        continue
                    if not stat.S_ISREG(listed.st_mode):
                        inventory_omissions += 1
                        add_diagnostic(f"SPECIAL_FILE_SKIPPED:{relative}")
                        continue
                    regular_file_count += 1
                    if regular_file_count > policy.max_files:
                        raise ContractError("project snapshot exceeds file-count limit")

                    folded = path_collision_key(relative)
                    collision = casefold_paths.get(folded)
                    if collision is not None and collision != relative:
                        raise ContractError(
                            f"case-colliding project paths: {collision} and {relative}"
                        )
                    casefold_paths[folded] = relative
                    size, digest = _snapshot_regular_file(
                        directory_fd,
                        filename,
                        relative,
                        listed,
                        max_bytes=policy.max_single_file_bytes,
                    )
                    if digest is None:
                        inventory_omissions += 1
                        add_diagnostic(f"OVERSIZED_FILE_SKIPPED:{relative}:{size}")
                        continue
                    total_bytes += size
                    if total_bytes > policy.max_total_bytes:
                        raise ContractError("project snapshot exceeds total byte limit")
                    suffix = PurePosixPath(filename).suffix.casefold()
                    language = LANGUAGE_EXTENSIONS.get(suffix)
                    if language:
                        language_counts[language] = language_counts.get(language, 0) + 1
                    marker_names.add(filename)
                    sensitive = filename.casefold() in SENSITIVE_NAMES or suffix in {
                        ".pem",
                        ".key",
                        ".p12",
                        ".pfx",
                    }
                    if sensitive:
                        add_diagnostic(
                            f"SENSITIVE_CONTENT_HASHED_NOT_EXPOSED:{relative}"
                        )
                    files.append(
                        {
                            "path": relative,
                            "kind": _kind(relative),
                            "size_bytes": size,
                            "sha256": digest,
                            "required": relative in required,
                            "sensitive_content_not_exposed": sensitive,
                        }
                    )
                frame["directories"] = directories
                frame["directory_identity"] = _identity(
                    directory_before, content=True
                )
                frame["entry_identities"] = entry_identities

            directories = frame["directories"]
            index = int(frame["index"])
            if index >= len(directories):
                relative_directory = (
                    PurePosixPath(*parts).as_posix() if parts else "."
                )
                try:
                    with os.scandir(directory_fd) as entries:
                        final_names: list[str] = []
                        for entry in entries:
                            if len(final_names) >= policy.max_entries:
                                raise ContractError(
                                    "project snapshot exceeds entry limit during stability check"
                                )
                            final_names.append(entry.name)
                        final_names.sort()
                    final_identities = {
                        filename: _identity(
                            os.stat(
                                filename,
                                dir_fd=directory_fd,
                                follow_symlinks=False,
                            ),
                            content=True,
                        )
                        for filename in final_names
                    }
                    directory_after = os.fstat(directory_fd)
                except OSError as exc:
                    raise ContractError(
                        "cannot verify stable project directory: "
                        f"{relative_directory}: {exc}"
                    ) from exc
                if (
                    final_identities != frame["entry_identities"]
                    or _identity(directory_after, content=True)
                    != frame["directory_identity"]
                ):
                    raise ContractError(
                        "project directory changed during snapshot: "
                        f"{relative_directory}"
                    )
                os.close(directory_fd)
                frames.pop()
                continue
            dirname, listed = directories[index]
            frame["index"] = index + 1
            relative = PurePosixPath(*parts, dirname).as_posix()
            child_descriptor = -1
            try:
                child_descriptor = os.open(
                    dirname,
                    _open_flags(directory=True),
                    dir_fd=directory_fd,
                )
                opened = os.fstat(child_descriptor)
                if not stat.S_ISDIR(opened.st_mode):
                    raise ContractError(
                        f"project directory changed type during snapshot: {relative}"
                    )
                if _identity(listed, content=False) != _identity(opened, content=False):
                    raise ContractError(
                        f"project directory changed before snapshot traversal: {relative}"
                    )
            except OSError as exc:
                if child_descriptor >= 0:
                    os.close(child_descriptor)
                raise ContractError(
                    f"cannot safely traverse project directory: {relative}: {exc}"
                ) from exc
            except ContractError:
                if child_descriptor >= 0:
                    os.close(child_descriptor)
                raise
            frames.append(
                {
                    "fd": child_descriptor,
                    "parts": (*parts, dirname),
                    "directories": None,
                    "index": 0,
                    "directory_identity": None,
                    "entry_identities": None,
                }
            )
    finally:
        for frame in reversed(frames):
            try:
                os.close(int(frame["fd"]))
            except OSError:
                pass
        if root_descriptor >= 0:
            os.close(root_descriptor)

    try:
        root_after = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise ContractError(f"project root changed during snapshot: {exc}") from exc
    if (
        not stat.S_ISDIR(root_after.st_mode)
        or _identity(root_metadata, content=False)
        != _identity(root_after, content=False)
    ):
        raise ContractError("project root changed identity during snapshot")

    present = {item["path"] for item in files}
    missing_required = sorted(required - present)
    for item in missing_required:
        add_diagnostic(f"REQUIRED_SOURCE_MISSING:{item}")
    frameworks = sorted(
        framework
        for framework, markers in FRAMEWORK_MARKERS.items()
        if set(markers) & marker_names
    )
    stable = {
        "policy_version": policy.version,
        "effective_policy": {
            "max_files": policy.max_files,
            "max_total_bytes": policy.max_total_bytes,
            "max_single_file_bytes": policy.max_single_file_bytes,
            "max_entries": policy.max_entries,
            "max_directories": policy.max_directories,
            "max_diagnostics": policy.max_diagnostics,
            "max_depth": policy.max_depth,
            "excluded_dirs": sorted(policy.excluded_dirs),
        },
        "files": files,
        "technology_profile": {
            "languages": sorted(language_counts),
            "language_file_counts": dict(sorted(language_counts.items())),
            "frameworks": frameworks,
        },
        "diagnostics": diagnostics,
        "required_complete": not missing_required,
        "inventory_complete": inventory_omissions == 0,
        "inventory_omission_count": inventory_omissions,
        "complete": not missing_required and inventory_omissions == 0,
    }
    return {
        "schema_version": "elmos.autonomous-qa.project-snapshot.v1",
        "snapshot_id": "snapshot-" + digest_json(stable)[7:39],
        **stable,
    }
