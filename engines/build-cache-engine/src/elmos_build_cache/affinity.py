"""Compatibility-first cache affinity routing.

Routing has two deliberately separate phases:

1. authorization, trust, provider/model/tool/prefix/platform, health, and
   capacity are hard filters;
2. compatible targets are ranked by verified cache value minus operational
   penalties.

Locality can therefore turn a possible hit into a real hit, but can never make
an incompatible or unauthorized worker eligible.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .canonical import canonical_json_bytes, digest_of, require_digest
from .errors import ContractViolation, PermissionDenied
from .prompt_cache import PromptProvider
from .security import ProvenanceSigner, SignedStatement, require_asymmetric

AFFINITY_SCHEMA_VERSION = "elmos.cache-affinity/v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")


class _ValueEnum(StrEnum):
    pass


class TargetHealth(_ValueEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    DRAINING = "DRAINING"


class HardRejection(_ValueEnum):
    TENANT_MISMATCH = "TENANT_MISMATCH"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    AUTHORIZATION_SCOPE_MISMATCH = "AUTHORIZATION_SCOPE_MISMATCH"
    TRUST_NAMESPACE_MISMATCH = "TRUST_NAMESPACE_MISMATCH"
    PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    EFFORT_MISMATCH = "EFFORT_MISMATCH"
    TOOL_SCHEMA_MISMATCH = "TOOL_SCHEMA_MISMATCH"
    PREFIX_COMPATIBILITY_MISMATCH = "PREFIX_COMPATIBILITY_MISMATCH"
    PLATFORM_MISMATCH = "PLATFORM_MISMATCH"
    INSUFFICIENT_CAPACITY = "INSUFFICIENT_CAPACITY"
    TARGET_NOT_HEALTHY = "TARGET_NOT_HEALTHY"


class RoutingReason(_ValueEnum):
    PREFIX_LOCAL = "PREFIX_LOCAL"
    ENVIRONMENT_LOCAL = "ENVIRONMENT_LOCAL"
    ARTIFACT_LOCAL = "ARTIFACT_LOCAL"
    DAG_LOCAL = "DAG_LOCAL"
    BALANCED_SCORE = "BALANCED_SCORE"
    NO_COMPATIBLE_TARGET = "NO_COMPATIBLE_TARGET"


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field} must be a bounded identifier", field=field)
    return value


def _non_negative(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be numeric", field=field)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContractViolation(f"{field} must be finite and non-negative", field=field)
    return number


@dataclass(frozen=True)
class AffinityRequest:
    tenant_scope_digest: str
    authorization_scope_digest: str
    trust_namespace: str
    provider: PromptProvider
    model: str
    effort_profile: str
    tool_schema_digest: str
    prefix_compatibility_digest: str
    platform_digest: str
    required_capacity: int

    def __post_init__(self) -> None:
        require_digest(self.tenant_scope_digest)
        require_digest(self.authorization_scope_digest)
        _identifier(self.trust_namespace, "trust_namespace")
        if not isinstance(self.provider, PromptProvider):
            raise ContractViolation("provider must use the closed vocabulary")
        _identifier(self.model, "model")
        _identifier(self.effort_profile, "effort_profile")
        require_digest(self.tool_schema_digest)
        require_digest(self.prefix_compatibility_digest)
        require_digest(self.platform_digest)
        if (
            isinstance(self.required_capacity, bool)
            or not isinstance(self.required_capacity, int)
            or self.required_capacity < 1
        ):
            raise ContractViolation("required_capacity must be a positive integer")

    @property
    def affinity_key(self) -> str:
        return digest_of(
            {
                "schema_version": AFFINITY_SCHEMA_VERSION,
                "tenant_scope_digest": self.tenant_scope_digest,
                "authorization_scope_digest": self.authorization_scope_digest,
                "trust_namespace": self.trust_namespace,
                "provider": self.provider.value,
                "model": self.model,
                "effort_profile": self.effort_profile,
                "tool_schema_digest": self.tool_schema_digest,
                "prefix_compatibility_digest": self.prefix_compatibility_digest,
                "platform_digest": self.platform_digest,
            }
        )


@dataclass(frozen=True)
class AffinityCandidate:
    target_id: str
    tenant_scope_digest: str
    authorization_scope_digest: str
    authorized: bool
    trust_namespace: str
    provider: PromptProvider
    model: str
    effort_profile: str
    tool_schema_digest: str
    prefix_compatibility_digest: str
    platform_digest: str
    available_capacity: int
    health: TargetHealth
    prompt_cache_value_ms: float = 0.0
    environment_value_ms: float = 0.0
    artifact_value_ms: float = 0.0
    dag_next_use_value_ms: float = 0.0
    queue_delay_ms: float = 0.0
    transfer_cost_ms: float = 0.0
    failure_penalty_ms: float = 0.0
    fairness_debt_ms: float = 0.0

    def __post_init__(self) -> None:
        _identifier(self.target_id, "target_id")
        require_digest(self.tenant_scope_digest)
        require_digest(self.authorization_scope_digest)
        if not isinstance(self.authorized, bool):
            raise ContractViolation("authorized must be boolean")
        _identifier(self.trust_namespace, "trust_namespace")
        if not isinstance(self.provider, PromptProvider):
            raise ContractViolation("provider must use the closed vocabulary")
        _identifier(self.model, "model")
        _identifier(self.effort_profile, "effort_profile")
        require_digest(self.tool_schema_digest)
        require_digest(self.prefix_compatibility_digest)
        require_digest(self.platform_digest)
        if (
            isinstance(self.available_capacity, bool)
            or not isinstance(self.available_capacity, int)
            or self.available_capacity < 0
        ):
            raise ContractViolation("available_capacity must be a non-negative integer")
        if not isinstance(self.health, TargetHealth):
            raise ContractViolation("health must use the closed vocabulary")
        for field in (
            "prompt_cache_value_ms",
            "environment_value_ms",
            "artifact_value_ms",
            "dag_next_use_value_ms",
            "queue_delay_ms",
            "transfer_cost_ms",
            "failure_penalty_ms",
            "fairness_debt_ms",
        ):
            object.__setattr__(self, field, _non_negative(getattr(self, field), field))

    def hard_rejections(self, request: AffinityRequest) -> tuple[HardRejection, ...]:
        reasons: list[HardRejection] = []
        if self.tenant_scope_digest != request.tenant_scope_digest:
            reasons.append(HardRejection.TENANT_MISMATCH)
        if not self.authorized:
            reasons.append(HardRejection.AUTHORIZATION_DENIED)
        if self.authorization_scope_digest != request.authorization_scope_digest:
            reasons.append(HardRejection.AUTHORIZATION_SCOPE_MISMATCH)
        if self.trust_namespace != request.trust_namespace:
            reasons.append(HardRejection.TRUST_NAMESPACE_MISMATCH)
        if self.provider is not request.provider:
            reasons.append(HardRejection.PROVIDER_MISMATCH)
        if self.model != request.model:
            reasons.append(HardRejection.MODEL_MISMATCH)
        if self.effort_profile != request.effort_profile:
            reasons.append(HardRejection.EFFORT_MISMATCH)
        if self.tool_schema_digest != request.tool_schema_digest:
            reasons.append(HardRejection.TOOL_SCHEMA_MISMATCH)
        if self.prefix_compatibility_digest != request.prefix_compatibility_digest:
            reasons.append(HardRejection.PREFIX_COMPATIBILITY_MISMATCH)
        if self.platform_digest != request.platform_digest:
            reasons.append(HardRejection.PLATFORM_MISMATCH)
        if self.available_capacity < request.required_capacity:
            reasons.append(HardRejection.INSUFFICIENT_CAPACITY)
        if self.health is not TargetHealth.HEALTHY:
            reasons.append(HardRejection.TARGET_NOT_HEALTHY)
        return tuple(reasons)

    def attestation_document(self) -> dict[str, Any]:
        """Closed runner state signed by the inventory authority."""

        return {
            "target_id": self.target_id,
            "tenant_scope_digest": self.tenant_scope_digest,
            "authorization_scope_digest": self.authorization_scope_digest,
            "authorized": self.authorized,
            "trust_namespace": self.trust_namespace,
            "provider": self.provider.value,
            "model": self.model,
            "effort_profile": self.effort_profile,
            "tool_schema_digest": self.tool_schema_digest,
            "prefix_compatibility_digest": self.prefix_compatibility_digest,
            "platform_digest": self.platform_digest,
            "available_capacity": self.available_capacity,
            "health": self.health.value,
            "prompt_cache_value_ms": self.prompt_cache_value_ms,
            "environment_value_ms": self.environment_value_ms,
            "artifact_value_ms": self.artifact_value_ms,
            "dag_next_use_value_ms": self.dag_next_use_value_ms,
            "queue_delay_ms": self.queue_delay_ms,
            "transfer_cost_ms": self.transfer_cost_ms,
            "failure_penalty_ms": self.failure_penalty_ms,
            "fairness_debt_ms": self.fairness_debt_ms,
        }


@dataclass(frozen=True)
class AttestedAffinityCandidate:
    """Server-owned runner inventory record; never accepted from request JSON."""

    tenant_id: str
    project_id: str
    candidate: AffinityCandidate
    attestation_digest: str
    verifier_identity: str
    attested_at: float
    expires_at: float
    signed_attestation: SignedStatement
    revoked: bool = False

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.attestation_digest)
        _identifier(self.verifier_identity, "verifier_identity")
        if (
            isinstance(self.attested_at, bool)
            or isinstance(self.expires_at, bool)
            or not isinstance(self.attested_at, int | float)
            or not isinstance(self.expires_at, int | float)
            or not math.isfinite(float(self.attested_at))
            or not math.isfinite(float(self.expires_at))
            or self.attested_at < 0
            or self.expires_at <= self.attested_at
        ):
            raise ContractViolation("runner attestation lifetime is invalid")
        if not self.candidate.authorized:
            raise ContractViolation("attested runner candidate must be policy-authorized")
        if not isinstance(self.signed_attestation, SignedStatement):
            raise ContractViolation("runner attestation must be a signed statement")
        if self.signed_attestation.key_id != self.verifier_identity:
            raise ContractViolation("runner attestation verifier identity does not match its key")
        if digest_of(self.signed_attestation.to_dict()) != self.attestation_digest:
            raise ContractViolation("runner attestation digest does not match the signed bytes")
        expected = self.unsigned_statement()
        if (
            self.signed_attestation.kind != "elmos.cache-affinity-runner-attestation/v1.2"
            or self.signed_attestation.statement != expected
        ):
            raise ContractViolation("runner attestation statement does not match the candidate")

    def unsigned_statement(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "candidate": self.candidate.attestation_document(),
            "attested_at": self.attested_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class AffinityAuthorizationContext:
    """Trusted PIP/PDP result; never reconstructed from request JSON."""

    tenant_id: str
    project_id: str
    principal_digest: str
    authorization_scope_digest: str
    allowed: bool

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.principal_digest)
        require_digest(self.authorization_scope_digest)
        if not isinstance(self.allowed, bool):
            raise ContractViolation("affinity authorization decision must be boolean")


class AffinityAuthorizationResolver(Protocol):
    """Resolve the authenticated subject's exact project routing scope."""

    def resolve(
        self,
        principal_digest: str,
        tenant_id: str,
        project_id: str,
        request_id: str,
    ) -> AffinityAuthorizationContext: ...


