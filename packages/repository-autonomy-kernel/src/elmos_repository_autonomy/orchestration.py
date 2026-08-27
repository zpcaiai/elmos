"""Pure planning, routing, continuity and DAG functions."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict, deque
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from .errors import ContractError
from .models import (
    digest,
    paths_overlap,
    relative_path,
    require_mapping,
    require_string,
    string_list,
    utc_now,
)


def task_spec(requirements: Any, snapshot: Mapping[str, Any] | None, previous: Mapping[str, Any] | None, policy: Mapping[str, Any] | None) -> dict[str, Any]:
    if requirements is None:
        raise ContractError("SPEC_INVALID", "requirements are required")
    if isinstance(requirements, str):
        objective = requirements.strip()
        body: dict[str, Any] = {}
    elif isinstance(requirements, Mapping):
        body = dict(requirements)
        objective = str(body.get("objective", body.get("goal", ""))).strip()
    else:
        body = {"requirements": requirements}
        objective = "Compile supplied requirements"
    if not objective:
        raise ContractError("SPEC_INVALID", "requirements must contain an objective")
    repo_sha = (snapshot or {}).get("sha256") or digest(snapshot or {})
    old_hash = (previous or {}).get("hash") or (previous or {}).get("task_spec_hash")
    acceptance_raw = body.get("acceptance_criteria", body.get("acceptance", []))
    if isinstance(acceptance_raw, Mapping):
        criteria = [{"id": str(key), "description": str(value), "verifier_type": "deterministic"} for key, value in acceptance_raw.items()]
    elif isinstance(acceptance_raw, list):
        criteria = [{"id": str(item.get("id", index)) if isinstance(item, Mapping) else str(item), "description": str(item.get("description", item)) if isinstance(item, Mapping) else str(item), "verifier_type": str(item.get("verifier_type", "deterministic")) if isinstance(item, Mapping) else "deterministic"} for index, item in enumerate(acceptance_raw)]
    else:
        raise ContractError("SPEC_INVALID", "acceptance_criteria must be an object or array")
    if not criteria:
        criteria = [{"id": "schema-valid", "description": "Output satisfies the typed contract", "verifier_type": "schema"}]
    ambiguities = []
    for field in ("scope", "target_environment", "rollback", "data_migration"):
        if field in body and body[field] in (None, "", []):
            ambiguities.append({"field": field, "severity": "HIGH", "reason": "declared but empty", "requires_approval": True})
    spec = {"id": "task-spec:" + hashlib.sha256((objective + repo_sha).encode()).hexdigest()[:16], "version": "2.0.0", "objective": objective, "non_goals": list(body.get("non_goals", [])) if isinstance(body.get("non_goals", []), list) else [], "constraints": list(body.get("constraints", [])) if isinstance(body.get("constraints", []), list) else [], "deliverables": list(body.get("deliverables", [])) if isinstance(body.get("deliverables", []), list) else [], "acceptance_criteria": criteria, "risk": body.get("risk", {}), "repository_snapshot_sha": repo_sha, "requirements_hash": digest(requirements), "immutable": True}
    spec_hash = digest(spec)
    changed = [] if not old_hash or old_hash == spec_hash else ["objective", "acceptance_criteria", "constraints", "deliverables"]
    delta = {"base_hash": old_hash, "candidate_hash": spec_hash, "changed_fields": changed, "affected_nodes": [f"criterion:{item['id']}" for item in criteria] if changed else [], "cache_invalidation": changed, "status": "CHANGED" if changed else "UNCHANGED"}
    return {"task_spec": {**spec, "hash": spec_hash}, "spec_delta": delta, "acceptance_criteria": criteria, "ambiguity_register": ambiguities, "affected_node_set": delta["affected_nodes"]}


def _task_rows(tasks: Any) -> list[dict[str, Any]]:
    if not isinstance(tasks, list) or not tasks:
        raise ContractError("DAG_INVALID", "tasks must be a non-empty array")
    rows = []
    ids: set[str] = set()
    for item in tasks:
        row = require_mapping(item, "tasks[]")
        task_id = require_string(row.get("id"), "tasks[].id")
        if task_id in ids:
            raise ContractError("DAG_INVALID", f"duplicate task id: {task_id}")
        ids.add(task_id)
        owned = [relative_path(path, "tasks[].owned_paths[]") for path in string_list(row.get("owned_paths", []), "tasks[].owned_paths")]
        read_only = bool(row.get("read_only", False))
        if not read_only and not owned:
            raise ContractError("DAG_INVALID", f"task {task_id} must own paths or be read_only")
        for index, left in enumerate(owned):
            if any(paths_overlap(left, right) for right in owned[index + 1:]):
                raise ContractError("DAG_INVALID", f"task {task_id} has overlapping owned paths")
        rows.append({**row, "id": task_id, "dependencies": string_list(row.get("dependencies", []), "tasks[].dependencies"), "owned_paths": owned, "read_only": read_only, "status": row.get("status", "planned")})
    for row in rows:
        missing = sorted(set(row["dependencies"]) - ids)
        if missing:
            raise ContractError("DAG_INVALID", f"task {row['id']} has missing dependencies: {missing}")
    return rows


def dag(tasks: Any) -> dict[str, Any]:
    rows = _task_rows(tasks)
    by_id = {row["id"]: row for row in rows}
    indegree = {key: len(value["dependencies"]) for key, value in by_id.items()}
    dependants: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        for dependency in row["dependencies"]:
            dependants[dependency].append(row["id"])
    queue = deque(sorted(key for key, value in indegree.items() if value == 0))
    order: list[str] = []
    waves: list[list[str]] = []
    while queue:
        wave = sorted(queue)
        queue.clear()
        waves.append(wave)
        for task_id in wave:
            order.append(task_id)
            for child in sorted(dependants[task_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
    if len(order) != len(rows):
        raise ContractError("DAG_INVALID", "task dependencies contain a cycle")
    # A simple longest dependency path is deterministic and sufficient for scheduling.
    distance: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    for task_id in order:
        predecessors = by_id[task_id]["dependencies"]
        if predecessors:
            chosen = max(predecessors, key=lambda item: (distance[item], item))
            distance[task_id] = distance[chosen] + 1
            parent[task_id] = chosen
        else:
            distance[task_id] = 1
            parent[task_id] = None
    end = max(order, key=lambda item: (distance[item], item))
    critical: list[str] = []
    while end is not None:
        critical.append(end)
        end = parent[end]
    critical.reverse()
    payload = {"tasks": rows, "waves": waves, "order": order, "critical_path": critical}
    return {**payload, "digest": digest(payload)}


def context_plan(task: Mapping[str, Any], index: Mapping[str, Any], current_step: Mapping[str, Any], metadata: Mapping[str, Any], token_budget: int, previous: Mapping[str, Any] | None) -> dict[str, Any]:
    if token_budget < 1:
        raise ContractError("CONTEXT_BUDGET_EXCEEDED", "token_budget must be positive")
    symbols = index.get("symbols", []) if isinstance(index.get("symbols", []), list) else []
    step_text = " ".join(str(value) for value in current_step.values())
    ranked = sorted([item for item in symbols if isinstance(item, Mapping)], key=lambda item: (0 if any(str(item.get("name", "")).casefold() in step_text.casefold() for _ in [0]) else 1, str(item.get("uri", ""))))
    selected = ranked[: max(1, token_budget // 500)] if ranked else []
    ledger = {"objective": task.get("objective"), "completed": list((previous or {}).get("completed", [])), "decisions": list((previous or {}).get("decisions", [])), "assumptions": list((previous or {}).get("assumptions", [])), "open_findings": list((previous or {}).get("open_findings", [])), "next_step": current_step.get("id"), "snapshot_sha": task.get("repository_snapshot_sha")}
    stable_prefix = {"task_spec_hash": digest(task), "skill_version": metadata.get("version", "2.0.0"), "policy_hash": metadata.get("policy_hash", "unknown")}
    bundle = {"stable_prefix": stable_prefix, "task": task, "step": current_step, "selected_symbols": selected, "token_budget": token_budget}
    return {"context_plan": {"layers": ["L0-contract", "L1-task", "L2-index", "L3-evidence", "L4-step"], "selection_count": len(selected), "stable_prefix_hash": digest(stable_prefix)}, "context_bundle": bundle, "context_ledger": ledger, "retrieval_trace": [{"uri": item.get("uri"), "reason": "step relevance"} for item in selected], "compaction_snapshot": {"ledger_hash": digest(ledger), "created_at": utc_now()}}


def cache_key(payload: Mapping[str, Any]) -> str:
    required = ("snapshot_hash", "task_spec_hash", "workflow_version", "skill_versions", "policy_hash", "tool_schema_versions", "model_profile")
    missing = [name for name in required if name not in payload]
    if missing:
        raise ContractError("CACHE_KEY_INCOMPLETE", f"missing cache key parts: {missing}")
    return digest({name: payload[name] for name in required})


def route(step: Mapping[str, Any], profiles: Any, risk: Mapping[str, Any], budget: Mapping[str, Any], provider_policy: Mapping[str, Any], recent_evals: Any) -> dict[str, Any]:
    if not isinstance(profiles, list) or not profiles:
        raise ContractError("MODEL_ROUTE_UNAVAILABLE", "model capability profiles are required")
    required_context = int(step.get("required_context", 0))
    risk_level = str(risk.get("level", step.get("risk_level", "LOW"))).upper()
    candidates = []
    for profile in profiles:
        item = require_mapping(profile, "model_capability_profiles[]")
        reasons = []
        if str(item.get("eval_status", "UNKNOWN")).upper() != "PASS":
            reasons.append("model_not_evaluated")
        if int(item.get("max_context", 0)) < required_context:
            reasons.append("context_insufficient")
        if risk_level in {"HIGH", "CRITICAL"} and str(item.get("eval_status", "UNKNOWN")).upper() != "PASS":
            reasons.append("high_risk_requires_pass")
        if str(item.get("privacy_mode", "")) not in set(provider_policy.get("allowed_privacy_modes", [item.get("privacy_mode", "")])):
            reasons.append("privacy_mode_not_allowed")
        quality = float(item.get("quality", 0))
        cost = float(item.get("cost_per_call", 0))
        latency = float(item.get("latency_ms", 1))
        score = quality / max(cost + latency / 100000, 0.000001)
        candidates.append({"model_id": require_string(item.get("model_id"), "model.model_id"), "eligible": not reasons, "reasons": sorted(set(reasons)), "score": score, "quality": quality, "cost": cost, "latency_ms": latency})
    eligible = sorted([item for item in candidates if item["eligible"]], key=lambda item: (-item["score"], item["model_id"]))
    chosen = eligible[0] if eligible else None
    return {"routing_decision": {"status": "ROUTED" if chosen else "BLOCKED", "chosen_model": chosen["model_id"] if chosen else None, "candidates": candidates, "policy_hash": digest(provider_policy)}, "fallback_chain": [item["model_id"] for item in eligible[1:]], "escalation_plan": {"required": not bool(chosen), "reason": "no eligible model" if not chosen else "none"}, "estimated_cost": chosen["cost"] if chosen else None, "usage_record": {"status": "NOT_RUN", "provider_execution": False}}


def cost_eta(events: Any, history: Any, repo_features: Mapping[str, Any], usage: Any, cache_metrics: Mapping[str, Any], pricing: Mapping[str, Any]) -> dict[str, Any]:
    rows = [require_mapping(item, "run_events[]") for item in events] if isinstance(events, list) else []
    durations = [float(item.get("wall_clock_ms", item.get("duration_ms", 0))) / 1000 for item in rows if float(item.get("wall_clock_ms", item.get("duration_ms", 0))) >= 0]
    if not durations:
        durations = [0.0]
    sorted_values = sorted(durations)
    def quantile(q: float) -> float:
        index = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
        return sorted_values[index]
    by_phase: dict[str, float] = defaultdict(float)
    for item in rows:
        by_phase[str(item.get("phase", item.get("event_type", "unknown")))] += float(item.get("wall_clock_ms", item.get("duration_ms", 0))) / 1000
    total_cost = Decimal(0)
    cost_rows = []
    if isinstance(usage, list):
        for item in usage:
            value = require_mapping(item, "model_tool_usage[]")
            quantity = Decimal(str(value.get("quantity", 0)))
            unit_price = Decimal(str(value.get("unit_price", 0)))
            amount = quantity * unit_price
            total_cost += amount
            cost_rows.append({"category": value.get("category", "model"), "quantity": str(quantity), "unit_price": str(unit_price), "total": str(amount), "currency": value.get("currency", "USD")})
    if pricing and any(value is None for value in pricing.values()):
        raise ContractError("PRICE_PROFILE_MISSING", "pricing profile contains null values")
    return {"progress_snapshot": {"events": len(rows), "completed_events": sum(1 for item in rows if str(item.get("status", "")).upper() in {"PASS", "SUCCEEDED", "COMPLETED"}), "machine_wall_clock_seconds": sum(durations), "human_wait_seconds": sum(float(item.get("approval_wait_seconds", 0)) for item in rows)}, "eta_distribution": {"p50": quantile(.5), "p80": quantile(.8), "p95": quantile(.95), "worst_case": max(durations), "confidence": "engineering-estimate"}, "critical_path": {"phases": sorted(by_phase, key=lambda key: (-by_phase[key], key)), "durations_seconds": dict(sorted(by_phase.items()))}, "cost_breakdown": cost_rows, "billing_record": {"status": "CALCULATED" if cost_rows else "NOT_RUN", "total": str(total_cost), "currency": "USD", "pricing_profile": digest(pricing)}, "slo_metrics": {"cache_hit_rate": float(cache_metrics.get("hit_rate", 0)), "historical_sample_count": len(history) if isinstance(history, list) else 0, "repo_features": dict(repo_features)}}


def continuity(ledger: Mapping[str, Any], run_state: Mapping[str, Any], agent_state: Mapping[str, Any], tool_results: Any, findings: Any, provider_event: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = {"version": "2.0.0", "ledger": dict(ledger), "run_state": dict(run_state), "agent_state": dict(agent_state), "tool_results": list(tool_results) if isinstance(tool_results, list) else [], "open_findings": list(findings) if isinstance(findings, list) else [], "provider_event": dict(provider_event), "captured_at": utc_now()}
    previous = provider_event.get("previous_state") if isinstance(provider_event.get("previous_state"), Mapping) else {}
    changed = sorted(key for key in set(snapshot) | set(previous) if snapshot.get(key) != previous.get(key))
    return {"model_state_snapshot": {**snapshot, "hash": digest(snapshot)}, "continuation_prompt": {"objective": ledger.get("objective"), "completed": ledger.get("completed", []), "next_step": ledger.get("next_step"), "constraints": ["do not replay unknown side effects", "revalidate authority before writes"]}, "resume_cursor": {"event_sequence": provider_event.get("sequence_no", 0), "checkpoint_hash": provider_event.get("checkpoint_hash")}, "state_diff": {"changed_fields": changed}, "continuity_report": {"status": "REQUIRES_AUTHORITY_REVALIDATION", "resume_equivalence": not bool(provider_event.get("diverged", False)), "duplicate_side_effect_risk": bool(provider_event.get("unknown_side_effect", False))}}


def time_travel(events: Any, checkpoints: Any, ledgers: Any, change_graph_value: Any, artifacts: Any) -> dict[str, Any]:
    rows = [require_mapping(item, "run_event_stream[]") for item in events] if isinstance(events, list) else []
    sequence = sorted(rows, key=lambda item: int(item.get("sequence_no", 0)))
    return {"session_snapshot": {"event_count": len(sequence), "latest_sequence": sequence[-1].get("sequence_no", 0) if sequence else 0, "checkpoint_count": len(checkpoints) if isinstance(checkpoints, list) else 0, "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0, "state_hash": digest(sequence)}, "forked_run": {"status": "PLANNED", "from_sequence": sequence[-1].get("sequence_no", 0) if sequence else 0, "new_run_id": str(__import__("uuid").uuid4())}, "replay_report": {"status": "REPLAYABLE" if sequence else "NOT_RUN", "ordered": all(sequence[index]["sequence_no"] <= sequence[index + 1]["sequence_no"] for index in range(len(sequence) - 1)), "change_graph_bound": bool(change_graph_value)}, "state_comparison": {"ledgers": len(ledgers) if isinstance(ledgers, list) else 0}, "rollback_plan": {"status": "PLANNED", "requires_external_scm": True}}
