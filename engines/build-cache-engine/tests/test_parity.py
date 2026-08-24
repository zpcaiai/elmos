from __future__ import annotations

from dataclasses import asdict

import pytest

from elmos_build_cache.canonical import sha256_bytes
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.parity import (
    MANDATORY_SCENARIOS,
    EvidenceBinding,
    ParityDecision,
    ParityThresholds,
    ScenarioResult,
    ScenarioStatus,
    evaluate_parity,
    weighted_reuse,
)
from elmos_build_cache.security import Ed25519ProvenanceSigner, HmacProvenanceSigner


def digest(label: str) -> str:
    return sha256_bytes(label.encode())


def binding() -> EvidenceBinding:
    return EvidenceBinding(
        source_digest=digest("source"),
        configuration_digest=digest("config"),
        provider_profiles_digest=digest("providers"),
        corpus_digest=digest("corpus"),
        platform_digest=digest("platform"),
        generated_at="2026-08-20T12:00:00Z",
        executor_identity="runner-a",
        verifier_identity="reviewer-b",
    )


def passing_metrics() -> dict[str, float | int]:
    values: dict[str, float | int] = asdict(ParityThresholds())
    values.update(
        {
            "stable_turn_cached_token_reuse": 0.94,
            "unexpected_full_prefix_miss": 0.01,
            "exact_rerun_weighted_reuse": 1.0,
            "small_edit_weighted_reuse": 0.93,
            "unnecessary_invalidation": 0.02,
            "environment_snapshot_hit": 0.97,
            "warm_start_p95_reduction": 0.84,
            "restart_artifact_reuse": 1.0,
            "stable_followup_wall_clock_saved": 0.75,
            "model_input_cost_saved": 0.85,
            "long_session_cached_token_reuse": 0.83,
        }
    )
    return values


def passing_scenarios() -> list[ScenarioResult]:
    return [
        ScenarioResult(name, ScenarioStatus.PASS, (digest(f"evidence:{name}"),))
        for name in MANDATORY_SCENARIOS
    ]


def evaluate(**overrides: object):
    arguments: dict[str, object] = {
        "report_id": "parity-1",
        "metrics": passing_metrics(),
        "cohorts": {"python-small": passing_metrics(), "java-large": passing_metrics()},
        "scenarios": passing_scenarios(),
        "binding": binding(),
    }
    arguments.update(overrides)
    return evaluate_parity(**arguments)  # type: ignore[arg-type]


def test_complete_measured_report_is_only_ready_for_external_gate() -> None:
    report = evaluate()
    assert report.decision is ParityDecision.READY_FOR_EXTERNAL_GATE
    assert report.mandatory_pass
    assert report.failures == ()
    assert report.missing == ()
    assert report.to_dict()["claim_policy"] == "measured_only_external_gate_required"


def test_missing_metric_or_scenario_stays_not_run() -> None:
    metrics = passing_metrics()
    del metrics["environment_snapshot_hit"]
    report = evaluate(metrics=metrics, scenarios=passing_scenarios()[:-1])
    assert report.decision is ParityDecision.NOT_RUN
    assert "global:environment_snapshot_hit" in report.missing
    assert "scenario:CROSS_TENANT_NEGATIVE" in report.missing


def test_missing_cohorts_stays_not_run() -> None:
    report = evaluate(cohorts={})
    assert report.decision is ParityDecision.NOT_RUN
    assert "cohorts" in report.missing


@pytest.mark.parametrize(
    "metric",
    [
        "redundant_validated_rerun_calls",
        "false_hits",
        "cross_tenant_hits",
        "corrupt_executions",
        "under_validated_publications",
    ],
)
def test_every_zero_tolerance_metric_blocks(metric: str) -> None:
    metrics = passing_metrics()
    metrics[metric] = 1
    report = evaluate(metrics=metrics)
    assert report.decision is ParityDecision.FAILED
    assert any(metric in failure for failure in report.failures)


