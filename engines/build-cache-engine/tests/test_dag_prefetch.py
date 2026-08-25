"""Prefetch driven by the real plan, and bounded by real budgets.

Every assertion here starts from a `ConversionDag` built the way the pipeline
builds one, because the whole claim of this module is that ELMOS does not have
to guess: the next consumer is in the graph. The other half is the budget --
horizon, concurrency, bandwidth -- and what happens when a prediction is wrong.
"""

from __future__ import annotations

import pytest

from elmos_build_cache.dag import ConversionDag, DagNode, EdgeKind, Granularity
from elmos_build_cache.dag_prefetch import (
    Artifact,
    FutureUseIndex,
    LocalityScheduler,
    PrefetchBudget,
    PrefetchPlanner,
    PrefetchReason,
    restore_or_recompute,
)
from elmos_build_cache.errors import ContractViolation


def chain(length: int = 6) -> ConversionDag:
    dag = ConversionDag()
    for index in range(length):
        dag.add_node(
            DagNode(
                f"n{index}",
                "target-code-generation",
                Granularity.GENERATED_FILE,
                logical_outputs=(f"art{index}",),
                estimated_cost_ms=1000,
            )
        )
    for index in range(length - 1):
        dag.add_edge(f"n{index}", f"n{index + 1}", EdgeKind.PUBLIC_INTERFACE)
    return dag


def artifacts(count: int = 6, **kwargs: object) -> dict[str, Artifact]:
    base: dict[str, object] = {"size_bytes": 2_000_000, "restore_ms": 40.0, "recompute_ms": 2_000.0}
    base.update(kwargs)
    return {f"art{index}": Artifact(key=f"art{index}", **base) for index in range(count)}  # type: ignore[arg-type]


# ==========================================================================
# the index comes from the plan
# ==========================================================================
def test_the_index_is_built_from_declared_dependencies_only() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    assert index.order == tuple(f"n{i}" for i in range(6))
    # n1 consumes what n0 declared, and nothing else.
    assert index.consumes["n1"] == ("art0",)
    assert index.consumes["n0"] == ()
    assert index.known_future("art0") is True
    assert index.known_future("never-declared") is False


def test_next_use_is_a_distance_in_scheduled_steps() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    assert index.next_use("art0", 0) == 1
    assert index.next_use("art3", 0) == 4
    assert index.next_use("art0", 3) is None, "a consumed artifact has no future use"


def test_protection_covers_exactly_the_horizon() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    assert sorted(index.protected_keys(0, 1)) == ["art0"]
    assert sorted(index.protected_keys(0, 3)) == ["art0", "art1", "art2"]


def test_victims_are_ranked_by_furthest_next_use_then_cost_density() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    ranked = sorted(index.artifacts, key=lambda key: index.victim_rank(key, 0))
    # The artifact used furthest in the future is the first victim.
    assert ranked[0] == "art5"
    assert ranked[-1] == "art0"


def test_a_consumer_outside_the_plan_is_refused() -> None:
    with pytest.raises(ContractViolation, match="outside the planned order"):
        FutureUseIndex(("n0",), {"n0": ("a",), "ghost": ("b",)}, {})


# ==========================================================================
# budgets
# ==========================================================================
def test_prefetch_is_issued_in_earliest_beneficial_use_order() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=4, max_in_flight=3))
    issued = planner.plan(0)
    assert [decision.key for decision in issued] == ["art0", "art1", "art2"]
    assert all(decision.reason == PrefetchReason.ISSUED.value for decision in issued)


def test_the_horizon_bounds_what_is_fetched() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=1, max_in_flight=10))
    assert [decision.key for decision in planner.plan(0)] == ["art0"]
    assert planner.metrics.skipped[PrefetchReason.SKIPPED_BEYOND_HORIZON.value] >= 4


def test_the_concurrency_budget_is_enforced() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=6, max_in_flight=2))
    assert len(planner.plan(0)) == 2
    assert planner.metrics.skipped[PrefetchReason.SKIPPED_CONCURRENCY_BUDGET.value] >= 1


def test_the_byte_budget_is_enforced() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(
        index, PrefetchBudget(horizon=6, max_in_flight=10, max_bytes=3_000_000)
    )
    assert len(planner.plan(0)) == 1
    assert planner.metrics.skipped[PrefetchReason.SKIPPED_BANDWIDTH_BUDGET.value] >= 1


def test_a_resident_object_is_not_fetched_again() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=6, max_in_flight=10))
    issued = planner.plan(0, resident=["art0", "art1"])
    assert "art0" not in [decision.key for decision in issued]
    assert planner.metrics.skipped[PrefetchReason.SKIPPED_ALREADY_RESIDENT.value] >= 2


