"""Typed failures for the PDHI v1 foundation."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


class PDHIError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PDHI_ERROR",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = MappingProxyType(dict(details or {}))


class ValidationError(PDHIError):
    pass


class AuthorizationError(PDHIError):
    pass


class ConflictError(PDHIError):
    pass


class NotFoundError(PDHIError):
    pass


class IntegrityError(PDHIError):
    pass


class RegistryError(PDHIError):
    pass


class UnknownSkillError(NotFoundError, RegistryError):
    pass


class UnknownCapabilityError(NotFoundError, RegistryError):
    pass


class AmbiguousCapabilityError(ConflictError, RegistryError):
    pass


class ArchiveSecurityError(PDHIError):
    pass
