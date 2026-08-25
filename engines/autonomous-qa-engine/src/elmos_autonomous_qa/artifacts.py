"""Fail-closed artifact registration, bundling, publication, and lifecycle."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import io
import os
import re
import sqlite3
import stat
import sys
import threading
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .canonical import (
    UnsafePathError,
    canonical_digest,
    canonical_json_bytes,
    normalize_relative_path,
    parse_json_strict,
    path_collision_key,
    require_sha256,
    safe_join,
    sha256_bytes,
    sha256_file,
    validate_unique_paths,
)


FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MAX_BUNDLE_ENTRIES = 10_000
MAX_BUNDLE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_METADATA_BYTES = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_REGISTERED_ARTIFACTS = MAX_BUNDLE_ENTRIES - 1
MAX_REGISTERED_ARTIFACT_BYTES = (
    MAX_BUNDLE_UNCOMPRESSED_BYTES - MAX_BUNDLE_METADATA_BYTES
)
MAX_REFERENCES_PER_ARTIFACT = 1_024
MAX_STAGING_TREE_ENTRIES = 20_004
MAX_STAGING_TREE_DEPTH = 64
MAX_OUTPUT_TREE_ENTRIES = 20_004
MAX_OUTPUT_TREE_BYTES = MAX_BUNDLE_UNCOMPRESSED_BYTES * 6
MAX_OUTPUT_TREE_DEPTH = 64
LIFECYCLE_LAYOUT_VERSION = 2
LIFECYCLE_SCHEMA_VERSION = 2
LIFECYCLE_LEASE_SECONDS = 60 * 60
LIFECYCLE_PAGE_SIZE = 256
MAX_LIFECYCLE_RESULTS = 10_000
MAX_GC_SNAPSHOT_BYTES = 64 * 1024 * 1024

_SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(
        rb"(?i)(?:api[_-]?key|client[_-]?secret|password|auth[_-]?token)"
        rb"\s*[:=]\s*[\"'][^\"']{12,}[\"']"
    ),
)
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\b(?:TODO|FIXME)\b", re.IGNORECASE),
    re.compile(r"\bNotImplemented(?:Error)?\b"),
    re.compile(r"^\s*pass\s*(?:#.*)?$", re.MULTILINE),
)
_ASSERT_TRUE_PATTERNS = (
    re.compile(r"\bassert\s+True\b"),
    re.compile(r"\bassert(?:True)?\s*\(\s*true\s*\)", re.IGNORECASE),
    re.compile(r"\bexpect\s*\(\s*true\s*\)\s*\.\s*toBe\s*\(\s*true\s*\)", re.IGNORECASE),
)
_DISABLED_TEST_PATTERNS = (
    re.compile(r"@Disabled\b"),
    re.compile(r"pytest\.(?:mark\.skip|skip)\b"),
    re.compile(r"\b(?:test|describe|it)\.skip\s*\("),
    re.compile(r"\b(?:xit|xdescribe)\s*\("),
    re.compile(r"#\s*\[\s*ignore\s*\]"),
)

_BUNDLE_CATEGORIES: dict[str, frozenset[str]] = {
    "project-with-tests": frozenset(
        {
            "application_source",
            "application_config",
            "test_source",
            "test_config",
            "test_fixture",
            "test_data",
            "test_mock",
            "test_baseline",
            "ci_config",
            "replay_script",
            "manifest",
        }
    ),
    "tests-only": frozenset(
        {
            "test_source",
            "test_config",
            "test_fixture",
            "test_data",
            "test_mock",
            "test_baseline",
            "ci_config",
            "replay_script",
            "manifest",
        }
    ),
    "qa-evidence": frozenset(
        {
            "test_plan",
            "traceability",
            "test_result",
            "report",
            "evidence",
            "coverage",
            "performance_baseline",
            "security_result",
            "defect",
            "patch",
            "certificate",
            "manifest",
        }
    ),
    "repair-patches": frozenset({"patch", "defect", "replay_script", "manifest"}),
}
_EMBEDDED_CATEGORIES = _BUNDLE_CATEGORIES["tests-only"]
_ARTIFACT_CATEGORIES = frozenset().union(*_BUNDLE_CATEGORIES.values())

_ARTIFACT_ROLES = frozenset(
    {
        "application",
        "configuration",
        "unit",
        "unit_test",
        "integration_test",
        "contract_test",
        "security_test",
        "performance_test",
        "fixture",
        "test_data",
        "mock",
        "baseline",
        "ci",
        "replay",
        "test_plan",
        "traceability",
        "test_result",
        "report",
        "evidence",
        "coverage",
        "defect",
        "patch",
        "manifest",
    }
)
_ARTIFACT_PRODUCERS = frozenset(
    {
        "generator",
        "test-generator-v1",
        "autonomous-qa-engine",
        "qa-generator",
        "qa-runner",
        "repair-engine",
        "evidence-collector",
    }
)
_ARTIFACT_VALIDATION_STATUSES = frozenset(
    {"generated", "locally_validated", "failed", "partial", "not_run"}
)
_FORBIDDEN_EVIDENCE_LABELS = frozenset(
    {"certificate", "certified", "signed", "released", "deployed", "externally_verified"}
)
_RUN_MODES = frozenset(
    {"plan-only", "generate", "verify", "repair", "certify", "continuous"}
)
_OUTPUT_MODES = frozenset({"embedded", "sidecar", "both"})


class ArtifactError(RuntimeError):
    pass


class ArtifactValidationError(ArtifactError):
    pass


class PublicationError(ArtifactError):
    pass


class CertificationDenied(PublicationError):
    pass


class LifecycleError(ArtifactError):
    pass


class OutputMode(StrEnum):
    EMBEDDED = "embedded"
    SIDECAR = "sidecar"
    BOTH = "both"


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _utc_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat().replace(
        "+00:00", "Z"
    )


def _safe_segment(value: str, field: str) -> str:
    normalized = normalize_relative_path(value)
    if len(PurePosixPath(normalized).parts) != 1:
        raise UnsafePathError(f"{field} must be exactly one path segment")
    return normalized


def _safe_root(path: Path, field: str) -> Path:
    absolute = Path(os.path.abspath(path))
    if absolute == Path(absolute.anchor):
        raise UnsafePathError(f"{field} may not be a filesystem root")
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor /= part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise UnsafePathError(f"{field} may not contain a symlink: {cursor}")
    return absolute


def _storage_segment(kind: str, value: str) -> str:
    """Return a case- and Unicode-alias-resistant filesystem identity."""

    safe_value = _safe_segment(value, kind)
    digest = canonical_digest({"kind": kind, "value": safe_value})
    return f"{kind}-{digest}"


def _metadata_value(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"{field} must be a non-empty string of at most 256 bytes")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ArtifactValidationError(f"{field} is not valid UTF-8 text") from exc
    if len(encoded) > 256:
        raise ArtifactValidationError(f"{field} must be a non-empty string of at most 256 bytes")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ArtifactValidationError(f"{field} contains a control character")
    try:
        canonical_json_bytes({"value": value})
    except ValueError as exc:
        raise ArtifactValidationError(f"{field} is not canonical JSON text") from exc
    return value


def _created_at_value(value: str) -> str:
    value = _metadata_value(value, "created_at")
    if not value.endswith("Z"):
        raise ArtifactValidationError("created_at must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ArtifactValidationError("created_at must be a canonical UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ArtifactValidationError("created_at must be a canonical UTC timestamp")
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise ArtifactValidationError("created_at must be a canonical UTC timestamp")
    return value


def _open_directory_chain_nofollow(path: Path, *, create: bool = False) -> list[int]:
    """Open an absolute directory through pinned, no-follow directory descriptors."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None or not path.is_absolute():
        raise OSError(errno.ENOTSUP, "descriptor-rooted directory access is unavailable")
    flags = os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        current = os.open(path.anchor, flags)
        descriptors.append(current)
        for part in path.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o755, dir_fd=current)
                child = os.open(part, flags, dir_fd=current)
            descriptors.append(child)
            current = child
        return descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _read_regular_file_nofollow(root: Path, relative_path: str) -> bytes:
    """Read one stable regular file through a no-follow descriptor chain."""

    relative = normalize_relative_path(relative_path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None or not hasattr(os, "open"):
        raise ArtifactValidationError("descriptor-based no-follow reads are unavailable")
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    try:
        root_descriptors = _open_directory_chain_nofollow(root)
        descriptors.extend(root_descriptors)
        current = root_descriptors[-1]
        root_stat = os.fstat(current)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ArtifactValidationError(f"artifact root is not a directory: {root}")
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | directory | nofollow | close_on_exec,
                dir_fd=current,
            )
            descriptors.append(current)
        file_descriptor = os.open(
            parts[-1], os.O_RDONLY | nofollow | close_on_exec, dir_fd=current
        )
        descriptors.append(file_descriptor)
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ArtifactValidationError(f"artifact is not a regular file: {relative!r}")
        if before.st_nlink != 1:
            raise ArtifactValidationError(f"hard-linked artifact is forbidden: {relative!r}")
        if before.st_size > MAX_ARTIFACT_BYTES:
            raise ArtifactValidationError(f"artifact exceeds the size limit: {relative!r}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(file_descriptor)
        fingerprint_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_uid,
            before.st_gid,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        fingerprint_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_gid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        data = b"".join(chunks)
        if fingerprint_before != fingerprint_after or len(data) != after.st_size:
            raise ArtifactValidationError(f"artifact changed while being read: {relative!r}")
        return data
    except OSError as exc:
        raise ArtifactValidationError(
            f"cannot safely read artifact {relative!r}: {exc.strerror or type(exc).__name__}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _fsync_directory(path: Path) -> None:
    descriptors = _open_directory_chain_nofollow(path)
    try:
        _fsync_directory_descriptor(descriptors[-1])
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _fsync_directory_descriptor(descriptor: int) -> None:
    # An unsupported directory barrier is not equivalent to durability.  The
    # caller either rolls an uncommitted operation back or records the already
    # committed namespace change as durability-unknown.
    os.fsync(descriptor)


def _require_private_directory_descriptor(descriptor: int, field: str) -> None:
    """Require a directory whose namespace cannot be changed by another OS user."""

    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise OSError(errno.ENOTDIR, f"{field} is not a directory")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise OSError(errno.EPERM, f"{field} is not owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise OSError(errno.EPERM, f"{field} is group/world writable")


def _renameat_no_replace(
    source_parent: int,
    source_name: str,
    destination_parent: int,
    destination_name: str,
) -> None:
    """Perform only the platform no-replace namespace operation."""

    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    libc = ctypes.CDLL(None, use_errno=True)
    result: int
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        renameatx = libc.renameatx_np
        renameatx.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameatx.restype = ctypes.c_int
        result = int(
            renameatx(
                source_parent,
                source_bytes,
                destination_parent,
                destination_bytes,
                0x00000004,
            )
        )
    elif os.name == "posix" and hasattr(libc, "renameat2"):
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = int(
            renameat2(
                source_parent,
                source_bytes,
                destination_parent,
                destination_bytes,
                1,
            )
        )
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(error_number, os.strerror(error_number), destination_name)
        raise OSError(error_number, os.strerror(error_number), destination_name)


def _rename_no_replace(
    source: Path,
    destination: Path,
    *,
    expected_source_identity: tuple[int, int] | None = None,
    expected_source_snapshot: _TreeSnapshot | None = None,
) -> bool:
    """Commit an atomic rename and report whether both parent syncs succeeded.

    Once the namespace operation succeeds this function never raises: the
    caller must preserve the committed result and surface ``False`` as
    durability-unknown rather than pretending either that no commit occurred
    or that the rename is known durable.
    """

    source_descriptors: list[int] = []
    destination_descriptors: list[int] = []
    source_root_descriptor: int | None = None
    renamed = False
    durable = True
    try:
        source_descriptors = _open_directory_chain_nofollow(source.parent)
        destination_descriptors = _open_directory_chain_nofollow(destination.parent)
        source_parent = source_descriptors[-1]
        destination_parent = destination_descriptors[-1]
        _require_private_directory_descriptor(source_parent, "publication source parent")
        _require_private_directory_descriptor(
            destination_parent, "publication destination parent"
        )
        source_metadata = os.stat(
            source.name, dir_fd=source_parent, follow_symlinks=False
        )
        if not stat.S_ISDIR(source_metadata.st_mode):
            raise PublicationError("atomic publication source is not a directory")
        if expected_source_identity is not None and (
            int(source_metadata.st_dev),
            int(source_metadata.st_ino),
        ) != expected_source_identity:
            raise PublicationError("atomic publication source identity changed")
        source_root_descriptor = os.open(
            source.name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=source_parent,
        )
        opened = os.fstat(source_root_descriptor)
        if (opened.st_dev, opened.st_ino) != (
            source_metadata.st_dev,
            source_metadata.st_ino,
        ):
            raise PublicationError("atomic publication source changed while opening")
        if expected_source_snapshot is not None:
            current_snapshot = _snapshot_tree_from_descriptor(source_root_descriptor)
            if current_snapshot != expected_source_snapshot:
                raise PublicationError("atomic publication source tree changed before commit")
        current = os.stat(source.name, dir_fd=source_parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise PublicationError("atomic publication source changed before commit")
        try:
            _renameat_no_replace(
                source_parent,
                source.name,
                destination_parent,
                destination.name,
            )
        except FileExistsError as exc:
            raise PublicationError(f"immutable output already exists: {destination}") from exc
        renamed = True
    except ArtifactValidationError as exc:
        raise PublicationError("atomic publication source verification failed") from exc
    except OSError as exc:
        raise PublicationError(
            f"atomic publication failed: {exc.strerror or type(exc).__name__}"
        ) from exc
    finally:
        if renamed:
            # The namespace commit is irreversible here. Durability sync is best effort and
            # must never turn a committed output into a reported publication failure.
            for descriptor in (
                destination_descriptors[-1:] + source_descriptors[-1:]
            ):
                try:
                    _fsync_directory_descriptor(descriptor)
                except BaseException:
                    durable = False
        if source_root_descriptor is not None:
            try:
                os.close(source_root_descriptor)
            except BaseException:
                if renamed:
                    durable = False
        for descriptor in reversed(destination_descriptors):
            try:
                os.close(descriptor)
            except BaseException:
                if renamed:
                    durable = False
        for descriptor in reversed(source_descriptors):
            try:
                os.close(descriptor)
            except BaseException:
                if renamed:
                    durable = False
    return durable


@dataclass(frozen=True, slots=True)
class OutputPlan:
    tenant_id: str
    project_id: str
    revision_id: str
    run_id: str
    run_mode: str
    output_mode: OutputMode
    source_snapshot_digest: str
    staging_root: Path
    publication_root: Path
    embedded_root: Path | None = None
    created_at: str = "1970-01-01T00:00:00Z"

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_mode", OutputMode(self.output_mode))
        object.__setattr__(self, "tenant_id", _safe_segment(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "project_id", _safe_segment(self.project_id, "project_id"))
        object.__setattr__(self, "revision_id", _safe_segment(self.revision_id, "revision_id"))
        object.__setattr__(self, "run_id", _safe_segment(self.run_id, "run_id"))
        if not isinstance(self.run_mode, str) or self.run_mode not in _RUN_MODES:
            raise ValueError(f"unsupported run mode: {self.run_mode!r}")
        try:
            object.__setattr__(self, "created_at", _created_at_value(self.created_at))
        except ArtifactValidationError as exc:
            raise ValueError(str(exc)) from exc
        object.__setattr__(
            self, "source_snapshot_digest", require_sha256(self.source_snapshot_digest)
        )
        object.__setattr__(self, "staging_root", _safe_root(Path(self.staging_root), "staging_root"))
        object.__setattr__(
            self,
            "publication_root",
            _safe_root(Path(self.publication_root), "publication_root"),
        )
        if self.output_mode in {OutputMode.EMBEDDED, OutputMode.BOTH}:
            if self.embedded_root is None:
                raise ValueError(f"{self.output_mode.value} output requires embedded_root")
            object.__setattr__(
                self, "embedded_root", _safe_root(Path(self.embedded_root), "embedded_root")
            )

    @property
    def output_id(self) -> str:
        identity = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "run_id": self.run_id,
            "source_snapshot_digest": self.source_snapshot_digest,
            "output_mode": self.output_mode.value,
            "run_mode": self.run_mode,
        }
        return f"out_{canonical_digest(identity)[:24]}"

    @property
    def final_root(self) -> Path:
        return safe_join(
            self.publication_root,
            "/".join(
                (
                    _storage_segment("tenant", self.tenant_id),
                    _storage_segment("project", self.project_id),
                    _storage_segment("revision", self.revision_id),
                    _storage_segment("output", self.output_id),
                )
            ),
        )

    def materialization_targets(self) -> tuple[Path, ...]:
        if self.run_mode == "plan-only":
            return ()
        targets: list[Path] = []
        if self.output_mode in {OutputMode.EMBEDDED, OutputMode.BOTH}:
            assert self.embedded_root is not None
            targets.append(self.embedded_root)
        if self.output_mode in {OutputMode.SIDECAR, OutputMode.BOTH}:
            targets.append(self.final_root / "project")
        return tuple(targets)


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    path: str
    category: str
    role: str
    sha256: str
    size_bytes: int
    producer: str
    required: bool
    validation_status: str
    requirement_refs: tuple[str, ...]
    test_case_refs: tuple[str, ...]
    risk_justification: str | None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "category": self.category,
            "role": self.role,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "producer": self.producer,
            "required": self.required,
            "validation_status": self.validation_status,
            "requirement_refs": list(self.requirement_refs),
            "test_case_refs": list(self.test_case_refs),
        }
        if self.risk_justification is not None:
            result["risk_justification"] = self.risk_justification
        return result


@dataclass(frozen=True, slots=True)
class PublishedOutput:
    tenant_id: str
    output_id: str
    project_id: str
    revision_id: str
    run_id: str
    status: str
    root: Path
    manifest_digest: str
    bundle_digests: Mapping[str, str]
    durability_status: str
    failure: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class _TreeFile:
    device: int
    inode: int
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _TreeSnapshot:
    root_device: int
    root_inode: int
    files: Mapping[str, _TreeFile]
    directories: Mapping[str, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class _LifecycleFence:
    descriptor: int
    parent_descriptor: int
    key: str
    device: int
    inode: int
    mode: int
    uid: int


@dataclass(slots=True)
class _PinnedCandidate:
    path: Path
    parent_descriptor: int
    root_descriptor: int
    root_device: int
    root_inode: int
    cleanup_snapshot: _TreeSnapshot


@dataclass(frozen=True, slots=True)
class _EmbeddedCreation:
    relative_path: str
    parent_descriptor: int
    file_name: str
    device: int
    inode: int
    size_bytes: int
    sha256: str


def _close_descriptors(descriptors: list[int] | tuple[int, ...]) -> None:
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except OSError:
            pass


def _bounded_directory_names(
    descriptor: int, *, maximum: int, field: str
) -> list[str]:
    """Collect at most ``maximum`` names without an unbounded listdir allocation."""

    names: list[str] = []
    with os.scandir(descriptor) as entries:
        for entry in entries:
            if len(names) >= maximum:
                raise ArtifactValidationError(f"{field} entry limit exceeded")
            names.append(entry.name)
    return names


def _close_candidate(candidate: _PinnedCandidate) -> None:
    for field in ("root_descriptor", "parent_descriptor"):
        descriptor = getattr(candidate, field)
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
            setattr(candidate, field, -1)


def _tree_snapshot_bytes(snapshot: _TreeSnapshot) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": "elmos.autonomous-qa.gc-tree.v1",
            "root_device": snapshot.root_device,
            "root_inode": snapshot.root_inode,
            "files": [
                {
                    "path": path,
                    "device": snapshot.files[path].device,
                    "inode": snapshot.files[path].inode,
                    "size_bytes": snapshot.files[path].size_bytes,
                    "sha256": snapshot.files[path].sha256,
                }
                for path in sorted(snapshot.files)
            ],
            "directories": [
                {
                    "path": path,
                    "device": snapshot.directories[path][0],
                    "inode": snapshot.directories[path][1],
                }
                for path in sorted(snapshot.directories)
            ],
        }
    )


def _tree_snapshot_from_bytes(payload: bytes) -> _TreeSnapshot:
    if not isinstance(payload, bytes) or len(payload) > MAX_GC_SNAPSHOT_BYTES:
        raise LifecycleError("garbage-collection snapshot byte limit exceeded")
    try:
        document = parse_json_strict(payload)
    except (TypeError, ValueError) as exc:
        raise LifecycleError("garbage-collection snapshot is invalid JSON") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "root_device",
        "root_inode",
        "files",
        "directories",
    }:
        raise LifecycleError("garbage-collection snapshot fields are not exact")
    if document.get("schema_version") != "elmos.autonomous-qa.gc-tree.v1":
        raise LifecycleError("garbage-collection snapshot schema is unsupported")

    def identity(value: object, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise LifecycleError(f"garbage-collection snapshot {field} is invalid")
        return value

    root_device = identity(document.get("root_device"), "root device")
    root_inode = identity(document.get("root_inode"), "root inode")
    file_rows = document.get("files")
    directory_rows = document.get("directories")
    if not isinstance(file_rows, list) or not isinstance(directory_rows, list):
        raise LifecycleError("garbage-collection snapshot tree is invalid")
    if len(file_rows) + len(directory_rows) > MAX_OUTPUT_TREE_ENTRIES:
        raise LifecycleError("garbage-collection snapshot entry limit exceeded")
    files: dict[str, _TreeFile] = {}
    total_bytes = 0
    ordered_file_paths: list[str] = []
    for row in file_rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "device",
            "inode",
            "size_bytes",
            "sha256",
        }:
            raise LifecycleError("garbage-collection file snapshot is invalid")
        try:
            path = normalize_relative_path(row.get("path"))
            digest = require_sha256(row.get("sha256"), field="gc file sha256")
        except (AttributeError, TypeError, ValueError) as exc:
            raise LifecycleError("garbage-collection file snapshot is invalid") from exc
        size_bytes = identity(row.get("size_bytes"), "file size")
        total_bytes += size_bytes
        if total_bytes > MAX_OUTPUT_TREE_BYTES:
            raise LifecycleError("garbage-collection snapshot byte limit exceeded")
        ordered_file_paths.append(path)
        files[path] = _TreeFile(
            device=identity(row.get("device"), "file device"),
            inode=identity(row.get("inode"), "file inode"),
            size_bytes=size_bytes,
            sha256=digest,
        )
    directories: dict[str, tuple[int, int]] = {}
    ordered_directory_paths: list[str] = []
    for row in directory_rows:
        if not isinstance(row, dict) or set(row) != {"path", "device", "inode"}:
            raise LifecycleError("garbage-collection directory snapshot is invalid")
        try:
            path = normalize_relative_path(row.get("path"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise LifecycleError("garbage-collection directory snapshot is invalid") from exc
        ordered_directory_paths.append(path)
        directories[path] = (
            identity(row.get("device"), "directory device"),
            identity(row.get("inode"), "directory inode"),
        )
    try:
        validate_unique_paths((*ordered_file_paths, *ordered_directory_paths))
    except ValueError as exc:
        raise LifecycleError("garbage-collection snapshot paths collide") from exc
    if ordered_file_paths != sorted(ordered_file_paths) or ordered_directory_paths != sorted(
        ordered_directory_paths
    ):
        raise LifecycleError("garbage-collection snapshot paths are not canonical")
    if set(directories) != _expected_directory_paths(set(files)):
        raise LifecycleError("garbage-collection snapshot directory tree is not exact")
    if canonical_json_bytes(document) != payload:
        raise LifecycleError("garbage-collection snapshot is not canonically encoded")
    return _TreeSnapshot(
        root_device=root_device,
        root_inode=root_inode,
        files=files,
        directories=directories,
    )


def _gc_snapshot_envelope_bytes(
    snapshot: _TreeSnapshot,
    *,
    tenant_id: str,
    output_id: str,
    project_id: str,
    revision_id: str,
    run_id: str,
    manifest_digest: str,
    quarantine_name: str,
) -> bytes:
    manifest_file = snapshot.files.get("manifests/project-output-manifest.json")
    if manifest_file is None or manifest_file.sha256 != manifest_digest:
        raise LifecycleError("garbage-collection snapshot is not bound to its manifest")
    tree_bytes = _tree_snapshot_bytes(snapshot)
    tree_document = parse_json_strict(tree_bytes)
    payload = canonical_json_bytes(
        {
            "schema_version": "elmos.autonomous-qa.gc-envelope.v2",
            "layout_version": LIFECYCLE_LAYOUT_VERSION,
            "tenant_id": tenant_id,
            "output_id": output_id,
            "project_id": project_id,
            "revision_id": revision_id,
            "run_id": run_id,
            "manifest_digest": manifest_digest,
            "quarantine_name": _safe_segment(quarantine_name, "quarantine_name"),
            "tree_sha256": sha256_bytes(tree_bytes),
            "tree": tree_document,
        }
    )
    if len(payload) > MAX_GC_SNAPSHOT_BYTES:
        raise LifecycleError("garbage-collection snapshot byte limit exceeded")
    return payload


def _gc_snapshot_envelope_from_bytes(
    payload: bytes,
    *,
    tenant_id: str,
    output_id: str,
    project_id: str,
    revision_id: str,
    run_id: str,
    manifest_digest: str,
    quarantine_name: str,
) -> _TreeSnapshot:
    if not isinstance(payload, bytes) or len(payload) > MAX_GC_SNAPSHOT_BYTES:
        raise LifecycleError("garbage-collection snapshot byte limit exceeded")
    try:
        document = parse_json_strict(payload)
    except (TypeError, ValueError) as exc:
        raise LifecycleError("garbage-collection envelope is invalid JSON") from exc
    expected_fields = {
        "schema_version",
        "layout_version",
        "tenant_id",
        "output_id",
        "project_id",
        "revision_id",
        "run_id",
        "manifest_digest",
        "quarantine_name",
        "tree_sha256",
        "tree",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        raise LifecycleError("garbage-collection envelope fields are not exact")
    expected_identity = {
        "schema_version": "elmos.autonomous-qa.gc-envelope.v2",
        "layout_version": LIFECYCLE_LAYOUT_VERSION,
        "tenant_id": tenant_id,
        "output_id": output_id,
        "project_id": project_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "manifest_digest": manifest_digest,
        "quarantine_name": _safe_segment(quarantine_name, "quarantine_name"),
    }
    if any(document.get(field) != value for field, value in expected_identity.items()):
        raise LifecycleError("garbage-collection envelope identity mismatch")
    if canonical_json_bytes(document) != payload:
        raise LifecycleError("garbage-collection envelope is not canonically encoded")
    tree_document = document.get("tree")
    try:
        tree_bytes = canonical_json_bytes(tree_document)
        tree_digest = require_sha256(
            document.get("tree_sha256"), field="garbage-collection tree digest"
        )
    except (TypeError, ValueError) as exc:
        raise LifecycleError("garbage-collection envelope tree is invalid") from exc
    if sha256_bytes(tree_bytes) != tree_digest:
        raise LifecycleError("garbage-collection envelope tree digest mismatch")
    snapshot = _tree_snapshot_from_bytes(tree_bytes)
    manifest_file = snapshot.files.get("manifests/project-output-manifest.json")
    if manifest_file is None or manifest_file.sha256 != manifest_digest:
        raise LifecycleError("garbage-collection envelope manifest binding mismatch")
    return snapshot


def _stable_file_digest(
    descriptor: int,
    *,
    max_bytes: int,
    capture: bool = False,
) -> tuple[_TreeFile, bytes | None]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ArtifactValidationError("descriptor does not identify a regular file")
    if before.st_nlink != 1:
        raise ArtifactValidationError("hard-linked published files are forbidden")
    if before.st_size > max_bytes:
        raise ArtifactValidationError("published file exceeds the size limit")
    digest = hashlib.sha256()
    chunks: list[bytes] | None = [] if capture else None
    total = 0
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ArtifactValidationError("published file exceeds the size limit")
        digest.update(chunk)
        if chunks is not None:
            chunks.append(chunk)
    after = os.fstat(descriptor)
    before_fingerprint = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_fingerprint = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_uid,
        after.st_gid,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_fingerprint != after_fingerprint or total != after.st_size:
        raise ArtifactValidationError("published file changed while being read")
    snapshot = _TreeFile(
        device=int(after.st_dev),
        inode=int(after.st_ino),
        size_bytes=total,
        sha256=digest.hexdigest(),
    )
    return snapshot, None if chunks is None else b"".join(chunks)


def _read_regular_file_at(
    root_descriptor: int,
    relative_path: str,
    *,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> bytes:
    relative = normalize_relative_path(relative_path)
    directory = getattr(os, "O_DIRECTORY", None)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if directory is None or nofollow is None:
        raise ArtifactValidationError("descriptor-rooted reads are unavailable")
    descriptors: list[int] = []
    try:
        current = os.dup(root_descriptor)
        descriptors.append(current)
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | directory | nofollow | getattr(os, "O_CLOEXEC", 0),
                dir_fd=current,
            )
            descriptors.append(current)
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=current,
        )
        descriptors.append(file_descriptor)
        _, data = _stable_file_digest(
            file_descriptor,
            max_bytes=max_bytes,
            capture=True,
        )
        assert data is not None
        return data
    except OSError as exc:
        raise ArtifactValidationError(
            f"cannot safely read published file {relative!r}: "
            f"{exc.strerror or type(exc).__name__}"
        ) from exc
    finally:
        _close_descriptors(descriptors)


def _snapshot_tree_from_descriptor(root_descriptor: int) -> _TreeSnapshot:
    directory_flag = getattr(os, "O_DIRECTORY", None)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if directory_flag is None or nofollow is None:
        raise ArtifactValidationError("descriptor-rooted tree inspection is unavailable")
    root_metadata = os.fstat(root_descriptor)
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ArtifactValidationError("published-output root is not a directory")
    files: dict[str, _TreeFile] = {}
    directories: dict[str, tuple[int, int]] = {}
    collision_keys: dict[str, str] = {}
    entry_count = 0
    total_bytes = 0

    def walk(descriptor: int, prefix: str, depth: int) -> None:
        nonlocal entry_count, total_bytes
        if depth > MAX_OUTPUT_TREE_DEPTH:
            raise ArtifactValidationError("published-output tree depth limit exceeded")
        before_directory = os.fstat(descriptor)
        before_names = _bounded_directory_names(
            descriptor,
            maximum=max(0, MAX_OUTPUT_TREE_ENTRIES - entry_count),
            field="published-output tree",
        )
        if len(before_names) != len(set(before_names)):
            raise ArtifactValidationError("published-output directory entries are ambiguous")
        for name in sorted(before_names):
            if not isinstance(name, str) or not name or "/" in name or name in {".", ".."}:
                raise ArtifactValidationError("published-output entry name is invalid")
            relative = normalize_relative_path(f"{prefix}/{name}" if prefix else name)
            collision_key = path_collision_key(relative)
            other = collision_keys.get(collision_key)
            if other is not None:
                raise ArtifactValidationError(
                    f"published-output paths collide: {other!r}, {relative!r}"
                )
            collision_keys[collision_key] = relative
            entry_count += 1
            if entry_count > MAX_OUTPUT_TREE_ENTRIES:
                raise ArtifactValidationError("published-output tree entry limit exceeded")
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY
                    | directory_flag
                    | nofollow
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
                try:
                    opened = os.fstat(child)
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or (opened.st_dev, opened.st_ino)
                        != (metadata.st_dev, metadata.st_ino)
                    ):
                        raise ArtifactValidationError(
                            f"published-output directory changed: {relative!r}"
                        )
                    directories[relative] = (int(opened.st_dev), int(opened.st_ino))
                    walk(child, relative, depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(metadata.st_mode):
                file_descriptor = os.open(
                    name,
                    os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
                try:
                    opened = os.fstat(file_descriptor)
                    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                        raise ArtifactValidationError(
                            f"published-output file changed: {relative!r}"
                        )
                    file_snapshot, _ = _stable_file_digest(
                        file_descriptor,
                        max_bytes=MAX_BUNDLE_UNCOMPRESSED_BYTES,
                    )
                finally:
                    os.close(file_descriptor)
                total_bytes += file_snapshot.size_bytes
                if total_bytes > MAX_OUTPUT_TREE_BYTES:
                    raise ArtifactValidationError("published-output byte limit exceeded")
                files[relative] = file_snapshot
            else:
                raise ArtifactValidationError(
                    f"published-output special entry is forbidden: {relative!r}"
                )
        after_names = _bounded_directory_names(
            descriptor,
            maximum=MAX_OUTPUT_TREE_ENTRIES,
            field="published-output tree",
        )
        after_directory = os.fstat(descriptor)
        if set(after_names) != set(before_names) or (
            before_directory.st_dev,
            before_directory.st_ino,
            before_directory.st_mode,
            before_directory.st_uid,
            before_directory.st_gid,
            before_directory.st_mtime_ns,
            before_directory.st_ctime_ns,
        ) != (
            after_directory.st_dev,
            after_directory.st_ino,
            after_directory.st_mode,
            after_directory.st_uid,
            after_directory.st_gid,
            after_directory.st_mtime_ns,
            after_directory.st_ctime_ns,
        ):
            raise ArtifactValidationError("published-output directory changed during inspection")

    walk(root_descriptor, "", 0)
    return _TreeSnapshot(
        root_device=int(root_metadata.st_dev),
        root_inode=int(root_metadata.st_ino),
        files=files,
        directories=directories,
    )


def _open_tree_snapshot(path: Path) -> tuple[list[int], _TreeSnapshot]:
    descriptors = _open_directory_chain_nofollow(path)
    try:
        snapshot = _snapshot_tree_from_descriptor(descriptors[-1])
        return descriptors, snapshot
    except BaseException:
        _close_descriptors(descriptors)
        raise


def _directory_identity_nofollow(path: Path) -> tuple[int, int]:
    descriptors = _open_directory_chain_nofollow(path)
    try:
        metadata = os.fstat(descriptors[-1])
        if not stat.S_ISDIR(metadata.st_mode):
            raise ArtifactValidationError(f"path is not a directory: {path}")
        return int(metadata.st_dev), int(metadata.st_ino)
    finally:
        _close_descriptors(descriptors)


def _expected_directory_paths(file_paths: set[str]) -> set[str]:
    directories: set[str] = set()
    for file_path in file_paths:
        parent = PurePosixPath(file_path).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _checksums_bytes(files: Mapping[str, _TreeFile]) -> bytes:
    checksum_path = "manifests/checksums.sha256"
    return (
        "".join(
            f"{files[path].sha256}  {path}\n"
            for path in sorted(files)
            if path != checksum_path
        )
    ).encode("utf-8")


def _checksums_from_expected(files: Mapping[str, tuple[str, int]]) -> bytes:
    checksum_path = "manifests/checksums.sha256"
    return (
        "".join(
            f"{files[path][0]}  {path}\n"
            for path in sorted(files)
            if path != checksum_path
        )
    ).encode("utf-8")


def _verify_exact_tree_descriptor(
    root_descriptor: int,
    *,
    expected_files: Mapping[str, tuple[str, int]],
    exact_bytes: Mapping[str, bytes],
) -> _TreeSnapshot:
    normalized_files = validate_unique_paths(expected_files)
    expected_file_set = set(normalized_files)
    expected_directories = _expected_directory_paths(expected_file_set)
    snapshot = _snapshot_tree_from_descriptor(root_descriptor)
    if set(snapshot.files) != expected_file_set:
        raise ArtifactValidationError(
            "published-output files do not match the exact manifest-owned tree"
        )
    if set(snapshot.directories) != expected_directories:
        raise ArtifactValidationError(
            "published-output directories do not match the exact manifest-owned tree"
        )
    for path, (expected_digest, expected_size) in expected_files.items():
        actual = snapshot.files[path]
        if actual.sha256 != expected_digest or actual.size_bytes != expected_size:
            raise ArtifactValidationError(f"published-output content mismatch: {path!r}")
    for path, expected in exact_bytes.items():
        actual = _read_regular_file_at(
            root_descriptor, path, max_bytes=MAX_BUNDLE_UNCOMPRESSED_BYTES
        )
        if actual != expected:
            raise ArtifactValidationError(f"published-output bytes mismatch: {path!r}")
    checksum_path = "manifests/checksums.sha256"
    if checksum_path in snapshot.files:
        actual_checksums = _read_regular_file_at(
            root_descriptor, checksum_path, max_bytes=MAX_ARTIFACT_BYTES
        )
        if actual_checksums != _checksums_bytes(snapshot.files):
            raise ArtifactValidationError("published-output checksum index is not exact")
    return snapshot


def _verify_exact_tree(
    root: Path,
    *,
    expected_files: Mapping[str, tuple[str, int]],
    exact_bytes: Mapping[str, bytes],
) -> _TreeSnapshot:
    descriptors = _open_directory_chain_nofollow(root)
    try:
        return _verify_exact_tree_descriptor(
            descriptors[-1], expected_files=expected_files, exact_bytes=exact_bytes
        )
    finally:
        _close_descriptors(descriptors)


def _assert_named_descriptor_identity(
    parent_descriptor: int,
    name: str,
    pinned_descriptor: int,
    *,
    device: int,
    inode: int,
    directory: bool,
    link_count: int | None = None,
) -> os.stat_result:
    """Fence a final namespace mutation to the still-open verified descriptor."""

    pinned = os.fstat(pinned_descriptor)
    named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        not expected_type(pinned.st_mode)
        or not expected_type(named.st_mode)
        or (int(pinned.st_dev), int(pinned.st_ino)) != (device, inode)
        or (int(named.st_dev), int(named.st_ino)) != (device, inode)
        or (
            link_count is not None
            and (pinned.st_nlink != link_count or named.st_nlink != link_count)
        )
    ):
        raise LifecycleError("pinned namespace entry changed before mutation")
    return named


def _delete_directory_tree_nofollow(
    parent: Path,
    name: str,
    *,
    expected: _TreeSnapshot,
    allow_missing: bool = False,
) -> None:
    """Delete an inode-bound tree, resuming deterministic tombstones when requested."""

    safe_name = _safe_segment(name, "deletion target")
    directory_flag = getattr(os, "O_DIRECTORY", None)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if directory_flag is None or nofollow is None:
        raise LifecycleError("descriptor-rooted deletion is unavailable")
    parent_descriptors: list[int] = []
    root_descriptor: int | None = None
    expected_children_by_parent: dict[str, set[str]] = {}
    for expected_path in (*expected.files, *expected.directories):
        parsed = PurePosixPath(expected_path)
        expected_children_by_parent.setdefault(parsed.parent.as_posix(), set()).add(
            parsed.name
        )
    try:
        parent_descriptors = _open_directory_chain_nofollow(parent)
        parent_descriptor = parent_descriptors[-1]
        _require_private_directory_descriptor(parent_descriptor, "deletion parent")
        root_descriptor = os.open(
            safe_name,
            os.O_RDONLY | directory_flag | nofollow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        root_metadata = os.fstat(root_descriptor)
        if (root_metadata.st_dev, root_metadata.st_ino) != (
            expected.root_device,
            expected.root_inode,
        ):
            raise LifecycleError("deletion target filesystem identity changed")

        def tombstone(relative: str, device: int, inode: int) -> str:
            return ".elmos-delete-" + canonical_digest(
                {"path": relative, "device": device, "inode": inode}
            )[:32]

        def restore_unknown(
            descriptor: int, temporary_name: str, original_name: str
        ) -> None:
            try:
                _renameat_no_replace(
                    descriptor, temporary_name, descriptor, original_name
                )
                _fsync_directory_descriptor(descriptor)
            except OSError:
                # Retain the unknown entry under its tombstone rather than deleting it.
                pass

        def delete_contents(descriptor: int, prefix: str) -> None:
            expected_children = expected_children_by_parent.get(prefix or ".", set())
            names = set(
                _bounded_directory_names(
                    descriptor,
                    maximum=max(1, len(expected_children) * 2 + 1),
                    field="deletion target",
                )
            )
            allowed_names: set[str] = set()
            choices: dict[str, tuple[str, str]] = {}
            for child_name in expected_children:
                relative = normalize_relative_path(
                    f"{prefix}/{child_name}" if prefix else child_name
                )
                if relative in expected.directories:
                    device, inode = expected.directories[relative]
                else:
                    expected_file = expected.files[relative]
                    device, inode = expected_file.device, expected_file.inode
                temporary_name = tombstone(relative, device, inode)
                allowed_names.update({child_name, temporary_name})
                choices[child_name] = (relative, temporary_name)
            if names - allowed_names:
                raise LifecycleError("deletion target tree changed after verification")
            for child_name in sorted(expected_children):
                relative, temporary_name = choices[child_name]
                present = names.intersection({child_name, temporary_name})
                if len(present) > 1:
                    raise LifecycleError("deletion target contains an ambiguous tombstone")
                if not present:
                    if allow_missing:
                        continue
                    raise LifecycleError("deletion target tree changed after verification")
                current_name = next(iter(present))
                if relative in expected.directories:
                    expected_identity = expected.directories[relative]
                    child_descriptor = os.open(
                        current_name,
                        os.O_RDONLY
                        | directory_flag
                        | nofollow
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=descriptor,
                    )
                    try:
                        opened = os.fstat(child_descriptor)
                        if (opened.st_dev, opened.st_ino) != expected_identity:
                            raise LifecycleError(
                                "deletion target directory identity changed"
                            )
                        delete_contents(child_descriptor, relative)
                        _fsync_directory_descriptor(child_descriptor)
                        _assert_named_descriptor_identity(
                            descriptor,
                            current_name,
                            child_descriptor,
                            device=expected_identity[0],
                            inode=expected_identity[1],
                            directory=True,
                        )
                        if current_name != temporary_name:
                            _renameat_no_replace(
                                descriptor, current_name, descriptor, temporary_name
                            )
                            _fsync_directory_descriptor(descriptor)
                        _assert_named_descriptor_identity(
                            descriptor,
                            temporary_name,
                            child_descriptor,
                            device=expected_identity[0],
                            inode=expected_identity[1],
                            directory=True,
                        )
                        if _bounded_directory_names(
                            child_descriptor,
                            maximum=1,
                            field="deletion target directory",
                        ):
                            raise LifecycleError(
                                "deletion target directory is not empty after cleanup"
                            )
                        _assert_named_descriptor_identity(
                            descriptor,
                            temporary_name,
                            child_descriptor,
                            device=expected_identity[0],
                            inode=expected_identity[1],
                            directory=True,
                        )
                        os.rmdir(temporary_name, dir_fd=descriptor)
                    finally:
                        try:
                            os.close(child_descriptor)
                        except OSError:
                            pass
                elif relative in expected.files:
                    expected_file = expected.files[relative]
                    file_descriptor = os.open(
                        current_name,
                        os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=descriptor,
                    )
                    try:
                        actual_file, _ = _stable_file_digest(
                            file_descriptor,
                            max_bytes=MAX_BUNDLE_UNCOMPRESSED_BYTES,
                        )
                        if actual_file != expected_file:
                            raise LifecycleError(
                                "deletion target file changed after verification"
                            )
                        _assert_named_descriptor_identity(
                            descriptor,
                            current_name,
                            file_descriptor,
                            device=expected_file.device,
                            inode=expected_file.inode,
                            directory=False,
                            link_count=1,
                        )
                        if current_name != temporary_name:
                            _renameat_no_replace(
                                descriptor, current_name, descriptor, temporary_name
                            )
                            _fsync_directory_descriptor(descriptor)
                        _assert_named_descriptor_identity(
                            descriptor,
                            temporary_name,
                            file_descriptor,
                            device=expected_file.device,
                            inode=expected_file.inode,
                            directory=False,
                            link_count=1,
                        )
                        os.lseek(file_descriptor, 0, os.SEEK_SET)
                        pinned_snapshot, _ = _stable_file_digest(
                            file_descriptor,
                            max_bytes=MAX_BUNDLE_UNCOMPRESSED_BYTES,
                        )
                        if pinned_snapshot != expected_file:
                            restore_unknown(descriptor, temporary_name, child_name)
                            raise LifecycleError(
                                "deletion target file changed before removal"
                            )
                        _assert_named_descriptor_identity(
                            descriptor,
                            temporary_name,
                            file_descriptor,
                            device=expected_file.device,
                            inode=expected_file.inode,
                            directory=False,
                            link_count=1,
                        )
                        os.unlink(temporary_name, dir_fd=descriptor)
                    finally:
                        try:
                            os.close(file_descriptor)
                        except OSError:
                            pass
                else:
                    raise LifecycleError("deletion target contains an unverified entry")
                _fsync_directory_descriptor(descriptor)

        delete_contents(root_descriptor, "")
        _assert_named_descriptor_identity(
            parent_descriptor,
            safe_name,
            root_descriptor,
            device=expected.root_device,
            inode=expected.root_inode,
            directory=True,
        )
        os.rmdir(safe_name, dir_fd=parent_descriptor)
        _fsync_directory_descriptor(parent_descriptor)
    except ArtifactValidationError as exc:
        raise LifecycleError("deletion target could not be verified") from exc
    except OSError as exc:
        raise LifecycleError(
            f"descriptor-rooted deletion failed: {exc.strerror or type(exc).__name__}"
        ) from exc
    finally:
        if root_descriptor is not None:
            try:
                os.close(root_descriptor)
            except OSError:
                pass
        _close_descriptors(parent_descriptors)


def _verify_bundle_payload(
    payload: bytes,
    *,
    expected_kind: str,
    expected_output_id: str,
    artifacts: tuple[Mapping[str, Any], ...],
) -> dict[str, bytes]:
    """Verify one bundle against the output manifest's exact artifact set."""

    if expected_kind not in _BUNDLE_CATEGORIES:
        raise ArtifactValidationError(f"unknown bundle kind: {expected_kind!r}")
    expected_files = [
        {
            "artifact_id": artifact["artifact_id"],
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "size_bytes": artifact["size_bytes"],
        }
        for artifact in artifacts
        if artifact.get("category") in _BUNDLE_CATEGORIES[expected_kind]
    ]
    expected_files.sort(key=lambda item: str(item["path"]))
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ArtifactValidationError("bundle is not a valid ZIP") from exc
    extracted: dict[str, bytes] = {}
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_BUNDLE_ENTRIES:
            raise ArtifactValidationError("bundle entry limit exceeded")
        total_size = sum(info.file_size for info in infos)
        if total_size > MAX_BUNDLE_UNCOMPRESSED_BYTES:
            raise ArtifactValidationError("bundle expansion limit exceeded")
        names = validate_unique_paths(info.filename for info in infos)
        if "bundle-content-manifest.json" not in names:
            raise ArtifactValidationError("bundle content manifest is missing")
        if archive.getinfo("bundle-content-manifest.json").file_size > MAX_BUNDLE_METADATA_BYTES:
            raise ArtifactValidationError("bundle content manifest exceeds its metadata limit")
        for info in infos:
            file_type = (info.external_attr >> 16) & 0o170000
            if file_type == stat.S_IFLNK:
                raise ArtifactValidationError(
                    f"symlink entry is forbidden: {info.filename!r}"
                )
            if (
                info.file_size
                and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO
            ):
                raise ArtifactValidationError(
                    f"bundle compression ratio exceeded: {info.filename!r}"
                )
        manifest = parse_json_strict(archive.read("bundle-content-manifest.json"))
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"schema_version", "output_id", "kind", "files"}
            or manifest.get("schema_version") != "elmos.autonomous-qa.bundle.v1"
            or manifest.get("output_id") != expected_output_id
            or manifest.get("kind") != expected_kind
        ):
            raise ArtifactValidationError("bundle content manifest identity mismatch")
        files = manifest.get("files")
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise ArtifactValidationError("bundle content manifest files are invalid")
        normalized_files: list[dict[str, Any]] = []
        for item in files:
            if set(item) != {"artifact_id", "path", "sha256", "size_bytes"}:
                raise ArtifactValidationError("bundle content manifest entry is ambiguous")
            path = normalize_relative_path(item.get("path"))
            digest = require_sha256(item.get("sha256"), field="bundle file sha256")
            size = item.get("size_bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ArtifactValidationError("bundle file size is invalid")
            artifact_id = _metadata_value(item.get("artifact_id"), "artifact_id")
            normalized_files.append(
                {
                    "artifact_id": artifact_id,
                    "path": path,
                    "sha256": digest,
                    "size_bytes": size,
                }
            )
        normalized_files.sort(key=lambda item: str(item["path"]))
        if normalized_files != expected_files:
            raise ArtifactValidationError(
                "bundle content manifest does not match the output artifact manifest"
            )
        payload_names = set(names) - {"bundle-content-manifest.json"}
        if payload_names != {str(item["path"]) for item in expected_files}:
            raise ArtifactValidationError("bundle payload does not match its content manifest")
        for item in expected_files:
            path = str(item["path"])
            data = archive.read(path)
            if len(data) != item["size_bytes"] or sha256_bytes(data) != item["sha256"]:
                raise ArtifactValidationError(f"bundle payload hash mismatch: {path!r}")
            extracted[path] = data
        if archive.testzip() is not None:
            raise ArtifactValidationError("bundle CRC verification failed")
    return extracted


def _scan_artifact_content(record_category: str, path: str, data: bytes) -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(data):
            raise ArtifactValidationError(f"possible secret in artifact {path!r}")
    if record_category != "test_source":
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactValidationError(f"test source is not UTF-8: {path!r}") from exc
    for label, patterns in (
        ("placeholder", _PLACEHOLDER_PATTERNS),
        ("assert-true", _ASSERT_TRUE_PATTERNS),
        ("disabled test", _DISABLED_TEST_PATTERNS),
    ):
        if any(pattern.search(text) for pattern in patterns):
            raise ArtifactValidationError(f"{label} pattern in test source {path!r}")


def _bounded_metadata_refs(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ArtifactValidationError(f"{field} must be a tuple")
    if len(values) > MAX_REFERENCES_PER_ARTIFACT:
        raise ArtifactValidationError(f"{field} exceeds the per-artifact limit")
    normalized = tuple(sorted({_metadata_value(value, field) for value in values}))
    if len(normalized) != len(values):
        raise ArtifactValidationError(f"{field} contains duplicate references")
    return normalized


def _remove_exact_temporary_link(
    parent_descriptor: int,
    temporary_name: str,
    pinned_descriptor: int,
    creation: _EmbeddedCreation,
) -> bool:
    """Remove only this atomic write's temporary hardlink before target rollback."""

    try:
        pinned = os.fstat(pinned_descriptor)
        if (
            not stat.S_ISREG(pinned.st_mode)
            or (int(pinned.st_dev), int(pinned.st_ino))
            != (creation.device, creation.inode)
        ):
            return False
        try:
            named = os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return pinned.st_nlink == 1
        if (int(named.st_dev), int(named.st_ino)) != (
            creation.device,
            creation.inode,
        ):
            # The owned temp link was already removed and an unknown name replaced it.
            return pinned.st_nlink == 1
        if pinned.st_nlink != 2:
            return False
        _assert_named_descriptor_identity(
            parent_descriptor,
            temporary_name,
            pinned_descriptor,
            device=creation.device,
            inode=creation.inode,
            directory=False,
            link_count=2,
        )
        os.unlink(temporary_name, dir_fd=parent_descriptor)
        after = os.fstat(pinned_descriptor)
        removed = (
            (int(after.st_dev), int(after.st_ino))
            == (creation.device, creation.inode)
            and after.st_nlink == 1
        )
        if not removed:
            return False
        try:
            _fsync_directory_descriptor(parent_descriptor)
        except OSError:
            # The exact temporary namespace link is already gone. Continue with
            # exact target rollback so a sync failure cannot strand the target.
            pass
        return True
    except (LifecycleError, OSError):
        return False


def _write_bytes_atomic(path: Path, data: bytes, mode: int = 0o644) -> None:
    descriptors: list[int] = []
    file_descriptor: int | None = None
    temporary_name = f".{path.name}.tmp-{uuid.uuid4().hex}"
    temporary_present = False
    installed = False
    creation: _EmbeddedCreation | None = None
    try:
        descriptors = _open_directory_chain_nofollow(path.parent, create=True)
        parent_descriptor = descriptors[-1]
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        file_descriptor = os.open(
            temporary_name, flags, mode, dir_fd=parent_descriptor
        )
        temporary_present = True
        remaining = memoryview(data)
        while remaining:
            written = os.write(file_descriptor, remaining)
            if written <= 0:
                raise OSError(errno.EIO, "short artifact write")
            remaining = remaining[written:]
        os.fchmod(file_descriptor, mode)
        os.fsync(file_descriptor)
        metadata = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size != len(data)
        ):
            raise PublicationError("atomic output staging identity is invalid")
        creation = _EmbeddedCreation(
            relative_path=path.as_posix(),
            parent_descriptor=parent_descriptor,
            file_name=path.name,
            device=int(metadata.st_dev),
            inode=int(metadata.st_ino),
            size_bytes=len(data),
            sha256=sha256_bytes(data),
        )
        try:
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise PublicationError(f"refusing to overwrite existing output: {path}") from exc
        installed = True
        os.unlink(temporary_name, dir_fd=parent_descriptor)
        temporary_present = False
        _fsync_directory_descriptor(parent_descriptor)
    except BaseException as exc:
        if installed and creation is not None:
            if temporary_present:
                if file_descriptor is None or not _remove_exact_temporary_link(
                    creation.parent_descriptor,
                    temporary_name,
                    file_descriptor,
                    creation,
                ):
                    raise PublicationError(
                        "atomic write failed and its exact temporary link "
                        "could not be rolled back"
                    ) from exc
                temporary_present = False
            if not _remove_pinned_file_nofollow(creation):
                raise PublicationError(
                    "atomic write failed and its exact installed inode could not be rolled back"
                ) from exc
            installed = False
        raise
    finally:
        if temporary_present and descriptors:
            try:
                os.unlink(temporary_name, dir_fd=descriptors[-1])
            except OSError:
                pass
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        _close_descriptors(descriptors)


def _remove_pinned_file_nofollow(creation: _EmbeddedCreation) -> bool:
    """Remove only the pinned embedded inode; retain and report any unknown replacement."""

    source_descriptor: int | None = None
    tombstone_descriptor: int | None = None
    tombstone = ".elmos-rollback-" + canonical_digest(
        {
            "path": creation.relative_path,
            "device": creation.device,
            "inode": creation.inode,
        }
    )[:32]
    expected = _TreeFile(
        device=creation.device,
        inode=creation.inode,
        size_bytes=creation.size_bytes,
        sha256=creation.sha256,
    )
    try:
        try:
            source_descriptor = os.open(
                creation.file_name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=creation.parent_descriptor,
            )
        except FileNotFoundError:
            try:
                tombstone_descriptor = os.open(
                    tombstone,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=creation.parent_descriptor,
                )
            except FileNotFoundError:
                return True
            tombstone_snapshot, _ = _stable_file_digest(
                tombstone_descriptor,
                max_bytes=max(MAX_ARTIFACT_BYTES, creation.size_bytes),
            )
            if tombstone_snapshot != expected:
                return False
            _assert_named_descriptor_identity(
                creation.parent_descriptor,
                tombstone,
                tombstone_descriptor,
                device=creation.device,
                inode=creation.inode,
                directory=False,
                link_count=1,
            )
            os.unlink(tombstone, dir_fd=creation.parent_descriptor)
            _fsync_directory_descriptor(creation.parent_descriptor)
            return True
        source_snapshot, _ = _stable_file_digest(
            source_descriptor,
            max_bytes=max(MAX_ARTIFACT_BYTES, creation.size_bytes),
        )
        if source_snapshot != expected:
            return False
        _assert_named_descriptor_identity(
            creation.parent_descriptor,
            creation.file_name,
            source_descriptor,
            device=creation.device,
            inode=creation.inode,
            directory=False,
            link_count=1,
        )
        _renameat_no_replace(
            creation.parent_descriptor,
            creation.file_name,
            creation.parent_descriptor,
            tombstone,
        )
        _fsync_directory_descriptor(creation.parent_descriptor)
        tombstone_descriptor = os.open(
            tombstone,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=creation.parent_descriptor,
        )
        tombstone_snapshot, _ = _stable_file_digest(
            tombstone_descriptor,
            max_bytes=max(MAX_ARTIFACT_BYTES, creation.size_bytes),
        )
        if tombstone_snapshot != expected:
            try:
                _renameat_no_replace(
                    creation.parent_descriptor,
                    tombstone,
                    creation.parent_descriptor,
                    creation.file_name,
                )
                _fsync_directory_descriptor(creation.parent_descriptor)
            except OSError:
                pass
            return False
        _assert_named_descriptor_identity(
            creation.parent_descriptor,
            tombstone,
            tombstone_descriptor,
            device=creation.device,
            inode=creation.inode,
            directory=False,
            link_count=1,
        )
        os.unlink(tombstone, dir_fd=creation.parent_descriptor)
        _fsync_directory_descriptor(creation.parent_descriptor)
        return True
    except (ArtifactValidationError, LifecycleError, OSError):
        return False
    finally:
        for descriptor in (tombstone_descriptor, source_descriptor):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def _install_embedded_file_atomic(
    path: Path,
    data: bytes,
    *,
    relative_path: str,
    expected_digest: str,
    expected_size: int,
) -> _EmbeddedCreation:
    """Install and pin one embedded file without an untracked post-install window."""

    descriptors: list[int] = []
    parent_pin = -1
    file_descriptor: int | None = None
    target_descriptor: int | None = None
    temporary_name = f".{path.name}.tmp-{uuid.uuid4().hex}"
    temporary_present = False
    installed = False
    creation: _EmbeddedCreation | None = None
    try:
        descriptors = _open_directory_chain_nofollow(path.parent, create=True)
        parent_pin = os.dup(descriptors[-1])
        _close_descriptors(descriptors)
        descriptors = []
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        file_descriptor = os.open(
            temporary_name, flags, 0o644, dir_fd=parent_pin
        )
        temporary_present = True
        remaining = memoryview(data)
        while remaining:
            written = os.write(file_descriptor, remaining)
            if written <= 0:
                raise OSError(errno.EIO, "short embedded artifact write")
            remaining = remaining[written:]
        os.fchmod(file_descriptor, 0o644)
        os.fsync(file_descriptor)
        metadata = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size != expected_size
            or len(data) != expected_size
            or sha256_bytes(data) != expected_digest
        ):
            raise PublicationError("embedded staging bytes do not match registration")
        creation = _EmbeddedCreation(
            relative_path=relative_path,
            parent_descriptor=parent_pin,
            file_name=path.name,
            device=int(metadata.st_dev),
            inode=int(metadata.st_ino),
            size_bytes=expected_size,
            sha256=expected_digest,
        )
        try:
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=parent_pin,
                dst_dir_fd=parent_pin,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise PublicationError(
                f"embedded materialization refuses to overwrite: {relative_path!r}"
            ) from exc
        installed = True
        os.unlink(temporary_name, dir_fd=parent_pin)
        temporary_present = False
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        file_descriptor = None
        _fsync_directory_descriptor(parent_pin)
        target_descriptor = os.open(
            path.name,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_pin,
        )
        target_snapshot, _ = _stable_file_digest(
            target_descriptor, max_bytes=MAX_ARTIFACT_BYTES
        )
        if target_snapshot != _TreeFile(
            device=creation.device,
            inode=creation.inode,
            size_bytes=creation.size_bytes,
            sha256=creation.sha256,
        ):
            raise PublicationError(
                f"embedded materialization changed before pinning: {relative_path!r}"
            )
        parent_pin = -1
        return creation
    except BaseException as exc:
        if temporary_present and parent_pin >= 0:
            try:
                os.unlink(temporary_name, dir_fd=parent_pin)
                temporary_present = False
            except OSError:
                pass
        if installed and creation is not None:
            if not _remove_pinned_file_nofollow(creation):
                raise PublicationError(
                    "embedded install failed and its exact inode could not be rolled back"
                ) from exc
        raise
    finally:
        for descriptor in (target_descriptor, file_descriptor):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if temporary_present and parent_pin >= 0:
            try:
                os.unlink(temporary_name, dir_fd=parent_pin)
            except OSError:
                pass
        _close_descriptors(descriptors)
        if parent_pin >= 0:
            try:
                os.close(parent_pin)
            except OSError:
                pass


class ArtifactPublisher:
    """Register immutable staging files and publish verified deterministic ZIPs."""

    def __init__(self, plan: OutputPlan) -> None:
        self.plan = plan
        self._records: dict[str, ArtifactRecord] = {}
        self._content: dict[str, bytes] = {}
        self._path_keys: dict[str, str] = {}
        self._artifact_ids: set[str] = set()
        self._total_size_bytes = 0

    @property
    def records(self) -> tuple[ArtifactRecord, ...]:
        return tuple(self._records[path] for path in sorted(self._records))

    def register_file(
        self,
        relative_path: str,
        *,
        artifact_id: str,
        category: str,
        role: str,
        producer: str,
        required: bool = True,
        validation_status: str = "generated",
        requirement_refs: tuple[str, ...] = (),
        test_case_refs: tuple[str, ...] = (),
        risk_justification: str | None = None,
    ) -> ArtifactRecord:
        if len(self._records) >= MAX_REGISTERED_ARTIFACTS:
            raise ArtifactValidationError("registered artifact count limit exceeded")
        path = normalize_relative_path(relative_path)
        collision_key = path_collision_key(path)
        if path in self._records or collision_key in self._path_keys:
            other = self._path_keys.get(collision_key, path)
            raise ArtifactValidationError(f"duplicate or colliding paths: {other!r}, {path!r}")
        artifact_id = _metadata_value(artifact_id, "artifact_id")
        category = _metadata_value(category, "category")
        if artifact_id in self._artifact_ids:
            raise ArtifactValidationError(f"duplicate or empty artifact_id: {artifact_id!r}")
        if category not in _ARTIFACT_CATEGORIES:
            raise ArtifactValidationError(f"unknown artifact category: {category!r}")
        if category == "certificate":
            raise CertificationDenied(
                "certificate artifacts require an authorized external gate and independent evidence"
            )
        role = _metadata_value(role, "role")
        producer = _metadata_value(producer, "producer")
        validation_status = _metadata_value(validation_status, "validation_status")
        if role not in _ARTIFACT_ROLES:
            raise ArtifactValidationError(f"unsupported artifact role: {role!r}")
        if producer not in _ARTIFACT_PRODUCERS:
            raise ArtifactValidationError(f"unsupported artifact producer: {producer!r}")
        if validation_status in _FORBIDDEN_EVIDENCE_LABELS:
            raise CertificationDenied(
                f"artifact status {validation_status!r} requires an authorized external gate"
            )
        if validation_status not in _ARTIFACT_VALIDATION_STATUSES:
            raise ArtifactValidationError(
                f"unsupported artifact validation status: {validation_status!r}"
            )
        if not isinstance(required, bool):
            raise ArtifactValidationError("required must be a boolean")
        normalized_requirement_refs = _bounded_metadata_refs(
            requirement_refs, "requirement_refs"
        )
        normalized_test_case_refs = _bounded_metadata_refs(
            test_case_refs, "test_case_refs"
        )
        if risk_justification is not None:
            risk_justification = _metadata_value(risk_justification, "risk_justification")
        if category == "test_source" and not test_case_refs:
            raise ArtifactValidationError(f"test source lacks test-case refs: {path!r}")
        if category == "test_source" and not requirement_refs and not risk_justification:
            raise ArtifactValidationError(f"test source lacks requirement/risk refs: {path!r}")
        if required and not (
            normalized_requirement_refs or normalized_test_case_refs or risk_justification
        ):
            raise ArtifactValidationError(f"required artifact lacks traceability: {path!r}")
        data = _read_regular_file_nofollow(self.plan.staging_root, path)
        if self._total_size_bytes + len(data) > MAX_REGISTERED_ARTIFACT_BYTES:
            raise ArtifactValidationError("registered artifact aggregate byte limit exceeded")
        _scan_artifact_content(category, path, data)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            path=path,
            category=category,
            role=role,
            sha256=sha256_bytes(data),
            size_bytes=len(data),
            producer=producer,
            required=required,
            validation_status=validation_status,
            requirement_refs=normalized_requirement_refs,
            test_case_refs=normalized_test_case_refs,
            risk_justification=risk_justification,
        )
        self._records[path] = record
        self._content[path] = data
        self._path_keys[collision_key] = path
        self._artifact_ids.add(artifact_id)
        self._total_size_bytes += len(data)
        return record

    def _inventory_files(self) -> tuple[str, ...]:
        root = self.plan.staging_root
        paths: list[str] = []
        collision_keys: dict[str, str] = {}
        entry_count = 0
        descriptors: list[int] = []
        directory_flag = getattr(os, "O_DIRECTORY", None)
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if directory_flag is None or nofollow is None:
            raise ArtifactValidationError("descriptor-rooted staging inventory is unavailable")

        def walk(descriptor: int, prefix: str, depth: int) -> None:
            nonlocal entry_count
            if depth > MAX_STAGING_TREE_DEPTH:
                raise ArtifactValidationError("staging tree depth limit exceeded")
            before_directory = os.fstat(descriptor)
            before_names = _bounded_directory_names(
                descriptor,
                maximum=max(0, MAX_STAGING_TREE_ENTRIES - entry_count),
                field="staging tree",
            )
            if len(before_names) != len(set(before_names)):
                raise ArtifactValidationError("staging directory entries are ambiguous")
            for name in sorted(before_names):
                if not isinstance(name, str) or not name or "/" in name or name in {".", ".."}:
                    raise ArtifactValidationError("staging entry name is invalid")
                relative = normalize_relative_path(f"{prefix}/{name}" if prefix else name)
                collision_key = path_collision_key(relative)
                other = collision_keys.get(collision_key)
                if other is not None:
                    raise ArtifactValidationError(
                        f"staging paths collide: {other!r}, {relative!r}"
                    )
                collision_keys[collision_key] = relative
                entry_count += 1
                if entry_count > MAX_STAGING_TREE_ENTRIES:
                    raise ArtifactValidationError("staging tree entry limit exceeded")
                metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode):
                    child = os.open(
                        name,
                        os.O_RDONLY
                        | directory_flag
                        | nofollow
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=descriptor,
                    )
                    try:
                        opened = os.fstat(child)
                        if (opened.st_dev, opened.st_ino) != (
                            metadata.st_dev,
                            metadata.st_ino,
                        ):
                            raise ArtifactValidationError(
                                f"staging directory changed: {relative!r}"
                            )
                        walk(child, relative, depth + 1)
                        named_after = os.stat(
                            name, dir_fd=descriptor, follow_symlinks=False
                        )
                        opened_after = os.fstat(child)
                        if (
                            named_after.st_dev,
                            named_after.st_ino,
                            opened_after.st_dev,
                            opened_after.st_ino,
                        ) != (
                            metadata.st_dev,
                            metadata.st_ino,
                            metadata.st_dev,
                            metadata.st_ino,
                        ):
                            raise ArtifactValidationError(
                                f"staging directory was replaced: {relative!r}"
                            )
                    finally:
                        try:
                            os.close(child)
                        except OSError:
                            pass
                elif stat.S_ISREG(metadata.st_mode):
                    paths.append(relative)
                    if len(paths) > MAX_REGISTERED_ARTIFACTS:
                        raise ArtifactValidationError("staging file count limit exceeded")
                else:
                    raise ArtifactValidationError(
                        f"staging special entry is forbidden: {relative!r}"
                    )
            after_names = _bounded_directory_names(
                descriptor,
                maximum=MAX_STAGING_TREE_ENTRIES,
                field="staging tree",
            )
            after_directory = os.fstat(descriptor)
            if set(after_names) != set(before_names) or (
                before_directory.st_dev,
                before_directory.st_ino,
                before_directory.st_mode,
                before_directory.st_uid,
                before_directory.st_gid,
                before_directory.st_mtime_ns,
                before_directory.st_ctime_ns,
            ) != (
                after_directory.st_dev,
                after_directory.st_ino,
                after_directory.st_mode,
                after_directory.st_uid,
                after_directory.st_gid,
                after_directory.st_mtime_ns,
                after_directory.st_ctime_ns,
            ):
                raise ArtifactValidationError("staging tree changed during inventory")

        try:
            descriptors = _open_directory_chain_nofollow(root)
            walk(descriptors[-1], "", 0)
        except OSError as exc:
            raise ArtifactValidationError(
                f"cannot safely inventory staging root: "
                f"{exc.strerror or type(exc).__name__}"
            ) from exc
        finally:
            _close_descriptors(descriptors)
        return validate_unique_paths(paths)

    def validate(self) -> None:
        inventory_before = self._inventory_files()
        inventory = set(inventory_before)
        registered = set(self._records)
        if inventory != registered:
            missing = sorted(inventory - registered)
            absent = sorted(registered - inventory)
            raise ArtifactValidationError(
                f"manifest/file mismatch; unmanifested={missing}, missing={absent}"
            )
        for record in self.records:
            data = _read_regular_file_nofollow(self.plan.staging_root, record.path)
            if (
                len(data) != record.size_bytes
                or sha256_bytes(data) != record.sha256
                or data != self._content[record.path]
            ):
                raise ArtifactValidationError(f"artifact changed after registration: {record.path!r}")
            _scan_artifact_content(record.category, record.path, data)
        inventory_after = self._inventory_files()
        if inventory_after != inventory_before:
            raise ArtifactValidationError("staging tree changed during validation")

    def build_bundle(self, kind: str) -> tuple[bytes, str]:
        if kind not in _BUNDLE_CATEGORIES:
            raise ArtifactValidationError(f"unknown bundle kind: {kind!r}")
        self.validate()
        selected = [
            record for record in self.records if record.category in _BUNDLE_CATEGORIES[kind]
        ]
        content_manifest = {
            "schema_version": "elmos.autonomous-qa.bundle.v1",
            "output_id": self.plan.output_id,
            "kind": kind,
            "files": [
                {
                    "artifact_id": record.artifact_id,
                    "path": record.path,
                    "sha256": record.sha256,
                    "size_bytes": record.size_bytes,
                }
                for record in selected
            ],
        }
        content_manifest_bytes = canonical_json_bytes(content_manifest)
        if len(content_manifest_bytes) > MAX_BUNDLE_METADATA_BYTES:
            raise ArtifactValidationError("bundle content manifest exceeds its metadata limit")
        if (
            sum(record.size_bytes for record in selected) + len(content_manifest_bytes)
            > MAX_BUNDLE_UNCOMPRESSED_BYTES
        ):
            raise ArtifactValidationError("bundle payload and metadata exceed the expansion limit")
        stream = io.BytesIO()
        with zipfile.ZipFile(
            stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for record in selected:
                info = zipfile.ZipInfo(record.path, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o644 & 0xFFFF) << 16
                archive.writestr(info, self._content[record.path])
            info = zipfile.ZipInfo("bundle-content-manifest.json", FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, content_manifest_bytes)
        payload = stream.getvalue()
        self._verify_bundle(payload, kind)
        return payload, sha256_bytes(payload)

    def _verify_bundle(self, payload: bytes, expected_kind: str) -> None:
        extracted = _verify_bundle_payload(
            payload,
            expected_kind=expected_kind,
            expected_output_id=self.plan.output_id,
            artifacts=tuple(record.as_dict() for record in self.records),
        )
        directory_name = f".autonomous-qa-verify-{uuid.uuid4().hex}"
        clean_root = safe_join(self.plan.publication_root, directory_name)
        descriptors: list[int] = []
        root_descriptor = -1
        parent_pin = -1
        candidate: _PinnedCandidate | None = None
        identity: tuple[int, int] | None = None
        try:
            descriptors = _open_directory_chain_nofollow(
                self.plan.publication_root, create=True
            )
            parent_descriptor = descriptors[-1]
            _require_private_directory_descriptor(
                parent_descriptor, "bundle verification parent"
            )
            os.mkdir(directory_name, mode=0o700, dir_fd=parent_descriptor)
            root_descriptor = os.open(
                directory_name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_descriptor,
            )
            metadata = os.fstat(root_descriptor)
            identity = int(metadata.st_dev), int(metadata.st_ino)
            cleanup_snapshot = _verify_exact_tree_descriptor(
                root_descriptor, expected_files={}, exact_bytes={}
            )
            parent_pin = os.dup(parent_descriptor)
            candidate = _PinnedCandidate(
                path=clean_root,
                parent_descriptor=parent_pin,
                root_descriptor=root_descriptor,
                root_device=identity[0],
                root_inode=identity[1],
                cleanup_snapshot=cleanup_snapshot,
            )
            parent_pin = -1
            root_descriptor = -1
            _close_descriptors(descriptors)
            descriptors = []
            expected_files: dict[str, tuple[str, int]] = {}
            for path, data in sorted(extracted.items()):
                destination = safe_join(clean_root, path)
                _write_bytes_atomic(destination, data)
                expected_files[path] = (sha256_bytes(data), len(data))
                self._checkpoint_candidate(
                    candidate,
                    expected_files,
                    exact_bytes={path: data},
                )
        finally:
            if candidate is not None:
                try:
                    self._discard_candidate(candidate)
                finally:
                    _close_candidate(candidate)
            elif descriptors and identity is not None:
                try:
                    _assert_named_descriptor_identity(
                        descriptors[-1],
                        directory_name,
                        root_descriptor,
                        device=identity[0],
                        inode=identity[1],
                        directory=True,
                    )
                    os.rmdir(directory_name, dir_fd=descriptors[-1])
                    _fsync_directory_descriptor(descriptors[-1])
                except (LifecycleError, OSError):
                    pass
            if root_descriptor >= 0:
                try:
                    os.close(root_descriptor)
                except OSError:
                    pass
            if parent_pin >= 0:
                try:
                    os.close(parent_pin)
                except OSError:
                    pass
            _close_descriptors(descriptors)

    def _required_bundle_kinds(self) -> tuple[str, ...]:
        if self.plan.run_mode == "plan-only":
            return ()
        kinds = ["project-with-tests", "tests-only"]
        if self.plan.run_mode in {"verify", "repair", "certify", "continuous"} or any(
            record.category in _BUNDLE_CATEGORIES["qa-evidence"]
            for record in self.records
        ):
            kinds.append("qa-evidence")
        if self.plan.run_mode == "repair" or any(
            record.category == "patch" for record in self.records
        ):
            kinds.append("repair-patches")
        return tuple(kinds)

    def _validate_delivery_coverage(self, status: str) -> None:
        if status != "verified" or self.plan.run_mode == "plan-only":
            return
        bundle_kinds = self._required_bundle_kinds()
        for record in self.records:
            delivered = any(
                record.category in _BUNDLE_CATEGORIES[kind] for kind in bundle_kinds
            )
            if (
                self.plan.output_mode in {OutputMode.SIDECAR, OutputMode.BOTH}
                and record.category in _BUNDLE_CATEGORIES["project-with-tests"]
            ):
                delivered = True
            if (
                self.plan.output_mode in {OutputMode.EMBEDDED, OutputMode.BOTH}
                and record.category in _EMBEDDED_CATEGORIES
            ):
                delivered = True
            if not delivered:
                raise ArtifactValidationError(
                    f"registered artifact has no materialization or required-bundle channel: "
                    f"{record.path!r}"
                )

    def publish(
        self,
        *,
        requested_status: str = "verified",
        partial_on_failure: bool = True,
    ) -> PublishedOutput:
        if requested_status in {"certified", "signed", "released", "deployed"}:
            raise CertificationDenied(
                "this core cannot sign, certify, release, or deploy; use an authorized "
                "external gate with independently verified evidence"
            )
        if requested_status in {"partial", "failed"}:
            raise PublicationError(
                "partial and failed publication statuses may only be derived from "
                "a captured publication failure"
            )
        if requested_status != "verified":
            raise PublicationError(f"unsupported publication status: {requested_status!r}")
        try:
            return self._publish_verified(requested_status)
        except CertificationDenied:
            raise
        except Exception as exc:
            if not partial_on_failure:
                raise
            return self._publish_failure(exc)

    def _candidate_root(self) -> _PinnedCandidate:
        final_root = self.plan.final_root
        candidate = final_root.parent / f".pending-{self.plan.output_id}-{uuid.uuid4().hex}"
        descriptors: list[int] = []
        parent_pin = -1
        root_descriptor = -1
        created = False
        identity: tuple[int, int] | None = None
        try:
            descriptors = _open_directory_chain_nofollow(final_root.parent, create=True)
            parent_descriptor = descriptors[-1]
            _require_private_directory_descriptor(
                parent_descriptor, "publication candidate parent"
            )
            try:
                os.stat(final_root.name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise PublicationError(f"immutable output already exists: {final_root}")
            os.mkdir(candidate.name, mode=0o700, dir_fd=parent_descriptor)
            created = True
            root_descriptor = os.open(
                candidate.name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_descriptor,
            )
            root_metadata = os.fstat(root_descriptor)
            identity = int(root_metadata.st_dev), int(root_metadata.st_ino)
            cleanup_snapshot = _verify_exact_tree_descriptor(
                root_descriptor,
                expected_files={},
                exact_bytes={},
            )
            parent_pin = os.dup(parent_descriptor)
            _fsync_directory_descriptor(parent_descriptor)
            pinned = _PinnedCandidate(
                path=candidate,
                parent_descriptor=parent_pin,
                root_descriptor=root_descriptor,
                root_device=identity[0],
                root_inode=identity[1],
                cleanup_snapshot=cleanup_snapshot,
            )
            parent_pin = -1
            root_descriptor = -1
            created = False
            return pinned
        except OSError as exc:
            raise PublicationError(
                f"cannot create atomic publication candidate: {exc.strerror or type(exc).__name__}"
            ) from exc
        finally:
            if (
                created
                and descriptors
                and identity is not None
                and root_descriptor >= 0
            ):
                try:
                    _assert_named_descriptor_identity(
                        descriptors[-1],
                        candidate.name,
                        root_descriptor,
                        device=identity[0],
                        inode=identity[1],
                        directory=True,
                    )
                    os.rmdir(candidate.name, dir_fd=descriptors[-1])
                    _fsync_directory_descriptor(descriptors[-1])
                except (LifecycleError, OSError):
                    pass
            if root_descriptor >= 0:
                try:
                    os.close(root_descriptor)
                except OSError:
                    pass
            if parent_pin >= 0:
                try:
                    os.close(parent_pin)
                except OSError:
                    pass
            _close_descriptors(descriptors)

    @staticmethod
    def _checkpoint_candidate(
        candidate: _PinnedCandidate,
        expected_files: Mapping[str, tuple[str, int]],
        *,
        exact_bytes: Mapping[str, bytes] | None = None,
    ) -> _TreeSnapshot:
        """Advance cleanup authority only after an exact owned-tree check."""

        snapshot = _verify_exact_tree_descriptor(
            candidate.root_descriptor,
            expected_files=expected_files,
            exact_bytes={} if exact_bytes is None else exact_bytes,
        )
        candidate.cleanup_snapshot = snapshot
        return snapshot

    def _publish_verified(self, status: str) -> PublishedOutput:
        self.validate()
        self._validate_delivery_coverage(status)
        candidate = self._candidate_root()
        bundle_records: list[dict[str, Any]] = []
        bundle_digests: dict[str, str] = {}
        embedded_created: list[_EmbeddedCreation] = []
        committed = False
        try:
            materialize = status == "verified" and self.plan.run_mode != "plan-only"
            expected_files: dict[str, tuple[str, int]] = {}
            if materialize:
                embedded_created = self._materialize_project(
                    candidate, expected_files
                )
                for kind in self._required_bundle_kinds():
                    payload, digest = self.build_bundle(kind)
                    filename = f"{self.plan.output_id}-{kind}.zip"
                    relative = f"bundles/{filename}"
                    _write_bytes_atomic(safe_join(candidate.path, relative), payload)
                    expected_files[relative] = (digest, len(payload))
                    self._checkpoint_candidate(candidate, expected_files)
                    bundle_digests[kind] = digest
                    bundle_records.append(
                        {
                            "kind": kind,
                            "path": relative,
                            "sha256": digest,
                            "size_bytes": len(payload),
                            "status": "verified",
                        }
                    )
            manifest = self._manifest(status, bundle_records, failure=None)
            manifest_bytes = canonical_json_bytes(manifest)
            manifest_path = safe_join(candidate.path, "manifests/project-output-manifest.json")
            _write_bytes_atomic(manifest_path, manifest_bytes)
            expected_files["manifests/project-output-manifest.json"] = (
                sha256_bytes(manifest_bytes),
                len(manifest_bytes),
            )
            self._checkpoint_candidate(
                candidate,
                expected_files,
                exact_bytes={
                    "manifests/project-output-manifest.json": manifest_bytes,
                },
            )
            checksums = _checksums_from_expected(expected_files)
            _write_bytes_atomic(
                safe_join(candidate.path, "manifests/checksums.sha256"),
                checksums,
            )
            expected_files["manifests/checksums.sha256"] = (
                sha256_bytes(checksums),
                len(checksums),
            )
            verified_candidate = self._checkpoint_candidate(
                candidate,
                expected_files,
                exact_bytes={
                    "manifests/project-output-manifest.json": manifest_bytes,
                    "manifests/checksums.sha256": checksums,
                },
            )
            durable = _rename_no_replace(
                candidate.path,
                self.plan.final_root,
                expected_source_identity=(
                    verified_candidate.root_device,
                    verified_candidate.root_inode,
                ),
                expected_source_snapshot=verified_candidate,
            )
            committed = True
            result = PublishedOutput(
                tenant_id=self.plan.tenant_id,
                output_id=self.plan.output_id,
                project_id=self.plan.project_id,
                revision_id=self.plan.revision_id,
                run_id=self.plan.run_id,
                status=status,
                root=self.plan.final_root,
                manifest_digest=sha256_bytes(manifest_bytes),
                bundle_digests=dict(bundle_digests),
                durability_status=(
                    "DURABLE" if durable else "COMMITTED_DURABILITY_UNKNOWN"
                ),
            )
            _close_candidate(candidate)
            self._release_embedded_pins(embedded_created)
            embedded_created = []
            return result
        except BaseException:
            self._rollback_embedded(embedded_created)
            raise
        finally:
            if not committed:
                self._discard_candidate(candidate)
            _close_candidate(candidate)

    def _materialize_project(
        self,
        candidate: _PinnedCandidate,
        expected_files: dict[str, tuple[str, int]],
    ) -> list[_EmbeddedCreation]:
        """Materialize registered project/test files without overwriting a worktree."""

        if self.plan.output_mode in {OutputMode.SIDECAR, OutputMode.BOTH}:
            sidecar = safe_join(candidate.path, "project")
            for record in self.records:
                if record.category not in _BUNDLE_CATEGORIES["project-with-tests"]:
                    continue
                destination = safe_join(sidecar, record.path)
                _write_bytes_atomic(
                    destination,
                    self._content[record.path],
                )
                expected_files[f"project/{record.path}"] = (
                    record.sha256,
                    record.size_bytes,
                )
                self._checkpoint_candidate(candidate, expected_files)

        if self.plan.output_mode not in {OutputMode.EMBEDDED, OutputMode.BOTH}:
            return []
        assert self.plan.embedded_root is not None
        embedded_root = self.plan.embedded_root
        if embedded_root.is_symlink() or not embedded_root.is_dir():
            raise PublicationError("embedded_root must be an existing non-symlink worktree")
        selected = [
            record for record in self.records if record.category in _EMBEDDED_CATEGORIES
        ]
        destinations: list[tuple[ArtifactRecord, Path]] = []
        for record in selected:
            destination = safe_join(embedded_root, record.path)
            if destination.exists() or destination.is_symlink():
                raise PublicationError(
                    f"embedded materialization refuses to overwrite: {record.path!r}"
                )
            destinations.append((record, destination))

        created: list[_EmbeddedCreation] = []
        try:
            for record, destination in destinations:
                creation = _install_embedded_file_atomic(
                    destination,
                    self._content[record.path],
                    relative_path=record.path,
                    expected_digest=record.sha256,
                    expected_size=record.size_bytes,
                )
                try:
                    created.append(creation)
                except BaseException as exc:
                    removed = _remove_pinned_file_nofollow(creation)
                    try:
                        os.close(creation.parent_descriptor)
                    except OSError:
                        pass
                    if not removed:
                        raise PublicationError(
                            "embedded file could not be tracked or safely rolled back"
                        ) from exc
                    raise
            return created
        except BaseException:
            self._rollback_embedded(created)
            raise

    @staticmethod
    def _release_embedded_pins(created: list[_EmbeddedCreation]) -> None:
        for creation in created:
            try:
                os.close(creation.parent_descriptor)
            except OSError:
                pass

    def _rollback_embedded(self, created: list[_EmbeddedCreation]) -> None:
        if not created:
            return
        retained_unknown: list[str] = []
        for creation in reversed(created):
            try:
                if not _remove_pinned_file_nofollow(creation):
                    retained_unknown.append(creation.relative_path)
            except OSError:
                retained_unknown.append(creation.relative_path)
            finally:
                try:
                    os.close(creation.parent_descriptor)
                except OSError:
                    pass
        if retained_unknown:
            raise PublicationError(
                "rollback retained modified or unsafe embedded outputs: "
                + ", ".join(sorted(retained_unknown))
            )

    @staticmethod
    def _discard_candidate(candidate: _PinnedCandidate) -> None:
        try:
            pinned = os.fstat(candidate.root_descriptor)
            if (pinned.st_dev, pinned.st_ino) != (
                candidate.root_device,
                candidate.root_inode,
            ):
                raise PublicationError("publication candidate pin identity changed")
            current = os.stat(
                candidate.path.name,
                dir_fd=candidate.parent_descriptor,
                follow_symlinks=False,
            )
            if (current.st_dev, current.st_ino) != (
                candidate.root_device,
                candidate.root_inode,
            ):
                raise PublicationError("publication candidate path was replaced")
            _require_private_directory_descriptor(
                candidate.root_descriptor, "publication candidate"
            )
            current_snapshot = _snapshot_tree_from_descriptor(candidate.root_descriptor)
            if current_snapshot != candidate.cleanup_snapshot:
                raise PublicationError(
                    "publication candidate differs from its exact owned cleanup snapshot"
                )
            _delete_directory_tree_nofollow(
                candidate.path.parent,
                candidate.path.name,
                expected=candidate.cleanup_snapshot,
            )
        except FileNotFoundError:
            return
        except (ArtifactValidationError, LifecycleError, OSError) as exc:
            raise PublicationError("cannot safely remove publication candidate") from exc

    def _publish_failure(self, failure: Exception) -> PublishedOutput:
        candidate = self._candidate_root()
        status = "partial" if self._records else "failed"
        committed = False
        try:
            failure_envelope = {
                "type": type(failure).__name__,
                "message": str(failure),
            }
            manifest = self._manifest(
                status,
                [],
                failure=failure_envelope,
            )
            manifest_bytes = canonical_json_bytes(manifest)
            _write_bytes_atomic(
                safe_join(candidate.path, "manifests/project-output-manifest.json"), manifest_bytes
            )
            expected_files = {
                "manifests/project-output-manifest.json": (
                    sha256_bytes(manifest_bytes),
                    len(manifest_bytes),
                )
            }
            self._checkpoint_candidate(
                candidate,
                expected_files,
                exact_bytes={
                    "manifests/project-output-manifest.json": manifest_bytes,
                },
            )
            checksums = _checksums_from_expected(expected_files)
            _write_bytes_atomic(
                safe_join(candidate.path, "manifests/checksums.sha256"), checksums
            )
            expected_files["manifests/checksums.sha256"] = (
                sha256_bytes(checksums),
                len(checksums),
            )
            verified_candidate = self._checkpoint_candidate(
                candidate,
                expected_files,
                exact_bytes={
                    "manifests/project-output-manifest.json": manifest_bytes,
                    "manifests/checksums.sha256": checksums,
                },
            )
            durable = _rename_no_replace(
                candidate.path,
                self.plan.final_root,
                expected_source_identity=(
                    verified_candidate.root_device,
                    verified_candidate.root_inode,
                ),
                expected_source_snapshot=verified_candidate,
            )
            committed = True
            result = PublishedOutput(
                tenant_id=self.plan.tenant_id,
                output_id=self.plan.output_id,
                project_id=self.plan.project_id,
                revision_id=self.plan.revision_id,
                run_id=self.plan.run_id,
                status=status,
                root=self.plan.final_root,
                manifest_digest=sha256_bytes(manifest_bytes),
                bundle_digests={},
                durability_status=(
                    "DURABLE" if durable else "COMMITTED_DURABILITY_UNKNOWN"
                ),
                failure=failure_envelope,
            )
            _close_candidate(candidate)
            return result
        finally:
            if not committed:
                self._discard_candidate(candidate)
            _close_candidate(candidate)

    def _manifest(
        self,
        status: str,
        bundles: list[dict[str, Any]],
        failure: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "schema_version": "elmos.autonomous-qa.output.v1",
            "output_id": self.plan.output_id,
            "tenant_id": self.plan.tenant_id,
            "project_id": self.plan.project_id,
            "revision_id": self.plan.revision_id,
            "run_id": self.plan.run_id,
            "run_mode": self.plan.run_mode,
            "output_mode": self.plan.output_mode.value,
            "source_snapshot_digest": self.plan.source_snapshot_digest,
            "status": status,
            "created_at": self.plan.created_at,
            "artifacts": [record.as_dict() for record in self.records],
            "bundles": bundles,
            "materialization": {
                "mode": self.plan.output_mode.value,
                "embedded_test_artifacts": sum(
                    record.category in _EMBEDDED_CATEGORIES for record in self.records
                )
                if failure is None
                and status == "verified"
                and self.plan.run_mode != "plan-only"
                and self.plan.output_mode in {OutputMode.EMBEDDED, OutputMode.BOTH}
                else 0,
                "sidecar_artifacts": sum(
                    record.category in _BUNDLE_CATEGORIES["project-with-tests"]
                    for record in self.records
                )
                if failure is None
                and status == "verified"
                and self.plan.run_mode != "plan-only"
                and self.plan.output_mode in {OutputMode.SIDECAR, OutputMode.BOTH}
                else 0,
                "existing_files_overwritten": False,
            },
            "signed": False,
            "certified": False,
            "external_evidence_status": "NOT_RUN",
        }
        if failure is not None:
            manifest["failure"] = dict(failure)
        return manifest


class ArtifactLifecycleStore:
    """Durable stale/superseded/legal-hold/reference-safe output lifecycle."""

    _SCHEMA_KEY = "elmos.autonomous-qa.lifecycle"
    _PROCESS_FENCE_GUARD = threading.Lock()
    _PROCESS_FENCES: set[str] = set()
    _FENCE_FILE = ".lifecycle-gc.lock"
    _SCHEMA_METADATA_SQL = f"""
        CREATE TABLE lifecycle_schema (
            schema_key TEXT NOT NULL PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            physical_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CHECK (schema_key = '{_SCHEMA_KEY}'),
            CHECK (schema_version = {LIFECYCLE_SCHEMA_VERSION}),
            CHECK (
                length(physical_fingerprint) = 64
                AND physical_fingerprint NOT GLOB '*[^0-9a-f]*'
            ),
            CHECK (length(created_at) > 0)
        )
    """
    _SCHEMA_OUTPUTS_SQL = f"""
        CREATE TABLE lifecycle_outputs (
            tenant_id TEXT NOT NULL,
            output_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            output_path TEXT NOT NULL,
            manifest_digest TEXT NOT NULL,
            fs_device INTEGER NOT NULL,
            fs_inode INTEGER NOT NULL,
            state TEXT NOT NULL,
            legal_hold INTEGER NOT NULL DEFAULT 0,
            superseded_by TEXT,
            collecting_from TEXT,
            quarantine_path TEXT,
            quarantine_verified INTEGER NOT NULL DEFAULT 0,
            quarantine_snapshot BLOB,
            quarantine_snapshot_digest TEXT,
            collection_owner TEXT,
            collection_lease_until TEXT,
            collection_phase TEXT,
            layout_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, output_id),
            FOREIGN KEY (tenant_id, superseded_by)
                REFERENCES lifecycle_outputs (tenant_id, output_id) ON DELETE RESTRICT,
            CHECK (
                length(tenant_id) > 0 AND length(output_id) > 0
                AND length(project_id) > 0 AND length(revision_id) > 0
                AND length(run_id) > 0 AND length(output_path) > 0
            ),
            CHECK (
                length(manifest_digest) = 64
                AND manifest_digest NOT GLOB '*[^0-9a-f]*'
            ),
            CHECK (fs_device >= 0 AND fs_inode >= 0),
            CHECK (state IN ('active', 'stale', 'superseded', 'collecting', 'collected')),
            CHECK (legal_hold IN (0, 1)),
            CHECK (quarantine_verified IN (0, 1)),
            CHECK (layout_version = {LIFECYCLE_LAYOUT_VERSION}),
            CHECK (
                (quarantine_verified = 0
                    AND quarantine_snapshot IS NULL
                    AND quarantine_snapshot_digest IS NULL)
                OR
                (quarantine_verified = 1
                    AND quarantine_snapshot IS NOT NULL
                    AND quarantine_snapshot_digest IS NOT NULL
                    AND length(quarantine_snapshot_digest) = 64
                    AND quarantine_snapshot_digest NOT GLOB '*[^0-9a-f]*')
            ),
            CHECK (
                quarantine_snapshot IS NULL
                OR (typeof(quarantine_snapshot) = 'blob'
                    AND length(quarantine_snapshot) <= {MAX_GC_SNAPSHOT_BYTES})
            ),
            CHECK (
                (state = 'collecting'
                    AND collecting_from IN ('stale', 'superseded')
                    AND quarantine_path IS NOT NULL
                    AND collection_owner IS NOT NULL
                    AND length(collection_owner) = 45
                    AND substr(collection_owner, 1, 13) = 'gc-operation-'
                    AND substr(collection_owner, 14) NOT GLOB '*[^0-9a-f]*'
                    AND collection_lease_until IS NOT NULL
                    AND collection_phase IN ('prepared', 'quarantined', 'verified'))
                OR
                (state <> 'collecting'
                    AND collecting_from IS NULL
                    AND quarantine_path IS NULL
                    AND quarantine_verified = 0
                    AND collection_owner IS NULL
                    AND collection_lease_until IS NULL
                    AND collection_phase IS NULL)
            ),
            CHECK (
                (collection_phase = 'verified' AND quarantine_verified = 1)
                OR
                (collection_phase IN ('prepared', 'quarantined')
                    AND quarantine_verified = 0)
                OR collection_phase IS NULL
            ),
            CHECK (length(created_at) > 0 AND length(updated_at) > 0)
        )
    """
    _SCHEMA_REFERENCES_SQL = """
        CREATE TABLE lifecycle_references (
            tenant_id TEXT NOT NULL,
            output_id TEXT NOT NULL,
            reference_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, output_id, reference_id),
            FOREIGN KEY (tenant_id, output_id)
                REFERENCES lifecycle_outputs (tenant_id, output_id) ON DELETE RESTRICT,
            CHECK (
                length(tenant_id) > 0 AND length(output_id) > 0
                AND length(reference_id) > 0 AND length(created_at) > 0
            )
        )
    """
    _SCHEMA_SQL = (
        _SCHEMA_METADATA_SQL,
        _SCHEMA_OUTPUTS_SQL,
        _SCHEMA_REFERENCES_SQL,
    )
    _ROW_SELECT_SQL = f"""
        tenant_id, output_id, project_id, revision_id, run_id, output_path,
        manifest_digest, fs_device, fs_inode, state, legal_hold, superseded_by,
        collecting_from, quarantine_path, quarantine_verified,
        CASE
            WHEN quarantine_snapshot IS NULL THEN NULL
            WHEN typeof(quarantine_snapshot) = 'blob'
                AND length(quarantine_snapshot) <= {MAX_GC_SNAPSHOT_BYTES}
            THEN quarantine_snapshot
            ELSE NULL
        END AS quarantine_snapshot,
        quarantine_snapshot_digest, collection_owner, collection_lease_until,
        collection_phase, layout_version, created_at, updated_at,
        length(quarantine_snapshot) AS quarantine_snapshot_size
    """

    def __init__(self, database_path: str | Path, managed_root: str | Path) -> None:
        self.database_path = Path(database_path)
        self.managed_root = _safe_root(Path(managed_root), "managed_root")
        database_resolved = self.database_path.resolve(strict=False)
        try:
            database_resolved.relative_to(self.managed_root)
        except ValueError:
            pass
        else:
            raise LifecycleError("lifecycle database may not live under its managed output root")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            managed_descriptors = _open_directory_chain_nofollow(
                self.managed_root, create=True
            )
        except OSError as exc:
            raise LifecycleError("cannot safely create managed artifact root") from exc
        for descriptor in reversed(managed_descriptors):
            os.close(descriptor)
        self.quarantine_root = safe_join(
            self.managed_root, ".autonomous-qa-gc-quarantine"
        )
        try:
            quarantine_descriptors = _open_directory_chain_nofollow(
                self.quarantine_root, create=True
            )
        except OSError as exc:
            raise LifecycleError("cannot safely create artifact quarantine") from exc
        try:
            os.fchmod(quarantine_descriptors[-1], 0o700)
            _fsync_directory_descriptor(quarantine_descriptors[-1])
        finally:
            for descriptor in reversed(quarantine_descriptors):
                os.close(descriptor)
        self._initialize()
        self.recover_collecting()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30, factory=_ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _normalize_schema_sql(value: str) -> str:
        return " ".join(value.strip().rstrip(";").split())

    @classmethod
    def _expected_schema_objects(cls) -> list[dict[str, str]]:
        return [
            {
                "type": "table",
                "name": name,
                "table": name,
                "sql": cls._normalize_schema_sql(sql),
            }
            for name, sql in (
                ("lifecycle_outputs", cls._SCHEMA_OUTPUTS_SQL),
                ("lifecycle_references", cls._SCHEMA_REFERENCES_SQL),
                ("lifecycle_schema", cls._SCHEMA_METADATA_SQL),
            )
        ]

    @classmethod
    def _physical_schema_objects(
        cls, connection: sqlite3.Connection
    ) -> list[dict[str, str]]:
        rows = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name LIMIT ?",
            (len(cls._SCHEMA_SQL) + 1,),
        ).fetchall()
        objects: list[dict[str, str]] = []
        for row in rows:
            if not all(isinstance(row[field], str) for field in ("type", "name", "tbl_name")):
                raise LifecycleError("lifecycle schema object identity is invalid")
            sql = row["sql"]
            if not isinstance(sql, str):
                raise LifecycleError("lifecycle schema contains an unsupported object")
            objects.append(
                {
                    "type": str(row["type"]),
                    "name": str(row["name"]),
                    "table": str(row["tbl_name"]),
                    "sql": cls._normalize_schema_sql(sql),
                }
            )
        return objects

    @classmethod
    def _expected_schema_fingerprint(cls) -> str:
        return canonical_digest(
            {
                "schema_version": LIFECYCLE_SCHEMA_VERSION,
                "objects": cls._expected_schema_objects(),
            }
        )

    @classmethod
    def _physical_schema_fingerprint(cls, connection: sqlite3.Connection) -> str:
        return canonical_digest(
            {
                "schema_version": LIFECYCLE_SCHEMA_VERSION,
                "objects": cls._physical_schema_objects(connection),
            }
        )

    @classmethod
    def _assert_current_schema(cls, connection: sqlite3.Connection) -> None:
        expected_objects = cls._expected_schema_objects()
        actual_objects = cls._physical_schema_objects(connection)
        if actual_objects != expected_objects:
            raise LifecycleError(
                "legacy or altered lifecycle schema requires an explicit verified migration"
            )
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != LIFECYCLE_SCHEMA_VERSION:
            raise LifecycleError("lifecycle schema version is unsupported")
        rows = connection.execute(
            "SELECT schema_key, schema_version, physical_fingerprint, created_at "
            "FROM lifecycle_schema"
        ).fetchall()
        expected_fingerprint = cls._expected_schema_fingerprint()
        if (
            len(rows) != 1
            or rows[0]["schema_key"] != cls._SCHEMA_KEY
            or rows[0]["schema_version"] != LIFECYCLE_SCHEMA_VERSION
            or rows[0]["physical_fingerprint"] != expected_fingerprint
            or cls._physical_schema_fingerprint(connection) != expected_fingerprint
        ):
            raise LifecycleError("lifecycle schema metadata or fingerprint is invalid")
        try:
            _created_at_value(rows[0]["created_at"])
        except (ArtifactValidationError, TypeError, ValueError) as exc:
            raise LifecycleError("lifecycle schema creation timestamp is invalid") from exc
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LifecycleError("lifecycle schema contains a foreign-key violation")
        oversized_snapshot = connection.execute(
            "SELECT tenant_id, output_id FROM lifecycle_outputs "
            "WHERE quarantine_snapshot IS NOT NULL AND ("
            "typeof(quarantine_snapshot) <> 'blob' "
            "OR length(quarantine_snapshot) > ?) LIMIT 1",
            (MAX_GC_SNAPSHOT_BYTES,),
        ).fetchone()
        if oversized_snapshot is not None:
            raise LifecycleError(
                "lifecycle database contains an invalid garbage-collection snapshot"
            )

    @classmethod
    def _create_current_schema(cls, connection: sqlite3.Connection) -> None:
        for statement in cls._SCHEMA_SQL:
            connection.execute(statement)
        fingerprint = cls._physical_schema_fingerprint(connection)
        expected = cls._expected_schema_fingerprint()
        if fingerprint != expected:
            raise LifecycleError("fresh lifecycle schema fingerprint is inconsistent")
        connection.execute(
            "INSERT INTO lifecycle_schema "
            "(schema_key, schema_version, physical_fingerprint, created_at) "
            "VALUES (?, ?, ?, ?)",
            (cls._SCHEMA_KEY, LIFECYCLE_SCHEMA_VERSION, expected, _utc_now()),
        )
        connection.execute(f"PRAGMA user_version = {LIFECYCLE_SCHEMA_VERSION}")

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN EXCLUSIVE")
                objects = self._physical_schema_objects(connection)
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if not objects:
                    if version != 0:
                        raise LifecycleError(
                            "empty lifecycle database has an unsupported schema version"
                        )
                    self._create_current_schema(connection)
                self._assert_current_schema(connection)
        except LifecycleError:
            raise
        except sqlite3.DatabaseError as exc:
            raise LifecycleError("lifecycle schema initialization failed atomically") from exc

    @staticmethod
    def _new_collection_token() -> str:
        return "gc-operation-" + uuid.uuid4().hex

    @staticmethod
    def _collection_token_value(value: object) -> str:
        if not isinstance(value, str) or re.fullmatch(
            r"gc-operation-[0-9a-f]{32}", value
        ) is None:
            raise LifecycleError("garbage-collection operation token is invalid")
        return value

    @classmethod
    def _assert_snapshot_row_is_bounded(cls, row: sqlite3.Row) -> None:
        size = row["quarantine_snapshot_size"]
        payload = row["quarantine_snapshot"]
        if size is None:
            if payload is not None:
                raise LifecycleError("garbage-collection snapshot shape is invalid")
            return
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or size > MAX_GC_SNAPSHOT_BYTES
            or not isinstance(payload, bytes)
            or len(payload) != size
        ):
            raise LifecycleError(
                "lifecycle database contains an invalid garbage-collection snapshot"
            )

    @classmethod
    def _select_lifecycle_row(
        cls,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        output_id: str,
    ) -> sqlite3.Row | None:
        row = connection.execute(
            f"SELECT {cls._ROW_SELECT_SQL} FROM lifecycle_outputs "
            "WHERE tenant_id = ? AND output_id = ?",
            (tenant_id, output_id),
        ).fetchone()
        if row is not None:
            cls._assert_snapshot_row_is_bounded(row)
        return row

    def _assert_gc_fence(self, fence: _LifecycleFence) -> None:
        current_root_descriptors: list[int] = []
        try:
            held_parent = os.fstat(fence.parent_descriptor)
            _require_private_directory_descriptor(
                fence.parent_descriptor, "garbage-collection fence parent"
            )
            current_root_descriptors = _open_directory_chain_nofollow(
                self.quarantine_root
            )
            current_parent = os.fstat(current_root_descriptors[-1])
            if (current_parent.st_dev, current_parent.st_ino) != (
                held_parent.st_dev,
                held_parent.st_ino,
            ):
                raise LifecycleError("garbage-collection fence root was replaced")
            descriptor_metadata = os.fstat(fence.descriptor)
            named_metadata = os.stat(
                self._FENCE_FILE,
                dir_fd=fence.parent_descriptor,
                follow_symlinks=False,
            )
            expected = (fence.device, fence.inode, fence.mode, fence.uid, 1)
            descriptor_identity = (
                int(descriptor_metadata.st_dev),
                int(descriptor_metadata.st_ino),
                stat.S_IMODE(descriptor_metadata.st_mode),
                int(descriptor_metadata.st_uid),
                int(descriptor_metadata.st_nlink),
            )
            named_identity = (
                int(named_metadata.st_dev),
                int(named_metadata.st_ino),
                stat.S_IMODE(named_metadata.st_mode),
                int(named_metadata.st_uid),
                int(named_metadata.st_nlink),
            )
            if (
                not stat.S_ISREG(descriptor_metadata.st_mode)
                or not stat.S_ISREG(named_metadata.st_mode)
                or descriptor_identity != expected
                or named_identity != expected
            ):
                raise LifecycleError("garbage-collection fence entry was replaced")
        except LifecycleError:
            raise
        except OSError as exc:
            raise LifecycleError("garbage-collection fence cannot be verified") from exc
        finally:
            _close_descriptors(current_root_descriptors)

    def _acquire_gc_fence(self) -> _LifecycleFence | None:
        key = str(self.quarantine_root.resolve(strict=False))
        with self._PROCESS_FENCE_GUARD:
            if key in self._PROCESS_FENCES:
                return None
            self._PROCESS_FENCES.add(key)
        descriptors: list[int] = []
        descriptor: int | None = None
        parent_descriptor: int | None = None
        try:
            descriptors = _open_directory_chain_nofollow(self.quarantine_root)
            _require_private_directory_descriptor(
                descriptors[-1], "garbage-collection fence parent"
            )
            parent_descriptor = os.dup(descriptors[-1])
            nofollow = getattr(os, "O_NOFOLLOW", None)
            if nofollow is None:
                raise LifecycleError("garbage-collection fencing is unavailable")
            descriptor = os.open(
                self._FENCE_FILE,
                os.O_RDWR
                | os.O_CREAT
                | nofollow
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise LifecycleError("garbage-collection fence file is unsafe")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
                    raise
                os.close(descriptor)
                descriptor = None
                if parent_descriptor is not None:
                    os.close(parent_descriptor)
                parent_descriptor = None
                with self._PROCESS_FENCE_GUARD:
                    self._PROCESS_FENCES.discard(key)
                return None
            if descriptor is None or parent_descriptor is None:
                raise LifecycleError("garbage-collection fence was not established")
            fence = _LifecycleFence(
                descriptor=descriptor,
                parent_descriptor=parent_descriptor,
                key=key,
                device=int(metadata.st_dev),
                inode=int(metadata.st_ino),
                mode=stat.S_IMODE(metadata.st_mode),
                uid=int(metadata.st_uid),
            )
            self._assert_gc_fence(fence)
            descriptor = None
            parent_descriptor = None
            return fence
        except LifecycleError:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if parent_descriptor is not None:
                try:
                    os.close(parent_descriptor)
                except OSError:
                    pass
            with self._PROCESS_FENCE_GUARD:
                self._PROCESS_FENCES.discard(key)
            raise
        except OSError as exc:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if parent_descriptor is not None:
                try:
                    os.close(parent_descriptor)
                except OSError:
                    pass
            with self._PROCESS_FENCE_GUARD:
                self._PROCESS_FENCES.discard(key)
            raise LifecycleError("cannot acquire garbage-collection fence") from exc
        finally:
            _close_descriptors(descriptors)

    def _release_gc_fence(self, fence: _LifecycleFence) -> None:
        verification_error: LifecycleError | None = None
        try:
            try:
                self._assert_gc_fence(fence)
            except LifecycleError as exc:
                verification_error = exc
            try:
                fcntl.flock(fence.descriptor, fcntl.LOCK_UN)
            finally:
                try:
                    os.close(fence.descriptor)
                finally:
                    os.close(fence.parent_descriptor)
        finally:
            with self._PROCESS_FENCE_GUARD:
                self._PROCESS_FENCES.discard(fence.key)
        if verification_error is not None:
            raise verification_error

    def _checked_output_path(
        self,
        path: Path,
        *,
        tenant_id: str,
        project_id: str | None = None,
        revision_id: str | None = None,
        output_id: str | None = None,
    ) -> Path:
        if path.is_symlink():
            raise LifecycleError(f"managed output may not be a symlink: {path}")
        resolved = path.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.managed_root)
        except ValueError as exc:
            raise LifecycleError(f"output is outside managed root: {path}") from exc
        if len(relative.parts) != 4:
            raise LifecycleError(
                "managed output path must be exactly tenant/project/revision/output"
            )
        expected = (
            _storage_segment("tenant", tenant_id),
            None if project_id is None else _storage_segment("project", project_id),
            None if revision_id is None else _storage_segment("revision", revision_id),
            None if output_id is None else _storage_segment("output", output_id),
        )
        for index, value in enumerate(expected):
            if value is not None and relative.parts[index] != value:
                raise LifecycleError("managed output path does not match its tenant identity")
        return resolved

    def _checked_quarantine_path(self, path: Path) -> Path:
        if path.is_symlink():
            raise LifecycleError(f"quarantine target may not be a symlink: {path}")
        resolved = path.resolve(strict=False)
        try:
            relative = resolved.relative_to(self.quarantine_root)
        except ValueError as exc:
            raise LifecycleError(f"quarantine target is outside the managed root: {path}") from exc
        if len(relative.parts) != 1:
            raise LifecycleError("quarantine target must be one managed path segment")
        return resolved

    @staticmethod
    def _filesystem_identity(path: Path) -> tuple[int, int]:
        try:
            return _directory_identity_nofollow(path)
        except (ArtifactValidationError, OSError) as exc:
            raise LifecycleError(f"managed output is not a safe directory: {path}") from exc

    @staticmethod
    def _manifest_document(root_descriptor: int) -> tuple[bytes, Mapping[str, Any]]:
        try:
            data = _read_regular_file_at(
                root_descriptor,
                "manifests/project-output-manifest.json",
                max_bytes=MAX_ARTIFACT_BYTES,
            )
            document = parse_json_strict(data)
        except (ArtifactValidationError, ValueError) as exc:
            raise LifecycleError("invalid published-output manifest") from exc
        if not isinstance(document, dict):
            raise LifecycleError("published-output manifest must be an object")
        if canonical_json_bytes(document) != data:
            raise LifecycleError("published-output manifest is not canonically encoded")
        return data, document

    def _verify_output_identity(
        self,
        path: Path,
        *,
        tenant_id: str,
        output_id: str,
        project_id: str,
        revision_id: str,
        run_id: str,
        manifest_digest: str,
        fs_device: int,
        fs_inode: int,
        normal_path: bool,
        status: str | None = None,
        bundle_digests: Mapping[str, str] | None = None,
        published_failure: Mapping[str, str] | None = None,
        verify_envelope: bool = False,
    ) -> _TreeSnapshot:
        if normal_path:
            checked = self._checked_output_path(
                path,
                tenant_id=tenant_id,
                project_id=project_id,
                revision_id=revision_id,
                output_id=output_id,
            )
        else:
            checked = self._checked_quarantine_path(path)
        descriptors: list[int] = []
        try:
            descriptors, snapshot = _open_tree_snapshot(checked)
            if (snapshot.root_device, snapshot.root_inode) != (fs_device, fs_inode):
                raise LifecycleError("managed output filesystem identity changed")
            root_descriptor = descriptors[-1]
            manifest_bytes, manifest = self._manifest_document(root_descriptor)
            if sha256_bytes(manifest_bytes) != manifest_digest:
                raise LifecycleError("managed output manifest digest changed")
            base_manifest_fields = {
                "schema_version",
                "output_id",
                "tenant_id",
                "project_id",
                "revision_id",
                "run_id",
                "run_mode",
                "output_mode",
                "source_snapshot_digest",
                "status",
                "created_at",
                "artifacts",
                "bundles",
                "materialization",
                "signed",
                "certified",
                "external_evidence_status",
            }
            manifest_fields = set(manifest)
            if (
                manifest_fields != base_manifest_fields
                and manifest_fields != base_manifest_fields | {"failure"}
            ):
                raise LifecycleError("managed output manifest fields are not exact")
            expected_identity = {
                "tenant_id": tenant_id,
                "output_id": output_id,
                "project_id": project_id,
                "revision_id": revision_id,
                "run_id": run_id,
            }
            for field, value in expected_identity.items():
                if manifest.get(field) != value:
                    raise LifecycleError(f"managed output manifest {field} mismatch")
            if status is not None and manifest.get("status") != status:
                raise LifecycleError("managed output manifest status mismatch")
            if manifest.get("schema_version") != "elmos.autonomous-qa.output.v1":
                raise LifecycleError("managed output manifest schema is unsupported")
            manifest_status = manifest.get("status")
            if not isinstance(manifest_status, str) or manifest_status not in {
                "verified",
                "partial",
                "failed",
            }:
                raise LifecycleError("managed output manifest has an unsupported status")
            try:
                require_sha256(
                    manifest.get("source_snapshot_digest"), field="source_snapshot_digest"
                )
                _created_at_value(manifest.get("created_at"))
            except (ArtifactValidationError, AttributeError, ValueError) as exc:
                raise LifecycleError("managed output manifest metadata is invalid") from exc
            run_mode = manifest.get("run_mode")
            output_mode = manifest.get("output_mode")
            if (
                not isinstance(run_mode, str)
                or run_mode not in _RUN_MODES
                or not isinstance(output_mode, str)
                or output_mode not in _OUTPUT_MODES
            ):
                raise LifecycleError("managed output execution mode is invalid")
            derived_output_id = "out_" + canonical_digest(
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "revision_id": revision_id,
                    "run_id": run_id,
                    "source_snapshot_digest": manifest["source_snapshot_digest"],
                    "output_mode": output_mode,
                    "run_mode": run_mode,
                }
            )[:24]
            if output_id != derived_output_id:
                raise LifecycleError("managed output ID is not digest-bound to its plan")
            if manifest.get("signed") is not False or manifest.get("certified") is not False:
                raise LifecycleError("local output may not claim signing or certification")
            if manifest.get("external_evidence_status") != "NOT_RUN":
                raise LifecycleError("local output has an unsupported external-evidence claim")
            failure = manifest.get("failure")
            if failure is not None and (
                not isinstance(failure, dict)
                or set(failure) != {"type", "message"}
                or not isinstance(failure.get("type"), str)
                or not isinstance(failure.get("message"), str)
            ):
                raise LifecycleError("managed output failure metadata is invalid")
            if (manifest_status == "verified") != (failure is None):
                raise LifecycleError(
                    "managed output status and failure envelope are inconsistent"
                )

            artifacts = manifest.get("artifacts")
            if not isinstance(artifacts, list):
                raise LifecycleError("managed output manifest artifacts are invalid")
            if len(artifacts) > MAX_REGISTERED_ARTIFACTS:
                raise LifecycleError("managed output manifest artifact limit exceeded")
            artifact_ids: set[str] = set()
            artifact_paths: list[str] = []
            aggregate_artifact_bytes = 0
            normalized_artifacts: list[dict[str, Any]] = []
            artifact_base_fields = {
                "artifact_id",
                "path",
                "category",
                "role",
                "sha256",
                "size_bytes",
                "producer",
                "required",
                "validation_status",
                "requirement_refs",
                "test_case_refs",
            }
            for artifact in artifacts:
                artifact_fields = set(artifact) if isinstance(artifact, dict) else set()
                if not isinstance(artifact, dict) or (
                    artifact_fields != artifact_base_fields
                    and artifact_fields != artifact_base_fields | {"risk_justification"}
                ):
                    raise LifecycleError("managed output manifest artifact fields are not exact")
                try:
                    artifact_id = _metadata_value(artifact.get("artifact_id"), "artifact_id")
                    artifact_path = normalize_relative_path(artifact.get("path"))
                    category = _metadata_value(artifact.get("category"), "category")
                    role = _metadata_value(artifact.get("role"), "role")
                    producer = _metadata_value(artifact.get("producer"), "producer")
                    validation_status = _metadata_value(
                        artifact.get("validation_status"), "validation_status"
                    )
                    artifact_digest = require_sha256(
                        artifact.get("sha256"), field="artifact sha256"
                    )
                except (ArtifactValidationError, AttributeError, TypeError, ValueError) as exc:
                    raise LifecycleError(
                        "managed output manifest artifact metadata is invalid"
                    ) from exc
                if artifact_id in artifact_ids:
                    raise LifecycleError("managed output manifest artifact ID is duplicated")
                artifact_ids.add(artifact_id)
                artifact_paths.append(artifact_path)
                if category not in _ARTIFACT_CATEGORIES or category == "certificate":
                    raise LifecycleError("managed output manifest artifact category is forbidden")
                if role not in _ARTIFACT_ROLES or producer not in _ARTIFACT_PRODUCERS:
                    raise LifecycleError("managed output manifest artifact authority is unknown")
                if validation_status not in _ARTIFACT_VALIDATION_STATUSES:
                    raise LifecycleError("managed output manifest artifact status is forbidden")
                if not isinstance(artifact.get("required"), bool):
                    raise LifecycleError(
                        "managed output manifest artifact required flag is invalid"
                    )
                size_bytes = artifact.get("size_bytes")
                if (
                    isinstance(size_bytes, bool)
                    or not isinstance(size_bytes, int)
                    or size_bytes < 0
                    or size_bytes > MAX_ARTIFACT_BYTES
                ):
                    raise LifecycleError("managed output manifest artifact size is invalid")
                aggregate_artifact_bytes += size_bytes
                if aggregate_artifact_bytes > MAX_REGISTERED_ARTIFACT_BYTES:
                    raise LifecycleError("managed output artifact byte limit exceeded")
                requirement_refs = artifact.get("requirement_refs")
                test_case_refs = artifact.get("test_case_refs")
                if not isinstance(requirement_refs, list) or not isinstance(test_case_refs, list):
                    raise LifecycleError("managed output manifest artifact traceability is invalid")
                if (
                    len(requirement_refs) > MAX_REFERENCES_PER_ARTIFACT
                    or len(test_case_refs) > MAX_REFERENCES_PER_ARTIFACT
                ):
                    raise LifecycleError(
                        "managed output artifact references are not bounded and exact"
                    )
                risk_justification = artifact.get("risk_justification")
                try:
                    for reference in (*requirement_refs, *test_case_refs):
                        _metadata_value(reference, "artifact reference")
                    if risk_justification is not None:
                        _metadata_value(risk_justification, "risk_justification")
                except (ArtifactValidationError, TypeError, ValueError) as exc:
                    raise LifecycleError(
                        "managed output manifest artifact reference is invalid"
                    ) from exc
                if (
                    requirement_refs != sorted(set(requirement_refs))
                    or test_case_refs != sorted(set(test_case_refs))
                ):
                    raise LifecycleError(
                        "managed output artifact references are not unique and sorted"
                    )
                if artifact["required"] and not (
                    requirement_refs or test_case_refs or risk_justification
                ):
                    raise LifecycleError("required managed artifact lacks traceability")
                normalized_artifacts.append(
                    {
                        **artifact,
                        "artifact_id": artifact_id,
                        "path": artifact_path,
                        "category": category,
                        "sha256": artifact_digest,
                        "size_bytes": size_bytes,
                    }
                )
            try:
                validate_unique_paths(artifact_paths)
            except ValueError as exc:
                raise LifecycleError("managed output manifest artifact paths collide") from exc
            if artifact_paths != sorted(artifact_paths):
                raise LifecycleError(
                    "managed output manifest artifacts are not canonically ordered"
                )

            materialize = manifest_status == "verified" and run_mode != "plan-only"
            materialization = manifest.get("materialization")
            if (
                not isinstance(materialization, dict)
                or set(materialization)
                != {
                    "mode",
                    "embedded_test_artifacts",
                    "sidecar_artifacts",
                    "existing_files_overwritten",
                }
                or materialization.get("mode") != output_mode
                or materialization.get("existing_files_overwritten") is not False
            ):
                raise LifecycleError("managed output has an unsafe materialization claim")
            expected_embedded_count = (
                sum(
                    artifact["category"] in _EMBEDDED_CATEGORIES
                    for artifact in normalized_artifacts
                )
                if materialize and output_mode in {"embedded", "both"}
                else 0
            )
            expected_sidecar = [
                artifact
                for artifact in normalized_artifacts
                if materialize
                and output_mode in {"sidecar", "both"}
                and artifact["category"] in _BUNDLE_CATEGORIES["project-with-tests"]
            ]
            if (
                materialization.get("embedded_test_artifacts") != expected_embedded_count
                or materialization.get("sidecar_artifacts") != len(expected_sidecar)
                or isinstance(materialization.get("embedded_test_artifacts"), bool)
                or isinstance(materialization.get("sidecar_artifacts"), bool)
            ):
                raise LifecycleError("managed output materialization counts are not exact")

            required_kinds: set[str] = set()
            if materialize:
                required_kinds.update({"project-with-tests", "tests-only"})
                if run_mode in {"verify", "repair", "certify", "continuous"} or any(
                    artifact["category"] in _BUNDLE_CATEGORIES["qa-evidence"]
                    for artifact in normalized_artifacts
                ):
                    required_kinds.add("qa-evidence")
                if any(
                    artifact["category"] == "patch" for artifact in normalized_artifacts
                ):
                    required_kinds.add("repair-patches")

            bundles = manifest.get("bundles")
            if not isinstance(bundles, list) or len(bundles) > len(_BUNDLE_CATEGORIES):
                raise LifecycleError("managed output manifest bundles are invalid")
            bundle_paths: list[str] = []
            bundle_kinds: set[str] = set()
            expected_files: dict[str, tuple[str, int]] = {
                "manifests/project-output-manifest.json": (
                    manifest_digest,
                    len(manifest_bytes),
                )
            }
            for artifact in expected_sidecar:
                expected_files[f"project/{artifact['path']}"] = (
                    artifact["sha256"],
                    artifact["size_bytes"],
                )
            for bundle in bundles:
                if not isinstance(bundle, dict) or set(bundle) != {
                    "kind",
                    "path",
                    "sha256",
                    "size_bytes",
                    "status",
                }:
                    raise LifecycleError("managed output manifest bundle fields are not exact")
                kind = bundle.get("kind")
                if not isinstance(kind, str) or kind not in _BUNDLE_CATEGORIES:
                    raise LifecycleError("managed output manifest bundle kind is invalid")
                if kind in bundle_kinds:
                    raise LifecycleError("managed output manifest bundle kind is duplicated")
                bundle_kinds.add(kind)
                if bundle.get("status") != "verified":
                    raise LifecycleError("managed output manifest bundle is not locally verified")
                try:
                    bundle_path = normalize_relative_path(bundle.get("path"))
                    bundle_digest = require_sha256(
                        bundle.get("sha256"), field="bundle sha256"
                    )
                except (AttributeError, TypeError, ValueError) as exc:
                    raise LifecycleError(
                        "managed output manifest bundle metadata is invalid"
                    ) from exc
                if bundle_path != f"bundles/{output_id}-{kind}.zip":
                    raise LifecycleError("managed output bundle path is not canonical")
                bundle_paths.append(bundle_path)
                size_bytes = bundle.get("size_bytes")
                if (
                    isinstance(size_bytes, bool)
                    or not isinstance(size_bytes, int)
                    or size_bytes < 0
                ):
                    raise LifecycleError("managed output manifest bundle size is invalid")
                expected_files[bundle_path] = (bundle_digest, size_bytes)
                try:
                    bundle_payload = _read_regular_file_at(
                        root_descriptor,
                        bundle_path,
                        max_bytes=MAX_BUNDLE_UNCOMPRESSED_BYTES,
                    )
                    if (
                        len(bundle_payload) != size_bytes
                        or sha256_bytes(bundle_payload) != bundle_digest
                    ):
                        raise ArtifactValidationError(
                            "published bundle size or digest mismatch"
                        )
                    _verify_bundle_payload(
                        bundle_payload,
                        expected_kind=kind,
                        expected_output_id=output_id,
                        artifacts=tuple(normalized_artifacts),
                    )
                except (ArtifactValidationError, UnsafePathError, ValueError) as exc:
                    raise LifecycleError("managed output bundle verification failed") from exc
            try:
                validate_unique_paths(bundle_paths)
            except ValueError as exc:
                raise LifecycleError("managed output manifest bundle paths collide") from exc
            if bundle_kinds != required_kinds:
                raise LifecycleError("managed output does not contain its exact required bundles")
            if verify_envelope:
                manifest_bundle_digests = {
                    str(bundle["kind"]): str(bundle["sha256"]) for bundle in bundles
                }
                if bundle_digests is None or dict(bundle_digests) != manifest_bundle_digests:
                    raise LifecycleError("published output bundle digest envelope mismatch")
                manifest_failure = dict(failure) if isinstance(failure, dict) else None
                if published_failure != manifest_failure:
                    raise LifecycleError("published output failure envelope mismatch")
            canonical_bundle_order: list[str] = []
            if materialize:
                canonical_bundle_order.extend(["project-with-tests", "tests-only"])
            if "qa-evidence" in required_kinds:
                canonical_bundle_order.append("qa-evidence")
            if "repair-patches" in required_kinds:
                canonical_bundle_order.append("repair-patches")
            if [bundle["kind"] for bundle in bundles] != canonical_bundle_order:
                raise LifecycleError("managed output bundles are not canonically ordered")
            if materialize:
                for artifact in normalized_artifacts:
                    delivered = any(
                        artifact["category"] in _BUNDLE_CATEGORIES[kind]
                        for kind in required_kinds
                    )
                    if artifact in expected_sidecar:
                        delivered = True
                    if (
                        output_mode in {"embedded", "both"}
                        and artifact["category"] in _EMBEDDED_CATEGORIES
                    ):
                        delivered = True
                    if not delivered:
                        raise LifecycleError("managed artifact has no declared delivery channel")

            checksum_path = "manifests/checksums.sha256"
            checksum_snapshot = snapshot.files.get(checksum_path)
            if checksum_snapshot is None:
                raise LifecycleError("managed output checksum index is missing")
            expected_files[checksum_path] = (
                checksum_snapshot.sha256,
                checksum_snapshot.size_bytes,
            )
            if set(snapshot.files) != set(expected_files):
                raise LifecycleError("managed output contains missing or extra files")
            if set(snapshot.directories) != _expected_directory_paths(set(expected_files)):
                raise LifecycleError("managed output contains missing or extra directories")
            for file_path, (expected_digest, expected_size) in expected_files.items():
                actual = snapshot.files[file_path]
                if actual.sha256 != expected_digest or actual.size_bytes != expected_size:
                    raise LifecycleError(f"managed output file bytes changed: {file_path!r}")
            checksums = _read_regular_file_at(
                root_descriptor,
                checksum_path,
                max_bytes=MAX_ARTIFACT_BYTES,
            )
            if checksums != _checksums_bytes(snapshot.files):
                raise LifecycleError(
                    "managed output checksum index is missing, stale, or ambiguous"
                )
            final_snapshot = _snapshot_tree_from_descriptor(root_descriptor)
            if final_snapshot != snapshot:
                raise LifecycleError("managed output changed during lifecycle verification")
            return final_snapshot
        except (ArtifactValidationError, OSError) as exc:
            raise LifecycleError("managed output tree verification failed") from exc
        finally:
            _close_descriptors(descriptors)

    def register_output(self, output: PublishedOutput) -> None:
        if output.durability_status != "DURABLE":
            raise LifecycleError("published output durability is not established")
        try:
            _metadata_value(output.output_id, "output_id")
            _metadata_value(output.run_id, "run_id")
        except ArtifactValidationError as exc:
            raise LifecycleError("published output identity is invalid") from exc
        path = self._checked_output_path(
            output.root,
            tenant_id=output.tenant_id,
            project_id=output.project_id,
            revision_id=output.revision_id,
            output_id=output.output_id,
        )
        try:
            manifest_digest = require_sha256(output.manifest_digest, field="manifest_digest")
        except (AttributeError, ValueError) as exc:
            raise LifecycleError("published output manifest digest is invalid") from exc
        if not isinstance(output.bundle_digests, Mapping):
            raise LifecycleError("published output bundle digest envelope is invalid")
        normalized_bundle_digests: dict[str, str] = {}
        try:
            for kind, digest in output.bundle_digests.items():
                if not isinstance(kind, str) or kind not in _BUNDLE_CATEGORIES:
                    raise LifecycleError("published output bundle kind is invalid")
                if kind in normalized_bundle_digests:
                    raise LifecycleError("published output bundle kind is duplicated")
                normalized_bundle_digests[kind] = require_sha256(
                    digest, field="published bundle digest"
                )
        except (AttributeError, TypeError, ValueError) as exc:
            raise LifecycleError("published output bundle digest envelope is invalid") from exc
        normalized_failure: dict[str, str] | None = None
        if output.failure is not None:
            if not isinstance(output.failure, Mapping) or set(output.failure) != {
                "type",
                "message",
            }:
                raise LifecycleError("published output failure envelope is invalid")
            failure_type = output.failure.get("type")
            failure_message = output.failure.get("message")
            if not isinstance(failure_type, str) or not isinstance(failure_message, str):
                raise LifecycleError("published output failure envelope is invalid")
            normalized_failure = {"type": failure_type, "message": failure_message}
        fs_device, fs_inode = self._filesystem_identity(path)
        self._verify_output_identity(
            path,
            tenant_id=output.tenant_id,
            output_id=output.output_id,
            project_id=output.project_id,
            revision_id=output.revision_id,
            run_id=output.run_id,
            manifest_digest=manifest_digest,
            fs_device=fs_device,
            fs_inode=fs_inode,
            normal_path=True,
            status=output.status,
            bundle_digests=normalized_bundle_digests,
            published_failure=normalized_failure,
            verify_envelope=True,
        )
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO lifecycle_outputs "
                "(tenant_id, output_id, project_id, revision_id, run_id, output_path, "
                "manifest_digest, fs_device, fs_inode, state, legal_hold, superseded_by, "
                "collecting_from, quarantine_path, quarantine_snapshot, layout_version, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, NULL, NULL, NULL, NULL, "
                "?, ?, ?)",
                (
                    output.tenant_id,
                    output.output_id,
                    output.project_id,
                    output.revision_id,
                    output.run_id,
                    str(path),
                    manifest_digest,
                    fs_device,
                    fs_inode,
                    LIFECYCLE_LAYOUT_VERSION,
                    now,
                    now,
                ),
            )

    def mark_stale(self, *, tenant_id: str, output_id: str) -> None:
        self._set_state(tenant_id, output_id, "stale")

    def _set_state(self, tenant_id: str, output_id: str, state: str) -> None:
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET state = ?, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? "
                "AND state NOT IN ('collecting', 'collected')",
                (state, _utc_now(), tenant_id, output_id),
            )
            if updated.rowcount != 1:
                raise LifecycleError(f"unknown or collected output: {tenant_id}/{output_id}")

    def supersede(
        self, *, tenant_id: str, old_output_id: str, new_output_id: str
    ) -> None:
        if old_output_id == new_output_id:
            raise LifecycleError("an output cannot supersede itself")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            new = connection.execute(
                "SELECT state, project_id FROM lifecycle_outputs "
                "WHERE tenant_id = ? AND output_id = ?",
                (tenant_id, new_output_id),
            ).fetchone()
            old = connection.execute(
                "SELECT project_id FROM lifecycle_outputs "
                "WHERE tenant_id = ? AND output_id = ?",
                (tenant_id, old_output_id),
            ).fetchone()
            if new is None or new["state"] != "active":
                raise LifecycleError(f"replacement output is unavailable: {new_output_id}")
            if old is None or old["project_id"] != new["project_id"]:
                raise LifecycleError("superseding outputs must belong to the same project")
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET state = 'superseded', superseded_by = ?, "
                "updated_at = ? WHERE tenant_id = ? AND output_id = ? "
                "AND state NOT IN ('collecting', 'collected')",
                (new_output_id, _utc_now(), tenant_id, old_output_id),
            )
            if updated.rowcount != 1:
                raise LifecycleError(f"output cannot be superseded: {old_output_id}")

    def set_legal_hold(
        self, *, tenant_id: str, output_id: str, enabled: bool
    ) -> None:
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET legal_hold = ?, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? "
                "AND state NOT IN ('collecting', 'collected')",
                (1 if enabled else 0, _utc_now(), tenant_id, output_id),
            )
            if updated.rowcount != 1:
                raise LifecycleError(f"unknown or collected output: {tenant_id}/{output_id}")

    def add_reference(
        self, *, tenant_id: str, output_id: str, reference_id: str
    ) -> None:
        if not reference_id:
            raise ValueError("reference_id is required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            output = connection.execute(
                "SELECT state FROM lifecycle_outputs "
                "WHERE tenant_id = ? AND output_id = ?",
                (tenant_id, output_id),
            ).fetchone()
            if output is None or output["state"] in {"collecting", "collected"}:
                raise LifecycleError("output is missing or already being collected")
            try:
                connection.execute(
                    "INSERT INTO lifecycle_references "
                    "(tenant_id, output_id, reference_id, created_at) VALUES (?, ?, ?, ?)",
                    (tenant_id, output_id, reference_id, _utc_now()),
                )
            except sqlite3.IntegrityError as exc:
                raise LifecycleError("output is missing or reference already exists") from exc

    def remove_reference(
        self, *, tenant_id: str, output_id: str, reference_id: str
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM lifecycle_references "
                "WHERE tenant_id = ? AND output_id = ? AND reference_id = ?",
                (tenant_id, output_id, reference_id),
            )

    def gc_candidates(self, *, tenant_id: str) -> tuple[str, ...]:
        tenant_id = _safe_segment(tenant_id, "tenant_id")
        candidates: list[str] = []
        last_output_id = ""
        while True:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT output_id, layout_version "
                    "FROM lifecycle_outputs AS output "
                    "WHERE tenant_id = ? AND output_id > ? "
                    "AND state IN ('stale', 'superseded') "
                    "AND legal_hold = 0 AND NOT EXISTS ("
                    "SELECT 1 FROM lifecycle_references AS reference "
                    "WHERE reference.tenant_id = output.tenant_id "
                    "AND reference.output_id = output.output_id) "
                    "ORDER BY output_id LIMIT ?",
                    (tenant_id, last_output_id, LIFECYCLE_PAGE_SIZE),
                ).fetchall()
            if not rows:
                break
            for row in rows:
                if row["layout_version"] != LIFECYCLE_LAYOUT_VERSION:
                    raise LifecycleError(
                        "legacy lifecycle layout requires an explicit verified migration"
                    )
                candidates.append(str(row["output_id"]))
                if len(candidates) > MAX_LIFECYCLE_RESULTS:
                    raise LifecycleError(
                        "garbage-collection candidate result limit exceeded"
                    )
            last_output_id = str(rows[-1]["output_id"])
        return tuple(candidates)

    def _quarantine_path(
        self, *, tenant_id: str, output_id: str, manifest_digest: str
    ) -> Path:
        name = "gc-" + canonical_digest(
            {
                "tenant_id": tenant_id,
                "output_id": output_id,
                "manifest_digest": manifest_digest,
            }
        )
        return self._checked_quarantine_path(safe_join(self.quarantine_root, name))

    def _verify_row_path(
        self, row: sqlite3.Row, path: Path, *, normal_path: bool
    ) -> _TreeSnapshot:
        if (
            "layout_version" not in row.keys()
            or row["layout_version"] != LIFECYCLE_LAYOUT_VERSION
        ):
            raise LifecycleError(
                "legacy lifecycle layout requires an explicit verified migration"
            )
        required_strings = (
            "tenant_id",
            "output_id",
            "project_id",
            "revision_id",
            "run_id",
            "manifest_digest",
        )
        if any(not isinstance(row[field], str) or not row[field] for field in required_strings):
            raise LifecycleError("managed output identity metadata is incomplete")
        if row["fs_device"] is None or row["fs_inode"] is None:
            raise LifecycleError("managed output filesystem identity is missing")
        try:
            manifest_digest = require_sha256(
                str(row["manifest_digest"]), field="manifest_digest"
            )
        except ValueError as exc:
            raise LifecycleError("managed output manifest digest is invalid") from exc
        return self._verify_output_identity(
            path,
            tenant_id=str(row["tenant_id"]),
            output_id=str(row["output_id"]),
            project_id=str(row["project_id"]),
            revision_id=str(row["revision_id"]),
            run_id=str(row["run_id"]),
            manifest_digest=manifest_digest,
            fs_device=int(row["fs_device"]),
            fs_inode=int(row["fs_inode"]),
            normal_path=normal_path,
        )

    def _row_quarantine_path(self, row: sqlite3.Row) -> Path:
        quarantine_value = row["quarantine_path"]
        if not isinstance(quarantine_value, str) or not quarantine_value:
            raise LifecycleError("collecting output lacks a quarantine path")
        actual = self._checked_quarantine_path(Path(quarantine_value))
        expected = self._quarantine_path(
            tenant_id=str(row["tenant_id"]),
            output_id=str(row["output_id"]),
            manifest_digest=str(row["manifest_digest"]),
        )
        if actual != expected:
            raise LifecycleError("collecting quarantine path is not deterministically bound")
        return actual

    @staticmethod
    def _safe_directory_exists(path: Path, field: str) -> bool:
        try:
            _directory_identity_nofollow(path)
            return True
        except FileNotFoundError:
            return False
        except (ArtifactValidationError, OSError) as exc:
            raise LifecycleError(f"{field} is unsafe") from exc

    @staticmethod
    def _establish_rename_durability(output_path: Path, quarantine_path: Path) -> None:
        for parent in dict.fromkeys((output_path.parent, quarantine_path.parent)):
            descriptors: list[int] = []
            try:
                descriptors = _open_directory_chain_nofollow(parent)
                _require_private_directory_descriptor(
                    descriptors[-1], "garbage-collection rename parent"
                )
                _fsync_directory_descriptor(descriptors[-1])
            except Exception as exc:
                raise LifecycleError(
                    "garbage-collection rename durability is unknown"
                ) from exc
            finally:
                _close_descriptors(descriptors)

    def _snapshot_envelope(
        self, row: sqlite3.Row, quarantine_path: Path, snapshot: _TreeSnapshot
    ) -> bytes:
        return _gc_snapshot_envelope_bytes(
            snapshot,
            tenant_id=str(row["tenant_id"]),
            output_id=str(row["output_id"]),
            project_id=str(row["project_id"]),
            revision_id=str(row["revision_id"]),
            run_id=str(row["run_id"]),
            manifest_digest=str(row["manifest_digest"]),
            quarantine_name=quarantine_path.name,
        )

    def _verified_snapshot(
        self, row: sqlite3.Row, quarantine_path: Path
    ) -> _TreeSnapshot:
        if row["quarantine_verified"] != 1:
            raise LifecycleError("garbage-collection snapshot is not verified")
        payload = row["quarantine_snapshot"]
        stored_digest = row["quarantine_snapshot_digest"]
        if not isinstance(payload, bytes) or not isinstance(stored_digest, str):
            raise LifecycleError("verified quarantine lacks its immutable deletion envelope")
        try:
            expected_digest = require_sha256(
                stored_digest, field="garbage-collection envelope digest"
            )
        except ValueError as exc:
            raise LifecycleError("garbage-collection envelope digest is invalid") from exc
        if sha256_bytes(payload) != expected_digest:
            raise LifecycleError("garbage-collection envelope digest mismatch")
        snapshot = _gc_snapshot_envelope_from_bytes(
            payload,
            tenant_id=str(row["tenant_id"]),
            output_id=str(row["output_id"]),
            project_id=str(row["project_id"]),
            revision_id=str(row["revision_id"]),
            run_id=str(row["run_id"]),
            manifest_digest=str(row["manifest_digest"]),
            quarantine_name=quarantine_path.name,
        )
        if (snapshot.root_device, snapshot.root_inode) != (
            int(row["fs_device"]),
            int(row["fs_inode"]),
        ):
            raise LifecycleError("garbage-collection snapshot root identity is inconsistent")
        return snapshot

    def _claim_collecting(
        self,
        *,
        tenant_id: str,
        output_id: str,
        expected_owner: str | None = None,
    ) -> sqlite3.Row | None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._select_lifecycle_row(
                connection, tenant_id=tenant_id, output_id=output_id
            )
            if row is None or row["state"] != "collecting":
                return None
            owner = row["collection_owner"]
            lease = row["collection_lease_until"]
            phase = row["collection_phase"]
            if (
                not isinstance(lease, str)
                or phase not in {"prepared", "quarantined", "verified"}
            ):
                raise LifecycleError("collecting ownership metadata is invalid")
            owner = self._collection_token_value(owner)
            try:
                _created_at_value(lease)
                lease_instant = datetime.fromisoformat(lease[:-1] + "+00:00")
                now_instant = datetime.fromisoformat(now[:-1] + "+00:00")
            except (ArtifactValidationError, TypeError, ValueError) as exc:
                raise LifecycleError("collecting lease is invalid") from exc
            if expected_owner is None:
                if lease_instant > now_instant:
                    return None
                claimed_owner = self._new_collection_token()
            else:
                if owner != expected_owner:
                    return None
                claimed_owner = expected_owner
            claimed = connection.execute(
                "UPDATE lifecycle_outputs SET collection_owner = ?, "
                "collection_lease_until = ?, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? AND state = 'collecting' "
                "AND collection_owner = ? AND collection_lease_until = ? "
                "AND collection_phase = ?",
                (
                    claimed_owner,
                    _utc_after(LIFECYCLE_LEASE_SECONDS),
                    now,
                    tenant_id,
                    output_id,
                    owner,
                    lease,
                    phase,
                ),
            )
            if claimed.rowcount != 1:
                return None
            return self._select_lifecycle_row(
                connection, tenant_id=tenant_id, output_id=output_id
            )

    def _renew_collection_lease(self, row: sqlite3.Row) -> None:
        owner = self._collection_token_value(row["collection_owner"])
        with self._connect() as connection:
            renewed = connection.execute(
                "UPDATE lifecycle_outputs SET collection_lease_until = ?, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? AND state = 'collecting' "
                "AND collection_owner = ? AND collection_phase = ?",
                (
                    _utc_after(LIFECYCLE_LEASE_SECONDS),
                    _utc_now(),
                    row["tenant_id"],
                    row["output_id"],
                    owner,
                    row["collection_phase"],
                ),
            )
            if renewed.rowcount != 1:
                raise LifecycleError("garbage-collection lease ownership was lost")

    def _advance_collection_phase(
        self, row: sqlite3.Row, *, previous: str, current: str
    ) -> sqlite3.Row:
        owner = self._collection_token_value(row["collection_owner"])
        with self._connect() as connection:
            advanced = connection.execute(
                "UPDATE lifecycle_outputs SET collection_phase = ?, "
                "collection_lease_until = ?, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? AND state = 'collecting' "
                "AND collection_owner = ? AND collection_phase = ?",
                (
                    current,
                    _utc_after(LIFECYCLE_LEASE_SECONDS),
                    _utc_now(),
                    row["tenant_id"],
                    row["output_id"],
                    owner,
                    previous,
                ),
            )
            if advanced.rowcount != 1:
                raise LifecycleError("garbage-collection phase ownership was lost")
            refreshed = self._select_lifecycle_row(
                connection,
                tenant_id=str(row["tenant_id"]),
                output_id=str(row["output_id"]),
            )
            if refreshed is None:
                raise LifecycleError("garbage-collection row disappeared")
            return refreshed

    def _persist_verified_snapshot(
        self, row: sqlite3.Row, quarantine_path: Path, snapshot: _TreeSnapshot
    ) -> sqlite3.Row:
        owner = self._collection_token_value(row["collection_owner"])
        payload = self._snapshot_envelope(row, quarantine_path, snapshot)
        digest = sha256_bytes(payload)
        with self._connect() as connection:
            persisted = connection.execute(
                "UPDATE lifecycle_outputs SET quarantine_verified = 1, "
                "quarantine_snapshot = ?, quarantine_snapshot_digest = ?, "
                "collection_phase = 'verified', collection_lease_until = ?, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? AND state = 'collecting' "
                "AND collection_owner = ? AND collection_phase = 'quarantined' "
                "AND quarantine_verified = 0",
                (
                    payload,
                    digest,
                    _utc_after(LIFECYCLE_LEASE_SECONDS),
                    _utc_now(),
                    row["tenant_id"],
                    row["output_id"],
                    owner,
                ),
            )
            if persisted.rowcount != 1:
                raise LifecycleError("quarantine changed before snapshot persistence")
            refreshed = self._select_lifecycle_row(
                connection,
                tenant_id=str(row["tenant_id"]),
                output_id=str(row["output_id"]),
            )
            if refreshed is None:
                raise LifecycleError("garbage-collection row disappeared")
            return refreshed

    def _finish_collection(
        self, row: sqlite3.Row, *, state: str, expected_phase: str
    ) -> None:
        if state not in {"stale", "superseded", "collected"}:
            raise LifecycleError("garbage-collection completion state is invalid")
        owner = self._collection_token_value(row["collection_owner"])
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE lifecycle_outputs SET state = ?, collecting_from = NULL, "
                "quarantine_path = NULL, quarantine_verified = 0, "
                "quarantine_snapshot = NULL, quarantine_snapshot_digest = NULL, "
                "collection_owner = NULL, collection_lease_until = NULL, "
                "collection_phase = NULL, updated_at = ? "
                "WHERE tenant_id = ? AND output_id = ? AND state = 'collecting' "
                "AND collection_owner = ? AND collection_phase = ?",
                (
                    state,
                    _utc_now(),
                    row["tenant_id"],
                    row["output_id"],
                    owner,
                    expected_phase,
                ),
            )
            if updated.rowcount != 1:
                raise LifecycleError("garbage-collection completion ownership was lost")

    def recover_collecting(self, *, tenant_id: str | None = None) -> tuple[str, ...]:
        """Reconcile crash-interrupted quarantine operations without deleting unknown data."""

        if tenant_id is not None:
            tenant_id = _safe_segment(tenant_id, "tenant_id")
        fence = self._acquire_gc_fence()
        if fence is None:
            return ()
        try:
            return self._recover_collecting_locked(tenant_id=tenant_id, fence=fence)
        finally:
            self._release_gc_fence(fence)

    def _recover_collecting_locked(
        self, *, tenant_id: str | None, fence: _LifecycleFence
    ) -> tuple[str, ...]:
        with self._connect() as connection:
            if tenant_id is None:
                collecting_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_outputs "
                        "WHERE state = 'collecting'"
                    ).fetchone()[0]
                )
            else:
                collecting_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_outputs "
                        "WHERE state = 'collecting' AND tenant_id = ?",
                        (tenant_id,),
                    ).fetchone()[0]
                )
        if collecting_count > MAX_LIFECYCLE_RESULTS:
            raise LifecycleError("collecting recovery result limit exceeded")
        recovered: list[str] = []
        last_tenant_id = ""
        last_output_id = ""
        while True:
            with self._connect() as connection:
                if tenant_id is None:
                    candidates = connection.execute(
                        "SELECT tenant_id, output_id FROM lifecycle_outputs "
                        "WHERE state = 'collecting' AND (tenant_id > ? OR "
                        "(tenant_id = ? AND output_id > ?)) "
                        "ORDER BY tenant_id, output_id LIMIT ?",
                        (
                            last_tenant_id,
                            last_tenant_id,
                            last_output_id,
                            LIFECYCLE_PAGE_SIZE,
                        ),
                    ).fetchall()
                else:
                    candidates = connection.execute(
                        "SELECT tenant_id, output_id FROM lifecycle_outputs "
                        "WHERE state = 'collecting' AND tenant_id = ? "
                        "AND output_id > ? ORDER BY output_id LIMIT ?",
                        (tenant_id, last_output_id, LIFECYCLE_PAGE_SIZE),
                    ).fetchall()
            if not candidates:
                break
            for candidate in candidates:
                row = self._claim_collecting(
                    tenant_id=str(candidate["tenant_id"]),
                    output_id=str(candidate["output_id"]),
                )
                if row is None:
                    continue
                self._recover_collecting_row(row, recovered, fence)
                if len(recovered) > MAX_LIFECYCLE_RESULTS:
                    raise LifecycleError("collecting recovery result limit exceeded")
            last_tenant_id = str(candidates[-1]["tenant_id"])
            last_output_id = str(candidates[-1]["output_id"])
        return tuple(recovered)

    def _recover_collecting_row(
        self,
        row: sqlite3.Row,
        recovered: list[str],
        fence: _LifecycleFence,
    ) -> None:
        self._assert_gc_fence(fence)
        if row["layout_version"] != LIFECYCLE_LAYOUT_VERSION:
            raise LifecycleError("legacy collecting output requires an explicit migration")
        output_path = self._checked_output_path(
            Path(row["output_path"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            revision_id=str(row["revision_id"]),
            output_id=str(row["output_id"]),
        )
        quarantine_path = self._row_quarantine_path(row)
        output_exists = self._safe_directory_exists(output_path, "collecting output path")
        quarantine_exists = self._safe_directory_exists(
            quarantine_path, "collecting quarantine path"
        )
        if output_exists and quarantine_exists:
            raise LifecycleError("both output and quarantine paths exist during recovery")
        phase = str(row["collection_phase"])
        if output_exists:
            if (
                phase not in {"prepared", "quarantined"}
                or row["quarantine_verified"] != 0
            ):
                raise LifecycleError("collecting phase contradicts the output namespace")
            if phase == "quarantined":
                # A restoration rename may have committed while its parent-directory
                # sync failed. Re-establish both namespace barriers before treating
                # the original path as safely restored.
                self._assert_gc_fence(fence)
                self._establish_rename_durability(output_path, quarantine_path)
                self._assert_gc_fence(fence)
            self._renew_collection_lease(row)
            self._verify_row_path(row, output_path, normal_path=True)
            self._renew_collection_lease(row)
            previous = row["collecting_from"]
            if previous not in {"stale", "superseded"}:
                raise LifecycleError("collecting output lacks a recoverable prior state")
            self._assert_gc_fence(fence)
            self._finish_collection(row, state=str(previous), expected_phase=phase)
        elif quarantine_exists:
            if phase == "prepared":
                self._assert_gc_fence(fence)
                self._establish_rename_durability(output_path, quarantine_path)
                self._assert_gc_fence(fence)
                row = self._advance_collection_phase(
                    row, previous="prepared", current="quarantined"
                )
                phase = "quarantined"
            if phase == "quarantined":
                self._renew_collection_lease(row)
                verified_tree = self._verify_row_path(
                    row, quarantine_path, normal_path=False
                )
                row = self._persist_verified_snapshot(
                    row, quarantine_path, verified_tree
                )
                phase = "verified"
            if phase != "verified":
                raise LifecycleError("collecting phase is unsupported")
            verified_tree = self._verified_snapshot(row, quarantine_path)
            self._renew_collection_lease(row)
            self._assert_gc_fence(fence)
            _delete_directory_tree_nofollow(
                quarantine_path.parent,
                quarantine_path.name,
                expected=verified_tree,
                allow_missing=True,
            )
            self._assert_gc_fence(fence)
            self._renew_collection_lease(row)
            self._finish_collection(row, state="collected", expected_phase="verified")
        else:
            if phase != "verified" or row["quarantine_verified"] != 1:
                raise LifecycleError(
                    "missing output has no verified deletion envelope; outcome is unknown"
                )
            self._verified_snapshot(row, quarantine_path)
            self._assert_gc_fence(fence)
            self._establish_rename_durability(output_path, quarantine_path)
            self._assert_gc_fence(fence)
            self._finish_collection(row, state="collected", expected_phase="verified")
        recovered.append(str(row["output_id"]))

    def collect_garbage(
        self, *, tenant_id: str, dry_run: bool = True
    ) -> tuple[str, ...]:
        candidates = self.gc_candidates(tenant_id=tenant_id)
        if dry_run:
            return candidates
        fence = self._acquire_gc_fence()
        if fence is None:
            raise LifecycleError("another garbage-collection operation is active")
        try:
            return self._collect_garbage_locked(
                tenant_id=tenant_id, candidates=candidates, fence=fence
            )
        finally:
            self._release_gc_fence(fence)

    def _collect_garbage_locked(
        self,
        *,
        tenant_id: str,
        candidates: tuple[str, ...],
        fence: _LifecycleFence,
    ) -> tuple[str, ...]:
        collected: list[str] = []
        for output_id in candidates:
            self._assert_gc_fence(fence)
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._select_lifecycle_row(
                    connection, tenant_id=tenant_id, output_id=output_id
                )
                references = connection.execute(
                    "SELECT COUNT(*) FROM lifecycle_references "
                    "WHERE tenant_id = ? AND output_id = ?",
                    (tenant_id, output_id),
                ).fetchone()[0]
                if (
                    row is None
                    or row["state"] not in {"stale", "superseded"}
                    or row["legal_hold"]
                    or references
                ):
                    continue
                if row["layout_version"] != LIFECYCLE_LAYOUT_VERSION:
                    raise LifecycleError(
                        "legacy lifecycle layout requires an explicit verified migration"
                    )
                path = self._checked_output_path(
                    Path(row["output_path"]),
                    tenant_id=tenant_id,
                    project_id=str(row["project_id"]),
                    revision_id=str(row["revision_id"]),
                    output_id=output_id,
                )
                quarantine_path = self._quarantine_path(
                    tenant_id=tenant_id,
                    output_id=output_id,
                    manifest_digest=str(row["manifest_digest"]),
                )
                operation_token = self._new_collection_token()
                prepared = connection.execute(
                    "UPDATE lifecycle_outputs SET state = 'collecting', collecting_from = ?, "
                    "quarantine_path = ?, quarantine_verified = 0, "
                    "quarantine_snapshot = NULL, quarantine_snapshot_digest = NULL, "
                    "collection_owner = ?, collection_lease_until = ?, "
                    "collection_phase = 'prepared', updated_at = ? "
                    "WHERE tenant_id = ? AND output_id = ? "
                    "AND state IN ('stale', 'superseded')",
                    (
                        row["state"],
                        str(quarantine_path),
                        operation_token,
                        _utc_after(LIFECYCLE_LEASE_SECONDS),
                        _utc_now(),
                        tenant_id,
                        output_id,
                    ),
                )
                if prepared.rowcount != 1:
                    continue
                row = self._select_lifecycle_row(
                    connection, tenant_id=tenant_id, output_id=output_id
                )
                if row is None:
                    raise LifecycleError("garbage-collection row disappeared")
            try:
                self._renew_collection_lease(row)
                source_tree = self._verify_row_path(row, path, normal_path=True)
                self._renew_collection_lease(row)
                try:
                    self._assert_gc_fence(fence)
                    durable = _rename_no_replace(
                        path,
                        quarantine_path,
                        expected_source_identity=(
                            source_tree.root_device,
                            source_tree.root_inode,
                        ),
                        expected_source_snapshot=source_tree,
                    )
                    self._assert_gc_fence(fence)
                except PublicationError as exc:
                    raise LifecycleError("cannot atomically quarantine managed output") from exc
                if durable is not True:
                    raise LifecycleError("quarantine rename durability is unknown")
                row = self._advance_collection_phase(
                    row, previous="prepared", current="quarantined"
                )
                try:
                    self._renew_collection_lease(row)
                    quarantine_tree = self._verify_row_path(
                        row, quarantine_path, normal_path=False
                    )
                except LifecycleError:
                    try:
                        self._renew_collection_lease(row)
                        self._assert_gc_fence(fence)
                        restore_durable = _rename_no_replace(
                            quarantine_path,
                            path,
                            expected_source_identity=(
                                int(row["fs_device"]),
                                int(row["fs_inode"]),
                            ),
                            expected_source_snapshot=source_tree,
                        )
                        self._assert_gc_fence(fence)
                    except PublicationError as restore_error:
                        raise LifecycleError(
                            "quarantined identity mismatch and safe restoration failed"
                        ) from restore_error
                    if restore_durable is not True:
                        raise LifecycleError(
                            "safe restoration committed with unknown durability"
                        )
                    previous = row["collecting_from"]
                    if previous not in {"stale", "superseded"}:
                        raise LifecycleError(
                            "collecting output lacks a recoverable prior state"
                        )
                    self._finish_collection(
                        row, state=str(previous), expected_phase="quarantined"
                    )
                    raise
                row = self._persist_verified_snapshot(row, quarantine_path, quarantine_tree)
                self._renew_collection_lease(row)
                self._assert_gc_fence(fence)
                _delete_directory_tree_nofollow(
                    quarantine_path.parent,
                    quarantine_path.name,
                    expected=quarantine_tree,
                    allow_missing=True,
                )
                self._assert_gc_fence(fence)
                self._renew_collection_lease(row)
            except LifecycleError:
                current = self._claim_collecting(
                    tenant_id=tenant_id,
                    output_id=output_id,
                    expected_owner=str(row["collection_owner"]),
                )
                if current is not None and current["collection_phase"] == "prepared":
                    output_exists = self._safe_directory_exists(
                        path, "collecting output path"
                    )
                    quarantine_exists = self._safe_directory_exists(
                        quarantine_path, "collecting quarantine path"
                    )
                    if output_exists and not quarantine_exists:
                        previous = current["collecting_from"]
                        if previous in {"stale", "superseded"}:
                            self._finish_collection(
                                current,
                                state=str(previous),
                                expected_phase="prepared",
                            )
                raise
            self._finish_collection(row, state="collected", expected_phase="verified")
            collected.append(output_id)
        return tuple(collected)
