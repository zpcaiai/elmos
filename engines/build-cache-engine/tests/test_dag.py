"""DAG-001..003: minimal affected closure, edge semantics and determinism."""

from __future__ import annotations

import pytest

from elmos_build_cache.dag import (
    CacheProbe,
    ConversionDag,
    DagNode,
    EdgeKind,
    Granularity,
    NodeDecision,
    PlanExecutionRecord,
    ProbeResult,
)
from elmos_build_cache.enums import MissReason
from elmos_build_cache.errors import ContractViolation, NotFound


def build_dag() -> ConversionDag:
    """Two independent modules; ``order`` imports ``user``'s public interface."""
    dag = ConversionDag()

    def node(node_id: str, granularity: Granularity, cost: int, **kwargs: object) -> None:
        dag.add_node(
            DagNode(node_id, node_id.split(":", 1)[0], granularity, estimated_cost_ms=cost, **kwargs)  # type: ignore[arg-type]
        )

    node("parse:user", Granularity.FILE, 200)
    node("parse:order", Granularity.FILE, 200)
    node("ir:user", Granularity.IR_PARTITION, 300)
    node("ir:order", Granularity.IR_PARTITION, 300)
    node("gen:user", Granularity.GENERATED_FILE, 900, logical_outputs=("src/User.cs",))
    node("gen:order", Granularity.GENERATED_FILE, 900, logical_outputs=("src/Order.cs",))
    node("compile", Granularity.COMPILE_TARGET, 1500)
    node("test:shard1", Granularity.TEST_SHARD, 700)

    # Same-unit production chains carry everything.
    dag.add_edge("parse:user", "ir:user", EdgeKind.SEQUENCING)
    dag.add_edge("parse:order", "ir:order", EdgeKind.SEQUENCING)
    dag.add_edge("ir:user", "gen:user", EdgeKind.SEQUENCING)
    dag.add_edge("ir:order", "gen:order", EdgeKind.SEQUENCING)
    # Cross-unit dependency carries interface changes only.
    dag.add_edge("ir:user", "ir:order", EdgeKind.PUBLIC_INTERFACE)
    dag.add_edge("gen:user", "compile", EdgeKind.SEQUENCING)
    dag.add_edge("gen:order", "compile", EdgeKind.SEQUENCING)
    dag.add_edge("compile", "test:shard1", EdgeKind.BEHAVIOR)
    return dag


def hits(*node_ids: str) -> CacheProbe:
    wanted = set(node_ids)

    def resolver(node: DagNode) -> ProbeResult:
        if node.node_id in wanted:
            return ProbeResult(True, "sha256:" + "a" * 64, ())
        return ProbeResult(False, "sha256:" + "b" * 64, (MissReason.NO_ENTRY,))

    return CacheProbe(resolver)


def test_dag_001_private_body_change_leaves_unrelated_dependents_cached() -> None:
    """DAG-001: a body change does not cross a PUBLIC_INTERFACE edge."""
    dag = build_dag()
    closure = dag.affected_closure(behavior_changed=["parse:user"])
    assert set(closure) == {"parse:user", "ir:user", "gen:user", "compile", "test:shard1"}
    assert "ir:order" not in closure
    assert "gen:order" not in closure


def test_dag_002_public_interface_change_invalidates_dependents() -> None:
    """DAG-002: an interface change propagates across module boundaries."""
    dag = build_dag()
    closure = dag.affected_closure(interface_changed=["ir:user"])
    assert {"ir:user", "gen:user", "ir:order", "gen:order", "compile"} <= set(closure)
    assert "parse:order" not in closure
    assert any("PUBLIC_INTERFACE" in reason for reason in closure["ir:order"])


def test_dag_003_unaffected_nodes_are_restored_from_cache() -> None:
    """DAG-003: a compatible hit restores instead of executing."""
    dag = build_dag()
    closure = dag.affected_closure(behavior_changed=["parse:user"])
    plan = dag.plan(closure, hits("parse:order", "ir:order", "gen:order"))

    assert plan.decision_of("ir:order").decision is NodeDecision.RESTORE
    assert plan.decision_of("gen:order").decision is NodeDecision.RESTORE
    assert plan.decision_of("ir:user").decision is NodeDecision.INVALIDATED
    assert set(plan.to_execute()) >= {"parse:user", "ir:user", "gen:user", "compile"}


