from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal

import pytest

from elmos_commercial_expansion.errors import ContractError
from elmos_commercial_expansion.kernels import _local_algorithms as algorithms
from elmos_commercial_expansion.kernels._local_algorithms import (
    build_explainability_ledger,
    classify_monotonic_risk,
    dependency_closed_slice,
    evaluate_rubric_scorecard,
    incident_causal_divergence,
    lineage_impact_closure,
    optimize_cost_latency_quality,
    progressive_disclosure,
    reconcile_keyed_rows,
    route_constrained_candidate,
    select_affected_tests,
    typed_graph_closure,
    validate_provenance_bindings,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _edges() -> list[dict[str, object]]:
    return [
        {"source": "api", "target": "service"},
        {"source": "service", "target": "database"},
        {"source": "service", "target": "events"},
    ]


def test_provenance_validates_closure_dag_and_is_order_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bindings = {"app": _digest("a"), "lib": _digest("b"), "runtime": _digest("c")}
    dependencies = {"app": ["lib"], "lib": ["runtime"], "runtime": []}
    result = validate_provenance_bindings(bindings, dependencies)
    reordered = validate_provenance_bindings(
        dict(reversed(tuple(bindings.items()))),
        {"runtime": [], "lib": ["runtime"], "app": ["lib"]},
    )
    assert result == reordered
    assert result["topological_order"] == ("runtime", "lib", "app")
    with pytest.raises(ContractError) as cycle:
        validate_provenance_bindings(bindings, {"app": ["lib"], "lib": ["app"], "runtime": []})
    assert cycle.value.code == "PROVENANCE_CYCLE"
    monkeypatch.setattr(algorithms, "MAX_EDGES", 1)
    with pytest.raises(ContractError) as limited:
        validate_provenance_bindings(bindings, dependencies)
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_provenance_large_fanout_uses_heap_without_reordering_the_ready_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bindings = {f"node-{index:05d}": _digest("a") for index in range(2_000)}
    dependencies = {name: [] for name in bindings}

    class NoSortDeque:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("topological scheduling must not rebuild sorted deques")

    monkeypatch.setattr(algorithms, "deque", NoSortDeque)
    result = validate_provenance_bindings(bindings, dependencies)
    assert result["binding_count"] == 2_000
    assert result["topological_order"] == tuple(sorted(bindings))


def _skill_metadata() -> list[dict[str, object]]:
    return [
        {
            "id": "db-small",
            "summary": "database migration",
            "tags": ["database"],
            "tokens": 3,
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "environment": "prod",
            "permissions": ["read"],
        },
        {
            "id": "db-large",
            "summary": "database migration and database validation",
            "tags": ["database", "migration"],
            "tokens": 8,
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "environment": "prod",
            "permissions": ["read"],
        },
        {
            "id": "other-tenant",
            "summary": "database migration",
            "tags": ["database"],
            "tokens": 1,
            "tenant_id": "tenant-b",
            "project_id": "project-a",
            "environment": "prod",
            "permissions": ["read"],
        },
    ]


def _context() -> dict[str, object]:
    return {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "environment": "prod",
        "permissions": ["read"],
    }


def test_progressive_disclosure_filters_scope_budgets_and_is_order_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _skill_metadata()
    result = progressive_disclosure(records, _context(), ["database", "migration"], 8)
    reordered = progressive_disclosure(list(reversed(records)), _context(), ["migration", "database"], 8)
    assert result == reordered
    assert result["selected_skill_ids"] == ("db-small",)
    assert result["deferred_skill_ids"] == ("db-large",)
    assert "other-tenant" not in result["selected_skill_ids"]
    bad = deepcopy(records)
    bad[0]["permissions"] = ["admin"]
    filtered = progressive_disclosure(bad, _context(), ["database"], 8)
    assert filtered["selected_skill_ids"] == ("db-large",)
    assert "db-small" not in filtered["selected_skill_ids"]
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 1)
    with pytest.raises(ContractError) as limited:
        progressive_disclosure(records, _context(), ["database"], 8)
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_progressive_disclosure_rejects_unbounded_query_term_scans() -> None:
    terms = [f"term-{index}" for index in range(algorithms.MAX_QUERY_TERMS + 1)]
    with pytest.raises(ContractError) as limited:
        progressive_disclosure(_skill_metadata(), _context(), terms, 8)
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _router_candidates() -> list[dict[str, object]]:
    return [
        {
            "id": "safe",
            "capabilities": ["compile", "test"],
            "cost": "5",
            "latency_ms": 100,
            "quality": "0.90",
            "proof": 4,
            "risk": 5,
        },
        {
            "id": "cheap-no-proof",
            "capabilities": ["compile", "test"],
            "cost": "1",
            "latency_ms": 10,
            "quality": "0.99",
            "proof": 1,
            "risk": 1,
        },
    ]


