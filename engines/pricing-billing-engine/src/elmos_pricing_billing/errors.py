from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class DomainError(ValueError):
    """Fail-closed domain error with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})

    def __str__(self) -> str:
        return f"{self.code}: {super().__str__()}"


def require(condition: bool, code: str, message: str, **context: Any) -> None:
    if not condition:
        raise DomainError(code, message, context=context)