def test_worst_cohort_blocks_a_good_global_average() -> None:
    weak = passing_metrics()
    weak["stable_turn_cached_token_reuse"] = 0.5
    report = evaluate(cohorts={"good": passing_metrics(), "weak": weak})
    assert report.decision is ParityDecision.FAILED
    assert any("cohort:weak" in failure for failure in report.failures)


def test_failed_and_blocked_scenarios_are_not_conflated() -> None:
    scenarios = passing_scenarios()
    scenarios[0] = ScenarioResult("EXACT_RERUN", ScenarioStatus.FAIL, (digest("failure"),))
    scenarios[1] = ScenarioResult("STABLE_10_TURN", ScenarioStatus.BLOCKED)
    report = evaluate(scenarios=scenarios)
    assert report.decision is ParityDecision.NOT_RUN
    assert "scenario:EXACT_RERUN:FAIL" in report.failures
    assert "scenario:STABLE_10_TURN:BLOCKED" in report.missing


def test_passed_scenario_requires_raw_evidence() -> None:
    with pytest.raises(ContractViolation, match="requires raw evidence"):
        ScenarioResult("EXACT_RERUN", ScenarioStatus.PASS)


def test_duplicate_scenario_is_rejected() -> None:
    scenarios = passing_scenarios()
    scenarios.append(scenarios[0])
    with pytest.raises(ContractViolation, match="duplicate"):
        evaluate(scenarios=scenarios)


def test_report_digest_is_deterministic_across_mapping_order() -> None:
    metrics = passing_metrics()
    reverse = dict(reversed(list(metrics.items())))
    left = evaluate(metrics=metrics)
    right = evaluate(metrics=reverse)
    assert left.report_digest == right.report_digest


def test_report_can_be_signed_and_verified_with_public_key_only() -> None:
    report = evaluate()
    signer = Ed25519ProvenanceSigner.generate("parity-key")
    signed = report.sign(signer)
    verifier = Ed25519ProvenanceSigner.verifier(signer.public_keyset())
    verifier.verify_statement(signed)


def test_symmetric_report_signing_is_refused() -> None:
    report = evaluate()
    signer = HmacProvenanceSigner({"dev": b"not-production"}, "dev")
    with pytest.raises(ContractViolation, match="asymmetric"):
        report.sign(signer)


def test_executor_cannot_self_verify() -> None:
    with pytest.raises(ContractViolation, match="independent"):
        EvidenceBinding(
            digest("source"),
            digest("config"),
            digest("provider"),
            digest("corpus"),
            digest("platform"),
            "2026-08-20T12:00:00Z",
            "same",
            "same",
        )


def test_zero_tolerance_thresholds_cannot_be_weakened() -> None:
    with pytest.raises(ContractViolation, match="cannot be weakened"):
        ParityThresholds(false_hits=1)


def test_package_parity_thresholds_can_only_be_made_stricter() -> None:
    with pytest.raises(ContractViolation, match="minimum parity threshold"):
        ParityThresholds(stable_turn_cached_token_reuse=0.0)
    with pytest.raises(ContractViolation, match="maximum parity threshold"):
        ParityThresholds(unexpected_full_prefix_miss=1.0)

    strict = ParityThresholds(
        stable_turn_cached_token_reuse=0.95,
        unexpected_full_prefix_miss=0.01,
    )
    assert strict.stable_turn_cached_token_reuse == 0.95
    assert strict.unexpected_full_prefix_miss == 0.01


def test_weighted_reuse_uses_avoided_compute_not_object_count() -> None:
    assert weighted_reuse([(True, 90.0), (False, 10.0)]) == 0.9
    with pytest.raises(ContractViolation, match="positive eligible denominator"):
        weighted_reuse([])
    with pytest.raises(ContractViolation, match="cannot be negative"):
        weighted_reuse([(True, -1.0)])
