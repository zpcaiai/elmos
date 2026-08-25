"""OBS-001..002 and PERF-001..002: attribution, correlation and budgets."""

from __future__ import annotations

import time

import pytest

from elmos_build_cache.clock import ManualClock
from elmos_build_cache.enums import MissReason
from elmos_build_cache.observability import (
    ALLOWED_LABELS,
    BENCHMARK_SCENARIOS,
    SPAN_LOOKUP,
    SPAN_MATERIALIZE,
    BenchmarkResult,
    CacheAccounting,
    MetricsRegistry,
    PerformanceGate,
    Slo,
    Tracer,
    TuningKnobs,
    correlation_fields,
    safe_labels,
    summarize_run,
    tenant_bucket,
)


def test_obs_001_miss_reasons_are_attributed_per_stage() -> None:
    """OBS-001: a miss names the exact dimension, per stage, not globally."""
    accounting = CacheAccounting()
    accounting.record_hit("source-parse", saved_cpu_ms=800)
    accounting.record_miss(
        "target-code-generation",
        [MissReason.RULE_PACK_CHANGED, MissReason.MODEL_SNAPSHOT_CHANGED],
        executed_cpu_ms=4200,
    )
    overall = accounting.overall()
    generation = next(item for item in overall["stages"] if item["stage_id"] == "target-code-generation")

    assert generation["miss_reasons"] == {"MODEL_SNAPSHOT_CHANGED": 1, "RULE_PACK_CHANGED": 1}
    assert generation["hit_rate"] == 0.0
    parse = next(item for item in overall["stages"] if item["stage_id"] == "source-parse")
    assert parse["hit_rate"] == 1.0
    assert accounting.top_miss_reasons()[0][1] == 1


def test_obs_002_failure_traces_correlate_every_identifier(clock: ManualClock) -> None:
    """OBS-002: run/node/ActionKey/artifact/staged-file/checkpoint all correlate."""
    tracer = Tracer(clock=clock)
    fields = correlation_fields(
        run_id="run-1",
        node_id="gen:user",
        action_key="sha256:" + "7" * 64,
        artifact_digest="sha256:" + "a" * 64,
        staged_file_id="sf_1",
        checkpoint_id="cp_1",
        lease_epoch=3,
    )
    with pytest.raises(RuntimeError):
        with tracer.span("elmos.stage.execute", stage_id="target-code-generation", **fields):
            raise RuntimeError("stage blew up")

    span = tracer.spans[-1]
    assert span.status == "ERROR"
    assert span.events[0]["type"] == "RuntimeError"
    assert set(fields) <= set(span.attributes)
    # Digests are truncated in attributes unless disclosure is enabled.
    assert span.attributes["action_key"].endswith("...")


def test_metric_labels_are_bounded_and_never_sensitive() -> None:
    labels = safe_labels(
        {
            "stage_id": "target-code-generation",
            "logical_path": "src/User.cs",
            "prompt": "generate a class",
            "action_key_digest": "sha256:abc",
            "run_id": "run-1",
            "outcome": "hit",
        }
    )
    assert labels == {"outcome": "hit", "stage_id": "target-code-generation"}
    assert "logical_path" not in ALLOWED_LABELS
    assert tenant_bucket("tenant-a") != tenant_bucket("tenant-b")


def test_prometheus_exposition_is_renderable() -> None:
    registry = MetricsRegistry()
    registry.increment("elmos_cache_hits_total", 3, stage_id="compile", outcome="local")
    registry.gauge("elmos_workspace_bytes", 4096)
    registry.observe("elmos_span_duration_ms", 12.5, stage_id="compile")
    text = registry.expose()
    assert 'elmos_cache_hits_total{outcome="local",stage_id="compile"} 3.0' in text
    assert "elmos_workspace_bytes 4096" in text
    assert "elmos_span_duration_ms_p95" in text


def test_perf_001_no_change_rerun_meets_the_budget(clock: ManualClock) -> None:
    """PERF-001: an identical rerun must clear the declared reuse floor."""
    gate = PerformanceGate()
    tracer = Tracer(clock=clock)
    with tracer.span(SPAN_LOOKUP, stage_id="compile"):
        pass
    benchmarks = {
        "identical-rerun": BenchmarkResult("identical-rerun", 0.98, 1200.0, 42000.0, 120000),
        "private-body": BenchmarkResult("private-body", 0.82, 5400.0, 21000.0, 60000),
    }
    outcome = gate.evaluate(tracer, benchmarks)
    named = {item["name"]: item for item in outcome["results"]}
    assert named["no-change-reuse"]["passed"] is True
    assert named["small-change-reuse"]["passed"] is True
    assert outcome["passed"] is True


def test_perf_002_a_reuse_regression_fails_the_gate(clock: ManualClock) -> None:
    """PERF-002: falling below the small-change budget is a release blocker."""
    gate = PerformanceGate()
    tracer = Tracer(clock=clock)
    benchmarks = {
        "identical-rerun": BenchmarkResult("identical-rerun", 0.99, 1000.0, 40000.0, 100000),
        "private-body": BenchmarkResult("private-body", 0.31, 30000.0, 2000.0, 5000),
    }
    outcome = gate.evaluate(tracer, benchmarks)
    named = {item["name"]: item for item in outcome["results"]}
    assert named["small-change-reuse"]["passed"] is False
    assert outcome["passed"] is False