class StaticAffinityAuthorizationResolver:
    """Immutable deployment/test adapter for pre-authorized project scopes."""

    def __init__(
        self,
        contexts: Mapping[tuple[str, str, str], AffinityAuthorizationContext],
    ) -> None:
        self._contexts = dict(contexts)

    def resolve(
        self,
        principal_digest: str,
        tenant_id: str,
        project_id: str,
        request_id: str,
    ) -> AffinityAuthorizationContext:
        require_digest(principal_digest)
        _identifier(request_id, "request_id")
        try:
            context = self._contexts[(principal_digest, tenant_id, project_id)]
        except KeyError as exc:
            raise PermissionDenied("affinity routing is not authorized for this principal") from exc
        if (
            context.principal_digest != principal_digest
            or context.tenant_id != tenant_id
            or context.project_id != project_id
        ):
            raise PermissionDenied("affinity authorization context scope mismatch")
        return context


class AttestedAffinityRegistry:
    """Immutable host-supplied runner inventory with expiry/revocation fences."""

    def __init__(
        self,
        records: Iterable[AttestedAffinityCandidate],
        *,
        trust_verifier: ProvenanceSigner,
        revoked_attestation_digests: Iterable[str] = (),
    ) -> None:
        require_asymmetric(trust_verifier)
        supplied = tuple(records)
        revoked = frozenset(require_digest(item) for item in revoked_attestation_digests)
        identities = [
            (item.tenant_id, item.project_id, item.candidate.target_id) for item in supplied
        ]
        if len(identities) != len(set(identities)):
            raise ContractViolation("runner registry contains duplicate scoped target IDs")
        for record in supplied:
            trust_verifier.verify_statement(record.signed_attestation)
        self._records = supplied
        self._revoked_attestation_digests = revoked

    def candidates(
        self,
        tenant_id: str,
        project_id: str,
        request: AffinityRequest,
        now: float,
    ) -> tuple[AffinityCandidate, ...]:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        if now < 0:
            raise ContractViolation("runner registry time cannot be negative")
        return tuple(
            record.candidate
            for record in self._records
            if record.tenant_id == tenant_id
            and record.project_id == project_id
            and not record.revoked
            and record.attestation_digest not in self._revoked_attestation_digests
            and record.attested_at <= now < record.expires_at
            and record.candidate.tenant_scope_digest == request.tenant_scope_digest
            and record.candidate.authorization_scope_digest
            == request.authorization_scope_digest
        )


