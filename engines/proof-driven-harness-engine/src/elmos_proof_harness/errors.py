"""Structured, stable errors for the proof-driven harness public API.

Every boundary raises a :class:`HarnessError` subclass rather than leaking
SQLite or operating-system exception text.  ``to_dict`` is intentionally safe
to serialize into audit records and API responses; callers should not put
secrets in ``details``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(eq=False)
class HarnessError(Exception):
    """Base error carrying a machine-readable code and safe context."""

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    retryable: bool = False
    http_status: int = 400

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
            "retryable": self.retryable,
            "http_status": self.http_status,
        }


class ValidationError(HarnessError):
    def __init__(self, message: str, *, code: str = "VALIDATION_FAILED", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 422)


class AuthorizationError(HarnessError, PermissionError):
    def __init__(self, message: str, *, code: str = "AUTHORITY_DENIED", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 403)


class ConflictError(HarnessError):
    def __init__(self, message: str, *, code: str = "OPTIMISTIC_CONFLICT", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, True, 409)


class IntegrityError(HarnessError):
    def __init__(self, message: str, *, code: str = "INTEGRITY_FAILED", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 409)


class NotFoundError(HarnessError, LookupError):
    def __init__(self, message: str, *, code: str = "NOT_FOUND", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 404)


class StoreError(HarnessError):
    def __init__(self, message: str, *, code: str = "STORE_FAILED", details: Mapping[str, Any] | None = None, retryable: bool = False) -> None:
        super().__init__(code, message, details or {}, retryable, 500)


class WorkflowError(HarnessError):
    def __init__(self, message: str, *, code: str = "WORKFLOW_INVALID", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 409)


class ProofError(HarnessError):
    def __init__(self, message: str, *, code: str = "PROOF_INVALID", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 422)


class CertificationError(HarnessError):
    def __init__(self, message: str, *, code: str = "CERTIFICATION_BLOCKED", details: Mapping[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, False, 422)
