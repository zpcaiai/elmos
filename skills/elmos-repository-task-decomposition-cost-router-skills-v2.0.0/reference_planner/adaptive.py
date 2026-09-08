"""Dependency-free reference utilities for Elmos adaptive repository planning.

This is intentionally not a semantic planner. It implements deterministic pieces
that should surround the model planner: granularity scoring, graph verification,
coverage checks, refinement frontier selection, and local split/merge signals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

DEFAULT_WEIGHTS = {
    "context_demand": 0.15,
    "write_surface": 0.12,
    "semantic_breadth": 0.18,
    "cross_boundary_coupling": 0.18,
    "invariant_density": 0.15,
    "verification_distance": 0.12,
    "uncertainty": 0.10,
}

@dataclass(frozen=True)
class GranularityDecision:
    score: float
    decision: str
    reasons: tuple[str, ...]


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def granularity_score(features: dict[str, float], weights: dict[str, float] | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    denom = sum(max(0.0, float(x)) for x in w.values()) or 1.0
    score = sum(_clamp01(features.get(k, 0.0)) * max(0.0, float(weight)) for k, weight in w.items()) / denom
    return round(_clamp01(score), 6)


def decide_granularity(
    features: dict[str, float],
    *,
    split_threshold: float = 0.72,
    merge_threshold: float = 0.20,
    hard_merge: bool = False,
    indivisible_invariant: bool = False,
) -> GranularityDecision:
    score = granularity_score(features)
    reasons: list[str] = []
    if indivisible_invariant:
        reasons.append("indivisible_invariant")
        return GranularityDecision(score, "keep", tuple(reasons))
    if hard_merge:
        reasons.append("unsafe_split_requires_merge")
        return GranularityDecision(score, "merge", tuple(reasons))
    if score >= split_threshold:
        reasons.append("score_above_split_threshold")
        if features.get("cross_boundary_coupling", 0) >= 0.8:
            reasons.append("split_only_at_semantic_seam")
        return GranularityDecision(score, "split", tuple(reasons))
    if score <= merge_threshold:
        reasons.append("score_below_merge_threshold")
        return GranularityDecision(score, "merge", tuple(reasons))
    reasons.append("within_target_band")
    return GranularityDecision(score, "keep", tuple(reasons))


def _task_ids(tasks: Iterable[dict[str, Any]]) -> set[str]:
    return {str(t["id"]) for t in tasks}


def verify_dag(tasks: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    """Return structural errors. Empty list means deterministic checks pass."""
    errors: list[str] = []
    ids = _task_ids(tasks)
    indeg = {i: 0 for i in ids}
    adj = {i: [] for i in ids}
    seen_edge = set()
    for e in edges:
        a, b = str(e.get("from")), str(e.get("to"))
        key = (a, b, str(e.get("type")))
        if key in seen_edge:
            errors.append(f"duplicate_edge:{key}")
        seen_edge.add(key)
        if a not in ids or b not in ids:
            errors.append(f"edge_unknown_node:{a}->{b}")
            continue
        if a == b:
            errors.append(f"self_cycle:{a}")
        adj[a].append(b)
        indeg[b] += 1
        if e.get("type") not in {"lock"} and not e.get("contract_ref") and e.get("type") in {"contract","schema","data","runtime","integration"}:
            errors.append(f"missing_handoff_contract:{a}->{b}:{e.get('type')}")
        if e.get("type") in {"contract","schema","data","runtime","integration"} and not e.get("validator"):
            errors.append(f"missing_edge_validator:{a}->{b}:{e.get('type')}")

    q = [n for n, d in indeg.items() if d == 0]
    visited = 0
    while q:
        n = q.pop()
        visited += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    if visited != len(ids):
        errors.append("cycle_detected")

    # Path ownership overlap among tasks that have no explicit dependency is a warning/error.
    owners: dict[str, list[str]] = {}
    for t in tasks:
        for p in t.get("owned_paths", []) or []:
            owners.setdefault(str(p), []).append(str(t["id"]))
    for path, ts in owners.items():
        if len(ts) > 1:
            errors.append(f"overlapping_owned_path:{path}:{','.join(sorted(ts))}")
    return sorted(set(errors))


def coverage_gaps(
    tasks: list[dict[str, Any]],
    required_scenarios: Iterable[str],
    required_invariants: Iterable[str],
    required_proofs: Iterable[str] = (),
) -> dict[str, list[str]]:
    s = set(); inv = set(); proofs = set()
    for t in tasks:
        s.update(map(str, t.get("scenario_refs", []) or []))
        inv.update(map(str, t.get("invariant_refs", []) or []))
        proofs.update(map(str, t.get("proof_obligation_refs", []) or []))
    return {
        "missing_scenarios": sorted(set(map(str, required_scenarios)) - s),
        "missing_invariants": sorted(set(map(str, required_invariants)) - inv),
        "missing_proofs": sorted(set(map(str, required_proofs)) - proofs),
    }


def refinement_frontier(nodes: list[dict[str, Any]]) -> list[str]:
    """Select coarse/planned nodes that should be refined next.

    Priority: high/critical uncertainty, high risk, then ready coarse nodes.
    """
    rank_unc = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    candidates = []
    for n in nodes:
        if n.get("hierarchy_level") in {"atomic_task", "microstep"}:
            continue
        if n.get("status") not in {"coarse", "planned", "ready"}:
            continue
        uncertainty = (n.get("uncertainty") or {}).get("level", "low")
        risk = n.get("risk") or {}
        criticality = str(risk.get("criticality") or risk.get("blast_radius") or "low")
        risk_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(criticality, 1)
        blocked = bool(n.get("dependencies")) and n.get("status") != "ready"
        score = 10 * rank_unc.get(uncertainty, 1) + 5 * risk_rank + (0 if blocked else 3)
        candidates.append((score, str(n["id"])))
    return [i for _, i in sorted(candidates, key=lambda x: (-x[0], x[1]))]


def replan_scope(trigger: str) -> str:
    trigger = trigger.lower()
    if trigger in {"contract_change", "integration_conflict", "schema_change"}:
        return "boundary_cluster"
    if trigger in {"acceptance_scenario_change", "architecture_invariant_change", "global_requirement_change"}:
        return "global"
    return "local"
