from __future__ import annotations

from dataclasses import asdict

import pytest

from elmos_build_cache.canonical import sha256_bytes
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.parity import (
    MANDATORY_SCENARIOS,
    EvidenceBinding,
    ParityThresholds,
    ScenarioResult,
    ScenarioStatus,
    evaluate_parity,
)
from elmos_build_cache.slo_autotune import (
    CacheTuningParameters,
    ProgressiveRolloutController,
    RollbackReason,
    RolloutEvidence,
    RolloutPhase,
    RolloutState,
    SloAutotuner,
    TuningObservation,
)


def digest(value: str) -> str:
    return sha256_bytes(value.encode())


def parameters() -> CacheTuningParameters:
    return CacheTuningParameters(capacity_bytes=10 * 1024 * 1024 * 1024)


def observation(**overrides: object) -> TuningObservation:
    values: dict[str, object] = {
        "sample_count": 10_000,
        "unexpected_prefix_miss_rate": 0.03,
        "wrong_shard_rate": 0.02,
        "environment_hit_rate": 0.90,
        "storage_pressure": 0.50,
        "useful_prefetch_rate": 0.10,
        "context_limit_pressure": 0.80,
        "restore_bypass_rate": 0.40,
    }
    values.update(overrides)
    return TuningObservation(**values)  # type: ignore[arg-type]


def passing_report():
    metrics: dict[str, float | int] = asdict(ParityThresholds())
    scenarios = [
        ScenarioResult(name, ScenarioStatus.PASS, (digest(f"evidence:{name}"),))
        for name in MANDATORY_SCENARIOS
    ]
    binding = EvidenceBinding(
        digest("source"),
        digest("config"),
        digest("providers"),
        digest("corpus"),
        digest("platform"),
        "2026-08-20T12:00:00Z",
        "executor",
        "verifier",
    )
    return evaluate_parity(
        report_id="report-1",
        metrics=metrics,
        cohorts={"representative": metrics},
        scenarios=scenarios,
        binding=binding,
    )


def evidence(report=None, **overrides: object) -> RolloutEvidence:
    values: dict[str, object] = {
        "parity_report": report or passing_report(),
        "provider_accounting_matches": True,
        "worst_cohort_regressed": False,
        "unknown_outcome_rate": 0.0,
        "unknown_outcome_budget": 0.01,
        "out_of_distribution": False,
        "cost_guardrail_passed": True,
        "clean_fallback_exercised": True,
        "rollback_exercised": True,
    }
    values.update(overrides)
    return RolloutEvidence(**values)  # type: ignore[arg-type]


def test_autotuner_changes_only_bounded_performance_knobs() -> None:
    baseline = parameters()
    proposal = SloAutotuner().propose(baseline, observation())
    assert proposal.shadow_only
    assert proposal.baseline_digest == baseline.digest
    assert proposal.candidate.provider_prefix_ttl_seconds > baseline.provider_prefix_ttl_seconds
    assert proposal.candidate.affinity_locality_weight > baseline.affinity_locality_weight
    assert proposal.candidate.environment_ttl_seconds > baseline.environment_ttl_seconds
    assert proposal.candidate.prefetch_max_bytes < baseline.prefetch_max_bytes
    assert proposal.candidate.context_compaction_soft_ratio < baseline.context_compaction_soft_ratio
    assert proposal.candidate.restore_cost_bias > baseline.restore_cost_bias
    assert "tenant" not in asdict(proposal.candidate)
    assert "validation" not in asdict(proposal.candidate)
    assert "action_key" not in asdict(proposal.candidate)


def test_ood_and_small_samples_pin_the_baseline() -> None:
    baseline = parameters()
    ood = SloAutotuner().propose(baseline, observation(out_of_distribution=True))
    small = SloAutotuner().propose(baseline, observation(sample_count=10))
    assert ood.candidate == baseline and ood.reason_codes == ("OOD_PIN_BASELINE",)
    assert small.candidate == baseline and small.reason_codes == ("INSUFFICIENT_SAMPLE",)


def test_storage_pressure_shortens_prefix_retention() -> None:
    baseline = parameters()
    proposal = SloAutotuner().propose(
        baseline,
        observation(storage_pressure=0.95, unexpected_prefix_miss_rate=0.05),
    )
    assert proposal.candidate.provider_prefix_ttl_seconds < baseline.provider_prefix_ttl_seconds
    assert "REDUCE_PREFIX_TTL_FOR_PRESSURE" in proposal.reason_codes


