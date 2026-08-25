"""Symlink-safe, bounded, read-only repository snapshot capture.

Traversal and reads are descriptor-relative and use ``O_NOFOLLOW``.  Regular
file bytes are read exactly once, after which analysis consumes the immutable
snapshot rather than reopening repository paths.  No repository content is
imported, evaluated, executed, or passed to a child process.
"""

from __future__ import annotations

from collections import Counter
import fnmatch
import os
from pathlib import Path
import re
import stat
from typing import Final

from .canonical import canonical_digest, digest_bytes
from .contracts import (
    EntryKind,
    RepositorySnapshot,
    Result,
    SecretFingerprint,
    SnapshotEntry,
    SnapshotRequest,
    SnapshotResult,
)


_READ_CHUNK: Final = 64 * 1024
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class SnapshotError(RuntimeError):
    """Base class for safe, expected snapshot failures."""

    code = "SNAPSHOT_ERROR"


class SnapshotLimitExceeded(SnapshotError):
    code = "SNAPSHOT_LIMIT_EXCEEDED"


class SnapshotChanged(SnapshotError):
    code = "SNAPSHOT_CHANGED_DURING_READ"


class UnsafeFilesystemEntry(SnapshotError):
    code = "UNSAFE_FILESYSTEM_ENTRY"


class SnapshotUnsupported(SnapshotError):
    code = "SNAPSHOT_PLATFORM_UNSUPPORTED"


# The captured value is never returned by the detector.  Findings contain only
# a category, a domain-separated digest, and an occurrence count.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes], int], ...] = (
    (
        "aws-access-key",
        re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        0,
    ),
    (
        "github-token",
        re.compile(
            rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{20,255})\b"
        ),
        0,
    ),
    (
        "private-key-marker",
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        0,
    ),
    (
        "credential-assignment",
        re.compile(
            rb"(?im)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|"
            rb"client[_-]?secret|password|passwd|secret)\b\s*[:=]\s*"
            rb"[\"']?([^\s\"'`,;]{8,512})"
        ),
        1,
    ),
)


def _stable_stat(info: os.stat_result) -> tuple[int, ...]:
    """Metadata used for before/after stability checks (intentionally no atime)."""

    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _entry_metadata_digest(
    *, kind: EntryKind, size: int, mode: int, mtime_ns: int
) -> str:
    # Device/inode/uid/ctime are stability controls, not portable content
    # identity, and therefore stay out of the deterministic manifest.
    return canonical_digest(
        {
            "kind": kind.value,
            "size": size,
            "mode": mode,
            "mtime_ns": mtime_ns,
        }
    )


def _secret_fingerprints(data: bytes, *, maximum: int) -> tuple[SecretFingerprint, ...]:
    if maximum == 0:
        return ()
    findings: Counter[tuple[str, str]] = Counter()
    for kind, pattern, group in _SECRET_PATTERNS:
        for match in pattern.finditer(data):
            secret = match.group(group)
            # Domain separation prevents a file digest and a secret fingerprint
            # from being interpreted as the same kind of evidence.
            fingerprint = digest_bytes(
                b"elmos.project-intelligence.secret-fingerprint.v1\0"
                + kind.encode("ascii")
                + b"\0"
                + secret
            )
            findings[(kind, fingerprint)] += 1
            if len(findings) > maximum:
                raise SnapshotLimitExceeded(
                    "secret fingerprint count exceeds the configured per-file limit"
                )
    return tuple(
        SecretFingerprint(kind=kind, fingerprint=fingerprint, occurrences=count)
        for (kind, fingerprint), count in sorted(findings.items())
    )


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None