def _router_constraints() -> dict[str, object]:
    return {
        "required_capabilities": ["compile", "test"],
        "max_cost": "10",
        "max_latency_ms": 1000,
        "min_quality": "0.8",
        "min_proof": 3,
        "max_risk": 20,
    }


def test_router_enforces_hard_constraints_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    candidates = _router_candidates()
    result = route_constrained_candidate(candidates, _router_constraints())
    assert result == route_constrained_candidate(list(reversed(candidates)), _router_constraints())
    assert result["selected_id"] == "safe"
    with pytest.raises(ContractError) as infeasible:
        route_constrained_candidate(candidates, {**_router_constraints(), "min_proof": 5})
    assert infeasible.value.code == "NO_FEASIBLE_CANDIDATE"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 1)
    with pytest.raises(ContractError) as limited:
        route_constrained_candidate(candidates, _router_constraints())
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_typed_graph_closure_handles_chains_cycles_order_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes = ["api", "service", "database", "events"]
    result = typed_graph_closure(nodes, _edges(), ["api"])
    reordered = typed_graph_closure(list(reversed(nodes)), list(reversed(_edges())), ["api"])
    assert result == reordered
    assert result["affected_nodes"] == ("api", "database", "events", "service")
    cyclic = [*_edges(), {"source": "database", "target": "api"}]
    assert typed_graph_closure(nodes, cyclic, ["api"])["affected_count"] == 4
    with pytest.raises(ContractError) as dangling:
        typed_graph_closure(nodes, [*_edges(), {"source": "api", "target": "missing"}], ["api"])
    assert dangling.value.code == "INVALID_GRAPH"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 2)
    with pytest.raises(ContractError) as limited:
        typed_graph_closure(nodes, _edges(), ["api"])
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_affected_tests_exposes_uncovered_critical_and_is_order_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes = ["api", "service", "database", "events"]
    coverage = {"api": ["test-api"], "service": ["test-service"], "database": [], "events": ["test-events"]}
    result = select_affected_tests(nodes, _edges(), ["api"], coverage, ["database"])
    reordered = select_affected_tests(
        list(reversed(nodes)),
        list(reversed(_edges())),
        ["api"],
        dict(reversed(tuple(coverage.items()))),
        ["database"],
    )
    assert result == reordered
    assert result["confidence"] == "INCOMPLETE"
    assert result["uncovered_critical_nodes"] == ("database",)
    with pytest.raises(ContractError) as invalid:
        select_affected_tests(nodes, _edges(), ["api"], {"missing": ["test"]}, [])
    assert invalid.value.code == "INVALID_GRAPH"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 2)
    with pytest.raises(ContractError) as limited:
        select_affected_tests(nodes, _edges(), ["api"], coverage, ["database"])
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_dependency_slice_is_closed_all_or_fail_and_order_invariant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes = ["app", "lib", "runtime"]
    edges = [{"source": "app", "target": "lib"}, {"source": "lib", "target": "runtime"}]
    costs = {"app": 3, "lib": 2, "runtime": 1}
    result = dependency_closed_slice(nodes, edges, ["app"], costs, 6)
    reordered = dependency_closed_slice(list(reversed(nodes)), list(reversed(edges)), ["app"], costs, 6)
    assert result == reordered
    assert result["selected_nodes"] == ("app", "lib", "runtime")
    with pytest.raises(ContractError) as budget:
        dependency_closed_slice(nodes, edges, ["app"], costs, 5)
    assert budget.value.code == "SLICE_BUDGET_EXCEEDED"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 2)
    with pytest.raises(ContractError) as limited:
        dependency_closed_slice(nodes, edges, ["app"], costs, 6)
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_risk_is_monotonic_order_invariant_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    low = classify_monotonic_risk(["api", "db"], [], [], [], 0, "1")
    high = classify_monotonic_risk(["db", "api"], ["db"], ["api"], ["db"], 3, "0.5")
    reordered = classify_monotonic_risk(["api", "db"], ["db"], ["api"], ["db"], 3, "0.5")
    assert high == reordered
    assert isinstance(high["score"], int)
    assert isinstance(low["score"], int)
    assert high["score"] >= low["score"]
    with pytest.raises(ContractError) as invalid:
        classify_monotonic_risk(["api"], ["db"], [], [], 0, "1")
    assert invalid.value.code == "INVALID_RISK_INPUT"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 1)
    with pytest.raises(ContractError) as limited:
        classify_monotonic_risk(["api", "db"], [], [], [], 0, "1")
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _ledger_edits() -> list[dict[str, object]]:
    return [
        {
            "sequence": 0,
            "edit_id": "edit-a",
            "path_digest": _digest("a"),
            "before_digest": _digest("b"),
            "after_digest": _digest("c"),
            "rule_id": "rule-a",
            "reason": "required migration",
            "source_evidence_digests": [_digest("d")],
            "assumptions": ["exact version"],
            "validation_digests": [_digest("e")],
            "rollback_digest": _digest("f"),
        },
        {
            "sequence": 1,
            "edit_id": "edit-b",
            "path_digest": _digest("1"),
            "before_digest": _digest("2"),
            "after_digest": _digest("3"),
            "rule_id": "rule-b",
            "reason": "preserve contract",
            "source_evidence_digests": [_digest("4")],
            "assumptions": [],
            "validation_digests": [_digest("5")],
            "rollback_digest": _digest("6"),
        },
    ]


