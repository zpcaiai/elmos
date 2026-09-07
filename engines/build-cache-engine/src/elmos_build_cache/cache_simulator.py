"""Deterministic replay: the only place a policy claim is allowed to come from.

A policy that wins on somebody else's web-cache trace has told you nothing
about ELMOS. This module replays an ELMOS trace against a policy and reports
what the cache is actually for -- avoided compute, avoided model tokens,
critical-path time saved -- alongside the object hit ratio that cache papers
usually optimise and that, on its own, can go up while the build gets slower.

Two properties make the numbers usable:

**Determinism.** The same trace, capacity, protected set and policy produce
identical decisions and identical metrics, every run. `SOTA-01` asserts it.

**Equal treatment.** Every policy in a comparison sees the same request
sequence, the same capacity, the same object sizes, the same protected roots
and the same warm-up. `benchmark` is the only supported way to produce a
comparison, precisely so that none of those can quietly differ between arms.

The report is written to the package's `cache-benchmark-report.schema.json`
shape, so an ELMOS run and the reference simulator can be compared field by
field rather than by eye.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .cache_policy import CacheObject, CachePolicy, PolicyName, create_policy
from .cache_trace import (
    CacheTraceEvent,
    TraceCorpus,
    workload_features,
)
from .canonical import digest_of
from .errors import ContractViolation

SCHEMA_VERSION = "1.1.0"

#: Restoring is only worth it when it is meaningfully cheaper than rebuilding.
#: Below this ratio the simulator records a bypass instead of a hit, which is
#: the behaviour `SOTA-08` asks for.
DEFAULT_BYPASS_RATIO = 0.9


@dataclass
class SimulationResult:
    """Everything one policy did on one trace."""

    policy: str
    capacity_bytes: int
    requests: int = 0
    hits: int = 0
    misses: int = 0
    admitted_misses: int = 0
    bypassed_misses: int = 0
    evictions: int = 0
    request_bytes: int = 0
    hit_bytes: int = 0
    total_recompute_ms: float = 0.0
    avoided_recompute_ms: float = 0.0
    restore_ms_on_hits: float = 0.0
    total_model_tokens: int = 0
    avoided_model_tokens: int = 0
    critical_path_saved_ms: float = 0.0
    restore_bypasses: int = 0
    protected_rejections: int = 0
    decision_micros: list[float] = field(default_factory=list)
    per_tenant_hits: dict[str, int] = field(default_factory=dict)
    per_tenant_requests: dict[str, int] = field(default_factory=dict)
    per_stage_hits: dict[str, int] = field(default_factory=dict)
    per_stage_requests: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, int] = field(default_factory=dict)
    correctness_failures: int = 0

    # -- derived ---------------------------------------------------------
    @property
    def object_hit_ratio(self) -> float:
        return self.hits / self.requests if self.requests else 0.0

    @property
    def byte_hit_ratio(self) -> float:
        return self.hit_bytes / self.request_bytes if self.request_bytes else 0.0

    @property
    def avoided_compute_ratio(self) -> float:
        return self.avoided_recompute_ms / self.total_recompute_ms if self.total_recompute_ms else 0.0

    @property
    def avoided_model_token_ratio(self) -> float:
        return self.avoided_model_tokens / self.total_model_tokens if self.total_model_tokens else 0.0

    @property
    def net_saved_ms(self) -> float:
        """What the cache actually bought: avoided work minus the restores it cost."""
        return self.avoided_recompute_ms - self.restore_ms_on_hits

    @property
    def churn(self) -> float:
        return self.evictions / self.admitted_misses if self.admitted_misses else 0.0

    @property
    def p95_decision_micros(self) -> float:
        if not self.decision_micros:
            return 0.0
        ordered = sorted(self.decision_micros)
        index = min(int(0.95 * len(ordered)), len(ordered) - 1)
        return ordered[index]

    @property
    def tenant_fairness(self) -> float:
        """Worst tenant's hit ratio over the best tenant's. 1.0 is perfectly even."""
        ratios = [
            self.per_tenant_hits.get(tenant, 0) / count
            for tenant, count in self.per_tenant_requests.items()
            if count
        ]
        if len(ratios) < 2:
            return 1.0
        best = max(ratios)
        return min(ratios) / best if best else 1.0

    def metrics(self) -> dict[str, float]:
        """The flat metric map the benchmark report carries."""
        return {
            "requests": float(self.requests),
            "hits": float(self.hits),
            "misses": float(self.misses),
            "admitted_misses": float(self.admitted_misses),
            "bypassed_misses": float(self.bypassed_misses),
            "evictions": float(self.evictions),
            "request_bytes": float(self.request_bytes),
            "hit_bytes": float(self.hit_bytes),
            "total_recompute_ms": round(self.total_recompute_ms, 6),
            "avoided_recompute_ms": round(self.avoided_recompute_ms, 6),
            "restore_ms_on_hits": round(self.restore_ms_on_hits, 6),
            "total_model_tokens": float(self.total_model_tokens),
            "avoided_model_tokens": float(self.avoided_model_tokens),
            "critical_path_saved_ms": round(self.critical_path_saved_ms, 6),
            "object_hit_ratio": round(self.object_hit_ratio, 9),
            "byte_hit_ratio": round(self.byte_hit_ratio, 9),
            "avoided_compute_ratio": round(self.avoided_compute_ratio, 9),
            "avoided_model_token_ratio": round(self.avoided_model_token_ratio, 9),
            "net_saved_ms": round(self.net_saved_ms, 6),
            "churn": round(self.churn, 9),
            "restore_bypasses": float(self.restore_bypasses),
            "protected_rejections": float(self.protected_rejections),
            "p95_decision_micros": round(self.p95_decision_micros, 6),
            "tenant_fairness": round(self.tenant_fairness, 9),
            "correctness_failures": float(self.correctness_failures),
        }

    def cohorts(self) -> list[dict[str, Any]]:
        """Per-stage and per-tenant hit ratios: where an average is hiding a regression."""
        rows: list[dict[str, Any]] = []
        for stage, count in sorted(self.per_stage_requests.items()):
            rows.append(
                {
                    "cohort": "stage",
                    "name": stage,
                    "requests": count,
                    "object_hit_ratio": round(self.per_stage_hits.get(stage, 0) / count, 9),
                }
            )
        for index, (tenant, count) in enumerate(sorted(self.per_tenant_requests.items())):
            rows.append(
                {
                    "cohort": "tenant",
                    "name": f"tenant-{index:02d}",  # the pseudonym is not even in the report
                    "requests": count,
                    "object_hit_ratio": round(self.per_tenant_hits.get(tenant, 0) / count, 9),
                }
            )
        return rows


def replay(
    policy: CachePolicy | str | PolicyName,
    events: Sequence[CacheTraceEvent],
    capacity_bytes: int | None = None,
    *,
    protected: Iterable[str] = (),
    warmup: int = 0,
    bypass_ratio: float = DEFAULT_BYPASS_RATIO,
    policy_parameters: Mapping[str, Any] | None = None,
) -> SimulationResult:
    """Replay ``events`` against one policy and measure what the cache bought.

    ``warmup`` events populate the cache but are excluded from the metrics, so
    every arm of a comparison is measured from the same cache state rather than
    from whichever arm happened to fill up first.
    """
    if isinstance(policy, CachePolicy):
        if capacity_bytes is not None and capacity_bytes != policy.capacity_bytes:
            raise ContractViolation(
                "capacity disagrees with the policy instance",
                policy=policy.capacity_bytes,
                requested=capacity_bytes,
            )
        engine = policy
    else:
        if capacity_bytes is None:
            raise ContractViolation("capacity_bytes is required when the policy is named")
        engine = create_policy(policy, capacity_bytes, **(policy_parameters or {}))
    for key in protected:
        engine.protect(key)

    result = SimulationResult(policy=engine.name.value, capacity_bytes=engine.capacity_bytes)
    for index, event in enumerate(events):
        measured = index >= warmup
        obj = CacheObject(
            key=event.key_hash,
            size_bytes=event.size_bytes,
            recompute_ms=event.recompute_ms,
            restore_ms=event.restore_ms,
            model_tokens=event.model_tokens,
            critical_path_weight=event.critical_path_weight,
            stage_class=event.stage_class,
            validation_level=event.validation_level,
            tenant_hash=event.namespace_hash,
            next_use_distance=event.next_use_distance,
        )

        started = time.perf_counter()
        try:
            decision = engine.access(obj)
        except ContractViolation:
            # An immutable key that changed size is a correctness failure in the
            # trace or the key contract, never something to smooth over.
            result.correctness_failures += 1
            continue
        elapsed_micros = (time.perf_counter() - started) * 1_000_000

        if not measured:
            continue

        result.requests += 1
        result.request_bytes += event.size_bytes
        result.total_recompute_ms += event.recompute_ms
        result.total_model_tokens += event.model_tokens
        result.decision_micros.append(elapsed_micros)
        result.per_stage_requests[event.stage_class] = result.per_stage_requests.get(event.stage_class, 0) + 1
        result.per_tenant_requests[event.namespace_hash] = (
            result.per_tenant_requests.get(event.namespace_hash, 0) + 1
        )
        for reason in decision.reasons:
            result.reasons[reason] = result.reasons.get(reason, 0) + 1
        result.evictions += len(decision.evicted)

        if decision.hit:
            # A "hit" that costs more to restore than to rebuild is not a win.
            if event.restore_ms > event.recompute_ms * bypass_ratio:
                result.restore_bypasses += 1
                result.misses += 1
                continue
            result.hits += 1
            result.hit_bytes += event.size_bytes
            result.avoided_recompute_ms += event.recompute_ms
            result.restore_ms_on_hits += event.restore_ms
            result.avoided_model_tokens += event.model_tokens
            result.critical_path_saved_ms += event.critical_path_weight * event.net_recompute_ms
            result.per_stage_hits[event.stage_class] = result.per_stage_hits.get(event.stage_class, 0) + 1
            result.per_tenant_hits[event.namespace_hash] = (
                result.per_tenant_hits.get(event.namespace_hash, 0) + 1
            )
            continue

        result.misses += 1
        if decision.admitted:
            result.admitted_misses += 1
        else:
            result.bypassed_misses += 1
            if decision.bypass_reason == "CAPACITY_FULLY_PROTECTED":
                result.protected_rejections += 1
    return result


# --------------------------------------------------------------------------
# objectives
# --------------------------------------------------------------------------
class ObjectiveProfile(str, Enum):
    """What "better" means for this deployment.

    A cache tuned for a developer's laptop and a cache tuned to stop paying for
    model tokens are not the same cache, and pretending there is one universal
    objective is how a benchmark ends up optimising the wrong number.
    """

    DEV_SPEED = "DEV_SPEED"
    TOKEN_COST = "TOKEN_COST"  # noqa: S105 - an objective profile, not a credential
    BYTE_NETWORK = "BYTE_NETWORK"
    BALANCED = "BALANCED"
    CERTIFICATION_RETENTION = "CERTIFICATION_RETENTION"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


#: Weights over the *ratio* metrics, so the score is comparable across traces.
OBJECTIVE_WEIGHTS: dict[str, dict[str, float]] = {
    ObjectiveProfile.DEV_SPEED.value: {
        "avoided_compute_ratio": 0.45,
        "critical_path_ratio": 0.45,
        "object_hit_ratio": 0.10,
    },
    ObjectiveProfile.TOKEN_COST.value: {
        "avoided_model_token_ratio": 0.75,
        "avoided_compute_ratio": 0.20,
        "object_hit_ratio": 0.05,
    },
    ObjectiveProfile.BYTE_NETWORK.value: {
        "byte_hit_ratio": 0.70,
        "avoided_compute_ratio": 0.20,
        "object_hit_ratio": 0.10,
    },
    ObjectiveProfile.BALANCED.value: {
        "avoided_compute_ratio": 0.35,
        "critical_path_ratio": 0.25,
        "byte_hit_ratio": 0.20,
        "avoided_model_token_ratio": 0.10,
        "object_hit_ratio": 0.10,
    },
    ObjectiveProfile.CERTIFICATION_RETENTION.value: {
        "avoided_compute_ratio": 0.40,
        "critical_path_ratio": 0.30,
        "object_hit_ratio": 0.20,
        "byte_hit_ratio": 0.10,
    },
}


def weighted_value(result: SimulationResult, objective: str | ObjectiveProfile) -> float:
    """One number per policy, under an explicitly named objective."""
    profile = ObjectiveProfile(str(objective)).value
    critical_total = result.critical_path_saved_ms
    denominator = max(result.total_recompute_ms, 1e-9)
    components = {
        "object_hit_ratio": result.object_hit_ratio,
        "byte_hit_ratio": result.byte_hit_ratio,
        "avoided_compute_ratio": result.avoided_compute_ratio,
        "avoided_model_token_ratio": result.avoided_model_token_ratio,
        "critical_path_ratio": min(critical_total / denominator, 1.0),
    }
    weights = OBJECTIVE_WEIGHTS[profile]
    return round(sum(components[name] * weight for name, weight in weights.items()), 9)


@dataclass(frozen=True)
class BenchmarkGates:
    """What a candidate has to clear before it may be selected.

    These are the numbers the certification skill calls "the configured
    weighted improvement gate": a candidate must be better overall, must not be
    materially worse for any cohort, must not cost more per decision than the
    budget, and must not have traded fairness for throughput.
    """

    minimum_weighted_improvement: float = 0.02
    maximum_cohort_regression: float = 0.05
    maximum_p95_decision_micros: float = float(os.environ.get("ELMOS_MAX_P95_DECISION_MICROS", "500.0"))
    minimum_tenant_fairness: float = 0.5
    require_zero_correctness_failures: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_weighted_improvement": self.minimum_weighted_improvement,
            "maximum_cohort_regression": self.maximum_cohort_regression,
            "maximum_p95_decision_micros": self.maximum_p95_decision_micros,
            "minimum_tenant_fairness": self.minimum_tenant_fairness,
            "require_zero_correctness_failures": self.require_zero_correctness_failures,
        }


DEFAULT_CANDIDATES: tuple[str, ...] = tuple(item.value for item in PolicyName)


def recommended_capacity(events: Sequence[CacheTraceEvent], fraction: float = 0.2) -> int:
    """A capacity that makes the comparison interesting rather than trivial.

    Sized as a fraction of the trace's *unique* bytes: too large and every
    policy hits everything, too small and none of them hit anything. Either way
    the comparison says nothing.
    """
    unique: dict[str, int] = {}
    for event in events:
        unique[event.key_hash] = event.size_bytes
    total = sum(unique.values())
    return max(int(total * fraction), 1)


def benchmark(
    corpus: TraceCorpus | Sequence[CacheTraceEvent],
    *,
    policies: Sequence[str] = DEFAULT_CANDIDATES,
    capacity_bytes: int | None = None,
    baseline: str = PolicyName.LRU.value,
    objective: str | ObjectiveProfile = ObjectiveProfile.BALANCED,
    gates: BenchmarkGates | None = None,
    protected: Iterable[str] = (),
    warmup: int = 0,
    report_id: str | None = None,
    created_at: str | None = None,
    policy_parameters: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay every candidate on identical inputs and produce the report.

    This is the only supported way to compare policies. Capacity, warm-up,
    protected roots and the request sequence are bound once, here, so no arm
    can be measured under conditions another arm did not get.
    """
    events = tuple(corpus.events if isinstance(corpus, TraceCorpus) else corpus)
    if not events:
        raise ContractViolation("cannot benchmark an empty trace")
    if baseline not in policies:
        policies = (baseline, *policies)
    capacity = capacity_bytes or recommended_capacity(events)
    gates = gates or BenchmarkGates()
    protected_keys = tuple(protected)
    parameters = dict(policy_parameters or {})

    results: dict[str, SimulationResult] = {}
    for policy in policies:
        results[policy] = replay(
            policy,
            events,
            capacity,
            protected=protected_keys,
            warmup=warmup,
            policy_parameters=parameters.get(policy),
        )

    scores = {name: weighted_value(result, objective) for name, result in results.items()}
    baseline_result = results[baseline]
    baseline_score = scores[baseline]
    baseline_cohorts = {
        (row["cohort"], row["name"]): row["object_hit_ratio"] for row in baseline_result.cohorts()
    }

    candidates: list[dict[str, Any]] = []
    verdicts: dict[str, dict[str, Any]] = {}
    for name, result in results.items():
        cohort_regression = 0.0
        for row in result.cohorts():
            reference = baseline_cohorts.get((row["cohort"], row["name"]))
            if reference is None:
                continue
            cohort_regression = max(cohort_regression, reference - row["object_hit_ratio"])
        failures: list[str] = []
        if gates.require_zero_correctness_failures and result.correctness_failures:
            failures.append("CORRECTNESS_FAILURE")
        if name != baseline and scores[name] - baseline_score < gates.minimum_weighted_improvement:
            failures.append("INSUFFICIENT_WEIGHTED_IMPROVEMENT")
        if cohort_regression > gates.maximum_cohort_regression:
            failures.append("WORST_COHORT_REGRESSION")
        if result.p95_decision_micros > gates.maximum_p95_decision_micros:
            failures.append("DECISION_OVERHEAD_ABOVE_BUDGET")
        if result.tenant_fairness < gates.minimum_tenant_fairness:
            failures.append("TENANT_FAIRNESS_BELOW_FLOOR")
        verdicts[name] = {
            "weighted_value": scores[name],
            "improvement": round(scores[name] - baseline_score, 9),
            "worst_cohort_regression": round(cohort_regression, 9),
            "failures": failures,
        }
        candidates.append(
            {
                "policy": name,
                "metrics": {**result.metrics(), "weighted_value": scores[name]},
                "configuration": {
                    "capacity_bytes": capacity,
                    "objective_profile": ObjectiveProfile(str(objective)).value,
                    **({"parameters": dict(parameters[name])} if name in parameters else {}),
                },
            }
        )

    eligible = [
        name
        for name in results
        if name != baseline and not verdicts[name]["failures"]
    ]
    # Deterministic tie-break: highest value, then the cheaper decision, then
    # the name. A benchmark that picks a different winner on a coin flip is not
    # reproducible, and reproducibility is the point of this module.
    selected = (
        min(eligible, key=lambda name: (-scores[name], results[name].p95_decision_micros, name))
        if eligible
        else None
    )
    reasons: list[str] = []
    if selected is None:
        reasons.append("NO_CANDIDATE_CLEARED_THE_GATES")
        for name in sorted(verdicts):
            if name != baseline and verdicts[name]["failures"]:
                reasons.append(f"{name}:{'+'.join(verdicts[name]['failures'])}")
    else:
        reasons.append(f"SELECTED_{selected}")

    features = workload_features(events)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id or f"cache-benchmark-{digest_of(features)[7:19]}",
        "trace_corpus_digest": (
            corpus.digest() if isinstance(corpus, TraceCorpus) else digest_of([e.to_dict() for e in events])
        ),
        "capacity_bytes": capacity,
        "baseline": baseline,
        "candidates": sorted(candidates, key=lambda item: item["policy"]),
        "cohorts": [
            {"policy": name, "rows": result.cohorts()} for name, result in sorted(results.items())
        ],
        "gates": {
            "correctness_failures": sum(result.correctness_failures for result in results.values()),
            "selected": selected,
            "reasons": reasons,
            "thresholds": gates.to_dict(),
            "verdicts": verdicts,
        },
        "workload_features": features,
    }
    # ``cache-benchmark-report.schema.json`` is a closed schema, so the
    # objective travels inside each candidate's ``configuration`` and inside
    # the selector recommendation rather than as a new top-level key.
    report["selector_recommendation"] = {
        "policy": selected or baseline,
        "confidence": 0.0 if selected is None else 0.75,
        "reason_codes": [
            ObjectiveProfile(str(objective)).value,
            *(["NO_CANDIDATE_CLEARED_THE_GATES"] if selected is None else []),
            *(["STRONG_FIXED_FALLBACK"] if selected is None else []),
        ],
    }
    if created_at is not None:
        report["created_at"] = created_at
    return report
