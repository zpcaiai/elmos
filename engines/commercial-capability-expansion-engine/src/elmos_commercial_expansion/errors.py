"""Typed failures for the commercial capability control plane."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class CommercialRuntimeError(RuntimeError):
    """Base error with a stable, non-secret machine-readable code."""

    default_code = "COMMERCIAL_RUNTIME_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.details = dict(details or {})


class ContractError(CommercialRuntimeError, ValueError):
    default_code = "INVALID_CONTRACT"


class AuthorizationError(CommercialRuntimeError, PermissionError):
    default_code = "AUTHORIZATION_DENIED"


class IdempotencyConflict(CommercialRuntimeError):
    default_code = "IDEMPOTENCY_CONFLICT"


class IntegrityError(CommercialRuntimeError):
    default_code = "INTEGRITY_ERROR"


class StoreError(CommercialRuntimeError):
    default_code = "STORE_ERROR"


class NotFoundError(StoreError):
    default_code = "NOT_FOUND"


class TransitionConflict(StoreError):
    default_code = "TRANSITION_CONFLICT"
