"""Fail-closed, tenant-scoped publication of bounded archive contents.

Archive parsing is deliberately split from publication.  Every input is first
spooled under hard limits and passively inspected.  The original archive and
each extracted file must then receive a byte-bound CLEAN receipt from the
injected malware provider before any object is copied into readable CAS.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import tarfile
import tempfile
import threading
import unicodedata
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Iterator, Literal, Protocol

from .canonical import (
    canonical_digest,
    canonical_json,
    normalize_sha256,
    require_resource_id,
    sha256_bytes,
)
from .errors import IntakeError, ValidationError
from .models import ResultStatus
from .projects import (
    ProjectContractError,
    _ZipEntryView,
    _archive_depth,
    _archive_limits,
    _archive_safety_report,
    _decode_base64_bounded,
    _inputs,
    _reject_input_archive_authority,
    _zip_declared_entry_count,
    detect_archive_container,
    normalize_relative_path,
)
from .providers import ExternalToolProvider, ProviderResult, ToolCapability
from .store import IntakeStore, LocalCasStore

try:  # POSIX hosts also receive an inter-process lock; other hosts retain process serialization.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on non-POSIX hosts
    fcntl = None  # type: ignore[assignment]


_CHUNK_BYTES = 1024 * 1024
_SPOOL_MEMORY_BYTES = 1024 * 1024
_SECRET_FIELDS = frozenset({"password", "passphrase", "archive_password", "decryption_key"})
_SCANNER_PAYLOAD_FIELDS = frozenset({"verdict", "findings"})
_SCANNER_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "tool",
        "executable",
        "executable_sha256",
        "input_sha256",
        "input_bytes",
        "media_type",
        "argv",
        "argv_sha256",
        "policy_sha256",
        "job_id",
        "stage",
        "exit_code",
        "stdout_sha256",
        "stdout_bytes",
        "stderr_summary",
        "duration_ms",
        "sandboxed",
        "network_allowed",
        "started_at",
        "completed_at",
        "received_at",
        "provider_auth_tag",
    }
)
_SCANNER_ARGV = ["--input", "-", "--output", "json"]
_ZIP_COMPRESSION_METHODS = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_ARCHIVE_PASSWORD_PURPOSE = "ARCHIVE_ZIP_DECRYPT"
_ARCHIVE_PASSWORD_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "tenant_id",
        "project_id",
        "job_id",
        "purpose",
        "handle_digest",
        "expires_at",
        "revoked",
    }
)
_MAX_ARCHIVE_PASSWORD_LEASE = timedelta(minutes=15)
_PROCESS_LOCK = threading.RLock()
_ARCHIVE_PARENT_FIELDS = frozenset(
    {
        "parent_archive_digest",
        "parent_entry_digest",
        "parent_entry_receipt_digest",
        "parent_generation_digest",
    }
)


class _ArchiveCumulativeLimitError(ProjectContractError):
    """A streamed or declared entry/byte counter reached its current ceiling."""


@dataclass(frozen=True, slots=True)
class ArchivePasswordLease:
    """Ephemeral secret plus a non-secret, exact-scope resolution receipt."""

    secret: bytes = field(repr=False)
    receipt: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt", MappingProxyType(dict(self.receipt)))


class ArchivePasswordProvider(Protocol):
    """Runtime-owned resolver for a short-lived non-secret password handle."""

    def resolve_archive_password(
        self,
        handle: str,
        *,
        tenant_id: str,
        project_id: str,
        job_id: str,
        purpose: str,
    ) -> ArchivePasswordLease: ...


class _BinaryReader(Protocol):
    """The byte-reader surface shared by archive-library entry streams."""

    def read(self, size: int = -1, /) -> bytes: ...


class _SeekableBinaryReader(_BinaryReader, Protocol):
    """A byte reader whose cursor can be rewound for bounded inspection."""

    def seek(self, offset: int, whence: int = 0, /) -> int: ...


@dataclass(slots=True)
class _StagedObject:
    path: str
    media_type: str
    digest: str
    size: int
    spool: _SeekableBinaryReader
    nested_container: str | None = None
    scanner_binding: Mapping[str, Any] | None = None


def _tag(digest: str) -> str:
    return "sha256:" + digest.removeprefix("sha256:")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json(value).encode("utf-8")


def _archive_parent(values: Mapping[str, Any]) -> dict[str, str] | None:
    raw = values.get("archive_parent")
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or set(raw) != _ARCHIVE_PARENT_FIELDS:
        raise ProjectContractError("archive parent lineage shape is invalid")
    try:
        return {name: normalize_sha256(raw[name]) for name in sorted(_ARCHIVE_PARENT_FIELDS)}
    except (KeyError, TypeError, ValidationError):
        raise ProjectContractError("archive parent lineage digest is invalid") from None


def _validate_archive_password_lease(
    lease: ArchivePasswordLease,
    *,
    handle: str,
    tenant_id: str,
    project_id: str,
    job_id: str,
) -> bytes:
    if not isinstance(lease, ArchivePasswordLease):
        raise ProjectContractError("archive password provider returned an invalid lease")
    if not isinstance(lease.secret, bytes) or not 1 <= len(lease.secret) <= 4096:
        raise ProjectContractError("archive password provider returned an invalid secret")
    receipt = lease.receipt
    if set(receipt) != _ARCHIVE_PASSWORD_RECEIPT_FIELDS:
        raise ProjectContractError("archive password lease receipt shape is invalid")
    expected_handle_digest = sha256_bytes(handle.encode("utf-8", errors="strict"))
    try:
        receipt_handle_digest = normalize_sha256(receipt.get("handle_digest"))
        expires_at_value = receipt.get("expires_at")
        if not isinstance(expires_at_value, str):
            raise ValueError("expires_at must be a string")
        expires_at = datetime.fromisoformat(expires_at_value)
    except (UnicodeEncodeError, ValueError, TypeError, ValidationError):
        raise ProjectContractError("archive password lease receipt is invalid") from None
    now = datetime.now(UTC)
    if (
        receipt.get("schema_version") != "1.0.0"
        or receipt.get("tenant_id") != tenant_id
        or receipt.get("project_id") != project_id
        or receipt.get("job_id") != job_id
        or receipt.get("purpose") != _ARCHIVE_PASSWORD_PURPOSE
        or receipt.get("handle_digest") != f"sha256:{receipt_handle_digest}"
        or receipt_handle_digest != expected_handle_digest
        or expires_at.tzinfo is None
        or expires_at <= now
        or expires_at > now + _MAX_ARCHIVE_PASSWORD_LEASE
        or receipt.get("revoked") is not False
    ):
        raise ProjectContractError("archive password lease scope is invalid")
    return lease.secret


def _read_bounded(stream: _SeekableBinaryReader, limit: int) -> bytes:
    stream.seek(0)
    data = stream.read(limit + 1)
    stream.seek(0)
    if not isinstance(data, bytes) or len(data) > limit:
        raise ProjectContractError("spooled object exceeded its bounded byte limit")
    return data


def _sniff_entry_media(stream: _SeekableBinaryReader) -> tuple[str, str | None]:
    """Return a byte-derived media type and nested-container classification."""

    stream.seek(0)
    prefix = stream.read(4096)
    stream.seek(0)
    container = detect_archive_container(prefix[:512])
    if container == "zip":
        return "application/zip", "zip"
    if container == "tar":
        return "application/x-tar", "tar"
    if container == "gzip":
        return "application/gzip", "gzip"
    if any(prefix.find(marker, 1) >= 0 for marker in (b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b\x08")):
        return "application/octet-stream", "ambiguous"
    if prefix.startswith(b"%PDF-"):
        return "application/pdf", None
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", None
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", None
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", None
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp", None
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WAVE":
        return "audio/wav", None
    if prefix.startswith(b"OggS"):
        return "application/ogg", None
    if prefix.startswith(b"fLaC"):
        return "audio/flac", None
    if prefix.startswith(b"ID3"):
        return "audio/mpeg", None
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp":
        return "video/mp4", None
    if prefix:
        try:
            text = prefix.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            pass
        else:
            if all(character in "\n\r\t" or ord(character) >= 32 for character in text):
                return "text/plain", None
    return "application/octet-stream", None


def _spool_entry(
    source: _BinaryReader,
    *,
    path: str,
    declared_size: int | None,
    entry_limit: int,
    total_limit: int,
    total: list[int],
    stack: ExitStack,
) -> _StagedObject:
    spool = stack.enter_context(
        tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY_BYTES, mode="w+b")
    )
    measured = hashlib.sha256()
    size = 0
    while True:
        chunk = source.read(_CHUNK_BYTES)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise ProjectContractError("archive reader returned a non-byte chunk")
        if len(chunk) > entry_limit - size or len(chunk) > total_limit - total[0]:
            raise _ArchiveCumulativeLimitError("archive actual resource limit exceeded")
        spool.write(chunk)
        measured.update(chunk)
        size += len(chunk)
        total[0] += len(chunk)
    if declared_size is not None and size != declared_size:
        raise ProjectContractError("archive entry size differs from declared metadata")
    spool.flush()
    spool.seek(0)
    media_type, nested_container = _sniff_entry_media(spool)
    return _StagedObject(
        path=path,
        media_type=media_type,
        digest=measured.hexdigest(),
        size=size,
        spool=spool,
        nested_container=nested_container,
    )


def _archive_media_type(archive_format: str) -> str:
    return {
        "zip": "application/zip",
        "tar": "application/x-tar",
        "tar.gz": "application/gzip",
        "tgz": "application/gzip",
        "gz": "application/gzip",
        "gzip": "application/gzip",
    }[archive_format]


def _scanner_binding(
    providers: ExternalToolProvider,
    result: ProviderResult,
    *,
    data: bytes,
    media_type: str,
    job_id: str,
    stage: str,
) -> tuple[Mapping[str, Any] | None, str]:
    """Return a stable, path-free binding only for a valid CLEAN provider result."""

    if result.capability is not ToolCapability.MALWARE_SCAN:
        return None, "MALWARE_SCAN_CAPABILITY_MISMATCH"
    if result.status is ResultStatus.NOT_RUN:
        return None, result.error_code or "MALWARE_SCAN_NOT_RUN"
    if result.status is not ResultStatus.PASSED or result.error_code is not None:
        return None, result.error_code or "MALWARE_SCAN_FAILED"
    verifier = getattr(providers, "verify_issued_result", None)
    try:
        authentic = callable(verifier) and verifier(result) is True
    except Exception:
        authentic = False
    if not authentic:
        return None, "MALWARE_SCAN_RECEIPT_UNAUTHENTIC"
    if set(result.payload) != _SCANNER_PAYLOAD_FIELDS:
        return None, "MALWARE_SCAN_PAYLOAD_INVALID"
    verdict = result.payload.get("verdict")
    findings = result.payload.get("findings")
    if verdict != "CLEAN" or findings != [] or result.warnings:
        return None, "MALWARE_SCAN_NOT_CLEAN"
    receipt = result.receipt
    stderr_summary = receipt.get("stderr_summary")
    stdout_bytes = receipt.get("stdout_bytes")
    duration_ms = receipt.get("duration_ms")
    if set(receipt) != _SCANNER_RECEIPT_FIELDS:
        return None, "MALWARE_SCAN_RECEIPT_INVALID"
    input_digest = sha256_bytes(data)
    try:
        receipt_input_digest = normalize_sha256(receipt.get("input_sha256"))
        executable_digest = normalize_sha256(receipt.get("executable_sha256"))
        argv_digest = normalize_sha256(receipt.get("argv_sha256"))
        policy_digest = normalize_sha256(receipt.get("policy_sha256"))
        stdout_digest = normalize_sha256(receipt.get("stdout_sha256"))
        if stderr_summary:
            normalize_sha256(stderr_summary)
        started_at = datetime.fromisoformat(str(receipt.get("started_at")))
        completed_at = datetime.fromisoformat(str(receipt.get("completed_at")))
        received_at = datetime.fromisoformat(str(receipt.get("received_at")))
    except Exception:
        return None, "MALWARE_SCAN_RECEIPT_INVALID"
    executable = receipt.get("executable")
    argv = receipt.get("argv")
    if (
        receipt.get("schema_version") != "1.0.0"
        or receipt.get("tool") != ToolCapability.MALWARE_SCAN.value
        # Public receipts expose only the fixed allowlisted basename.  The
        # exact private path is authenticated indirectly through policy_sha256
        # and ExternalToolProvider.verify_issued_result above.
        or executable != "elmos-malware-scan"
        or "/" in executable
        or "\\" in executable
        or receipt_input_digest != input_digest
        or isinstance(receipt.get("input_bytes"), bool)
        or not isinstance(receipt.get("input_bytes"), int)
        or receipt.get("input_bytes") != len(data)
        or receipt.get("media_type") != media_type
        or argv != _SCANNER_ARGV
        or argv_digest != canonical_digest(_SCANNER_ARGV)
        or receipt.get("job_id") != job_id
        or receipt.get("stage") != stage
        or isinstance(receipt.get("exit_code"), bool)
        or not isinstance(receipt.get("exit_code"), int)
        or receipt.get("exit_code") != 0
        or isinstance(stdout_bytes, bool)
        or not isinstance(stdout_bytes, int)
        or stdout_bytes < 0
        or not isinstance(stderr_summary, str)
        or (
            bool(stderr_summary)
            and not stderr_summary.startswith("sha256:")
        )
        or isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms < 0
        or receipt.get("sandboxed") is not True
        or receipt.get("network_allowed") is not False
        or started_at.tzinfo is None
        or completed_at.tzinfo is None
        or received_at.tzinfo is None
        or not started_at <= completed_at <= received_at
    ):
        return None, "MALWARE_SCAN_RECEIPT_INVALID"
    binding = {
        "schema_version": "1.0.0",
        "tool": ToolCapability.MALWARE_SCAN.value,
        "verdict": "CLEAN",
        "input_digest": _tag(input_digest),
        "input_bytes": len(data),
        "media_type": media_type,
        "job_id": job_id,
        "stage": stage,
        "executable_digest": _tag(executable_digest),
        "argv_digest": _tag(argv_digest),
        "policy_digest": _tag(policy_digest),
        "stdout_digest": _tag(stdout_digest),
        "stdout_bytes": int(receipt["stdout_bytes"]),
        "scanner_result_digest": _tag(
            canonical_digest({"verdict": verdict, "findings": findings})
        ),
        "sandboxed": True,
        "network_allowed": False,
    }
    return binding, "CLEAN"


def _scan(
    providers: ExternalToolProvider,
    staged: _StagedObject,
    *,
    job_id: str,
    stage: str,
    maximum_bytes: int,
) -> tuple[bool, str, str]:
    data = _read_bounded(staged.spool, maximum_bytes)
    result = providers.run(
        ToolCapability.MALWARE_SCAN,
        data,
        staged.media_type,
        job_id=job_id,
        stage=stage,
    )
    binding, reason = _scanner_binding(
        providers,
        result,
        data=data,
        media_type=staged.media_type,
        job_id=job_id,
        stage=stage,
    )
    if binding is None:
        status = "NOT_RUN" if result.status is ResultStatus.NOT_RUN else "NEEDS_REVIEW"
        return False, status, reason
    staged.scanner_binding = binding
    return True, "PASSED", "CLEAN"


def _portable_key(path: str) -> str:
    return unicodedata.normalize("NFKC", path).casefold()


def _preflight_tar(
    raw_stream: BinaryIO,
    *,
    archive_format: str,
    compressed_size: int,
    limits: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    descriptors: list[Mapping[str, Any]] = []
    exact: set[str] = set()
    portable: set[str] = set()
    kinds: dict[str, str] = {}
    portable_kinds: dict[str, str] = {}
    total = 0
    max_entries = int(limits["max_entries"])
    total_limit = min(
        int(limits["max_total_uncompressed_bytes"]),
        max(1, int(compressed_size * float(limits["max_compression_ratio"]))),
    )
    raw_stream.seek(0)
    mode: Literal["r|", "r|gz"] = "r|" if archive_format == "tar" else "r|gz"
    with tarfile.open(fileobj=raw_stream, mode=mode) as archive:
        for member in archive:
            if len(descriptors) >= max_entries:
                raise _ArchiveCumulativeLimitError("archive entry limit exceeded")
            path = normalize_relative_path(member.name.rstrip("/"))
            portable_path = _portable_key(path)
            if path in exact or portable_path in portable:
                raise ProjectContractError("archive contains a duplicate or portable path collision")
            exact.add(path)
            portable.add(portable_path)
            if _archive_depth(path) > int(limits["max_nested_depth"]):
                raise ProjectContractError("archive nested depth limit exceeded")
            if not (member.isdir() or member.isfile()):
                raise ProjectContractError("archive contains a link or special entry")
            kinds[path] = "directory" if member.isdir() else "file"
            portable_kinds[portable_path] = kinds[path]
            if isinstance(member.size, bool) or not isinstance(member.size, int) or member.size < 0:
                raise ProjectContractError("tar member has an invalid declared size")
            if member.isfile():
                if member.size > int(limits["max_entry_uncompressed_bytes"]):
                    raise ProjectContractError("archive declared entry resource limit exceeded")
                if member.size > total_limit - total:
                    raise _ArchiveCumulativeLimitError(
                        "archive declared cumulative resource limit exceeded"
                    )
                total += member.size
            descriptors.append(
                {
                    "path": path,
                    "size": member.size,
                    "kind": "directory" if member.isdir() else "file",
                }
            )
    raw_stream.seek(0)
    if not descriptors:
        raise ProjectContractError("archive is empty")
    for path in sorted(kinds):
        components = path.split("/")
        for boundary in range(1, len(components)):
            ancestor = "/".join(components[:boundary])
            if ancestor in kinds and kinds[ancestor] != "directory":
                raise ProjectContractError("archive contains a file-directory ancestor conflict")
            portable_ancestor = _portable_key(ancestor)
            if portable_ancestor in portable_kinds and portable_kinds[portable_ancestor] != "directory":
                raise ProjectContractError("archive contains a portable file-directory ancestor conflict")
    return descriptors


def _preflight_zip(
    raw_stream: BinaryIO,
    *,
    compressed_size: int,
    limits: Mapping[str, Any],
) -> tuple[list[zipfile.ZipInfo], bool]:
    declared_count = _zip_declared_entry_count(raw_stream, archive_size=compressed_size)
    if declared_count > int(limits["max_entries"]):
        raise _ArchiveCumulativeLimitError("archive entry limit exceeded")
    with zipfile.ZipFile(raw_stream, "r") as archive:
        infos = list(archive.infolist())
        if len(infos) != declared_count:
            raise ProjectContractError("zip entry count differs from bounded preflight metadata")
        if any(info.compress_type not in _ZIP_COMPRESSION_METHODS for info in infos):
            raise ProjectContractError("zip compression method is outside the allowlist")
        encrypted = any(info.flag_bits & 0x1 for info in infos)
        report = _archive_safety_report(_ZipEntryView(infos), limits)
        if report["decision"] != "ALLOW":
            finding_codes = {
                str(item.get("code"))
                for item in report.get("findings", [])
                if isinstance(item, Mapping)
            }
            if finding_codes.intersection(
                {"ARCHIVE_ENTRY_LIMIT_EXCEEDED", "ARCHIVE_TOTAL_SIZE_LIMIT"}
            ):
                raise _ArchiveCumulativeLimitError(
                    "archive metadata exceeded its cumulative resource limit"
                )
            raise ProjectContractError("archive metadata failed passive safety preflight")
    raw_stream.seek(0)
    return infos, encrypted


def _preflight_gzip(values: Mapping[str, Any], limits: Mapping[str, Any]) -> str:
    del limits
    return normalize_relative_path(values.get("output_name", "payload"))


def _gzip_inner_container(raw_stream: BinaryIO) -> str:
    """Classify the first decompressed header after original bytes are cleared."""

    raw_stream.seek(0)
    with gzip.GzipFile(fileobj=raw_stream, mode="rb") as source:
        prefix = source.read(512)
    raw_stream.seek(0)
    return detect_archive_container(prefix)


def _extract_entries(
    raw_stream: BinaryIO,
    *,
    archive_format: str,
    preflight: Sequence[Any] | str,
    compressed_size: int,
    limits: Mapping[str, Any],
    stack: ExitStack,
    password: bytes | None,
) -> list[_StagedObject]:
    entry_limit = int(limits["max_entry_uncompressed_bytes"])
    total_limit = min(
        int(limits["max_total_uncompressed_bytes"]),
        max(1, int(compressed_size * float(limits["max_compression_ratio"]))),
    )
    total = [0]
    staged: list[_StagedObject] = []
    raw_stream.seek(0)
    if archive_format == "zip":
        with zipfile.ZipFile(raw_stream, "r") as archive:
            for info in preflight:
                if not isinstance(info, zipfile.ZipInfo) or info.is_dir():
                    continue
                path = normalize_relative_path(info.filename)
                with archive.open(info, "r", pwd=password) as zip_source:
                    staged.append(
                        _spool_entry(
                            zip_source,
                            path=path,
                            declared_size=info.file_size,
                            entry_limit=entry_limit,
                            total_limit=total_limit,
                            total=total,
                            stack=stack,
                        )
                    )
    elif archive_format in {"tar", "tar.gz", "tgz"}:
        mode: Literal["r|", "r|gz"] = "r|" if archive_format == "tar" else "r|gz"
        with tarfile.open(fileobj=raw_stream, mode=mode) as archive:
            for member in archive:
                if member.isdir():
                    continue
                path = normalize_relative_path(member.name)
                tar_source = archive.extractfile(member)
                if tar_source is None:
                    raise ProjectContractError("tar member could not be opened safely")
                with tar_source:
                    staged.append(
                        _spool_entry(
                            tar_source,
                            path=path,
                            declared_size=member.size,
                            entry_limit=entry_limit,
                            total_limit=total_limit,
                            total=total,
                            stack=stack,
                        )
                    )
    else:
        if not isinstance(preflight, str):
            raise ProjectContractError("gzip output path is unavailable")
        with gzip.GzipFile(fileobj=raw_stream, mode="rb") as gzip_source:
            staged.append(
                _spool_entry(
                    gzip_source,
                    path=preflight,
                    declared_size=None,
                    entry_limit=entry_limit,
                    total_limit=total_limit,
                    total=total,
                    stack=stack,
                )
            )
    if not staged:
        raise ProjectContractError("archive contains no file assets")
    staged.sort(key=lambda item: item.path)
    return staged


@contextmanager
def _publication_lock(cas: LocalCasStore) -> Iterator[None]:
    """Serialize archive set publication for this local CAS process and root."""

    lock_path = Path(cas.root) / ".archive-publication.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        with _PROCESS_LOCK:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _iter_chunks(stream: _SeekableBinaryReader) -> Iterator[bytes]:
    """Yield a staged object without relying on an untyped sentinel lambda."""

    while True:
        chunk = stream.read(_CHUNK_BYTES)
        if not chunk:
            return
        yield chunk


def _publish(
    *,
    cas: LocalCasStore,
    tenant_id: str,
    raw_archive: _StagedObject,
    entries: Sequence[_StagedObject],
    generated: Sequence[tuple[str, bytes]],
    generation_digest: str,
) -> int:
    with _publication_lock(cas):
        objects: list[tuple[str, int, Iterable[bytes]]] = []
        seen: set[str] = set()
        for staged in (raw_archive, *entries):
            if staged.digest in seen:
                continue
            seen.add(staged.digest)
            staged.spool.seek(0)
            objects.append(
                (
                    staged.digest,
                    staged.size,
                    _iter_chunks(staged.spool),
                )
            )
        for digest, data in generated:
            if digest in seen:
                continue
            seen.add(digest)
            objects.append((digest, len(data), (data,)))
        cas.publish_generation(tenant_id, generation_digest, objects)
        return len(objects)


def publish_archive_to_cas(
    request: Mapping[str, Any],
    *,
    providers: ExternalToolProvider,
    cas: LocalCasStore,
    tenant_id: str,
    project_id: str,
    job_id: str,
    password_provider: ArchivePasswordProvider | None = None,
    store: IntakeStore | None = None,
) -> dict[str, Any]:
    """Safely publish one archive and its entries into tenant-scoped CAS.

    The caller supplies trusted tenant/project/job identity and runtime-owned
    provider/CAS capabilities.  Nothing in ``inputs`` can select a scanner,
    executable, host path, CAS root, or policy limit.
    """

    safe_tenant = require_resource_id(tenant_id, "tenant_id")
    safe_project = require_resource_id(project_id, "project_id")
    safe_job = require_resource_id(job_id, "job_id")
    values = _inputs(request)
    _reject_input_archive_authority(values)
    try:
        parent = _archive_parent(values)
    except ProjectContractError:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_PARENT_LINEAGE_INVALID",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    if parent is not None and store is None:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_LINEAGE_STORE_REQUIRED",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    if _SECRET_FIELDS.intersection(values):
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_PASSWORD_SECRET_CHANNEL_REQUIRED",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    encoded = values.get("archive_bytes_b64")
    if not isinstance(encoded, str):
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_CONTENT_REQUIRED",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    archive_format = str(values.get("format", "zip")).lower()
    if archive_format not in {"zip", "tar", "tar.gz", "tgz", "gz", "gzip"}:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_FORMAT_UNSUPPORTED",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    password_handle = values.get("password_handle")
    if password_handle is not None:
        try:
            password_handle = require_resource_id(password_handle, "password_handle")
        except Exception:
            return {
                "state": "BLOCKED",
                "code": "ARCHIVE_PASSWORD_HANDLE_INVALID",
                "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
            }
        if archive_format != "zip":
            return {
                "state": "BLOCKED",
                "code": "ARCHIVE_PASSWORD_FORMAT_UNSUPPORTED",
                "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
            }
    limits = _archive_limits(request)
    try:
        raw_stream, compressed_size = _decode_base64_bounded(
            encoded,
            decoded_limit=int(limits["max_archive_bytes"]),
        )
    except ProjectContractError:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_INPUT_SIZE_LIMIT",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }

    try:
        with ExitStack() as stack:
            stack.callback(raw_stream.close)
            prefix = raw_stream.read(min(compressed_size, 512))
            raw_stream.seek(0)
            detected_outer = detect_archive_container(prefix)
            expected_outer = (
                "gzip" if archive_format in {"tar.gz", "tgz", "gz", "gzip"} else archive_format
            )
            if detected_outer == "unknown" or detected_outer != expected_outer:
                return {
                    "state": "BLOCKED",
                    "code": "ARCHIVE_FORMAT_SIGNATURE_MISMATCH",
                    "outputs": {
                        "publication_state": "NOT_RUN",
                        "declared_format": archive_format,
                        "detected_container": detected_outer,
                        "parser_execution": "NOT_RUN",
                        "readable_cas_objects": [],
                    },
                }
            archive_data = _read_bounded(raw_stream, int(limits["max_archive_bytes"]))
            raw_archive = _StagedObject(
                path="archive",
                media_type=_archive_media_type(archive_format),
                digest=sha256_bytes(archive_data),
                size=len(archive_data),
                spool=raw_stream,
            )
            policy_limits = dict(limits)
            policy_digest = canonical_digest(policy_limits)
            lineage_context: dict[str, Any] | None = None
            if parent is not None:
                assert store is not None
                try:
                    lineage_context = store.get_archive_expansion_context(
                        tenant_id=safe_tenant,
                        project_id=safe_project,
                        parent_archive_digest=parent["parent_archive_digest"],
                        parent_entry_digest=parent["parent_entry_digest"],
                        parent_entry_receipt_digest=parent["parent_entry_receipt_digest"],
                        parent_generation_digest=parent["parent_generation_digest"],
                    )
                except IntakeError as error:
                    return {
                        "state": "BLOCKED",
                        "code": error.code,
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                except Exception:
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_EXPANSION_STORE_INVALID",
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                if (
                    raw_archive.digest != parent["parent_entry_digest"]
                    or lineage_context["policy_digest"] != policy_digest
                ):
                    return {
                        "state": "BLOCKED",
                        "code": (
                            "ARCHIVE_PARENT_LINEAGE_INVALID"
                            if raw_archive.digest != parent["parent_entry_digest"]
                            else "ARCHIVE_ROOT_POLICY_MISMATCH"
                        ),
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                if int(lineage_context["depth"]) > int(lineage_context["max_nested_depth"]):
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_NESTED_DEPTH_LIMIT",
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                remaining_bytes = int(lineage_context["max_total_uncompressed_bytes"]) - int(
                    lineage_context["consumed_uncompressed_bytes"]
                )
                remaining_entries = int(lineage_context["max_entries"]) - int(
                    lineage_context["consumed_entries"]
                )
                replay_candidate = lineage_context["existing_child_node_digest"] is not None
                if not replay_candidate and (remaining_bytes < 1 or remaining_entries < 1):
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_GLOBAL_BUDGET_EXCEEDED",
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                if not replay_candidate:
                    limits = {
                        **policy_limits,
                        "max_total_uncompressed_bytes": min(
                            int(policy_limits["max_total_uncompressed_bytes"]), remaining_bytes
                        ),
                        "max_entries": min(
                            int(policy_limits["max_entries"]), remaining_entries
                        ),
                    }
            clean, scanner_status, reason = _scan(
                providers,
                raw_archive,
                job_id=safe_job,
                stage="archive-original",
                maximum_bytes=int(limits["max_archive_bytes"]),
            )
            if not clean:
                return {
                    "state": "PARTIAL",
                    "code": "ARCHIVE_MALWARE_CLEARANCE_REQUIRED",
                    "outputs": {
                        "publication_state": "NEEDS_REVIEW",
                        "scanner_status": scanner_status,
                        "scanner_code": reason,
                        "readable_cas_objects": [],
                    },
                }

            inner_container: str | None = None
            if archive_format in {"tar.gz", "tgz", "gz", "gzip"}:
                inner_container = _gzip_inner_container(raw_stream)
                if archive_format in {"tar.gz", "tgz"} and inner_container != "tar":
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_FORMAT_SIGNATURE_MISMATCH",
                        "outputs": {
                            "publication_state": "NOT_RUN",
                            "declared_format": archive_format,
                            "detected_container": detected_outer,
                            "detected_inner_container": inner_container,
                            "readable_cas_objects": [],
                        },
                    }
                if archive_format in {"gz", "gzip"} and inner_container == "tar":
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_FORMAT_SIGNATURE_MISMATCH",
                        "outputs": {
                            "publication_state": "NOT_RUN",
                            "declared_format": archive_format,
                            "detected_container": detected_outer,
                            "detected_inner_container": inner_container,
                            "readable_cas_objects": [],
                        },
                    }

            password: bytes | None = None
            if archive_format == "zip":
                zip_preflight, zip_encrypted = _preflight_zip(
                    raw_stream,
                    compressed_size=compressed_size,
                    limits=limits,
                )
                preflight: Sequence[Any] | str = zip_preflight
                if zip_encrypted:
                    if password_handle is None or password_provider is None:
                        return {
                            "state": "BLOCKED",
                            "code": "ARCHIVE_PASSWORD_SECRET_CHANNEL_REQUIRED",
                            "outputs": {
                                "publication_state": "NOT_RUN",
                                "readable_cas_objects": [],
                            },
                        }
                    try:
                        lease = password_provider.resolve_archive_password(
                            password_handle,
                            tenant_id=safe_tenant,
                            project_id=safe_project,
                            job_id=safe_job,
                            purpose=_ARCHIVE_PASSWORD_PURPOSE,
                        )
                    except Exception:
                        return {
                            "state": "BLOCKED",
                            "code": "ARCHIVE_PASSWORD_SECRET_RESOLUTION_FAILED",
                            "outputs": {
                                "publication_state": "NOT_RUN",
                                "readable_cas_objects": [],
                            },
                        }
                    try:
                        password = _validate_archive_password_lease(
                            lease,
                            handle=password_handle,
                            tenant_id=safe_tenant,
                            project_id=safe_project,
                            job_id=safe_job,
                        )
                    except ProjectContractError:
                        return {
                            "state": "BLOCKED",
                            "code": "ARCHIVE_PASSWORD_LEASE_INVALID",
                            "outputs": {
                                "publication_state": "NOT_RUN",
                                "readable_cas_objects": [],
                            },
                        }
            elif archive_format in {"tar", "tar.gz", "tgz"}:
                preflight = _preflight_tar(
                    raw_stream,
                    archive_format=archive_format,
                    compressed_size=compressed_size,
                    limits=limits,
                )
            else:
                preflight = _preflight_gzip(values, limits)

            entries = _extract_entries(
                raw_stream,
                archive_format=archive_format,
                preflight=preflight,
                compressed_size=compressed_size,
                limits=limits,
                stack=stack,
                password=password,
            )
            password = None
            current_archive_depth = (
                0 if lineage_context is None else int(lineage_context["depth"])
            )
            for entry in entries:
                if entry.nested_container == "ambiguous":
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_NESTED_CONTAINER_AMBIGUOUS",
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                if (
                    entry.nested_container is not None
                    and current_archive_depth + 1
                    > int(policy_limits["max_nested_depth"])
                ):
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_NESTED_DEPTH_LIMIT",
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
            for index, entry in enumerate(entries, start=1):
                clean, scanner_status, reason = _scan(
                    providers,
                    entry,
                    job_id=safe_job,
                    stage=f"archive-entry-{index:05d}",
                    maximum_bytes=int(limits["max_entry_uncompressed_bytes"]),
                )
                if not clean:
                    return {
                        "state": "PARTIAL",
                        "code": "ARCHIVE_ENTRY_MALWARE_CLEARANCE_REQUIRED",
                        "outputs": {
                            "publication_state": "NEEDS_REVIEW",
                            "scanner_status": scanner_status,
                            "scanner_code": reason,
                            "failed_entry": entry.path,
                            "readable_cas_objects": [],
                        },
                    }

            expanded_uncompressed_bytes = sum(entry.size for entry in entries)
            expanded_entry_count = len(preflight) if not isinstance(preflight, str) else 1
            expansion_request_digest = canonical_digest(
                {
                    "schema_version": "archive-expansion-request-v1",
                    "tenant_id": safe_tenant,
                    "project_id": safe_project,
                    "archive_digest": _tag(raw_archive.digest),
                    "archive_format": archive_format,
                    "parent": None
                    if parent is None
                    else {key: _tag(value) for key, value in sorted(parent.items())},
                    "policy_digest": _tag(policy_digest),
                    "entries": [
                        {
                            "path_digest": _tag(sha256_bytes(entry.path.encode("utf-8"))),
                            "content_digest": _tag(entry.digest),
                            "byte_count": entry.size,
                            "nested_container": entry.nested_container,
                        }
                        for entry in entries
                    ],
                    "expanded_entry_count": expanded_entry_count,
                    "expanded_uncompressed_bytes": expanded_uncompressed_bytes,
                }
            )
            if store is not None:
                reserve_parent = None
                if parent is not None:
                    assert lineage_context is not None
                    reserve_parent = {
                        "parent_node_digest": str(lineage_context["parent_node_digest"]),
                        **parent,
                    }
                try:
                    expansion = store.reserve_archive_expansion(
                        tenant_id=safe_tenant,
                        project_id=safe_project,
                        archive_digest=raw_archive.digest,
                        policy_digest=policy_digest,
                        max_total_uncompressed_bytes=int(
                            policy_limits["max_total_uncompressed_bytes"]
                        ),
                        max_entries=int(policy_limits["max_entries"]),
                        max_nested_depth=int(policy_limits["max_nested_depth"]),
                        expanded_uncompressed_bytes=expanded_uncompressed_bytes,
                        expanded_entries=expanded_entry_count,
                        request_digest=expansion_request_digest,
                        parent=reserve_parent,
                    )
                except IntakeError as error:
                    return {
                        "state": "BLOCKED",
                        "code": error.code,
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
                except Exception:
                    return {
                        "state": "BLOCKED",
                        "code": "ARCHIVE_EXPANSION_STORE_INVALID",
                        "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                    }
            else:
                root_archive_digest = raw_archive.digest
                expansion_depth = 0
                expansion_node_digest = canonical_digest(
                    {
                        "schema_version": "archive-expansion-node-v1",
                        "tenant_id": safe_tenant,
                        "project_id": safe_project,
                        "root_archive_digest": _tag(root_archive_digest),
                        "parent_node_digest": None,
                        "parent_entry_receipt_digest": None,
                        "archive_digest": _tag(raw_archive.digest),
                        "depth": expansion_depth,
                    }
                )
                expansion = {
                    "node_digest": expansion_node_digest,
                    "root_archive_digest": root_archive_digest,
                    "depth": expansion_depth,
                    "state": "RESERVED",
                    "generation_digest": None,
                    "result_digest": None,
                    "consumed_uncompressed_bytes": expanded_uncompressed_bytes,
                    "consumed_entries": expanded_entry_count,
                    "budget_version": 1,
                    "replay": False,
                }

            scope_digest = _tag(
                canonical_digest({"tenant_id": safe_tenant, "project_id": safe_project})
            )
            lineage_binding = {
                "schema_version": "archive-expansion-lineage-v1",
                "root_archive_digest": _tag(str(expansion["root_archive_digest"])),
                "node_digest": _tag(str(expansion["node_digest"])),
                "parent_node_digest": (
                    None
                    if lineage_context is None
                    else _tag(str(lineage_context["parent_node_digest"]))
                ),
                "depth": int(expansion["depth"]),
                "request_digest": _tag(expansion_request_digest),
            }
            raw_binding = raw_archive.scanner_binding
            if raw_binding is None:
                raise ProjectContractError("archive scanner binding disappeared before publication")
            archive_receipt = {
                "schema_version": "1.0.0",
                "kind": "ARCHIVE_OBJECT_RECEIPT",
                "scope_digest": scope_digest,
                "content_digest": _tag(raw_archive.digest),
                "byte_count": raw_archive.size,
                "media_type": raw_archive.media_type,
                "lineage": lineage_binding,
                "scanner": raw_binding,
            }
            archive_receipt_bytes = _canonical_bytes(archive_receipt)
            archive_receipt_digest = sha256_bytes(archive_receipt_bytes)

            entry_receipt_blobs: list[tuple[str, bytes]] = []
            manifest_entries: list[dict[str, Any]] = []
            for entry in entries:
                if entry.scanner_binding is None:
                    raise ProjectContractError("entry scanner binding disappeared before publication")
                receipt = {
                    "schema_version": "1.0.0",
                    "kind": "ARCHIVE_ENTRY_RECEIPT",
                    "scope_digest": scope_digest,
                    "archive_digest": _tag(raw_archive.digest),
                    "path": entry.path,
                    "content_digest": _tag(entry.digest),
                    "byte_count": entry.size,
                    "media_type": entry.media_type,
                    "nested_archive": entry.nested_container is not None,
                    "nested_container": entry.nested_container,
                    "nested_archive_state": (
                        "PRESERVED_NOT_EXPANDED"
                        if entry.nested_container is not None
                        else "NOT_APPLICABLE"
                    ),
                    "nested_depth_observed": 1 if entry.nested_container is not None else 0,
                    "contained_nested_depth_state": (
                        "NOT_INSPECTED_OPAQUE_CONTAINER"
                        if entry.nested_container is not None
                        else "NOT_APPLICABLE"
                    ),
                    "lineage": lineage_binding,
                    "scanner": entry.scanner_binding,
                }
                receipt_bytes = _canonical_bytes(receipt)
                receipt_digest = sha256_bytes(receipt_bytes)
                entry_receipt_blobs.append((receipt_digest, receipt_bytes))
                manifest_entries.append(
                    {
                        "path": entry.path,
                        "content_digest": _tag(entry.digest),
                        "byte_count": entry.size,
                        "media_type": entry.media_type,
                        "nested_archive": entry.nested_container is not None,
                        "nested_container": entry.nested_container,
                        "nested_archive_state": (
                            "PRESERVED_NOT_EXPANDED"
                            if entry.nested_container is not None
                            else "NOT_APPLICABLE"
                        ),
                        "nested_depth_observed": 1 if entry.nested_container is not None else 0,
                        "contained_nested_depth_state": (
                            "NOT_INSPECTED_OPAQUE_CONTAINER"
                            if entry.nested_container is not None
                            else "NOT_APPLICABLE"
                        ),
                        "entry_receipt_digest": _tag(receipt_digest),
                    }
                )

            entry_set_digest = _tag(canonical_digest(manifest_entries))
            manifest = {
                "schema_version": "1.0.0",
                "kind": "SAFE_ARCHIVE_PUBLICATION_MANIFEST",
                "scope_digest": scope_digest,
                "policy_version": str(limits["version"]),
                "policy_digest": _tag(policy_digest),
                "lineage": lineage_binding,
                "archive": {
                    "content_digest": _tag(raw_archive.digest),
                    "byte_count": raw_archive.size,
                    "format": archive_format,
                    "detected_outer_container": detected_outer,
                    "detected_inner_container": inner_container,
                    "media_type": raw_archive.media_type,
                    "archive_receipt_digest": _tag(archive_receipt_digest),
                },
                "entries": manifest_entries,
                "entry_set_digest": entry_set_digest,
                "total_uncompressed_bytes": expanded_uncompressed_bytes,
            }
            manifest_bytes = _canonical_bytes(manifest)
            manifest_digest = sha256_bytes(manifest_bytes)
            publication_receipt = {
                "schema_version": "1.0.0",
                "kind": "ARCHIVE_PUBLICATION_RECEIPT",
                "scope_digest": scope_digest,
                "manifest_digest": _tag(manifest_digest),
                "archive_digest": _tag(raw_archive.digest),
                "archive_receipt_digest": _tag(archive_receipt_digest),
                "entry_set_digest": entry_set_digest,
                "entry_receipt_digests": [item["entry_receipt_digest"] for item in manifest_entries],
                "lineage": lineage_binding,
                "publication_semantics": "ALL_SCANNED_CLEAN_THEN_ATOMIC_GENERATION_RENAME",
            }
            publication_receipt_bytes = _canonical_bytes(publication_receipt)
            publication_receipt_digest = sha256_bytes(publication_receipt_bytes)
            generated_without_generation = [
                (archive_receipt_digest, archive_receipt_bytes),
                *entry_receipt_blobs,
                (manifest_digest, manifest_bytes),
                (publication_receipt_digest, publication_receipt_bytes),
            ]
            generation_objects: dict[str, int] = {
                raw_archive.digest: raw_archive.size,
                **{entry.digest: entry.size for entry in entries},
                **{digest: len(data) for digest, data in generated_without_generation},
            }
            generation_binding = {
                "schema_version": "1.0.0",
                "kind": "ATOMIC_CAS_GENERATION_MANIFEST",
                "scope_digest": scope_digest,
                "manifest_digest": _tag(manifest_digest),
                "publication_receipt_digest": _tag(publication_receipt_digest),
                "objects": [
                    {"digest": _tag(digest), "byte_count": generation_objects[digest]}
                    for digest in sorted(generation_objects)
                ],
            }
            generation_bytes = _canonical_bytes(generation_binding)
            generation_digest = sha256_bytes(generation_bytes)
            if generation_digest in generation_objects:
                raise ProjectContractError("generation manifest digest collides with a bound object")
            generated = [
                *generated_without_generation,
                (generation_digest, generation_bytes),
            ]
            if expansion["state"] == "PUBLISHED" and (
                str(expansion["generation_digest"]) != generation_digest
                or str(expansion["result_digest"]) != publication_receipt_digest
            ):
                return {
                    "state": "BLOCKED",
                    "code": "ARCHIVE_EXPANSION_REPLAY_MISMATCH",
                    "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
                }
            try:
                if expansion["state"] == "PUBLISHED":
                    published_object_count = len(generation_objects) + 1
                else:
                    published_object_count = _publish(
                        cas=cas,
                        tenant_id=safe_tenant,
                        raw_archive=raw_archive,
                        entries=entries,
                        generated=generated,
                        generation_digest=generation_digest,
                    )
            except Exception as exc:
                rollback_incomplete = getattr(exc, "code", "") == "CAS_GENERATION_ROLLBACK_INCOMPLETE"
                return {
                    "state": "FAILED",
                    "code": (
                        "ARCHIVE_CAS_ROLLBACK_INCOMPLETE"
                        if rollback_incomplete
                        else "ARCHIVE_CAS_PUBLICATION_FAILED"
                    ),
                    "retryable": True,
                    "outputs": {
                        "publication_state": (
                            "ROLLBACK_INCOMPLETE" if rollback_incomplete else "FAILED"
                        ),
                        "generation_digest": _tag(generation_digest),
                        "readable_generation_state": "UNKNOWN",
                    },
                }

            if store is not None:
                try:
                    expansion = {
                        **expansion,
                        **store.complete_archive_expansion(
                            tenant_id=safe_tenant,
                            project_id=safe_project,
                            node_digest=str(expansion["node_digest"]),
                            generation_digest=generation_digest,
                            result_digest=publication_receipt_digest,
                            entries=[
                                {
                                    "entry_receipt_digest": item["entry_receipt_digest"],
                                    "entry_digest": item["content_digest"],
                                    "path_digest": _tag(
                                        sha256_bytes(item["path"].encode("utf-8"))
                                    ),
                                    "byte_count": item["byte_count"],
                                    "nested_container": item["nested_container"],
                                }
                                for item in manifest_entries
                            ],
                        ),
                    }
                except IntakeError as error:
                    return {
                        "state": "FAILED",
                        "code": error.code,
                        "retryable": True,
                        "outputs": {
                            "publication_state": "LINEAGE_COMMIT_UNKNOWN",
                            "generation_digest": _tag(generation_digest),
                            "readable_generation_state": "UNKNOWN",
                        },
                    }
                except Exception:
                    return {
                        "state": "FAILED",
                        "code": "ARCHIVE_EXPANSION_STORE_INVALID",
                        "retryable": True,
                        "outputs": {
                            "publication_state": "LINEAGE_COMMIT_UNKNOWN",
                            "generation_digest": _tag(generation_digest),
                            "readable_generation_state": "UNKNOWN",
                        },
                    }

            return {
                "state": "SUCCEEDED",
                "code": "ARCHIVE_PUBLISHED_TO_TENANT_CAS",
                "outputs": {
                    "publication_state": "PUBLISHED",
                    "scope_digest": scope_digest,
                    "archive_root_digest": _tag(str(expansion["root_archive_digest"])),
                    "archive_node_digest": _tag(str(expansion["node_digest"])),
                    "archive_parent_node_digest": lineage_binding["parent_node_digest"],
                    "archive_depth": int(expansion["depth"]),
                    "archive_budget": {
                        "schema_version": "archive-global-budget-v1",
                        "policy_digest": _tag(policy_digest),
                        "consumed_uncompressed_bytes": int(
                            expansion["consumed_uncompressed_bytes"]
                        ),
                        "max_total_uncompressed_bytes": int(
                            policy_limits["max_total_uncompressed_bytes"]
                        ),
                        "consumed_entries": int(expansion["consumed_entries"]),
                        "max_entries": int(policy_limits["max_entries"]),
                        "max_nested_depth": int(policy_limits["max_nested_depth"]),
                        "version": int(expansion["budget_version"]),
                        "persistence": "DURABLE" if store is not None else "NOT_RUN",
                    },
                    "archive_digest": _tag(raw_archive.digest),
                    "archive_receipt_digest": _tag(archive_receipt_digest),
                    "manifest_digest": _tag(manifest_digest),
                    "generation_digest": _tag(generation_digest),
                    "generation_manifest_digest": _tag(generation_digest),
                    "publication_receipt_digest": _tag(publication_receipt_digest),
                    "entry_set_digest": entry_set_digest,
                    "entries": manifest_entries,
                    "total_uncompressed_bytes": manifest["total_uncompressed_bytes"],
                    "published_object_count": published_object_count,
                    "publication_semantics": "ATOMIC_TENANT_GENERATION",
                    "host_paths_returned": False,
                    "raw_content_returned": False,
                },
                "metrics": {
                    "entry_count": len(entries),
                    "archive_bytes": raw_archive.size,
                    "uncompressed_bytes": manifest["total_uncompressed_bytes"],
                },
            }
    except _ArchiveCumulativeLimitError:
        return {
            "state": "BLOCKED",
            "code": (
                "ARCHIVE_GLOBAL_BUDGET_EXCEEDED"
                if parent is not None
                else "ARCHIVE_EXTRACTION_BLOCKED"
            ),
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    except PermissionError:
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_PASSWORD_SECRET_CHANNEL_REQUIRED",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
    except (
        zipfile.BadZipFile,
        tarfile.TarError,
        gzip.BadGzipFile,
        EOFError,
        OSError,
        NotImplementedError,
        RuntimeError,
        ProjectContractError,
    ):
        return {
            "state": "BLOCKED",
            "code": "ARCHIVE_EXTRACTION_BLOCKED",
            "outputs": {"publication_state": "NOT_RUN", "readable_cas_objects": []},
        }
