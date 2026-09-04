#!/usr/bin/env python3
"""Build references and verify signed Spring launch evidence receipts.

The module is deliberately an intake verifier, not an evidence producer.  It can
hash bytes already present below an explicitly approved root, calculate canonical
JSON digests, and verify Ed25519 envelopes against a separate trust store.  It
never creates a ``PASSED_EXTERNAL`` claim and it never signs on behalf of an
executor, verifier, reviewer, approver, or design partner.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (  # noqa: E402
    TrustedKey,
    TrustStore,
    canonical_bytes,
    canonical_digest,
    decode_signature,
    read_regular_file_once,
)

NAMESPACE = "batch30-spring-launch-external-evidence"
BUSINESS_LINE = "spring-legacy-modernization"
ROUTE_ID = "boot-2.7-maven-to-boot-3.5.3-java-21"
PROFILE = ROOT / "deploy" / "production" / "spring-launch-profile.json"
DEFAULT_MAX_AGE = timedelta(hours=72)
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_CONTENT_BYTES = 5 * 1024 * 1024 * 1024
MAX_GATE_EVIDENCE_BYTES = 512 * 1024 * 1024
ED25519_SPKI_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")
ED25519_SIGNATURE_BYTES = 64

GATE_IDS = (
    "STAGING_DEPLOYMENT",
    "ROOTLESS_ISOLATION_ATTESTATION",
    "DEFAULT_DENY_NETWORK_ATTESTATION",
    "INDEPENDENT_VERIFICATION",
    "ROLLBACK_AND_RESTORE_DRILL",
    "DESIGN_PARTNER_ACCEPTANCE",
    "SECURITY_AND_PRIVACY_REVIEW",
    "OPERATIONS_SLO_SIGNOFF",
    "LEGAL_TAX_PAYMENT_READINESS",
)

EXECUTOR_ROLE = "spring-launch-evidence-executor"
VERIFIER_ROLE = "spring-launch-gate-verifier"
REVIEWER_ROLE = "spring-launch-independent-reviewer"
APPROVER_ROLE = "spring-launch-release-approver"
DESIGN_PARTNER_ROLE = "spring-launch-design-partner-approver"
INDEX_AUTHORITY_ROLE = "spring-launch-evidence-index-authority"
ALLOWED_ROLES = {
    EXECUTOR_ROLE,
    VERIFIER_ROLE,
    REVIEWER_ROLE,
    APPROVER_ROLE,
    DESIGN_PARTNER_ROLE,
    INDEX_AUTHORITY_ROLE,
}

# This is the byte-level handoff between the safe environment-file loader and
# the signed environment manifest.  Values are configuration or host paths;
# secret file contents are deliberately excluded.
SPRING_CONFIGURATION_ENV_KEYS = (
    "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
    "ELMOS_SPRING_CODING_AGENT_ENABLED",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED",
    "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_PROXY_ENABLED",
    "ELMOS_SPRING_PROXY_MULTI_TENANT",
    "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
    "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
    "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED",
    "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
    "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
    "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
    "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID",
    "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}$")
UTC_INSTANT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?Z$"
)
NON_SUCCESS = {
    "UNKNOWN",
    "INCONCLUSIVE",
    "NOT_RUN",
    "NOT_EVALUATED",
    "NOT_APPLICABLE",
    "UNSUPPORTED",
    "BLOCKED",
    "CHANGE_ME",
}
PLACEHOLDER_PREFIXES = (
    "CHANGE_ME",
    "PLACEHOLDER",
    "TODO",
    "TBD",
)

TOP_LEVEL_FIELDS = {
    "schema_version",
    "namespace",
    "receipt_id",
    "business_line",
    "route_id",
    "observed_at",
    "binding",
    "binding_digest",
    "principals",
    "evidence_index",
    "gates",
    "approvals",
    "design_partner_acceptances",
    "independent_review",
    "receipt_digest",
}
BINDING_FIELDS = {
    "deployed_revision",
    "launch_profile",
    "artifact",
    "environment",
}
CONTENT_REFERENCE_FIELDS = {"uri", "digest", "size_bytes", "media_type"}
EVIDENCE_REFERENCE_FIELDS = {*CONTENT_REFERENCE_FIELDS, "verification"}
PRINCIPAL_FIELDS = {"actor_id", "organization_id"}
ENVELOPE_FIELDS = {"algorithm", "key_id", "payload", "signature"}
COMMON_PAYLOAD_FIELDS = {
    "record_id",
    "issued_at",
    "expires_at",
    "actor_id",
    "organization_id",
    "role",
    "receipt_id",
    "binding_digest",
    "evidence_set_digest",
    "outcome",
    "synthetic",
    "unknowns",
    "not_run",
}
EXECUTION_PAYLOAD_FIELDS = {
    *COMMON_PAYLOAD_FIELDS,
    "gate_id",
    "evidence_uri",
    "evidence_digest",
    "evidence_size_bytes",
    "evidence_class",
}
VERIFICATION_PAYLOAD_FIELDS = {
    *EXECUTION_PAYLOAD_FIELDS,
    "execution_record_id",
    "execution_payload_digest",
}
APPROVAL_PAYLOAD_FIELDS = {*COMMON_PAYLOAD_FIELDS, "approval_scope"}
PARTNER_PAYLOAD_FIELDS = {*COMMON_PAYLOAD_FIELDS, "partner_organization_id"}
REVIEW_PAYLOAD_FIELDS = {*COMMON_PAYLOAD_FIELDS, "review_subject_digest"}
INDEX_PAYLOAD_FIELDS = {
    "record_id",
    "issued_at",
    "expires_at",
    "actor_id",
    "organization_id",
    "role",
    "receipt_id",
    "binding_digest",
    "index_id",
    "index_content_digest",
    "index_content_size_bytes",
    "outcome",
    "synthetic",
    "unknowns",
    "not_run",
}


class SpringLaunchEvidenceError(ValueError):
    """A Spring launch receipt failed closed."""


@dataclass(frozen=True)
class ContentObservation:
    uri: str
    digest: str
    size_bytes: int
    media_type: str
    path: Path
    content: bytes


@dataclass(frozen=True)
class OpenedLocalFile:
    descriptor: int
    parent_descriptor: int
    filename: str
    path: Path


@dataclass(frozen=True)
class SecureFileSnapshot:
    content: bytes
    stat_result: os.stat_result


@dataclass(frozen=True)
class KeyMetadata:
    key_id: str
    actor_id: str
    organization_id: str
    role: str
    public_key_digest: str


@dataclass(frozen=True)
class LoadedTrust:
    store: TrustStore
    metadata: dict[str, KeyMetadata]


@dataclass(frozen=True)
class VerifiedEnvelope:
    payload: dict[str, Any]
    key_id: str
    actor_id: str
    organization_id: str
    role: str
    public_key_digest: str
    payload_digest: str
    envelope_digest: str
    issued_at: datetime


@dataclass(frozen=True)
class ControlledIndex:
    index_id: str
    content_digest: str
    entries: dict[str, dict[str, Any]]
    attestation: VerifiedEnvelope


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpringLaunchEvidenceError(f"{label} must be an object")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise SpringLaunchEvidenceError(
            f"{label} fields are invalid; missing={missing}, extra={extra}"
        )


def _identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or IDENTITY_RE.fullmatch(value) is None
        or _is_non_success_sentinel(value)
    ):
        raise SpringLaunchEvidenceError(
            f"{label} must be an exact non-placeholder identity"
        )
    return value


def _is_non_success_sentinel(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized in NON_SUCCESS:
        return True
    if any(normalized.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES):
        return True
    return any(
        normalized.startswith(prefix + separator)
        for prefix in NON_SUCCESS
        for separator in ("_", "-", ":")
    )


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise SpringLaunchEvidenceError(
            f"{label} must be sha256:<64 lowercase hex>"
        )
    return value


def _positive_size(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SpringLaunchEvidenceError(f"{label} must be a positive integer")
    return value


def _utc_instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_INSTANT_RE.fullmatch(value) is None:
        raise SpringLaunchEvidenceError(
            f"{label} must be an RFC3339 UTC instant ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpringLaunchEvidenceError(f"{label} is not a valid RFC3339 instant") from exc
    return parsed.astimezone(timezone.utc)


def _reject_non_success(value: Any, label: str) -> None:
    if isinstance(value, str) and _is_non_success_sentinel(value):
        raise SpringLaunchEvidenceError(
            f"{label} contains non-success or placeholder sentinel {value}"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_success(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_success(item, f"{label}[{index}]")


def _approved_roots(values: Iterable[Path]) -> tuple[Path, ...]:
    candidates = list(values)
    if not candidates:
        raise SpringLaunchEvidenceError(
            "at least one explicit --evidence-root is required"
        )
    roots: list[Path] = []
    for candidate in candidates:
        supplied = candidate.expanduser()
        if supplied.is_symlink():
            raise SpringLaunchEvidenceError(
                f"evidence root must not be a symlink: {candidate}"
            )
        try:
            resolved = supplied.resolve(strict=True)
        except OSError as exc:
            raise SpringLaunchEvidenceError(
                f"evidence root does not exist: {candidate}"
            ) from exc
        if not resolved.is_dir():
            raise SpringLaunchEvidenceError(
                f"evidence root must be a directory: {resolved}"
            )
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_local_file(
    uri: Any, roots: tuple[Path, ...], label: str
) -> OpenedLocalFile:
    if not isinstance(uri, str) or not uri:
        raise SpringLaunchEvidenceError(f"{label} is required")
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise SpringLaunchEvidenceError(f"{label} must be an absolute local file URI")
    lexical = Path(os.path.abspath(Path(unquote(parsed.path))))
    containing_root = next((root for root in roots if _within(lexical, (root,))), None)
    if containing_root is None:
        raise SpringLaunchEvidenceError(
            f"{label} escapes approved evidence roots or is not a canonical path"
        )
    relative = lexical.relative_to(containing_root)
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise SpringLaunchEvidenceError(f"{label} has an invalid relative path")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    current_descriptor = -1
    file_descriptor = -1
    try:
        current_descriptor = os.open(containing_root, directory_flags)
        root_opened = os.fstat(current_descriptor)
        root_path = os.stat(containing_root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or _stat_identity(root_opened) != _stat_identity(root_path)
        ):
            raise SpringLaunchEvidenceError(
                f"{label} approved root changed while it was opened"
            )
        for part in relative.parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            opened = os.fstat(next_descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(next_descriptor)
                raise SpringLaunchEvidenceError(
                    f"{label} contains a non-directory path component"
                )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        filename = relative.parts[-1]
        file_descriptor = os.open(filename, file_flags, dir_fd=current_descriptor)
        opened_file = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened_file.st_mode):
            raise SpringLaunchEvidenceError(f"{label} must resolve to a regular file")
        return OpenedLocalFile(
            descriptor=file_descriptor,
            parent_descriptor=current_descriptor,
            filename=filename,
            path=containing_root / relative,
        )
    except (OSError, SpringLaunchEvidenceError) as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if current_descriptor >= 0:
            os.close(current_descriptor)
        if isinstance(exc, SpringLaunchEvidenceError):
            raise
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened beneath its approved root: {exc}"
        ) from exc


def _open_absolute_file(path: Path, label: str) -> OpenedLocalFile:
    """Open an absolute file by walking every directory with no-follow openat."""

    supplied = path.expanduser()
    if not supplied.is_absolute():
        raise SpringLaunchEvidenceError(f"{label} path must be absolute")
    components = supplied.parts[1:]
    if not components or any(part in {"", ".", ".."} for part in components):
        raise SpringLaunchEvidenceError(f"{label} path is invalid")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    current_descriptor = -1
    file_descriptor = -1
    try:
        current_descriptor = os.open(Path(supplied.anchor), directory_flags)
        for part in components[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            opened = os.fstat(next_descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(next_descriptor)
                raise SpringLaunchEvidenceError(
                    f"{label} contains a non-directory path component"
                )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        filename = components[-1]
        file_descriptor = os.open(filename, file_flags, dir_fd=current_descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise SpringLaunchEvidenceError(f"{label} must be a regular file")
        return OpenedLocalFile(
            descriptor=file_descriptor,
            parent_descriptor=current_descriptor,
            filename=filename,
            path=supplied,
        )
    except (OSError, SpringLaunchEvidenceError) as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if current_descriptor >= 0:
            os.close(current_descriptor)
        if isinstance(exc, SpringLaunchEvidenceError):
            raise
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened without following links: {exc}"
        ) from exc


def _open_absolute_directory(path: Path, label: str) -> int:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        raise SpringLaunchEvidenceError(f"{label} path must be absolute")
    components = supplied.parts[1:]
    if any(part in {"", ".", ".."} for part in components):
        raise SpringLaunchEvidenceError(f"{label} path is invalid")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(Path(supplied.anchor), flags)
        for part in components:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened without following links: {exc}"
        ) from exc


def _read_secure_absolute_file(
    path: Path,
    *,
    max_bytes: int,
    label: str,
    allowed_modes: set[int] | None = None,
) -> SecureFileSnapshot:
    opened_file = _open_absolute_file(path, label)
    descriptor = opened_file.descriptor
    try:
        opened = os.fstat(descriptor)
        mode = stat.S_IMODE(opened.st_mode)
        if opened.st_uid != os.getuid():
            raise SpringLaunchEvidenceError(f"{label} must be owned by the current account")
        if opened.st_nlink != 1:
            raise SpringLaunchEvidenceError(f"{label} must have exactly one hard link")
        if allowed_modes is not None:
            if mode not in allowed_modes:
                rendered = ", ".join(f"{item:04o}" for item in sorted(allowed_modes))
                raise SpringLaunchEvidenceError(f"{label} mode must be one of {rendered}")
        elif mode & 0o022 or mode & 0o111 or not mode & 0o400:
            raise SpringLaunchEvidenceError(
                f"{label} must be owner-readable, non-executable, and not group/other writable"
            )
        if opened.st_size > max_bytes:
            raise SpringLaunchEvidenceError(f"{label} exceeds the byte budget")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise SpringLaunchEvidenceError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SpringLaunchEvidenceError(f"{label} changed while being read")
        completed = os.fstat(descriptor)
        path_after = os.stat(
            opened_file.filename,
            dir_fd=opened_file.parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _stat_identity(completed) != _stat_identity(opened)
            or _stat_identity(path_after) != _stat_identity(opened)
        ):
            raise SpringLaunchEvidenceError(f"{label} changed while it was verified")
        return SecureFileSnapshot(b"".join(chunks), opened)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"{label} could not be read safely: {exc}") from exc
    finally:
        os.close(descriptor)
        os.close(opened_file.parent_descriptor)


def _snapshot_content_reference(
    value: Any,
    roots: tuple[Path, ...],
    label: str,
    *,
    max_bytes: int = MAX_CONTENT_BYTES,
    capture_content: bool = True,
) -> ContentObservation:
    reference = _object(value, label)
    _exact_fields(reference, CONTENT_REFERENCE_FIELDS, label)
    uri = reference.get("uri")
    digest = _digest(reference.get("digest"), f"{label}.digest")
    size = _positive_size(reference.get("size_bytes"), f"{label}.size_bytes")
    media_type = reference.get("media_type")
    if not isinstance(media_type, str) or not media_type or len(media_type) > 200:
        raise SpringLaunchEvidenceError(f"{label}.media_type is invalid")
    opened_local = _open_local_file(uri, roots, f"{label}.uri")
    descriptor = opened_local.descriptor
    chunks: list[bytes] = []
    digest_value = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise SpringLaunchEvidenceError(
                f"{label}.uri must resolve to a regular file descriptor"
            )
        if opened.st_size > max_bytes:
            raise SpringLaunchEvidenceError(f"{label} exceeds the byte budget")
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise SpringLaunchEvidenceError(f"{label} changed while being read")
            digest_value.update(chunk)
            if capture_content:
                chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SpringLaunchEvidenceError(f"{label} changed while being read")
        completed = os.fstat(descriptor)
        path_after = os.stat(
            opened_local.filename,
            dir_fd=opened_local.parent_descriptor,
            follow_symlinks=False,
        )
    finally:
        os.close(descriptor)
        os.close(opened_local.parent_descriptor)
    if (
        _stat_identity(completed) != _stat_identity(opened)
        or _stat_identity(path_after) != _stat_identity(opened)
    ):
        raise SpringLaunchEvidenceError(f"{label} changed while it was verified")
    actual_digest = "sha256:" + digest_value.hexdigest()
    if size != opened.st_size:
        raise SpringLaunchEvidenceError(
            f"{label} byte count mismatch: expected {size}, observed {opened.st_size}"
        )
    if digest != actual_digest:
        raise SpringLaunchEvidenceError(
            f"{label} digest mismatch: expected {digest}, observed {actual_digest}"
        )
    return ContentObservation(
        uri=str(uri),
        digest=digest,
        size_bytes=size,
        media_type=media_type,
        path=opened_local.path,
        content=b"".join(chunks),
    )


def _immutable_uri(value: Any, digest: str, label: str) -> str:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise SpringLaunchEvidenceError(f"{label} must be a non-empty URI")
    parsed = urlparse(value)
    if parsed.scheme == "file":
        if (
            parsed.netloc not in {"", "localhost"}
            or not parsed.path.startswith("/")
            or parsed.query
            or parsed.fragment
        ):
            raise SpringLaunchEvidenceError(
                f"{label} file URI must be absolute and cannot carry query or fragment"
            )
        return value
    digest_hex = digest.removeprefix("sha256:")
    if parsed.scheme == "cas":
        if parsed.query or parsed.fragment:
            raise SpringLaunchEvidenceError(
                f"{label} CAS identity cannot carry query or fragment"
            )
        if f"{parsed.netloc}{parsed.path}".lstrip("/") != f"sha256/{digest_hex}":
            raise SpringLaunchEvidenceError(
                f"{label} CAS identity must equal the declared digest"
            )
        return value
    if parsed.scheme not in {"https", "s3", "gs", "az"} or not parsed.netloc:
        raise SpringLaunchEvidenceError(
            f"{label} must use file, cas, https, s3, gs, or az"
        )
    decoded_path = unquote(parsed.path)
    if (
        parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in decoded_path)
    ):
        raise SpringLaunchEvidenceError(
            f"{label} remote URI contains credentials, fragment, whitespace, or control characters"
        )
    query: dict[str, list[str]] = {}
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        query.setdefault(key.lower(), []).extend(values)
    digest_pins = [
        item
        for key in ("sha256", "digest")
        for item in query.get(key, [])
    ]
    if any(not item for item in digest_pins):
        raise SpringLaunchEvidenceError(
            f"{label} digest query pin cannot be empty"
        )
    if digest_pins and any(
        item not in {digest_hex, f"sha256:{digest_hex}"} for item in digest_pins
    ):
        raise SpringLaunchEvidenceError(
            f"{label} digest query pin must equal the declared content digest"
        )
    scheme_version_keys = {
        "https": set(),
        "s3": {"versionid"},
        "gs": {"generation"},
        "az": {"versionid", "snapshot"},
    }
    version_values = [
        item
        for key in scheme_version_keys[parsed.scheme]
        for item in query.get(key, [])
    ]
    valid_version = re.compile(r"^[A-Za-z0-9._~:+/=\-]{1,512}$")
    if any(valid_version.fullmatch(item) is None for item in version_values):
        raise SpringLaunchEvidenceError(
            f"{label} version pin contains whitespace, control characters, or invalid length"
        )
    if any(
        item.lower() in {"latest", "current", "head", "null"}
        or _is_non_success_sentinel(item)
        for item in version_values
    ):
        raise SpringLaunchEvidenceError(
            f"{label} version pin cannot use a mutable or placeholder value"
        )
    if parsed.scheme == "gs" and any(
        re.fullmatch(r"[1-9][0-9]{0,30}", item) is None for item in version_values
    ):
        raise SpringLaunchEvidenceError(
            f"{label} gs generation pin must be a positive decimal integer"
        )
    version_pinned = any(
        item for item in version_values
    )
    path_digests = re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", parsed.path)
    if path_digests and any(item != digest_hex for item in path_digests):
        raise SpringLaunchEvidenceError(
            f"{label} digest path pin must equal the declared content digest"
        )
    if not version_pinned and not digest_pins and digest_hex not in path_digests:
        raise SpringLaunchEvidenceError(
            f"{label} remote URI must carry a version/generation/snapshot/digest pin"
        )
    return value


def _load_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = item
        return result

    try:
        value = json.loads(
            content.decode("utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {constant}")
            ),
            object_pairs_hook=strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SpringLaunchEvidenceError(f"{label} must be strict UTF-8 JSON: {exc}") from exc
    return _object(value, label)


def _canonical_json_document(content: bytes, label: str) -> dict[str, Any]:
    value = _load_json_bytes(content, label)
    if content != canonical_bytes(value):
        raise SpringLaunchEvidenceError(
            f"{label} bytes must be canonical JSON (sorted keys, UTF-8, no whitespace)"
        )
    return value


def _validate_trust_store_path(path: Path, evidence_roots: tuple[Path, ...]) -> Path:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        raise SpringLaunchEvidenceError("Spring launch trust store path must be absolute")
    try:
        path_stat = os.stat(supplied, follow_symlinks=False)
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"Spring launch trust store is unavailable: {exc}"
        ) from exc
    if stat.S_ISLNK(path_stat.st_mode) or supplied != resolved:
        raise SpringLaunchEvidenceError(
            "Spring launch trust store path must be canonical and contain no symlink"
        )
    if not stat.S_ISREG(path_stat.st_mode):
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must be a regular file"
        )
    if path_stat.st_uid != os.getuid():
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must be owned by the current account"
        )
    if stat.S_IMODE(path_stat.st_mode) not in {0o400, 0o600}:
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must use owner-only mode 0400 or 0600"
        )
    if path_stat.st_nlink != 1:
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must have exactly one hard link"
        )
    if evidence_roots and _within(resolved, evidence_roots):
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must be outside all evidence roots"
        )
    return resolved


@lru_cache(maxsize=256)
def _canonical_ed25519_spki(public_key_bytes: bytes) -> bytes:
    try:
        completed = subprocess.run(
            ["openssl", "pkey", "-pubin", "-outform", "DER"],
            input=public_key_bytes,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"OpenSSL public-key decode failed: {exc}") from exc
    der = completed.stdout
    if (
        completed.returncode != 0
        or len(der) != len(ED25519_SPKI_DER_PREFIX) + 32
        or not der.startswith(ED25519_SPKI_DER_PREFIX)
    ):
        raise ValueError("public key is not canonical Ed25519 SubjectPublicKeyInfo")
    return der


def _ed25519_spki_digest(public_key_bytes: bytes, label: str) -> str:
    """Return a representation-independent Ed25519 SPKI fingerprint."""

    try:
        der = _canonical_ed25519_spki(public_key_bytes)
    except ValueError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} must be an Ed25519 SubjectPublicKeyInfo public key: {exc}"
        ) from exc
    return "sha256:" + hashlib.sha256(der).hexdigest()


def _load_trust(
    path: Path, *, evidence_roots: tuple[Path, ...] = ()
) -> LoadedTrust:
    canonical_path = _validate_trust_store_path(path, evidence_roots)
    snapshot = _read_secure_absolute_file(
        canonical_path,
        max_bytes=1024 * 1024,
        label="Spring launch trust store",
        allowed_modes={0o400, 0o600},
    )
    document = _load_json_bytes(snapshot.content, "Spring launch trust store")
    trust = _object(document, "trust store")
    _exact_fields(
        trust,
        {"schema_version", "namespace", "keys", "revoked_record_ids"},
        "trust store",
    )
    if (
        type(trust.get("schema_version")) is not int
        or trust.get("schema_version") != 1
        or trust.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("trust store identity is invalid")
    records = trust.get("keys")
    if not isinstance(records, list) or not records:
        raise SpringLaunchEvidenceError("trust store keys must be a non-empty array")
    revoked_ids = trust.get("revoked_record_ids")
    if (
        not isinstance(revoked_ids, list)
        or len(set(map(str, revoked_ids))) != len(revoked_ids)
        or any(not isinstance(item, str) or not item for item in revoked_ids)
    ):
        raise SpringLaunchEvidenceError("trust store revoked_record_ids is invalid")
    metadata: dict[str, KeyMetadata] = {}
    trusted_keys: dict[str, TrustedKey] = {}
    raw_public_key_digests: dict[str, str] = {}
    key_fields = {
        "key_id",
        "actor_id",
        "organization_id",
        "roles",
        "public_key_path",
        "not_before",
        "not_after",
        "revoked",
    }
    for index, raw in enumerate(records):
        item = _object(raw, f"trust store key {index}")
        _exact_fields(item, key_fields, f"trust store key {index}")
        key_id = _identity(item.get("key_id"), f"trust store key {index}.key_id")
        if key_id in metadata:
            raise SpringLaunchEvidenceError(f"duplicate trust key identity: {key_id}")
        actor = _identity(item.get("actor_id"), f"trust store key {key_id}.actor_id")
        organization = _identity(
            item.get("organization_id"), f"trust store key {key_id}.organization_id"
        )
        roles = item.get("roles")
        if not isinstance(roles, list) or len(roles) != 1 or roles[0] not in ALLOWED_ROLES:
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id} must have exactly one allowed role"
            )
        not_before = _utc_instant(
            item.get("not_before"), f"trust store key {key_id}.not_before"
        )
        not_after = _utc_instant(
            item.get("not_after"), f"trust store key {key_id}.not_after"
        )
        if not_after <= not_before:
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id} validity window is invalid"
            )
        if not isinstance(item.get("revoked"), bool):
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id}.revoked must be boolean"
            )
        relative_key = item.get("public_key_path")
        if (
            not isinstance(relative_key, str)
            or not relative_key
            or Path(relative_key).is_absolute()
            or ".." in Path(relative_key).parts
        ):
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id}.public_key_path is invalid"
            )
        key_path = canonical_path.parent / relative_key
        key_snapshot = _read_secure_absolute_file(
            key_path,
            max_bytes=64 * 1024,
            label=f"trust store key {key_id}",
        )
        public_digest = _ed25519_spki_digest(
            key_snapshot.content,
            f"trust store key {key_id}.public_key_path",
        )
        raw_public_key_digests[key_id] = (
            "sha256:" + hashlib.sha256(key_snapshot.content).hexdigest()
        )
        if item["revoked"] is False:
            trusted_keys[key_id] = TrustedKey(
                key_id=key_id,
                roles=frozenset(roles),
                public_key_path=key_path,
                public_key_bytes=key_snapshot.content,
                public_key_digest=raw_public_key_digests[key_id],
                not_before=not_before,
                not_after=not_after,
            )
        metadata[key_id] = KeyMetadata(
            key_id=key_id,
            actor_id=actor,
            organization_id=organization,
            role=roles[0],
            public_key_digest=public_digest,
        )
    after_load = os.stat(canonical_path, follow_symlinks=False)
    if _stat_identity(after_load) != _stat_identity(snapshot.stat_result):
        raise SpringLaunchEvidenceError(
            "Spring launch trust store changed while its keys were loaded"
        )
    store = TrustStore(
        path=canonical_path,
        keys=trusted_keys,
        revoked_record_ids=frozenset(revoked_ids),
        digest=canonical_digest(
            {
                "trust_store": "sha256:" + hashlib.sha256(snapshot.content).hexdigest(),
                "public_keys": dict(sorted(raw_public_key_digests.items())),
            }
        ),
    )
    return LoadedTrust(store=store, metadata=metadata)


def _verify_envelope(
    loaded: LoadedTrust,
    value: Any,
    *,
    role: str,
    expected_fields: set[str],
    bindings: dict[str, Any],
    now: datetime,
    expected_principal: dict[str, str] | None = None,
) -> VerifiedEnvelope:
    envelope = _object(value, f"{role} envelope")
    _exact_fields(envelope, ENVELOPE_FIELDS, f"{role} envelope")
    if envelope.get("algorithm") != "ed25519":
        raise SpringLaunchEvidenceError(
            f"{role} envelope algorithm must be exactly ed25519"
        )
    key_id = envelope.get("key_id")
    if not isinstance(key_id, str) or key_id not in loaded.metadata:
        raise SpringLaunchEvidenceError(f"{role} signing key is unknown")
    metadata = loaded.metadata[key_id]
    if metadata.role != role:
        raise SpringLaunchEvidenceError(
            f"{role} signing key must be dedicated to exactly that role"
        )
    if expected_principal is not None and (
        metadata.actor_id != expected_principal["actor_id"]
        or metadata.organization_id != expected_principal["organization_id"]
    ):
        raise SpringLaunchEvidenceError(
            f"{role} signer does not match its declared principal"
        )
    payload = _object(envelope.get("payload"), f"{role} payload")
    _exact_fields(payload, expected_fields, f"{role} payload")
    _identity(payload.get("record_id"), f"{role} payload.record_id")
    issued_at = _utc_instant(payload.get("issued_at"), f"{role} payload.issued_at")
    _utc_instant(payload.get("expires_at"), f"{role} payload.expires_at")
    if payload.get("actor_id") != metadata.actor_id:
        raise SpringLaunchEvidenceError(f"{role} signed actor does not match trust store")
    if payload.get("organization_id") != metadata.organization_id:
        raise SpringLaunchEvidenceError(
            f"{role} signed organization does not match trust store"
        )
    if payload.get("role") != role:
        raise SpringLaunchEvidenceError(f"{role} payload role binding is invalid")
    if payload.get("synthetic") is not False:
        raise SpringLaunchEvidenceError(f"{role} payload.synthetic must be false")
    for field in ("unknowns", "not_run"):
        if not isinstance(payload.get(field), list) or payload[field]:
            raise SpringLaunchEvidenceError(
                f"{role} payload.{field} must be an exact empty array"
            )
    for field in ("evidence_size_bytes", "index_content_size_bytes"):
        if field in payload:
            _positive_size(payload[field], f"{role} payload.{field}")
    _reject_non_success(payload, f"{role} payload")
    try:
        decoded_signature = decode_signature(envelope.get("signature"))
    except (TypeError, ValueError) as exc:
        raise SpringLaunchEvidenceError(
            f"{role} signature is not valid base64"
        ) from exc
    if len(decoded_signature) != ED25519_SIGNATURE_BYTES:
        raise SpringLaunchEvidenceError(
            f"{role} signature must decode to exactly {ED25519_SIGNATURE_BYTES} bytes"
        )
    try:
        receipt = loaded.store.verify_envelope(
            envelope,
            required_role=role,
            bindings=bindings,
            now=now,
        )
    except (OSError, ValueError) as exc:
        raise SpringLaunchEvidenceError(
            f"{role} signature verification failed: {exc}"
        ) from exc
    return VerifiedEnvelope(
        payload=payload,
        key_id=key_id,
        actor_id=metadata.actor_id,
        organization_id=metadata.organization_id,
        role=role,
        public_key_digest=metadata.public_key_digest,
        payload_digest=receipt["payload_digest"],
        envelope_digest=canonical_digest(envelope),
        issued_at=issued_at,
    )


def _principal(value: Any, label: str) -> dict[str, str]:
    principal = _object(value, label)
    _exact_fields(principal, PRINCIPAL_FIELDS, label)
    return {
        "actor_id": _identity(principal.get("actor_id"), f"{label}.actor_id"),
        "organization_id": _identity(
            principal.get("organization_id"), f"{label}.organization_id"
        ),
    }


def _expected_revision(value: str | None, repo_root: Path) -> str:
    if value is not None:
        if REVISION_RE.fullmatch(value) is None:
            raise SpringLaunchEvidenceError(
                "expected revision must be 40 lowercase hexadecimal characters"
            )
        return value
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or REVISION_RE.fullmatch(revision) is None:
        raise SpringLaunchEvidenceError("could not resolve the current repository HEAD")
    return revision


def _committed_file_bytes(
    repo_root: Path,
    revision: str,
    path: Path,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    """Read one exact blob from Git without trusting working-tree bytes."""

    try:
        canonical_root = repo_root.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"{label} repository root is unavailable") from exc
    supplied = path if path.is_absolute() else canonical_root / path
    try:
        relative = supplied.relative_to(canonical_root)
    except ValueError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} must be inside the repository"
        ) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise SpringLaunchEvidenceError(f"{label} repository path is invalid")
    object_name = f"{revision}:{relative.as_posix()}"
    try:
        size_result = subprocess.run(
            ["git", "cat-file", "-s", object_name],
            cwd=canonical_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob size could not be resolved"
        ) from exc
    try:
        size = int(size_result.stdout.strip())
    except ValueError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} is not a blob at the expected revision"
        ) from exc
    if size_result.returncode != 0 or size < 0 or size > max_bytes:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob is unavailable or exceeds the byte budget"
        )
    try:
        blob_result = subprocess.run(
            ["git", "cat-file", "blob", object_name],
            cwd=canonical_root,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob could not be read"
        ) from exc
    if blob_result.returncode != 0 or len(blob_result.stdout) != size:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob changed or could not be read exactly"
        )
    return blob_result.stdout


def _validate_environment_manifest(
    observation: ContentObservation,
    *,
    binding: dict[str, Any],
    observed_at: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    if observation.media_type != "application/json":
        raise SpringLaunchEvidenceError(
            "binding.environment.media_type must be application/json"
        )
    document = _canonical_json_document(observation.content, "environment manifest")
    fields = {
        "schema_version",
        "namespace",
        "environment_id",
        "deployment_id",
        "environment_class",
        "provider",
        "region",
        "tenant_mode",
        "execution_plane",
        "deployed_revision",
        "launch_profile_digest",
        "artifact_digest",
        "configuration_digest",
        "network_policy_digest",
        "rootless_policy_digest",
        "runtime_image_digests",
        "captured_at",
        "secrets_embedded",
    }
    _exact_fields(document, fields, "environment manifest")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or document.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("environment manifest identity is invalid")
    for name in ("environment_id", "deployment_id", "provider", "region"):
        _identity(document.get(name), f"environment manifest.{name}")
    if document.get("environment_class") not in {"STAGING", "PRODUCTION"}:
        raise SpringLaunchEvidenceError(
            "environment manifest.environment_class must be STAGING or PRODUCTION"
        )
    if document.get("tenant_mode") != "MULTI_TENANT":
        raise SpringLaunchEvidenceError(
            "environment manifest must bind MULTI_TENANT"
        )
    if document.get("execution_plane") != "PRIVATE_ROOTLESS_RUNNER_BROKER":
        raise SpringLaunchEvidenceError(
            "environment manifest must bind PRIVATE_ROOTLESS_RUNNER_BROKER"
        )
    for name in (
        "configuration_digest",
        "network_policy_digest",
        "rootless_policy_digest",
    ):
        _digest(document.get(name), f"environment manifest.{name}")
    images = document.get("runtime_image_digests")
    if (
        not isinstance(images, dict)
        or len(images) < 3
        or any(not isinstance(name, str) or not name for name in images)
        or any(DIGEST_RE.fullmatch(str(value)) is None for value in images.values())
        or len(set(images.values())) != len(images)
    ):
        raise SpringLaunchEvidenceError(
            "environment manifest.runtime_image_digests must contain at least three distinct digest-pinned images"
        )
    captured_at = _utc_instant(
        document.get("captured_at"), "environment manifest.captured_at"
    )
    if captured_at > observed_at:
        raise SpringLaunchEvidenceError(
            "environment manifest cannot be captured after receipt.observed_at"
        )
    if observed_at - captured_at > max_age:
        raise SpringLaunchEvidenceError(
            "environment manifest capture is older than the allowed evidence age"
        )
    if document.get("secrets_embedded") is not False:
        raise SpringLaunchEvidenceError(
            "environment manifest.secrets_embedded must be exactly false"
        )
    expected = {
        "deployed_revision": binding["deployed_revision"],
        "launch_profile_digest": binding["launch_profile"]["digest"],
        "artifact_digest": binding["artifact"]["digest"],
    }
    for field, expected_value in expected.items():
        if document.get(field) != expected_value:
            raise SpringLaunchEvidenceError(
                f"environment manifest binding mismatch: {field}"
            )
    _reject_non_success(document, "environment manifest")
    return document


def _validate_binding(
    value: Any,
    *,
    roots: tuple[Path, ...],
    expected_revision: str,
    expected_profile_path: Path,
    repo_root: Path,
    observed_at: datetime,
    max_age: timedelta,
) -> tuple[
    dict[str, Any],
    dict[str, ContentObservation],
    dict[str, Any],
]:
    binding = _object(value, "receipt.binding")
    _exact_fields(binding, BINDING_FIELDS, "receipt.binding")
    revision = binding.get("deployed_revision")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise SpringLaunchEvidenceError(
            "receipt.binding.deployed_revision must be 40 lowercase hex"
        )
    if revision != expected_revision:
        raise SpringLaunchEvidenceError(
            "receipt binding deployed_revision does not match the expected repository revision"
        )
    profile = _snapshot_content_reference(
        binding.get("launch_profile"), roots, "binding.launch_profile", max_bytes=1024 * 1024
    )
    artifact = _snapshot_content_reference(
        binding.get("artifact"),
        roots,
        "binding.artifact",
        capture_content=False,
    )
    environment = _snapshot_content_reference(
        binding.get("environment"), roots, "binding.environment", max_bytes=1024 * 1024
    )
    if profile.media_type != "application/json":
        raise SpringLaunchEvidenceError(
            "binding.launch_profile.media_type must be application/json"
        )
    try:
        expected_profile = read_regular_file_once(
            expected_profile_path,
            max_bytes=1024 * 1024,
            label="expected Spring launch profile",
        )
    except (OSError, ValueError) as exc:
        raise SpringLaunchEvidenceError(
            f"expected Spring launch profile could not be read safely: {exc}"
        ) from exc
    committed_profile = _committed_file_bytes(
        repo_root,
        expected_revision,
        expected_profile_path,
        max_bytes=1024 * 1024,
        label="expected Spring launch profile",
    )
    if expected_profile != committed_profile:
        raise SpringLaunchEvidenceError(
            "expected Spring launch profile working-tree bytes do not match the expected revision"
        )
    expected_profile_digest = "sha256:" + hashlib.sha256(committed_profile).hexdigest()
    if (
        profile.digest != expected_profile_digest
        or profile.size_bytes != len(committed_profile)
    ):
        raise SpringLaunchEvidenceError(
            "receipt launch profile does not bind the expected profile bytes"
        )
    digests = {profile.digest, artifact.digest, environment.digest}
    if len(digests) != 3:
        raise SpringLaunchEvidenceError(
            "launch profile, deployed artifact, and environment manifest must be content-distinct"
        )
    environment_manifest = _validate_environment_manifest(
        environment,
        binding=binding,
        observed_at=observed_at,
        max_age=max_age,
    )
    return (
        binding,
        {
            "launch_profile": profile,
            "artifact": artifact,
            "environment": environment,
        },
        environment_manifest,
    )


def _load_controlled_index(
    value: Any,
    *,
    roots: tuple[Path, ...],
    loaded: LoadedTrust,
    receipt_id: str,
    binding_digest: str,
    observed_at: datetime,
    now: datetime,
    max_age: timedelta,
) -> ControlledIndex | None:
    if value is None:
        return None
    item = _object(value, "receipt.evidence_index")
    _exact_fields(item, {"content", "attestation"}, "receipt.evidence_index")
    content = _snapshot_content_reference(
        item.get("content"), roots, "receipt.evidence_index.content", max_bytes=MAX_JSON_BYTES
    )
    if content.media_type != "application/json":
        raise SpringLaunchEvidenceError("controlled evidence index must be application/json")
    document = _canonical_json_document(content.content, "controlled evidence index")
    _exact_fields(
        document,
        {"schema_version", "namespace", "index_id", "generated_at", "entries"},
        "controlled evidence index",
    )
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or document.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("controlled evidence index identity is invalid")
    index_id = _identity(document.get("index_id"), "controlled evidence index.index_id")
    generated_at = _utc_instant(
        document.get("generated_at"), "controlled evidence index.generated_at"
    )
    if generated_at > observed_at:
        raise SpringLaunchEvidenceError(
            "controlled evidence index cannot be generated after receipt.observed_at"
        )
    if observed_at - generated_at > max_age:
        raise SpringLaunchEvidenceError(
            "controlled evidence index is older than the allowed evidence age"
        )
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SpringLaunchEvidenceError(
            "controlled evidence index.entries must be non-empty"
        )
    entries: dict[str, dict[str, Any]] = {}
    entry_fields = {
        "entry_id",
        "uri",
        "digest",
        "size_bytes",
        "media_type",
        "recorded_at",
    }
    for index, raw in enumerate(raw_entries):
        entry = _object(raw, f"controlled evidence index.entries[{index}]")
        _exact_fields(entry, entry_fields, f"controlled evidence index.entries[{index}]")
        entry_id = _identity(entry.get("entry_id"), f"controlled evidence index.entries[{index}].entry_id")
        if entry_id in entries:
            raise SpringLaunchEvidenceError(
                f"duplicate controlled evidence index entry: {entry_id}"
            )
        digest = _digest(entry.get("digest"), f"controlled evidence index entry {entry_id}.digest")
        entry_size = _positive_size(
            entry.get("size_bytes"),
            f"controlled evidence index entry {entry_id}.size_bytes",
        )
        if entry_size > MAX_GATE_EVIDENCE_BYTES:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} exceeds the gate evidence byte budget"
            )
        if not isinstance(entry.get("media_type"), str) or not entry["media_type"]:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id}.media_type is invalid"
            )
        entry_uri = _immutable_uri(
            entry.get("uri"), digest, f"controlled evidence index entry {entry_id}.uri"
        )
        if urlparse(entry_uri).scheme == "file":
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} must use immutable remote or CAS identity"
            )
        recorded_at = _utc_instant(
            entry.get("recorded_at"), f"controlled evidence index entry {entry_id}.recorded_at"
        )
        if recorded_at > generated_at:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} was recorded after index generation"
            )
        if observed_at - recorded_at > max_age:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} is older than the allowed evidence age"
            )
        entries[entry_id] = entry
    bindings = {
        "role": INDEX_AUTHORITY_ROLE,
        "receipt_id": receipt_id,
        "binding_digest": binding_digest,
        "index_id": index_id,
        "index_content_digest": content.digest,
        "index_content_size_bytes": content.size_bytes,
        "outcome": "INDEX_AUTHENTICATED",
        "synthetic": False,
        "unknowns": [],
        "not_run": [],
    }
    attestation = _verify_envelope(
        loaded,
        item.get("attestation"),
        role=INDEX_AUTHORITY_ROLE,
        expected_fields=INDEX_PAYLOAD_FIELDS,
        bindings=bindings,
        now=now,
    )
    if attestation.issued_at < observed_at:
        raise SpringLaunchEvidenceError(
            "controlled evidence index attestation predates receipt.observed_at"
        )
    return ControlledIndex(
        index_id=index_id,
        content_digest=content.digest,
        entries=entries,
        attestation=attestation,
    )


def _verify_evidence_reference(
    value: Any,
    *,
    roots: tuple[Path, ...],
    controlled_index: ControlledIndex | None,
    label: str,
) -> dict[str, Any]:
    reference = _object(value, label)
    _exact_fields(reference, EVIDENCE_REFERENCE_FIELDS, label)
    digest = _digest(reference.get("digest"), f"{label}.digest")
    size = _positive_size(reference.get("size_bytes"), f"{label}.size_bytes")
    media_type = reference.get("media_type")
    if not isinstance(media_type, str) or not media_type:
        raise SpringLaunchEvidenceError(f"{label}.media_type is invalid")
    uri = _immutable_uri(reference.get("uri"), digest, f"{label}.uri")
    verification = _object(reference.get("verification"), f"{label}.verification")
    mode = verification.get("mode")
    if mode == "LOCAL_BYTES":
        _exact_fields(verification, {"mode", "local_uri"}, f"{label}.verification")
        local = {
            "uri": verification.get("local_uri"),
            "digest": digest,
            "size_bytes": size,
            "media_type": media_type,
        }
        observation = _snapshot_content_reference(
            local,
            roots,
            f"{label}.local_bytes",
            max_bytes=MAX_GATE_EVIDENCE_BYTES,
            capture_content=False,
        )
        return {
            "uri": uri,
            "digest": observation.digest,
            "size_bytes": observation.size_bytes,
            "media_type": media_type,
            "verification_mode": mode,
        }
    if mode == "CONTROLLED_INDEX":
        _exact_fields(
            verification,
            {"mode", "entry_id", "entry_digest"},
            f"{label}.verification",
        )
        if controlled_index is None:
            raise SpringLaunchEvidenceError(
                f"{label} requires a signed controlled evidence index"
            )
        if urlparse(uri).scheme == "file":
            raise SpringLaunchEvidenceError(
                f"{label} CONTROLLED_INDEX mode cannot authorize a file URI"
            )
        entry_id = _identity(verification.get("entry_id"), f"{label}.verification.entry_id")
        entry_digest = _digest(
            verification.get("entry_digest"), f"{label}.verification.entry_digest"
        )
        entry = controlled_index.entries.get(entry_id)
        if entry is None:
            raise SpringLaunchEvidenceError(
                f"{label} controlled index entry is missing"
            )
        if canonical_digest(entry) != entry_digest:
            raise SpringLaunchEvidenceError(
                f"{label} controlled index entry digest mismatch"
            )
        expected = {
            "uri": uri,
            "digest": digest,
            "size_bytes": size,
            "media_type": media_type,
        }
        if size > MAX_GATE_EVIDENCE_BYTES:
            raise SpringLaunchEvidenceError(
                f"{label} exceeds the gate evidence byte budget"
            )
        for field, expected_value in expected.items():
            if entry.get(field) != expected_value:
                raise SpringLaunchEvidenceError(
                    f"{label} controlled index binding mismatch: {field}"
                )
        return {
            **expected,
            "verification_mode": mode,
            "index_id": controlled_index.index_id,
            "entry_id": entry_id,
        }
    raise SpringLaunchEvidenceError(
        f"{label}.verification.mode must be LOCAL_BYTES or CONTROLLED_INDEX"
    )


def receipt_digest(value: dict[str, Any]) -> str:
    """Return the canonical digest of all receipt fields except receipt_digest."""

    subject = dict(value)
    subject.pop("receipt_digest", None)
    return canonical_digest(subject)


def spring_environment_configuration_digest(
    environment: Mapping[str, str],
) -> str:
    """Digest the effective Spring launch configuration without secret bytes.

    The contract is canonical JSON over every exact key in
    :data:`SPRING_CONFIGURATION_ENV_KEYS`; absent keys normalize to the empty
    string.  Secret *host paths* are configuration and therefore included, but
    this helper never opens them and never includes their contents.  Callers
    must run the ordinary secret-file validation separately.
    """

    values: dict[str, str] = {}
    for name in SPRING_CONFIGURATION_ENV_KEYS:
        raw = environment.get(name, "")
        if not isinstance(raw, str):
            raise SpringLaunchEvidenceError(
                f"effective Spring environment value {name} must be a string"
            )
        values[name] = raw
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-effective-environment-v1",
            "values": values,
        }
    )


def _register_signer(
    verified: VerifiedEnvelope,
    *,
    record_ids: set[str],
    key_owners: dict[str, tuple[str, str]],
    public_key_owners: dict[str, tuple[str, str]],
    actor_roles: dict[str, str],
    organization_roles: dict[str, str],
) -> None:
    record_id = verified.payload["record_id"]
    if record_id in record_ids:
        raise SpringLaunchEvidenceError("signed record identities must be unique")
    record_ids.add(record_id)
    prior_actor_role = actor_roles.setdefault(verified.actor_id, verified.role)
    if prior_actor_role != verified.role:
        raise SpringLaunchEvidenceError(
            "one actor identity cannot occupy multiple receipt signing roles"
        )
    prior_organization_role = organization_roles.setdefault(
        verified.organization_id, verified.role
    )
    if prior_organization_role != verified.role:
        raise SpringLaunchEvidenceError(
            "one organization cannot occupy multiple receipt signing roles"
        )
    owner = (verified.actor_id, verified.role)
    prior_key_owner = key_owners.setdefault(verified.key_id, owner)
    if prior_key_owner != owner:
        raise SpringLaunchEvidenceError("signing key identity was reused across roles")
    prior_public_owner = public_key_owners.setdefault(
        verified.public_key_digest, owner
    )
    if prior_public_owner != owner:
        raise SpringLaunchEvidenceError(
            "public-key material was reused across actors or roles"
        )


def verify_spring_launch_receipt(
    value: Any,
    *,
    trust_store: Path | LoadedTrust,
    evidence_roots: Iterable[Path],
    expected_revision: str | None = None,
    expected_profile_path: Path = PROFILE,
    expected_trust_store_digest: str | None = None,
    expected_environment_id: str | None = None,
    expected_deployment_id: str | None = None,
    expected_provider: str | None = None,
    expected_region: str | None = None,
    expected_environment_class: str | None = None,
    expected_configuration_digest: str | None = None,
    repo_root: Path = ROOT,
    now: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> dict[str, Any]:
    """Authenticate a complete receipt without changing any launch status."""

    receipt = _object(value, "receipt")
    _exact_fields(receipt, TOP_LEVEL_FIELDS, "receipt")
    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("receipt identity is invalid")
    if receipt.get("business_line") != BUSINESS_LINE:
        raise SpringLaunchEvidenceError("receipt business_line is invalid")
    if receipt.get("route_id") != ROUTE_ID:
        raise SpringLaunchEvidenceError("receipt route_id is invalid")
    receipt_id = _identity(receipt.get("receipt_id"), "receipt.receipt_id")
    _reject_non_success(receipt, "receipt")
    observed_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed_now.utcoffset() != timedelta(0):
        raise SpringLaunchEvidenceError("verification clock must be UTC")
    if max_age <= timedelta(0):
        raise SpringLaunchEvidenceError("max_age must be positive")
    observed_at = _utc_instant(receipt.get("observed_at"), "receipt.observed_at")
    if observed_at > observed_now:
        raise SpringLaunchEvidenceError("receipt.observed_at cannot be in the future")
    if observed_now - observed_at > max_age:
        raise SpringLaunchEvidenceError("receipt external evidence is stale")
    roots = _approved_roots(evidence_roots)
    revision = _expected_revision(expected_revision, repo_root)
    binding, primary, environment_manifest = _validate_binding(
        receipt.get("binding"),
        roots=roots,
        expected_revision=revision,
        expected_profile_path=expected_profile_path,
        repo_root=repo_root,
        observed_at=observed_at,
        max_age=max_age,
    )
    expected_environment_values = {
        "environment_id": expected_environment_id,
        "deployment_id": expected_deployment_id,
        "provider": expected_provider,
        "region": expected_region,
        "environment_class": expected_environment_class,
        "configuration_digest": expected_configuration_digest,
    }
    for field, expected_value in expected_environment_values.items():
        if expected_value is None:
            continue
        if field == "configuration_digest":
            _digest(expected_value, "expected configuration digest")
        elif field == "environment_class":
            if expected_value not in {"STAGING", "PRODUCTION"}:
                raise SpringLaunchEvidenceError(
                    "expected environment class must be STAGING or PRODUCTION"
                )
        else:
            _identity(expected_value, f"expected {field}")
        if environment_manifest[field] != expected_value:
            raise SpringLaunchEvidenceError(
                f"signed environment manifest does not match expected {field}"
            )
    binding_digest = canonical_digest(binding)
    if receipt.get("binding_digest") != binding_digest:
        raise SpringLaunchEvidenceError("receipt.binding_digest mismatch")
    expected_receipt_digest = receipt_digest(receipt)
    if receipt.get("receipt_digest") != expected_receipt_digest:
        raise SpringLaunchEvidenceError("receipt.receipt_digest mismatch")

    principals_raw = _object(receipt.get("principals"), "receipt.principals")
    _exact_fields(
        principals_raw,
        {"execution", "independent_verifier", "independent_reviewer"},
        "receipt.principals",
    )
    principals = {
        name: _principal(principals_raw[name], f"receipt.principals.{name}")
        for name in ("execution", "independent_verifier", "independent_reviewer")
    }
    if len({item["actor_id"] for item in principals.values()}) != 3:
        raise SpringLaunchEvidenceError(
            "execution, verifier, and reviewer actor identities must be distinct"
        )
    if len({item["organization_id"] for item in principals.values()}) != 3:
        raise SpringLaunchEvidenceError(
            "execution, verifier, and reviewer organizations must be distinct"
        )

    if isinstance(trust_store, Path):
        loaded = _load_trust(trust_store, evidence_roots=roots)
    else:
        loaded = trust_store
        _validate_trust_store_path(loaded.store.path, roots)
    if expected_trust_store_digest is not None:
        _digest(expected_trust_store_digest, "expected trust store digest")
        if loaded.store.digest != expected_trust_store_digest:
            raise SpringLaunchEvidenceError(
                "loaded trust store does not match expected trust store digest"
            )
    controlled_index = _load_controlled_index(
        receipt.get("evidence_index"),
        roots=roots,
        loaded=loaded,
        receipt_id=receipt_id,
        binding_digest=binding_digest,
        observed_at=observed_at,
        now=observed_now,
        max_age=max_age,
    )

    raw_gates = receipt.get("gates")
    if not isinstance(raw_gates, list) or len(raw_gates) != len(GATE_IDS):
        raise SpringLaunchEvidenceError("receipt.gates must contain nine exact gates")
    evidence_subject_gates: list[dict[str, Any]] = []
    evidence_observations: list[dict[str, Any]] = []
    for index, expected_gate_id in enumerate(GATE_IDS):
        gate = _object(raw_gates[index], f"receipt.gates[{index}]")
        _exact_fields(
            gate,
            {"id", "status", "evidence", "execution_attestation", "verification_attestation"},
            f"receipt.gates[{index}]",
        )
        if gate.get("id") != expected_gate_id:
            raise SpringLaunchEvidenceError(
                f"receipt.gates[{index}] must be {expected_gate_id}"
            )
        if gate.get("status") != "PASSED_EXTERNAL":
            raise SpringLaunchEvidenceError(
                f"external gate {expected_gate_id} is not PASSED_EXTERNAL"
            )
        observed = _verify_evidence_reference(
            gate.get("evidence"),
            roots=roots,
            controlled_index=controlled_index,
            label=f"receipt.gates[{index}].evidence",
        )
        evidence_subject_gates.append(
            {
                "id": expected_gate_id,
                "status": "PASSED_EXTERNAL",
                "evidence": gate["evidence"],
            }
        )
        evidence_observations.append(observed)
    evidence_digests = [item["digest"] for item in evidence_observations]
    if len(set(evidence_digests)) != len(GATE_IDS):
        raise SpringLaunchEvidenceError(
            "all nine external gates must bind content-distinct evidence"
        )
    primary_digests = {item.digest for item in primary.values()}
    if primary_digests.intersection(evidence_digests):
        raise SpringLaunchEvidenceError(
            "gate evidence must be distinct from profile, artifact, and environment bytes"
        )
    evidence_uris = [item["uri"] for item in evidence_observations]
    if len(set(evidence_uris)) != len(evidence_uris):
        raise SpringLaunchEvidenceError("all nine external gates must use distinct evidence URIs")
    used_index = any(
        item["verification_mode"] == "CONTROLLED_INDEX"
        for item in evidence_observations
    )
    if used_index != (controlled_index is not None):
        raise SpringLaunchEvidenceError(
            "receipt.evidence_index must exist exactly when controlled-index evidence is used"
        )
    evidence_set_digest = canonical_digest(
        {
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "observed_at": receipt["observed_at"],
            "controlled_index_content_digest": (
                controlled_index.content_digest if controlled_index is not None else None
            ),
            "gates": evidence_subject_gates,
        }
    )

    record_ids: set[str] = set()
    key_owners: dict[str, tuple[str, str]] = {}
    public_key_owners: dict[str, tuple[str, str]] = {}
    actor_roles: dict[str, str] = {}
    organization_roles: dict[str, str] = {}
    signed_records: list[VerifiedEnvelope] = []
    if controlled_index is not None:
        if (
            controlled_index.attestation.actor_id
            in {item["actor_id"] for item in principals.values()}
            or controlled_index.attestation.organization_id
            in {item["organization_id"] for item in principals.values()}
        ):
            raise SpringLaunchEvidenceError(
                "controlled-index authority must be separate from execution and assurance principals"
            )
        _register_signer(
            controlled_index.attestation,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        signed_records.append(controlled_index.attestation)

    gate_attestation_subject: list[dict[str, str]] = []
    latest_gate_signature = observed_at
    for index, gate_id in enumerate(GATE_IDS):
        gate = raw_gates[index]
        observed = evidence_observations[index]
        common = {
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "evidence_set_digest": evidence_set_digest,
            "gate_id": gate_id,
            "evidence_uri": observed["uri"],
            "evidence_digest": observed["digest"],
            "evidence_size_bytes": observed["size_bytes"],
            "outcome": "PASSED_EXTERNAL",
            "evidence_class": "EXTERNAL_NON_SYNTHETIC",
            "synthetic": False,
            "unknowns": [],
            "not_run": [],
        }
        execution = _verify_envelope(
            loaded,
            gate.get("execution_attestation"),
            role=EXECUTOR_ROLE,
            expected_fields=EXECUTION_PAYLOAD_FIELDS,
            bindings={"role": EXECUTOR_ROLE, **common},
            now=observed_now,
            expected_principal=principals["execution"],
        )
        if execution.issued_at < observed_at:
            raise SpringLaunchEvidenceError(
                f"{gate_id} execution attestation predates receipt.observed_at"
            )
        _register_signer(
            execution,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        verification_bindings = {
            "role": VERIFIER_ROLE,
            **common,
            "execution_record_id": execution.payload["record_id"],
            "execution_payload_digest": execution.payload_digest,
        }
        verification = _verify_envelope(
            loaded,
            gate.get("verification_attestation"),
            role=VERIFIER_ROLE,
            expected_fields=VERIFICATION_PAYLOAD_FIELDS,
            bindings=verification_bindings,
            now=observed_now,
            expected_principal=principals["independent_verifier"],
        )
        if verification.issued_at < execution.issued_at:
            raise SpringLaunchEvidenceError(
                f"{gate_id} verification attestation predates execution attestation"
            )
        _register_signer(
            verification,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        signed_records.extend((execution, verification))
        latest_gate_signature = max(latest_gate_signature, verification.issued_at)
        gate_attestation_subject.append(
            {
                "gate_id": gate_id,
                "execution_envelope_digest": execution.envelope_digest,
                "verification_envelope_digest": verification.envelope_digest,
            }
        )

    core_actor_ids = {item["actor_id"] for item in principals.values()}
    core_organization_ids = {item["organization_id"] for item in principals.values()}
    approvals_raw = receipt.get("approvals")
    if not isinstance(approvals_raw, list) or len(approvals_raw) < 2:
        raise SpringLaunchEvidenceError("at least two signed external approvals are required")
    approvals: list[VerifiedEnvelope] = []
    approval_scopes: set[str] = set()
    for index, raw in enumerate(approvals_raw):
        envelope = _object(raw, f"receipt.approvals[{index}]")
        payload = _object(envelope.get("payload"), f"receipt.approvals[{index}].payload")
        scope = payload.get("approval_scope")
        if scope not in {"RELEASE_AUTHORIZATION", "RISK_ACCEPTANCE"}:
            raise SpringLaunchEvidenceError(
                "approval_scope must be RELEASE_AUTHORIZATION or RISK_ACCEPTANCE"
            )
        verified = _verify_envelope(
            loaded,
            envelope,
            role=APPROVER_ROLE,
            expected_fields=APPROVAL_PAYLOAD_FIELDS,
            bindings={
                "role": APPROVER_ROLE,
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "approval_scope": scope,
                "outcome": "APPROVED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
            now=observed_now,
        )
        if verified.issued_at < latest_gate_signature:
            raise SpringLaunchEvidenceError(
                "external approval predates completion of gate verification"
            )
        if verified.actor_id in core_actor_ids:
            raise SpringLaunchEvidenceError(
                "external approvers must be separate from execution, verifier, and reviewer"
            )
        if verified.organization_id in core_organization_ids:
            raise SpringLaunchEvidenceError(
                "external approval organizations must be separate from execution and assurance organizations"
            )
        _register_signer(
            verified,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        approvals.append(verified)
        approval_scopes.add(scope)
    if len({item.actor_id for item in approvals}) < 2:
        raise SpringLaunchEvidenceError("external approvals require two distinct actors")
    if len({item.organization_id for item in approvals}) < 2:
        raise SpringLaunchEvidenceError(
            "external approvals require two distinct organizations"
        )
    if approval_scopes != {"RELEASE_AUTHORIZATION", "RISK_ACCEPTANCE"}:
        raise SpringLaunchEvidenceError(
            "external approvals must cover release authorization and risk acceptance"
        )

    partners_raw = receipt.get("design_partner_acceptances")
    if not isinstance(partners_raw, list) or len(partners_raw) < 2:
        raise SpringLaunchEvidenceError(
            "at least two signed design-partner acceptances are required"
        )
    partners: list[VerifiedEnvelope] = []
    for index, raw in enumerate(partners_raw):
        envelope = _object(raw, f"receipt.design_partner_acceptances[{index}]")
        payload = _object(
            envelope.get("payload"),
            f"receipt.design_partner_acceptances[{index}].payload",
        )
        partner_organization = payload.get("partner_organization_id")
        verified = _verify_envelope(
            loaded,
            envelope,
            role=DESIGN_PARTNER_ROLE,
            expected_fields=PARTNER_PAYLOAD_FIELDS,
            bindings={
                "role": DESIGN_PARTNER_ROLE,
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "partner_organization_id": partner_organization,
                "outcome": "ACCEPTED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
            now=observed_now,
        )
        if partner_organization != verified.organization_id:
            raise SpringLaunchEvidenceError(
                "design-partner organization must match its trusted signing identity"
            )
        if verified.issued_at < latest_gate_signature:
            raise SpringLaunchEvidenceError(
                "design-partner acceptance predates completion of gate verification"
            )
        if verified.actor_id in core_actor_ids or verified.organization_id in core_organization_ids:
            raise SpringLaunchEvidenceError(
                "design partners must be separate from execution and assurance principals"
            )
        _register_signer(
            verified,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        partners.append(verified)
    if len({item.actor_id for item in partners}) < 2:
        raise SpringLaunchEvidenceError(
            "design-partner acceptances require two distinct actors"
        )
    partner_organizations = {item.organization_id for item in partners}
    if len(partner_organizations) < 2:
        raise SpringLaunchEvidenceError(
            "design-partner acceptances require two distinct organizations"
        )

    review_subject_digest = canonical_digest(
        {
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "evidence_set_digest": evidence_set_digest,
            "controlled_index_attestation_digest": (
                controlled_index.attestation.envelope_digest
                if controlled_index is not None
                else None
            ),
            "gate_attestations": gate_attestation_subject,
            "approval_envelope_digests": sorted(
                item.envelope_digest for item in approvals
            ),
            "design_partner_envelope_digests": sorted(
                item.envelope_digest for item in partners
            ),
        }
    )
    review = _verify_envelope(
        loaded,
        receipt.get("independent_review"),
        role=REVIEWER_ROLE,
        expected_fields=REVIEW_PAYLOAD_FIELDS,
        bindings={
            "role": REVIEWER_ROLE,
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "evidence_set_digest": evidence_set_digest,
            "review_subject_digest": review_subject_digest,
            "outcome": "REVIEWED",
            "synthetic": False,
            "unknowns": [],
            "not_run": [],
        },
        now=observed_now,
        expected_principal=principals["independent_reviewer"],
    )
    latest_endorsement = max(
        [latest_gate_signature]
        + [item.issued_at for item in approvals]
        + [item.issued_at for item in partners]
        + (
            [controlled_index.attestation.issued_at]
            if controlled_index is not None
            else []
        )
    )
    if review.issued_at < latest_endorsement:
        raise SpringLaunchEvidenceError(
            "independent review predates a gate, approval, or partner endorsement"
        )
    _register_signer(
        review,
        record_ids=record_ids,
        key_owners=key_owners,
        public_key_owners=public_key_owners,
        actor_roles=actor_roles,
        organization_roles=organization_roles,
    )
    signed_records.append(review)

    return {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "receipt_id": receipt_id,
        "business_line": BUSINESS_LINE,
        "route_id": ROUTE_ID,
        "source_revision": binding["deployed_revision"],
        "launch_profile_sha256": primary["launch_profile"].digest.removeprefix("sha256:"),
        "artifact_sha256": primary["artifact"].digest.removeprefix("sha256:"),
        "environment_digest": primary["environment"].digest.removeprefix("sha256:"),
        "environment_id": environment_manifest["environment_id"],
        "deployment_id": environment_manifest["deployment_id"],
        "configuration_digest": environment_manifest["configuration_digest"],
        "network_policy_digest": environment_manifest["network_policy_digest"],
        "rootless_policy_digest": environment_manifest["rootless_policy_digest"],
        "binding_digest": binding_digest,
        "evidence_set_digest": evidence_set_digest,
        "review_subject_digest": review_subject_digest,
        "receipt_digest": expected_receipt_digest,
        "trust_store_digest": loaded.store.digest,
        "observed_at": receipt["observed_at"],
        "verified_gate_ids": list(GATE_IDS),
        "execution_identity": principals["execution"]["actor_id"],
        "independent_verifier": principals["independent_verifier"]["actor_id"],
        "independent_reviewer": principals["independent_reviewer"]["actor_id"],
        "approved_by": sorted(item.actor_id for item in approvals),
        "design_partner_organizations": sorted(partner_organizations),
        "evidence_status": "VERIFIED_EXTERNAL_RECEIPT",
        "external_evidence_intake": "VALIDATED_NOT_CERTIFIED",
        "certification": "NOT_CERTIFIED",
        "certification_promoted": False,
        "synthetic_evidence_can_promote": False,
    }


def verify_spring_launch_receipt_file(
    path: Path,
    *,
    trust_store: Path | LoadedTrust,
    evidence_roots: Iterable[Path],
    expected_revision: str | None = None,
    expected_profile_path: Path = PROFILE,
    expected_trust_store_digest: str | None = None,
    expected_environment_id: str | None = None,
    expected_deployment_id: str | None = None,
    expected_provider: str | None = None,
    expected_region: str | None = None,
    expected_environment_class: str | None = None,
    expected_configuration_digest: str | None = None,
    repo_root: Path = ROOT,
    now: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> dict[str, Any]:
    """Read a bounded receipt snapshot and authenticate it."""

    roots = _approved_roots(evidence_roots)
    supplied = path.expanduser()
    if not supplied.is_absolute() or not _within(supplied, roots):
        raise SpringLaunchEvidenceError(
            "Spring launch receipt must be an absolute path below an evidence root"
        )
    snapshot = _read_secure_absolute_file(
        supplied,
        max_bytes=MAX_JSON_BYTES,
        label="Spring launch receipt",
    )
    raw = snapshot.content
    value = _load_json_bytes(raw, "Spring launch receipt")
    result = verify_spring_launch_receipt(
        value,
        trust_store=trust_store,
        evidence_roots=roots,
        expected_revision=expected_revision,
        expected_profile_path=expected_profile_path,
        expected_trust_store_digest=expected_trust_store_digest,
        expected_environment_id=expected_environment_id,
        expected_deployment_id=expected_deployment_id,
        expected_provider=expected_provider,
        expected_region=expected_region,
        expected_environment_class=expected_environment_class,
        expected_configuration_digest=expected_configuration_digest,
        repo_root=repo_root,
        now=now,
        max_age=max_age,
    )
    return {
        **result,
        "receipt_file_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "receipt_file_size_bytes": len(raw),
    }


def content_reference(
    path: Path,
    *,
    evidence_roots: Iterable[Path],
    media_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Create a digest reference for existing bytes below an approved root."""

    roots = _approved_roots(evidence_roots)
    supplied = Path(os.path.abspath(path.expanduser()))
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError("reference file does not exist") from exc
    if supplied != resolved:
        raise SpringLaunchEvidenceError(
            "reference file path must be canonical and contain no symlink"
        )
    opened_local = _open_local_file(resolved.as_uri(), roots, "reference file")
    # Stream once to derive the digest, then use the ordinary verifier on future
    # intake.  This command never copies, uploads, or signs the source bytes.
    descriptor = opened_local.descriptor
    digest_value = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size <= 0
            or opened.st_size > MAX_CONTENT_BYTES
        ):
            raise SpringLaunchEvidenceError("reference file is invalid or exceeds the byte budget")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest_value.update(chunk)
        completed = os.fstat(descriptor)
        path_after = os.stat(
            opened_local.filename,
            dir_fd=opened_local.parent_descriptor,
            follow_symlinks=False,
        )
    finally:
        os.close(descriptor)
        os.close(opened_local.parent_descriptor)
    if (
        _stat_identity(opened) != _stat_identity(completed)
        or _stat_identity(path_after) != _stat_identity(completed)
    ):
        raise SpringLaunchEvidenceError("reference file changed while being hashed")
    return {
        "uri": opened_local.path.as_uri(),
        "digest": "sha256:" + digest_value.hexdigest(),
        "size_bytes": opened.st_size,
        "media_type": media_type,
    }


