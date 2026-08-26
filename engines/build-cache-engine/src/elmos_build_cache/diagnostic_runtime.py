"""Content-free runtime wiring for first-difference cache diagnostics.

The lower-level diagnostic taxonomy deliberately does not know where cache
identity documents come from.  This module is the production-facing bridge:
it accepts the exact before/after identities used by a real lookup, persists
only their digests and first changed closed dimension, and derives bounded
top-loss summaries from the same durable outcome documents consumed by the
explain API.  Raw prompt, source, path, credential and tool output values are
never written to the repository.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from .canonical import digest_of
from .clock import SYSTEM_CLOCK, Clock
from .errors import ContractViolation
from .miss_diagnostics import (
    CacheCohort,
    CacheLayer,
    CacheOutcome,
    CacheOutcomeEvent,
    CacheOutcomeReason,
    FirstDifference,
    first_difference,
)

DIAGNOSTIC_SCHEMA_VERSION = "1.2.0"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_EXTERNAL_LAYER: Mapping[CacheLayer, str] = {
    CacheLayer.PROVIDER_PROMPT: "PROMPT",
    CacheLayer.ACTION: "ACTION",
    CacheLayer.CAS: "CAS_LOCAL",
    CacheLayer.CONTEXT: "CONTEXT",
    CacheLayer.ENVIRONMENT: "ENVIRONMENT",
    CacheLayer.NATIVE_BUILD: "NATIVE_BUILD",
    CacheLayer.STAGING: "CHECKPOINT",
    CacheLayer.COORDINATOR: "COORDINATOR",
}
_VALUE_FIELDS = (
    "compute_ms",
    "model_tokens",
    "bytes",
    "critical_path_ms",
    "monetary_micros",
)


class DiagnosticOutcomeRepository(Protocol):
    """The durable parity repository methods used by this runtime."""

    def put_cache_outcome(
        self,
        tenant_id: str,
        project_id: str,
        request_id: str,
        event_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def list_cache_outcomes(
        self, tenant_id: str, project_id: str, request_id: str
    ) -> Sequence[dict[str, Any]]: ...


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier")
    return value


def _non_negative_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContractViolation(f"{field} must be finite and non-negative")
    return number


def _non_negative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractViolation(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class LostValue:
    """Bounded, additive cost attached to one real cache miss."""

    compute_ms: float = 0.0
    model_tokens: int = 0
    bytes: int = 0
    critical_path_ms: float = 0.0
    monetary_micros: int = 0

    def __post_init__(self) -> None:
        _non_negative_number(self.compute_ms, "compute_ms")
        _non_negative_integer(self.model_tokens, "model_tokens")
        _non_negative_integer(self.bytes, "bytes")
        _non_negative_number(self.critical_path_ms, "critical_path_ms")
        _non_negative_integer(self.monetary_micros, "monetary_micros")

    def to_dict(self) -> dict[str, float | int]:
        return {
            "compute_ms": float(self.compute_ms),
            "model_tokens": self.model_tokens,
            "bytes": self.bytes,
            "critical_path_ms": float(self.critical_path_ms),
            "monetary_micros": self.monetary_micros,
        }


@dataclass(frozen=True)
class DiagnosticSummary:
    request_id: str
    events: int
    unknown_events: int
    by_reason: tuple[tuple[str, int], ...]
    total_lost_value: LostValue
    summary_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "request_id": self.request_id,
            "events": self.events,
            "unknown_events": self.unknown_events,
            "by_reason": [
                {"reason_code": reason, "count": count}
                for reason, count in self.by_reason
            ],
            "total_lost_value": self.total_lost_value.to_dict(),
            "summary_digest": self.summary_digest,
        }


class IdentityDiagnosticRuntime:
    """Persist exact identity drift without persisting identity values."""

    def __init__(
        self,
        repository: DiagnosticOutcomeRepository,
        *,
        tenant_id: str,
        project_id: str,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self.repository = repository
        self.tenant_id = _identifier(tenant_id, "tenant_id")
        self.project_id = _identifier(project_id, "project_id")
        self.clock = clock

    def record_miss(
        self,
        *,
        request_id: str,
        layer: CacheLayer,
        previous_identity: Mapping[str, Any],
        current_identity: Mapping[str, Any],
        eligible: bool = True,
        cohort: CacheCohort = CacheCohort.DEFAULT,
        lost_value: LostValue | None = None,
    ) -> dict[str, Any]:
        request = _identifier(request_id, "request_id")
        if not isinstance(layer, CacheLayer):
            raise ContractViolation("diagnostic layer uses an unknown vocabulary")
        if not isinstance(eligible, bool):
            raise ContractViolation("diagnostic eligibility must be boolean")
        if not isinstance(cohort, CacheCohort):
            raise ContractViolation("diagnostic cohort uses an unknown vocabulary")
        resolved_value = LostValue() if lost_value is None else lost_value
        if not isinstance(resolved_value, LostValue):
            raise ContractViolation("diagnostic lost value has an invalid type")

        difference = first_difference(previous_identity, current_identity)
        reason, outcome = _terminal_miss(difference)
        event = CacheOutcomeEvent(
            layer=layer,
            outcome=outcome,
            reason=reason,
            eligible=eligible,
            cohort=cohort,
            first_difference=difference,
        )
        previous_digest = digest_of(dict(previous_identity))
        current_digest = digest_of(dict(current_identity))
        event_id = "cache_event_" + digest_of(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "request_id": request,
                "layer": layer.value,
                "previous_identity_digest": previous_digest,
                "current_identity_digest": current_digest,
                "reason_code": reason.value,
            }
        ).removeprefix("sha256:")
        document: dict[str, Any] = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "event_id": event_id,
            "request_id": request,
            "layer": _EXTERNAL_LAYER[layer],
            "outcome": outcome.value,
            "reason_code": reason.value,
            "eligible": eligible,
            "identity_digest": current_digest,
            "first_difference": (
                None if difference is None else difference.to_dict()
            ),
            "avoided_or_lost_value": {
                **resolved_value.to_dict(),
                "identity_transition": {
                    "previous_identity_digest": previous_digest,
                    "current_identity_digest": current_digest,
                },
            },
            "occurred_at": datetime.fromtimestamp(
                self.clock.now(), tz=UTC
            ).isoformat(),
        }
        # Constructing the typed event above validates the reason/outcome pair.
        # Persist only after every closed-vocabulary and cost check succeeds.
        del event
        return self.repository.put_cache_outcome(
            self.tenant_id,
            self.project_id,
            request,
            event_id,
            document,
        )

    def summarize(self, request_id: str) -> DiagnosticSummary:
        request = _identifier(request_id, "request_id")
        documents = self.repository.list_cache_outcomes(
            self.tenant_id, self.project_id, request
        )
        reasons: Counter[str] = Counter()
        totals: dict[str, float | int] = {
            "compute_ms": 0.0,
            "model_tokens": 0,
            "bytes": 0,
            "critical_path_ms": 0.0,
            "monetary_micros": 0,
        }
        unknown = 0
        for document in documents:
            reason = CacheOutcomeReason(str(document.get("reason_code")))
            reasons[reason.value] += 1
            if reason in {
                CacheOutcomeReason.UNKNOWN_IDENTITY_CHANGE,
                CacheOutcomeReason.UNKNOWN_MISS,
                CacheOutcomeReason.UNKNOWN_LOOKUP_ERROR,
            }:
                unknown += 1
            value = document.get("avoided_or_lost_value", {})
            if not isinstance(value, Mapping):
                raise ContractViolation("stored diagnostic value is not an object")
            totals["compute_ms"] = float(totals["compute_ms"]) + _non_negative_number(
                value.get("compute_ms", 0.0), "compute_ms"
            )
            totals["critical_path_ms"] = float(
                totals["critical_path_ms"]
            ) + _non_negative_number(
                value.get("critical_path_ms", 0.0), "critical_path_ms"
            )
            for field in ("model_tokens", "bytes", "monetary_micros"):
                totals[field] = int(totals[field]) + _non_negative_integer(
                    value.get(field, 0), field
                )
        ordered = tuple(sorted(reasons.items(), key=lambda item: (-item[1], item[0])))
        total = LostValue(
            compute_ms=float(totals["compute_ms"]),
            model_tokens=int(totals["model_tokens"]),
            bytes=int(totals["bytes"]),
            critical_path_ms=float(totals["critical_path_ms"]),
            monetary_micros=int(totals["monetary_micros"]),
        )
        digest = digest_of(
            {
                "request_id": request,
                "events": len(documents),
                "unknown_events": unknown,
                "by_reason": list(ordered),
                "total_lost_value": total.to_dict(),
            }
        )
        return DiagnosticSummary(
            request,
            len(documents),
            unknown,
            ordered,
            total,
            digest,
        )


def _terminal_miss(
    difference: FirstDifference | None,
) -> tuple[CacheOutcomeReason, CacheOutcome]:
    if difference is None:
        return CacheOutcomeReason.UNKNOWN_MISS, CacheOutcome.UNEXPECTED_MISS
    if difference.reason is CacheOutcomeReason.WRONG_SHARD:
        return difference.reason, CacheOutcome.UNEXPECTED_MISS
    return difference.reason, CacheOutcome.NECESSARY_MISS


__all__ = [
    "DiagnosticOutcomeRepository",
    "DiagnosticSummary",
    "IdentityDiagnosticRuntime",
    "LostValue",
]
