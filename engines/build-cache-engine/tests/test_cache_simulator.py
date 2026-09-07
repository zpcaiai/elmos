"""Replay, and the report that comes out of it.

The metrics are checked against a hand-computed trace rather than against
themselves: if `avoided_compute_ratio` is wrong, no amount of internal
consistency will show it. The rest of the file is about the two properties that
make a comparison trustworthy -- identical treatment of every arm, and a report
whose shape is the one the package's schema specifies.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from elmos_build_cache.cache_policy import PolicyName, create_policy
from elmos_build_cache.cache_simulator import (
    BenchmarkGates,
    ObjectiveProfile,
    benchmark,
    recommended_capacity,
    replay,
    weighted_value,
)
from elmos_build_cache.cache_trace import GENERATORS, CacheTraceEvent, Tier, key_hash
from elmos_build_cache.errors import ContractViolation

SCHEMA = Path("/tmp/sota/elmos-build-cache-staging-sota-skills-v1.1.0/references/schemas")
PACKAGED_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "cache-benchmark-report.schema.json"


def event(
    key: str,
    size: int,
    *,
    recompute: float = 100.0,
    restore: float = 10.0,
    tokens: int = 0,
    weight: float = 0.0,
    stage: str = "ir",
    tenant: str = "t",
) -> CacheTraceEvent:
    return CacheTraceEvent(
        event_id=f"evt-{key}",
        timestamp_bucket=0,
        tier=Tier.L1_LOCAL_CAS.value,
        key_hash=key_hash(key),
        namespace_hash=key_hash(tenant),
        size_bytes=size,
        access="GET",
        stage_class=stage,
        recompute_ms=recompute,
        restore_ms=restore,
        model_tokens=tokens,
        critical_path_weight=weight,
    )


# ==========================================================================
# the metrics, against arithmetic
# ==========================================================================
def test_metrics_match_a_hand_computed_trace() -> None:
    """Four requests, two of them hits, everything checked by hand."""
    trace = [
        event("a", 1000, recompute=100, restore=10, tokens=500, weight=1.0),
        event("b", 3000, recompute=200, restore=20),
        event("a", 1000, recompute=100, restore=10, tokens=500, weight=1.0),
        event("b", 3000, recompute=200, restore=20),
    ]
    result = replay("LRU", trace, 10_000)

    assert result.requests == 4
    assert result.hits == 2 and result.misses == 2
    assert result.request_bytes == 8000
    assert result.hit_bytes == 4000
    assert result.byte_hit_ratio == 0.5
    assert result.object_hit_ratio == 0.5
    assert result.total_recompute_ms == 600.0
    assert result.avoided_recompute_ms == 300.0  # 100 + 200 on the two hits
    assert result.avoided_compute_ratio == 0.5
    assert result.restore_ms_on_hits == 30.0
    assert result.net_saved_ms == 270.0
    assert result.total_model_tokens == 1000 and result.avoided_model_tokens == 500
    assert result.avoided_model_token_ratio == 0.5
    assert result.critical_path_saved_ms == 90.0  # 1.0 × (100 − 10)


def test_a_restore_slower_than_a_rebuild_is_not_counted_as_a_win() -> None:
    """SOTA-08: a hit that costs more than the miss is a bypass, not a hit."""
    trace = [
        event("slow", 1000, recompute=100, restore=99),
        event("slow", 1000, recompute=100, restore=99),
    ]
    result = replay("LRU", trace, 10_000)
    assert result.hits == 0
    assert result.restore_bypasses == 1
    assert result.avoided_recompute_ms == 0.0


def test_warmup_events_populate_the_cache_without_being_measured() -> None:
    trace = [event(f"k{index % 4}", 1000) for index in range(20)]
    warmed = replay("LRU", trace, 10_000, warmup=8)
    cold = replay("LRU", trace, 10_000)
    assert warmed.requests == 12 and cold.requests == 20
    assert warmed.object_hit_ratio > cold.object_hit_ratio


def test_cohorts_expose_a_regression_an_average_would_hide() -> None:
    trace = [event(f"hot{index % 2}", 1000, stage="ir", tenant="big") for index in range(40)]
    trace += [event(f"cold{index}", 1000, stage="generation", tenant="small") for index in range(40)]
    result = replay("LRU", trace, 8_000)
    rows = {(row["cohort"], row["name"]): row for row in result.cohorts()}
    stages = {name for (cohort, name) in rows if cohort == "stage"}
    assert stages == {"ir", "generation"}
    assert rows[("stage", "ir")]["object_hit_ratio"] > rows[("stage", "generation")]["object_hit_ratio"]


def test_tenant_names_never_reach_the_report() -> None:
    trace = [event(f"k{index}", 1000, tenant=f"tenant-{index % 3}") for index in range(30)]
    rows = replay("LRU", trace, 10_000).cohorts()
    for row in rows:
        if row["cohort"] == "tenant":
            assert row["name"].startswith("tenant-") and len(row["name"]) <= 10
            assert "sha256" not in row["name"]


def test_a_broken_key_contract_is_counted_as_a_correctness_failure() -> None:
    """The same exact key with two sizes is never smoothed over."""
    trace = [event("k", 1000), event("k", 2000)]
    result = replay("LRU", trace, 10_000)
    assert result.correctness_failures == 1


# ==========================================================================
# determinism and equal treatment
# ==========================================================================
@pytest.mark.parametrize("policy_name", [name.value for name in PolicyName])
def test_replay_is_deterministic(policy_name: str) -> None:
    """SOTA-01: three runs, identical metrics."""
    events = GENERATORS["single-file-edit"]().events
    runs = [replay(policy_name, events, 4_000_000).metrics() for _ in range(3)]
    for metrics in runs[1:]:
        assert {k: v for k, v in metrics.items() if k != "p95_decision_micros"} == {
            k: v for k, v in runs[0].items() if k != "p95_decision_micros"
        }


def test_every_arm_of_a_benchmark_gets_identical_conditions() -> None:
    corpus = GENERATORS["large-binaries"]()
    report = benchmark(corpus, capacity_bytes=10_000_000)
    capacities = {candidate["configuration"]["capacity_bytes"] for candidate in report["candidates"]}
    requests = {candidate["metrics"]["requests"] for candidate in report["candidates"]}
    request_bytes = {candidate["metrics"]["request_bytes"] for candidate in report["candidates"]}
    assert capacities == {10_000_000}
    assert len(requests) == 1 and len(request_bytes) == 1


def test_the_baseline_is_always_present_even_if_not_requested() -> None:
    report = benchmark(GENERATORS["model-change"](), policies=("SIEVE",), baseline="LRU")
    assert {candidate["policy"] for candidate in report["candidates"]} == {"LRU", "SIEVE"}


def test_an_empty_trace_is_refused() -> None:
    with pytest.raises(ContractViolation, match="empty trace"):
        benchmark([])


def test_a_policy_instance_and_a_capacity_must_agree() -> None:
    policy = create_policy("LRU", 1000)
    with pytest.raises(ContractViolation, match="capacity disagrees"):
        replay(policy, GENERATORS["model-change"]().events, 2000)


# ==========================================================================
# objectives and gates
# ==========================================================================
def test_the_objective_changes_which_policy_looks_best() -> None:
    """The point of profiles: "better" is not one number."""
    events = GENERATORS["identical-rerun"]().events
    capacity = recommended_capacity(events, 0.2)
    gdsf = replay("GDSF", events, capacity)
    lru = replay("LRU", events, capacity)
    # GDSF keeps the expensive artifacts, which is invisible to a hit count.
    assert weighted_value(gdsf, ObjectiveProfile.DEV_SPEED) > weighted_value(lru, ObjectiveProfile.DEV_SPEED)


def test_a_candidate_that_does_not_clear_the_margin_is_not_selected() -> None:
    report = benchmark(
        GENERATORS["identical-rerun"](),
        gates=BenchmarkGates(minimum_weighted_improvement=0.99),
    )
    assert report["gates"]["selected"] is None
    assert "NO_CANDIDATE_CLEARED_THE_GATES" in report["gates"]["reasons"]
    assert report["selector_recommendation"]["confidence"] == 0.0


def test_a_decision_overhead_budget_can_reject_an_otherwise_better_policy() -> None:
    report = benchmark(
        GENERATORS["monorepo-scan"](),
        gates=BenchmarkGates(maximum_p95_decision_micros=0.0),
    )
    failures = {
        name: verdict["failures"] for name, verdict in report["gates"]["verdicts"].items()
    }
    assert any("DECISION_OVERHEAD_ABOVE_BUDGET" in reasons for reasons in failures.values())


def test_selection_is_reproducible_including_ties() -> None:
    corpus = GENERATORS["monorepo-scan"]()
    first = benchmark(corpus)["gates"]["selected"]
    second = benchmark(corpus)["gates"]["selected"]
    assert first == second


# ==========================================================================
# the report shape
# ==========================================================================
@pytest.mark.parametrize("workload", ["monorepo-scan", "large-binaries", "multi-tenant-burst"])
def test_the_report_validates_against_the_packaged_schema(workload: str) -> None:
    schema = json.loads(PACKAGED_SCHEMA.read_text(encoding="utf-8"))
    report = benchmark(GENERATORS[workload](), created_at="2026-08-19T10:00:00+00:00")
    jsonschema.validate(report, schema)


def test_the_report_carries_the_evidence_a_reader_needs() -> None:
    report = benchmark(GENERATORS["interface-edit"]())
    assert report["trace_corpus_digest"].startswith("sha256:")
    assert report["workload_features"]["request_count"] > 0
    assert report["gates"]["thresholds"]["minimum_weighted_improvement"] >= 0
    assert all("weighted_value" in candidate["metrics"] for candidate in report["candidates"])
    assert report["cohorts"]