def test_explainability_ledger_hash_chain_is_order_invariant_and_tamper_evident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    edits = _ledger_edits()
    result = build_explainability_ledger(edits)
    assert result == build_explainability_ledger(list(reversed(edits)))
    tampered = deepcopy(edits)
    tampered[0]["reason"] = "different reason"
    assert build_explainability_ledger(tampered)["ledger_digest"] != result["ledger_digest"]
    invalid = deepcopy(edits)
    invalid[1]["sequence"] = 3
    with pytest.raises(ContractError) as sequence:
        build_explainability_ledger(invalid)
    assert sequence.value.code == "INVALID_LEDGER_SEQUENCE"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 1)
    with pytest.raises(ContractError) as limited:
        build_explainability_ledger(edits)
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _lineage_entities() -> list[dict[str, object]]:
    return [
        {"id": "raw", "kind": "dataset"},
        {"id": "clean", "kind": "dataset"},
        {"id": "report", "kind": "dataset"},
    ]


def _lineage_edges() -> list[dict[str, object]]:
    return [
        {"source": "raw", "target": "clean", "kind": "dataset"},
        {"source": "clean", "target": "report", "kind": "dataset"},
    ]


def test_lineage_closure_is_typed_downstream_order_invariant_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = lineage_impact_closure(_lineage_entities(), _lineage_edges(), ["raw"])
    reordered = lineage_impact_closure(
        list(reversed(_lineage_entities())), list(reversed(_lineage_edges())), ["raw"]
    )
    assert result == reordered
    assert result["affected_consumers"] == ("clean", "report")
    invalid_edges = [{"source": "raw", "target": "clean", "kind": "table"}]
    with pytest.raises(ContractError) as invalid:
        lineage_impact_closure(_lineage_entities(), invalid_edges, ["raw"])
    assert invalid.value.code == "INVALID_LINEAGE"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 2)
    with pytest.raises(ContractError) as limited:
        lineage_impact_closure(_lineage_entities(), _lineage_edges(), ["raw"])
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _source_rows() -> list[dict[str, object]]:
    return [
        {"id": 1, "amount": Decimal("1.10"), "value": "a"},
        {"id": 2, "amount": Decimal("2.20"), "value": "b"},
        {"id": 2, "amount": Decimal("2.20"), "value": "b"},
    ]


