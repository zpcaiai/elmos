"""Typed error codes shared by the API, CLI and library surfaces.

Every failure that crosses a process or protocol boundary carries a stable
``code`` so operators and adapters can react without string matching.
"""

from __future__ import annotations

from typing import Any


class ErrorCode:
    """Stable machine-readable error codes (see the API contract skill)."""

    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    STALE_LEASE = "STALE_LEASE"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    VALIDATION_TOO_LOW = "VALIDATION_TOO_LOW"
    QUARANTINED_ENTRY = "QUARANTINED_ENTRY"
    CONFLICT = "CONFLICT"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    UNSAFE_PATH = "UNSAFE_PATH"
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    TRUST_NAMESPACE_MISMATCH = "TRUST_NAMESPACE_MISMATCH"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    SECRET_DETECTED = "SECRET_DETECTED"  # noqa: S105 - an error code, not a credential
    NONDETERMINISTIC_STAGE = "NONDETERMINISTIC_STAGE"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    CORRUPT_OBJECT = "CORRUPT_OBJECT"
    REMOTE_UNAVAILABLE = "REMOTE_UNAVAILABLE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    CERTIFICATE_INVALID = "CERTIFICATE_INVALID"
    UNSUPPORTED = "UNSUPPORTED"


class ElmosCacheError(Exception):
    """Base class for every error raised by this subsystem."""

    code: str = "ELMOS_CACHE_ERROR"
    http_status: int = 500

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}"


class DigestMismatch(ElmosCacheError):
    code = ErrorCode.DIGEST_MISMATCH
    http_status = 422


class CorruptObject(ElmosCacheError):
    code = ErrorCode.CORRUPT_OBJECT
    http_status = 422


class StaleLease(ElmosCacheError):
    code = ErrorCode.STALE_LEASE
    http_status = 409


class InvalidTransition(ElmosCacheError):
    code = ErrorCode.INVALID_TRANSITION
    http_status = 409


class VersionConflict(ElmosCacheError):
    code = ErrorCode.VERSION_CONFLICT
    http_status = 409


class ValidationTooLow(ElmosCacheError):
    code = ErrorCode.VALIDATION_TOO_LOW
    http_status = 412


class QuarantinedEntry(ElmosCacheError):
    code = ErrorCode.QUARANTINED_ENTRY
    http_status = 409


class ConflictError(ElmosCacheError):
    code = ErrorCode.CONFLICT
    http_status = 409


class QuotaExceeded(ElmosCacheError):
    code = ErrorCode.QUOTA_EXCEEDED
    http_status = 507


class UnsafePath(ElmosCacheError):
    code = ErrorCode.UNSAFE_PATH
    http_status = 400


class NotFound(ElmosCacheError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class PermissionDenied(ElmosCacheError):
    code = ErrorCode.PERMISSION_DENIED
    http_status = 403


class TenantMismatch(ElmosCacheError):
    code = ErrorCode.TENANT_MISMATCH
    http_status = 404


class TrustNamespaceMismatch(ElmosCacheError):
    code = ErrorCode.TRUST_NAMESPACE_MISMATCH
    http_status = 403


class ProvenanceInvalid(ElmosCacheError):
    code = ErrorCode.PROVENANCE_INVALID
    http_status = 403


class SecretDetected(ElmosCacheError):
    code = ErrorCode.SECRET_DETECTED
    http_status = 422


class NondeterministicStage(ElmosCacheError):
    code = ErrorCode.NONDETERMINISTIC_STAGE
    http_status = 409


class ContractViolation(ElmosCacheError):
    code = ErrorCode.CONTRACT_VIOLATION
    http_status = 422


class SchemaInvalid(ElmosCacheError):
    code = ErrorCode.SCHEMA_INVALID
    http_status = 422


class RemoteUnavailable(ElmosCacheError):
    code = ErrorCode.REMOTE_UNAVAILABLE
    http_status = 503


class IdempotencyConflict(ElmosCacheError):
    code = ErrorCode.IDEMPOTENCY_CONFLICT
    http_status = 409


class CertificateInvalid(ElmosCacheError):
    code = ErrorCode.CERTIFICATE_INVALID
    http_status = 403


class Unsupported(ElmosCacheError):
    code = ErrorCode.UNSUPPORTED
    http_status = 501
