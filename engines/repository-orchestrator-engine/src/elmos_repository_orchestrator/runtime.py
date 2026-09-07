from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import MappingProxyType
from typing import Any, Final

from .canonical import CanonicalValueError, canonical_digest, canonical_value


class SkillRuntimeError(ValueError):
    """Raised when a request, scope, or capability result fails closed."""


ALLOWED_MODELS: Final[tuple[str, ...]] = (
    "gpt-5.6-sol-max",
    "claude-opus-5-max",
    "claude-fable-5",
    "grok-4.6",
    "kimi-k3-max",
    "glm-5.3-max",
    "qwen3.8-max",
    "deepseek-v4-pro-0813",
    "gemini-3.7-flash-high",
    "claude-sonnet-5",
)

TIERS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "L0": ("gemini-3.7-flash-high", "glm-5.3-max", "qwen3.8-max"),
        "L1": (
            "kimi-k3-max",
            "grok-4.6",
            "deepseek-v4-pro-0813",
            "claude-sonnet-5",
        ),
        "L2": (
            "grok-4.6",
            "kimi-k3-max",
            "claude-sonnet-5",
            "gpt-5.6-sol-max",
        ),
        "L3": ("gpt-5.6-sol-max", "claude-opus-5-max"),
        "L4": ("claude-fable-5", "claude-opus-5-max", "gpt-5.6-sol-max"),
    }
)

TASK_PREFERENCES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "docs_config_boilerplate": TIERS["L0"],
        "frontend_standard": ("qwen3.8-max", "kimi-k3-max", "claude-sonnet-5"),
        "backend_standard": (
            "glm-5.3-max",
            "deepseek-v4-pro-0813",
            "kimi-k3-max",
            "grok-4.6",
        ),
        "algorithmic": ("deepseek-v4-pro-0813", "kimi-k3-max", "gpt-5.6-sol-max"),
        "terminal_devops": ("grok-4.6", "kimi-k3-max", "claude-sonnet-5"),
        "repository_refactor": ("claude-sonnet-5", "grok-4.6", "claude-opus-5-max"),
        "complex_debug": ("grok-4.6", "gpt-5.6-sol-max", "claude-opus-5-max"),
        "architecture_contracts": TIERS["L3"],
        "long_horizon_migration": TIERS["L4"],
        "final_repository_certification": TIERS["L3"],
    }
)

GRANULARITY_WEIGHTS: Final[Mapping[str, Decimal]] = MappingProxyType(
    {
        "context_demand": Decimal("0.15"),
        "write_surface": Decimal("0.12"),
        "semantic_breadth": Decimal("0.18"),
        "cross_boundary_coupling": Decimal("0.18"),
        "invariant_density": Decimal("0.15"),
        "verification_distance": Decimal("0.12"),
        "uncertainty": Decimal("0.10"),
    }
)

RISK_RANK: Final[Mapping[str, int]] = MappingProxyType(
    {"low": 1, "medium": 2, "high": 3, "critical": 4}
)

