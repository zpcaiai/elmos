"""Closed cache outcome taxonomy and privacy-safe first-difference diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .canonical import digest_of
from .errors import ContractViolation

OUTCOME_SCHEMA_VERSION = "elmos.cache-outcome/v1"

_COHORT_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class _ValueEnum(StrEnum):
    pass


class CacheLayer(_ValueEnum):
    PROVIDER_PROMPT = "provider-prompt"
    ACTION = "action"
    CAS = "cas"
    CONTEXT = "context"
    ENVIRONMENT = "environment"
    NATIVE_BUILD = "native-build"
    STAGING = "staging"
    COORDINATOR = "coordinator"


class CacheOutcome(_ValueEnum):
    HIT = "HIT"
    NECESSARY_MISS = "NECESSARY_MISS"
    UNEXPECTED_MISS = "UNEXPECTED_MISS"
    BYPASS = "BYPASS"
    RESTORE_FAILURE = "RESTORE_FAILURE"
    LOOKUP_ERROR = "LOOKUP_ERROR"


class ReasonFamily(_ValueEnum):
    HIT = "HIT"
    COLD = "COLD"
    IDENTITY_CHANGED = "IDENTITY_CHANGED"
    TTL_OR_RETENTION = "TTL_OR_RETENTION"
    PLACEMENT = "PLACEMENT"
    CAPACITY_POLICY = "CAPACITY_POLICY"
    RESTORE = "RESTORE"
    SECURITY = "SECURITY"
    CORRUPTION = "CORRUPTION"
    ECONOMIC_BYPASS = "ECONOMIC_BYPASS"
    UNSUPPORTED = "UNSUPPORTED"
    BACKEND = "BACKEND"
    UNKNOWN = "UNKNOWN"


class CacheOutcomeReason(_ValueEnum):
    EXACT_RESULT_REUSED = "EXACT_RESULT_REUSED"
    PROMPT_PREFIX_REUSED = "PROMPT_PREFIX_REUSED"
    ARTIFACT_RESTORED = "ARTIFACT_RESTORED"
    COLD_NO_ENTRY = "COLD_NO_ENTRY"
    TENANT_CHANGED = "TENANT_CHANGED"
    AUTHORIZATION_CHANGED = "AUTHORIZATION_CHANGED"
    TRUST_NAMESPACE_CHANGED = "TRUST_NAMESPACE_CHANGED"
    PROVIDER_CHANGED = "PROVIDER_CHANGED"
    MODEL_CHANGED = "MODEL_CHANGED"
    EFFORT_CHANGED = "EFFORT_CHANGED"
    TOOL_SCHEMA_CHANGED = "TOOL_SCHEMA_CHANGED"
    PREFIX_COMPATIBILITY_CHANGED = "PREFIX_COMPATIBILITY_CHANGED"
    PROMPT_SEGMENT_CHANGED = "PROMPT_SEGMENT_CHANGED"
    PUBLIC_INTERFACE_CHANGED = "PUBLIC_INTERFACE_CHANGED"
    RULE_PACK_CHANGED = "RULE_PACK_CHANGED"
    LOCKFILE_CHANGED = "LOCKFILE_CHANGED"
    ENVIRONMENT_CHANGED = "ENVIRONMENT_CHANGED"
    VALIDATION_REQUIREMENT_CHANGED = "VALIDATION_REQUIREMENT_CHANGED"
    TTL_EXPIRED = "TTL_EXPIRED"
    CACHE_EVICTED = "CACHE_EVICTED"
    WRONG_SHARD = "WRONG_SHARD"
    CAPACITY_EXHAUSTED = "CAPACITY_EXHAUSTED"
    POLICY_BYPASS = "POLICY_BYPASS"
    SNAPSHOT_REVOKED = "SNAPSHOT_REVOKED"
    SNAPSHOT_CORRUPT = "SNAPSHOT_CORRUPT"
    RESTORE_FAILED = "RESTORE_FAILED"
    RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE = "RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE"
    TENANT_MISMATCH = "TENANT_MISMATCH"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    TRUST_NAMESPACE_MISMATCH = "TRUST_NAMESPACE_MISMATCH"
    CORRUPT_OBJECT = "CORRUPT_OBJECT"
    PROVIDER_UNSUPPORTED = "PROVIDER_UNSUPPORTED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    UNKNOWN_IDENTITY_CHANGE = "UNKNOWN_IDENTITY_CHANGE"
    UNKNOWN_MISS = "UNKNOWN_MISS"
    UNKNOWN_LOOKUP_ERROR = "UNKNOWN_LOOKUP_ERROR"


class CacheCohort(_ValueEnum):
    DEFAULT = "default"
    INTERACTIVE = "interactive"
    BATCH = "batch"
    CI = "ci"
    CANARY = "canary"
    HOLDOUT = "holdout"


class IdentityDimension(_ValueEnum):
    TENANT = "tenant"
    AUTHORIZATION = "authorization"
    TRUST_NAMESPACE = "trust_namespace"
    PROVIDER = "provider"
    MODEL = "model"
    EFFORT = "effort"
    TOOL_SCHEMA = "tool_schema"
    PREFIX_COMPATIBILITY = "prefix_compatibility"
    PROMPT_SEGMENTS = "prompt_segments"
    PUBLIC_INTERFACE = "public_interface"
    RULE_PACK = "rule_pack"
    LOCKFILE = "lockfile"
    ENVIRONMENT = "environment"
    SHARD = "shard"
    VALIDATION = "validation"


@dataclass(frozen=True)
class ReasonDefinition:
    family: ReasonFamily
    allowed_outcomes: frozenset[CacheOutcome]
    consumes_unexpected_budget: bool = False


_HIT = frozenset({CacheOutcome.HIT})
_NECESSARY = frozenset({CacheOutcome.NECESSARY_MISS})
_UNEXPECTED = frozenset({CacheOutcome.UNEXPECTED_MISS})
_BYPASS = frozenset({CacheOutcome.BYPASS})
_RESTORE = frozenset({CacheOutcome.RESTORE_FAILURE})
_LOOKUP = frozenset({CacheOutcome.LOOKUP_ERROR})

REASON_DEFINITIONS: dict[CacheOutcomeReason, ReasonDefinition] = {
    CacheOutcomeReason.EXACT_RESULT_REUSED: ReasonDefinition(ReasonFamily.HIT, _HIT),
    CacheOutcomeReason.PROMPT_PREFIX_REUSED: ReasonDefinition(ReasonFamily.HIT, _HIT),
    CacheOutcomeReason.ARTIFACT_RESTORED: ReasonDefinition(ReasonFamily.HIT, _HIT),
    CacheOutcomeReason.COLD_NO_ENTRY: ReasonDefinition(ReasonFamily.COLD, _NECESSARY),
    CacheOutcomeReason.TENANT_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.AUTHORIZATION_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.TRUST_NAMESPACE_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.PROVIDER_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.MODEL_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.EFFORT_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.TOOL_SCHEMA_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED: ReasonDefinition(
        ReasonFamily.IDENTITY_CHANGED, _NECESSARY
    ),
    CacheOutcomeReason.PROMPT_SEGMENT_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.PUBLIC_INTERFACE_CHANGED: ReasonDefinition(
        ReasonFamily.IDENTITY_CHANGED, _NECESSARY
    ),
    CacheOutcomeReason.RULE_PACK_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.LOCKFILE_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.ENVIRONMENT_CHANGED: ReasonDefinition(ReasonFamily.IDENTITY_CHANGED, _NECESSARY),
    CacheOutcomeReason.VALIDATION_REQUIREMENT_CHANGED: ReasonDefinition(
        ReasonFamily.IDENTITY_CHANGED, _NECESSARY
    ),
    CacheOutcomeReason.TTL_EXPIRED: ReasonDefinition(ReasonFamily.TTL_OR_RETENTION, _NECESSARY),
    CacheOutcomeReason.CACHE_EVICTED: ReasonDefinition(
        ReasonFamily.CAPACITY_POLICY, _UNEXPECTED, consumes_unexpected_budget=True
    ),
    CacheOutcomeReason.WRONG_SHARD: ReasonDefinition(
        ReasonFamily.PLACEMENT, _UNEXPECTED, consumes_unexpected_budget=True
    ),
    CacheOutcomeReason.CAPACITY_EXHAUSTED: ReasonDefinition(
        ReasonFamily.CAPACITY_POLICY, frozenset({CacheOutcome.BYPASS, CacheOutcome.UNEXPECTED_MISS})
    ),
    CacheOutcomeReason.POLICY_BYPASS: ReasonDefinition(ReasonFamily.CAPACITY_POLICY, _BYPASS),
    CacheOutcomeReason.SNAPSHOT_REVOKED: ReasonDefinition(
        ReasonFamily.SECURITY, frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.RESTORE_FAILURE})
    ),
    CacheOutcomeReason.SNAPSHOT_CORRUPT: ReasonDefinition(
        ReasonFamily.CORRUPTION, _RESTORE, consumes_unexpected_budget=True
    ),
    CacheOutcomeReason.RESTORE_FAILED: ReasonDefinition(
        ReasonFamily.RESTORE, _RESTORE, consumes_unexpected_budget=True
    ),
    CacheOutcomeReason.RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE: ReasonDefinition(
        ReasonFamily.ECONOMIC_BYPASS, _BYPASS
    ),
    CacheOutcomeReason.TENANT_MISMATCH: ReasonDefinition(
        ReasonFamily.SECURITY, frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.BYPASS})
    ),
    CacheOutcomeReason.AUTHORIZATION_DENIED: ReasonDefinition(
        ReasonFamily.SECURITY, frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.BYPASS})
    ),
    CacheOutcomeReason.TRUST_NAMESPACE_MISMATCH: ReasonDefinition(
        ReasonFamily.SECURITY, frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.BYPASS})
    ),
    CacheOutcomeReason.CORRUPT_OBJECT: ReasonDefinition(
        ReasonFamily.CORRUPTION,
        frozenset({CacheOutcome.RESTORE_FAILURE, CacheOutcome.UNEXPECTED_MISS}),
        consumes_unexpected_budget=True,
    ),
    CacheOutcomeReason.PROVIDER_UNSUPPORTED: ReasonDefinition(
        ReasonFamily.UNSUPPORTED, frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.BYPASS})
    ),
    CacheOutcomeReason.BACKEND_UNAVAILABLE: ReasonDefinition(
        ReasonFamily.BACKEND, _LOOKUP, consumes_unexpected_budget=True
    ),
    CacheOutcomeReason.UNKNOWN_IDENTITY_CHANGE: ReasonDefinition(
        ReasonFamily.UNKNOWN,
        frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.UNEXPECTED_MISS}),
        consumes_unexpected_budget=True,
    ),
    CacheOutcomeReason.UNKNOWN_MISS: ReasonDefinition(
        ReasonFamily.UNKNOWN,
        frozenset({CacheOutcome.NECESSARY_MISS, CacheOutcome.UNEXPECTED_MISS}),
        consumes_unexpected_budget=True,
    ),
    CacheOutcomeReason.UNKNOWN_LOOKUP_ERROR: ReasonDefinition(
        ReasonFamily.UNKNOWN, _LOOKUP, consumes_unexpected_budget=True
    ),
}

DIMENSION_REASONS: dict[IdentityDimension, CacheOutcomeReason] = {
    IdentityDimension.TENANT: CacheOutcomeReason.TENANT_CHANGED,
    IdentityDimension.AUTHORIZATION: CacheOutcomeReason.AUTHORIZATION_CHANGED,
    IdentityDimension.TRUST_NAMESPACE: CacheOutcomeReason.TRUST_NAMESPACE_CHANGED,
    IdentityDimension.PROVIDER: CacheOutcomeReason.PROVIDER_CHANGED,
    IdentityDimension.MODEL: CacheOutcomeReason.MODEL_CHANGED,
    IdentityDimension.EFFORT: CacheOutcomeReason.EFFORT_CHANGED,
    IdentityDimension.TOOL_SCHEMA: CacheOutcomeReason.TOOL_SCHEMA_CHANGED,
    IdentityDimension.PREFIX_COMPATIBILITY: CacheOutcomeReason.PREFIX_COMPATIBILITY_CHANGED,
    IdentityDimension.PROMPT_SEGMENTS: CacheOutcomeReason.PROMPT_SEGMENT_CHANGED,
    IdentityDimension.PUBLIC_INTERFACE: CacheOutcomeReason.PUBLIC_INTERFACE_CHANGED,
    IdentityDimension.RULE_PACK: CacheOutcomeReason.RULE_PACK_CHANGED,
    IdentityDimension.LOCKFILE: CacheOutcomeReason.LOCKFILE_CHANGED,
    IdentityDimension.ENVIRONMENT: CacheOutcomeReason.ENVIRONMENT_CHANGED,
    IdentityDimension.SHARD: CacheOutcomeReason.WRONG_SHARD,
    IdentityDimension.VALIDATION: CacheOutcomeReason.VALIDATION_REQUIREMENT_CHANGED,
}


@dataclass(frozen=True)
class FirstDifference:
    dimension: IdentityDimension
    previous_digest: str
    current_digest: str
    reason: CacheOutcomeReason

    def to_dict(self) -> dict[str, str]:
        return {
            "dimension": self.dimension.value,
            "previous_digest": self.previous_digest,
            "current_digest": self.current_digest,
            "reason": self.reason.value,
        }


def first_difference(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> FirstDifference | None:
    """Find the first changed closed identity dimension, returning digests only."""

    allowed = {dimension.value for dimension in IdentityDimension}
    unknown = sorted((set(previous) | set(current)) - allowed)
    if unknown:
        raise ContractViolation("identity document contains unknown dimensions", dimensions=unknown)
    for dimension in IdentityDimension:
        before = previous.get(dimension.value)
        after = current.get(dimension.value)
        if before == after:
            continue
        try:
            before_digest = digest_of(before)
            after_digest = digest_of(after)
        except (TypeError, ValueError) as exc:
            raise ContractViolation(
                "identity dimension is not canonically serialisable",
                dimension=dimension.value,
            ) from exc
        return FirstDifference(
            dimension=dimension,
            previous_digest=before_digest,
            current_digest=after_digest,
            reason=DIMENSION_REASONS[dimension],
        )
    return None


@dataclass(frozen=True)
class CacheOutcomeEvent:
    layer: CacheLayer
    outcome: CacheOutcome
    reason: CacheOutcomeReason
    eligible: bool
    cohort: CacheCohort = CacheCohort.DEFAULT
    first_difference: FirstDifference | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.layer, CacheLayer):
            raise ContractViolation("cache layer must use the closed vocabulary")
        if not isinstance(self.outcome, CacheOutcome):
            raise ContractViolation("cache outcome must use the closed vocabulary")
        if not isinstance(self.reason, CacheOutcomeReason):
            raise ContractViolation("cache reason must use the closed vocabulary")
        if not isinstance(self.eligible, bool):
            raise ContractViolation("eligible must be boolean")
        if not isinstance(self.cohort, CacheCohort):
            raise ContractViolation("cache cohort must use the closed vocabulary")
        definition = REASON_DEFINITIONS[self.reason]
        if self.outcome not in definition.allowed_outcomes:
            raise ContractViolation(
                "cache reason is incompatible with terminal outcome",
                reason=self.reason.value,
                outcome=self.outcome.value,
            )
        if self.outcome is CacheOutcome.HIT and not self.eligible:
            raise ContractViolation("an ineligible request cannot be recorded as a cache hit")
        if self.first_difference is not None:
            expected = DIMENSION_REASONS[self.first_difference.dimension]
            if self.reason is not expected:
                raise ContractViolation(
                    "first difference does not match the terminal reason",
                    difference_reason=expected.value,
                    event_reason=self.reason.value,
                )

    @property
    def family(self) -> ReasonFamily:
        return REASON_DEFINITIONS[self.reason].family

    @property
    def consumes_unexpected_budget(self) -> bool:
        definition = REASON_DEFINITIONS[self.reason]
        return (
            definition.consumes_unexpected_budget
            or definition.family is ReasonFamily.UNKNOWN
            or self.outcome is CacheOutcome.UNEXPECTED_MISS
        )

    def metric_labels(self) -> dict[str, str]:
        """Bounded metric labels: no IDs, paths, prompts, or digests."""

        labels = {
            "layer": self.layer.value,
            "outcome": self.outcome.value,
            "reason": self.reason.value,
            "reason_family": self.family.value,
            "eligible": str(self.eligible).lower(),
            "cohort": self.cohort.value,
            "unexpected_budget": str(self.consumes_unexpected_budget).lower(),
        }
        if any(not _COHORT_IDENTIFIER.fullmatch(value) for key, value in labels.items() if key == "cohort"):
            raise ContractViolation("cohort is not a low-cardinality identifier")
        return labels

    def diagnostic(self) -> dict[str, Any]:
        return {
            "schema_version": OUTCOME_SCHEMA_VERSION,
            **self.metric_labels(),
            "first_difference": (
                None if self.first_difference is None else self.first_difference.to_dict()
            ),
        }


@dataclass
class UnexpectedMissBudget:
    """Small deterministic accumulator used by gates and dashboards."""

    eligible: int = 0
    consumed: int = 0
    unknown: int = 0

    def observe(self, event: CacheOutcomeEvent) -> None:
        if event.eligible:
            self.eligible += 1
        if event.consumes_unexpected_budget:
            self.consumed += 1
        if event.family is ReasonFamily.UNKNOWN:
            self.unknown += 1

    @property
    def rate(self) -> float:
        if self.eligible == 0:
            return 0.0
        return self.consumed / self.eligible

    def to_dict(self) -> dict[str, float | int]:
        return {
            "eligible": self.eligible,
            "consumed": self.consumed,
            "unknown": self.unknown,
            "rate": self.rate,
        }