def test_keyed_decimal_reconciliation_preserves_duplicates_order_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _source_rows()
    result = reconcile_keyed_rows(rows, list(reversed(rows)), ["id"], ["amount"])
    assert result["equivalent"] is True
    assert result["duplicate_key_rows"] == {"source": 1, "target": 1}
    changed = deepcopy(rows)
    changed[-1]["amount"] = Decimal("2.21")
    mismatch = reconcile_keyed_rows(rows, changed, ["id"], ["amount"])
    assert mismatch["equivalent"] is False
    assert mismatch["aggregate_deltas"] == {"amount": "0.01"}
    assert isinstance(mismatch["mismatched_key_digests"], tuple)
    assert len(mismatch["mismatched_key_digests"]) == 1
    with pytest.raises(ContractError) as binary_float:
        reconcile_keyed_rows([{"id": 1, "amount": 1.1}], [], ["id"], ["amount"])
    assert binary_float.value.code == "INVALID_RECONCILIATION_ROW"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 2)
    with pytest.raises(ContractError) as limited:
        reconcile_keyed_rows(rows, rows, ["id"], ["amount"])
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _rubric() -> list[dict[str, object]]:
    return [
        {"metric": "quality", "weight": "0.7", "minimum": "0.8", "mandatory": True},
        {"metric": "coverage", "weight": "0.3", "minimum": "0.5", "mandatory": False},
    ]


def test_rubric_scorecard_has_hard_mandatory_gates_order_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = {"quality": "0.9", "coverage": "0.6"}
    result = evaluate_rubric_scorecard(observations, _rubric())
    reordered = evaluate_rubric_scorecard(
        dict(reversed(tuple(observations.items()))), list(reversed(_rubric()))
    )
    assert result == reordered
    assert result["decision"] == "PASS_BOUNDED_LOCAL"
    failed = evaluate_rubric_scorecard({"quality": "0.7", "coverage": "1"}, _rubric())
    assert failed["decision"] == "FAIL"
    assert failed["mandatory_failures"] == ("quality",)
    with pytest.raises(ContractError) as missing:
        evaluate_rubric_scorecard({"quality": "0.9"}, _rubric())
    assert missing.value.code == "INVALID_RUBRIC"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 1)
    with pytest.raises(ContractError) as limited:
        evaluate_rubric_scorecard(observations, _rubric())
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _events() -> list[dict[str, object]]:
    return [
        {
            "sequence": 0,
            "event_id": "root",
            "parent_id": None,
            "kind": "start",
            "payload_digest": _digest("a"),
        },
        {
            "sequence": 1,
            "event_id": "child",
            "parent_id": "root",
            "kind": "tool",
            "payload_digest": _digest("b"),
        },
    ]


def test_incident_divergence_finds_first_cause_and_rejects_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = _events()
    assert incident_causal_divergence(events, list(reversed(events)))["equivalent"] is True
    observed = deepcopy(events)
    observed[1]["payload_digest"] = _digest("c")
    result = incident_causal_divergence(events, observed)
    assert result["first_divergence_sequence"] == 1
    invalid = deepcopy(events)
    invalid[1]["sequence"] = 2
    with pytest.raises(ContractError) as gap:
        incident_causal_divergence(events, invalid)
    assert gap.value.code == "INCIDENT_REPLAY_INCONCLUSIVE"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 1)
    with pytest.raises(ContractError) as limited:
        incident_causal_divergence(events, events)
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def _optimizer_candidates() -> list[dict[str, object]]:
    return [
        {"id": "balanced", "cost": "5", "latency_ms": 50, "quality": "0.9", "proof_satisfied": True},
        {"id": "dominated", "cost": "6", "latency_ms": 60, "quality": "0.8", "proof_satisfied": True},
        {"id": "fast", "cost": "7", "latency_ms": 20, "quality": "0.9", "proof_satisfied": True},
        {"id": "cheap-no-proof", "cost": "1", "latency_ms": 10, "quality": "1", "proof_satisfied": False},
    ]