class RepositorySnapshotter:
    """Capture immutable repository files without following symlinks."""

    def __init__(self) -> None:
        self._entries: list[SnapshotEntry] = []
        self._total_bytes = 0
        self._observed_entries = 0
        self._request: SnapshotRequest | None = None
        self._visited_directories: set[tuple[int, int]] = set()

    def capture(self, request: SnapshotRequest) -> SnapshotResult:
        """Return a typed success or a fail-closed error with no partial snapshot."""

        if not isinstance(request, SnapshotRequest):
            return Result.failure(
                code="INVALID_SNAPSHOT_REQUEST",
                message="request must be a validated SnapshotRequest",
            )
        try:
            return Result.success(self.capture_or_raise(request))
        except SnapshotError as exc:
            return Result.failure(code=exc.code, message=str(exc))
        except OSError as exc:
            return Result.failure(
                code="SNAPSHOT_IO_ERROR",
                message="repository snapshot failed during a filesystem operation",
                details={"errno": exc.errno if exc.errno is not None else -1},
            )
        except Exception:
            # Unexpected errors remain non-success and do not expose paths or
            # repository-derived exception text to an API boundary.
            return Result.failure(
                code="SNAPSHOT_INTERNAL_ERROR",
                message="repository snapshot failed closed",
            )

    def capture_or_raise(self, request: SnapshotRequest) -> RepositorySnapshot:
        """Capture a snapshot, raising a typed error instead of returning partial data."""

        self._ensure_platform_support()
        self._entries = []
        self._total_bytes = 0
        self._observed_entries = 0
        self._visited_directories = set()
        self._request = request

        root = Path(str(request.root)).absolute()
        root_lstat = os.lstat(root)
        if stat.S_ISLNK(root_lstat.st_mode):
            raise UnsafeFilesystemEntry("repository root cannot be a symlink")
        if not stat.S_ISDIR(root_lstat.st_mode):
            raise UnsafeFilesystemEntry("repository root must be a directory")

        root_fd = os.open(
            root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            root_fstat = os.fstat(root_fd)
            if not _same_object(root_lstat, root_fstat):
                raise SnapshotChanged("repository root changed before traversal")
            self._walk_directory(
                directory_fd=root_fd,
                relative_directory="",
                depth=0,
                before=root_fstat,
            )
            root_after_fd = os.fstat(root_fd)
            root_after_path = os.lstat(root)
            if (
                _stable_stat(root_fstat) != _stable_stat(root_after_fd)
                or _stable_stat(root_lstat) != _stable_stat(root_after_path)
                or not _same_object(root_after_fd, root_after_path)
            ):
                raise SnapshotChanged("repository root changed during traversal")
        finally:
            os.close(root_fd)

        entries = tuple(sorted(self._entries, key=lambda entry: entry.path))
        root_label = root.name or "root"
        provisional = RepositorySnapshot(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            run_id=request.run_id,
            root_label=root_label,
            entries=entries,
            file_count=sum(entry.kind is EntryKind.FILE for entry in entries),
            symlink_count=sum(entry.kind is EntryKind.SYMLINK for entry in entries),
            total_bytes=self._total_bytes,
            exclusions=request.exclusions,
            snapshot_digest=_ZERO_DIGEST,
        )
        snapshot_digest = canonical_digest(provisional.digest_manifest())
        return RepositorySnapshot(
            tenant_id=provisional.tenant_id,
            project_id=provisional.project_id,
            run_id=provisional.run_id,
            root_label=provisional.root_label,
            entries=provisional.entries,
            file_count=provisional.file_count,
            symlink_count=provisional.symlink_count,
            total_bytes=provisional.total_bytes,
            exclusions=provisional.exclusions,
            snapshot_digest=snapshot_digest,
        )

    @staticmethod
    def _ensure_platform_support() -> None:
        required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
        if any(not hasattr(os, flag) for flag in required_flags):
            raise SnapshotUnsupported(
                "platform lacks descriptor flags required for symlink-safe traversal"
            )
        if os.stat not in os.supports_dir_fd or os.open not in os.supports_dir_fd:
            raise SnapshotUnsupported(
                "platform lacks descriptor-relative filesystem operations"
            )
        if os.scandir not in os.supports_fd:
            raise SnapshotUnsupported(
                "platform lacks descriptor-based directory iteration"
            )

    @property
    def _limits(self):
        assert self._request is not None
        return self._request.limits

    def _is_excluded(self, relative_path: str) -> bool:
        assert self._request is not None
        return any(
            fnmatch.fnmatchcase(relative_path, pattern)
            for pattern in self._request.exclusions
        )

    def _validate_relative_path(self, relative_path: str) -> None:
        try:
            encoded = relative_path.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise UnsafeFilesystemEntry(
                "repository contains a path that is not valid UTF-8"
            ) from exc
        if len(encoded) > self._limits.max_path_bytes:
            raise SnapshotLimitExceeded(
                "repository path exceeds the configured byte limit"
            )

    def _reserve_entry(self) -> None:
        self._observed_entries += 1
        if self._observed_entries > self._limits.max_files:
            raise SnapshotLimitExceeded(
                "repository entry count exceeds the configured file limit"
            )

    def _walk_directory(
        self,
        *,
        directory_fd: int,
        relative_directory: str,
        depth: int,
        before: os.stat_result,
    ) -> None:
        directory_key = (before.st_dev, before.st_ino)
        if directory_key in self._visited_directories:
            raise UnsafeFilesystemEntry("directory identity was visited more than once")
        self._visited_directories.add(directory_key)

        # Collect names through a bounded iterator before sorting.  Counting
        # directories and excluded entries as observed work prevents a tree of
        # empty directories (or a huge excluded listing) from bypassing limits.
        names: list[str] = []
        with os.scandir(directory_fd) as iterator:
            for directory_entry in iterator:
                self._reserve_entry()
                names.append(directory_entry.name)
        names.sort()
        for name in names:
            if name in {".", ".."} or "/" in name or "\x00" in name:
                raise UnsafeFilesystemEntry("repository contains an unsafe entry name")
            relative_path = (
                name if not relative_directory else f"{relative_directory}/{name}"
            )
            self._validate_relative_path(relative_path)
            if self._is_excluded(relative_path):
                continue

            entry_before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            entry_mode = entry_before.st_mode
            if stat.S_ISDIR(entry_mode):
                if depth + 1 > self._limits.max_depth:
                    raise SnapshotLimitExceeded(
                        "repository depth exceeds the configured limit"
                    )
                self._walk_child_directory(
                    parent_fd=directory_fd,
                    name=name,
                    relative_path=relative_path,
                    depth=depth + 1,
                    before=entry_before,
                )
            elif stat.S_ISREG(entry_mode):
                self._read_regular_file(
                    parent_fd=directory_fd,
                    name=name,
                    relative_path=relative_path,
                    before=entry_before,
                )
            elif stat.S_ISLNK(entry_mode):
                self._record_symlink(
                    parent_fd=directory_fd,
                    name=name,
                    relative_path=relative_path,
                    before=entry_before,
                )
            else:
                raise UnsafeFilesystemEntry(
                    f"special filesystem entry is not allowed: {relative_path}"
                )

        after = os.fstat(directory_fd)
        if _stable_stat(before) != _stable_stat(after):
            label = relative_directory or "."
            raise SnapshotChanged(f"directory changed during traversal: {label}")

    def _walk_child_directory(
        self,
        *,
        parent_fd: int,
        name: str,
        relative_path: str,
        depth: int,
        before: os.stat_result,
    ) -> None:
        child_fd = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(child_fd)
            if not _same_object(before, opened) or _stable_stat(before) != _stable_stat(
                opened
            ):
                raise SnapshotChanged(f"directory changed before read: {relative_path}")
            self._walk_directory(
                directory_fd=child_fd,
                relative_directory=relative_path,
                depth=depth,
                before=opened,
            )
            after_fd = os.fstat(child_fd)
            after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                _stable_stat(before) != _stable_stat(after_fd)
                or _stable_stat(before) != _stable_stat(after_path)
                or not _same_object(after_fd, after_path)
            ):
                raise SnapshotChanged(f"directory changed during read: {relative_path}")
        finally:
            os.close(child_fd)

    def _read_regular_file(
        self,
        *,
        parent_fd: int,
        name: str,
        relative_path: str,
        before: os.stat_result,
    ) -> None:
        if before.st_size > self._limits.max_file_bytes:
            raise SnapshotLimitExceeded(
                f"file exceeds the configured byte limit: {relative_path}"
            )
        if self._total_bytes + before.st_size > self._limits.max_total_bytes:
            raise SnapshotLimitExceeded(
                "repository exceeds the configured total byte limit"
            )

        file_fd = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
        try:
            opened = os.fstat(file_fd)
            if (
                not stat.S_ISREG(opened.st_mode)
                or not _same_object(before, opened)
                or _stable_stat(before) != _stable_stat(opened)
            ):
                raise SnapshotChanged(f"file changed before read: {relative_path}")

            captured = bytearray()
            while True:
                chunk = os.read(file_fd, _READ_CHUNK)
                if not chunk:
                    break
                captured.extend(chunk)
                if len(captured) > self._limits.max_file_bytes:
                    raise SnapshotLimitExceeded(
                        f"file grew beyond the configured byte limit: {relative_path}"
                    )
                if self._total_bytes + len(captured) > self._limits.max_total_bytes:
                    raise SnapshotLimitExceeded(
                        "repository grew beyond the configured total byte limit"
                    )

            after_fd = os.fstat(file_fd)
            after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                len(captured) != before.st_size
                or _stable_stat(before) != _stable_stat(after_fd)
                or _stable_stat(before) != _stable_stat(after_path)
                or not _same_object(after_fd, after_path)
            ):
                raise SnapshotChanged(f"file changed during read: {relative_path}")
        finally:
            os.close(file_fd)

        data = bytes(captured)
        mode = stat.S_IMODE(before.st_mode)
        findings = _secret_fingerprints(
            data, maximum=self._limits.max_secret_fingerprints_per_file
        )
        self._entries.append(
            SnapshotEntry(
                path=relative_path,
                kind=EntryKind.FILE,
                size=len(data),
                mode=mode,
                mtime_ns=before.st_mtime_ns,
                content_digest=digest_bytes(data),
                metadata_digest=_entry_metadata_digest(
                    kind=EntryKind.FILE,
                    size=len(data),
                    mode=mode,
                    mtime_ns=before.st_mtime_ns,
                ),
                secret_fingerprints=findings,
                text=_decode_text(data),
            )
        )
        self._total_bytes += len(data)

    def _record_symlink(
        self,
        *,
        parent_fd: int,
        name: str,
        relative_path: str,
        before: os.stat_result,
    ) -> None:
        target = os.readlink(name, dir_fd=parent_fd)
        target_bytes = os.fsencode(target)
        if len(target_bytes) > self._limits.max_path_bytes:
            raise SnapshotLimitExceeded(
                f"symlink target exceeds the configured path limit: {relative_path}"
            )
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _stable_stat(before) != _stable_stat(after):
            raise SnapshotChanged(f"symlink changed during read: {relative_path}")
        mode = stat.S_IMODE(before.st_mode)
        self._entries.append(
            SnapshotEntry(
                path=relative_path,
                kind=EntryKind.SYMLINK,
                size=len(target_bytes),
                mode=mode,
                mtime_ns=before.st_mtime_ns,
                content_digest=digest_bytes(target_bytes),
                metadata_digest=_entry_metadata_digest(
                    kind=EntryKind.SYMLINK,
                    size=len(target_bytes),
                    mode=mode,
                    mtime_ns=before.st_mtime_ns,
                ),
            )
        )


def snapshot_repository(request: SnapshotRequest) -> SnapshotResult:
    """Convenience wrapper around :class:`RepositorySnapshotter`."""

    return RepositorySnapshotter().capture(request)


__all__ = [
    "RepositorySnapshotter",
    "SnapshotChanged",
    "SnapshotError",
    "SnapshotLimitExceeded",
    "SnapshotUnsupported",
    "UnsafeFilesystemEntry",
    "snapshot_repository",
]
