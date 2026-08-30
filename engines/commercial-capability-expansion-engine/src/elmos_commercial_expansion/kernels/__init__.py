"""Read-only metadata surface for the eight commercial capability kernels.

The execution registry is intentionally private.  Only the authenticated
runtime resolves exact handlers; package callers receive catalog metadata.
"""

from collections.abc import Callable, Mapping
from typing import Any

from ..contracts import HandlerRequest, HandlerResult, SkillInputContract


def _exact_registry() -> tuple[
    Mapping[str, Callable[[HandlerRequest], HandlerResult]],
    Mapping[str, SkillInputContract],
]:
    """Return the internal exact registry and contracts to trusted package code."""

    from .exact_handlers import EXACT_SKILL_HANDLERS, EXACT_SKILL_INPUT_CONTRACTS

    return EXACT_SKILL_HANDLERS, EXACT_SKILL_INPUT_CONTRACTS


def list_capability_kernels() -> list[dict[str, Any]]:
    """Late-bound compatibility export owned by the fail-closed service."""

    from ..service import list_capability_kernels as implementation

    return implementation()


def get_commercial_status() -> dict[str, Any]:
    """Late-bound compatibility export; never manufactures an ACTIVE state."""

    from ..service import get_commercial_status as implementation

    return implementation()


__all__ = [
    "get_commercial_status",
    "list_capability_kernels",
]