#: Long enough that the gate's verdict cannot turn on measurement noise.
SLOW_SPAN_SECONDS = 0.005


def test_latency_slo_breach_is_reported(clock: ManualClock) -> None:
    """A span over its budget fails the gate; the same span inside one passes.

    This used to assert a breach from an *empty* span against ``budget_ms=0.0``,
    which only ever worked by accident. ``Tracer.span`` times with
    ``time.perf_counter`` -- the injected ``ManualClock`` only stamps
    ``started_at`` -- and ``Histogram.summary`` rounds p95 to three decimals,
    i.e. to the microsecond. An empty span on a fast host measures a few
    hundred nanoseconds, rounds to exactly ``0.0`` ms, and ``0.0 <= 0.0``
    correctly reports no breach; this container's slower interpreter happened
    to round to ``0.001`` and hid it. That test measured the host, not the gate.

    ``time.sleep`` can only overshoot, so a 5 ms span against a 1 ms budget is
    a breach on any machine at any load, and the same span against a 10 s
    budget is a pass -- which also proves the gate discriminates rather than
    failing everything. The ``<=`` boundary itself is pinned separately, in
    ``test_a_measurement_exactly_at_budget_is_not_a_breach``.
    """
    tracer = Tracer(clock=clock)
    with tracer.span(SPAN_LOOKUP, stage_id="compile"):
        time.sleep(SLOW_SPAN_SECONDS)

    breached = PerformanceGate([Slo("lookup-p95", SPAN_LOOKUP, 0.95, budget_ms=1.0)]).evaluate(tracer, {})
    assert breached["passed"] is False
    assert breached["results"][0]["budget_ms"] == 1.0
    assert breached["results"][0]["observed"] > 1.0

    within_budget = PerformanceGate(
        [Slo("lookup-p95", SPAN_LOOKUP, 0.95, budget_ms=10_000.0)]
    ).evaluate(tracer, {})
    assert within_budget["passed"] is True


def test_a_measurement_exactly_at_budget_is_not_a_breach() -> None:
    """A latency budget is "at most", so landing exactly on it passes.

    Pinned deliberately: the tempting "fix" for a flaky zero-budget test is to
    turn ``Slo.evaluate``'s ``observed <= budget_ms`` into ``<``, which would
    make every SLO in ``DEFAULT_SLOS`` reject its own stated budget.
    """
    at_budget = Slo("lookup-p95", SPAN_LOOKUP, 0.95, budget_ms=50.0)
    assert at_budget.evaluate(50.0)["passed"] is True
    assert at_budget.evaluate(50.001)["passed"] is False
    assert at_budget.evaluate(49.999)["passed"] is True


def test_all_ten_benchmark_scenarios_are_declared() -> None:
    assert len(BENCHMARK_SCENARIOS) == 10
    assert "remote-outage-recovery" in BENCHMARK_SCENARIOS


def test_tuning_recommendations_are_derived_from_measurements(clock: ManualClock) -> None:
    accounting = CacheAccounting()
    accounting.record_miss("target-code-generation", [MissReason.MODEL_SNAPSHOT_CHANGED])
    accounting.record_incident("nondeterminism")
    accounting.record_incident("quota")
    tracer = Tracer(clock=clock)
    advice = TuningKnobs().recommend(accounting, tracer)
    assert any("target-code-generation" in item for item in advice)
    assert any("quota" in item for item in advice)
    assert any("nondeterministic" in item for item in advice)


def test_quiet_system_produces_no_false_advice(clock: ManualClock) -> None:
    accounting = CacheAccounting()
    accounting.record_hit("compile")
    advice = TuningKnobs().recommend(accounting, Tracer(clock=clock))
    assert advice == ["no tuning action indicated by the current measurements"]


def test_summary_reports_savings_and_incidents(clock: ManualClock) -> None:
    accounting = CacheAccounting()
    accounting.record_hit("compile", saved_cpu_ms=9000, saved_wall_ms=12000, saved_compiler_ms=8000)
    accounting.record_hit("target-code-generation", source="remote", saved_model_tokens=42000)
    accounting.record_storage(stored=1024, deduplicated=512, restored=256)
    accounting.record_transfer(uploaded=2048, downloaded=1024)
    accounting.record_workspace(bytes_used=4096, files=12)
    tracer = Tracer(clock=clock)
    with tracer.span(SPAN_MATERIALIZE, stage_id="compile"):
        pass

    report = summarize_run(accounting, tracer)
    assert report["accounting"]["saved"]["model_tokens"] == 42000
    assert report["accounting"]["bytes"]["deduplicated"] == 512
    assert report["accounting"]["workspace"]["files"] == 12
    assert SPAN_MATERIALIZE in report["spans"]
    assert report["accounting"]["overall_hit_rate"] == 1.0