def test_an_object_cheaper_to_rebuild_is_not_fetched() -> None:
    """SOTA-08 at planning time, before any bytes move."""
    index = FutureUseIndex.from_dag(chain(), artifacts(recompute_ms=10.0))
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=6, bandwidth_bytes_per_ms=1_000.0))
    assert planner.plan(0) == []
    assert planner.metrics.skipped[PrefetchReason.BYPASS_RECOMPUTE_CHEAPER.value] >= 1


# ==========================================================================
# outcomes
# ==========================================================================
def test_a_used_prefetch_counts_as_precision_and_saved_critical_path() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index)
    issued = planner.plan(0)
    for decision in issued:
        planner.observe_consumption(decision.key, arrived_in_time=True)
    assert planner.metrics.precision == 1.0
    assert planner.metrics.critical_path_saved_ms > 0
    assert planner.metrics.late_rate == 0.0


def test_a_late_prefetch_is_counted_but_saves_nothing() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index)
    issued = planner.plan(0)
    planner.observe_consumption(issued[0].key, arrived_in_time=False)
    assert planner.metrics.late == 1
    assert planner.metrics.critical_path_saved_ms == 0.0


def test_an_unused_prefetch_is_counted_as_wasted_bytes() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index)
    issued = planner.plan(0)
    planner.observe_unused(issued[0].key)
    assert planner.metrics.wasted_bytes == 2_000_000
    assert planner.metrics.precision < 1.0


def test_cancellation_stops_paying_for_a_resolved_branch() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=6, max_in_flight=4))
    issued = planner.plan(0)
    cancelled = planner.cancel([decision.key for decision in issued[:2]])
    assert cancelled == 2
    assert planner.metrics.cancelled == 2
    assert planner.metrics.wasted_bytes == 4_000_000


def test_wrong_predictions_switch_prefetching_off() -> None:
    """A prefetcher that cannot be throttled is a bandwidth incident waiting."""
    index = FutureUseIndex.from_dag(chain(20), artifacts(20))
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=20, max_in_flight=20))
    issued = planner.plan(0)
    assert len(issued) >= 8
    for decision in issued:
        planner.observe_unused(decision.key)
    assert planner.should_throttle() is True


def test_throttling_needs_evidence_not_one_bad_guess() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    planner = PrefetchPlanner(index, PrefetchBudget(horizon=1))
    planner.plan(0)
    assert planner.should_throttle() is False


# ==========================================================================
# restore or recompute
# ==========================================================================
def test_a_slow_link_makes_recomputation_the_right_answer() -> None:
    decision, explanation = restore_or_recompute(
        Artifact("big", 600_000_000, restore_ms=100.0, recompute_ms=5_000.0),
        PrefetchBudget(bandwidth_bytes_per_ms=20_000.0),
    )
    assert decision == "RECOMPUTE"
    assert explanation["reason"] == PrefetchReason.BYPASS_RECOMPUTE_CHEAPER.value
    assert explanation["transfer_ms"] > explanation["recompute_ms"]


def test_a_fast_link_makes_restoring_the_right_answer() -> None:
    decision, explanation = restore_or_recompute(
        Artifact("small", 2_000_000, restore_ms=10.0, recompute_ms=5_000.0),
        PrefetchBudget(bandwidth_bytes_per_ms=20_000.0),
    )
    assert decision == "RESTORE"
    assert explanation["transfer_ms"] < explanation["recompute_ms"]


def test_decompression_is_part_of_the_comparison() -> None:
    artifact = Artifact("archive", 40_000_000, restore_ms=10.0, recompute_ms=2_100.0)
    budget = PrefetchBudget(bandwidth_bytes_per_ms=20_000.0)
    assert restore_or_recompute(artifact, budget)[0] == "RESTORE"
    assert restore_or_recompute(artifact, budget, decompression_ms=1_000.0)[0] == "RECOMPUTE"


# ==========================================================================
# placement
# ==========================================================================
def test_a_node_is_placed_where_its_inputs_already_are() -> None:
    index = FutureUseIndex.from_dag(chain(8), artifacts(8))
    scheduler = LocalityScheduler(index, ["w1", "w2"], fair_share_slack=4.0)
    first = scheduler.place("n0")
    second = scheduler.place("n1")
    assert second.worker == first.worker
    assert second.reason == "CACHE_LOCALITY"
    assert second.resident_bytes > 0


def test_locality_gives_way_to_fairness() -> None:
    """A scheduler that only chases locality starves half the fleet."""
    index = FutureUseIndex.from_dag(chain(12), artifacts(12))
    scheduler = LocalityScheduler(index, ["w1", "w2", "w3"], fair_share_slack=1.0)
    placements = [scheduler.place(f"n{index}") for index in range(9)]
    used = {placement.worker for placement in placements}
    assert used == {"w1", "w2", "w3"}


def test_at_least_one_worker_is_required() -> None:
    index = FutureUseIndex.from_dag(chain(), artifacts())
    with pytest.raises(ContractViolation):
        LocalityScheduler(index, [])
