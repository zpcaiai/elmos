"""Cost-aware admission: what an object is worth, not how often it was touched.

Object hit ratio is the wrong sole objective for ELMOS and optimising it alone
actively hurts. A 6 KB manifest that rebuilds in 3 ms and a 96 KB generated file
that cost 15 000 model tokens and eight seconds are one hit each. A cache that
maximises hit count will happily evict the second to keep a hundred of the
first, and the build gets slower while the dashboard gets greener.

So admission here is driven by an explicit value function::

    CacheValue = P(reuse) × (avoided_work + critical_path + validation_value)
               - storage_cost - restore_cost - pollution_risk - trust_risk

with three properties that make it safe to run in production:

1. **Costs are versioned and separated.** Every component is tagged `observed`,
   `predicted` or `fallback`. A number nobody measured is never silently
   presented as a measurement.
2. **Validation raises value, never authority.** A `PRODUCTION_CERTIFIED`
   artifact is worth more to keep. It is not thereby more reusable -- that is
   decided by the correctness plane before this module is consulted.
3. **Determinism.** For a fixed policy state and input, the decision and its
   explanation are the same every time.

Tenant quotas and stage reservations sit on top: a burst from one tenant cannot
take the whole shared cache, and active-run state has a protected floor that no
value comparison can touch.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cache_policy import CacheObject, CachePolicy, Decision
from .canonical import digest_of

SCHEMA_VERSION = "1.1.0"


class CostSource(str, Enum):
    """Where a number came from. Never inferred, always recorded."""

    OBSERVED = "OBSERVED"
    PREDICTED = "PREDICTED"
    FALLBACK = "FALLBACK"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


#: Retention value of a validation level, relative to an unverified artifact.
#: Re-earning a `TEST_VERIFIED` result costs a test run, so it is worth keeping.
VALIDATION_VALUE: dict[str, float] = {
    "QUARANTINED": 0.0,
    "UNVERIFIED": 1.0,
    "COMPILE_VERIFIED": 1.2,
    "TEST_VERIFIED": 1.6,
    "BEHAVIOR_VERIFIED": 1.8,
    "PRODUCTION_CERTIFIED": 2.0,
}

#: Cost of a millisecond of model time relative to a millisecond of CPU, and of
#: a model token. Deployment-tunable; versioned with the policy configuration.
DEFAULT_TOKEN_MS = 0.35
DEFAULT_STORAGE_MS_PER_MB = 0.4
DEFAULT_POLLUTION_MS_PER_MB = 0.25


@dataclass(frozen=True)
class CostModel:
    """The prices this deployment puts on time, tokens, bytes and risk."""

    token_ms: float = DEFAULT_TOKEN_MS
    storage_ms_per_mb: float = DEFAULT_STORAGE_MS_PER_MB
    pollution_ms_per_mb: float = DEFAULT_POLLUTION_MS_PER_MB
    critical_path_multiplier: float = 1.5
    trust_risk_ms: float = 0.0
    version: str = "cost-model/1.1.0"

    def digest(self) -> str:
        return digest_of(
            {
                "version": self.version,
                "token_ms": self.token_ms,
                "storage_ms_per_mb": self.storage_ms_per_mb,
                "pollution_ms_per_mb": self.pollution_ms_per_mb,
                "critical_path_multiplier": self.critical_path_multiplier,
                "trust_risk_ms": self.trust_risk_ms,
            }
        )


@dataclass
class ReuseEstimator:
    """P(reuse within the horizon), from what has actually been seen.

    Deliberately a counting estimator rather than a model: it is on the write
    path, it must be bounded, and a wrong probability here should cost a little
    performance rather than a correctness incident. Learned refinement lives in
    the control plane, off this path.
    """

    horizon: int = 4096
    prior: float = 0.25
    _seen: dict[str, int] = field(default_factory=dict)
    _reused: dict[str, int] = field(default_factory=dict)
    _stage_seen: dict[str, int] = field(default_factory=dict)
    _stage_reused: dict[str, int] = field(default_factory=dict)

    def observe(self, key: str, stage_class: str, *, reused: bool) -> None:
        self._seen[key] = self._seen.get(key, 0) + 1
        self._stage_seen[stage_class] = self._stage_seen.get(stage_class, 0) + 1
        if reused:
            self._reused[key] = self._reused.get(key, 0) + 1
            self._stage_reused[stage_class] = self._stage_reused.get(stage_class, 0) + 1

    def probability(self, obj: CacheObject) -> tuple[float, CostSource]:
        if obj.next_use_distance is not None:
            # The DAG says this object has a consumer. That is knowledge, not a
            # guess, and it is recorded as such.
            return (1.0 if obj.next_use_distance <= self.horizon else 0.0), CostSource.OBSERVED
        seen = self._seen.get(obj.key, 0)
        if seen:
            return min(self._reused.get(obj.key, 0) / seen, 1.0), CostSource.OBSERVED
        stage_seen = self._stage_seen.get(obj.stage_class, 0)
        if stage_seen >= 8:
            return min(self._stage_reused.get(obj.stage_class, 0) / stage_seen, 1.0), CostSource.PREDICTED
        return self.prior, CostSource.FALLBACK


@dataclass(frozen=True)
class ValueBreakdown:
    """Every term of the objective, so a decision can be explained term by term."""

    reuse_probability: float
    reuse_source: str
    avoided_work_ms: float
    critical_path_ms: float
    validation_value: float
    storage_cost_ms: float
    restore_cost_ms: float
    pollution_cost_ms: float
    trust_risk_ms: float

    @property
    def value(self) -> float:
        gain = self.reuse_probability * (
            self.avoided_work_ms + self.critical_path_ms + self.validation_value
        )
        return round(
            gain - self.storage_cost_ms - self.restore_cost_ms - self.pollution_cost_ms - self.trust_risk_ms,
            6,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reuse_probability": round(self.reuse_probability, 6),
            "reuse_source": self.reuse_source,
            "avoided_work_ms": round(self.avoided_work_ms, 6),
            "critical_path_ms": round(self.critical_path_ms, 6),
            "validation_value": round(self.validation_value, 6),
            "storage_cost_ms": round(self.storage_cost_ms, 6),
            "restore_cost_ms": round(self.restore_cost_ms, 6),
            "pollution_cost_ms": round(self.pollution_cost_ms, 6),
            "trust_risk_ms": round(self.trust_risk_ms, 6),
            "value": self.value,
        }


@dataclass(frozen=True)
class TenantQuota:
    """A tenant's share, and the floor nobody can take from it."""

    tenant_hash: str
    maximum_bytes: int
    reserved_bytes: int = 0
    burst_bytes: int = 0

    def ceiling(self) -> int:
        return self.maximum_bytes + self.burst_bytes