@dataclass(frozen=True)
class CandidateScore:
    target_id: str
    prompt_cache_value_ms: float
    environment_value_ms: float
    artifact_value_ms: float
    dag_next_use_value_ms: float
    queue_delay_ms: float
    transfer_cost_ms: float
    failure_penalty_ms: float
    fairness_debt_ms: float
    total_ms: float
    rendezvous_rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "value": {
                "prompt_cache_ms": self.prompt_cache_value_ms,
                "environment_ms": self.environment_value_ms,
                "artifact_ms": self.artifact_value_ms,
                "dag_next_use_ms": self.dag_next_use_value_ms,
            },
            "penalty": {
                "queue_delay_ms": self.queue_delay_ms,
                "transfer_cost_ms": self.transfer_cost_ms,
                "failure_penalty_ms": self.failure_penalty_ms,
                "fairness_debt_ms": self.fairness_debt_ms,
            },
            "total_ms": self.total_ms,
            "rendezvous_rank": self.rendezvous_rank,
        }


def _rendezvous_rank(affinity_key: str, target_id: str) -> int:
    payload = canonical_json_bytes(
        {
            "schema_version": AFFINITY_SCHEMA_VERSION,
            "affinity_key": affinity_key,
            "target_id": target_id,
        }
    )
    return int.from_bytes(hashlib.sha256(payload).digest(), byteorder="big", signed=False)


