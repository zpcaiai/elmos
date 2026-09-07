"""Idempotent, resumable upload protocol backed by the local tenant CAS."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .canonical import (
    canonical_digest,
    normalize_relative_path,
    normalize_sha256,
    require_idempotency_key,
    require_resource_id,
    sha256_bytes,
)
from .errors import ConflictError, IntegrityError, NotFoundError, ValidationError
from .models import InputAsset, PartAck, TenantContext, UploadSession, UploadStatus
from .store import IntakeStore, LocalCasStore


MAXIMUM_PROCESSABLE_ASSET_BYTES = 64 * 1024 * 1024
_DEFAULT_DECLARED_TYPE_LIMIT = 16 * 1024 * 1024
_DECLARED_TYPE_LIMITS = {
    "text/plain": 4 * 1024 * 1024,
    "text/markdown": 4 * 1024 * 1024,
    "text/x-log": 4 * 1024 * 1024,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 32 * 1024 * 1024,
    "application/msword": 32 * 1024 * 1024,
    "application/pdf": 48 * 1024 * 1024,
    "image/png": 24 * 1024 * 1024,
    "image/jpeg": 24 * 1024 * 1024,
    "image/gif": 16 * 1024 * 1024,
    "image/webp": 24 * 1024 * 1024,
    "audio/wav": 48 * 1024 * 1024,
    "audio/mpeg": 48 * 1024 * 1024,
    "audio/mp4": 48 * 1024 * 1024,
    "audio/ogg": 48 * 1024 * 1024,
    "application/zip": 32 * 1024 * 1024,
}


def maximum_bytes_for_media_type(media_type: str) -> int:
    normalized = str(media_type or "").split(";", 1)[0].strip().lower()
    return min(
        MAXIMUM_PROCESSABLE_ASSET_BYTES,
        _DECLARED_TYPE_LIMITS.get(normalized, _DEFAULT_DECLARED_TYPE_LIMIT),
    )


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    maximum_asset_bytes: int = MAXIMUM_PROCESSABLE_ASSET_BYTES
    default_part_size: int = 8 * 1024 * 1024
    maximum_part_size: int = 8 * 1024 * 1024
    maximum_parts: int = 4096
    default_ttl_seconds: int = 24 * 60 * 60
    maximum_ttl_seconds: int = 7 * 24 * 60 * 60

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_asset_bytes <= MAXIMUM_PROCESSABLE_ASSET_BYTES:
            raise ValidationError("UPLOAD_POLICY_ASSET_LIMIT_INVALID")
        if (
            not 1 <= self.default_part_size <= self.maximum_part_size
            or self.maximum_part_size > 8 * 1024 * 1024
        ):
            raise ValidationError("UPLOAD_POLICY_PART_SIZE_INVALID")
        if self.maximum_parts < 1:
            raise ValidationError("UPLOAD_POLICY_PART_COUNT_INVALID")
        if not 1 <= self.default_ttl_seconds <= self.maximum_ttl_seconds:
            raise ValidationError("UPLOAD_POLICY_TTL_INVALID")


class ResumableUploadManager:
    """Implements start/part/commit without trusting client offsets or hashes."""

    def __init__(
        self,
        store: IntakeStore,
        cas: LocalCasStore,
        policy: UploadPolicy | None = None,
    ) -> None:
        self.store = store
        self.cas = cas
        self.policy = policy or UploadPolicy()

    def start(
        self,
        context: TenantContext,
        *,
        session_id: str,
        display_name: str,
        declared_media_type: str,
        expected_size: int,
        expected_sha256: str,
        idempotency_key: str,
        part_size: int | None = None,
        ttl_seconds: int | None = None,
    ) -> tuple[InputAsset, UploadSession]:
        session_id = require_resource_id(session_id, "session_id")
        safe_name = normalize_relative_path(display_name)
        media_type = self._media_type(declared_media_type)
        digest = normalize_sha256(expected_sha256)
        key = self._idempotency_key(idempotency_key)
        if not isinstance(expected_size, int) or isinstance(expected_size, bool):
            raise ValidationError("UPLOAD_SIZE_INVALID")
        media_limit = min(self.policy.maximum_asset_bytes, maximum_bytes_for_media_type(media_type))
        if expected_size < 1 or expected_size > media_limit:
            raise ValidationError("UPLOAD_SIZE_OUTSIDE_POLICY")
        selected_part_size = self.policy.default_part_size if part_size is None else part_size
        if not isinstance(selected_part_size, int) or not 1 <= selected_part_size <= self.policy.maximum_part_size:
            raise ValidationError("UPLOAD_PART_SIZE_OUTSIDE_POLICY")
        part_count = (expected_size + selected_part_size - 1) // selected_part_size
        if part_count > self.policy.maximum_parts:
            raise ValidationError("UPLOAD_PART_COUNT_OUTSIDE_POLICY")
        selected_ttl = self.policy.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if not isinstance(selected_ttl, int) or not 1 <= selected_ttl <= self.policy.maximum_ttl_seconds:
            raise ValidationError("UPLOAD_TTL_OUTSIDE_POLICY")
        request = {
            "session_id": session_id,
            "display_name": safe_name,
            "declared_media_type": media_type,
            "expected_size": expected_size,
            "expected_sha256": digest,
            "part_size": selected_part_size,
            "ttl_seconds": selected_ttl,
            "maximum_bytes_for_declared_type": media_limit,
        }
        expires_at = (datetime.now(UTC) + timedelta(seconds=selected_ttl)).replace(microsecond=0).isoformat()
        return self.store.create_upload(
            context,
            session_id=session_id,
            display_name=safe_name,
            declared_media_type=media_type,
            expected_size=expected_size,
            expected_sha256=digest,
            part_size=selected_part_size,
            idempotency_key=key,
            request_digest=canonical_digest(request),
            expires_at=expires_at,
        )

    def upload_part(
        self,
        context: TenantContext,
        *,
        upload_id: str,
        part_number: int,
        byte_offset: int,
        data: bytes,
        sha256: str,
        idempotency_key: str,
    ) -> PartAck:
        upload_id = require_resource_id(upload_id, "upload_id")
        upload = self.store.get_upload(context, upload_id, write=True)
        if upload.status is UploadStatus.OPEN:
            upload = self._open_upload(context, upload_id)
        elif upload.status is not UploadStatus.COMPLETED:
            raise ConflictError("UPLOAD_SESSION_NOT_OPEN")
        if not isinstance(part_number, int) or isinstance(part_number, bool) or part_number < 0:
            raise ValidationError("UPLOAD_PART_NUMBER_INVALID")
        if part_number >= self.policy.maximum_parts:
            raise ValidationError("UPLOAD_PART_NUMBER_OUTSIDE_POLICY")
        if not isinstance(byte_offset, int) or byte_offset < 0:
            raise ValidationError("UPLOAD_PART_OFFSET_INVALID")
        if not isinstance(data, bytes) or not data:
            raise ValidationError("UPLOAD_PART_BYTES_REQUIRED")
        expected_offset = part_number * upload.part_size
        if byte_offset != expected_offset or byte_offset >= upload.expected_size:
            raise ConflictError("UPLOAD_PART_OFFSET_MISMATCH")
        expected_length = min(upload.part_size, upload.expected_size - byte_offset)
        if len(data) != expected_length:
            raise ValidationError("UPLOAD_PART_LENGTH_MISMATCH")
        declared_digest = normalize_sha256(sha256)
        actual_digest = sha256_bytes(data)
        if actual_digest != declared_digest:
            raise IntegrityError("UPLOAD_PART_DIGEST_MISMATCH")
        cas_digest = self.cas.put_bytes(context.tenant_id, data, declared_digest)
        duplicate, received, next_offset = self.store.record_part(
            context,
            upload_id,
            part_number=part_number,
            idempotency_key=self._idempotency_key(idempotency_key),
            byte_offset=byte_offset,
            byte_size=len(data),
            sha256=declared_digest,
            cas_digest=cas_digest,
        )
        return PartAck(
            upload_id=upload_id,
            part_number=part_number,
            status="DUPLICATE_IDENTICAL" if duplicate else "ACCEPTED",
            received_bytes=received,
            next_offset=next_offset,
            sha256=declared_digest,
        )

    def commit(
        self,
        context: TenantContext,
        *,
        upload_id: str,
        idempotency_key: str,
    ) -> InputAsset:
        upload_id = require_resource_id(upload_id, "upload_id")
        commit_key = self._idempotency_key(idempotency_key)
        upload = self.store.get_upload(context, upload_id, write=True)
        if upload.status is UploadStatus.COMPLETED:
            return self.store.complete_upload(
                context,
                upload_id,
                commit_idempotency_key=commit_key,
                digest=upload.expected_sha256,
                byte_size=upload.expected_size,
            )
        upload = self._open_upload(context, upload_id)
        parts = self.store.upload_parts(context, upload_id)
        expected_offset = 0
        chunks: list[tuple[str, int]] = []
        for expected_number, part in enumerate(parts):
            if part["part_number"] != expected_number or part["byte_offset"] != expected_offset:
                raise ConflictError("UPLOAD_PARTS_NOT_CONTIGUOUS")
            expected_size = min(upload.part_size, upload.expected_size - expected_offset)
            if part["byte_size"] != expected_size:
                raise IntegrityError("UPLOAD_STORED_PART_SIZE_MISMATCH")
            chunks.append((part["cas_digest"], part["byte_size"]))
            expected_offset += part["byte_size"]
        if expected_offset != upload.expected_size:
            raise ConflictError(
                "UPLOAD_INCOMPLETE",
                details={"received_bytes": expected_offset, "expected_bytes": upload.expected_size},
            )

        def stream() -> Iterator[bytes]:
            for digest, _size in chunks:
                yield from self.cas.iter_bytes(context.tenant_id, digest)

        try:
            final_digest = self.cas.put_stream(
                context.tenant_id,
                upload.expected_sha256,
                upload.expected_size,
                stream(),
            )
        except (IntegrityError, NotFoundError) as error:
            self.store.quarantine_upload(context, upload_id, error.code)
            raise
        return self.store.complete_upload(
            context,
            upload_id,
            commit_idempotency_key=commit_key,
            digest=final_digest,
            byte_size=upload.expected_size,
        )

    def status(self, context: TenantContext, upload_id: str) -> UploadSession:
        return self.store.get_upload(context, require_resource_id(upload_id, "upload_id"))

    def abort(self, context: TenantContext, upload_id: str) -> UploadSession:
        return self.store.abort_upload(context, require_resource_id(upload_id, "upload_id"))

    def _open_upload(self, context: TenantContext, upload_id: str) -> UploadSession:
        upload = self.store.get_upload(context, upload_id, write=True)
        if upload.status is not UploadStatus.OPEN:
            raise ConflictError("UPLOAD_SESSION_NOT_OPEN")
        expires_at = datetime.fromisoformat(upload.expires_at)
        if expires_at.tzinfo is None or expires_at <= datetime.now(UTC):
            self.store.expire_upload(context, upload_id)
            raise ConflictError("UPLOAD_SESSION_EXPIRED")
        return upload

    @staticmethod
    def _idempotency_key(value: str) -> str:
        return require_idempotency_key(value)

    @staticmethod
    def _media_type(value: str) -> str:
        media_type = str(value or "").split(";", 1)[0].strip().lower()
        if not media_type or "/" not in media_type or len(media_type) > 127:
            raise ValidationError("MEDIA_TYPE_INVALID")
        return media_type
