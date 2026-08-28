"""Safe, deterministic, read-only repository snapshots and evidence graphs.

The snapshotter deliberately does not run build hooks, parsers, repository
scripts, or VCS commands.  Files are opened beneath an already-open root file
descriptor with ``O_NOFOLLOW`` where the host supports it.  Metadata is checked
before and after reading so a path race is reported instead of silently
producing evidence for different bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Iterable, Mapping, Sequence
import unicodedata


ENGINE_VERSION = "3.0.0"


class SnapshotError(RuntimeError):
    """Base class for fail-closed snapshot errors."""


class SnapshotLimitError(SnapshotError):
    """A configured repository limit was exceeded."""


class SnapshotRaceError(SnapshotError):
    """A file or directory changed while it was being snapshotted."""


class UnsafeRepositoryPath(SnapshotError):
    """A path escaped the root, traversed a symlink, or was otherwise unsafe."""


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    max_files: int = 50_000
    max_directories: int = 10_000
    max_total_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 16 * 1024 * 1024
    max_depth: int = 64
    max_path_bytes: int = 4_096

    def __post_init__(self) -> None:
        for name in (
            "max_files",
            "max_directories",
            "max_total_bytes",
            "max_file_bytes",
            "max_depth",
            "max_path_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class SnapshotOmission:
    path: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class FileEvidence:
    path: str
    digest: str
    size: int
    mode: int
    language: str | None
    binary: bool
    generated: bool
    vendored: bool
    device: int
    inode: int
    mtime_ns: int
    content: bytes = field(repr=False, compare=False, default=b"")

    @property
    def evidence_id(self) -> str:
        return f"file:sha256:{self.digest}"

    def text(self) -> str:
        if self.binary:
            raise UnicodeError(f"binary file has no source text: {self.path}")
        return self.content.decode("utf-8", errors="strict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "digest": self.digest,
            "size": self.size,
            "mode": self.mode,
            "language": self.language,
            "binary": self.binary,
            "generated": self.generated,
            "vendored": self.vendored,
            "device": self.device,
            "inode": self.inode,
            "mtime_ns": self.mtime_ns,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class RepositoryNode:
    id: str
    kind: str
    name: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "attributes": dict(self.attributes),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class RepositoryEdge:
    source: str
    target: str
    kind: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class RepositoryEvidenceGraph:
    snapshot_id: str
    root_digest: str
    files: tuple[FileEvidence, ...]
    nodes: tuple[RepositoryNode, ...]
    edges: tuple[RepositoryEdge, ...]
    omissions: tuple[SnapshotOmission, ...]
    complete: bool
    provenance: Mapping[str, Any]

    @property
    def declared_scope_complete(self) -> bool:
        """Whether every file admitted by the declared policy was captured."""

        return bool(self.provenance.get("declared_scope_complete", self.complete))

    @property
    def whole_repository_complete(self) -> bool:
        """Whether no path was omitted from the repository as observed."""

        return self.complete

    def file(self, path: str) -> FileEvidence | None:
        normalized = _normalize_relative(path)
        return next((entry for entry in self.files if entry.path == normalized), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_version": "elmos.ai/v3",
            "kind": "RepositoryEvidenceGraph",
            "snapshot_id": self.snapshot_id,
            "root_digest": self.root_digest,
            "complete": self.complete,
            "declared_scope_complete": self.declared_scope_complete,
            "whole_repository_complete": self.whole_repository_complete,
            "files": [item.to_dict() for item in self.files],
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "omissions": [item.to_dict() for item in self.omissions],
            "provenance": dict(self.provenance),
        }

    def shard(self, prefix: str) -> "RepositoryEvidenceGraph":
        normalized = _normalize_relative(prefix).rstrip("/")
        selected = tuple(
            item
            for item in self.files
            if item.path == normalized or item.path.startswith(normalized + "/")
        )
        file_ids = {f"file:{item.path}" for item in selected}
        nodes = tuple(
            node
            for node in self.nodes
            if node.id in file_ids
            or (
                node.kind == "module"
                and (node.name == normalized or normalized.startswith(node.name + "/"))
            )
        )
        node_ids = {node.id for node in nodes}
        edges = tuple(
            edge for edge in self.edges if edge.source in node_ids and edge.target in node_ids
        )
        digest = _canonical_digest([item.to_dict() for item in selected])
        selected_omissions = tuple(
            omission
            for omission in self.omissions
            if omission.path == normalized
            or omission.path.startswith(normalized + "/")
        )
        whole_repository_complete = not selected_omissions
        return RepositoryEvidenceGraph(
            snapshot_id=f"sha256:{digest}",
            root_digest=digest,
            files=selected,
            nodes=nodes,
            edges=edges,
            omissions=selected_omissions,
            complete=whole_repository_complete,
            provenance={
                **self.provenance,
                "parent_snapshot_id": self.snapshot_id,
                "prefix": normalized,
                "declared_scope_complete": True,
                "whole_repository_complete": whole_repository_complete,
            },
        )


_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".swift": "swift",
    ".dart": "dart",
    ".php": "php",
    ".sql": "sql",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}

_BINARY_SUFFIXES = {
    ".a",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".wasm",
    ".webp",
    ".zip",
}

_DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
}

_VENDOR_DIRS = {"third_party", "third-party", "vendor", "vendors"}
_GENERATED_DIRS = {"build", "generated", "gen", "out", "target"}


def detect_language(path: str) -> str | None:
    return _LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower())


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_relative(value: str | os.PathLike[str]) -> str:
    raw = os.fspath(value).replace("\\", "/")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute() or not raw or any(part in {"", ".", ".."} for part in candidate.parts):
        raise UnsafeRepositoryPath(f"unsafe relative path: {raw!r}")
    if "\x00" in raw:
        raise UnsafeRepositoryPath("NUL in repository path")
    return candidate.as_posix()


class _IgnoreMatcher:
    def __init__(self, patterns: Sequence[str]) -> None:
        parsed: list[tuple[str, bool, bool]] = []
        for raw in patterns:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            directory_only = line.endswith("/")
            line = line.strip("/")
            if line:
                parsed.append((line, negated, directory_only))
        self._patterns = tuple(parsed)

    def matches(self, path: str, *, is_dir: bool) -> bool:
        result = False
        name = PurePosixPath(path).name
        for pattern, negated, directory_only in self._patterns:
            if directory_only and not is_dir:
                continue
            matched = (
                fnmatch(path, pattern)
                or fnmatch(name, pattern)
                or ("/" not in pattern and any(fnmatch(part, pattern) for part in path.split("/")))
            )
            if matched:
                result = not negated
        return result


def _load_ignore_patterns(
    root_fd: int,
    additional: Iterable[str],
) -> tuple[tuple[str, ...], tuple[tuple[int, int, int, int, int], str] | None]:
    patterns = list(additional)
    binding: tuple[tuple[int, int, int, int, int], str] | None = None
    try:
        content, metadata = _read_stable_file(root_fd, ".gitignore", 1024 * 1024)
    except FileNotFoundError:
        pass
    else:
        patterns.extend(content.decode("utf-8", errors="replace").splitlines())
        binding = (_file_binding(metadata), hashlib.sha256(content).hexdigest())
    return tuple(patterns), binding


def _is_binary(path: str, content: bytes) -> bool:
    if PurePosixPath(path).suffix.lower() in _BINARY_SUFFIXES:
        return True
    sample = content[:8192]
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    control = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return control / len(sample) > 0.20


def _secure_open(root_fd: int, relative: str) -> int:
    parts = _normalize_relative(relative).split("/")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    current = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise UnsafeRepositoryPath(f"cannot safely open {relative}: {exc}") from exc
    finally:
        os.close(current)


def _secure_open_directory(root_fd: int, relative: str) -> int:
    parts = _normalize_relative(relative).split("/")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | nofollow
    current = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = next_fd
        result = current
        current = -1
        return result
    except OSError as exc:
        raise SnapshotRaceError(
            f"directory binding changed while snapshotting: {relative}"
        ) from exc
    finally:
        if current >= 0:
            os.close(current)


def _read_stable_file(root_fd: int, relative: str, limit: int) -> tuple[bytes, os.stat_result]:
    fd = _secure_open(root_fd, relative)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise UnsafeRepositoryPath(f"not a regular file: {relative}")
        if before.st_size > limit:
            raise SnapshotLimitError(
                f"file exceeds max_file_bytes ({before.st_size} > {limit}): {relative}"
            )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > limit:
            raise SnapshotLimitError(f"file grew beyond max_file_bytes: {relative}")
        after = os.fstat(fd)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or len(content) != after.st_size:
            raise SnapshotRaceError(f"file changed while reading: {relative}")
        return content, after
    finally:
        os.close(fd)


def _read_stable_file_at(
    directory_fd: int,
    name: str,
    relative: str,
    limit: int,
    expected: os.stat_result,
) -> tuple[bytes, os.stat_result]:
    """Read one enumerated file through its already-bound parent directory."""

    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise SnapshotRaceError(f"file binding changed before reading: {relative}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise SnapshotRaceError(f"file type changed before reading: {relative}")
        if _file_binding(expected) != _file_binding(before):
            raise SnapshotRaceError(f"file identity changed before reading: {relative}")
        if before.st_size > limit:
            raise SnapshotLimitError(
                f"file exceeds max_file_bytes ({before.st_size} > {limit}): {relative}"
            )
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > limit:
            raise SnapshotLimitError(f"file grew beyond max_file_bytes: {relative}")
        after = os.fstat(fd)
        if _file_binding(before) != _file_binding(after) or len(content) != after.st_size:
            raise SnapshotRaceError(f"file changed while reading: {relative}")
        return content, after
    finally:
        os.close(fd)


def _file_binding(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


class RepositorySnapshotter:
    """Create byte-bound evidence without executing repository-controlled code."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        limits: SnapshotLimits | None = None,
        ignore_patterns: Sequence[str] = (),
        include_generated: bool = False,
        include_vendor: bool = False,
    ) -> None:
        path = Path(root)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafeRepositoryPath("repository root must not be a symlink")
        if not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeRepositoryPath("repository root must be a directory")
        self.root = path.resolve(strict=True)
        self.limits = limits or SnapshotLimits()
        self.ignore_patterns = tuple(ignore_patterns)
        self.include_generated = include_generated
        self.include_vendor = include_vendor

    def snapshot(self) -> RepositoryEvidenceGraph:
        root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(self.root, root_flags)
        files: list[FileEvidence] = []
        omissions: list[SnapshotOmission] = []
        total_bytes = 0
        directories_seen = 1
        collision_paths: dict[str, str] = {}
        directory_bindings: list[
            tuple[str, int, tuple[int, int, int, int]]
        ] = []
        try:
            root_before = os.fstat(root_fd)
            patterns, ignore_binding = _load_ignore_patterns(
                root_fd, self.ignore_patterns
            )
            matcher = _IgnoreMatcher(patterns)

            def visit(directory_fd: int, relative_dir: str, depth: int) -> None:
                nonlocal directories_seen, total_bytes
                if depth > self.limits.max_depth:
                    raise SnapshotLimitError(
                        f"repository exceeds max_depth at {relative_dir or '.'}"
                    )
                try:
                    entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
                except OSError as exc:
                    raise SnapshotRaceError(
                        f"directory could not be enumerated: {relative_dir or '.'}"
                    ) from exc
                for entry in entries:
                    name = entry.name
                    if not isinstance(name, str) or name in {"", ".", ".."}:
                        raise UnsafeRepositoryPath("repository entry name is unsafe")
                    relative = f"{relative_dir}/{name}" if relative_dir else name
                    _register_path_identity(collision_paths, relative)
                    if len(os.fsencode(relative)) > self.limits.max_path_bytes:
                        raise SnapshotLimitError(
                            f"path exceeds max_path_bytes: {relative}"
                        )
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except FileNotFoundError as exc:
                        raise SnapshotRaceError(f"entry disappeared: {relative}") from exc
                    except OSError as exc:
                        raise SnapshotRaceError(
                            f"entry metadata changed: {relative}"
                        ) from exc
                    if stat.S_ISLNK(metadata.st_mode):
                        detail = (
                            "directory not traversed"
                            if entry.is_dir(follow_symlinks=False)
                            else "file not read"
                        )
                        omissions.append(SnapshotOmission(relative, "symlink", detail))
                        continue
                    if stat.S_ISDIR(metadata.st_mode):
                        if name in _DEFAULT_IGNORED_DIRS or matcher.matches(
                            relative, is_dir=True
                        ):
                            omissions.append(
                                SnapshotOmission(relative, "ignored", "directory")
                            )
                            continue
                        if name.lower() in _VENDOR_DIRS and not self.include_vendor:
                            omissions.append(
                                SnapshotOmission(relative, "vendor", "directory")
                            )
                            continue
                        if (
                            name.lower() in _GENERATED_DIRS
                            and not self.include_generated
                        ):
                            omissions.append(
                                SnapshotOmission(relative, "generated", "directory")
                            )
                            continue
                        if directories_seen >= self.limits.max_directories:
                            raise SnapshotLimitError(
                                "repository exceeds max_directories "
                                f"({self.limits.max_directories})"
                            )
                        try:
                            child_fd = os.open(
                                name,
                                os.O_RDONLY
                                | getattr(os, "O_DIRECTORY", 0)
                                | getattr(os, "O_NOFOLLOW", 0),
                                dir_fd=directory_fd,
                            )
                        except OSError as exc:
                            raise SnapshotRaceError(
                                f"directory binding changed before traversal: {relative}"
                            ) from exc
                        try:
                            child_metadata = os.fstat(child_fd)
                            expected_identity = _stable_identity(metadata)
                            if (
                                not stat.S_ISDIR(child_metadata.st_mode)
                                or _stable_identity(child_metadata)
                                != expected_identity
                            ):
                                raise SnapshotRaceError(
                                    f"directory identity changed before traversal: {relative}"
                                )
                            directories_seen += 1
                            directory_bindings.append(
                                (relative, os.dup(child_fd), expected_identity)
                            )
                            visit(child_fd, relative, depth + 1)
                        finally:
                            os.close(child_fd)
                        continue
                    if not stat.S_ISREG(metadata.st_mode):
                        omissions.append(SnapshotOmission(relative, "special-file", "not a regular file"))
                        continue
                    if matcher.matches(relative, is_dir=False):
                        omissions.append(SnapshotOmission(relative, "ignored", "file"))
                        continue
                    parts_lower = {part.lower() for part in PurePosixPath(relative).parts}
                    vendored = bool(parts_lower & _VENDOR_DIRS)
                    generated = bool(parts_lower & _GENERATED_DIRS) or name.endswith(
                        (".generated.py", ".generated.ts", ".g.cs", ".pb.go")
                    )
                    if vendored and not self.include_vendor:
                        omissions.append(SnapshotOmission(relative, "vendor", "file"))
                        continue
                    if generated and not self.include_generated:
                        omissions.append(SnapshotOmission(relative, "generated", "file"))
                        continue
                    if len(files) >= self.limits.max_files:
                        raise SnapshotLimitError(
                            f"repository exceeds max_files ({self.limits.max_files})"
                        )
                    content, stable = _read_stable_file_at(
                        directory_fd,
                        name,
                        relative,
                        self.limits.max_file_bytes,
                        metadata,
                    )
                    total_bytes += len(content)
                    if total_bytes > self.limits.max_total_bytes:
                        raise SnapshotLimitError(
                            f"repository exceeds max_total_bytes ({self.limits.max_total_bytes})"
                        )
                    files.append(
                        FileEvidence(
                            path=relative,
                            digest=hashlib.sha256(content).hexdigest(),
                            size=len(content),
                            mode=stat.S_IMODE(stable.st_mode),
                            language=detect_language(relative),
                            binary=_is_binary(relative, content),
                            generated=generated,
                            vendored=vendored,
                            device=stable.st_dev,
                            inode=stable.st_ino,
                            mtime_ns=stable.st_mtime_ns,
                            content=content,
                        )
                    )

            visit(root_fd, "", 0)
            for relative, bound_fd, expected_identity in reversed(
                directory_bindings
            ):
                if _stable_identity(os.fstat(bound_fd)) != expected_identity:
                    raise SnapshotRaceError(
                        f"directory changed during snapshot: {relative}"
                    )
                reopened_fd = _secure_open_directory(root_fd, relative)
                try:
                    if _stable_identity(os.fstat(reopened_fd)) != expected_identity:
                        raise SnapshotRaceError(
                            f"directory path binding changed during snapshot: {relative}"
                        )
                finally:
                    os.close(reopened_fd)
            root_after = os.fstat(root_fd)
            if _stable_identity(root_before) != _stable_identity(root_after):
                raise SnapshotRaceError("repository root changed during snapshot")
            if ignore_binding is not None:
                ignore_content, ignore_metadata = _read_stable_file(
                    root_fd, ".gitignore", 1024 * 1024
                )
                if (
                    _file_binding(ignore_metadata) != ignore_binding[0]
                    or hashlib.sha256(ignore_content).hexdigest()
                    != ignore_binding[1]
                ):
                    raise SnapshotRaceError(
                        ".gitignore changed while its policy was in use"
                    )
            root_reopened = os.open(self.root, root_flags)
            try:
                if _stable_identity(os.fstat(root_reopened)) != _stable_identity(
                    root_before
                ):
                    raise SnapshotRaceError(
                        "repository root path binding changed during snapshot"
                    )
            finally:
                os.close(root_reopened)
        finally:
            for _, bound_fd, _ in directory_bindings:
                os.close(bound_fd)
            os.close(root_fd)

        files.sort(key=lambda item: item.path)
        omissions.sort(key=lambda item: (item.path, item.reason, item.detail))
        root_digest = _canonical_digest(
            [
                {
                    "path": item.path,
                    "digest": item.digest,
                    "size": item.size,
                    "mode": item.mode,
                    "binary": item.binary,
                    "generated": item.generated,
                    "vendored": item.vendored,
                }
                for item in files
            ]
        )
        nodes, edges = _build_graph(files)
        snapshot_id = f"sha256:{_canonical_digest({'root': root_digest, 'version': ENGINE_VERSION})}"
        return RepositoryEvidenceGraph(
            snapshot_id=snapshot_id,
            root_digest=root_digest,
            files=tuple(files),
            nodes=nodes,
            edges=edges,
            omissions=tuple(omissions),
            complete=not omissions,
            provenance={
                "snapshotter": "elmos-proof-harness",
                "version": ENGINE_VERSION,
                "root": str(self.root),
                "follow_symlinks": False,
                "executed_repository_code": False,
                "declared_scope_complete": True,
                "whole_repository_complete": not omissions,
                "root_identity": {
                    "device": root_before.st_dev,
                    "inode": root_before.st_ino,
                    "mtime_ns": root_before.st_mtime_ns,
                    "ctime_ns": root_before.st_ctime_ns,
                },
                "limits": {
                    name: getattr(self.limits, name)
                    for name in SnapshotLimits.__dataclass_fields__
                },
            },
        )