def score_candidate(request: AffinityRequest, candidate: AffinityCandidate) -> CandidateScore:
    rejections = candidate.hard_rejections(request)
    if rejections:
        raise ContractViolation(
            "cannot score an incompatible affinity candidate",
            target_id=candidate.target_id,
            reasons=[reason.value for reason in rejections],
        )
    gain = (
        candidate.prompt_cache_value_ms
        + candidate.environment_value_ms
        + candidate.artifact_value_ms
        + candidate.dag_next_use_value_ms
    )
    penalty = (
        candidate.queue_delay_ms
        + candidate.transfer_cost_ms
        + candidate.failure_penalty_ms
        + candidate.fairness_debt_ms
    )
    return CandidateScore(
        target_id=candidate.target_id,
        prompt_cache_value_ms=candidate.prompt_cache_value_ms,
        environment_value_ms=candidate.environment_value_ms,
        artifact_value_ms=candidate.artifact_value_ms,
        dag_next_use_value_ms=candidate.dag_next_use_value_ms,
        queue_delay_ms=candidate.queue_delay_ms,
        transfer_cost_ms=candidate.transfer_cost_ms,
        failure_penalty_ms=candidate.failure_penalty_ms,
        fairness_debt_ms=candidate.fairness_debt_ms,
        total_ms=round(gain - penalty, 6),
        rendezvous_rank=_rendezvous_rank(request.affinity_key, candidate.target_id),
    )


