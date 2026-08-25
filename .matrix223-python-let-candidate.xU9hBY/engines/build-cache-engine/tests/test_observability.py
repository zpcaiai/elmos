"""OBS-001..002 and PERF-001..002: attribution, correlation and budgets."""

from __future__ import annotations

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


def test_latency_slo_breach_is_reported(clock: ManualClock) -> None:
    tracer = Tracer(clock=clock)
    slow = Slo("lookup-p95", SPAN_LOOKUP, 0.95, budget_ms=0.0)
    with tracer.span(SPAN_LOOKUP, stage_id="compile"):
        pass
    outcome = PerformanceGate([slow]).evaluate(tracer, {})
    assert outcome["passed"] is False


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
