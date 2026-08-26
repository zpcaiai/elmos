"""Bounded, read-only and symlink-safe repository snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any

from .canonical import canonical_digest, digest_bytes


DEFAULT_EXCLUDES = (
    ".git",
    ".git/**",
    ".venv",
    ".venv/**",
    "node_modules",
    "node_modules/**",
    "**/node_modules",
    "**/node_modules/**",
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__",
    "**/__pycache__/**",
    ".next",
    ".next/**",
    "**/.next",
    "**/.next/**",
)

_SECRET_PATTERNS = (
    ("private-key-marker", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("cloud-access-key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("credential-assignment", re.compile(rb"(?i)\b(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret)\b\s*[:=]\s*[^\s,;]{8,}")),
)


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    max_files: int = 50_000
    max_total_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 16 * 1024 * 1024
    max_path_bytes: int = 4_096


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    path: str
    kind: str
    size: int
    mode: int
    mtime_ns: int
    digest: str
    metadata_digest: str
    text: str | None = None
    secret_fingerprints: tuple[dict[str, Any], ...] = ()

    def manifest(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "path": self.path,
            "kind": self.kind,
            "bytes": self.size,
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "sha256": self.digest,
            "metadataDigest": self.metadata_digest,
            "secretFingerprints": [dict(item) for item in self.secret_fingerprints],
        }
        return value


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    root_label: str
    files: tuple[SnapshotFile, ...]
    digest: str
    total_bytes: int
    symlink_count: int
    excluded_count: int
    stable: bool = True

    def manifest(self) -> dict[str, Any]:
        return {
            "snapshotVersion": "1.0.0",
            "rootLabel": self.root_label,
            "digest": self.digest,
            "fileCount": sum(item.kind == "file" for item in self.files),
            "symlinkCount": self.symlink_count,
            "excludedCount": self.excluded_count,
            "totalBytes": self.total_bytes,
            "stable": self.stable,
            "files": [item.manifest() for item in self.files],
        }

    def text_files(self) -> dict[str, str]:
        return {item.path: item.text for item in self.files if item.kind == "file" and item.text is not None}


def _metadata_digest(kind: str, size: int, mode: int, mtime_ns: int) -> str:
    return canonical_digest({"kind": kind, "size": size, "mode": mode, "mtime_ns": mtime_ns})


def _secret_fingerprints(data: bytes) -> tuple[dict[str, Any], ...]:
    result: dict[tuple[str, str], int] = {}
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(data):
            fingerprint = digest_bytes(b"elmos.legacy-web.secret.v1\0" + kind.encode() + b"\0" + match.group(0))
            result[(kind, fingerprint)] = result.get((kind, fingerprint), 0) + 1
    return tuple(
        {"kind": kind, "fingerprint": digest, "occurrences": count}
        for (kind, digest), count in sorted(result.items())
    )


def _validate_real_directory(path: Path) -> Path:
    absolute = path.absolute()
    if not absolute.is_absolute():
        raise SnapshotError("repository root must be absolute")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise SnapshotError("repository root is not readable") from exc
        if stat.S_ISLNK(info.st_mode):
            raise SnapshotError("repository root ancestry contains a symlink")
    if not absolute.is_dir() or absolute.is_symlink():
        raise SnapshotError("repository root must be a real directory")
    return absolute


def _excluded(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _read_regular_file(path: Path, before: os.stat_result, limit: int) -> bytes:
    if before.st_size > limit:
        raise SnapshotError(f"file exceeds configured limit: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SnapshotError("repository file could not be opened safely") from exc
    try:
        data = bytearray()
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > limit:
                raise SnapshotError("file exceeds configured limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise SnapshotError("repository changed during snapshot")
    return bytes(data)


def capture_repository(
    root: str | os.PathLike[str],
    *,
    limits: SnapshotLimits | None = None,
    exclusions: tuple[str, ...] = DEFAULT_EXCLUDES,
) -> RepositorySnapshot:
    """Capture bytes once; all later analysis must consume this object."""

    limits = limits or SnapshotLimits()
    if limits.max_files < 1 or limits.max_total_bytes < 1 or limits.max_file_bytes < 1:
        raise ValueError("snapshot limits must be positive")
    root_path = _validate_real_directory(Path(root))
    entries: list[SnapshotFile] = []
    total = 0
    symlinks = 0
    excluded_count = 0
    visited_directories: set[tuple[int, int]] = set()

    def walk(directory: Path, relative: str) -> None:
        nonlocal total, symlinks, excluded_count
        directory_info = directory.lstat()
        identity = (directory_info.st_dev, directory_info.st_ino)
        if identity in visited_directories:
            raise SnapshotError("directory identity was visited twice")
        visited_directories.add(identity)
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise SnapshotError("repository directory could not be read") from exc
        for child in children:
            child_relative = f"{relative}/{child.name}" if relative else child.name
            if len(child_relative.encode("utf-8", errors="strict")) > limits.max_path_bytes:
                raise SnapshotError("repository path exceeds configured limit")
            if _excluded(child_relative, exclusions):
                excluded_count += 1
                continue
            if len(entries) >= limits.max_files:
                raise SnapshotError("repository file count exceeds configured limit")
            info = child.stat(follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                symlinks += 1
                target = os.readlink(child.path)
                entries.append(SnapshotFile(
                    path=child_relative,
                    kind="symlink",
                    size=len(target.encode("utf-8")),
                    mode=mode,
                    mtime_ns=info.st_mtime_ns,
                    digest=digest_bytes(target.encode("utf-8")),
                    metadata_digest=_metadata_digest("symlink", len(target.encode("utf-8")), mode, info.st_mtime_ns),
                ))
                continue
            if stat.S_ISDIR(info.st_mode):
                walk(Path(child.path), child_relative)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise SnapshotError("special files are not supported")
            data = _read_regular_file(Path(child.path), info, limits.max_file_bytes)
            total += len(data)
            if total > limits.max_total_bytes:
                raise SnapshotError("repository byte limit exceeded")
            try:
                text = data.decode("utf-8") if b"\x00" not in data else None
            except UnicodeDecodeError:
                text = None
            entries.append(SnapshotFile(
                path=child_relative,
                kind="file",
                size=len(data),
                mode=mode,
                mtime_ns=info.st_mtime_ns,
                digest=digest_bytes(data),
                metadata_digest=_metadata_digest("file", len(data), mode, info.st_mtime_ns),
                text=text,
                secret_fingerprints=_secret_fingerprints(data),
            ))

    walk(root_path, "")
    entries.sort(key=lambda item: item.path)
    manifest_without_digest = {
        "rootLabel": root_path.name or "root",
        "files": [item.manifest() for item in entries],
        "excludedCount": excluded_count,
    }
    return RepositorySnapshot(
        root_label=root_path.name or "root",
        files=tuple(entries),
        digest=canonical_digest(manifest_without_digest),
        total_bytes=total,
        symlink_count=symlinks,
        excluded_count=excluded_count,
    )
