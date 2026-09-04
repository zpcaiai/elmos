"""Stable, machine-readable failure taxonomy for the autonomy kernel.

Every failure crossing a kernel boundary is a :class:`KernelError`.  A bare
string is never a valid error: the wire shape mandated by every SKILL.md is::

    {"code", "category", "retryable", "partial", "interrupted",
     "evidenceIds", "recommendedAction"}

Two rules are enforced here rather than left to callers:

* ``INTERRUPTED``/``PARTIAL``/``FAILED``/``SUCCEEDED`` never collapse into each
  other.  ``partial`` and ``interrupted`` are separate booleans and a result
  carrying either can never be rendered as success (see :mod:`.contracts`).
* Unknown codes are rejected at construction time.  A typo becomes an
  ``AssertionError`` in tests, not a silent new taxonomy member in production.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "Category",
    "KernelError",
    "CODES",
    "register_codes",
    "code_category",
]


class Category(StrEnum):
    """Coarse routing class for a failure.

    The category decides *who* handles the failure; the code decides *what*
    happened.  Retry controllers key off the category, dashboards off the code.
    """

    INPUT = "input"
    AUTHORITY = "authority"
    POLICY = "policy"
    SANDBOX = "sandbox"
    CONCURRENCY = "concurrency"
    ORCHESTRATION = "orchestration"
    SEMANTIC = "semantic"
    VERIFICATION = "verification"
    RELEASE = "release"
    RESOURCE = "resource"
    PROVIDER = "provider"
    INTEGRITY = "integrity"
    NOT_APPLICABLE = "not-applicable"


#: Canonical registry: code -> category.  Populated by the kernel modules at
#: import time through :func:`register_codes` so that each capability owns its
#: own codes while the union stays centrally validatable.
CODES: dict[str, Category] = {}


def register_codes(category: Category, *codes: str) -> None:
    """Register stable failure codes for ``category``.

    Re-registering the same code with the same category is a no-op (module
    reimport is harmless).  Re-registering with a *different* category is a
    programming error and raises immediately: a code must mean one thing.
    """

    for code in codes:
        if not code or code != code.upper():
            raise ValueError(f"failure code must be UPPER_SNAKE: {code!r}")
        existing = CODES.get(code)
        if existing is not None and existing != category:
            raise ValueError(
                f"failure code {code!r} already registered as {existing!r}, "
                f"cannot re-register as {category!r}"
            )
        CODES[code] = category


def code_category(code: str) -> Category:
    """Return the registered category for ``code`` or raise ``KeyError``."""

    return CODES[code]


# --- kernel-wide codes -------------------------------------------------------

register_codes(
    Category.INPUT,
    "MALFORMED_INPUT",
    "MISSING_REQUIRED_INPUT",
    "UNKNOWN_FIELD",
    "INPUT_TOO_LARGE",
    "STALE_SNAPSHOT",
    "STALE_POLICY_SNAPSHOT",
)
register_codes(
    Category.AUTHORITY,
    "AUTHORITY_SCOPE_MISMATCH",
    "AUTHORITY_EXPIRED",
    "THREAD_GLOBAL_AUTHORITY_FORBIDDEN",
    "FENCING_REJECTED",
    "TOOL_DENIED",
)
register_codes(
    Category.POLICY,
    "POLICY_DENIED",
    "POLICY_REQUIRES_APPROVAL",
    "POLICY_SNAPSHOT_MISSING",
)
register_codes(
    Category.CONCURRENCY,
    "LEASE_LOST",
    "LEASE_HELD_BY_OTHER",
    "WRITE_CONFLICT",
)
register_codes(
    Category.ORCHESTRATION,
    "ORCHESTRATOR_INCONSISTENT",
    "ILLEGAL_TRANSITION",
    "FAILED_RETRYABLE",
    "FAILED_TERMINAL",
    "CANCELLED",
    "PARTIAL",
    "BUDGET_EXHAUSTED",
    "MAX_TURNS_EXCEEDED",
)
register_codes(
    Category.INTEGRITY,
    "DIGEST_MISMATCH",
    "EVIDENCE_MISSING",
    "EVIDENCE_UNVERIFIABLE",
    "IDEMPOTENCY_CONFLICT",
)
register_codes(
    Category.NOT_APPLICABLE,
    "NOT_APPLICABLE",
)


@dataclass
class KernelError(Exception):
    """A structured, wire-serialisable kernel failure.

    ``retryable`` is deliberately *not* derived from the category: the same
    code can be retryable in one call site and terminal in another (a lease
    conflict is retryable during acquisition, terminal mid-write).  Callers
    must state it, and the default is the safe one.

    **Why this dataclass is neither frozen nor slotted**, unlike every other
    dataclass in the kernel: Python attaches ``__traceback__``, ``__cause__``
    and ``__context__`` to an exception *by assignment* as it propagates.  A
    ``frozen=True, slots=True`` dataclass generates a ``__setattr__`` that
    refuses those writes — and, worse, fails with
    ``TypeError: super(type, obj): obj must be an instance or subtype of type``
    rather than anything readable.  The original error is then replaced by a
    confusing type error at whatever context manager happened to re-raise it,
    which is a spectacular way to lose the actual cause of a production
    incident.  This was a real defect here: it only surfaced when the first
    ``KernelError`` propagated out of a live database transaction, because a
    plain ``pytest.raises`` never exercises the re-raise path.  Immutability is
    kept by convention instead; an exception's life is one raise long.
    """

    code: str
    message: str
    retryable: bool = False
    partial: bool = False
    interrupted: bool = False
    evidence_ids: tuple[str, ...] = ()
    recommended_action: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in CODES:
            raise ValueError(
                f"unregistered failure code {self.code!r}; "
                "register it with errors.register_codes before raising it"
            )
        if not self.message:
            raise ValueError("KernelError requires a non-empty message")

    @property
    def category(self) -> Category:
        return CODES[self.code]

    def to_payload(self) -> dict[str, Any]:
        """Render the mandated error envelope."""

        return {
            "code": self.code,
            "category": str(self.category),
            "message": self.message,
            "retryable": self.retryable,
            "partial": self.partial,
            "interrupted": self.interrupted,
            "evidenceIds": list(self.evidence_ids),
            "recommendedAction": self.recommended_action,
            "details": dict(self.details),
        }

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"


def not_applicable(reason: str, *, skill: str) -> KernelError:
    """Build the canonical NOT_APPLICABLE error.

    A skill whose input contract is unmet returns this instead of guessing.
    It is not a failure of the run; the caller decides whether to route
    elsewhere.
    """

    return KernelError(
        code="NOT_APPLICABLE",
        message=f"{skill}: {reason}",
        retryable=False,
        recommended_action="route to a capability whose input contract is satisfied",
        details={"skill": skill},
    )


def require_codes_registered(codes: Sequence[str]) -> None:
    """Assert every code in ``codes`` is registered (used by conformance tests)."""

    missing = [code for code in codes if code not in CODES]
    if missing:
        raise ValueError(f"unregistered failure codes: {sorted(missing)}")
