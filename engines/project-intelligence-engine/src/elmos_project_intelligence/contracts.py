"""Typed, fail-closed contracts shared by the project-intelligence core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import os
import re
from typing import Any

from .canonical import JsonValue, canonical_value, validate_digest


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")
_OPERATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")


def require_identifier(value: str, *, field_name: str) -> str:
    """Validate an opaque storage-scope identifier.

    Restricting identifiers prevents ambiguous empty scopes, control
    characters, and accidental path-like values from entering persistent keys.
    """

    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must match {_IDENTIFIER.pattern} and be at most 128 bytes"
        )
    if len(value.encode("utf-8")) > 128:
        raise ValueError(f"{field_name} must be at most 128 UTF-8 bytes")
    return value


def require_operation(value: str) -> str:
    if not isinstance(value, str) or _OPERATION.fullmatch(value) is None:
        raise ValueError("operation is empty or contains unsupported characters")
    return value


def require_relative_path(value: str, *, field_name: str = "path") -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{field_name} must be a non-empty relative POSIX path")
    if value.startswith("/") or "\\" in value:
        raise ValueError(f"{field_name} must be a relative POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{field_name} contains an unsafe path component")
    return value


def _freeze_json(value: Any) -> JsonValue:
    return canonical_value(value)


class EntryKind(StrEnum):
    FILE = "file"
    SYMLINK = "symlink"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class EvidenceState(StrEnum):
    NOT_RUN = "NOT_RUN"
    COLLECTED = "COLLECTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class IdempotencyDisposition(StrEnum):
    CREATED = "CREATED"
    REPLAYED = "REPLAYED"


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    code: str
    message: str
    details: JsonValue = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_operation(self.code)
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("error message must be non-empty")
        object.__setattr__(self, "details", _freeze_json(self.details))


@dataclass(frozen=True, slots=True)
class Result[T]:
    """A result that cannot represent ambiguous partial success."""

    ok: bool
    value: T | None = None
    error: ErrorInfo | None = None

    def __post_init__(self) -> None:
        if self.ok and (self.value is None or self.error is not None):
            raise ValueError("successful Result requires value and forbids error")
        if not self.ok and (self.value is not None or self.error is None):
            raise ValueError("failed Result requires error and forbids value")

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(ok=True, value=value)

    @classmethod
    def failure(
        cls,
        *,
        code: str,
        message: str,
        details: JsonValue | None = None,
    ) -> "Result[T]":
        return cls(
            ok=False,
            error=ErrorInfo(
                code=code,
                message=message,
                details={} if details is None else details,
            ),
        )


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    max_files: int = 20_000
    max_total_bytes: int = 256 * 1024 * 1024
    max_file_bytes: int = 8 * 1024 * 1024
    max_depth: int = 64
    max_path_bytes: int = 4_096
    max_secret_fingerprints_per_file: int = 64

    def __post_init__(self) -> None:
        bounds = {
            "max_files": (self.max_files, 1, 1_000_000),
            "max_total_bytes": (self.max_total_bytes, 1, 16 * 1024**3),
            "max_file_bytes": (self.max_file_bytes, 1, 1024**3),
            "max_depth": (self.max_depth, 1, 256),
            "max_path_bytes": (self.max_path_bytes, 16, 16_384),
            "max_secret_fingerprints_per_file": (
                self.max_secret_fingerprints_per_file,
                0,
                1_024,
            ),
        }
        for name, (value, minimum, maximum) in bounds.items():
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            if value < minimum or value > maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
        if self.max_file_bytes > self.max_total_bytes:
            raise ValueError("max_file_bytes cannot exceed max_total_bytes")


DEFAULT_EXCLUSIONS = (
    ".git",
    ".git/**",
    ".hg",
    ".hg/**",
    ".svn",
    ".svn/**",
    ".venv",
    ".venv/**",
    "node_modules",
    "node_modules/**",
    "**/node_modules",
    "**/node_modules/**",
    ".next",
    ".next/**",
    "**/.next",
    "**/.next/**",
    "__pycache__",
    "__pycache__/**",
    "**/__pycache__",
    "**/__pycache__/**",
)


def _validate_exclusion(pattern: str) -> str:
    if not isinstance(pattern, str) or not pattern or "\x00" in pattern:
        raise ValueError("exclusion patterns must be non-empty strings")
    if pattern.startswith("/") or "\\" in pattern:
        raise ValueError("exclusion patterns must be relative POSIX patterns")
    if any(part == ".." for part in pattern.split("/")):
        raise ValueError("exclusion pattern cannot contain '..'")
    if len(pattern.encode("utf-8")) > 1_024:
        raise ValueError("exclusion pattern exceeds 1024 UTF-8 bytes")
    return pattern


@dataclass(frozen=True, slots=True)
class SnapshotRequest:
    tenant_id: str
    project_id: str
    run_id: str
    root: str | os.PathLike[str]
    limits: SnapshotLimits = field(default_factory=SnapshotLimits)
    exclusions: tuple[str, ...] = DEFAULT_EXCLUSIONS

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, field_name="tenant_id")
        require_identifier(self.project_id, field_name="project_id")
        require_identifier(self.run_id, field_name="run_id")
        root = os.fspath(self.root)
        if not isinstance(root, str) or not root or "\x00" in root:
            raise ValueError("root must be a non-empty filesystem path")
        object.__setattr__(self, "root", root)
        if not isinstance(self.limits, SnapshotLimits):
            raise TypeError("limits must be SnapshotLimits")
        exclusions = tuple(_validate_exclusion(item) for item in self.exclusions)
        if len(exclusions) > 1_024:
            raise ValueError("at most 1024 exclusion patterns are supported")
        object.__setattr__(self, "exclusions", exclusions)


@dataclass(frozen=True, slots=True)
class SecretFingerprint:
    kind: str
    fingerprint: str
    occurrences: int

    def __post_init__(self) -> None:
        require_operation(self.kind)
        object.__setattr__(self, "fingerprint", validate_digest(self.fingerprint))
        if self.occurrences < 1:
            raise ValueError("occurrences must be positive")


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    path: str
    kind: EntryKind
    size: int
    mode: int
    mtime_ns: int
    content_digest: str
    metadata_digest: str
    secret_fingerprints: tuple[SecretFingerprint, ...] = ()
    text: str | None = None

    def __post_init__(self) -> None:
        require_relative_path(self.path)
        if not isinstance(self.kind, EntryKind):
            raise TypeError("kind must be EntryKind")
        if self.size < 0 or self.mode < 0 or self.mtime_ns < 0:
            raise ValueError("snapshot metadata values cannot be negative")
        object.__setattr__(self, "content_digest", validate_digest(self.content_digest))
        object.__setattr__(
            self, "metadata_digest", validate_digest(self.metadata_digest)
        )
        object.__setattr__(self, "secret_fingerprints", tuple(self.secret_fingerprints))
        if self.kind is EntryKind.SYMLINK and self.secret_fingerprints:
            raise ValueError("symlink entries cannot carry secret fingerprints")
        if self.kind is EntryKind.SYMLINK and self.text is not None:
            raise ValueError("symlink entries cannot carry decoded text")
        if self.text is not None:
            if not isinstance(self.text, str):
                raise TypeError("text must be a string or None")
            if len(self.text.encode("utf-8", errors="strict")) != self.size:
                raise ValueError("decoded text byte length does not match entry size")

    @property
    def sha256(self) -> str:
        """Bare SHA-256 hex for compact file manifests."""

        return self.content_digest.partition(":")[2]

    @property
    def bytes(self) -> int:
        """Alias used by repository-analysis file contracts."""

        return self.size

    def to_manifest_entry(self, *, include_text: bool = False) -> JsonValue:
        entry: dict[str, JsonValue] = {
            "path": self.path,
            "kind": self.kind.value,
            "sha256": self.sha256,
            "bytes": self.size,
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "metadata_digest": self.metadata_digest,
            "secret_fingerprints": [
                {
                    "kind": finding.kind,
                    "fingerprint": finding.fingerprint,
                    "occurrences": finding.occurrences,
                }
                for finding in self.secret_fingerprints
            ],
        }
        if include_text and self.text is not None:
            entry["text"] = self.text
        return entry


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    tenant_id: str
    project_id: str
    run_id: str
    root_label: str
    entries: tuple[SnapshotEntry, ...]
    file_count: int
    symlink_count: int
    total_bytes: int
    exclusions: tuple[str, ...]
    snapshot_digest: str
    stable: bool = True

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, field_name="tenant_id")
        require_identifier(self.project_id, field_name="project_id")
        require_identifier(self.run_id, field_name="run_id")
        if not self.root_label or "/" in self.root_label or "\\" in self.root_label:
            raise ValueError("root_label must be a single non-empty path component")
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        paths = [entry.path for entry in entries]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("snapshot entries must be uniquely path-sorted")
        if self.file_count != sum(e.kind is EntryKind.FILE for e in entries):
            raise ValueError("file_count does not match entries")
        if self.symlink_count != sum(e.kind is EntryKind.SYMLINK for e in entries):
            raise ValueError("symlink_count does not match entries")
        if self.total_bytes != sum(
            entry.size for entry in entries if entry.kind is EntryKind.FILE
        ):
            raise ValueError("total_bytes does not match file entries")
        if not self.stable:
            raise ValueError("an unstable snapshot cannot be represented as successful")
        object.__setattr__(
            self, "snapshot_digest", validate_digest(self.snapshot_digest)
        )

    def digest_manifest(self, *, include_text: bool = False) -> JsonValue:
        """Return the deterministic payload covered by ``snapshot_digest``.

        Scope identifiers and wall-clock time are intentionally absent so an
        identical repository snapshot has the same content identity in every
        authorized tenant run.  Text is omitted by default to avoid accidental
        source disclosure; its SHA-256 remains present.
        """

        return {
            "schema_version": "elmos.project-intelligence.snapshot.v1",
            "root_label": self.root_label,
            "files": [
                entry.to_manifest_entry(include_text=include_text)
                for entry in self.entries
            ],
            "file_count": self.file_count,
            "symlink_count": self.symlink_count,
            "total_bytes": self.total_bytes,
            "exclusions": list(self.exclusions),
            "stable": True,
        }

    def to_manifest(self, *, include_text: bool = False) -> JsonValue:
        """Return a deterministic JSON-ready snapshot manifest."""

        manifest = dict(self.digest_manifest(include_text=include_text))
        manifest.update(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "run_id": self.run_id,
                "snapshot_digest": self.snapshot_digest,
            }
        )
        return manifest

    def read_text(self, path: str) -> str:
        """Read immutable UTF-8 text captured during the stable snapshot read.

        This performs no filesystem access, avoiding a second-read TOCTOU gap.
        """

        require_relative_path(path)
        for entry in self.entries:
            if entry.path == path:
                if entry.kind is not EntryKind.FILE:
                    raise ValueError(f"snapshot path is not a regular file: {path}")
                if entry.text is None:
                    raise ValueError(f"snapshot file is not valid UTF-8 text: {path}")
                return entry.text
        raise KeyError(path)


type SnapshotResult = Result[RepositorySnapshot]


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    tenant_id: str
    project_id: str
    metadata: JsonValue
    created_at: str


@dataclass(frozen=True, slots=True)
class CreateRunRequest:
    tenant_id: str
    project_id: str
    run_id: str
    operation: str
    idempotency_key: str
    request: JsonValue

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, field_name="tenant_id")
        require_identifier(self.project_id, field_name="project_id")
        require_identifier(self.run_id, field_name="run_id")
        require_operation(self.operation)
        require_identifier(self.idempotency_key, field_name="idempotency_key")
        object.__setattr__(self, "request", _freeze_json(self.request))


@dataclass(frozen=True, slots=True)
class RunRecord:
    tenant_id: str
    project_id: str
    run_id: str
    operation: str
    request_digest: str
    status: RunStatus
    response: JsonValue | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    disposition: IdempotencyDisposition
    run: RunRecord


@dataclass(frozen=True, slots=True)
class ArtifactInput:
    artifact_id: str
    kind: str
    content_digest: str
    byte_count: int
    media_type: str
    metadata: JsonValue = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_identifier(self.artifact_id, field_name="artifact_id")
        require_operation(self.kind)
        object.__setattr__(self, "content_digest", validate_digest(self.content_digest))
        if self.byte_count < 0:
            raise ValueError("byte_count cannot be negative")
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ValueError("media_type must be non-empty")
        object.__setattr__(self, "metadata", _freeze_json(self.metadata))


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    tenant_id: str
    project_id: str
    run_id: str
    artifact_id: str
    kind: str
    content_digest: str
    byte_count: int
    media_type: str
    metadata: JsonValue
    created_at: str


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    evidence_id: str
    kind: str
    subject_digest: str
    state: EvidenceState
    details: JsonValue = field(default_factory=dict)
    artifact_id: str | None = None
    verifier: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.evidence_id, field_name="evidence_id")
        require_operation(self.kind)
        object.__setattr__(self, "subject_digest", validate_digest(self.subject_digest))
        if not isinstance(self.state, EvidenceState):
            raise TypeError("state must be EvidenceState")
        if self.artifact_id is not None:
            require_identifier(self.artifact_id, field_name="artifact_id")
        if self.verifier is not None:
            require_identifier(self.verifier, field_name="verifier")
            raise ValueError(
                "repository-local evidence cannot name an independent verifier"
            )
        if self.state in {EvidenceState.VERIFIED, EvidenceState.REJECTED}:
            raise ValueError(
                "repository-local evidence cannot claim VERIFIED or REJECTED"
            )
        object.__setattr__(self, "details", _freeze_json(self.details))


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    tenant_id: str
    project_id: str
    run_id: str
    evidence_id: str
    kind: str
    subject_digest: str
    state: EvidenceState
    details: JsonValue
    artifact_id: str | None
    verifier: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    tenant_id: str
    project_id: str
    run_id: str
    sequence: int
    state_digest: str
    state: JsonValue
    created_at: str


@dataclass(frozen=True, slots=True)
class EventRecord:
    tenant_id: str
    project_id: str
    run_id: str
    sequence: int
    event_type: str
    payload_digest: str
    payload: JsonValue
    created_at: str


__all__ = [
    "ArtifactInput",
    "ArtifactRecord",
    "CheckpointRecord",
    "CreateRunRequest",
    "DEFAULT_EXCLUSIONS",
    "EntryKind",
    "ErrorInfo",
    "EventRecord",
    "EvidenceInput",
    "EvidenceRecord",
    "EvidenceState",
    "IdempotencyDecision",
    "IdempotencyDisposition",
    "ProjectRecord",
    "RepositorySnapshot",
    "Result",
    "RunRecord",
    "RunStatus",
    "SecretFingerprint",
    "SnapshotEntry",
    "SnapshotLimits",
    "SnapshotRequest",
    "SnapshotResult",
    "require_identifier",
    "require_operation",
    "require_relative_path",
]
