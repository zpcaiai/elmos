"""Certifying a cache policy, and knowing exactly when the certificate dies.

A policy that wins a benchmark is not certified. Certification here means a
specific, checkable claim: *this* policy implementation, at *this* capacity,
under *this* objective, beat the deployed baseline on a trace window that no
tuning ever touched, without regressing any cohort, without exceeding the
decision-overhead budget, without a fairness violation, and with zero
correctness failures -- and it survived a rollback exercise.

Two things make the certificate worth anything:

**It binds everything that could change the answer.** Policy digest, model
digest, configuration digest, trace corpus and split digests, capacity,
protected-root rules, objective weights, hardware profile. `expired_reasons`
compares a live context against that binding and names each thing that moved.
A certificate that cannot expire is a decoration.

**A correctness failure is fatal regardless of hit rate.** There is no weighted
objective in which invalid reuse is worth performance, so the gate is separate
from the score rather than a term inside it.

The rollout ladder -- simulator, shadow, read-only recommendation, canary,
progressive, full -- is modelled here as well, because "we certified it" and
"we turned it on everywhere at once" should never be the same sentence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from itertools import product
from typing import Any

from .cache_policy import PolicyName
from .cache_simulator import (
    BenchmarkGates,
    ObjectiveProfile,
    SimulationResult,
    benchmark,
    recommended_capacity,
    replay,
    weighted_value,
)
from .cache_trace import GENERATORS, Split, TraceCorpus, detect_leakage, sufficient_sample
from .canonical import digest_of
from .errors import ContractViolation
from .security import ProvenanceSigner, SignedStatement

SCHEMA_VERSION = "1.1.0"

CERTIFICATE_KIND = "elmos.cache-policy-certificate/v1"

#: The fixed portfolio, as a benchmark default.
ALL_POLICIES: tuple[str, ...] = tuple(policy.value for policy in PolicyName)


class RolloutPhase(str, Enum):
    """The ladder. Each rung has to be climbed; none may be skipped."""

    SIMULATOR = "SIMULATOR"
    SHADOW = "SHADOW"
    RECOMMENDATION = "RECOMMENDATION"
    CANARY = "CANARY"
    PROGRESSIVE = "PROGRESSIVE"
    FULL = "FULL"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


ROLLOUT_ORDER: tuple[RolloutPhase, ...] = (
    RolloutPhase.SIMULATOR,
    RolloutPhase.SHADOW,
    RolloutPhase.RECOMMENDATION,
    RolloutPhase.CANARY,
    RolloutPhase.PROGRESSIVE,
    RolloutPhase.FULL,
)


@dataclass
class RolloutPlan:
    """Where a policy is in the ladder, and what would send it back down."""

    phase: RolloutPhase = RolloutPhase.SIMULATOR
    history: list[dict[str, Any]] = field(default_factory=list)
    rolled_back: bool = False

    def advance(self, evidence: Mapping[str, Any]) -> RolloutPhase:
        index = ROLLOUT_ORDER.index(self.phase)
        if index + 1 >= len(ROLLOUT_ORDER):
            return self.phase
        self.phase = ROLLOUT_ORDER[index + 1]
        self.history.append({"phase": self.phase.value, "evidence": dict(evidence)})
        return self.phase

    def rollback(self, reason: str) -> RolloutPhase:
        """Straight back to the simulator; a rollback is not a demotion by one."""
        self.phase = RolloutPhase.SIMULATOR
        self.rolled_back = True
        self.history.append({"phase": self.phase.value, "reason": reason})
        return self.phase

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase.value, "rolled_back": self.rolled_back, "history": self.history}


@dataclass(frozen=True)
class CertificationGates:
    """The thresholds a policy has to clear on the untouched window."""

    minimum_weighted_improvement: float = 0.02
    maximum_cohort_regression: float = 0.05
    maximum_p95_decision_micros: float = 250.0
    minimum_tenant_fairness: float = 0.5
    minimum_test_events: int = 200
    require_rollback_exercise: bool = True

    def benchmark_gates(self) -> BenchmarkGates:
        return BenchmarkGates(
            minimum_weighted_improvement=self.minimum_weighted_improvement,
            maximum_cohort_regression=self.maximum_cohort_regression,
            maximum_p95_decision_micros=self.maximum_p95_decision_micros,
            minimum_tenant_fairness=self.minimum_tenant_fairness,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_weighted_improvement": self.minimum_weighted_improvement,
            "maximum_cohort_regression": self.maximum_cohort_regression,
            "maximum_p95_decision_micros": self.maximum_p95_decision_micros,
            "minimum_tenant_fairness": self.minimum_tenant_fairness,
            "minimum_test_events": self.minimum_test_events,
            "require_rollback_exercise": self.require_rollback_exercise,
        }


# --------------------------------------------------------------------------
# the benchmark matrix
# --------------------------------------------------------------------------
def benchmark_matrix(
    *,
    workloads: Mapping[str, TraceCorpus] | None = None,
    capacity_fractions: Sequence[float] = (0.05, 0.2, 0.5),
    policies: Sequence[str] = ALL_POLICIES,
    objective: str | ObjectiveProfile = ObjectiveProfile.BALANCED,
    baseline: str = PolicyName.LRU.value,
) -> dict[str, Any]:
    """Every workload against every capacity: where a policy stops winning.

    A single-point benchmark hides the interesting part. The same policy that
    wins at 50 % of the working set can lose badly at 5 %, and a deployment
    lives at one specific point on that curve.
    """
    if workloads is None:
        workloads = {name: generator() for name, generator in GENERATORS.items()}
    corpora: dict[str, TraceCorpus] = dict(workloads)
    cells: list[dict[str, Any]] = []
    for (name, corpus), fraction in product(sorted(corpora.items()), capacity_fractions):
        capacity = recommended_capacity(corpus.events, fraction)
        report = benchmark(
            corpus,
            policies=policies,
            capacity_bytes=capacity,
            baseline=baseline,
            objective=objective,
        )
        cells.append(
            {
                "workload": name,
                "capacity_fraction": fraction,
                "capacity_bytes": capacity,
                "selected": report["gates"]["selected"],
                "scores": {
                    candidate["policy"]: candidate["metrics"]["weighted_value"]
                    for candidate in report["candidates"]
                },
            }
        )
    wins: dict[str, int] = {}
    for cell in cells:
        best = max(cell["scores"], key=lambda policy: (cell["scores"][policy], policy))
        wins[best] = wins.get(best, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "objective_profile": ObjectiveProfile(str(objective)).value,
        "cells": cells,
        "wins": dict(sorted(wins.items(), key=lambda item: (-item[1], item[0]))),
        "no_single_winner": len(wins) > 1,
    }


def pareto_frontier(
    results: Mapping[str, SimulationResult], metrics: Sequence[str] = ("avoided_compute_ratio", "byte_hit_ratio")
) -> tuple[str, ...]:
    """Policies nothing else dominates on every listed metric at once."""
    scores = {name: result.metrics() for name, result in results.items()}
    frontier = []
    for name, values in scores.items():
        dominated = any(
            other != name
            and all(scores[other][metric] >= values[metric] for metric in metrics)
            and any(scores[other][metric] > values[metric] for metric in metrics)
            for other in scores
        )
        if not dominated:
            frontier.append(name)
    return tuple(sorted(frontier))


def search_parameters(
    corpus: TraceCorpus,
    policy: str,
    grid: Mapping[str, Sequence[float]],
    *,
    capacity_bytes: int | None = None,
    objective: str | ObjectiveProfile = ObjectiveProfile.BALANCED,
) -> dict[str, Any]:
    """Tune on ``train``, choose on ``validation``, and never look at ``test``.

    The returned record says which split each number came from, so a later
    reader can check that the choice was not made on the window it is about to
    be certified against.
    """
    train = corpus.split(Split.TRAIN) if Split.TRAIN.value in corpus.splits else corpus.events
    validation = (
        corpus.split(Split.VALIDATION) if Split.VALIDATION.value in corpus.splits else corpus.events
    )
    capacity = capacity_bytes or recommended_capacity(corpus.events)
    names = sorted(grid)
    trials: list[dict[str, Any]] = []
    for combination in product(*(grid[name] for name in names)):
        parameters = dict(zip(names, combination, strict=True))
        train_result = replay(policy, train, capacity, policy_parameters=parameters)
        validation_result = replay(policy, validation, capacity, policy_parameters=parameters)
        trials.append(
            {
                "parameters": parameters,
                "train_value": weighted_value(train_result, objective),
                "validation_value": weighted_value(validation_result, objective),
            }
        )
    best = max(trials, key=lambda trial: (trial["validation_value"], -sum(trial["parameters"].values())))
    return {
        "policy": policy,
        "capacity_bytes": capacity,
        "objective_profile": ObjectiveProfile(str(objective)).value,
        "trials": trials,
        "selected_parameters": best["parameters"],
        "selected_on_split": Split.VALIDATION.value,
        "test_split_untouched": True,
    }


# --------------------------------------------------------------------------
# the certificate
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CertificationContext:
    """Everything the certificate binds to. Change any of it and it expires."""

    elmos_commit: str
    policy_digest: str
    configuration_digest: str
    capacity_bytes: int
    objective_profile: str
    protected_root_rules: str
    hardware_profile: str
    model_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "elmos_commit": self.elmos_commit,
            "policy_digest": self.policy_digest,
            "configuration_digest": self.configuration_digest,
            "capacity_bytes": self.capacity_bytes,
            "objective_profile": self.objective_profile,
            "protected_root_rules": self.protected_root_rules,
            "hardware_profile": self.hardware_profile,
            "model_digest": self.model_digest,
        }


@dataclass(frozen=True)
class CertificationResult:
    """Certified or not, and either way the complete reason."""

    certified: bool
    policy: str
    reasons: tuple[str, ...]
    statement: Mapping[str, Any]
    signed: SignedStatement | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "certified": self.certified,
            "policy": self.policy,
            "reasons": list(self.reasons),
            "statement": dict(self.statement),
            "signed": self.signed.to_dict() if self.signed else None,
        }


def certify_policy(
    corpus: TraceCorpus,
    candidate: str,
    context: CertificationContext,
    signer: ProvenanceSigner,
    *,
    baseline: str = PolicyName.LRU.value,
    objective: str | ObjectiveProfile = ObjectiveProfile.BALANCED,
    gates: CertificationGates | None = None,
    rollout: RolloutPlan | None = None,
    shadow_evidence: Mapping[str, Any] | None = None,
    canary_evidence: Mapping[str, Any] | None = None,
    rollback_evidence: Mapping[str, Any] | None = None,
    issued_at: str = "1970-01-01T00:00:00+00:00",
    expires_at: str | None = None,
) -> CertificationResult:
    """Run the final gate on the untouched window and issue or refuse.

    Nothing here is optional-if-inconvenient: a missing rollback exercise, a
    too-small test window, a leaked split or a single correctness failure each
    refuse the certificate on their own.
    """
    gates = gates or CertificationGates()
    reasons: list[str] = []

    test_events = corpus.split(Split.TEST) if Split.TEST.value in corpus.splits else corpus.events
    enough, detail = sufficient_sample(test_events, minimum_events=gates.minimum_test_events)
    if not enough:
        reasons.append(f"INSUFFICIENT_TEST_WINDOW:{detail}")
    leakage = detect_leakage(corpus)
    if leakage:
        reasons.extend(f"LEAKAGE:{finding.kind}" for finding in leakage)

    report = benchmark(
        test_events,
        policies=(baseline, candidate),
        capacity_bytes=context.capacity_bytes,
        baseline=baseline,
        objective=objective,
        gates=gates.benchmark_gates(),
    )
    verdict = report["gates"]["verdicts"].get(candidate, {})
    if report["gates"]["correctness_failures"]:
        reasons.append("CORRECTNESS_FAILURE")
    for failure in verdict.get("failures", ()):
        reasons.append(failure)

    if gates.require_rollback_exercise and not rollback_evidence:
        reasons.append("NO_ROLLBACK_EXERCISE")
    if not shadow_evidence:
        reasons.append("NO_SHADOW_EVIDENCE")

    plan = rollout or RolloutPlan()
    statement: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": CERTIFICATE_KIND,
        "policy": candidate,
        "baseline": baseline,
        "context": context.to_dict(),
        "trace": {
            "corpus_digest": corpus.digest(),
            "split_digests": corpus.split_digests(),
            "test_events": len(test_events),
        },
        "objective_profile": ObjectiveProfile(str(objective)).value,
        "gates": gates.to_dict(),
        "measurements": {
            "weighted_improvement": verdict.get("improvement"),
            "worst_cohort_regression": verdict.get("worst_cohort_regression"),
            "report_id": report["report_id"],
            "candidates": {
                item["policy"]: item["metrics"] for item in report["candidates"]
            },
        },
        "shadow_evidence": dict(shadow_evidence or {}),
        "canary_evidence": dict(canary_evidence or {}),
        "rollback_evidence": dict(rollback_evidence or {}),
        "rollout": plan.to_dict(),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "expiry_conditions": [
            "policy_digest changed",
            "model_digest changed",
            "configuration_digest changed",
            "capacity_bytes changed",
            "objective_profile changed",
            "protected_root_rules changed",
            "hardware_profile changed",
            "workload regime drifted beyond the certified range",
        ],
    }
    if reasons:
        return CertificationResult(False, candidate, tuple(dict.fromkeys(reasons)), statement)

    statement["certified"] = True
    signed = signer.sign_statement(CERTIFICATE_KIND, statement)
    return CertificationResult(True, candidate, ("CERTIFIED",), statement, signed)


def verify_certificate(
    signed: SignedStatement,
    signer: ProvenanceSigner,
    *,
    now: str | None = None,
) -> Mapping[str, Any]:
    """Signature first, then the certificate's own expiry."""
    if signed.kind != CERTIFICATE_KIND:
        raise ContractViolation("not a cache policy certificate", kind=signed.kind)
    signer.verify_statement(signed)
    statement = signed.statement
    expires_at = statement.get("expires_at")
    if now is not None and expires_at is not None and str(now) >= str(expires_at):
        raise ContractViolation("certificate has expired", expires_at=expires_at, now=now)
    return statement


def expired_reasons(
    statement: Mapping[str, Any],
    context: CertificationContext,
    *,
    drift: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Name every bound value that has moved since the certificate was issued."""
    certified = dict(statement.get("context", {}))
    live = context.to_dict()
    moved = [
        f"{name}:{certified.get(name)!r}->{live.get(name)!r}"
        for name in sorted(set(certified) | set(live))
        if certified.get(name) != live.get(name)
    ]
    if drift and drift.get("drifted"):
        moved.append("workload_regime:" + ",".join(drift.get("drifted_features", ())[:4]))
    return tuple(moved)


def certification_digest(statement: Mapping[str, Any]) -> str:
    return digest_of(dict(statement))
