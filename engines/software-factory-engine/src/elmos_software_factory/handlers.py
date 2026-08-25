"""Deterministic, bounded local handlers for P00 through P07."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_digest, is_sha256_digest, strict_json_copy
from .models import ExecutionError, ExecutionRequest, ExecutionStatus
from .registry import PackageDefinition, SkillRegistry


@dataclass(frozen=True)
class HandlerOutcome:
    status: ExecutionStatus
    output: Mapping[str, Any]
    error: ExecutionError | None = None


@dataclass(frozen=True)
class HandlerContext:
    skill_name: str
    capability_identity: str
    capability_action: str
    required_inputs: tuple[str, ...]


def _blocked(code: str, message: str, **details: Any) -> HandlerOutcome:
    return HandlerOutcome(
        ExecutionStatus.BLOCKED,
        {},
        ExecutionError(code, message, False, details or None),
    )


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _object(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 192:
        raise ValueError(f"{field} must be a non-empty bounded string")
    return value


def _integer(value: object, field: str, *, minimum: int = 0, maximum: int = 10**15) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


def _action(payload: Mapping[str, Any], default: str) -> str:
    return _identifier(payload.get("action", default), "payload.action")


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unsupported payload fields: {', '.join(unknown)}")


def _string_list(value: object, field: str, *, limit: int = 4096) -> list[str]:
    items = _array(value, field)
    if len(items) > limit:
        raise ValueError(f"{field} exceeds limit {limit}")
    parsed = [_identifier(item, f"{field}[]") for item in items]
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{field} contains duplicates")
    return parsed


def _topological_nodes(value: object, *, max_nodes: int) -> tuple[list[dict[str, Any]], list[str]]:
    items = _array(value, "payload.nodes")
    if len(items) > max_nodes:
        raise ValueError(f"payload.nodes exceeds policy max_nodes {max_nodes}")
    normalized: list[dict[str, Any]] = []
    by_id: dict[str, tuple[str, ...]] = {}
    for index, item in enumerate(items):
        node = _object(item, f"payload.nodes[{index}]")
        unknown = sorted(set(node) - {"id", "depends_on", "state", "retries", "critical"})
        if unknown:
            raise ValueError(f"payload.nodes[{index}] has unsupported fields: {', '.join(unknown)}")
        node_id = _identifier(node.get("id"), f"payload.nodes[{index}].id")
        if node_id in by_id:
            raise ValueError(f"duplicate node id {node_id}")
        dependencies = tuple(_string_list(node.get("depends_on", []), f"node {node_id}.depends_on"))
        by_id[node_id] = dependencies
        normalized.append(
            {
                "id": node_id,
                "depends_on": list(dependencies),
                "state": _identifier(node.get("state", "pending"), f"node {node_id}.state"),
                "retries": _integer(node.get("retries", 0), f"node {node_id}.retries", maximum=10),
                "critical": node.get("critical", False) is True,
            }
        )
    for node_id, dependencies in by_id.items():
        missing = sorted(set(dependencies) - set(by_id))
        if missing:
            raise ValueError(f"node {node_id} has missing dependencies: {', '.join(missing)}")
        if node_id in dependencies:
            raise ValueError(f"node {node_id} depends on itself")
    indegree = {node_id: len(dependencies) for node_id, dependencies in by_id.items()}
    dependents: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    for node_id, dependencies in by_id.items():
        for dependency in dependencies:
            dependents[dependency].append(node_id)
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for dependent in sorted(dependents[node_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort()
    if len(order) != len(by_id):
        raise ValueError("node dependency graph contains a cycle")
    return normalized, order


def _p00(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    payload = request.payload
    _reject_unknown(
        payload,
        {
            "action", "nodes", "invariants", "violations", "package_id", "capability",
            "version_range", "budget_micros", "job", "config_revision",
        },
    )
    action = _action(payload, "compile-workflow")
    if action == "resolve-package":
        package_id = _identifier(payload.get("package_id"), "payload.package_id")
        resolved = registry.packages.get(package_id)
        if resolved is None:
            return _blocked("PACKAGE_NOT_FOUND", "requested package is not registered", package_id=package_id)
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "package_id": package_id,
                "skill_name": resolved.name,
                "dependencies": list(resolved.dependencies),
                "operation": resolved.operation,
                "capability": payload.get("capability"),
                "version_range": payload.get("version_range"),
                "compatibility_decision": "LOCALLY_REGISTERED_NOT_RUNTIME_CERTIFIED",
            },
        )
    if action == "plan-job":
        budget = _integer(payload.get("budget_micros", 0), "payload.budget_micros")
        if budget > request.policy.max_cost_micros:
            return _blocked("QUOTA_EXCEEDED", "requested budget exceeds policy", requested=budget)
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "job_plan": strict_json_copy(payload.get("job", {}), field="payload.job"),
                "budget_micros": budget,
                "state": "PLANNED_NOT_STARTED",
            },
        )
    if action != "compile-workflow":
        return _blocked("CAPABILITY_UNSUPPORTED", "P00 action has no local handler", action=action)
    nodes, order = _topological_nodes(payload.get("nodes", []), max_nodes=request.policy.max_nodes)
    invariants = _string_list(payload.get("invariants", []), "payload.invariants")
    violations = _string_list(payload.get("violations", []), "payload.violations")
    if violations:
        return _blocked("INVARIANT_VIOLATION", "workflow violates declared invariants", violations=violations)
    contract = {
        "nodes": nodes,
        "topological_order": order,
        "invariants": invariants,
        "policy_revision": request.envelope.policy_revision,
        "source_revision": request.envelope.source_revision,
    }
    return HandlerOutcome(
        ExecutionStatus.EXECUTED,
        {"execution_contract": contract, "contract_digest": canonical_digest(contract)},
    )


def _p01(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(
        payload,
        {"action", "requested_permissions", "sandbox_mode", "tools", "resource", "subject", "context"},
    )
    action = _action(payload, "permission-decision")
    if action not in {"permission-decision", "adapter-contract", "runtime-readiness"}:
        return _blocked("CAPABILITY_UNSUPPORTED", "P01 action requires a runtime adapter", action=action)
    requested = _string_list(payload.get("requested_permissions", []), "payload.requested_permissions")
    denied = sorted(set(requested) - request.policy.allowed_permissions)
    sandbox_mode = _identifier(payload.get("sandbox_mode", "read-only"), "payload.sandbox_mode")
    if sandbox_mode not in request.policy.allowed_sandbox_modes:
        denied.append(f"sandbox:{sandbox_mode}")
    approval_missing = (
        action in request.policy.approval_required_actions
        and action not in request.policy.approved_actions
    )
    decision = "deny" if denied else ("ask" if approval_missing else "allow")
    tools = _string_list(payload.get("tools", []), "payload.tools")
    if action == "adapter-contract":
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "adapter_contract": {
                    "requested_permissions": requested,
                    "sandbox_mode": sandbox_mode,
                    "tools": tools,
                    "policy_decision": decision,
                    "runtime_execution_state": "NOT_STARTED",
                }
            },
        )
    if action == "runtime-readiness":
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "ready": decision == "allow",
                "policy_decision": decision,
                "denied": denied,
                "adapter_availability_state": "NOT_RUN",
                "sandbox_enforcement_state": "NOT_RUN",
            },
        )
    return HandlerOutcome(
        ExecutionStatus.EXECUTED,
        {
            "decision": decision,
            "denied": denied,
            "sandbox_mode": sandbox_mode,
            "tools": tools,
            "enforcement_state": "POLICY_DECISION_ONLY",
        },
    )


def _p02(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(payload, {"action", "inventory", "edges", "capabilities", "unknowns", "query"})
    action = _action(payload, "build-graph")
    if action not in {"build-graph", "compile-semantic-ir", "discover-capabilities", "query-repository"}:
        return _blocked("CAPABILITY_UNSUPPORTED", "P02 action requires a repository adapter", action=action)
    inventory_values = _array(payload.get("inventory", []), "payload.inventory")
    if len(inventory_values) > request.policy.max_nodes:
        return _blocked("QUERY_TOO_EXPENSIVE", "inventory exceeds policy max_nodes")
    inventory: list[dict[str, Any]] = []
    identities: set[str] = set()
    for index, item in enumerate(inventory_values):
        entry = _object(item, f"payload.inventory[{index}]")
        if sorted(set(entry) - {"id", "kind", "language", "framework", "provenance"}):
            raise ValueError(f"payload.inventory[{index}] contains unsupported fields")
        identity = _identifier(entry.get("id"), f"payload.inventory[{index}].id")
        if identity in identities:
            raise ValueError(f"duplicate inventory id {identity}")
        identities.add(identity)
        inventory.append(strict_json_copy(entry, field=f"payload.inventory[{index}]"))
    edges: list[dict[str, str]] = []
    for index, item in enumerate(_array(payload.get("edges", []), "payload.edges")):
        edge = _object(item, f"payload.edges[{index}]")
        if set(edge) != {"from", "to"}:
            raise ValueError(f"payload.edges[{index}] must contain exact from/to fields")
        source = _identifier(edge.get("from"), f"payload.edges[{index}].from")
        target = _identifier(edge.get("to"), f"payload.edges[{index}].to")
        if source not in identities or target not in identities:
            return _blocked("GRAPH_INCONSISTENT", "graph edge references an unknown inventory id")
        edges.append({"from": source, "to": target})
    capabilities = _string_list(payload.get("capabilities", []), "payload.capabilities")
    unknowns = _string_list(payload.get("unknowns", []), "payload.unknowns")
    snapshot = {
        "inventory": sorted(inventory, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"])),
        "capabilities": sorted(capabilities),
        "unknowns": sorted(unknowns),
        "coverage": {
            "known": len(capabilities),
            "unknown": len(unknowns),
            "complete": not unknowns,
        },
        "source_revision": request.envelope.source_revision,
    }
    query_plan = None
    if action == "query-repository":
        query = strict_json_copy(_object(payload.get("query"), "payload.query"), field="payload.query")
        query_plan = {
            "query": query,
            "query_digest": canonical_digest(query),
            "snapshot_result_limit": request.policy.max_nodes,
            "execution_state": "PLANNED_AGAINST_SUPPLIED_SNAPSHOT",
        }
    return HandlerOutcome(
        ExecutionStatus.EXECUTED,
        {
            "semantic_snapshot": snapshot,
            "snapshot_digest": canonical_digest(snapshot),
            "query_plan": query_plan,
        },
    )


def _p03(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(payload, {"action", "requirements", "target_profile", "rules", "rollback"})
    action = _action(payload, "plan-transformation")
    if action not in {
        "expand-requirements", "design-architecture", "plan-transformation", "plan-migration", "evaluate-gap"
    }:
        return _blocked("CAPABILITY_UNSUPPORTED", "P03 action requires a transformation adapter", action=action)
    requirements: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    for index, item in enumerate(_array(payload.get("requirements", []), "payload.requirements")):
        requirement = _object(item, f"payload.requirements[{index}]")
        if set(requirement) - {"id", "semantics", "support_state", "target"}:
            raise ValueError(f"payload.requirements[{index}] contains unsupported fields")
        identity = _identifier(requirement.get("id"), f"payload.requirements[{index}].id")
        state = _identifier(requirement.get("support_state", "unknown"), "requirement.support_state")
        if state not in {"supported", "unsupported", "unknown"}:
            raise ValueError("requirement.support_state must be supported, unsupported, or unknown")
        normalized = strict_json_copy(requirement, field=f"payload.requirements[{index}]")
        requirements.append(normalized)
        if state != "supported":
            gaps.append({"requirement_id": identity, "support_state": state})
    if gaps:
        return HandlerOutcome(
            ExecutionStatus.BLOCKED,
            {"semantic_gaps": gaps, "silent_drop_count": 0},
            ExecutionError("UNSUPPORTED_SEMANTICS", "unsupported or unknown semantics block generation"),
        )
    plan = {
        "action": action,
        "requirements": requirements,
        "target_profile": strict_json_copy(payload.get("target_profile", {}), field="payload.target_profile"),
        "rules": _string_list(payload.get("rules", []), "payload.rules"),
        "rollback": strict_json_copy(payload.get("rollback", {}), field="payload.rollback"),
        "artifact_state": "PLANNED_NOT_EMITTED",
        "silent_drop_count": 0,
    }
    return HandlerOutcome(ExecutionStatus.EXECUTED, {"transformation_plan": plan, "plan_digest": canonical_digest(plan)})


def _p04(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(payload, {"action", "nodes", "capacity", "roles", "evidence_refs"})
    action = _action(payload, "reconcile-tasks")
    if action not in {"reconcile-tasks", "dispatch-plan", "compose-agent", "assemble-proof"}:
        return _blocked("CAPABILITY_UNSUPPORTED", "P04 action requires an orchestration adapter", action=action)
    if action == "compose-agent":
        roles = _string_list(payload.get("roles", []), "payload.roles")
        if not roles:
            return _blocked("ROLE_UNAVAILABLE", "at least one allowed role is required")
        profile = {
            "roles": sorted(roles),
            "max_parallelism": request.policy.max_parallelism,
            "max_retries": request.policy.max_retries,
            "execution_state": "PROFILE_ONLY_NOT_STARTED",
        }
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {"agent_profile": profile, "profile_digest": canonical_digest(profile)},
        )
    if action == "assemble-proof":
        refs = _string_list(payload.get("evidence_refs", []), "payload.evidence_refs")
        invalid = [item for item in refs if not is_sha256_digest(item)]
        if not refs or invalid:
            return _blocked(
                "EVIDENCE_INCOMPLETE",
                "proof assembly requires lowercase sha256 evidence references",
                invalid=invalid,
            )
        bundle = {
            "evidence_refs": sorted(refs),
            "scope": request.envelope.as_dict(),
            "verification_state": "CONTENT_REFS_NOT_RESOLVED",
        }
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {"proof_bundle": bundle, "bundle_digest": canonical_digest(bundle)},
        )
    nodes, order = _topological_nodes(payload.get("nodes", []), max_nodes=request.policy.max_nodes)
    state = {item["id"]: item["state"] for item in nodes}
    dependencies = {item["id"]: item["depends_on"] for item in nodes}
    ready = [
        node_id for node_id in order
        if state[node_id] == "pending" and all(state[dep] == "succeeded" for dep in dependencies[node_id])
    ]
    exhausted = [
        item["id"] for item in nodes
        if item["state"] == "failed" and item["retries"] >= request.policy.max_retries
    ]
    capacity = _integer(payload.get("capacity", request.policy.max_parallelism), "payload.capacity", maximum=64)
    assignments = ready[: min(capacity, request.policy.max_parallelism)]
    if ready and capacity == 0:
        return HandlerOutcome(
            ExecutionStatus.BLOCKED,
            {"ready": ready, "assignments": [], "side_effect_state": "NOT_STARTED"},
            ExecutionError("NO_CAPACITY", "ready work exists but available capacity is zero"),
        )
    journal = [
        {"sequence": index + 1, "task_id": task_id, "decision": "READY_NOT_STARTED"}
        for index, task_id in enumerate(assignments)
    ]
    return HandlerOutcome(
        ExecutionStatus.EXECUTED,
        {
            "topological_order": order,
            "ready": ready,
            "assignments": assignments,
            "retry_exhausted": exhausted,
            "journal": journal,
            "journal_digest": canonical_digest(journal),
            "side_effect_state": "NOT_STARTED",
        },
    )


def _p05(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(payload, {"action", "claims", "changes", "risk", "failures", "budget_micros"})
    action = _action(payload, "evaluate-gate")
    if action not in {"evaluate-coverage", "plan-verification", "evaluate-gate", "plan-repair"}:
        return _blocked("CAPABILITY_UNSUPPORTED", "P05 action requires a verification adapter", action=action)
    if action == "plan-verification":
        changes = _string_list(payload.get("changes", []), "payload.changes")
        if not changes:
            return _blocked("COVERAGE_UNSATISFIABLE", "verification planning requires explicit changes")
        claim_inputs: list[dict[str, Any]] = []
        for index, item in enumerate(_array(payload.get("claims", []), "payload.claims")):
            claim = _object(item, f"payload.claims[{index}]")
            identity = _identifier(claim.get("id"), f"payload.claims[{index}].id")
            claim_inputs.append(
                {
                    "id": identity,
                    "state": claim.get("state", "NOT_RUN"),
                    "critical": claim.get("critical", False) is True,
                    "input_digest": canonical_digest(
                        strict_json_copy(claim, field=f"payload.claims[{index}]")
                    ),
                }
            )
        dag = [
            {
                "id": f"verify-{index + 1}",
                "change": change,
                "state": "NOT_RUN",
                "requires_independent_verifier": True,
            }
            for index, change in enumerate(sorted(changes))
        ]
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "verification_dag": dag,
                "claim_inputs": claim_inputs,
                "claim_set_digest": canonical_digest(claim_inputs),
                "external_execution_state": "NOT_RUN",
            },
        )
    if action == "plan-repair":
        failures = _array(payload.get("failures", []), "payload.failures")
        budget = _integer(payload.get("budget_micros", 0), "payload.budget_micros")
        if not failures:
            return _blocked("NO_PROGRESS", "repair planning requires at least one failure")
        if budget == 0 or budget > request.policy.max_cost_micros:
            return _blocked("BUDGET_EXHAUSTED", "repair budget is absent or exceeds policy")
        normalized_failures = [
            strict_json_copy(item, field=f"payload.failures[{index}]")
            for index, item in enumerate(failures)
        ]
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "repair_plan": {
                    "failure_count": len(normalized_failures),
                    "budget_micros": budget,
                    "attempt_limit": request.policy.max_retries,
                    "state": "PLANNED_NOT_APPLIED",
                }
            },
        )
    claims: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    allowed_states = {"PASSED", "FAILED", "BLOCKED", "NOT_RUN", "UNKNOWN", "INCONCLUSIVE"}
    for index, item in enumerate(_array(payload.get("claims", []), "payload.claims")):
        claim = _object(item, f"payload.claims[{index}]")
        if set(claim) - {
            "id", "state", "critical", "evidence_digest", "executor_id", "verifier_id",
            "tenant_id", "project_id", "correlation_id", "policy_revision", "source_revision",
        }:
            raise ValueError(f"payload.claims[{index}] contains unsupported fields")
        identity = _identifier(claim.get("id"), f"payload.claims[{index}].id")
        state = _identifier(claim.get("state", "NOT_RUN"), f"claim {identity}.state").upper()
        if state not in allowed_states:
            raise ValueError(f"claim {identity}.state is unsupported")
        critical = claim.get("critical", False) is True
        evidence_digest = claim.get("evidence_digest")
        executor_id = claim.get("executor_id")
        verifier_id = claim.get("verifier_id")
        independent = False
        if isinstance(executor_id, str) and isinstance(verifier_id, str):
            executor_id = _identifier(executor_id, f"claim {identity}.executor_id")
            verifier_id = _identifier(verifier_id, f"claim {identity}.verifier_id")
            independent = executor_id != verifier_id
        scope_matches = (
            claim.get("tenant_id") == request.envelope.tenant_id
            and claim.get("project_id") == request.envelope.project_id
            and claim.get("correlation_id") == request.envelope.correlation_id
            and claim.get("policy_revision") == request.envelope.policy_revision
            and claim.get("source_revision") == request.envelope.source_revision
        )
        normalized = {
            "id": identity,
            "state": state,
            "critical": critical,
            "evidence_digest": evidence_digest,
            "independent_roles_declared": independent,
            "scope_matches": scope_matches,
        }
        claims.append(normalized)
        if state != "PASSED" or not is_sha256_digest(evidence_digest) or not independent or not scope_matches:
            blockers.append(normalized)
    decision = "LOCAL_STRUCTURE_PASSED" if claims and not blockers else "BLOCKED"
    output = {
        "decision": decision,
        "claims": claims,
        "blockers": blockers,
        "critical_blocker_count": sum(1 for item in blockers if item["critical"]),
        "critical_failures_compensable": False,
        "external_gate_state": "EXTERNAL_GATE_NOT_RUN",
        "certified": False,
    }
    if blockers or not claims:
        return HandlerOutcome(
            ExecutionStatus.BLOCKED,
            output,
            ExecutionError(
                "EVIDENCE_INCOMPLETE",
                "missing, failed, stale, mismatched-scope, or non-independent evidence fails closed",
            ),
        )
    return HandlerOutcome(ExecutionStatus.EXECUTED, output)


def _p06(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(payload, {"action", "candidates", "data_classes", "task", "usage"})
    action = _action(payload, "route-plan")
    if action not in {"classify-task", "route-plan", "forecast-cost"}:
        return _blocked("CAPABILITY_UNSUPPORTED", "P06 action requires a model/provider adapter", action=action)
    if action == "classify-task":
        task = _object(payload.get("task"), "payload.task")
        if set(task) - {"kind", "modalities", "context_tokens", "risk"}:
            raise ValueError("payload.task contains unsupported fields")
        profile = {
            "kind": _identifier(task.get("kind"), "payload.task.kind"),
            "modalities": _string_list(task.get("modalities", []), "payload.task.modalities"),
            "context_tokens": _integer(
                task.get("context_tokens", 0), "payload.task.context_tokens", maximum=10**9
            ),
            "risk": _identifier(task.get("risk", "unknown"), "payload.task.risk"),
            "classification_state": "DETERMINISTIC_LOCAL_PROFILE",
        }
        return HandlerOutcome(ExecutionStatus.EXECUTED, {"task_profile": profile})
    if action == "forecast-cost":
        usage = _object(payload.get("usage"), "payload.usage")
        if set(usage) - {"input_tokens", "output_tokens", "runs"}:
            raise ValueError("payload.usage contains unsupported fields")
        input_tokens = _integer(usage.get("input_tokens", 0), "payload.usage.input_tokens", maximum=10**12)
        output_tokens = _integer(usage.get("output_tokens", 0), "payload.usage.output_tokens", maximum=10**12)
        runs = _integer(usage.get("runs", 1), "payload.usage.runs", minimum=1, maximum=10**6)
        estimates: list[dict[str, Any]] = []
        for index, item in enumerate(_array(payload.get("candidates", []), "payload.candidates")):
            candidate = _object(item, f"payload.candidates[{index}]")
            if set(candidate) - {
                "provider", "model", "available", "cost_micros", "quality_basis_points", "data_classes"
            }:
                raise ValueError(f"payload.candidates[{index}] contains unsupported fields")
            provider = _identifier(candidate.get("provider"), f"candidate {index}.provider")
            model = _identifier(candidate.get("model"), f"candidate {index}.model")
            per_run = _integer(candidate.get("cost_micros", 0), f"candidate {index}.cost_micros")
            estimates.append(
                {
                    "provider": provider,
                    "model": model,
                    "caller_cost_micros_per_run": per_run,
                    "caller_cost_micros_total": per_run * runs,
                    "price_evidence_state": "CALLER_DECLARED_UNVERIFIED",
                }
            )
        estimates.sort(key=lambda item: (item["caller_cost_micros_total"], item["provider"], item["model"]))
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {
                "usage_envelope": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "runs": runs,
                    "provider_price_evidence_state": "NOT_RUN",
                    "currency_cost": None,
                },
                "candidate_estimates": estimates,
                "candidate_set_digest": canonical_digest(estimates),
            },
        )
    data_classes = set(_string_list(payload.get("data_classes", []), "payload.data_classes"))
    denied_classes = sorted(data_classes - request.policy.allowed_data_classes)
    if denied_classes:
        return _blocked("POLICY_DENIED", "request contains disallowed data classes", data_classes=denied_classes)
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for index, item in enumerate(_array(payload.get("candidates", []), "payload.candidates")):
        candidate = _object(item, f"payload.candidates[{index}]")
        if set(candidate) - {"provider", "model", "available", "cost_micros", "quality_basis_points", "data_classes"}:
            raise ValueError(f"payload.candidates[{index}] contains unsupported fields")
        provider = _identifier(candidate.get("provider"), f"candidate {index}.provider")
        model = _identifier(candidate.get("model"), f"candidate {index}.model")
        cost = _integer(candidate.get("cost_micros", 0), f"candidate {index}.cost_micros")
        quality = _integer(
            candidate.get("quality_basis_points", 0),
            f"candidate {index}.quality_basis_points",
            maximum=10_000,
        )
        reasons: list[str] = []
        if provider not in request.policy.allowed_providers:
            reasons.append("PROVIDER_DENIED")
        if candidate.get("available") is not True:
            reasons.append("AVAILABILITY_UNCONFIRMED")
        if cost > request.policy.max_cost_micros:
            reasons.append("COST_EXCEEDED")
        if quality < request.policy.min_quality_basis_points:
            reasons.append("QUALITY_BELOW_MINIMUM")
        candidate_classes = set(_string_list(candidate.get("data_classes", []), "candidate.data_classes"))
        if not data_classes.issubset(candidate_classes):
            reasons.append("DATA_CLASS_UNSUPPORTED")
        if reasons:
            rejected.append({"provider": provider, "model": model, "reasons": ",".join(reasons)})
        else:
            eligible.append(
                {
                    "provider": provider,
                    "model": model,
                    "cost_micros": cost,
                    "quality_basis_points": quality,
                    "availability_state": "CALLER_DECLARED_UNVERIFIED",
                }
            )
    eligible.sort(key=lambda item: (-item["quality_basis_points"], item["cost_micros"], item["provider"], item["model"]))
    if action == "route-plan" and not eligible:
        return HandlerOutcome(
            ExecutionStatus.BLOCKED,
            {"eligible": [], "rejected": rejected},
            ExecutionError("NO_ELIGIBLE_ROUTE", "no route satisfies privacy, availability, cost, and quality policy"),
        )
    return HandlerOutcome(
        ExecutionStatus.EXECUTED,
        {
            "selected": eligible[0] if eligible else None,
            "fallbacks": eligible[1:],
            "rejected": rejected,
            "execution_state": "TENTATIVE_PLAN_NOT_INVOKED",
            "availability_evidence_state": "NOT_RUN",
        },
    )


def _p07(
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    del package, registry
    payload = request.payload
    _reject_unknown(payload, {"action", "entries", "failure_signature", "candidate", "drift", "value_score"})
    action = _action(payload, "query-knowledge")
    if action not in {"query-knowledge", "rank-repairs", "evaluate-promotion", "plan-learning"}:
        return _blocked("CAPABILITY_UNSUPPORTED", "P07 action requires a learning adapter", action=action)
    visible: list[dict[str, Any]] = []
    rejected: list[str] = []
    for index, item in enumerate(_array(payload.get("entries", []), "payload.entries")):
        entry = _object(item, f"payload.entries[{index}]")
        if set(entry) - {"id", "tenant_id", "project_id", "visibility", "score", "evidence_digest", "state"}:
            raise ValueError(f"payload.entries[{index}] contains unsupported fields")
        identity = _identifier(entry.get("id"), f"payload.entries[{index}].id")
        visibility = _identifier(entry.get("visibility", "tenant"), f"entry {identity}.visibility")
        tenant_id = entry.get("tenant_id")
        project_id = entry.get("project_id")
        same_scope = tenant_id == request.envelope.tenant_id and project_id in {
            None, request.envelope.project_id
        }
        global_allowed = visibility == "global" and request.policy.allow_global_knowledge
        if not (same_scope or global_allowed):
            rejected.append(identity)
            continue
        score = _integer(entry.get("score", 0), f"entry {identity}.score", maximum=10_000)
        evidence_digest = entry.get("evidence_digest")
        declared_state = entry.get("state", "candidate")
        if declared_state != "trusted-verified" or not is_sha256_digest(evidence_digest):
            rejected.append(identity)
            continue
        visible.append(
            {
                "id": identity,
                "visibility": visibility,
                "score": score,
                "evidence_digest": evidence_digest,
                "state": declared_state,
                "trust_state": "CALLER_DECLARED_NOT_LOCALLY_VERIFIED",
            }
        )
    visible.sort(key=lambda item: (-item["score"], item["id"]))
    if action == "plan-learning":
        value_score = _integer(payload.get("value_score", 0), "payload.value_score", maximum=10_000)
        candidate = strict_json_copy(
            _object(payload.get("candidate"), "payload.candidate"), field="payload.candidate"
        )
        entries_digest = canonical_digest(
            strict_json_copy(payload.get("entries", []), field="payload.entries")
        )
        item = {
            "value_score": value_score,
            "candidate": candidate,
            "eligible_knowledge_ids": [entry["id"] for entry in visible],
            "rejected_knowledge_ids": sorted(rejected),
            "entries_digest": entries_digest,
            "tenant_id": request.envelope.tenant_id,
            "project_id": request.envelope.project_id,
            "queue_mutation_state": "NOT_APPLIED",
        }
        return HandlerOutcome(
            ExecutionStatus.EXECUTED,
            {"learning_item_plan": item, "item_digest": canonical_digest(item)},
        )
    if action == "evaluate-promotion":
        return HandlerOutcome(
            ExecutionStatus.BLOCKED,
            {
                "promotion_decision": "BLOCKED",
                "promoted": False,
                "visible_candidates": visible,
                "scope_rejections": rejected,
                "reason": "local runtime cannot verify signatures, trust roots, or publish authorization",
            },
            ExecutionError(
                "INDEPENDENT_EVIDENCE_REQUIRED",
                "promotion requires an authorized external verifier and content-byte resolution",
            ),
        )
    if action in {"query-knowledge", "rank-repairs"} and not visible:
        return HandlerOutcome(
            ExecutionStatus.BLOCKED,
            {"matches": [], "scope_rejections": rejected},
            ExecutionError("NO_TRUSTED_RULE", "no tenant-safe knowledge entry is eligible"),
        )
    query_output: dict[str, Any] = {
        "matches": visible,
        "scope_rejections": rejected,
        "mutation_state": "NOT_APPLIED",
    }
    if action == "rank-repairs":
        signature = _identifier(payload.get("failure_signature"), "payload.failure_signature")
        query_output["failure_signature"] = signature
        query_output["repair_query_digest"] = canonical_digest(
            {"failure_signature": signature, "match_ids": [item["id"] for item in visible]}
        )
    return HandlerOutcome(
        ExecutionStatus.EXECUTED,
        query_output,
    )


HANDLERS = {
    "workflow": _p00,
    "runtime-plan": _p01,
    "repository-intelligence": _p02,
    "transformation-plan": _p03,
    "orchestration": _p04,
    "evidence-gate": _p05,
    "model-route": _p06,
    "knowledge": _p07,
}


def handle(
    operation: str,
    request: ExecutionRequest,
    package: PackageDefinition,
    registry: SkillRegistry,
    context: HandlerContext,
) -> HandlerOutcome:
    handler = HANDLERS.get(operation)
    if handler is None:
        return _blocked("CAPABILITY_UNSUPPORTED", "operation has no local handler", operation=operation)
    try:
        outcome = handler(request, package, registry, context)
        output = {
            "handler_contract": {
                "skill_name": context.skill_name,
                "capability_identity": context.capability_identity,
                "capability_action": context.capability_action,
                "required_inputs": list(context.required_inputs),
            },
            **outcome.output,
        }
        return HandlerOutcome(outcome.status, output, outcome.error)
    except (TypeError, ValueError) as exc:
        return _blocked("PAYLOAD_INVALID", str(exc))