@dataclass(frozen=True)
class AffinityDecision:
    affinity_key: str
    selected_target: str | None
    reason: RoutingReason
    compatible_targets: int
    rejected_targets: int
    rejection_counts: tuple[tuple[str, int], ...]
    scores: tuple[CandidateScore, ...]

    def __post_init__(self) -> None:
        require_digest(self.affinity_key)

    @property
    def selected_score(self) -> CandidateScore | None:
        if self.selected_target is None:
            return None
        return next(score for score in self.scores if score.target_id == self.selected_target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AFFINITY_SCHEMA_VERSION,
            "affinity_key": self.affinity_key,
            "selected_target": self.selected_target,
            "reason": self.reason.value,
            "compatible_targets": self.compatible_targets,
            "rejected_targets": self.rejected_targets,
            "rejection_counts": dict(self.rejection_counts),
            "scores": [score.to_dict() for score in self.scores],
        }


def _selection_reason(candidate: AffinityCandidate) -> RoutingReason:
    values = (
        (candidate.prompt_cache_value_ms, RoutingReason.PREFIX_LOCAL),
        (candidate.environment_value_ms, RoutingReason.ENVIRONMENT_LOCAL),
        (candidate.artifact_value_ms, RoutingReason.ARTIFACT_LOCAL),
        (candidate.dag_next_use_value_ms, RoutingReason.DAG_LOCAL),
    )
    best_value, best_reason = max(values, key=lambda item: (item[0], item[1].value))
    return best_reason if best_value > 0 else RoutingReason.BALANCED_SCORE


def route_affinity(
    request: AffinityRequest,
    candidates: Iterable[AffinityCandidate],
) -> AffinityDecision:
    supplied = tuple(candidates)
    ids = [candidate.target_id for candidate in supplied]
    if len(ids) != len(set(ids)):
        raise ContractViolation("affinity candidate target IDs must be unique")

    compatible: list[AffinityCandidate] = []
    rejected = 0
    rejection_counter: Counter[str] = Counter()
    for candidate in supplied:
        reasons = candidate.hard_rejections(request)
        if reasons:
            rejected += 1
            rejection_counter.update(reason.value for reason in reasons)
        else:
            compatible.append(candidate)

    if not compatible:
        return AffinityDecision(
            affinity_key=request.affinity_key,
            selected_target=None,
            reason=RoutingReason.NO_COMPATIBLE_TARGET,
            compatible_targets=0,
            rejected_targets=rejected,
            rejection_counts=tuple(sorted(rejection_counter.items())),
            scores=(),
        )

    scores = tuple(score_candidate(request, candidate) for candidate in compatible)
    selected_score = max(scores, key=lambda item: (item.total_ms, item.rendezvous_rank, item.target_id))
    selected_candidate = next(
        candidate for candidate in compatible if candidate.target_id == selected_score.target_id
    )
    ordered_scores = tuple(
        sorted(
            scores,
            key=lambda item: (item.total_ms, item.rendezvous_rank, item.target_id),
            reverse=True,
        )
    )
    return AffinityDecision(
        affinity_key=request.affinity_key,
        selected_target=selected_candidate.target_id,
        reason=_selection_reason(selected_candidate),
        compatible_targets=len(compatible),
        rejected_targets=rejected,
        rejection_counts=tuple(sorted(rejection_counter.items())),
        scores=ordered_scores,
    )
