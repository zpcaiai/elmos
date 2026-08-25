"""Choosing a policy, and being able to defend the choice afterwards.

No fixed policy wins everywhere -- the benchmarks in this repository show SIEVE
winning a monorepo scan, GDSF winning on expensive sparse reuse and plain LRU
holding its own on a uniform multi-tenant burst. So the interesting question is
not "which policy" but "which policy *now*, and how do we change our mind
safely".

The selector answers it from a compact workload fingerprint that is computed
off the hit path from counters the cache already keeps. It is deliberately
rule-based first: the rules are readable, their reasons are printable, and they
cannot fail in a way an operator cannot follow. A learned selector may later
choose among the same fixed experts (see `learned_control`), but it selects
among policies -- it never becomes one.

Everything expensive about switching is handled here rather than wished away:

- **Hysteresis and dwell.** A policy is not replaced unless the candidate is
  better by a margin and the incumbent has been in place for a minimum time.
  Oscillation costs more than either policy's difference.
- **Safe epochs.** Switches happen at epoch boundaries with an explicit state
  decision -- migrate the frequency history, or reset it and say so.
- **Shadow first.** Candidates can be fed the same request stream without
  authority over the real cache, so a comparison exists *before* the switch.
- **Fallback is pinned.** Low confidence, out-of-distribution features, drift,
  or missing telemetry select the pinned fixed policy, not the next best guess.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cache_policy import CachePolicy, PolicyName, create_policy, restore_policy
from .cache_simulator import ObjectiveProfile
from .cache_trace import CacheTraceEvent, workload_features
from .canonical import digest_of

SCHEMA_VERSION = "1.1.0"

#: What the selector falls back to when it does not know. SIEVE rather than
#: LRU: it is no more complex, and it does not collapse on a scan.
PINNED_FALLBACK = PolicyName.SIEVE


class SelectionReason(str, Enum):
    ONE_HIT_HEAVY = "ONE_HIT_HEAVY"
    HIGH_TEMPORAL_REUSE = "HIGH_TEMPORAL_REUSE"
    HETEROGENEOUS_SIZE = "HETEROGENEOUS_SIZE"
    EXPENSIVE_SPARSE_REUSE = "EXPENSIVE_SPARSE_REUSE"
    KNOWN_FUTURE = "KNOWN_FUTURE"
    UNIFORM_WORKLOAD = "UNIFORM_WORKLOAD"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    TELEMETRY_DEGRADED = "TELEMETRY_DEGRADED"
    STRONG_FIXED_FALLBACK = "STRONG_FIXED_FALLBACK"
    WITHIN_DWELL_TIME = "WITHIN_DWELL_TIME"
    IMPROVEMENT_BELOW_MARGIN = "IMPROVEMENT_BELOW_MARGIN"
    SHADOW_EVIDENCE = "SHADOW_EVIDENCE"
    OPERATOR_PINNED = "OPERATOR_PINNED"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(frozen=True)
class Selection:
    """A recommendation, with everything needed to argue about it later."""

    policy: str
    confidence: float
    reason_codes: tuple[str, ...]
    features: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "confidence": round(self.confidence, 6),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class PolicyEpoch:
    """One period during which one policy had authority over one tier.

    Serialises to the package's ``cache-policy.schema.json`` so an epoch can be
    handed to an operator, an auditor or another tool unchanged.
    """

    policy_epoch: str
    tier: str
    policy: str
    capacity_bytes: int
    objective_profile: str
    fallback_policy: str
    configuration_digest: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    selector: Mapping[str, Any] | None = None
    model_digest: str | None = None
    trace_corpus_digest: str | None = None
    confidence: float | None = None
    reason_codes: tuple[str, ...] = ()
    effective_from: str = "1970-01-01T00:00:00+00:00"
    expires_at: str | None = None
    state_carried: bool = True

    def to_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "policy_epoch": self.policy_epoch,
            "tier": self.tier,
            "policy": self.policy,
            "capacity_bytes": self.capacity_bytes,
            "objective_profile": self.objective_profile,
            "fallback_policy": self.fallback_policy,
            "configuration_digest": self.configuration_digest,
            "parameters": dict(self.parameters),
            "reason_codes": list(self.reason_codes),
            "effective_from": self.effective_from,
        }
        if self.selector is not None:
            document["selector"] = dict(self.selector)
        for name, value in (
            ("model_digest", self.model_digest),
            ("trace_corpus_digest", self.trace_corpus_digest),
            ("confidence", self.confidence),
            ("expires_at", self.expires_at),
        ):
            if value is not None:
                document[name] = value
        return document


def configuration_digest(
    policy: str, capacity_bytes: int, objective: str, parameters: Mapping[str, Any]
) -> str:
    return digest_of(
        {
            "policy": policy,
            "capacity_bytes": capacity_bytes,
            "objective_profile": objective,
            "parameters": dict(parameters),
        }
    )


class RuleSelector:
    """Deterministic rules over the fingerprint. Readable on purpose.

    Each branch encodes one thing the replay experiments actually showed, and
    each returns the evidence for its own choice. A rule nobody can explain is
    a rule nobody can safely disable at 3am.
    """

    def __init__(
        self,
        minimum_requests: int = 200,
        minimum_unique: int = 20,
        certified_ranges: Mapping[str, tuple[float, float]] | None = None,
    ) -> None:
        self.minimum_requests = minimum_requests
        self.minimum_unique = minimum_unique
        self.certified_ranges = dict(certified_ranges or {})

    def select(self, features: Mapping[str, float]) -> Selection:
        if not features or features.get("request_count", 0) < self.minimum_requests:
            return Selection(
                PINNED_FALLBACK.value,
                0.2,
                (SelectionReason.INSUFFICIENT_SAMPLE.value, SelectionReason.STRONG_FIXED_FALLBACK.value),
                features,
            )
        if features.get("unique_count", 0) < self.minimum_unique:
            return Selection(
                PINNED_FALLBACK.value,
                0.25,
                (SelectionReason.INSUFFICIENT_SAMPLE.value, SelectionReason.STRONG_FIXED_FALLBACK.value),
                features,
            )
        outside = self.out_of_distribution(features)
        if outside:
            return Selection(
                PINNED_FALLBACK.value,
                0.15,
                (SelectionReason.OUT_OF_DISTRIBUTION.value, *outside),
                features,
            )

        one_hit = features.get("one_hit_ratio", 0.0)
        reuse = features.get("reuse_ratio", 0.0)
        size_cv = features.get("size_cv", 0.0)
        cost_cv = features.get("cost_cv", 0.0)
        known_future = features.get("known_future_ratio", 0.0)

        if known_future >= 0.4:
            # A substantial share of accesses have a planned consumer: protection
            # and prefetch do the heavy lifting, and the replacement policy only
            # has to avoid thrashing. This branch comes first because knowledge
            # of the future outranks any inference from the past.
            return Selection(
                PolicyName.SIEVE.value, 0.7, (SelectionReason.KNOWN_FUTURE.value,), features
            )
        if size_cv >= 1.5 and cost_cv >= 1.0:
            # Sizes and costs both vary by orders of magnitude: value per byte
            # is the only comparison that means anything.
            return Selection(
                PolicyName.GDSF.value, 0.75, (SelectionReason.EXPENSIVE_SPARSE_REUSE.value,), features
            )
        if one_hit >= 0.6:
            return Selection(
                PolicyName.S3_FIFO.value, 0.8, (SelectionReason.ONE_HIT_HEAVY.value,), features
            )
        if size_cv >= 1.5:
            return Selection(
                PolicyName.SIZE_AWARE_TINY_LFU.value,
                0.65,
                (SelectionReason.HETEROGENEOUS_SIZE.value,),
                features,
            )
        if reuse >= 0.5:
            return Selection(
                PolicyName.W_TINY_LFU.value, 0.7, (SelectionReason.HIGH_TEMPORAL_REUSE.value,), features
            )
        return Selection(
            PINNED_FALLBACK.value, 0.5, (SelectionReason.UNIFORM_WORKLOAD.value,), features
        )

    def out_of_distribution(self, features: Mapping[str, float]) -> tuple[str, ...]:
        """Features outside the range the selector was certified on."""
        outside: list[str] = []
        for name, (low, high) in sorted(self.certified_ranges.items()):
            value = features.get(name)
            if value is None:
                continue
            if value < low or value > high:
                outside.append(f"OOD:{name}")
        return tuple(outside)


@dataclass
class ShadowPolicy:
    """A candidate fed the real request stream with no authority over it."""

    policy: CachePolicy
    hits: int = 0
    misses: int = 0

    @property
    def object_hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class PolicyOrchestrator:
    """Owns the active epoch, the shadows, and the right to switch between them."""

    def __init__(
        self,
        tier: str,
        capacity_bytes: int,
        *,
        objective: str | ObjectiveProfile = ObjectiveProfile.BALANCED,
        selector: RuleSelector | None = None,
        initial_policy: str = PINNED_FALLBACK.value,
        minimum_dwell_events: int = 5_000,
        improvement_margin: float = 0.03,
        fallback_policy: str = PINNED_FALLBACK.value,
        clock: Any | None = None,
    ) -> None:
        self.tier = tier
        self.capacity_bytes = capacity_bytes
        self.objective = ObjectiveProfile(str(objective)).value
        self.selector = selector or RuleSelector()
        self.minimum_dwell_events = minimum_dwell_events
        self.improvement_margin = improvement_margin
        self.fallback_policy = fallback_policy
        self.clock = clock
        self.policy: CachePolicy = create_policy(initial_policy, capacity_bytes)
        self.events_in_epoch = 0
        self.epochs: list[PolicyEpoch] = []
        self.shadows: dict[str, ShadowPolicy] = {}
        self._epoch_counter = 0
        self._open_epoch(
            initial_policy, (SelectionReason.OPERATOR_PINNED.value,), confidence=None, carried=False
        )

    # -- epochs -----------------------------------------------------------
    def _open_epoch(
        self,
        policy_name: str,
        reasons: Sequence[str],
        *,
        confidence: float | None,
        carried: bool,
        selector: Mapping[str, Any] | None = None,
        trace_corpus_digest: str | None = None,
        model_digest: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> PolicyEpoch:
        self._epoch_counter += 1
        parameters = dict(parameters or {})
        epoch = PolicyEpoch(
            policy_epoch=f"{self.tier}-epoch-{self._epoch_counter:04d}",
            tier=self.tier,
            policy=policy_name,
            capacity_bytes=self.capacity_bytes,
            objective_profile=self.objective,
            fallback_policy=self.fallback_policy,
            configuration_digest=configuration_digest(
                policy_name, self.capacity_bytes, self.objective, parameters
            ),
            parameters=parameters,
            selector=dict(selector) if selector else None,
            confidence=confidence,
            trace_corpus_digest=trace_corpus_digest,
            model_digest=model_digest,
            reason_codes=tuple(reasons),
            state_carried=carried,
        )
        self.epochs.append(epoch)
        self.events_in_epoch = 0
        return epoch

    @property
    def current_epoch(self) -> PolicyEpoch:
        return self.epochs[-1]

    # -- the stream -------------------------------------------------------
    def observe(self, events: Sequence[CacheTraceEvent]) -> None:
        """Count traffic toward the dwell requirement and feed the shadows."""
        self.events_in_epoch += len(events)
        for shadow in self.shadows.values():
            for event in events:
                from .cache_policy import CacheObject

                decision = shadow.policy.access(
                    CacheObject(
                        key=event.key_hash,
                        size_bytes=event.size_bytes,
                        recompute_ms=event.recompute_ms,
                        restore_ms=event.restore_ms,
                        stage_class=event.stage_class,
                        tenant_hash=event.namespace_hash,
                    )
                )
                if decision.hit:
                    shadow.hits += 1
                else:
                    shadow.misses += 1

    def add_shadow(self, policy_name: str) -> ShadowPolicy:
        shadow = ShadowPolicy(create_policy(policy_name, self.capacity_bytes))
        self.shadows[policy_name] = shadow
        return shadow

    # -- switching --------------------------------------------------------
    def evaluate(
        self,
        events: Sequence[CacheTraceEvent],
        *,
        drifted: bool = False,
        telemetry_healthy: bool = True,
        trace_corpus_digest: str | None = None,
        force: bool = False,
    ) -> tuple[PolicyEpoch, Selection]:
        """Decide whether to switch, and open a new epoch if so."""
        features = workload_features(events)
        selection = self.selector.select(features)

        if not telemetry_healthy:
            selection = Selection(
                self.fallback_policy,
                0.1,
                (SelectionReason.TELEMETRY_DEGRADED.value, SelectionReason.STRONG_FIXED_FALLBACK.value),
                features,
            )
        elif drifted:
            selection = Selection(
                self.fallback_policy,
                0.2,
                (SelectionReason.DRIFT_DETECTED.value, SelectionReason.STRONG_FIXED_FALLBACK.value),
                features,
            )

        if selection.policy == self.policy.name.value:
            return self.current_epoch, selection
        if not force and self.events_in_epoch < self.minimum_dwell_events:
            # Hysteresis: a better idea is not worth a switch this soon.
            return self.current_epoch, Selection(
                self.policy.name.value,
                selection.confidence,
                (*selection.reason_codes, SelectionReason.WITHIN_DWELL_TIME.value),
                features,
            )
        shadow = self.shadows.get(selection.policy)
        incumbent = self.shadows.get(self.policy.name.value)
        if shadow is not None and incumbent is not None:
            if shadow.object_hit_ratio - incumbent.object_hit_ratio < self.improvement_margin:
                return self.current_epoch, Selection(
                    self.policy.name.value,
                    selection.confidence,
                    (*selection.reason_codes, SelectionReason.IMPROVEMENT_BELOW_MARGIN.value),
                    features,
                )
            selection = Selection(
                selection.policy,
                min(selection.confidence + 0.1, 1.0),
                (*selection.reason_codes, SelectionReason.SHADOW_EVIDENCE.value),
                features,
            )

        epoch = self.switch(
            selection.policy,
            reasons=selection.reason_codes,
            confidence=selection.confidence,
            selector={"kind": "rule", "features": dict(features)},
            trace_corpus_digest=trace_corpus_digest,
        )
        return epoch, selection

    def switch(
        self,
        policy_name: str,
        *,
        reasons: Sequence[str],
        confidence: float | None = None,
        carry_state: bool = False,
        selector: Mapping[str, Any] | None = None,
        trace_corpus_digest: str | None = None,
        model_digest: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> PolicyEpoch:
        """Open a new epoch. State is migrated or reset -- never ambiguously kept."""
        previous = self.policy
        if carry_state and policy_name == previous.name.value:
            self.policy = restore_policy(previous.snapshot())
        else:
            self.policy = create_policy(policy_name, self.capacity_bytes, **dict(parameters or {}))
            for key in previous.protected():
                self.policy.protect(key)
        return self._open_epoch(
            policy_name,
            reasons,
            confidence=confidence,
            carried=carry_state,
            selector=selector,
            trace_corpus_digest=trace_corpus_digest,
            model_digest=model_digest,
            parameters=parameters,
        )

    def fallback(self, reason: str) -> PolicyEpoch:
        """Immediate, unconditional return to the pinned policy."""
        return self.switch(
            self.fallback_policy,
            reasons=(reason, SelectionReason.STRONG_FIXED_FALLBACK.value),
            confidence=0.0,
        )

    def history(self) -> list[dict[str, Any]]:
        return [epoch.to_dict() for epoch in self.epochs]

    def state(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "tier": self.tier,
            "policy": self.policy.name.value,
            "epoch": self.current_epoch.policy_epoch,
            "events_in_epoch": self.events_in_epoch,
            "shadows": {
                name: round(shadow.object_hit_ratio, 6) for name, shadow in sorted(self.shadows.items())
            },
            "policy_state_digest": self.policy.state_digest(),
        }
