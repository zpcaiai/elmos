"""Stable, machine-readable failures used by every kernel boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    code: str
    category: str = "capability-specific"
    retryable: bool = False
    partial: bool = False
    interrupted: bool = False
    evidence_ids: tuple[str, ...] = ()
    recommended_action: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "retryable": self.retryable,
            "partial": self.partial,
            "interrupted": self.interrupted,
            "evidenceIds": list(self.evidence_ids),
            "recommendedAction": self.recommended_action,
            "details": self.details,
        }


class KernelError(Exception):
    """Expected domain failure; never expose free text as the only error."""

    def __init__(self, info: ErrorInfo):
        super().__init__(info.code)
        self.info = info


class ContractError(KernelError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(
            ErrorInfo(
                code=code,
                details={"message": message, **(details or {})},
                recommended_action="Correct the typed input and retry.",
            )
        )


class AuthorizationError(KernelError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(
            ErrorInfo(
                code=code,
                category="authorization",
                details={"message": message, **(details or {})},
                recommended_action="Obtain an explicit scoped authority or stop the operation.",
            )
        )


class StaleStateError(KernelError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(
            ErrorInfo(
                code=code,
                category="state",
                retryable=False,
                details={"message": message, **(details or {})},
                recommended_action="Refresh the immutable snapshot and reconcile before retrying.",
            )
        )
