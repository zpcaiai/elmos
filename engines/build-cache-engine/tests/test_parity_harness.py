from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path

import pytest

import elmos_build_cache.parity_harness as parity_harness_module
from elmos_build_cache.canonical import sha256_bytes
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.parity import (
    MANDATORY_SCENARIOS,
    EvidenceBinding,
    ParityDecision,
    ParityThresholds,
    ScenarioStatus,
)
from elmos_build_cache.parity_harness import (
    CallableScenarioExecutor,
    EvidenceClass,
    MeasurementBundle,
    ParityScenarioHarness,
    RawEvidence,
    ReplayMetadata,
    ScenarioCase,
    ScenarioCorpus,
    ScenarioExecution,
    ScenarioRequest,
)
from elmos_build_cache.security import Ed25519ProvenanceSigner, HmacProvenanceSigner


def digest(label: str) -> str:
    return sha256_bytes(label.encode())


def exact_corpus(*, first_timeout: float = 2.0) -> ScenarioCorpus:
    return ScenarioCorpus.from_cases(
        [
            ScenarioCase(
                scenario_id=scenario_id,
                input_digest=digest(f"input:{scenario_id}"),
                timeout_seconds=first_timeout if index == 0 else 2.0,
                parameters={"fixture_id": f"fixture:{scenario_id}"},
            )
            for index, scenario_id in enumerate(MANDATORY_SCENARIOS)
        ]
    )


def evidence_binding(corpus: ScenarioCorpus, *, corpus_digest: str | None = None) -> EvidenceBinding:
    return EvidenceBinding(
        source_digest=digest("source"),
        configuration_digest=digest("config"),
        provider_profiles_digest=digest("providers"),
        corpus_digest=corpus_digest or corpus.digest,
        platform_digest=digest("platform"),
        generated_at="2026-08-20T12:00:00Z",
        executor_identity="synthetic-runner",
        verifier_identity="independent-reviewer",
    )


