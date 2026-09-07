"""Deterministic v2 adaptive-decomposition, graph, and scheduling primitives."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .contracts import (
    ContractError,
    decimal_value,
    finite_probability,
    normalize_relative_path,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
)
from .planning import paths_overlap


GRANULARITY_WEIGHTS: Mapping[str, Decimal] = {
    "context_demand": Decimal("0.15"),
    "write_surface": Decimal("0.12"),
    "semantic_breadth": Decimal("0.18"),
    "cross_boundary_coupling": Decimal("0.18"),
    "invariant_density": Decimal("0.15"),
    "verification_distance": Decimal("0.12"),
    "uncertainty": Decimal("0.10"),
}
RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
HIERARCHY_LEVELS = ("goal", "capability", "changeset", "atomic_task", "microstep")
CROSS_TASK_EDGE_TYPES = frozenset({"contract", "schema", "data", "runtime", "integration"})
PROOF_BOUNDARY_KINDS = frozenset(
    {
        "public_api",
        "security",
        "authentication",
        "authorization",
        "transaction",
        "concurrency",
        "idempotency",
        "data_migration",
        "backward_compatibility",
        "distributed_side_effect",
    }
)


def mapping_sequence(
    value: Any, field_name: str, *, allow_empty: bool = True
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContractError("invalid_array", f"{field_name} must be an array of objects")
    result = tuple(require_mapping(item, f"{field_name}[]") for item in value)
    if not result and not allow_empty:
        raise ContractError("invalid_array", f"{field_name} must not be empty")
    return result


def _identifier(value: Any, field_name: str) -> str:
    result = require_string(value, field_name)
    if any(character.isspace() for character in result):
        raise ContractError("invalid_identifier", f"{field_name} must not contain whitespace")
    return result


def _topological(
    node_ids: Sequence[str], edges: Sequence[Mapping[str, Any]]
) -> tuple[tuple[str, ...], Mapping[str, tuple[str, ...]], Mapping[str, int], tuple[str, ...]]:
    if len(node_ids) != len(set(node_ids)):
        raise ContractError("duplicate_node_id", "graph node IDs must be unique")
    known = set(node_ids)
    adjacency: dict[str, list[str]] = {node: [] for node in node_ids}
    indegree = {node: 0 for node in node_ids}
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in edges:
        source = _identifier(raw.get("from"), "edge.from")
        target = _identifier(raw.get("to"), "edge.to")
        edge_type = require_string(raw.get("type", "dependency"), "edge.type")
        key = (source, target, edge_type)
        if key in seen:
            errors.append(f"duplicate_edge:{source}->{target}:{edge_type}")
        seen.add(key)
        if source not in known or target not in known:
            errors.append(f"edge_unknown_node:{source}->{target}")
            continue
        if source == target:
            errors.append(f"self_cycle:{source}")
        adjacency[source].append(target)
        indegree[target] += 1
    degrees = dict(indegree)
    ready = deque(sorted(node for node, degree in degrees.items() if degree == 0))
    order: list[str] = []
    while ready:
        node = ready.popleft()
        order.append(node)
        for target in sorted(adjacency[node]):
            degrees[target] -= 1
            if degrees[target] == 0:
                ready.append(target)
    if len(order) != len(node_ids):
        errors.append("cycle_detected")
    return (
        tuple(order),
        {key: tuple(sorted(value)) for key, value in adjacency.items()},
        indegree,
        tuple(sorted(set(errors))),
    )


@dataclass(frozen=True, slots=True)
class GranularityDecision:
    score: Decimal
    decision: str
    reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "score": format(self.score, "f"),
            "decision": self.decision,
            "reasons": list(self.reasons),
        }


def decide_granularity(
    features: Mapping[str, Any], *, indivisible_invariant: bool, unsafe_split: bool
) -> GranularityDecision:
    unknown = sorted(set(features) - set(GRANULARITY_WEIGHTS))
    if unknown:
        raise ContractError(
            "unknown_granularity_feature",
            "unknown granularity features: " + ", ".join(unknown),
        )
    score = sum(
        finite_probability(features.get(name, "0"), f"features.{name}") * weight
        for name, weight in GRANULARITY_WEIGHTS.items()
    )
    reasons: list[str] = []
    if indivisible_invariant:
        decision = "keep"
        reasons.append("indivisible_invariant")
    elif unsafe_split:
        decision = "merge"
        reasons.append("unsafe_split_requires_merge")
    elif score >= Decimal("0.72"):
        decision = "split"
        reasons.append("score_above_split_threshold")
        if finite_probability(
            features.get("cross_boundary_coupling", "0"),
            "features.cross_boundary_coupling",
        ) >= Decimal("0.8"):
            reasons.append("split_only_at_validated_semantic_seam")
    elif score <= Decimal("0.20"):
        decision = "merge"
        reasons.append("score_below_merge_threshold")
    else:
        decision = "keep"
        reasons.append("within_target_band")
    return GranularityDecision(score.quantize(Decimal("0.000001")), decision, tuple(reasons))


def build_scenario_graph(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    scenarios = mapping_sequence(payload.get("scenarios"), "scenarios", allow_empty=False)
    edges = mapping_sequence(payload.get("edges", []), "edges")
    ids = [_identifier(item.get("id"), "scenario.id") for item in scenarios]
    kinds = {"happy", "failure", "boundary", "compatibility", "rollback", "operational"}
    normalized = []
    for item, scenario_id in zip(scenarios, ids, strict=True):
        kind = require_string(item.get("kind"), "scenario.kind")
        if kind not in kinds:
            raise ContractError("invalid_scenario_kind", f"unsupported scenario kind: {kind}")
        normalized.append(
            {
                "id": scenario_id,
                "kind": kind,
                "statement": require_string(item.get("statement"), "scenario.statement"),
                "evidence_refs": list(
                    require_string_sequence(item.get("evidence_refs", []), "scenario.evidence_refs")
                ),
            }
        )
    _, _, _, errors = _topological(ids, edges)
    observed = {item["kind"] for item in normalized}
    return {
        "scenarios": normalized,
        "edges": [dict(item) for item in edges],
        "graph_errors": list(errors),
        "missing_scenario_kinds": sorted(kinds - observed),
        "digest": sha256_payload({"scenarios": normalized, "edges": edges}),
    }


def build_repository_graph(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nodes = mapping_sequence(payload.get("nodes"), "nodes", allow_empty=False)
    edges = mapping_sequence(payload.get("edges", []), "edges")
    ids = [_identifier(item.get("id"), "node.id") for item in nodes]
    known = set(ids)
    errors: list[str] = []
    normalized_nodes = []
    for item, node_id in zip(nodes, ids, strict=True):
        evidence = require_string_sequence(item.get("evidence_refs", []), "node.evidence_refs")
        if not evidence:
            errors.append(f"node_missing_evidence:{node_id}")
        normalized_nodes.append(
            {
                "id": node_id,
                "kind": require_string(item.get("kind"), "node.kind"),
                "path": normalize_relative_path(item["path"], "node.path") if item.get("path") else None,
                "evidence_refs": list(evidence),
            }
        )
    normalized_edges = []
    for item in edges:
        source = _identifier(item.get("from"), "edge.from")
        target = _identifier(item.get("to"), "edge.to")
        evidence = require_string_sequence(item.get("evidence_refs", []), "edge.evidence_refs")
        if source not in known or target not in known:
            errors.append(f"edge_unknown_node:{source}->{target}")
        if not evidence:
            errors.append(f"edge_missing_evidence:{source}->{target}")
        normalized_edges.append(
            {
                "from": source,
                "to": target,
                "type": require_string(item.get("type"), "edge.type"),
                "evidence_refs": list(evidence),
            }
        )
    body = {
        "revision": require_string(payload.get("revision"), "revision"),
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }
    return {**body, "valid": not errors, "errors": sorted(set(errors)), "digest": sha256_payload(body)}


def mine_implicit_requirements(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = mapping_sequence(payload.get("candidates"), "candidates")
    inferred, explore = [], []
    for item in candidates:
        record = {
            "id": _identifier(item.get("id"), "candidate.id"),
            "statement": require_string(item.get("statement"), "candidate.statement"),
            "confidence": format(
                finite_probability(item.get("confidence"), "candidate.confidence"), "f"
            ),
            "evidence_refs": list(
                require_string_sequence(item.get("evidence_refs", []), "candidate.evidence_refs")
            ),
        }
        if not record["evidence_refs"] or Decimal(record["confidence"]) < Decimal("0.70"):
            explore.append(record)
        else:
            inferred.append(record)
    return {"inferred_requirements": inferred, "exploration_candidates": explore}


def build_invariant_ledger(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    entries = mapping_sequence(payload.get("invariants"), "invariants", allow_empty=False)
    normalized, blocking = [], []
    seen: set[str] = set()
    for item in entries:
        identifier = _identifier(item.get("id"), "invariant.id")
        if identifier in seen:
            raise ContractError("duplicate_invariant", f"duplicate invariant: {identifier}")
        seen.add(identifier)
        risk = require_string(item.get("risk"), "invariant.risk").lower()
        if risk not in RISK_RANK:
            raise ContractError("invalid_risk", f"invalid invariant risk: {risk}")
        status = require_string(item.get("status", "UNVERIFIED"), "invariant.status").upper()
        if status not in {"VERIFIED", "UNVERIFIED", "VIOLATED"}:
            raise ContractError("invalid_invariant_status", f"invalid invariant status: {status}")
        evidence = require_string_sequence(item.get("evidence_refs", []), "invariant.evidence_refs")
        if status == "VERIFIED" and not evidence:
            raise ContractError("verified_without_evidence", f"invariant {identifier} has no evidence")
        record = {
            "id": identifier,
            "statement": require_string(item.get("statement"), "invariant.statement"),
            "risk": risk,
            "status": status,
            "scope": list(require_string_sequence(item.get("scope", []), "invariant.scope")),
            "evidence_refs": list(evidence),
        }
        normalized.append(record)
        if RISK_RANK[risk] >= RISK_RANK["high"] and status != "VERIFIED":
            blocking.append(identifier)
    return {"invariants": normalized, "blocking_high_risk": sorted(blocking), "digest": sha256_payload(normalized)}


def detect_semantic_seams(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = mapping_sequence(payload.get("candidates"), "candidates")
    safe, unsafe = [], []
    for item in candidates:
        record = {
            "id": _identifier(item.get("id"), "seam.id"),
            "semantic_cohesion": finite_probability(item.get("semantic_cohesion"), "semantic_cohesion"),
            "cross_boundary_coupling": finite_probability(item.get("cross_boundary_coupling"), "cross_boundary_coupling"),
            "verification_locality": finite_probability(item.get("verification_locality"), "verification_locality"),
            "cuts_indivisible_invariant": bool(item.get("cuts_indivisible_invariant", False)),
        }
        score = (
            record["semantic_cohesion"]
            * (Decimal("1") - record["cross_boundary_coupling"])
            * record["verification_locality"]
        ).quantize(Decimal("0.000001"))
        output = {
            "id": record["id"],
            "seam_score": format(score, "f"),
            "cuts_indivisible_invariant": record["cuts_indivisible_invariant"],
        }
        if record["cuts_indivisible_invariant"] or score < Decimal("0.15"):
            unsafe.append(output)
        else:
            safe.append(output)
    safe.sort(key=lambda item: (-Decimal(item["seam_score"]), item["id"]))
    return {"recommended_seams": safe, "unsafe_seams": unsafe}


def build_hierarchical_plan(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    nodes = mapping_sequence(payload.get("nodes"), "nodes", allow_empty=False)
    normalized, identifiers = [], []
    for item in nodes:
        identifier = _identifier(item.get("id"), "node.id")
        level = require_string(item.get("hierarchy_level"), "node.hierarchy_level")
        if level not in HIERARCHY_LEVELS:
            raise ContractError("invalid_hierarchy_level", f"invalid hierarchy level: {level}")
        parent = item.get("parent_id")
        if parent is not None:
            parent = _identifier(parent, "node.parent_id")
        unc_raw = item.get("uncertainty", "low")
        if isinstance(unc_raw, Mapping):
            uncertainty = str(unc_raw.get("level", "low")).lower()
        else:
            uncertainty = require_string(unc_raw, "node.uncertainty").lower()

        risk_raw = item.get("risk", "low")
        if isinstance(risk_raw, Mapping):
            risk = str(risk_raw.get("criticality", risk_raw.get("blast_radius", "low"))).lower()
        else:
            risk = require_string(risk_raw, "node.risk").lower()

        if uncertainty not in RISK_RANK or risk not in RISK_RANK:
            raise ContractError("invalid_plan_rank", "plan risk/uncertainty must be low through critical")
        normalized.append(
            {
                "id": identifier,
                "parent_id": parent,
                "hierarchy_level": level,
                "status": require_string(item.get("status", "planned"), "node.status"),
                "uncertainty": uncertainty,
                "risk": risk,
            }
        )
        identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("duplicate_node_id", "hierarchical plan node IDs must be unique")
    known = set(identifiers)
    if any(item["parent_id"] is not None and item["parent_id"] not in known for item in normalized):
        raise ContractError("unknown_parent", "hierarchical plan contains an unknown parent")
    frontier = []
    for item in normalized:
        if item["hierarchy_level"] in {"atomic_task", "microstep"}:
            continue
        if item["status"] not in {"coarse", "planned", "ready"}:
            continue
        priority = 10 * RISK_RANK[item["uncertainty"]] + 5 * RISK_RANK[item["risk"]]
        if item["status"] == "ready":
            priority += 3
        frontier.append((priority, item["id"]))
    raw_rev = payload.get("revision")
    if raw_rev is None:
        raise ContractError("missing_revision", "hierarchical plan requires revision")
    body = {
        "run_id": require_string(payload.get("run_id"), "run_id"),
        "revision": str(raw_rev),
        "nodes": normalized,
        "refinement_frontier": [item for _, item in sorted(frontier, key=lambda pair: (-pair[0], pair[1]))],
        "lazy_refinement": True,
    }
    return {**body, "digest": sha256_payload(body)}


def verify_plan_graph(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks_raw = payload.get("tasks")
    if tasks_raw is None and "nodes" in payload:
        nodes = mapping_sequence(payload.get("nodes"), "nodes", allow_empty=False)
        atomic_nodes = [item for item in nodes if item.get("hierarchy_level") == "atomic_task"]
        tasks = tuple(atomic_nodes if atomic_nodes else nodes)
    else:
        tasks = mapping_sequence(tasks_raw, "tasks", allow_empty=False)
    edges = mapping_sequence(payload.get("edges", []), "edges")
    ids = [_identifier(item.get("id"), "task.id") for item in tasks]
    _, _, _, graph_errors = _topological(ids, edges)
    errors = list(graph_errors)
    owned: list[tuple[str, str]] = []
    coverage = {"scenario": set(), "invariant": set(), "proof": set()}
    for item, task_id in zip(tasks, ids, strict=True):
        task_paths = tuple(
            normalize_relative_path(path, "task.owned_paths[]")
            for path in require_string_sequence(item.get("owned_paths", []), "task.owned_paths")
        )
        if not task_paths and not bool(item.get("read_only", False)):
            errors.append(f"unowned_task:{task_id}")
        for path in task_paths:
            for other_path, other_id in owned:
                if other_id != task_id and paths_overlap(path, other_path):
                    errors.append(f"overlapping_owned_path:{other_id}:{task_id}:{other_path}:{path}")
            owned.append((path, task_id))
        for group, field in (
            ("scenario", "scenario_refs"),
            ("invariant", "invariant_refs"),
            ("proof", "proof_obligation_refs"),
        ):
            coverage[group].update(require_string_sequence(item.get(field, []), f"task.{field}"))
    for edge in edges:
        edge_type = require_string(edge.get("type", "dependency"), "edge.type")
        if edge_type in CROSS_TASK_EDGE_TYPES:
            source = edge.get("from")
            target = edge.get("to")
            if not edge.get("contract_ref"):
                errors.append(f"missing_handoff_contract:{source}->{target}:{edge_type}")
            if not edge.get("validator"):
                errors.append(f"missing_edge_validator:{source}->{target}:{edge_type}")
    gaps = {}
    for group in coverage:
        required = set(
            require_string_sequence(payload.get(f"required_{group}s", []), f"required_{group}s")
        )
        gaps[f"missing_{group}s"] = sorted(required - coverage[group])
        errors.extend(f"missing_{group}:{item}" for item in gaps[f"missing_{group}s"])
    return {
        "executable": not errors,
        "errors": sorted(set(errors)),
        "coverage": gaps,
        "digest": sha256_payload({"tasks": tasks, "edges": edges, "coverage": gaps}),
    }


def plan_exploration(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    uncertainties = mapping_sequence(payload.get("uncertainties", []), "uncertainties")
    run_budget = decimal_value(payload.get("run_budget"), "run_budget", minimum=Decimal("0"))
    ceiling = run_budget * Decimal("0.12")
    consumed = Decimal("0")
    tasks = []
    for index, item in enumerate(uncertainties, start=1):
        cost = decimal_value(item.get("estimated_cost"), "estimated_cost", minimum=Decimal("0"))
        if consumed + cost > ceiling:
            continue
        consumed += cost
        tasks.append(
            {
                "id": f"EXP{index:03d}",
                "question": require_string(item.get("question"), "uncertainty.question"),
                "decision_unblocked": require_string(
                    item.get("decision_unblocked"), "uncertainty.decision_unblocked"
                ),
                "estimated_cost": format(cost, "f"),
                "execution": "NOT_RUN",
            }
        )
    return {
        "tasks": tasks,
        "budget_ceiling": format(ceiling, "f"),
        "planned_cost": format(consumed, "f"),
        "execution": "NOT_RUN",
    }


def generate_proof_obligations(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    boundaries = mapping_sequence(payload.get("boundaries", []), "boundaries")
    obligations = []
    for index, item in enumerate(boundaries, start=1):
        kind = require_string(item.get("kind"), "boundary.kind")
        if kind not in PROOF_BOUNDARY_KINDS:
            continue
        obligations.append(
            {
                "id": str(item.get("id") or f"PO{index:03d}"),
                "statement": require_string(item.get("statement"), "boundary.statement"),
                "scope": list(require_string_sequence(item.get("scope"), "boundary.scope", allow_empty=False)),
                "preferred_verifier": require_string(
                    item.get("preferred_verifier", "deterministic_test"),
                    "boundary.preferred_verifier",
                ),
                "status": "NOT_RUN",
                "evidence_refs": [],
            }
        )
    return {"proof_obligations": obligations, "all_required_kinds_materialized": True}


def plan_integration_edges(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    edges = mapping_sequence(payload.get("edges", []), "edges")
    normalized = []
    for item in edges:
        edge_type = require_string(item.get("type", "dependency"), "edge.type")
        cross_task = edge_type in CROSS_TASK_EDGE_TYPES
        ready = not cross_task or bool(item.get("contract_ref") and item.get("validator"))
        normalized.append(
            {
                **dict(item),
                "barrier_required": cross_task,
                "handoff_ready": ready,
            }
        )
    return {"edges": normalized, "all_handoffs_ready": all(item["handoff_ready"] for item in normalized)}


def plan_replan(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    trigger = require_string(payload.get("trigger"), "trigger").lower()
    if trigger in {"contract_change", "integration_conflict", "schema_change"}:
        scope = "boundary_cluster"
    elif trigger in {
        "acceptance_scenario_change",
        "architecture_invariant_change",
        "global_requirement_change",
    }:
        scope = "global"
    else:
        scope = "local"
    return {
        "trigger": trigger,
        "scope": scope,
        "preserved_evidence": list(
            require_string_sequence(payload.get("still_valid_evidence", []), "still_valid_evidence")
        ),
        "invalidated_tasks": list(
            require_string_sequence(payload.get("invalidated_tasks", []), "invalidated_tasks")
        ),
        "plan_mutated": False,
        "next_revision_required": True,
    }


def detect_semantic_conflicts(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    patches = mapping_sequence(payload.get("patches", []), "patches")
    normalized = []
    for item in patches:
        normalized.append(
            {
                "task_id": _identifier(item.get("task_id"), "patch.task_id"),
                "paths": tuple(
                    normalize_relative_path(path, "patch.paths[]")
                    for path in require_string_sequence(item.get("paths", []), "patch.paths")
                ),
                "contracts": set(
                    require_string_sequence(item.get("contracts", []), "patch.contracts")
                ),
                "invariants": set(
                    require_string_sequence(item.get("invariants", []), "patch.invariants")
                ),
            }
        )
    conflicts = []
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            overlaps = sorted(
                {path for path in left["paths"] for other in right["paths"] if paths_overlap(path, other)}
            )
            contracts = sorted(left["contracts"] & right["contracts"])
            invariants = sorted(left["invariants"] & right["invariants"])
            if overlaps or contracts or invariants:
                conflicts.append(
                    {
                        "left": left["task_id"],
                        "right": right["task_id"],
                        "overlapping_paths": overlaps,
                        "shared_contracts": contracts,
                        "shared_invariants": invariants,
                    }
                )
    return {"conflicts": conflicts, "safe_to_integrate": not conflicts}


def schedule_critical_path(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks = mapping_sequence(payload.get("tasks"), "tasks", allow_empty=False)
    edges = mapping_sequence(payload.get("edges", []), "edges")
    ids = [_identifier(item.get("id"), "task.id") for item in tasks]
    order, adjacency, _, errors = _topological(ids, edges)
    if errors:
        raise ContractError("invalid_dag", ";".join(errors))
    durations = {
        task_id: decimal_value(item.get("duration_seconds"), "duration_seconds", minimum=Decimal("0"))
        for task_id, item in zip(ids, tasks, strict=True)
    }
    longest = dict(durations)
    predecessor: dict[str, str] = {}
    for node in order:
        for target in adjacency[node]:
            candidate = longest[node] + durations[target]
            if candidate > longest[target]:
                longest[target] = candidate
                predecessor[target] = node
    end = max(ids, key=lambda item: (longest[item], item))
    path = []
    while end:
        path.append(end)
        end = predecessor.get(end, "")
    path.reverse()

    dependencies: dict[str, set[str]] = {task_id: set() for task_id in ids}
    for edge in edges:
        dependencies[str(edge["to"])].add(str(edge["from"]))
    remaining, completed = set(ids), set()
    waves = []
    while remaining:
        ready = sorted(task_id for task_id in remaining if dependencies[task_id] <= completed)
        wave: list[str] = []
        owned: list[str] = []
        for task_id in ready:
            task = tasks[ids.index(task_id)]
            paths = [
                normalize_relative_path(path, "task.owned_paths[]")
                for path in require_string_sequence(task.get("owned_paths", []), "task.owned_paths")
            ]
            if any(paths_overlap(path, other) for path in paths for other in owned):
                continue
            wave.append(task_id)
            owned.extend(paths)
        if not wave:
            raise ContractError("resource_deadlock", "no path-lock-safe task can be scheduled")
        waves.append(wave)
        completed.update(wave)
        remaining.difference_update(wave)
    return {
        "critical_path": path,
        "critical_path_seconds": format(longest[path[-1]], "f"),
        "waves": waves,
        "path_lock_safe": True,
    }


def capture_baseline(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    observations = require_mapping(payload.get("observations"), "observations")
    environment = require_mapping(payload.get("environment"), "environment")
    return {
        "baseline_digest": sha256_payload(observations),
        "environment_digest": sha256_payload(environment),
        "known_failures": list(
            require_string_sequence(payload.get("known_failures", []), "known_failures")
        ),
        "commands_executed": False,
        "external_evidence": "NOT_RUN",
    }


def diff_plans(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    before = require_mapping(payload.get("before"), "before")
    after = require_mapping(payload.get("after"), "after")
    before_nodes = {
        _identifier(item.get("id"), "before.node.id"): item
        for item in mapping_sequence(before.get("nodes", []), "before.nodes")
    }
    after_nodes = {
        _identifier(item.get("id"), "after.node.id"): item
        for item in mapping_sequence(after.get("nodes", []), "after.nodes")
    }
    return {
        "added_nodes": sorted(set(after_nodes) - set(before_nodes)),
        "removed_nodes": sorted(set(before_nodes) - set(after_nodes)),
        "changed_nodes": sorted(
            node
            for node in set(before_nodes) & set(after_nodes)
            if sha256_payload(before_nodes[node]) != sha256_payload(after_nodes[node])
        ),
        "before_digest": sha256_payload(before),
        "after_digest": sha256_payload(after),
        "persisted": False,
    }


def summarize_decomposition_telemetry(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    records = mapping_sequence(payload.get("records", []), "records")
    metrics: dict[str, Any] = {"sample_count": len(records)}
    for field in (
        "first_pass_success",
        "replanned",
        "split_after_start",
        "merge_after_start",
        "integration_conflict",
        "hidden_dependency",
        "context_overflow",
    ):
        metrics[field + "_rate"] = (
            format(
                Decimal(sum(int(bool(item.get(field))) for item in records))
                / Decimal(len(records)),
                "f",
            )
            if records
            else None
        )
    return {
        "metrics": metrics,
        "minimum_samples_met": len(records) >= 30,
        "priors_updated": False,
    }