def _optimizer_constraints() -> dict[str, object]:
    return {"max_cost": "10", "max_latency_ms": 100, "min_quality": "0.8", "proof_required": True}


def test_optimizer_returns_pareto_frontier_without_quality_proof_compensation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = _optimizer_candidates()
    result = optimize_cost_latency_quality(candidates, _optimizer_constraints())
    assert result == optimize_cost_latency_quality(list(reversed(candidates)), _optimizer_constraints())
    assert result["pareto_frontier_ids"] == ("balanced", "fast")
    assert result["selected_id"] == "balanced"
    with pytest.raises(ContractError) as infeasible:
        optimize_cost_latency_quality(candidates, {**_optimizer_constraints(), "min_quality": "1.1"})
    assert infeasible.value.code == "NO_FEASIBLE_CANDIDATE"
    monkeypatch.setattr(algorithms, "MAX_ITEMS", 2)
    with pytest.raises(ContractError) as limited:
        optimize_cost_latency_quality(candidates, _optimizer_constraints())
    assert limited.value.code == "LOCAL_INPUT_LIMIT"


def test_optimizer_handles_maximum_tradeoff_frontier_and_identical_metrics() -> None:
    # Each candidate contributes six canonical JSON nodes, so 8,000 records
    # exercise the largest practical frontier below the global 50,000-node cap.
    candidate_count = 8_000
    candidates = [
        {
            "id": f"candidate-{index:05d}",
            "cost": str(index + 1),
            "latency_ms": candidate_count - index,
            "quality": "0.9",
            "proof_satisfied": True,
        }
        for index in range(candidate_count)
    ]
    constraints = {
        "max_cost": str(candidate_count),
        "max_latency_ms": candidate_count,
        "min_quality": "0.8",
        "proof_required": True,
    }
    result = optimize_cost_latency_quality(candidates, constraints)
    assert result["feasible_count"] == candidate_count
    assert len(result["pareto_frontier_ids"]) == candidate_count

    identical = [
        {
            "id": "same-a",
            "cost": "1",
            "latency_ms": 1,
            "quality": "1",
            "proof_satisfied": True,
        },
        {
            "id": "same-b",
            "cost": "1",
            "latency_ms": 1,
            "quality": "1",
            "proof_satisfied": True,
        },
    ]
    duplicate_result = optimize_cost_latency_quality(
        identical,
        {
            "max_cost": "1",
            "max_latency_ms": 1,
            "min_quality": "1",
            "proof_required": True,
        },
    )
    assert duplicate_result["pareto_frontier_ids"] == ("same-a", "same-b")


def test_every_public_algorithm_rejects_noncanonical_total_input() -> None:
    huge = "x" * (algorithms.MAX_TEXT_BYTES + 1)
    calls: tuple[Callable[[], object], ...] = (
        lambda: validate_provenance_bindings({huge: _digest("a")}, {huge: []}),
        lambda: progressive_disclosure([], {"tenant_id": huge}, [], 1),
        lambda: route_constrained_candidate([], {"required_capabilities": [huge]}),
        lambda: typed_graph_closure([huge], [], [huge]),
        lambda: select_affected_tests([huge], [], [huge], {}, []),
        lambda: dependency_closed_slice([huge], [], [huge], {huge: 1}, 1),
        lambda: classify_monotonic_risk([huge], [], [], [], 0, "1"),
        lambda: build_explainability_ledger([{"reason": huge}]),
        lambda: lineage_impact_closure([{"id": huge}], [], []),
        lambda: reconcile_keyed_rows([{"id": huge}], [], ["id"]),
        lambda: evaluate_rubric_scorecard({huge: "1"}, []),
        lambda: incident_causal_divergence([{"event_id": huge}], []),
        lambda: optimize_cost_latency_quality([{"id": huge}], {}),
    )
    for call in calls:
        with pytest.raises(ContractError) as limited:
            call()
        assert limited.value.code == "LOCAL_INPUT_LIMIT"
