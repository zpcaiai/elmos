"""Content-addressed artifacts and host-bound evidence validation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractError,
    ExecutionAuthority,
    RuntimeRequest,
    canonical_json,
    digest_json,
    require_digest,
    require_identifier,
)
from .models import EvidenceState


_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}/[a-z0-9][a-z0-9.+-]{0,127}$")
_EVIDENCE_KEYS = frozenset(
    {
        "schema_version",
        "evidence_id",
        "evidence_type",
        "producer_id",
        "verifier_id",
        "tenant_id",
        "project_id",
        "revision_digest",
        "environment_authority_id",
        "subject_digest",
        "artifact_digest",
        "status",
        "independent",
        "executed_at_epoch_seconds",
        "expires_at_epoch_seconds",
    }
)


class ArtifactStoreError(RuntimeError):
    pass


class ContentAddressedArtifactStore:
    """A no-overwrite, digest-addressed store rooted by trusted host config."""

    def __init__(self, root: Path):
        if not Path(root).is_absolute():
            raise ArtifactStoreError("artifact root must be absolute")
        self.root = Path(os.path.abspath(root))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ArtifactStoreError("artifact root must be a real directory")
        self._canonical_root = self.root.resolve(strict=True)
        if self._canonical_root != self.root:
            raise ArtifactStoreError("artifact root must have no symlink ancestors")
        os.chmod(self.root, 0o700)
        root_metadata = self._canonical_root.stat(follow_symlinks=False)
        self._root_identity = (root_metadata.st_dev, root_metadata.st_ino)

    @staticmethod
    def _stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_nlink,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    def _open_leaf(self, hexdigest: str, *, create: bool) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self._canonical_root, flags)
        root_metadata = os.fstat(descriptor)
        if (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity:
            os.close(descriptor)
            raise ArtifactStoreError("artifact root identity changed")
        try:
            for component in ("sha256", hexdigest[:2], hexdigest[2:4]):
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                        os.fsync(descriptor)
                    except FileExistsError:
                        pass
                child = os.open(component, flags, dir_fd=descriptor)
                child_metadata = os.fstat(child)
                if not stat.S_ISDIR(child_metadata.st_mode):
                    os.close(child)
                    raise ArtifactStoreError("artifact store component is not a real directory")
                os.close(descriptor)
                descriptor = child
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def _read_at(self, directory_fd: int, name: str) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > 64 * 1024 * 1024:
                raise ArtifactStoreError("artifact is not a bounded regular file")
            chunks: list[bytes] = []
            bytes_read = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                bytes_read += len(chunk)
                if bytes_read > 64 * 1024 * 1024:
                    raise ArtifactStoreError("artifact exceeds the local read limit")
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if self._stable_identity(after) != self._stable_identity(before) or bytes_read != before.st_size:
                raise ArtifactStoreError("artifact changed during read")
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    def put_json(self, value: Any, *, media_type: str = "application/json") -> dict[str, Any]:
        return self.put_bytes(canonical_json(value), media_type=media_type)

    def put_bytes(self, value: bytes, *, media_type: str) -> dict[str, Any]:
        if not isinstance(value, bytes):
            raise ArtifactStoreError("artifact value must be bytes")
        if len(value) > 64 * 1024 * 1024:
            raise ArtifactStoreError("artifact exceeds the 64 MiB local limit")
        if not isinstance(media_type, str) or _MEDIA_TYPE.fullmatch(media_type) is None:
            raise ArtifactStoreError("artifact media type is invalid")
        hexdigest = hashlib.sha256(value).hexdigest()
        relative = Path("sha256") / hexdigest[:2] / hexdigest[2:4] / hexdigest
        leaf_fd: int | None = None
        try:
            leaf_fd = self._open_leaf(hexdigest, create=True)
            try:
                current = self._read_at(leaf_fd, hexdigest)
            except FileNotFoundError:
                temporary = f".{hexdigest}.{secrets.token_hex(16)}"
                temporary_fd = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=leaf_fd,
                )
                try:
                    remaining = memoryview(value)
                    while remaining:
                        written = os.write(temporary_fd, remaining)
                        if written <= 0:
                            raise ArtifactStoreError("artifact temporary write was short")
                        remaining = remaining[written:]
                    os.fsync(temporary_fd)
                finally:
                    os.close(temporary_fd)
                try:
                    try:
                        os.link(
                            temporary,
                            hexdigest,
                            src_dir_fd=leaf_fd,
                            dst_dir_fd=leaf_fd,
                            follow_symlinks=False,
                        )
                        os.fsync(leaf_fd)
                    except FileExistsError:
                        pass
                finally:
                    try:
                        os.unlink(temporary, dir_fd=leaf_fd)
                    except FileNotFoundError:
                        pass
                current = self._read_at(leaf_fd, hexdigest)
            if current != value:
                raise ArtifactStoreError("content-addressed artifact bytes do not match digest")
        except ArtifactStoreError:
            raise
        except OSError as exc:
            raise ArtifactStoreError("artifact publication failed closed") from exc
        finally:
            if leaf_fd is not None:
                os.close(leaf_fd)
        return {
            "digest": f"sha256:{hexdigest}",
            "bytes": len(value),
            "media_type": media_type,
            "relative_path": relative.as_posix(),
        }

    def get(self, digest: str) -> bytes:
        require_digest(digest, "artifact digest")
        hexdigest = digest.removeprefix("sha256:")
        leaf_fd: int | None = None
        try:
            leaf_fd = self._open_leaf(hexdigest, create=False)
            value = self._read_at(leaf_fd, hexdigest)
        except ArtifactStoreError:
            raise
        except OSError as exc:
            raise ArtifactStoreError("artifact is unavailable") from exc
        finally:
            if leaf_fd is not None:
                os.close(leaf_fd)
        if hashlib.sha256(value).hexdigest() != hexdigest:
            raise ArtifactStoreError("artifact digest verification failed")
        return value


def validate_evidence_receipt(
    receipt: Mapping[str, Any],
    *,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    expected_subject_digest: str,
) -> tuple[EvidenceState, str, str | None]:
    """Validate one externally produced receipt against trusted host bindings.

    A caller-provided ``independent`` flag is never sufficient.  The canonical
    receipt digest must also have been verified and minted into authority by the
    host-side evidence verifier.
    """

    authority.authorize_scope(request)
    if not isinstance(receipt, Mapping) or set(receipt) != _EVIDENCE_KEYS:
        raise ContractError("evidence receipt fields differ from the exact contract")
    if receipt.get("schema_version") != "1.0":
        raise ContractError("evidence receipt schema_version must be '1.0'")
    for key in ("evidence_id", "evidence_type", "producer_id", "verifier_id"):
        require_identifier(receipt.get(key), f"evidence.{key}")
    require_digest(receipt.get("revision_digest"), "evidence.revision_digest")
    require_digest(receipt.get("subject_digest"), "evidence.subject_digest")
    require_digest(receipt.get("artifact_digest"), "evidence.artifact_digest")
    if receipt.get("tenant_id") != request.tenant_id or receipt.get("project_id") != request.project_id:
        return EvidenceState.INVALID, "EVIDENCE_SCOPE_MISMATCH", None
    if receipt.get("revision_digest") != request.revision_digest:
        return EvidenceState.INVALID, "EVIDENCE_REVISION_MISMATCH", None
    if receipt.get("environment_authority_id") != request.environment_authority_id:
        return EvidenceState.INVALID, "EVIDENCE_ENVIRONMENT_MISMATCH", None
    require_digest(expected_subject_digest, "expected evidence subject digest")
    if receipt.get("subject_digest") != expected_subject_digest:
        return EvidenceState.INVALID, "EVIDENCE_SUBJECT_MISMATCH", None
    status = receipt.get("status")
    if status not in {"PASSED", "FAILED", "INCONCLUSIVE", "NOT_RUN"}:
        raise ContractError("evidence.status is unsupported")
    executed_at = receipt.get("executed_at_epoch_seconds")
    expires_at = receipt.get("expires_at_epoch_seconds")
    if not isinstance(executed_at, int) or executed_at <= 0:
        raise ContractError("evidence execution time is invalid")
    if not isinstance(expires_at, int) or expires_at <= executed_at:
        raise ContractError("evidence expiry is invalid")
    receipt_digest = digest_json(dict(receipt))
    if expires_at <= int(time.time()):
        return EvidenceState.INVALID, "EVIDENCE_EXPIRED", receipt_digest
    if status == "NOT_RUN":
        return EvidenceState.NOT_RUN, "EVIDENCE_NOT_RUN", receipt_digest
    if status == "INCONCLUSIVE":
        return EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED, "EVIDENCE_INCONCLUSIVE", receipt_digest
    if status == "FAILED":
        return EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED, "EVIDENCE_FAILED", receipt_digest
    if receipt.get("independent") is not True or receipt.get("producer_id") == receipt.get("verifier_id"):
        return EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED, "INDEPENDENT_VERIFIER_MISSING", receipt_digest
    if receipt_digest not in authority.verified_evidence_digests:
        return EvidenceState.EXTERNAL_EXECUTED_UNVERIFIED, "HOST_VERIFICATION_MISSING", receipt_digest
    return EvidenceState.INDEPENDENTLY_VERIFIED, "EVIDENCE_VERIFIED", receipt_digest


def evaluate_evidence_set(
    receipts: Sequence[Mapping[str, Any]],
    *,
    request: RuntimeRequest,
    authority: ExecutionAuthority,
    expected_subject_digest: str,
) -> dict[str, Any]:
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise ContractError("evidence_receipts must be an array")
    if len(receipts) > 1_000:
        raise ContractError("evidence_receipts exceeds the bounded limit")
    outcomes = []
    for receipt in receipts:
        state, code, receipt_digest = validate_evidence_receipt(
            receipt,
            request=request,
            authority=authority,
            expected_subject_digest=expected_subject_digest,
        )
        outcomes.append(
            {
                "evidence_id": receipt.get("evidence_id"),
                "evidence_type": receipt.get("evidence_type"),
                "state": state.value,
                "code": code,
                "receipt_digest": receipt_digest,
            }
        )
    independently_verified = sum(
        item["state"] == EvidenceState.INDEPENDENTLY_VERIFIED.value for item in outcomes
    )
    return {
        "receipts": outcomes,
        "receipt_count": len(outcomes),
        "independently_verified_count": independently_verified,
        "all_independently_verified": bool(outcomes)
        and independently_verified == len(outcomes),
    }