def test_every_decision_carries_a_reason() -> None:
    dag = build_dag()
    plan = dag.plan(dag.affected_closure(interface_changed=["ir:user"]), hits("parse:user"))
    for node_plan in plan.nodes:
        assert node_plan.reasons, node_plan.node_id


def test_plan_is_deterministic() -> None:
    dag = build_dag()
    closure = dag.affected_closure(behavior_changed=["parse:user"])
    first = dag.plan(closure, hits("parse:order", "ir:order"))
    second = dag.plan(closure, hits("parse:order", "ir:order"))
    assert first.plan_digest == second.plan_digest
    assert first.waves == second.waves


def test_waves_respect_dependencies_and_critical_path() -> None:
    dag = build_dag()
    plan = dag.plan({}, hits())
    position = {node_id: index for index, wave in enumerate(plan.waves) for node_id in wave}
    for edge in dag.edges:
        assert position[edge.source] < position[edge.target], edge
    # The most expensive remaining path is scheduled first within a wave.
    assert plan.waves[0][0] == "parse:user"


def test_cycle_is_rejected() -> None:
    dag = ConversionDag()
    dag.add_node(DagNode("a", "a", Granularity.FILE))
    dag.add_node(DagNode("b", "b", Granularity.FILE))
    dag.add_edge("a", "b")
    dag.add_edge("b", "a")
    with pytest.raises(ContractViolation, match="cycle"):
        dag.topological_order()


def test_edge_to_unknown_node_is_rejected() -> None:
    dag = ConversionDag()
    dag.add_node(DagNode("a", "a", Granularity.FILE))
    with pytest.raises(NotFound):
        dag.add_edge("a", "ghost")


def test_shared_logical_output_requires_arbitration() -> None:
    dag = build_dag()
    dag.add_node(
        DagNode("gen:user-symbol", "gen", Granularity.SYMBOL, logical_outputs=("src/User.cs",))
    )
    contested = dag.contested_outputs()
    assert contested == {"src/User.cs": ["gen:user", "gen:user-symbol"]}
    # Finest granularity wins, and the decision is recorded on the plan.
    assert dag.arbitrate_outputs()["src/User.cs"] == "gen:user-symbol"
    assert dag.plan({}, hits()).arbitration["src/User.cs"] == "gen:user-symbol"


def test_non_idempotent_side_effects_are_rejected() -> None:
    dag = ConversionDag()
    with pytest.raises(ContractViolation):
        dag.add_node(
            DagNode("publish", "publish", Granularity.REPOSITORY, side_effects=("notify",), idempotent=False)
        )


def test_bypass_mode_never_probes_the_cache() -> None:
    from elmos_build_cache.enums import CacheMode

    dag = ConversionDag()
    dag.add_node(DagNode("a", "a", Granularity.FILE, cache_mode=CacheMode.BYPASS))
    plan = dag.plan({}, hits("a"))
    assert plan.decision_of("a").decision is NodeDecision.EXECUTE
    assert MissReason.POLICY_BYPASS in plan.decision_of("a").miss_reasons


def test_blocked_nodes_are_reported_not_executed() -> None:
    dag = build_dag()
    plan = dag.plan({}, hits(), blocked=["compile"])
    assert plan.decision_of("compile").decision is NodeDecision.BLOCKED


def test_plan_versus_actual_divergence_is_visible() -> None:
    dag = build_dag()
    plan = dag.plan(dag.affected_closure(behavior_changed=["parse:user"]), hits("ir:order"))
    record = PlanExecutionRecord(plan)
    for node_plan in plan.nodes:
        record.record(node_plan.node_id, node_plan.decision.value)
    assert record.divergences() == []
    record.record("ir:order", "EXECUTE")
    assert record.divergences() == [
        {"node_id": "ir:order", "planned": "RESTORE", "actual": "EXECUTE"}
    ]


def test_all_declared_granularities_are_supported() -> None:
    dag = ConversionDag()
    for index, granularity in enumerate(Granularity):
        dag.add_node(DagNode(f"n{index}", "stage", granularity))
    assert len(dag.nodes) == len(Granularity)
    assert len(dag.topological_order()) == len(Granularity)