def passing_metrics() -> dict[str, float | int]:
    metrics: dict[str, float | int] = asdict(ParityThresholds())
    metrics.update(
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
    return metrics


def measured_bundle(
    *,
    metrics: dict[str, float | int] | None = None,
    cohorts: dict[str, dict[str, float | int]] | None = None,
) -> MeasurementBundle:
    return MeasurementBundle(
        measurement_id="synthetic-measurement-1",
        producer_identity="synthetic-runner",
        evidence_class=EvidenceClass.SYNTHETIC_ENGINEERING,
        global_metrics=passing_metrics() if metrics is None else metrics,
        cohorts={"python-small": passing_metrics()} if cohorts is None else cohorts,
        raw_evidence=(RawEvidence("metrics-json", "application/json", b'{"synthetic":true}'),),
        replay=ReplayMetadata(
            replay_id="measurement-replay-1",
            runner="pytest-fake-measurement-runner",
            runner_version="1",
            request_digest=digest("measurement-plan"),
        ),
    )


class FakeExecutor:
    identity = "synthetic-runner"
    evidence_class = EvidenceClass.SYNTHETIC_ENGINEERING

    def __init__(self, modes: dict[str, str] | None = None) -> None:
        self.modes = modes or {}

    def __call__(self, request: ScenarioRequest) -> ScenarioExecution:
        mode = self.modes.get(request.case.scenario_id, "pass")
        if mode == "timeout":
            raise TimeoutError
        if mode == "error":
            raise RuntimeError("synthetic executor failure")
        if mode == "slow":
            time.sleep(request.case.timeout_seconds * 2.0)
        if mode == "blocked":
            return ScenarioExecution(ScenarioStatus.BLOCKED, reason="synthetic dependency unavailable")
        if mode == "not-run":
            return ScenarioExecution(ScenarioStatus.NOT_RUN, reason="synthetic scenario not requested")
        replay_digest = digest("wrong-request") if mode == "bad-replay" else request.request_digest
        return ScenarioExecution(
            ScenarioStatus.PASS,
            raw_evidence=(
                RawEvidence(
                    "scenario-observation",
                    "application/json",
                    f'{{"scenario":"{request.case.scenario_id}","synthetic":true}}'.encode(),
                ),
            ),
            replay=ReplayMetadata(
                replay_id=f"replay:{request.case.scenario_id}",
                runner="pytest-fake-scenario-runner",
                runner_version="1",
                request_digest=replay_digest,
            ),
            detail={"synthetic_fixture": True},
        )


class IgnoringDeadlineExecutor(FakeExecutor):
    """Negative fixture that never observes the cooperative deadline."""

    def __call__(self, request: ScenarioRequest) -> ScenarioExecution:
        if request.case.scenario_id == MANDATORY_SCENARIOS[0]:
            while True:
                time.sleep(1.0)
        return super().__call__(request)


def passing_callback(request: ScenarioRequest) -> ScenarioExecution:
    """Module-level so spawn-only platforms can transport the callback."""

    return FakeExecutor()(request)


def harness_for(
    tmp_path: Path,
    corpus: ScenarioCorpus,
    executor: FakeExecutor | CallableScenarioExecutor | None = None,
) -> tuple[ParityScenarioHarness, ContentAddressableStore]:
    cas = ContentAddressableStore(tmp_path / "objects")
    selected = executor or FakeExecutor()
    harness = ParityScenarioHarness(
        cas=cas,
        corpus=corpus,
        executors={scenario_id: selected for scenario_id in MANDATORY_SCENARIOS},
    )
    return harness, cas


def test_complete_synthetic_corpus_is_evidence_bound_but_not_external(tmp_path: Path) -> None:
    corpus = exact_corpus()
    harness, cas = harness_for(tmp_path, corpus)
    result = harness.run(
        report_id="parity-harness-1",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )

    assert result.report.decision is ParityDecision.READY_FOR_EXTERNAL_GATE
    assert len(result.report.scenarios) == len(MANDATORY_SCENARIOS) == 20
    assert result.evidence_class is EvidenceClass.SYNTHETIC_ENGINEERING
    assert result.external_evidence_state == "NOT_RUN"
    assert cas.verify(result.measurement_manifest_digest)
    assert cas.verify(result.report_artifact_digest)

    measurement_manifest = cas.get_document(result.measurement_manifest_digest)
    assert measurement_manifest["evidence_class"] == "SYNTHETIC_ENGINEERING"
    assert measurement_manifest["external_evidence_state"] == "NOT_RUN"
    assert measurement_manifest["binding"] == evidence_binding(corpus).to_dict()
    measurement_raw = measurement_manifest["raw_evidence"][0]
    assert cas.get_bytes(measurement_raw["digest"]) == b'{"synthetic":true}'

    for scenario in result.report.scenarios:
        assert scenario.status is ScenarioStatus.PASS
        assert scenario.detail["evidence_class"] == "SYNTHETIC_ENGINEERING"
        assert scenario.detail["external_evidence_state"] == "NOT_RUN"
        manifest_digest = scenario.detail["execution_manifest_digest"]
        manifest = cas.get_document(manifest_digest)
        assert manifest["request"]["binding"]["source_digest"] == digest("source")
        assert manifest["request"]["binding"]["configuration_digest"] == digest("config")
        assert manifest["request"]["binding"]["provider_profiles_digest"] == digest("providers")
        assert manifest["request"]["binding"]["corpus_digest"] == corpus.digest
        assert manifest["request"]["binding"]["platform_digest"] == digest("platform")
        raw_digest = manifest["raw_evidence"][0]["digest"]
        assert cas.verify(raw_digest)
        assert cas.get_bytes(raw_digest)


def test_corpus_rejects_missing_duplicate_and_noncanonical_order() -> None:
    cases = list(exact_corpus().cases)
    with pytest.raises(ContractViolation, match="exactly the 20"):
        ScenarioCorpus.from_cases(cases[:-1])
    with pytest.raises(ContractViolation, match="duplicate"):
        ScenarioCorpus.from_cases([*cases[:-1], cases[0]])
    cases[0], cases[1] = cases[1], cases[0]
    with pytest.raises(ContractViolation, match="canonical"):
        ScenarioCorpus.from_cases(cases)


def test_harness_requires_exact_executor_coverage(tmp_path: Path) -> None:
    corpus = exact_corpus()
    with pytest.raises(ContractViolation, match="every mandatory scenario"):
        ParityScenarioHarness(
            cas=ContentAddressableStore(tmp_path / "objects"),
            corpus=corpus,
            executors={scenario_id: FakeExecutor() for scenario_id in MANDATORY_SCENARIOS[:-1]},
        )


def test_callable_wrapper_executes_without_a_command_surface(tmp_path: Path) -> None:
    corpus = exact_corpus()
    wrapped = CallableScenarioExecutor(
        identity="synthetic-runner",
        evidence_class=EvidenceClass.SYNTHETIC_ENGINEERING,
        callback=passing_callback,
    )
    harness, _ = harness_for(tmp_path, corpus, wrapped)
    result = harness.run(
        report_id="callable-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )
    assert result.report.decision is ParityDecision.READY_FOR_EXTERNAL_GATE
    assert not hasattr(wrapped, "command")


def test_pass_requires_raw_bytes_and_replay_metadata() -> None:
    with pytest.raises(ContractViolation, match="raw evidence"):
        ScenarioExecution(ScenarioStatus.PASS)
    with pytest.raises(ContractViolation, match="replay"):
        ScenarioExecution(
            ScenarioStatus.PASS,
            raw_evidence=(RawEvidence("observation", "application/json", b"{}"),),
        )
    with pytest.raises(ContractViolation, match="non-empty bytes"):
        RawEvidence("observation", "application/json", b"")


def test_replay_mismatch_becomes_fail_instead_of_pass(tmp_path: Path) -> None:
    corpus = exact_corpus()
    harness, cas = harness_for(tmp_path, corpus, FakeExecutor({"EXACT_RERUN": "bad-replay"}))
    result = harness.run(
        report_id="bad-replay-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )
    scenario = result.report.scenarios[0]
    assert scenario.status is ScenarioStatus.FAIL
    assert scenario.detail["failure_kind"] == "REPLAY_BINDING_MISMATCH"
    assert result.report.decision is ParityDecision.FAILED
    assert cas.verify(scenario.evidence_digests[0])


@pytest.mark.parametrize(
    ("mode", "expected_status", "expected_decision"),
    [
        ("timeout", ScenarioStatus.BLOCKED, ParityDecision.NOT_RUN),
        ("error", ScenarioStatus.FAIL, ParityDecision.FAILED),
        ("blocked", ScenarioStatus.BLOCKED, ParityDecision.NOT_RUN),
        ("not-run", ScenarioStatus.NOT_RUN, ParityDecision.NOT_RUN),
    ],
)
def test_timeout_failure_blocked_and_not_run_are_preserved(
    tmp_path: Path,
    mode: str,
    expected_status: ScenarioStatus,
    expected_decision: ParityDecision,
) -> None:
    corpus = exact_corpus()
    harness, _ = harness_for(tmp_path, corpus, FakeExecutor({"EXACT_RERUN": mode}))
    result = harness.run(
        report_id=f"outcome-{mode}",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )
    assert result.report.scenarios[0].status is expected_status
    assert result.report.decision is expected_decision


def test_executor_that_returns_after_deadline_is_blocked(tmp_path: Path) -> None:
    corpus = exact_corpus(first_timeout=0.001)
    harness, _ = harness_for(tmp_path, corpus, FakeExecutor({"EXACT_RERUN": "slow"}))
    result = harness.run(
        report_id="deadline-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )
    assert result.report.scenarios[0].status is ScenarioStatus.BLOCKED
    assert result.report.scenarios[0].detail["failure_kind"] == "HARD_DEADLINE_EXCEEDED"
    assert result.report.scenarios[0].detail["worker_reclaimed"] is True
    assert result.report.decision is ParityDecision.NOT_RUN


def test_executor_that_permanently_ignores_deadline_is_killed_and_reaped(tmp_path: Path) -> None:
    corpus = exact_corpus(first_timeout=0.02)
    harness, _ = harness_for(tmp_path, corpus, IgnoringDeadlineExecutor())
    started = time.monotonic()
    result = harness.run(
        report_id="noncooperative-deadline-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )
    elapsed = time.monotonic() - started

    scenario = result.report.scenarios[0]
    assert elapsed < 5.0
    assert scenario.status is ScenarioStatus.BLOCKED
    assert scenario.detail["failure_kind"] == "HARD_DEADLINE_EXCEEDED"
    assert scenario.detail["hard_deadline_enforced"] is True
    assert scenario.detail["worker_reclaimed"] is True
    worker_pid = scenario.detail["worker_pid"]
    assert isinstance(worker_pid, int)
    with pytest.raises(OSError):
        os.kill(worker_pid, 0)
    assert result.report.decision is ParityDecision.NOT_RUN


def test_platform_without_reclaimable_process_is_blocked_without_invoking_executor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = exact_corpus()
    executor = FakeExecutor()
    calls = 0

    def must_not_run(request: ScenarioRequest) -> ScenarioExecution:
        nonlocal calls
        calls += 1
        return executor(request)

    wrapped = CallableScenarioExecutor(
        identity="synthetic-runner",
        evidence_class=EvidenceClass.SYNTHETIC_ENGINEERING,
        callback=must_not_run,
    )
    harness, _ = harness_for(tmp_path, corpus, wrapped)
    monkeypatch.setattr(
        parity_harness_module.multiprocessing,
        "get_all_start_methods",
        lambda: [],
    )
    result = harness.run(
        report_id="no-process-isolation-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
    )
    assert calls == 0
    assert result.report.decision is ParityDecision.NOT_RUN
    assert all(item.status is ScenarioStatus.BLOCKED for item in result.report.scenarios)
    assert all(
        item.detail["failure_kind"] == "HARD_DEADLINE_ISOLATION_UNAVAILABLE"
        for item in result.report.scenarios
    )


def test_missing_metrics_are_not_filled_with_favourable_defaults(tmp_path: Path) -> None:
    corpus = exact_corpus()
    metrics = passing_metrics()
    del metrics["environment_snapshot_hit"]
    harness, _ = harness_for(tmp_path, corpus)
    result = harness.run(
        report_id="missing-metric-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(metrics=metrics),
    )
    assert result.report.decision is ParityDecision.NOT_RUN
    assert "global:environment_snapshot_hit" in result.report.missing


def test_weak_cohort_is_not_hidden_by_global_metrics(tmp_path: Path) -> None:
    corpus = exact_corpus()
    weak = passing_metrics()
    weak["stable_turn_cached_token_reuse"] = 0.1
    harness, _ = harness_for(tmp_path, corpus)
    result = harness.run(
        report_id="weak-cohort-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(cohorts={"healthy": passing_metrics(), "weak": weak}),
    )
    assert result.report.decision is ParityDecision.FAILED
    assert any("cohort:weak" in failure for failure in result.report.failures)


def test_binding_must_match_corpus_and_executor_identity(tmp_path: Path) -> None:
    corpus = exact_corpus()
    harness, _ = harness_for(tmp_path, corpus)
    with pytest.raises(ContractViolation, match="exact scenario corpus"):
        harness.run(
            report_id="wrong-corpus-run",
            binding=evidence_binding(corpus, corpus_digest=digest("different-corpus")),
            measurements=measured_bundle(),
        )

    wrong_producer = MeasurementBundle(
        measurement_id="wrong-producer",
        producer_identity="different-runner",
        evidence_class=EvidenceClass.SYNTHETIC_ENGINEERING,
        global_metrics=passing_metrics(),
        cohorts={"python-small": passing_metrics()},
        raw_evidence=(RawEvidence("metrics", "application/json", b"{}"),),
        replay=ReplayMetadata("replay", "runner", "1", digest("plan")),
    )
    with pytest.raises(ContractViolation, match="measurement producer"):
        harness.run(
            report_id="wrong-producer-run",
            binding=evidence_binding(corpus),
            measurements=wrong_producer,
        )


def test_measurement_bundle_requires_raw_evidence() -> None:
    with pytest.raises(ContractViolation, match="non-empty raw evidence"):
        MeasurementBundle(
            measurement_id="missing-evidence",
            producer_identity="synthetic-runner",
            evidence_class=EvidenceClass.SYNTHETIC_ENGINEERING,
            global_metrics=passing_metrics(),
            cohorts={"python-small": passing_metrics()},
            raw_evidence=(),
            replay=ReplayMetadata("replay", "runner", "1", digest("plan")),
        )


def test_optional_signature_requires_asymmetric_signer(tmp_path: Path) -> None:
    corpus = exact_corpus()
    harness, cas = harness_for(tmp_path, corpus)
    signer = Ed25519ProvenanceSigner.generate("parity-harness-key")
    result = harness.run(
        report_id="signed-harness-run",
        binding=evidence_binding(corpus),
        measurements=measured_bundle(),
        signer=signer,
    )
    assert result.signed_report is not None
    assert result.signature_artifact_digest is not None
    assert cas.verify(result.signature_artifact_digest)
    Ed25519ProvenanceSigner.verifier(signer.public_keyset()).verify_statement(result.signed_report)

    with pytest.raises(ContractViolation, match="asymmetric"):
        harness.run(
            report_id="symmetric-harness-run",
            binding=evidence_binding(corpus),
            measurements=measured_bundle(),
            signer=HmacProvenanceSigner({"dev": b"development-only"}, "dev"),
        )