@dataclass(frozen=True)
class AdmissionDecision:
    """What the controller decided, and every reason it decided it."""

    admitted: bool
    reasons: tuple[str, ...]
    breakdown: ValueBreakdown
    evicted: tuple[str, ...] = ()
    quota_used_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "reasons": list(self.reasons),
            "evicted": list(self.evicted),
            "quota_used_bytes": self.quota_used_bytes,
            "value": self.breakdown.to_dict(),
        }


class AdmissionReason(str, Enum):
    ADMITTED_BY_VALUE = "ADMITTED_BY_VALUE"
    REJECTED_NEGATIVE_VALUE = "REJECTED_NEGATIVE_VALUE"
    REJECTED_TENANT_QUOTA = "REJECTED_TENANT_QUOTA"
    ADMITTED_WITHIN_RESERVATION = "ADMITTED_WITHIN_RESERVATION"
    ADMITTED_PROTECTED = "ADMITTED_PROTECTED"
    REJECTED_BY_POLICY = "REJECTED_BY_POLICY"
    BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE = "BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class AdmissionController:
    """Value-based admission in front of a replacement policy.

    The policy decides *who leaves*; this decides *who may come in at all*, and
    it is the layer that knows about money, model tokens, tenants and the
    critical path. Keeping them separate means a deployment can change its
    objective without touching a single eviction algorithm.
    """

    def __init__(
        self,
        policy: CachePolicy,
        cost_model: CostModel | None = None,
        estimator: ReuseEstimator | None = None,
        quotas: Sequence[TenantQuota] = (),
        bypass_ratio: float = 0.9,
    ) -> None:
        self.policy = policy
        self.cost_model = cost_model or CostModel()
        self.estimator = estimator or ReuseEstimator()
        self.quotas = {quota.tenant_hash: quota for quota in quotas}
        self.bypass_ratio = bypass_ratio
        self.tenant_bytes: dict[str, int] = {}
        self.decisions: list[AdmissionDecision] = []
        self.rejected_by_quota = 0
        self.rejected_by_value = 0
        self.admitted = 0

    # -- the objective ----------------------------------------------------
    def evaluate(self, obj: CacheObject) -> ValueBreakdown:
        probability, source = self.estimator.probability(obj)
        megabytes = obj.size_bytes / 1_000_000
        avoided = obj.net_recompute_ms + obj.model_tokens * self.cost_model.token_ms
        return ValueBreakdown(
            reuse_probability=probability,
            reuse_source=source.value,
            avoided_work_ms=avoided,
            critical_path_ms=obj.critical_path_weight * obj.net_recompute_ms * self.cost_model.critical_path_multiplier,
            validation_value=VALIDATION_VALUE.get(obj.validation_level, 1.0),
            storage_cost_ms=megabytes * self.cost_model.storage_ms_per_mb,
            restore_cost_ms=obj.restore_ms,
            pollution_cost_ms=megabytes * self.cost_model.pollution_ms_per_mb,
            trust_risk_ms=self.cost_model.trust_risk_ms if obj.validation_level == "QUARANTINED" else 0.0,
        )

    # -- the decision -----------------------------------------------------
    def admit(self, obj: CacheObject) -> AdmissionDecision:
        breakdown = self.evaluate(obj)
        reasons: list[str] = []

        if self.policy.is_protected(obj.key):
            decision = self.policy.put(obj)
            reasons.append(AdmissionReason.ADMITTED_PROTECTED.value)
            return self._record(obj, True, reasons, breakdown, decision)

        if obj.restore_ms > obj.recompute_ms * self.bypass_ratio and obj.next_use_distance is None:
            # Keeping this costs more to fetch back than to rebuild from scratch.
            reasons.append(AdmissionReason.BYPASS_RESTORE_SLOWER_THAN_RECOMPUTE.value)
            self.rejected_by_value += 1
            return self._record(obj, False, reasons, breakdown, None)

        quota = self.quotas.get(obj.tenant_hash)
        used = self.tenant_bytes.get(obj.tenant_hash, 0)
        if quota is not None and used + obj.size_bytes > quota.ceiling():
            reasons.append(AdmissionReason.REJECTED_TENANT_QUOTA.value)
            self.rejected_by_quota += 1
            return self._record(obj, False, reasons, breakdown, None)

        within_reservation = quota is not None and used + obj.size_bytes <= quota.reserved_bytes
        if breakdown.value <= 0 and not within_reservation:
            reasons.append(AdmissionReason.REJECTED_NEGATIVE_VALUE.value)
            self.rejected_by_value += 1
            return self._record(obj, False, reasons, breakdown, None)

        decision = self.policy.put(obj)
        if not decision.admitted:
            reasons.extend(decision.reasons or (AdmissionReason.REJECTED_BY_POLICY.value,))
            return self._record(obj, False, reasons, breakdown, decision)

        reasons.append(
            AdmissionReason.ADMITTED_WITHIN_RESERVATION.value
            if within_reservation
            else AdmissionReason.ADMITTED_BY_VALUE.value
        )
        self.admitted += 1
        return self._record(obj, True, reasons, breakdown, decision)

    def _record(
        self,
        obj: CacheObject,
        admitted: bool,
        reasons: list[str],
        breakdown: ValueBreakdown,
        policy_decision: Decision | None,
    ) -> AdmissionDecision:
        evicted = tuple(policy_decision.evicted) if policy_decision else ()
        if admitted:
            self.tenant_bytes[obj.tenant_hash] = self.tenant_bytes.get(obj.tenant_hash, 0) + obj.size_bytes
        for key in evicted:
            # Freed bytes come back to whoever held them; without this a tenant
            # that churns would keep paying for objects it no longer has.
            self.tenant_bytes[obj.tenant_hash] = max(
                self.tenant_bytes.get(obj.tenant_hash, 0) - self._size_of(key), 0
            )
        decision = AdmissionDecision(
            admitted=admitted,
            reasons=tuple(reasons),
            breakdown=breakdown,
            evicted=evicted,
            quota_used_bytes=self.tenant_bytes.get(obj.tenant_hash, 0),
        )
        self.decisions.append(decision)
        return decision

    def _size_of(self, key: str) -> int:
        explanation = self.policy.explain(key)
        return int(explanation.get("size_bytes", 0) or 0)

    def observe_access(self, obj: CacheObject, *, hit: bool) -> None:
        """Feed the reuse estimator with what actually happened."""
        self.estimator.observe(obj.key, obj.stage_class, reused=hit)

    def stats(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "rejected_by_value": self.rejected_by_value,
            "rejected_by_quota": self.rejected_by_quota,
            "tenants": len(self.tenant_bytes),
            "cost_model": self.cost_model.digest(),
            "policy": self.policy.name.value,
        }

    def explain(self, obj: CacheObject) -> dict[str, Any]:
        """A dry run: what would happen and why, without changing anything."""
        breakdown = self.evaluate(obj)
        quota = self.quotas.get(obj.tenant_hash)
        used = self.tenant_bytes.get(obj.tenant_hash, 0)
        return {
            "key": obj.key,
            "value": breakdown.to_dict(),
            "quota": None
            if quota is None
            else {
                "used_bytes": used,
                "maximum_bytes": quota.maximum_bytes,
                "reserved_bytes": quota.reserved_bytes,
                "ceiling_bytes": quota.ceiling(),
            },
            "would_admit": breakdown.value > 0
            and (quota is None or used + obj.size_bytes <= quota.ceiling()),
            "policy": self.policy.name.value,
            "cost_model": self.cost_model.version,
        }