EFFECTFUL_SKILLS: Final[frozenset[str]] = frozenset(
    {
        "elmos-worktree-manager",
        "elmos-worker-executor",
        "elmos-integration-manager",
        "elmos-conflict-resolver",
        "elmos-rollback-recovery",
        "elmos-run-state-journal",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeScope:
    tenant_id: str
    project_id: str
    actor_id: str
    environment: str
    repository_id: str
    revision: str
    purpose: str

    def __post_init__(self) -> None:
        for field, value in asdict(self).items():
            if not isinstance(value, str) or not value.strip():
                raise SkillRuntimeError(f"scope.{field} must be a non-empty string")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SkillRuntimeError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise SkillRuntimeError(f"{field} keys must be strings")
    return value


def _items(value: Any, field: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SkillRuntimeError(f"{field} must be an array")
    return [_mapping(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _strings(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SkillRuntimeError(f"{field} must be an array of strings")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SkillRuntimeError(f"{field} must contain non-empty strings")
        result.append(item.strip())
    return result


def _decimal(value: Any, field: str, default: str = "0") -> Decimal:
    if value is None:
        value = default
    if isinstance(value, bool):
        raise SkillRuntimeError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SkillRuntimeError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise SkillRuntimeError(f"{field} must be finite")
    return result


def _probability(value: Any, field: str, default: str = "0") -> Decimal:
    result = _decimal(value, field, default)
    if result < 0 or result > 1:
        raise SkillRuntimeError(f"{field} must be between 0 and 1")
    return result


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _iso_now(request: Mapping[str, Any]) -> str:
    supplied = request.get("observed_at")
    if supplied is not None:
        if not isinstance(supplied, str) or not supplied:
            raise SkillRuntimeError("observed_at must be a non-empty string")
        return supplied
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _topological(
    node_ids: Sequence[str], edges: Sequence[Mapping[str, Any]]
) -> tuple[list[str], dict[str, list[str]], dict[str, int], list[str]]:
    unique = set(node_ids)
    if len(unique) != len(node_ids):
        return [], {}, {}, ["duplicate_node_id"]
    adjacency = {node: [] for node in node_ids}
    indegree = {node: 0 for node in node_ids}
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        edge_type = str(edge.get("type", "dependency"))
        key = (source, target, edge_type)
        if key in seen:
            errors.append(f"duplicate_edge:{source}->{target}:{edge_type}")
        seen.add(key)
        if source not in unique or target not in unique:
            errors.append(f"edge_unknown_node:{source}->{target}")
            continue
        if source == target:
            errors.append(f"self_cycle:{source}")
        adjacency[source].append(target)
        indegree[target] += 1
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    order: list[str] = []
    degrees = dict(indegree)
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in sorted(adjacency[node]):
            degrees[target] -= 1
            if degrees[target] == 0:
                queue.append(target)
    if len(order) != len(node_ids):
        errors.append("cycle_detected")
    return order, adjacency, indegree, sorted(set(errors))


def _path_overlap(first: str, second: str) -> bool:
    left = first.strip("/")
    right = second.strip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _graph_errors(
    tasks: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> list[str]:
    ids = [str(task.get("id", "")) for task in tasks]
    _, _, _, errors = _topological(ids, edges)
    cross_types = {"contract", "schema", "data", "runtime", "integration"}
    for edge in edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        edge_type = str(edge.get("type", "dependency"))
        if edge_type in cross_types and not edge.get("contract_ref"):
            errors.append(f"missing_handoff_contract:{source}->{target}:{edge_type}")
        if edge_type in cross_types and not edge.get("validator"):
            errors.append(f"missing_edge_validator:{source}->{target}:{edge_type}")
    owned: list[tuple[str, str]] = []
    for task in tasks:
        task_id = str(task.get("id", ""))
        paths = _strings(task.get("owned_paths", []), f"task[{task_id}].owned_paths")
        if not paths:
            errors.append(f"unowned_task:{task_id}")
        for path in paths:
            for other_path, other_task in owned:
                if other_task != task_id and _path_overlap(path, other_path):
                    errors.append(
                        f"overlapping_owned_path:{other_task}:{task_id}:{other_path}:{path}"
                    )
            owned.append((path, task_id))
    return sorted(set(errors))


def _coverage(
    tasks: Sequence[Mapping[str, Any]], request: Mapping[str, Any]
) -> dict[str, list[str]]:
    observed = {
        "scenarios": set(),
        "invariants": set(),
        "proofs": set(),
    }
    keys = {
        "scenarios": "scenario_refs",
        "invariants": "invariant_refs",
        "proofs": "proof_obligation_refs",
    }
    for task in tasks:
        for group, key in keys.items():
            observed[group].update(_strings(task.get(key, []), f"task.{key}"))
    return {
        f"missing_{group}": sorted(
            set(_strings(request.get(f"required_{group}", []), f"required_{group}"))
            - values
        )
        for group, values in observed.items()
    }


def _op_repository_orchestrator(request: Mapping[str, Any]) -> Mapping[str, Any]:
    requirement = str(request.get("requirement", "")).strip()
    if not requirement:
        raise SkillRuntimeError("requirement is required")
    requested_stages = _strings(request.get("requested_stages", []), "requested_stages")
    stages = requested_stages or [
        "normalize",
        "intake",
        "recover_requirements",
        "build_graphs",
        "plan",
        "verify_plan",
        "route",
        "schedule",
        "execute_via_trusted_broker",
        "validate",
        "integrate_via_trusted_broker",
        "external_gate",
    ]
    return {
        "run_id": str(request.get("run_id") or canonical_digest(requirement)[7:23]),
        "stages": stages,
        "state": "PLANNED",
        "automatic_effects": False,
        "certified": False,
        "external_evidence": "NOT_RUN",
    }


def _op_requirement_normalizer(request: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = str(request.get("requirement", "")).strip()
    if not raw:
        raise SkillRuntimeError("requirement is required")
    constraints = sorted(set(_strings(request.get("constraints", []), "constraints")))
    acceptance = sorted(set(_strings(request.get("acceptance", []), "acceptance")))
    return {
        "normalized_requirement": " ".join(raw.split()),
        "constraints": constraints,
        "acceptance": acceptance,
        "unresolved_ambiguities": sorted(
            set(_strings(request.get("ambiguities", []), "ambiguities"))
        ),
        "requirement_digest": canonical_digest(
            {"requirement": " ".join(raw.split()), "constraints": constraints, "acceptance": acceptance}
        ),
    }


def _op_repo_intake(request: Mapping[str, Any]) -> Mapping[str, Any]:
    files = sorted(set(_strings(request.get("files", []), "files")))
    roots = sorted(set(_strings(request.get("workspace_roots", []), "workspace_roots")))
    return {
        "revision": str(request.get("revision", "UNRESOLVED")),
        "workspace_roots": roots,
        "file_count": len(files),
        "files": files,
        "dirty_paths": sorted(set(_strings(request.get("dirty_paths", []), "dirty_paths"))),
        "source_execution": "NOT_RUN",
        "intake_complete": bool(roots and request.get("revision")),
    }


def _op_architecture_indexer(request: Mapping[str, Any]) -> Mapping[str, Any]:
    components = _items(request.get("components", []), "components")
    normalized = sorted(
        (
            {
                "id": str(item.get("id", "")),
                "kind": str(item.get("kind", "module")),
                "paths": sorted(set(_strings(item.get("paths", []), "component.paths"))),
                "public_interfaces": sorted(
                    set(_strings(item.get("public_interfaces", []), "component.public_interfaces"))
                ),
            }
            for item in components
        ),
        key=lambda item: item["id"],
    )
    if any(not item["id"] for item in normalized):
        raise SkillRuntimeError("every component requires an id")
    return {
        "components": normalized,
        "entry_points": sorted(set(_strings(request.get("entry_points", []), "entry_points"))),
        "high_centrality_nodes": sorted(
            set(_strings(request.get("high_centrality_nodes", []), "high_centrality_nodes"))
        ),
        "runtime_verified": False,
    }


def _op_change_impact(request: Mapping[str, Any]) -> Mapping[str, Any]:
    changed = set(_strings(request.get("changed_nodes", []), "changed_nodes"))
    edges = _items(request.get("edges", []), "edges")
    adjacency: dict[str, set[str]] = defaultdict(set)
    evidence_edges = 0
    for edge in edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        if source and target:
            adjacency[source].add(target)
            if edge.get("evidence_ref"):
                evidence_edges += 1
    impacted = set(changed)
    queue = deque(sorted(changed))
    while queue:
        node = queue.popleft()
        for target in adjacency[node]:
            if target not in impacted:
                impacted.add(target)
                queue.append(target)
    confidence = Decimal("1") if not edges else Decimal(evidence_edges) / Decimal(len(edges))
    return {
        "impacted_nodes": sorted(impacted),
        "impact_confidence": float(confidence.quantize(Decimal("0.000001"))),
        "exploration_required": confidence < Decimal("0.70"),
    }


def _op_task_decomposer(request: Mapping[str, Any]) -> Mapping[str, Any]:
    capabilities = _items(request.get("capabilities", []), "capabilities")
    tasks = []
    for index, capability in enumerate(capabilities, start=1):
        title = str(capability.get("title", "")).strip()
        if not title:
            raise SkillRuntimeError("every capability requires a title")
        tasks.append(
            {
                "id": str(capability.get("id") or f"T{index:03d}"),
                "title": title,
                "objective": str(capability.get("objective") or title),
                "hierarchy_level": "atomic_task",
                "owned_paths": _strings(capability.get("owned_paths", []), "owned_paths"),
                "scenario_refs": _strings(capability.get("scenario_refs", []), "scenario_refs"),
                "invariant_refs": _strings(capability.get("invariant_refs", []), "invariant_refs"),
                "acceptance": _strings(capability.get("acceptance", []), "acceptance"),
                "status": "planned",
            }
        )
    return {"candidate_tasks": tasks, "fixed_size_heuristic_used": False}


def _op_atomicity(request: Mapping[str, Any]) -> Mapping[str, Any]:
    task = _mapping(request.get("task", {}), "task")
    reasons = []
    owned = _strings(task.get("owned_paths", []), "task.owned_paths")
    acceptance = _strings(task.get("acceptance", []), "task.acceptance")
    if not str(task.get("objective", "")).strip():
        reasons.append("missing_objective")
    if not owned:
        reasons.append("missing_owned_paths")
    if not acceptance:
        reasons.append("missing_acceptance")
    if len(owned) > int(request.get("max_owned_path_groups", 4)):
        reasons.append("write_surface_too_broad")
    if task.get("unverified_invariants"):
        reasons.append("unverified_invariants")
    return {"atomic": not reasons, "reasons": reasons}


def _op_dag_builder(request: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks = _items(request.get("tasks", []), "tasks")
    edges = _items(request.get("edges", []), "edges")
    task_ids = [str(task.get("id", "")) for task in tasks]
    order, _, indegree, errors = _topological(task_ids, edges)
    waves: list[list[str]] = []
    if not errors:
        remaining = set(order)
        completed: set[str] = set()
        dependencies: dict[str, set[str]] = {item: set() for item in order}
        for edge in edges:
            dependencies[str(edge["to"])].add(str(edge["from"]))
        while remaining:
            wave = sorted(node for node in remaining if dependencies[node] <= completed)
            if not wave:
                errors.append("cycle_detected")
                break
            waves.append(wave)
            completed.update(wave)
            remaining.difference_update(wave)
    return {
        "tasks": [dict(task) for task in tasks],
        "edges": [dict(edge) for edge in edges],
        "topological_order": order,
        "roots": sorted(node for node, degree in indegree.items() if degree == 0),
        "waves": waves,
        "valid": not errors,
        "errors": sorted(set(errors)),
    }


def _op_contract_boundary(request: Mapping[str, Any]) -> Mapping[str, Any]:
    edges = _items(request.get("edges", []), "edges")
    contracts = []
    for index, edge in enumerate(edges, start=1):
        contracts.append(
            {
                "id": str(edge.get("contract_ref") or f"HC{index:03d}"),
                "producer": str(edge.get("from", "")),
                "consumer": str(edge.get("to", "")),
                "artifact_type": str(edge.get("artifact_type", "structured_artifact")),
                "validator": edge.get("validator"),
                "status": "DECLARED" if edge.get("validator") else "INCOMPLETE",
            }
        )
    return {"contracts": contracts, "all_validatable": all(item["validator"] for item in contracts)}


def _op_complexity(request: Mapping[str, Any]) -> Mapping[str, Any]:
    features = _mapping(request.get("features", {}), "features")
    weights = {
        "semantic_breadth": Decimal("0.30"),
        "write_surface": Decimal("0.20"),
        "dependency_count": Decimal("0.15"),
        "verification_distance": Decimal("0.20"),
        "uncertainty": Decimal("0.15"),
    }
    score = sum(
        min(Decimal("1"), max(Decimal("0"), _decimal(features.get(key), key))) * weight
        for key, weight in weights.items()
    )
    return {"score": float(score), "band": "high" if score >= Decimal("0.7") else "medium" if score >= Decimal("0.35") else "low"}


def _op_risk(request: Mapping[str, Any]) -> Mapping[str, Any]:
    dimensions = _mapping(request.get("dimensions", {}), "dimensions")
    normalized = {key: str(value).lower() for key, value in dimensions.items()}
    if any(value not in RISK_RANK for value in normalized.values()):
        raise SkillRuntimeError("risk values must be low, medium, high, or critical")
    highest = max(normalized.values(), key=lambda item: RISK_RANK[item], default="low")
    minimum_tier = "L3" if RISK_RANK[highest] >= 3 else "L1" if highest == "medium" else "L0"
    if bool(request.get("long_horizon")):
        minimum_tier = "L4"
    return {"dimensions": normalized, "overall": highest, "minimum_tier": minimum_tier}


def _op_context_slicer(request: Mapping[str, Any]) -> Mapping[str, Any]:
    task = _mapping(request.get("task", {}), "task")
    owned = _strings(task.get("owned_paths", []), "task.owned_paths")
    read = _strings(task.get("read_paths", []), "task.read_paths")
    forbidden = _strings(task.get("forbidden_paths", []), "task.forbidden_paths")
    included = sorted(set(owned + read) - set(forbidden))
    manifest = {
        "task_id": str(task.get("id", "")),
        "included_paths": included,
        "contracts": _strings(task.get("incoming_contract_refs", []), "incoming_contract_refs")
        + _strings(task.get("outgoing_contract_refs", []), "outgoing_contract_refs"),
        "invariants": _strings(task.get("invariant_refs", []), "invariant_refs"),
        "proofs": _strings(task.get("proof_obligation_refs", []), "proof_obligation_refs"),
        "forbidden_paths": forbidden,
    }
    return {"manifest": manifest, "cache_key": canonical_digest(manifest)}


def _op_registry_guard(request: Mapping[str, Any]) -> Mapping[str, Any]:
    requested = str(request.get("model_alias", ""))
    return {
        "model_alias": requested,
        "allowed": requested in ALLOWED_MODELS,
        "reason": "allowlisted" if requested in ALLOWED_MODELS else "unknown_or_unconfigured_model",
        "allowlist": list(ALLOWED_MODELS),
    }


def _op_capability_profiler(request: Mapping[str, Any]) -> Mapping[str, Any]:
    samples = _items(request.get("samples", []), "samples")
    aggregates: dict[str, dict[str, Decimal | int]] = {
        model: {"attempts": 0, "successes": 0, "quality_total": Decimal("0"), "latency_total": Decimal("0")}
        for model in ALLOWED_MODELS
    }
    for sample in samples:
        model = str(sample.get("model_alias", ""))
        if model not in aggregates:
            raise SkillRuntimeError(f"sample uses unknown model: {model}")
        row = aggregates[model]
        row["attempts"] = int(row["attempts"]) + 1
        row["successes"] = int(row["successes"]) + int(bool(sample.get("success")))
        row["quality_total"] = Decimal(row["quality_total"]) + _probability(sample.get("quality"), "quality", "0.5")
        row["latency_total"] = Decimal(row["latency_total"]) + _decimal(sample.get("latency_seconds"), "latency_seconds")
    profiles = []
    for model, row in aggregates.items():
        attempts = int(row["attempts"])
        successes = int(row["successes"])
        posterior = (Decimal(successes) + Decimal("1")) / (Decimal(attempts) + Decimal("2"))
        profiles.append(
            {
                "model_alias": model,
                "samples": attempts,
                "p_success": float(posterior),
                "mean_quality": float(Decimal(row["quality_total"]) / attempts) if attempts else None,
                "mean_latency_seconds": float(Decimal(row["latency_total"]) / attempts) if attempts else None,
                "telemetry_override_allowed": attempts >= 30,
            }
        )
    return {"profiles": profiles}


def _eligible_models(request: Mapping[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    minimum_tier = str(request.get("minimum_tier", "L0"))
    if minimum_tier not in TIERS:
        raise SkillRuntimeError("minimum_tier must be L0 through L4")
    class_name = str(request.get("task_class", "backend_standard"))
    preferred = TASK_PREFERENCES.get(class_name, ALLOWED_MODELS)
    available = set(_strings(request.get("available_models", list(ALLOWED_MODELS)), "available_models"))
    unknown = available - set(ALLOWED_MODELS)
    if unknown:
        raise SkillRuntimeError(f"available_models contains unknown aliases: {sorted(unknown)}")
    minimum_index = ["L0", "L1", "L2", "L3", "L4"].index(minimum_tier)
    tier_eligible = set()
    for tier in ["L0", "L1", "L2", "L3", "L4"][minimum_index:]:
        tier_eligible.update(TIERS[tier])
    excluded: list[dict[str, str]] = []
    result = []
    candidates = list(preferred) + [model for model in ALLOWED_MODELS if model not in preferred]
    for model in candidates:
        reason = None
        if model not in available:
            reason = "unavailable"
        elif model not in tier_eligible:
            reason = "below_minimum_tier"
        if reason:
            excluded.append({"model_alias": model, "reason": reason})
        else:
            result.append(model)
    return result, excluded


def _op_cost_router(request: Mapping[str, Any]) -> Mapping[str, Any]:
    mode = str(request.get("mode", "smart"))
    if mode not in {"smart", "manual"}:
        raise SkillRuntimeError("mode must be smart or manual")
    eligible, excluded = _eligible_models(request)
    selected_model = request.get("selected_model")
    if mode == "manual":
        if not isinstance(selected_model, str) or selected_model not in ALLOWED_MODELS:
            raise SkillRuntimeError("manual mode requires an allowlisted selected_model")
        if selected_model not in eligible:
            return {
                "decision": "PREFLIGHT_BLOCKED",
                "selected_model": None,
                "reason": "manual_model_ineligible",
                "excluded": excluded,
            }
        return {
            "decision": "ROUTED",
            "selected_model": selected_model,
            "mode": "manual",
            "score": None,
            "excluded": excluded,
        }
    metrics = _mapping(request.get("model_metrics", {}), "model_metrics")
    scored = []
    for model in eligible:
        metric = _mapping(metrics.get(model, {}), f"model_metrics.{model}")
        p_success = _probability(metric.get("p_success"), "p_success", "0.5")
        quality = _probability(metric.get("quality"), "quality", "0.5")
        cache_affinity = _probability(metric.get("cache_affinity"), "cache_affinity", "1")
        invoke_cost = _decimal(metric.get("invoke_cost"), "invoke_cost", "1")
        escalation = _decimal(metric.get("expected_escalation_cost"), "expected_escalation_cost")
        integration = _decimal(metric.get("integration_risk_cost"), "integration_risk_cost")
        retry = _decimal(metric.get("retry_penalty"), "retry_penalty")
        latency = max(Decimal("0.000001"), _decimal(metric.get("latency_factor"), "latency_factor", "1"))
        total = invoke_cost + (Decimal("1") - p_success) * escalation + integration + retry
        if total <= 0:
            raise SkillRuntimeError("expected_total_cost must be positive")
        score = p_success * quality * cache_affinity / (total * latency)
        scored.append(
            {
                "model_alias": model,
                "score": float(score),
                "expected_total_cost": _money(total),
            }
        )
    scored.sort(key=lambda item: (-item["score"], item["expected_total_cost"], item["model_alias"]))
    return {
        "decision": "ROUTED" if scored else "PREFLIGHT_BLOCKED",
        "selected_model": scored[0]["model_alias"] if scored else None,
        "mode": "smart",
        "ranked_candidates": scored,
        "excluded": excluded,
    }


def _op_budget(request: Mapping[str, Any]) -> Mapping[str, Any]:
    hard_cap = _decimal(request.get("hard_cost"), "hard_cost")
    estimates = _items(request.get("task_estimates", []), "task_estimates")
    base = sum((_decimal(item.get("cost"), "task.cost") for item in estimates), Decimal("0"))
    integration_reserve = base * Decimal("0.20")
    escalation_reserve = base * Decimal("0.15")
    total = base + integration_reserve + escalation_reserve
    return {
        "base_cost": _money(base),
        "integration_certification_reserve": _money(integration_reserve),
        "escalation_reserve": _money(escalation_reserve),
        "planned_total": _money(total),
        "hard_cost": _money(hard_cap),
        "feasible": hard_cap > 0 and total <= hard_cap,
    }


def _critical_path(
    tasks: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> tuple[list[str], Decimal]:
    ids = [str(task.get("id", "")) for task in tasks]
    order, adjacency, _, errors = _topological(ids, edges)
    if errors:
        raise SkillRuntimeError("cannot compute critical path for invalid DAG: " + ",".join(errors))
    duration = {
        str(task.get("id", "")): _decimal(task.get("duration_seconds"), "duration_seconds")
        for task in tasks
    }
    best = {node: duration[node] for node in ids}
    predecessor: dict[str, str] = {}
    for node in order:
        for target in adjacency[node]:
            candidate = best[node] + duration[target]
            if candidate > best[target]:
                best[target] = candidate
                predecessor[target] = node
    end = max(ids, key=lambda node: (best[node], node), default="")
    path = []
    while end:
        path.append(end)
        end = predecessor.get(end, "")
    return list(reversed(path)), (max(best.values()) if best else Decimal("0"))


def _op_eta(request: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks = _items(request.get("tasks", []), "tasks")
    edges = _items(request.get("edges", []), "edges")
    path, p50 = _critical_path(tasks, edges)
    uncertainty = _decimal(request.get("p90_multiplier"), "p90_multiplier", "1.5")
    return {"critical_path": path, "p50_seconds": float(p50), "p90_seconds": float(p50 * uncertainty), "basis": "autonomous_machine_wall_clock"}


def _op_wave_scheduler(request: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks = _items(request.get("tasks", []), "tasks")
    edges = _items(request.get("edges", []), "edges")
    built = _op_dag_builder({"tasks": tasks, "edges": edges})
    if not built["valid"]:
        return {"dispatchable": False, "waves": [], "errors": built["errors"]}
    task_map = {str(task["id"]): task for task in tasks}
    waves = []
    for wave in built["waves"]:
        subwaves: list[list[str]] = []
        for task_id in wave:
            paths = _strings(task_map[task_id].get("owned_paths", []), "owned_paths")
            placed = False
            for subwave in subwaves:
                existing = [
                    path
                    for existing_id in subwave
                    for path in _strings(task_map[existing_id].get("owned_paths", []), "owned_paths")
                ]
                if not any(_path_overlap(path, other) for path in paths for other in existing):
                    subwave.append(task_id)
                    placed = True
                    break
            if not placed:
                subwaves.append([task_id])
        waves.extend(subwaves)
    return {"dispatchable": True, "waves": waves, "path_lock_safe": True}


def _op_worktree(request: Mapping[str, Any]) -> Mapping[str, Any]:
    task_id = str(request.get("task_id", "")).strip()
    base = str(request.get("base_commit", "")).strip()
    if not task_id or not base:
        raise SkillRuntimeError("task_id and base_commit are required")
    return {
        "task_id": task_id,
        "base_commit": base,
        "branch": f"codex/task-{task_id.lower()}",
        "worktree_operation": "PREPARED_ONLY",
        "git_mutated": False,
        "requires_trusted_broker": True,
    }


def _op_prompt(request: Mapping[str, Any]) -> Mapping[str, Any]:
    task = _mapping(request.get("task", {}), "task")
    objective = str(task.get("objective", "")).strip()
    if not objective:
        raise SkillRuntimeError("task.objective is required")
    lines = [
        f"Objective: {objective}",
        "Owned paths: " + ", ".join(_strings(task.get("owned_paths", []), "owned_paths")),
        "Read paths: " + ", ".join(_strings(task.get("read_paths", []), "read_paths")),
        "Forbidden paths: " + ", ".join(_strings(task.get("forbidden_paths", []), "forbidden_paths")),
        "Acceptance commands: " + " && ".join(_strings(task.get("acceptance", []), "acceptance")),
        "Return a minimal scoped patch and evidence; do not claim unexecuted checks.",
    ]
    return {"worker_prompt": "\n".join(lines), "prompt_digest": canonical_digest(lines), "secrets_included": False}


def _op_worker_executor(request: Mapping[str, Any]) -> Mapping[str, Any]:
    model = str(request.get("model_alias", ""))
    if model not in ALLOWED_MODELS:
        raise SkillRuntimeError("model_alias is not allowlisted")
    return {
        "model_alias": model,
        "dispatch_state": "BROKER_REQUIRED",
        "provider_invoked": False,
        "patch_applied": False,
        "external_evidence": "NOT_RUN",
    }


def _op_deterministic_validator(request: Mapping[str, Any]) -> Mapping[str, Any]:
    checks = _items(request.get("checks", []), "checks")
    results = []
    for check in checks:
        status = str(check.get("status", "NOT_RUN")).upper()
        if status not in {"PASS", "FAIL", "NOT_RUN", "BLOCKED"}:
            raise SkillRuntimeError("check status must be PASS, FAIL, NOT_RUN, or BLOCKED")
        results.append({"name": str(check.get("name", "")), "status": status, "evidence_ref": check.get("evidence_ref")})
    passed = bool(results) and all(item["status"] == "PASS" and item["evidence_ref"] for item in results)
    return {"checks": results, "decision": "PASS" if passed else "BLOCKED", "accepted": passed}


def _op_failure_classifier(request: Mapping[str, Any]) -> Mapping[str, Any]:
    text = " ".join(_strings(request.get("signals", []), "signals")).lower()
    patterns = [
        ("security_policy_violation", ("secret", "permission denied", "policy violation")),
        ("forbidden_path_write", ("forbidden path", "outside owned")),
        ("budget_hard_stop", ("budget", "quota exhausted")),
        ("transient_tool", ("timeout", "temporarily unavailable", "connection reset")),
        ("formatting", ("format", "lint")),
        ("context_loss", ("missing context", "context length")),
        ("integration", ("merge conflict", "integration")),
        ("architectural", ("architecture", "invariant")),
        ("semantic", ("assertion", "wrong behavior", "type error")),
    ]
    failure = "localized_test_failure"
    for candidate, needles in patterns:
        if any(needle in text for needle in needles):
            failure = candidate
            break
    action = {
        "security_policy_violation": "stop",
        "forbidden_path_write": "stop",
        "budget_hard_stop": "stop",
        "transient_tool": "retry_same_model",
        "formatting": "retry_same_model",
        "context_loss": "repair_context_and_promote",
        "integration": "replan_boundary_and_promote",
        "architectural": "global_review_and_promote",
        "semantic": "promote",
        "localized_test_failure": "retry_same_model",
    }[failure]
    return {"failure_class": failure, "recommended_action": action, "evidence": _strings(request.get("signals", []), "signals")}


def _op_retry(request: Mapping[str, Any]) -> Mapping[str, Any]:
    failure = str(request.get("failure_class", ""))
    attempt = int(request.get("attempt", 1))
    mode = str(request.get("mode", "smart"))
    current = str(request.get("model_alias", ""))
    if current not in ALLOWED_MODELS:
        raise SkillRuntimeError("model_alias is not allowlisted")
    if failure in {"forbidden_path_write", "security_policy_violation", "budget_hard_stop"}:
        return {"action": "TERMINAL_STOP", "next_model": None}
    if attempt >= 4:
        return {"action": "ATTEMPTS_EXHAUSTED", "next_model": None}
    if failure in {"transient_tool", "formatting", "localized_test_failure"} and attempt < 2:
        return {"action": "RETRY", "next_model": current}
    if mode == "manual" and str(request.get("fallback_policy", "strict")) == "strict":
        return {"action": "MODEL_RESELECTION_REQUIRED", "next_model": None}
    eligible, _ = _eligible_models({**dict(request), "minimum_tier": "L3"})
    promoted = next((model for model in eligible if model != current), None)
    return {"action": "PROMOTE" if promoted else "TERMINAL_STOP", "next_model": promoted}


def _gate(request: Mapping[str, Any], required: Sequence[str]) -> Mapping[str, Any]:
    evidence = _items(request.get("evidence", []), "evidence")
    by_name = {str(item.get("name", "")): item for item in evidence}
    missing = [name for name in required if name not in by_name]
    failed = [
        name
        for name in required
        if name in by_name
        and (str(by_name[name].get("status", "NOT_RUN")).upper() != "PASS" or not by_name[name].get("evidence_ref"))
    ]
    return {"decision": "PASS" if not missing and not failed else "BLOCKED", "missing": missing, "failed_or_unbound": failed}


def _op_patch_reviewer(request: Mapping[str, Any]) -> Mapping[str, Any]:
    findings = _items(request.get("findings", []), "findings")
    blocking = [dict(item) for item in findings if str(item.get("severity", "")).lower() in {"critical", "high"}]
    return {"decision": "CHANGES_REQUIRED" if blocking else "APPROVE_LOCAL_REVIEW", "blocking_findings": blocking, "independent_review": "NOT_RUN"}


def _op_security_gate(request: Mapping[str, Any]) -> Mapping[str, Any]:
    return _gate(request, ("threat_check", "secret_scan", "authorization_negative_tests"))


def _op_data_gate(request: Mapping[str, Any]) -> Mapping[str, Any]:
    result = _gate(request, ("migration_forward", "data_integrity_check", "rollback_or_approved_irreversible"))
    return {**result, "production_database": "NOT_RUN"}


def _op_concurrency_gate(request: Mapping[str, Any]) -> Mapping[str, Any]:
    return _gate(request, ("race_or_stress_tests", "idempotency_check", "cancellation_or_recovery"))


def _op_integration_manager(request: Mapping[str, Any]) -> Mapping[str, Any]:
    patches = _items(request.get("patches", []), "patches")
    ordered = sorted((str(item.get("task_id", "")) for item in patches))
    return {"integration_order": ordered, "state": "PREPARED_ONLY", "git_mutated": False, "requires_trusted_broker": True}


def _op_conflict_resolver(request: Mapping[str, Any]) -> Mapping[str, Any]:
    conflicts = _items(request.get("conflicts", []), "conflicts")
    return {
        "resolution_plans": [
            {
                "path": str(item.get("path", "")),
                "strategy": "reconcile_contracts_then_minimal_combined_behavior",
                "automatic_resolution": False,
            }
            for item in conflicts
        ],
        "git_mutated": False,
    }


def _op_regression(request: Mapping[str, Any]) -> Mapping[str, Any]:
    changed = set(_strings(request.get("changed_nodes", []), "changed_nodes"))
    tests = _items(request.get("tests", []), "tests")
    selected = []
    for test in tests:
        covers = set(_strings(test.get("covers", []), "test.covers"))
        if changed & covers or bool(test.get("always_run")):
            selected.append(str(test.get("id", "")))
    return {"selected_tests": sorted(set(selected)), "execution": "NOT_RUN", "unexpected_impact": []}


def _op_certifier(request: Mapping[str, Any]) -> Mapping[str, Any]:
    required = (
        "clean_build",
        "full_regression",
        "acceptance_scenarios",
        "requirement_traceability",
        "no_unowned_diff",
        "dependency_graph_complete",
    )
    gate = _gate(request, required)
    independent = bool(request.get("independent_verification"))
    external = str(request.get("external_evidence", "NOT_RUN")) == "VERIFIED"
    local_ready = gate["decision"] == "PASS"
    return {
        **gate,
        "local_ready": local_ready,
        "decision": "READY_FOR_EXTERNAL_GATE" if local_ready else "BLOCKED",
        "certified": False,
        "independent_verification": "VERIFIED" if independent else "NOT_RUN",
        "external_evidence": "VERIFIED" if external else "NOT_RUN",
    }


def _op_recovery(request: Mapping[str, Any]) -> Mapping[str, Any]:
    events = _items(request.get("events", []), "events")
    completed = sorted(
        {
            str(item.get("task_id"))
            for item in events
            if str(item.get("state", "")).upper() == "PASSED" and item.get("task_id")
        }
    )
    return {"preserve_tasks": completed, "state": "RECOVERY_PLANNED", "rollback_performed": False, "git_mutated": False}


def _op_run_journal(request: Mapping[str, Any]) -> Mapping[str, Any]:
    events = _items(request.get("events", []), "events")
    previous = str(request.get("previous_digest", "GENESIS"))
    chained = []
    for index, event in enumerate(events, start=1):
        record = {"sequence": index, "previous_digest": previous, "event": dict(event)}
        digest = canonical_digest(record)
        chained.append({**record, "digest": digest})
        previous = digest
    return {"events": chained, "head_digest": previous, "persisted": False, "requires_trusted_store": True}


def _op_telemetry(request: Mapping[str, Any]) -> Mapping[str, Any]:
    records = _items(request.get("records", []), "records")
    accepted = [item for item in records if bool(item.get("accepted"))]
    total_cost = sum((_decimal(item.get("cost"), "cost") for item in records), Decimal("0"))
    return {
        "sample_count": len(records),
        "accepted_count": len(accepted),
        "success_rate": (len(accepted) / len(records)) if records else None,
        "total_cost": _money(total_cost),
        "cost_per_accepted_task": _money(total_cost / len(accepted)) if accepted else None,
        "policy_mutated": False,
    }


def _op_policy_optimizer(request: Mapping[str, Any]) -> Mapping[str, Any]:
    telemetry = _items(request.get("telemetry", []), "telemetry")
    by_model: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in telemetry:
        model = str(item.get("model_alias", ""))
        if model not in ALLOWED_MODELS:
            raise SkillRuntimeError(f"unknown model in telemetry: {model}")
        by_model[model].append(item)
    proposals = []
    for model, items in sorted(by_model.items()):
        if len(items) < 30:
            continue
        success = sum(int(bool(item.get("accepted"))) for item in items) / len(items)
        proposals.append({"model_alias": model, "observations": len(items), "success_rate": success, "action": "HUMAN_REVIEW_PRIOR_UPDATE"})
    return {"proposals": proposals, "policy_mutated": False}


def _op_model_selection(request: Mapping[str, Any]) -> Mapping[str, Any]:
    mode = str(request.get("mode", "smart"))
    if mode == "smart":
        profile = str(request.get("optimization_profile", "cost_performance"))
        if profile not in {"cost_performance", "lowest_cost", "max_quality", "fastest"}:
            raise SkillRuntimeError("unsupported optimization_profile")
        return {"mode": "smart", "selected_model": None, "optimization_profile": profile, "locked": False}
    if mode != "manual":
        raise SkillRuntimeError("mode must be smart or manual")
    selected = str(request.get("selected_model", ""))
    if selected not in ALLOWED_MODELS:
        raise SkillRuntimeError("manual selected_model is not allowlisted")
    fallback = str(request.get("fallback_policy", "strict"))
    if fallback not in {"strict", "smart_within_allowlist"}:
        raise SkillRuntimeError("unsupported fallback_policy")
    verification = str(request.get("verification_policy", "system_required_verifiers"))
    if verification not in {"system_required_verifiers", "selected_model_only"}:
        raise SkillRuntimeError("unsupported verification_policy")
    return {"mode": "manual", "selected_model": selected, "fallback_policy": fallback, "verification_policy": verification, "locked": True}


def _op_implicit_requirements(request: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = _items(request.get("candidates", []), "candidates")
    inferred = []
    exploration = []
    for item in candidates:
        confidence = _probability(item.get("confidence"), "confidence")
        normalized = {
            "id": str(item.get("id", "")),
            "statement": str(item.get("statement", "")),
            "evidence_refs": _strings(item.get("evidence_refs", []), "evidence_refs"),
            "confidence": float(confidence),
        }
        if not normalized["evidence_refs"] or confidence < Decimal("0.70"):
            exploration.append(normalized)
        else:
            inferred.append(normalized)
    return {"inferred_requirements": inferred, "exploration_candidates": exploration}


def _op_scenario_graph(request: Mapping[str, Any]) -> Mapping[str, Any]:
    scenarios = _items(request.get("scenarios", []), "scenarios")
    edges = _items(request.get("edges", []), "edges")
    ids = [str(item.get("id", "")) for item in scenarios]
    _, _, _, errors = _topological(ids, edges)
    required_kinds = {"happy", "failure", "boundary", "compatibility", "rollback", "operational"}
    observed = {str(item.get("kind", "")) for item in scenarios}
    return {"scenarios": [dict(item) for item in scenarios], "edges": [dict(item) for item in edges], "errors": errors, "missing_kinds": sorted(required_kinds - observed)}


def _op_rig(request: Mapping[str, Any]) -> Mapping[str, Any]:
    nodes = _items(request.get("nodes", []), "nodes")
    edges = _items(request.get("edges", []), "edges")
    ids = {str(item.get("id", "")) for item in nodes}
    errors = []
    for item in nodes:
        if not item.get("evidence_ref"):
            errors.append(f"node_missing_evidence:{item.get('id', '')}")
    for edge in edges:
        if str(edge.get("from", "")) not in ids or str(edge.get("to", "")) not in ids:
            errors.append(f"edge_unknown_node:{edge.get('from')}->{edge.get('to')}")
        if not edge.get("evidence_ref"):
            errors.append(f"edge_missing_evidence:{edge.get('from')}->{edge.get('to')}")
    return {"revision": str(request.get("revision", "UNRESOLVED")), "nodes": [dict(item) for item in nodes], "edges": [dict(item) for item in edges], "valid": not errors, "errors": sorted(errors)}


def _op_invariants(request: Mapping[str, Any]) -> Mapping[str, Any]:
    invariants = _items(request.get("invariants", []), "invariants")
    normalized = []
    for item in invariants:
        status = str(item.get("status", "UNVERIFIED")).upper()
        if status not in {"VERIFIED", "UNVERIFIED", "VIOLATED"}:
            raise SkillRuntimeError("invalid invariant status")
        normalized.append({**dict(item), "status": status})
    return {"invariants": normalized, "blocking": [str(item.get("id", "")) for item in normalized if item["status"] != "VERIFIED" and str(item.get("risk", "")).lower() in {"high", "critical"}]}


def _op_seams(request: Mapping[str, Any]) -> Mapping[str, Any]:
    candidates = _items(request.get("candidates", []), "candidates")
    safe, unsafe = [], []
    for item in candidates:
        cohesion = _probability(item.get("semantic_cohesion"), "semantic_cohesion", "0.5")
        coupling = _probability(item.get("cross_boundary_coupling"), "cross_boundary_coupling", "0.5")
        locality = _probability(item.get("verification_locality"), "verification_locality", "0.5")
        score = cohesion * (Decimal("1") - coupling) * locality
        result = {**dict(item), "seam_score": float(score)}
        if bool(item.get("cuts_indivisible_invariant")) or score < Decimal("0.15"):
            unsafe.append(result)
        else:
            safe.append(result)
    return {"recommended_seams": sorted(safe, key=lambda item: (-item["seam_score"], str(item.get("id", "")))), "unsafe_seams": unsafe}


def _op_hierarchical_plan(request: Mapping[str, Any]) -> Mapping[str, Any]:
    nodes = _items(request.get("nodes", []), "nodes")
    allowed_levels = {"goal", "capability", "changeset", "atomic_task", "microstep"}
    if any(str(item.get("hierarchy_level", "")) not in allowed_levels for item in nodes):
        raise SkillRuntimeError("invalid hierarchy_level")
    rank_uncertainty = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    frontier = []
    for item in nodes:
        if item.get("hierarchy_level") in {"atomic_task", "microstep"}:
            continue
        if str(item.get("status", "planned")) not in {"coarse", "planned", "ready"}:
            continue
        unc_val = item.get("uncertainty", "low")
        uncertainty = str(unc_val.get("level", "low") if isinstance(unc_val, Mapping) else unc_val).lower()
        risk_val = item.get("risk", "low")
        risk_value = str((risk_val.get("criticality") or risk_val.get("blast_radius") or "low") if isinstance(risk_val, Mapping) else risk_val).lower()
        score = 10 * rank_uncertainty.get(uncertainty, 1) + 5 * RISK_RANK.get(risk_value, 1) + (3 if item.get("status") == "ready" else 0)
        frontier.append((score, str(item.get("id", ""))))
    return {"nodes": [dict(item) for item in nodes], "refinement_frontier": [item for _, item in sorted(frontier, key=lambda pair: (-pair[0], pair[1]))], "lazy_refinement": True}


def _op_granularity(request: Mapping[str, Any]) -> Mapping[str, Any]:
    features = _mapping(request.get("features", {}), "features")
    score = Decimal("0")
    for key, weight in GRANULARITY_WEIGHTS.items():
        score += _probability(features.get(key), key) * weight
    reasons = []
    if bool(request.get("indivisible_invariant")):
        decision = "keep"
        reasons.append("indivisible_invariant")
    elif bool(request.get("unsafe_split_requires_merge")):
        decision = "merge"
        reasons.append("unsafe_split_requires_merge")
    elif score >= Decimal("0.72"):
        decision = "split"
        reasons.append("score_above_split_threshold")
    elif score <= Decimal("0.20"):
        decision = "merge"
        reasons.append("score_below_merge_threshold")
    else:
        decision = "keep"
        reasons.append("within_target_band")
    return {"score": float(score.quantize(Decimal("0.000001"))), "decision": decision, "reasons": reasons}


def _op_plan_verifier(request: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks_raw = request.get("tasks")
    if tasks_raw is None and "nodes" in request:
        nodes = _items(request.get("nodes", []), "nodes")
        atomic_nodes = [item for item in nodes if str(item.get("hierarchy_level", "")) == "atomic_task"]
        tasks = atomic_nodes if atomic_nodes else nodes
    else:
        tasks = _items(tasks_raw or [], "tasks")
    edges = _items(request.get("edges", []), "edges")
    errors = _graph_errors(tasks, edges)
    coverage = _coverage(tasks, request)
    for group, gaps in coverage.items():
        errors.extend(f"{group}:{item}" for item in gaps)
    return {"executable": not errors, "errors": sorted(set(errors)), "coverage": coverage}


def _op_exploration(request: Mapping[str, Any]) -> Mapping[str, Any]:
    uncertainties = _items(request.get("uncertainties", []), "uncertainties")
    hard_budget = _decimal(request.get("run_budget"), "run_budget") * Decimal("0.12")
    tasks = []
    consumed = Decimal("0")
    for index, item in enumerate(uncertainties, start=1):
        cost = _decimal(item.get("estimated_cost"), "estimated_cost")
        if consumed + cost > hard_budget:
            break
        consumed += cost
        tasks.append({"id": f"EXP{index:03d}", "question": str(item.get("question", "")), "decision_unblocked": str(item.get("decision_unblocked", "")), "estimated_cost": _money(cost)})
    return {"exploration_tasks": tasks, "budget": _money(hard_budget), "planned_cost": _money(consumed), "execution": "NOT_RUN"}


def _op_proofs(request: Mapping[str, Any]) -> Mapping[str, Any]:
    boundaries = _items(request.get("boundaries", []), "boundaries")
    proofs = []
    required_kinds = {"public_api", "security", "authentication", "authorization", "transaction", "concurrency", "idempotency", "data_migration", "backward_compatibility", "distributed_side_effect"}
    for index, item in enumerate(boundaries, start=1):
        if str(item.get("kind", "")) not in required_kinds:
            continue
        proofs.append({"id": f"PO{index:03d}", "statement": str(item.get("invariant", item.get("kind", ""))), "scope": _strings(item.get("scope", []), "scope"), "preferred_verifier": str(item.get("preferred_verifier", "deterministic_test")), "status": "NOT_RUN"})
    return {"proof_obligations": proofs}


def _op_integration_edges(request: Mapping[str, Any]) -> Mapping[str, Any]:
    edges = _items(request.get("edges", []), "edges")
    planned = []
    for edge in edges:
        cross_boundary = str(edge.get("type", "dependency")) in {"contract", "schema", "data", "runtime", "integration"}
        planned.append({**dict(edge), "barrier_required": cross_boundary, "handoff_ready": bool(edge.get("contract_ref") and edge.get("validator")) if cross_boundary else True})
    return {"edges": planned, "all_handoffs_ready": all(item["handoff_ready"] for item in planned)}


def _op_replanner(request: Mapping[str, Any]) -> Mapping[str, Any]:
    trigger = str(request.get("trigger", "")).lower()
    if trigger in {"contract_change", "integration_conflict", "schema_change"}:
        scope = "boundary_cluster"
    elif trigger in {"acceptance_scenario_change", "architecture_invariant_change", "global_requirement_change"}:
        scope = "global"
    else:
        scope = "local"
    return {"scope": scope, "trigger": trigger, "preserved_evidence": _strings(request.get("still_valid_evidence", []), "still_valid_evidence"), "plan_mutated": False, "next_revision_required": True}


def _op_semantic_conflicts(request: Mapping[str, Any]) -> Mapping[str, Any]:
    patches = _items(request.get("patches", []), "patches")
    conflicts = []
    for index, left in enumerate(patches):
        left_paths = _strings(left.get("paths", []), "patch.paths")
        for right in patches[index + 1 :]:
            right_paths = _strings(right.get("paths", []), "patch.paths")
            overlap = sorted({a for a in left_paths for b in right_paths if _path_overlap(a, b)})
            shared_contracts = sorted(set(_strings(left.get("contracts", []), "contracts")) & set(_strings(right.get("contracts", []), "contracts")))
            if overlap or shared_contracts:
                conflicts.append({"left": str(left.get("task_id", "")), "right": str(right.get("task_id", "")), "overlapping_paths": overlap, "shared_contracts": shared_contracts})
    return {"conflicts": conflicts, "safe_to_integrate": not conflicts}


def _op_critical_scheduler(request: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks = _items(request.get("tasks", []), "tasks")
    edges = _items(request.get("edges", []), "edges")
    path, seconds = _critical_path(tasks, edges)
    wave = _op_wave_scheduler({"tasks": tasks, "edges": edges})
    return {"critical_path": path, "critical_path_seconds": float(seconds), "waves": wave["waves"], "dispatchable": wave["dispatchable"]}


def _op_baseline(request: Mapping[str, Any]) -> Mapping[str, Any]:
    observations = canonical_value(request.get("observations", {}))
    environment = canonical_value(request.get("environment", {}))
    return {"baseline_digest": canonical_digest(observations), "environment_digest": canonical_digest(environment), "known_failures": sorted(set(_strings(request.get("known_failures", []), "known_failures"))), "commands_executed": False}


def _op_plan_diff(request: Mapping[str, Any]) -> Mapping[str, Any]:
    before = _mapping(request.get("before", {}), "before")
    after = _mapping(request.get("after", {}), "after")
    before_nodes = {str(item.get("id", "")): item for item in _items(before.get("nodes", []), "before.nodes")}
    after_nodes = {str(item.get("id", "")): item for item in _items(after.get("nodes", []), "after.nodes")}
    return {
        "added_nodes": sorted(set(after_nodes) - set(before_nodes)),
        "removed_nodes": sorted(set(before_nodes) - set(after_nodes)),
        "changed_nodes": sorted(node for node in set(before_nodes) & set(after_nodes) if canonical_digest(before_nodes[node]) != canonical_digest(after_nodes[node])),
        "before_digest": canonical_digest(before),
        "after_digest": canonical_digest(after),
        "persisted": False,
    }


def _op_decomposition_telemetry(request: Mapping[str, Any]) -> Mapping[str, Any]:
    records = _items(request.get("records", []), "records")
    metrics = {}
    boolean_fields = (
        "first_pass_success",
        "replanned",
        "split_after_start",
        "merge_after_start",
        "integration_conflict",
        "hidden_dependency",
        "context_overflow",
    )
    for field in boolean_fields:
        metrics[field + "_rate"] = (sum(int(bool(item.get(field))) for item in records) / len(records)) if records else None
    metrics["sample_count"] = len(records)
    return {"metrics": metrics, "priors_mutated": False, "minimum_samples_met": len(records) >= 30}


HANDLERS: Final[Mapping[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]]] = MappingProxyType(
    {
        "elmos-repository-orchestrator": _op_repository_orchestrator,
        "elmos-requirement-normalizer": _op_requirement_normalizer,
        "elmos-repo-intake": _op_repo_intake,
        "elmos-architecture-indexer": _op_architecture_indexer,
        "elmos-change-impact-analyzer": _op_change_impact,
        "elmos-task-decomposer": _op_task_decomposer,
        "elmos-atomicity-validator": _op_atomicity,
        "elmos-task-dag-builder": _op_dag_builder,
        "elmos-contract-boundary-generator": _op_contract_boundary,
        "elmos-complexity-estimator": _op_complexity,
        "elmos-risk-classifier": _op_risk,
        "elmos-context-slicer": _op_context_slicer,
        "elmos-model-registry-guard": _op_registry_guard,
        "elmos-model-capability-profiler": _op_capability_profiler,
        "elmos-cost-performance-router": _op_cost_router,
        "elmos-budget-planner": _op_budget,
        "elmos-eta-estimator": _op_eta,
        "elmos-wave-scheduler": _op_wave_scheduler,
        "elmos-worktree-manager": _op_worktree,
        "elmos-worker-prompt-builder": _op_prompt,
        "elmos-worker-executor": _op_worker_executor,
        "elmos-deterministic-validator": _op_deterministic_validator,
        "elmos-failure-classifier": _op_failure_classifier,
        "elmos-retry-escalation-controller": _op_retry,
        "elmos-patch-reviewer": _op_patch_reviewer,
        "elmos-security-auth-gate": _op_security_gate,
        "elmos-data-migration-gate": _op_data_gate,
        "elmos-concurrency-idempotency-gate": _op_concurrency_gate,
        "elmos-integration-manager": _op_integration_manager,
        "elmos-conflict-resolver": _op_conflict_resolver,
        "elmos-incremental-regression-gate": _op_regression,
        "elmos-repository-certifier": _op_certifier,
        "elmos-rollback-recovery": _op_recovery,
        "elmos-run-state-journal": _op_run_journal,
        "elmos-telemetry-learner": _op_telemetry,
        "elmos-routing-policy-optimizer": _op_policy_optimizer,
        "elmos-model-selection-controller": _op_model_selection,
        "elmos-implicit-requirement-miner": _op_implicit_requirements,
        "elmos-behavioral-scenario-graph": _op_scenario_graph,
        "elmos-repository-intelligence-graph": _op_rig,
        "elmos-architecture-invariant-ledger": _op_invariants,
        "elmos-semantic-seam-detector": _op_seams,
        "elmos-adaptive-hierarchical-planner": _op_hierarchical_plan,
        "elmos-task-granularity-controller": _op_granularity,
        "elmos-plan-graph-verifier": _op_plan_verifier,
        "elmos-uncertainty-exploration-planner": _op_exploration,
        "elmos-proof-obligation-generator": _op_proofs,
        "elmos-integration-edge-planner": _op_integration_edges,
        "elmos-dynamic-replanner": _op_replanner,
        "elmos-semantic-conflict-detector": _op_semantic_conflicts,
        "elmos-critical-path-resource-scheduler": _op_critical_scheduler,
        "elmos-baseline-golden-snapshotter": _op_baseline,
        "elmos-plan-diff-audit-journal": _op_plan_diff,
        "elmos-decomposition-telemetry-learner": _op_decomposition_telemetry,
    }
)


def invoke(skill: str, request: Mapping[str, Any], scope: RuntimeScope) -> Mapping[str, Any]:
    handler = HANDLERS.get(skill)
    if handler is None:
        raise SkillRuntimeError(f"unknown skill: {skill}")
    _mapping(request, "request")
    try:
        canonical = canonical_value(request)
    except CanonicalValueError as exc:
        raise SkillRuntimeError(str(exc)) from exc
    if len(str(canonical).encode("utf-8")) > 16 * 1024 * 1024:
        raise SkillRuntimeError("request exceeds 16 MiB canonical budget")
    bound_scope = request.get("scope_digest")
    if bound_scope is not None and bound_scope != scope.digest:
        raise SkillRuntimeError("request scope_digest does not match trusted scope")
    output = dict(handler(_mapping(canonical, "request")))
    forbidden_truthy = {
        "certified",
        "provider_invoked",
        "patch_applied",
        "git_mutated",
        "rollback_performed",
        "commands_executed",
        "persisted",
        "policy_mutated",
        "priors_mutated",
        "automatic_effects",
    }
    for key in forbidden_truthy:
        if output.get(key) is True:
            raise SkillRuntimeError(f"local handler promoted unavailable authority: {key}")
    envelope = {
        "schema_version": "elmos.repository-orchestrator.outcome.v1",
        "skill": skill,
        "handler_id": f"repo-orchestrator.{skill.removeprefix('elmos-')}.v1",
        "scope_digest": scope.digest,
        "request_digest": canonical_digest(canonical),
        "evidence_state": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "effect_mode": "PREPARE_ONLY" if skill in EFFECTFUL_SKILLS else "LOCAL_PURE",
        "output": output,
    }
    return canonical_value(envelope)