def assemble_spring_launch_receipt(
    draft: dict[str, Any],
    **verification_options: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Add only the canonical receipt digest, then verify all existing evidence.

    The input must already contain every external success claim and every signature.
    No status, payload, identity, evidence byte, or signature is synthesized here.
    """

    if "receipt_digest" in draft:
        raise SpringLaunchEvidenceError(
            "assembly draft must omit receipt_digest; use verify for a finalized receipt"
        )
    assembled = copy.deepcopy(draft)
    assembled["receipt_digest"] = receipt_digest(assembled)
    result = verify_spring_launch_receipt(assembled, **verification_options)
    return assembled, result


def _load_cli_json(path: Path, label: str) -> dict[str, Any]:
    snapshot = _read_secure_absolute_file(
        path,
        max_bytes=MAX_JSON_BYTES,
        label=label,
    )
    return _load_json_bytes(snapshot.content, label)


def _write_new_owner_only(path: Path, content: bytes) -> None:
    supplied = path.expanduser()
    if not supplied.is_absolute() or supplied.name in {"", ".", ".."}:
        raise SpringLaunchEvidenceError("output path must be an absolute file path")
    try:
        parent = supplied.parent.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"output parent must be an existing directory: {exc}"
        ) from exc
    if supplied.parent != parent:
        raise SpringLaunchEvidenceError(
            "output path ancestors must be canonical and contain no symlink"
        )
    if parent == ROOT or ROOT in parent.parents:
        raise SpringLaunchEvidenceError(
            "assembled external evidence output must be outside the repository"
        )
    try:
        parent_stat = os.stat(parent, follow_symlinks=False)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"output parent is unavailable: {exc}") from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise SpringLaunchEvidenceError("output parent must be a directory")
    if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o022:
        raise SpringLaunchEvidenceError(
            "output parent must be current-account-owned and not group/other writable"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor = -1
    descriptor = -1
    created_identity: tuple[int, int] | None = None
    try:
        parent_descriptor = _open_absolute_directory(parent, "output parent")
        opened_parent = os.fstat(parent_descriptor)
        if (
            opened_parent.st_dev != parent_stat.st_dev
            or opened_parent.st_ino != parent_stat.st_ino
            or opened_parent.st_uid != parent_stat.st_uid
            or opened_parent.st_mode != parent_stat.st_mode
        ):
            raise SpringLaunchEvidenceError("output parent changed while it was opened")
        descriptor = os.open(
            supplied.name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        output_stat = os.fstat(descriptor)
        created_identity = (output_stat.st_dev, output_stat.st_ino)
        if (
            not stat.S_ISREG(output_stat.st_mode)
            or output_stat.st_uid != os.getuid()
            or output_stat.st_nlink != 1
            or stat.S_IMODE(output_stat.st_mode) != 0o600
        ):
            raise SpringLaunchEvidenceError(
                "assembled output must be a new owner-only regular file"
            )
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise SpringLaunchEvidenceError(
                    "assembled output write made no forward progress"
                )
            offset += written
        os.fsync(descriptor)
        completed = os.fstat(descriptor)
        path_after = os.stat(
            supplied.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            (completed.st_dev, completed.st_ino) != created_identity
            or (path_after.st_dev, path_after.st_ino) != created_identity
            or completed.st_size != len(content)
            or path_after.st_size != len(content)
            or stat.S_IMODE(completed.st_mode) != 0o600
            or stat.S_IMODE(path_after.st_mode) != 0o600
        ):
            raise SpringLaunchEvidenceError(
                "assembled output identity or size changed while it was written"
            )
        os.fsync(parent_descriptor)
    except BaseException as exc:
        if parent_descriptor >= 0 and descriptor >= 0:
            try:
                if created_identity is None:
                    current = os.fstat(descriptor)
                    created_identity = (current.st_dev, current.st_ino)
                entry = os.stat(
                    supplied.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (entry.st_dev, entry.st_ino) == created_identity:
                    os.unlink(supplied.name, dir_fd=parent_descriptor)
                    os.fsync(parent_descriptor)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise SpringLaunchEvidenceError(
                f"output must be a new file in an existing safe directory: {exc}"
            ) from exc
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _verification_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "trust_store": args.trust_store,
        "evidence_roots": args.evidence_root,
        "expected_revision": args.expected_revision,
        "expected_profile_path": args.expected_profile,
        "expected_trust_store_digest": args.expected_trust_store_digest,
        "expected_environment_id": args.expected_environment_id,
        "expected_deployment_id": args.expected_deployment_id,
        "expected_provider": args.expected_provider,
        "expected_region": args.expected_region,
        "expected_environment_class": args.expected_environment_class,
        "expected_configuration_digest": args.expected_configuration_digest,
        "max_age": timedelta(seconds=args.max_age_seconds),
    }


def _add_verification_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trust-store", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, action="append", type=Path)
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-profile", type=Path, default=PROFILE)
    parser.add_argument("--expected-trust-store-digest", required=True)
    parser.add_argument("--expected-environment-id", required=True)
    parser.add_argument("--expected-deployment-id", required=True)
    parser.add_argument("--expected-provider", required=True)
    parser.add_argument("--expected-region", required=True)
    parser.add_argument(
        "--expected-environment-class",
        choices=("STAGING", "PRODUCTION"),
        required=True,
    )
    parser.add_argument("--expected-configuration-digest", required=True)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=int(DEFAULT_MAX_AGE.total_seconds()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    reference_parser = subparsers.add_parser(
        "reference", help="hash existing local evidence bytes"
    )
    reference_parser.add_argument("file", type=Path)
    reference_parser.add_argument("--evidence-root", required=True, action="append", type=Path)
    reference_parser.add_argument(
        "--media-type", default="application/octet-stream"
    )
    reference_parser.add_argument(
        "--gate-reference",
        action="store_true",
        help="include LOCAL_BYTES verification metadata for a gate evidence reference",
    )
    reference_parser.add_argument(
        "--advertised-uri",
        help="immutable external URI attested by the local byte snapshot",
    )

    digest_parser = subparsers.add_parser(
        "digest", help="calculate a receipt canonical digest without signing"
    )
    digest_parser.add_argument("receipt", type=Path)

    verify_parser = subparsers.add_parser(
        "verify", help="authenticate a complete signed receipt"
    )
    verify_parser.add_argument("receipt", type=Path)
    _add_verification_arguments(verify_parser)

    assemble_parser = subparsers.add_parser(
        "assemble",
        help="add the canonical digest to an already complete signed draft and verify it",
    )
    assemble_parser.add_argument("draft", type=Path)
    assemble_parser.add_argument("--output", required=True, type=Path)
    _add_verification_arguments(assemble_parser)

    args = parser.parse_args(argv)
    try:
        if args.command == "reference":
            reference = content_reference(
                args.file,
                evidence_roots=args.evidence_root,
                media_type=args.media_type,
            )
            if args.advertised_uri and not args.gate_reference:
                raise SpringLaunchEvidenceError(
                    "--advertised-uri requires --gate-reference"
                )
            if args.gate_reference:
                advertised_uri = args.advertised_uri or reference["uri"]
                _immutable_uri(advertised_uri, reference["digest"], "--advertised-uri")
                reference = {
                    **reference,
                    "uri": advertised_uri,
                    "verification": {
                        "mode": "LOCAL_BYTES",
                        "local_uri": reference["uri"],
                    },
                }
            print(json.dumps(reference, indent=2, sort_keys=True))
            return 0
        if args.command == "digest":
            value = _load_cli_json(args.receipt, "Spring launch receipt")
            print(receipt_digest(value))
            return 0
        if args.command == "verify":
            result = verify_spring_launch_receipt_file(
                args.receipt, **_verification_options(args)
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "assemble":
            draft = _load_cli_json(args.draft, "Spring launch receipt draft")
            assembled, result = assemble_spring_launch_receipt(
                draft, **_verification_options(args)
            )
            rendered = (json.dumps(assembled, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            _write_new_owner_only(args.output, rendered)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
    except (SpringLaunchEvidenceError, OSError, ValueError) as exc:
        print(f"SPRING LAUNCH EVIDENCE FAIL: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