def _stable_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _register_path_identity(seen: dict[str, str], path: str) -> None:
    normalized = unicodedata.normalize("NFC", path).casefold()
    existing = seen.get(normalized)
    if existing is not None and existing != path:
        raise UnsafeRepositoryPath(
            f"repository contains a casefold/NFC path collision: {existing!r} and {path!r}"
        )
    seen[normalized] = path


def _build_graph(
    files: Sequence[FileEvidence],
) -> tuple[tuple[RepositoryNode, ...], tuple[RepositoryEdge, ...]]:
    nodes: dict[str, RepositoryNode] = {}
    edges: set[tuple[str, str, str, tuple[str, ...]]] = set()
    nodes["module:."] = RepositoryNode("module:.", "module", ".")
    for item in files:
        file_id = f"file:{item.path}"
        nodes[file_id] = RepositoryNode(
            id=file_id,
            kind="file",
            name=item.path,
            attributes={
                "digest": item.digest,
                "size": item.size,
                "language": item.language,
                "binary": item.binary,
            },
            evidence_refs=(item.evidence_id,),
        )
        parent = PurePosixPath(item.path).parent
        parent_name = "." if parent.as_posix() == "." else parent.as_posix()
        accumulated: list[str] = []
        previous = "module:."
        for part in parent.parts:
            if part == ".":
                continue
            accumulated.append(part)
            module_name = "/".join(accumulated)
            module_id = f"module:{module_name}"
            nodes.setdefault(module_id, RepositoryNode(module_id, "module", module_name))
            edges.add((previous, module_id, "contains", ()))
            previous = module_id
        parent_id = f"module:{parent_name}"
        edges.add((parent_id, file_id, "contains", (item.evidence_id,)))
    ordered_nodes = tuple(nodes[key] for key in sorted(nodes))
    ordered_edges = tuple(
        RepositoryEdge(source, target, kind, evidence_refs)
        for source, target, kind, evidence_refs in sorted(edges)
    )
    return ordered_nodes, ordered_edges


__all__ = [
    "ENGINE_VERSION",
    "FileEvidence",
    "RepositoryEdge",
    "RepositoryEvidenceGraph",
    "RepositoryNode",
    "RepositorySnapshotter",
    "SnapshotError",
    "SnapshotLimitError",
    "SnapshotLimits",
    "SnapshotOmission",
    "SnapshotRaceError",
    "UnsafeRepositoryPath",
    "detect_language",
]
