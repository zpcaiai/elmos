"""Stable, content-safe errors for the multimodal intake boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class IntakeError(RuntimeError):
    """Base error whose public representation never includes raw input bytes."""

    http_status = 400

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.public_message = message or code
        self.retryable = retryable
        self.details = dict(details or {})
        super().__init__(self.public_message)

    def as_dict(self, trace_id: str | None = None) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.public_message,
            "retryable": self.retryable,
        }
        if trace_id:
            error["trace_id"] = trace_id
        if self.details:
            error["details"] = self.details
        return {"error": error}


class ValidationError(IntakeError):
    http_status = 422


class AuthorizationError(IntakeError):
    http_status = 403


class NotFoundError(IntakeError):
    http_status = 404


class ConflictError(IntakeError):
    http_status = 409


class IntegrityError(IntakeError):
    http_status = 422


class QuarantineError(IntakeError):
    http_status = 422


class ProviderUnavailableError(IntakeError):
    http_status = 503

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(code, message, retryable=True)


class InternalError(IntakeError):
    http_status = 500