@pytest.mark.parametrize(
    "invalid",
    [
        {"capacity_bytes": 0},
        {"capacity_bytes": 1, "provider_prefix_ttl_seconds": 1},
        {"capacity_bytes": 1, "context_compaction_soft_ratio": 0.95},
        {"capacity_bytes": 1, "affinity_locality_weight": 10.0},
    ],
)
def test_tuning_parameters_are_bounded(invalid: dict[str, object]) -> None:
    with pytest.raises(ContractViolation):
        CacheTuningParameters(**invalid)  # type: ignore[arg-type]


def test_candidate_starts_in_shadow_and_never_serves_immediately() -> None:
    baseline = parameters()
    state = RolloutState(baseline.digest, None, baseline.digest)
    controller = ProgressiveRolloutController(state, required_windows=2)
    proposal = SloAutotuner().propose(baseline, observation())
    installed = controller.install_candidate(proposal)
    assert installed.phase is RolloutPhase.SHADOW
    assert installed.serving_digest == baseline.digest
    assert installed.candidate_digest == proposal.candidate.digest


def test_rollout_advances_only_after_consecutive_measured_windows() -> None:
    baseline = parameters()
    controller = ProgressiveRolloutController(
        RolloutState(baseline.digest, None, baseline.digest), required_windows=2
    )
    proposal = SloAutotuner().propose(baseline, observation())
    controller.install_candidate(proposal)
    first = controller.observe(evidence())
    assert first.phase is RolloutPhase.SHADOW
    second = controller.observe(evidence())
    assert second.phase is RolloutPhase.INTERNAL
    assert second.serving_digest == proposal.candidate.digest


@pytest.mark.parametrize(
    ("metric", "reason"),
    [
        ("false_hits", RollbackReason.FALSE_HIT),
        ("cross_tenant_hits", RollbackReason.CROSS_TENANT_HIT),
        ("corrupt_executions", RollbackReason.CORRUPT_EXECUTION),
        ("under_validated_publications", RollbackReason.UNDER_VALIDATED_PUBLICATION),
    ],
)
def test_zero_tolerance_incident_immediately_rolls_back(metric: str, reason: RollbackReason) -> None:
    baseline = parameters()
    controller = ProgressiveRolloutController(RolloutState(baseline.digest, None, baseline.digest))
    controller.install_candidate(SloAutotuner().propose(baseline, observation()))
    metrics = dict(passing_report().metrics)
    metrics[metric] = 1
    bad_report = evaluate_parity(
        report_id="bad",
        metrics=metrics,
        cohorts={"representative": metrics},
        scenarios=list(passing_report().scenarios),
        binding=passing_report().binding,
    )
    rolled = controller.observe(evidence(bad_report))
    assert rolled.phase is RolloutPhase.OBSERVE
    assert rolled.serving_digest == baseline.digest
    assert rolled.candidate_digest is None
    assert rolled.rollback_reason is reason


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"provider_accounting_matches": False}, RollbackReason.PROVIDER_ACCOUNTING_MISMATCH),
        ({"worst_cohort_regressed": True}, RollbackReason.FAIRNESS_REGRESSION),
        ({"unknown_outcome_rate": 0.2}, RollbackReason.UNKNOWN_OUTCOME_BUDGET),
        ({"out_of_distribution": True}, RollbackReason.OUT_OF_DISTRIBUTION),
        ({"cost_guardrail_passed": False}, RollbackReason.COST_GUARDRAIL),
    ],
)
def test_operational_guards_roll_back(override: dict[str, object], reason: RollbackReason) -> None:
    baseline = parameters()
    controller = ProgressiveRolloutController(RolloutState(baseline.digest, None, baseline.digest))
    controller.install_candidate(SloAutotuner().propose(baseline, observation()))
    state = controller.observe(evidence(**override))
    assert state.rollback_reason is reason
    assert state.serving_digest == baseline.digest


def test_no_advance_without_tested_fallback_and_rollback() -> None:
    baseline = parameters()
    controller = ProgressiveRolloutController(
        RolloutState(baseline.digest, None, baseline.digest), required_windows=1
    )
    controller.install_candidate(SloAutotuner().propose(baseline, observation()))
    state = controller.observe(evidence(rollback_exercised=False))
    assert state.rollback_reason is RollbackReason.CLEAN_FALLBACK_UNAVAILABLE
