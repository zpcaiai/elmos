"""Exact allowlisted handlers for the 85 commercial expansion Skills.

Every registry entry points at a distinct wrapper function.  Wrappers bind one
source Skill identity to a narrow kernel helper; there is intentionally no
``skill_id``-interpreting fallback dispatcher and no alias resolution.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, cast

from ..canonical import digest_object, to_jsonable
from ..contracts import (
    Evidence,
    EvidenceStatus,
    HandlerRequest,
    HandlerResult,
    Outcome,
    SkillInputContract,
)
from ..errors import ContractError
from ._local_algorithms import (
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

ExactHandler = Callable[[HandlerRequest], HandlerResult]
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_CATEGORY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_PRODUCER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/+\-]{0,199}$")
_CANDIDATE_EVIDENCE_STATUSES = frozenset(status.value for status in EvidenceStatus)


def _plain(value: Any) -> Any:
    return to_jsonable(value)


def _missing(request: HandlerRequest, required: Sequence[str]) -> tuple[str, ...]:
    return tuple(f"missing:{name}" for name in required if name not in request.inputs)


def _enforce_input_contract(request: HandlerRequest, expected_skill_id: str) -> None:
    request.assert_runtime_execution(expected_skill_id)
    contract = EXACT_SKILL_INPUT_CONTRACTS.get(expected_skill_id)
    if contract is None:
        raise ValueError(f"missing exact input contract for {expected_skill_id}")
    contract.validate(request.inputs)


def _analysis_evidence(
    request: HandlerRequest, expected_skill_id: str, output: Mapping[str, Any]
) -> Evidence:
    content_digest = digest_object(output, domain="exact-handler-output")
    suffix = content_digest.removeprefix("sha256:")[:16]
    return Evidence(
        evidence_id=f"ev-{suffix}",
        scope=request.scope,
        invocation_id=request.invocation.invocation_id,
        category="LOCAL_HANDLER_ANALYSIS",
        subject_digest=request.invocation.request_digest,
        content_digest=content_digest,
        status=EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED,
        producer_id=f"handler:{expected_skill_id}",
        verifier_id=None,
        authorization_id=request.lease.policy_decision_id,
        produced_at=request.invocation.issued_at,
        metadata={"certification": "NOT_CERTIFIED", "external_evidence": "NOT_RUN"},
    )


def _result(
    request: HandlerRequest,
    expected_skill_id: str,
    status: Outcome,
    output: Mapping[str, Any],
    *,
    unresolved: Sequence[str] = (),
    metrics: Mapping[str, int | float] | None = None,
) -> HandlerResult:
    if request.skill_id != expected_skill_id:
        return HandlerResult(
            skill_id=expected_skill_id,
            status=Outcome.BLOCKED,
            output={
                "schema": "elmos.exact-handler-result.v1",
                "executed": False,
                "expected_skill_id": expected_skill_id,
                "observed_skill_id": request.skill_id,
            },
            unresolved=("skill_binding_mismatch",),
            side_effects=(),
            metrics={},
        )
    normalized = {
        "schema": "elmos.exact-handler-result.v1",
        "skill_id": expected_skill_id,
        "operation": request.operation,
        "scope_digest": request.scope.digest,
        **_plain(output),
    }
    evidence = (
        (_analysis_evidence(request, expected_skill_id, normalized),)
        if status is Outcome.LOCAL_EXECUTED_SELF_ATTESTED
        else ()
    )
    return HandlerResult(
        skill_id=expected_skill_id,
        status=status,
        output=normalized,
        artifacts=(),
        evidence=evidence,
        unresolved=tuple(unresolved),
        side_effects=(),
        metrics=dict(metrics or {}),
    )


def _blocked(
    request: HandlerRequest, expected_skill_id: str, unresolved: Sequence[str]
) -> HandlerResult:
    return _result(
        request,
        expected_skill_id,
        Outcome.BLOCKED,
        {"executed": False, "reason": "INPUT_CONTRACT_UNSATISFIED"},
        unresolved=unresolved,
    )


def _not_run(
    request: HandlerRequest,
    expected_skill_id: str,
    output: Mapping[str, Any],
    unresolved: Sequence[str],
) -> HandlerResult:
    return _result(
        request,
        expected_skill_id,
        Outcome.NOT_RUN,
        {"executed": False, **output},
        unresolved=unresolved,
    )


def _external(
    request: HandlerRequest,
    expected_skill_id: str,
    output: Mapping[str, Any],
    unresolved: Sequence[str],
) -> HandlerResult:
    return _result(
        request,
        expected_skill_id,
        Outcome.EXTERNAL_ADAPTER_REQUIRED,
        {"executed": False, **output},
        unresolved=unresolved,
    )


def _bounded_partial_result(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    kernel: str,
    algorithm: str,
    algorithm_result: Mapping[str, object],
    unresolved: Sequence[str],
    limitations: Sequence[str],
    metadata: Mapping[str, object] | None = None,
) -> HandlerResult:
    """Report a real pure subcapability without promoting the whole Skill."""

    return _not_run(
        request,
        expected_skill_id,
        {
            "kernel": kernel,
            "bounded_subcapability": algorithm,
            "bounded_subcapability_executed": True,
            "algorithm_result": algorithm_result,
            "objective_coverage": "PARTIAL",
            "capability_scope": "PURE_DETERMINISTIC_CALLER_INPUT_ALGORITHM",
            "limitations": list(limitations),
            **dict(metadata or {}),
        },
        unresolved,
    )


def _strict_graph(value: object) -> tuple[Sequence[object], Sequence[object]]:
    if not isinstance(value, Mapping) or set(value) != {"nodes", "edges"}:
        raise ContractError(
            "graph must contain exactly nodes and edges",
            code="INVALID_LOCAL_SCHEMA",
        )
    nodes = value["nodes"]
    edges = value["edges"]
    if not isinstance(nodes, (tuple, list)) or not isinstance(edges, (tuple, list)):
        raise ContractError("graph nodes and edges must be arrays", code="INVALID_LOCAL_INPUT")
    return nodes, edges


def _progressive_disclosure_result(request: HandlerRequest) -> HandlerResult:
    expected_skill_id = "progressive-skill-disclosure"
    _enforce_input_contract(request, expected_skill_id)
    required = ("skill_metadata", "query_terms", "context_token_budget", "candidate_permissions")
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    metadata = request.inputs["skill_metadata"]
    if not isinstance(metadata, (tuple, list)):
        raise ContractError("skill_metadata must be an array", code="INVALID_LOCAL_INPUT")
    input_keys = {
        "id",
        "summary",
        "tags",
        "token_budget",
        "tenant_id",
        "project_id",
        "environment",
        "permissions",
    }
    algorithm_metadata: list[dict[str, object]] = []
    for index, item in enumerate(metadata):
        if not isinstance(item, Mapping) or set(item) != input_keys:
            raise ContractError(
                f"skill_metadata[{index}] does not match the exact disclosure schema",
                code="INVALID_LOCAL_SCHEMA",
            )
        algorithm_metadata.append(
            {
                **dict(item),
                "tokens": item["token_budget"],
            }
        )
        del algorithm_metadata[-1]["token_budget"]
    trusted_context = {
        "tenant_id": request.scope.tenant_id,
        "project_id": request.scope.project_id,
        "environment": request.scope.environment_id,
        "permissions": request.inputs["candidate_permissions"],
    }
    result = progressive_disclosure(
        algorithm_metadata,
        trusted_context,
        request.inputs["query_terms"],
        request.inputs["context_token_budget"],
    )
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K1-skill-runtime",
        algorithm="progressive_disclosure",
        algorithm_result=result,
        unresolved=("trusted_skill_catalog_and_permission_source_required",),
        limitations=(
            "skill_metadata_is_caller_supplied",
            "candidate_permissions_are_not_execution_authority",
            "no_skill_loaded_or_executed",
        ),
    )


def _version_provenance_result(request: HandlerRequest) -> HandlerResult:
    expected_skill_id = "skill-version-provenance"
    _enforce_input_contract(request, expected_skill_id)
    required = ("version_bindings", "source_digests")
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    source_digests = request.inputs["source_digests"]
    version_bindings = request.inputs["version_bindings"]
    if not isinstance(source_digests, Mapping) or not isinstance(version_bindings, Mapping):
        raise ContractError(
            "source_digests and version_bindings must be objects",
            code="INVALID_LOCAL_INPUT",
        )
    supplied_dependencies = request.inputs.get("dependencies")
    dependencies_supplied = supplied_dependencies is not None
    if supplied_dependencies is None:
        dependencies: Mapping[str, object] = {name: () for name in source_digests}
    elif isinstance(supplied_dependencies, Mapping):
        dependencies = cast(Mapping[str, object], supplied_dependencies)
    else:
        raise ContractError("dependencies must be an object", code="INVALID_LOCAL_INPUT")
    result = validate_provenance_bindings(
        cast(Mapping[str, object], source_digests),
        dependencies,
    )
    unresolved = ["trusted_provenance_source_and_signature_verifier_required"]
    if not dependencies_supplied:
        unresolved.append("dependency_graph_not_supplied_for_full_provenance")
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K1-skill-runtime",
        algorithm="validate_provenance_bindings",
        algorithm_result=result,
        unresolved=unresolved,
        limitations=(
            "source_digests_are_caller_supplied",
            "version_metadata_not_independently_verified",
            "no_signature_or_revocation_check",
        ),
        metadata={
            "dependencies_supplied": dependencies_supplied,
            "version_bindings_digest": digest_object(
                version_bindings,
                domain="version-binding-metadata",
            ),
        },
    )


def _constrained_router_result(request: HandlerRequest) -> HandlerResult:
    expected_skill_id = "model-tool-skill-router"
    _enforce_input_contract(request, expected_skill_id)
    required = ("candidates", "constraints")
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    result = route_constrained_candidate(
        request.inputs["candidates"],
        request.inputs["constraints"],
    )
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K1-skill-runtime",
        algorithm="route_constrained_candidate",
        algorithm_result=result,
        unresolved=("trusted_model_tool_inventory_and_execution_adapter_required",),
        limitations=("candidates_are_caller_supplied", "selected_candidate_not_invoked"),
    )


def _repository_algorithm_result(request: HandlerRequest, expected_skill_id: str) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    snapshot = request.inputs.get("repository_snapshot")
    graph = request.inputs.get("graph")
    if snapshot is None or graph is None:
        return _blocked(request, expected_skill_id, _missing(request, ("repository_snapshot", "graph")))
    nodes, edges = _strict_graph(graph)
    algorithm: str
    result: Mapping[str, object]
    if expected_skill_id == "cross-repository-impact-analysis":
        result = typed_graph_closure(nodes, edges, request.inputs["changed_paths"])
        algorithm = "typed_graph_closure"
    elif expected_skill_id == "repository-slicing-context-pack":
        result = dependency_closed_slice(
            nodes,
            edges,
            request.inputs["focus_nodes"],
            request.inputs["node_costs"],
            request.inputs["token_budget"],
        )
        algorithm = "dependency_closed_slice"
    elif expected_skill_id == "affected-test-selection":
        result = select_affected_tests(
            nodes,
            edges,
            request.inputs["changed_paths"],
            request.inputs["test_coverage"],
            request.inputs["critical_nodes"],
        )
        algorithm = "select_affected_tests"
    elif expected_skill_id == "change-risk-classifier":
        closure = typed_graph_closure(nodes, edges, request.inputs["changed_paths"])
        affected = cast(Sequence[object], closure["affected_nodes"])
        risk = classify_monotonic_risk(
            affected,
            request.inputs["critical_nodes"],
            request.inputs["runtime_hot_paths"],
            request.inputs["security_boundaries"],
            request.inputs["historical_failures"],
            request.inputs["proof_coverage"],
        )
        result = {"affected_closure": closure, "risk": risk}
        algorithm = "typed_graph_closure+classify_monotonic_risk"
    else:
        raise ContractError("unsupported repository algorithm binding", code="REGISTRY_INVALID")
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K2-repository-intelligence",
        algorithm=algorithm,
        algorithm_result=result,
        unresolved=("trusted_repository_ingestion_semantic_index_and_independent_evidence_required",),
        limitations=(
            "repository_snapshot_and_graph_are_caller_supplied",
            "no_filesystem_or_scm_read",
            "no_semantic_index_built",
        ),
        metadata={"repository_snapshot_digest": digest_object(snapshot, domain="repository-snapshot")},
    )


def _explainability_ledger_result(request: HandlerRequest) -> HandlerResult:
    expected_skill_id = "transformation-explainability-ledger"
    _enforce_input_contract(request, expected_skill_id)
    if "edits" not in request.inputs:
        return _blocked(request, expected_skill_id, ("missing:edits",))
    result = build_explainability_ledger(request.inputs["edits"])
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K3-transformation",
        algorithm="build_explainability_ledger",
        algorithm_result=result,
        unresolved=("trusted_transformation_runner_and_independent_validation_required",),
        limitations=("edits_are_caller_supplied", "no_edit_applied", "validation_evidence_not_verified"),
    )


def _database_algorithm_result(request: HandlerRequest, expected_skill_id: str) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    metadata: dict[str, object] = {
        "native_engine_execution": "NOT_RUN",
        "production_writes": False,
    }
    if expected_skill_id == "data-lineage-impact-analysis":
        lineage_result = lineage_impact_closure(
            request.inputs["datasets"],
            request.inputs["lineage_edges"],
            request.inputs["changed_entities"],
        )
        entity_kinds_value = lineage_result.pop("entity_kinds")
        if not isinstance(entity_kinds_value, Mapping):
            raise ContractError("lineage algorithm returned invalid kind bindings", code="REGISTRY_INVALID")
        entity_kinds = cast(Mapping[str, object], entity_kinds_value)
        result = {
            **lineage_result,
            "entity_kind_binding_digest": digest_object(
                entity_kinds,
                domain="lineage-entity-kind-bindings",
            ),
            "entity_kind_binding_count": len(entity_kinds),
        }
        algorithm = "lineage_impact_closure"
    elif expected_skill_id == "data-migration-reconciliation":
        decimal_fields = request.inputs.get("decimal_fields", ())
        result = reconcile_keyed_rows(
            request.inputs["source_rows"],
            request.inputs["target_rows"],
            request.inputs["key_fields"],
            decimal_fields,
        )
        algorithm = "reconcile_keyed_rows"
        metadata["decimal_fields_supplied"] = "decimal_fields" in request.inputs
    else:
        raise ContractError("unsupported database algorithm binding", code="REGISTRY_INVALID")
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K7-database-data",
        algorithm=algorithm,
        algorithm_result=result,
        unresolved=("native_source_target_database_and_independent_evidence_required",),
        limitations=(
            "database_rows_or_lineage_are_caller_supplied",
            "no_source_or_target_database_read",
            "no_independent_reconciliation_or_lineage_verification",
        ),
        metadata=metadata,
    )


def _observability_algorithm_result(request: HandlerRequest, expected_skill_id: str) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    if expected_skill_id == "agent-evidence-evaluation":
        result = evaluate_rubric_scorecard(
            request.inputs["observations"],
            request.inputs["rubric"],
        )
        algorithm = "evaluate_rubric_scorecard"
    elif expected_skill_id == "incident-replay-root-cause":
        result = incident_causal_divergence(
            request.inputs["expected_events"],
            request.inputs["observed_events"],
        )
        algorithm = "incident_causal_divergence"
    elif expected_skill_id == "cost-latency-quality-optimizer":
        result = optimize_cost_latency_quality(
            request.inputs["candidates"],
            request.inputs["constraints"],
        )
        algorithm = "optimize_cost_latency_quality"
    else:
        raise ContractError("unsupported observability algorithm binding", code="REGISTRY_INVALID")
    return _bounded_partial_result(
        request,
        expected_skill_id,
        kernel="K8-observability-evolution",
        algorithm=algorithm,
        algorithm_result=result,
        unresolved=("trusted_telemetry_catalog_and_independent_evidence_required",),
        limitations=(
            "observations_are_caller_supplied",
            "no_provider_or_catalog_effect",
            "no_independent_evidence_verification",
        ),
    )


def _k1_runtime_plan(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    plan_kind: str,
    required: Sequence[str],
    adapter_required: bool = False,
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    selected = {name: _plain(request.inputs[name]) for name in required}
    plan = {
        "kernel": "K1-skill-runtime",
        "plan_kind": plan_kind,
        "deterministic_plan_digest": digest_object(
            {"kind": plan_kind, "inputs": selected}, domain="k1-runtime-plan"
        ),
        "binding_digests": {
            f"{name}_digest": digest_object(value, domain=f"k1-runtime-binding:{name}")
            for name, value in selected.items()
        },
        "binding_count": len(selected),
        "approval_state": "REQUIRED" if "approval" in plan_kind else "NOT_APPLICABLE",
        "checkpoint_policy": "CONTENT_ADDRESSED",
        "execution_performed": False,
    }
    if adapter_required:
        return _external(
            request,
            expected_skill_id,
            plan,
            ("trusted_sandbox_or_workflow_adapter_required",),
        )
    return _not_run(
        request,
        expected_skill_id,
        {
            **plan,
            "capability_scope": "CALLER_INPUT_PLAN_CANDIDATE_ONLY",
            "limitations": ["no_skill_execution", "no_host_registry_authority"],
        },
        ("trusted_skill_runtime_adapter_required",),
    )


def _graph_parts(request: HandlerRequest) -> tuple[list[Any], list[Mapping[str, Any]]]:
    graph = request.inputs.get("graph", {})
    if not isinstance(graph, Mapping):
        return [], []
    nodes = list(graph.get("nodes", ()))
    edges = [edge for edge in graph.get("edges", ()) if isinstance(edge, Mapping)]
    return nodes, edges


def _blast_radius(changed: Iterable[str], edges: Sequence[Mapping[str, Any]]) -> list[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str) and isinstance(target, str):
            adjacency.setdefault(source, set()).add(target)
    seen = set(changed)
    queue = deque(sorted(seen))
    while queue and len(seen) <= 10_000:
        node = queue.popleft()
        for target in sorted(adjacency.get(node, ())):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return sorted(seen)


def _k2_repository_analysis(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    analysis_kind: str,
    required: Sequence[str],
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    snapshot = request.inputs.get("repository_snapshot", {})
    if not isinstance(snapshot, Mapping):
        return _blocked(request, expected_skill_id, ("repository_snapshot_must_be_object",))
    nodes, edges = _graph_parts(request)
    changed = [item for item in request.inputs.get("changed_paths", ()) if isinstance(item, str)]
    affected = _blast_radius(changed, edges)
    coverage = request.inputs.get("test_coverage", {})
    selected_tests: set[str] = set()
    if isinstance(coverage, Mapping):
        for path in affected:
            tests = coverage.get(path, ())
            if isinstance(tests, (tuple, list)):
                selected_tests.update(item for item in tests if isinstance(item, str))
    critical_tokens = ("auth", "security", "payment", "billing", "database", "secret")
    critical_matches = sorted(
        path for path in affected if any(token in path.lower() for token in critical_tokens)
    )
    output = {
        "kernel": "K2-repository-intelligence",
        "analysis_kind": analysis_kind,
        "input_boundary": "CALLER_SUPPLIED_SNAPSHOT_ONLY",
        "repository_snapshot_digest": digest_object(snapshot, domain="repository-snapshot"),
        "graph_digest": digest_object(
            {"nodes": nodes, "edges": edges}, domain="repository-graph"
        ),
        "file_count": len(snapshot.get("files", ())),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "changed_paths_digest": digest_object(sorted(changed), domain="repository-changed-paths"),
        "changed_path_count": len(changed),
        "affected_nodes_digest": digest_object(affected, domain="repository-affected-nodes"),
        "affected_node_count": len(affected),
        "selected_tests_digest": digest_object(sorted(selected_tests), domain="repository-selected-tests"),
        "selected_test_count": len(selected_tests),
        "risk": {
            "level": "HIGH" if critical_matches else ("MEDIUM" if len(affected) > 10 else "LOW"),
            "critical_matches_digest": digest_object(
                critical_matches,
                domain="repository-critical-matches",
            ),
            "critical_match_count": len(critical_matches),
            "external_history_considered": False,
        },
        "filesystem_read": False,
    }
    return _not_run(
        request,
        expected_skill_id,
        {
            **output,
            "capability_scope": "CALLER_SUPPLIED_GRAPH_ANALYSIS_ONLY",
            "limitations": ["repository_not_ingested", "semantic_index_not_built"],
        },
        ("trusted_repository_ingestion_and_semantic_adapter_required",),
    )


def _k3_transformation_plan(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    transformation_kind: str,
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    required = ("source_snapshot", "target_profile", "change_intent")
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    edits = request.inputs.get("proposed_edits", ())
    if not isinstance(edits, (tuple, list)):
        return _blocked(request, expected_skill_id, ("proposed_edits_must_be_array",))
    ledger: list[dict[str, Any]] = []
    rollback: list[dict[str, str]] = []
    for index, edit in enumerate(edits):
        if not isinstance(edit, Mapping) or not isinstance(edit.get("path"), str):
            return _blocked(request, expected_skill_id, (f"invalid_edit:{index}",))
        before = edit.get("before", "")
        after = edit.get("after", "")
        before_digest = digest_object(before, domain="edit-before")
        after_digest = digest_object(after, domain="edit-after")
        path_digest = digest_object(edit["path"], domain="edit-path")
        rule_digest = digest_object(
            edit.get("rule_id", transformation_kind),
            domain="edit-rule",
        )
        adapter_digest = digest_object(edit.get("adapter_id"), domain="edit-adapter")
        ledger.append(
            {
                "sequence": index,
                "path_digest": path_digest,
                "before_digest": before_digest,
                "after_digest": after_digest,
                "rule_digest": rule_digest,
                "adapter_digest": adapter_digest,
            }
        )
        rollback.append(
            {
                "path_digest": path_digest,
                "restore_digest": before_digest,
                "replace_digest": after_digest,
            }
        )
    output = {
        "kernel": "K3-transformation",
        "transformation_kind": transformation_kind,
        "transformation_plan": {
            "source_snapshot_digest": digest_object(
                request.inputs["source_snapshot"], domain="transformation-source"
            ),
            "target_profile_digest": digest_object(
                request.inputs["target_profile"], domain="transformation-target-profile"
            ),
            "change_intent_digest": digest_object(
                request.inputs["change_intent"], domain="transformation-change-intent"
            ),
            "edit_ledger": ledger,
            "rollback_map": rollback,
        },
        "writes_performed": False,
        "adapter_execution": "NOT_RUN",
    }
    if bool(request.inputs.get("apply_requested", False)):
        return _external(
            request,
            expected_skill_id,
            output,
            ("typed_transformation_adapter_required_for_writes",),
        )
    return _not_run(
        request,
        expected_skill_id,
        {
            **output,
            "capability_scope": "DIGEST_BOUND_TRANSFORMATION_CANDIDATE_ONLY",
            "limitations": ["no_source_parse", "no_edits_applied", "no_target_build"],
        },
        ("typed_transformation_adapter_and_verification_required",),
    )


def _k4_execution_contract(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    execution_kind: str,
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    required = ("command", "input_digests", "quotas")
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    command = request.inputs["command"]
    inputs = request.inputs["input_digests"]
    quotas = request.inputs["quotas"]
    if not isinstance(command, (tuple, list)) or not all(isinstance(v, str) for v in command):
        return _blocked(request, expected_skill_id, ("command_must_be_string_array",))
    if not isinstance(inputs, Mapping) or not isinstance(quotas, Mapping):
        return _blocked(request, expected_skill_id, ("input_digests_and_quotas_must_be_objects",))
    if any(not isinstance(name, str) or not _DIGEST_RE.fullmatch(str(value)) for name, value in inputs.items()):
        return _blocked(request, expected_skill_id, ("input_digests_must_be_exact_sha256_bindings",))
    contract_material = {
        "execution_kind": execution_kind,
        "command": list(command),
        "input_digests": dict(inputs),
        "toolchain_lock": _plain(request.inputs.get("toolchain_lock", {})),
        "quotas": dict(quotas),
    }
    output = {
        "kernel": "K4-build-execution",
        "execution_contract": {
            "content_key": digest_object(contract_material, domain="execution-action"),
            "execution_kind": execution_kind,
            "command_digest": digest_object(list(command), domain="execution-command"),
            "argument_count": max(0, len(command) - 1),
            "arguments_disclosed": False,
            "input_binding_digest": digest_object(
                dict(inputs),
                domain="execution-input-bindings",
            ),
            "input_binding_count": len(inputs),
            "toolchain_lock_digest": digest_object(
                request.inputs.get("toolchain_lock", {}), domain="execution-toolchain-lock"
            ),
            "quota_digest": digest_object(quotas, domain="execution-quotas"),
            "quota_count": len(quotas),
            "required_sandbox_policy": {
                "rootless": True,
                "read_only_source": True,
                "network": "DEFAULT_DENY",
                "secrets": "BROKERED_REFERENCES_ONLY",
                "outputs": "EPHEMERAL_CONTENT_ADDRESSED",
            },
            "required_receipts": [
                "adapter_identity",
                "sandbox_policy",
                "input_digest_binding",
                "raw_exit_stdout_stderr",
            ],
        },
        "subprocess_started": False,
        "execution_evidence": "NOT_RUN",
    }
    return _external(
        request,
        expected_skill_id,
        output,
        (f"external_{execution_kind}_adapter_required",),
    )


def _validated_evidence_records(
    records: Any,
) -> tuple[list[Mapping[str, Any]], tuple[str, ...]]:
    if not isinstance(records, (tuple, list)) or not records:
        return [], ("raw_evidence_required",)
    valid: list[Mapping[str, Any]] = []
    problems: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            problems.append(f"evidence_not_object:{index}")
            continue
        required = {"category", "raw", "content_digest", "status", "producer_id"}
        allowed = required | {"authorization_id", "produced_at", "verifier_id"}
        missing = sorted(required - set(record))
        if missing:
            problems.extend(f"evidence_missing:{index}:{name}" for name in missing)
            continue
        unknown = sorted(set(record) - allowed)
        if unknown:
            problems.extend(f"evidence_unknown:{index}:{name}" for name in unknown)
            continue
        category = record["category"]
        producer_id = record["producer_id"]
        status = record["status"]
        if not isinstance(category, str) or _EVIDENCE_CATEGORY_RE.fullmatch(category) is None:
            problems.append(f"evidence_category_invalid:{index}")
            continue
        if not isinstance(producer_id, str) or _PRODUCER_ID_RE.fullmatch(producer_id) is None:
            problems.append(f"evidence_producer_invalid:{index}")
            continue
        if not isinstance(status, str) or status not in _CANDIDATE_EVIDENCE_STATUSES:
            problems.append(f"evidence_status_invalid:{index}")
            continue
        expected = digest_object(record["raw"], domain="commercial-evidence-raw")
        if record["content_digest"] != expected:
            problems.append(f"evidence_digest_mismatch:{index}")
            continue
        if not _DIGEST_RE.fullmatch(str(record["content_digest"])):
            problems.append(f"evidence_digest_invalid:{index}")
            continue
        valid.append(record)
    return valid, tuple(problems)


def _k5_evidence_analysis(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    analysis_kind: str,
    required_categories: Sequence[str],
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    if "evidence" not in request.inputs:
        return _not_run(
            request,
            expected_skill_id,
            {"kernel": "K5-verification", "analysis_kind": analysis_kind},
            ("raw_evidence_required",),
        )
    records, problems = _validated_evidence_records(request.inputs["evidence"])
    if problems:
        return _blocked(request, expected_skill_id, problems)
    categories = {record["category"] for record in records}
    missing_categories = tuple(
        f"evidence_category_not_run:{category}"
        for category in required_categories
        if category not in categories
    )
    if missing_categories:
        return _not_run(
            request,
            expected_skill_id,
            {
                "kernel": "K5-verification",
                "analysis_kind": analysis_kind,
                "received_category_digest": digest_object(
                    sorted(categories),
                    domain="verification-received-categories",
                ),
                "received_category_count": len(categories),
            },
            missing_categories,
        )
    failed_count = sum(record.get("status") == "FAILED" for record in records)
    output = {
        "kernel": "K5-verification",
        "analysis_kind": analysis_kind,
        "evidence_bundle_digest": digest_object(records, domain="verification-evidence-bundle"),
        "received_category_digest": digest_object(
            sorted(categories),
            domain="verification-received-categories",
        ),
        "received_category_count": len(categories),
        "required_categories": list(required_categories),
        "candidate_evidence_count": len(records),
        "independently_verified_count": 0,
        "candidate_failed_count": failed_count,
        "decision": "EVIDENCE_PENDING",
        "trust_status": "UNAUTHENTICATED_CALLER_CANDIDATE",
        "promotion_authorized": False,
        "certification": "NOT_CERTIFIED",
    }
    return _not_run(
        request,
        expected_skill_id,
        output,
        ("trusted_runtime_evidence_verifier_required",),
    )


def _redact(text: str) -> tuple[str, int]:
    patterns = (
        re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)([A-Za-z0-9_\-]{16,})"),
        re.compile(r"(?i)(bearer\s+)([A-Za-z0-9_.\-]{20,})"),
        re.compile(r"()(ghp_[A-Za-z0-9]{36})"),
    )
    result = text
    count = 0
    for pattern in patterns:
        result, current = pattern.subn(r"\1[REDACTED_SECRET]", result)
        count += current
    return result, count


def _k6_security_analysis(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    analysis_kind: str,
    required: Sequence[str],
    external_adapter: str | None = None,
    evidence_required: bool = False,
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    if evidence_required and "evidence" not in request.inputs:
        return _not_run(
            request,
            expected_skill_id,
            {"kernel": "K6-security-governance", "analysis_kind": analysis_kind},
            ("external_security_evidence_required",),
        )
    output: dict[str, Any] = {
        "kernel": "K6-security-governance",
        "analysis_kind": analysis_kind,
        "default_decision": "DENY",
        "external_trust_established": False,
        "certification": "NOT_CERTIFIED",
    }
    if evidence_required:
        output["caller_evidence_status"] = "UNTRUSTED_CANDIDATE_ONLY"
        return _not_run(
            request,
            expected_skill_id,
            output,
            ("trusted_security_evidence_verifier_required",),
        )
    if analysis_kind == "secret-redaction":
        sanitized, count = _redact(str(request.inputs["text"]))
        output.update(
            {
                "sanitized_text_digest": digest_object(sanitized, domain="sanitized-text"),
                "redaction_count": count,
                "scanner_scope": "BOUNDED_PATTERN_SET",
                "complete_secret_scan": False,
                "capability_scope": "BOUNDED_IN_MEMORY_PATTERN_REDACTION",
                "limitations": ["pattern_set_incomplete", "no_external_dlp_verification"],
            }
        )
    elif analysis_kind in {"policy", "authorization"}:
        rules = request.inputs.get("policy", request.inputs.get("grants", ()))
        output.update(
            {
                "candidate_policy_digest": digest_object(rules, domain="caller-policy-candidate"),
                "requested_action_digest": digest_object(
                    request.inputs.get("requested_action"), domain="requested-action"
                ),
                "resource_digest": digest_object(
                    request.inputs.get("resource"), domain="requested-resource"
                ),
                "decision": "DENY",
                "candidate_policy_status": "UNTRUSTED_CANDIDATE_ONLY",
            }
        )
        return _not_run(
            request,
            expected_skill_id,
            output,
            ("trusted_policy_decision_point_required",),
        )
    elif analysis_kind == "sbom":
        components = request.inputs["components"]
        output.update(
            {
                "component_digest": digest_object(components, domain="sbom-components"),
                "component_count": len(components),
                "sbom_format": "CycloneDX-1.5-CANDIDATE",
                "vulnerability_scan": "NOT_RUN",
                "license_verification": "NOT_RUN",
            }
        )
    elif analysis_kind == "provenance":
        output.update(
            {
                "provenance_draft": {
                    "subject_digest": request.inputs["subject_digest"],
                    "materials_digest": digest_object(
                        request.inputs["materials"], domain="provenance-materials"
                    ),
                    "material_count": len(request.inputs["materials"]),
                },
                "slsa_level": "NOT_CLAIMED",
                "signature": "NOT_RUN",
            }
        )
    else:
        output["input_digest"] = digest_object(
            {name: request.inputs[name] for name in required}, domain="security-analysis-input"
        )
    if external_adapter:
        return _external(
            request,
            expected_skill_id,
            output,
            (f"external_{external_adapter}_adapter_required",),
        )
    if analysis_kind == "secret-redaction":
        output.update(
            {
                "bounded_subcapability": "bounded_pattern_redaction",
                "bounded_subcapability_executed": True,
                "objective_coverage": "PARTIAL",
            }
        )
        return _not_run(
            request,
            expected_skill_id,
            output,
            ("complete_dlp_scanner_and_independent_verification_required",),
        )
    return _not_run(
        request,
        expected_skill_id,
        {
            **output,
            "capability_scope": "CALLER_INPUT_CANDIDATE_ONLY",
            "limitations": ["trusted_security_adapter_not_run"],
        },
        ("trusted_security_runtime_or_independent_evidence_required",),
    )


def _k7_database_analysis(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    analysis_kind: str,
    required: Sequence[str],
    needs_parser: bool = False,
    needs_native_evidence: bool = False,
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    output: dict[str, Any] = {
        "kernel": "K7-database-data",
        "analysis_kind": analysis_kind,
        "typed_ir_schema": "elmos.database-ir.v1",
        "production_writes": False,
        "native_engine_execution": "NOT_RUN",
    }
    if needs_parser:
        output.update(
            {
                "source_digest": digest_object(
                    {name: request.inputs[name] for name in required}, domain="database-source"
                ),
                "regex_conversion_used": False,
                "caller_parser_result": "UNTRUSTED_NOT_EXECUTION_AUTHORITY"
                if "parser_adapter_result" in request.inputs
                else "NOT_PROVIDED",
            }
        )
        return _external(
            request,
            expected_skill_id,
            output,
            ("real_versioned_sql_parser_and_engine_adapter_required",),
        )
    if needs_native_evidence:
        output["caller_evidence_status"] = (
            "UNTRUSTED_CANDIDATE_ONLY" if "evidence" in request.inputs else "NOT_PROVIDED"
        )
        return _not_run(
            request,
            expected_skill_id,
            output,
            ("trusted_source_and_target_native_engine_evidence_required",),
        )
    ir_material = {name: request.inputs[name] for name in required}
    output.update(
        {
            "database_ir_digest": digest_object(ir_material, domain="database-ir"),
            "input_binding_digests": {
                name: digest_object(request.inputs[name], domain=f"database-input:{name}")
                for name in required
            },
            "unsupported_constructs_digest": digest_object(
                request.inputs.get("unsupported_constructs", ()),
                domain="database-unsupported-constructs",
            ),
            "unsupported_construct_count": len(request.inputs.get("unsupported_constructs", ())),
        }
    )
    return _not_run(
        request,
        expected_skill_id,
        {
            **output,
            "capability_scope": "CALLER_INPUT_DIGEST_ANALYSIS_ONLY",
            "limitations": ["native_database_adapter_not_run", "independent_evidence_not_run"],
        },
        ("native_database_or_typed_parser_adapter_required",),
    )


def _k8_observability_plan(
    request: HandlerRequest,
    expected_skill_id: str,
    *,
    plan_kind: str,
    required: Sequence[str],
    promotion_gate: bool = False,
) -> HandlerResult:
    _enforce_input_contract(request, expected_skill_id)
    missing = _missing(request, required)
    if missing:
        return _blocked(request, expected_skill_id, missing)
    material = {name: request.inputs[name] for name in required}
    output = {
        "kernel": "K8-observability-evolution",
        "plan_kind": plan_kind,
        "plan_digest": digest_object(material, domain="observability-evolution-plan"),
        "input_binding_digests": {
            name: digest_object(value, domain=f"observability-input:{name}")
            for name, value in material.items()
        },
        "input_binding_count": len(material),
        "provider_effects": False,
        "promotion_authorized": False,
        "external_evidence": "NOT_RUN",
    }
    if promotion_gate:
        if "external_evidence" in request.inputs:
            output["caller_external_evidence"] = "UNVERIFIED_CANDIDATE_ONLY"
        return _not_run(
            request,
            expected_skill_id,
            output,
            ("independent_promotion_evidence_required",),
        )
    if plan_kind == "self-evolving-skill-candidate":
        output["candidate_only"] = True
        output["self_promotion_forbidden"] = True
    return _not_run(
        request,
        expected_skill_id,
        {
            **output,
            "capability_scope": "DIGEST_BOUND_PLAN_CANDIDATE_ONLY",
            "limitations": ["no_provider_effect", "no_independent_evidence"],
        },
        ("trusted_observability_or_evolution_adapter_required",),
    )


# K1 -- ten exact wrappers.
def handle_universal_agent_skill_runtime(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "universal-agent-skill-runtime", plan_kind="skill-execution", required=("requested_skills", "policy"))


def handle_progressive_skill_disclosure(request: HandlerRequest) -> HandlerResult:
    return _progressive_disclosure_result(request)


def handle_context_aware_skill_source(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "context-aware-skill-source", plan_kind="context-filter", required=("candidates", "filters"))


def handle_skill_registry_ingestion(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "skill-registry-ingestion", plan_kind="registry-ingestion", required=("entries", "registry_revision"))


def handle_skill_sandbox_runner(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "skill-sandbox-runner", plan_kind="sandbox-execution", required=("command", "sandbox_policy"), adapter_required=True)


def handle_skill_version_provenance(request: HandlerRequest) -> HandlerResult:
    return _version_provenance_result(request)


def handle_model_tool_skill_router(request: HandlerRequest) -> HandlerResult:
    return _constrained_router_result(request)


def handle_human_approval_message_injection(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "human-approval-message-injection", plan_kind="human-approval-plan", required=("approval_request", "checkpoint"))


def handle_durable_agent_workflow(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "durable-agent-workflow", plan_kind="durable-workflow", required=("workflow_steps", "idempotency"))


def handle_task_checkpoint_time_travel(request: HandlerRequest) -> HandlerResult:
    return _k1_runtime_plan(request, "task-checkpoint-time-travel", plan_kind="checkpoint-replay", required=("checkpoint", "target_step"))


# K2 -- ten exact wrappers.
def handle_polyglot_syntax_front_end(request: HandlerRequest) -> HandlerResult:
    return _k2_repository_analysis(request, "polyglot-syntax-front-end", analysis_kind="parsed-units", required=("repository_snapshot", "parsed_units"))


def handle_semantic_symbol_index(request: HandlerRequest) -> HandlerResult:
    return _k2_repository_analysis(request, "semantic-symbol-index", analysis_kind="symbol-index", required=("repository_snapshot", "symbols"))


def handle_repository_semantic_code_graph(request: HandlerRequest) -> HandlerResult:
    return _k2_repository_analysis(request, "repository-semantic-code-graph", analysis_kind="semantic-graph", required=("repository_snapshot", "graph"))


def handle_cross_repository_impact_analysis(request: HandlerRequest) -> HandlerResult:
    return _repository_algorithm_result(request, "cross-repository-impact-analysis")


def handle_dependency_build_graph_discovery(request: HandlerRequest) -> HandlerResult:
    return _k2_repository_analysis(request, "dependency-build-graph-discovery", analysis_kind="dependency-build-graph", required=("repository_snapshot", "graph"))


def handle_runtime_evidence_graph(request: HandlerRequest) -> HandlerResult:
    return _k2_repository_analysis(request, "runtime-evidence-graph", analysis_kind="runtime-evidence-graph", required=("repository_snapshot", "graph", "runtime_evidence"))


def handle_repository_slicing_context_pack(request: HandlerRequest) -> HandlerResult:
    return _repository_algorithm_result(request, "repository-slicing-context-pack")


def handle_affected_test_selection(request: HandlerRequest) -> HandlerResult:
    return _repository_algorithm_result(request, "affected-test-selection")


def handle_software_catalog_ownership_graph(request: HandlerRequest) -> HandlerResult:
    return _k2_repository_analysis(request, "software-catalog-ownership-graph", analysis_kind="ownership-graph", required=("repository_snapshot", "graph", "ownership"))


def handle_change_risk_classifier(request: HandlerRequest) -> HandlerResult:
    return _repository_algorithm_result(request, "change-risk-classifier")


# K3 -- ten exact wrappers.
def handle_multi_engine_rewrite_router(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "multi-engine-rewrite-router", transformation_kind="rewrite-routing")


def handle_compiler_api_rewrite(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "compiler-api-rewrite", transformation_kind="compiler-api-rewrite")


def handle_semantic_ir_lift_lower(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "semantic-ir-lift-lower", transformation_kind="semantic-ir-lift-lower")


def handle_behavioral_equivalence_migration(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "behavioral-equivalence-migration", transformation_kind="behavioral-equivalence")


def handle_framework_modernization_router(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "framework-modernization-router", transformation_kind="framework-modernization")


def handle_api_contract_preserving_transform(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "api-contract-preserving-transform", transformation_kind="api-contract-preservation")


def handle_concurrency_semantics_transform(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "concurrency-semantics-transform", transformation_kind="concurrency-semantics")


def handle_build_system_migration(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "build-system-migration", transformation_kind="build-system-migration")


def handle_configuration_iac_migration(request: HandlerRequest) -> HandlerResult:
    return _k3_transformation_plan(request, "configuration-iac-migration", transformation_kind="configuration-iac-migration")


def handle_transformation_explainability_ledger(request: HandlerRequest) -> HandlerResult:
    return _explainability_ledger_result(request)


# K4 -- nine exact wrappers.
def handle_hermetic_build_environment(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "hermetic-build-environment", execution_kind="hermetic_build")


def handle_untrusted_code_microvm_sandbox(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "untrusted-code-microvm-sandbox", execution_kind="microvm_sandbox")


def handle_reproducible_build_verifier(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "reproducible-build-verifier", execution_kind="independent_rebuild")


def handle_remote_execution_cache_planner(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "remote-execution-cache-planner", execution_kind="remote_cache_plan")


def handle_resource_quota_budget_enforcer(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "resource-quota-budget-enforcer", execution_kind="quota_enforced_execution")


def handle_deterministic_toolchain_lock(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "deterministic-toolchain-lock", execution_kind="locked_toolchain")


def handle_environment_capture_replay(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "environment-capture-replay", execution_kind="environment_replay")


def handle_native_runtime_lab(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "native-runtime-lab", execution_kind="native_runtime_lab")


def handle_fault_injection_chaos_execution(request: HandlerRequest) -> HandlerResult:
    return _k4_execution_contract(request, "fault-injection-chaos-execution", execution_kind="fault_injection_chaos")


# K5 -- fourteen exact wrappers.
def handle_compiler_grade_certification_gate(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "compiler-grade-certification-gate", analysis_kind="compiler-gate", required_categories=("COMPILER_GATE",))


def handle_differential_runtime_verification(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "differential-runtime-verification", analysis_kind="differential-runtime", required_categories=("DIFFERENTIAL_RUNTIME",))


def handle_continuous_fuzz_certification(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "continuous-fuzz-certification", analysis_kind="continuous-fuzz", required_categories=("FUZZ",))


def handle_property_based_test_generation(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "property-based-test-generation", analysis_kind="property-tests", required_categories=("PROPERTY_TEST",))


def handle_api_schema_fuzz_testing(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "api-schema-fuzz-testing", analysis_kind="api-schema-fuzz", required_categories=("API_SCHEMA_FUZZ",))


def handle_contract_compatibility_verification(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "contract-compatibility-verification", analysis_kind="contract-compatibility", required_categories=("CONTRACT_COMPATIBILITY",))


def handle_browser_e2e_trace_verification(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "browser-e2e-trace-verification", analysis_kind="browser-e2e", required_categories=("BROWSER_E2E",))


def handle_static_dataflow_assurance(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "static-dataflow-assurance", analysis_kind="static-dataflow", required_categories=("STATIC_DATAFLOW",))


def handle_formal_proof_router(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "formal-proof-router", analysis_kind="formal-proof-routing", required_categories=("FORMAL_PROOF",))


def handle_metamorphic_equivalence_testing(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "metamorphic-equivalence-testing", analysis_kind="metamorphic-equivalence", required_categories=("METAMORPHIC",))


def handle_mutation_strength_certification(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "mutation-strength-certification", analysis_kind="mutation-strength", required_categories=("MUTATION",))


def handle_performance_regression_certification(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "performance-regression-certification", analysis_kind="performance-regression", required_categories=("PERFORMANCE",))


def handle_golden_route_corpus_manager(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "golden-route-corpus-manager", analysis_kind="golden-route-corpus", required_categories=("GOLDEN_CORPUS",))


def handle_evidence_gate_orchestrator(request: HandlerRequest) -> HandlerResult:
    return _k5_evidence_analysis(request, "evidence-gate-orchestrator", analysis_kind="e0-e5-gate", required_categories=("GATE_INPUT",))


# K6 -- ten exact wrappers.
def handle_policy_as_code_kernel(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "policy-as-code-kernel", analysis_kind="policy", required=("policy", "requested_action", "resource"))


def handle_fine_grained_authorization_engine(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "fine-grained-authorization-engine", analysis_kind="authorization", required=("grants", "requested_action", "resource"))


def handle_secret_egress_control(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "secret-egress-control", analysis_kind="secret-redaction", required=("text",))


def handle_prompt_injection_tool_boundary(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "prompt-injection-tool-boundary", analysis_kind="prompt-tool-boundary", required=("untrusted_content", "tool_policy"))


def handle_sbom_vulnerability_attestation(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "sbom-vulnerability-attestation", analysis_kind="sbom", required=("components",))


def handle_slsa_in_toto_provenance(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "slsa-in-toto-provenance", analysis_kind="provenance", required=("subject_digest", "materials"))


def handle_artifact_signing_verification(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "artifact-signing-verification", analysis_kind="signature-verification", required=("artifact_digest", "signature_ref", "trust_root_ref"), external_adapter="signature_verifier")


def handle_license_compliance_scanner(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "license-compliance-scanner", analysis_kind="license-compliance", required=("components", "license_policy"), external_adapter="license_scanner")


def handle_multi_tenant_isolation_certifier(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "multi-tenant-isolation-certifier", analysis_kind="tenant-isolation", required=("isolation_contract",), evidence_required=True)


def handle_kubernetes_policy_certification(request: HandlerRequest) -> HandlerResult:
    return _k6_security_analysis(request, "kubernetes-policy-certification", analysis_kind="kubernetes-policy", required=("manifests", "policy_bundle"), evidence_required=True)


# K7 -- ten exact wrappers.
def handle_database_semantic_compiler(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "database-semantic-compiler", analysis_kind="database-ir", required=("source_engine", "source_version", "schema_metadata", "parsed_statements"))


def handle_schema_metadata_discovery(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "schema-metadata-discovery", analysis_kind="schema-metadata", required=("source_engine", "source_version", "schema_metadata"))


def handle_sql_dialect_transpiler(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "sql-dialect-transpiler", analysis_kind="sql-transpile", required=("sql", "source_engine", "target_engine"), needs_parser=True)


def handle_stored_routine_migration(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "stored-routine-migration", analysis_kind="routine-migration", required=("routine_source", "source_engine", "target_engine"), needs_parser=True)


def handle_transaction_semantic_equivalence(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "transaction-semantic-equivalence", analysis_kind="transaction-equivalence", required=("source_contract", "target_contract"), needs_native_evidence=True)


def handle_query_plan_performance_equivalence(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "query-plan-performance-equivalence", analysis_kind="query-plan-performance", required=("source_plan", "target_plan", "workload"), needs_native_evidence=True)


def handle_data_lineage_impact_analysis(request: HandlerRequest) -> HandlerResult:
    return _database_algorithm_result(request, "data-lineage-impact-analysis")


def handle_data_migration_reconciliation(request: HandlerRequest) -> HandlerResult:
    return _database_algorithm_result(request, "data-migration-reconciliation")


def handle_cdc_shadow_compare(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "cdc-shadow-compare", analysis_kind="cdc-shadow", required=("source_stream", "target_stream", "watermark"), needs_native_evidence=True)


def handle_database_security_policy_migration(request: HandlerRequest) -> HandlerResult:
    return _k7_database_analysis(request, "database-security-policy-migration", analysis_kind="database-security", required=("source_policies", "target_profile"), needs_native_evidence=True)


# K8 -- twelve exact wrappers.
def handle_otel_agent_execution_tracing(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "otel-agent-execution-tracing", plan_kind="otel-trace", required=("trace_events", "resource_attributes"))


def handle_agent_evidence_evaluation(request: HandlerRequest) -> HandlerResult:
    return _observability_algorithm_result(request, "agent-evidence-evaluation")


def handle_trajectory_dataset_versioning(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "trajectory-dataset-versioning", plan_kind="trajectory-dataset", required=("trajectories", "dataset_version"))


def handle_failure_attribution_learning(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "failure-attribution-learning", plan_kind="failure-attribution", required=("failure_events", "causal_dimensions"))


def handle_self_evolving_skill_factory(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "self-evolving-skill-factory", plan_kind="self-evolving-skill-candidate", required=("trajectories", "candidate_policy"))


def handle_automatic_task_corpus_generation(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "automatic-task-corpus-generation", plan_kind="task-corpus", required=("source_failures", "corpus_policy"))


def handle_skill_promotion_canary(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "skill-promotion-canary", plan_kind="skill-canary", required=("candidate_version", "canary_policy"), promotion_gate=True)


def handle_software_catalog_production_scorecard(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "software-catalog-production-scorecard", plan_kind="production-scorecard", required=("catalog_snapshot", "metric_definitions"))


def handle_feature_flag_progressive_rollout(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "feature-flag-progressive-rollout", plan_kind="feature-rollout", required=("flag_contract", "rollout_policy"), promotion_gate=True)


def handle_incident_replay_root_cause(request: HandlerRequest) -> HandlerResult:
    return _observability_algorithm_result(request, "incident-replay-root-cause")


def handle_cost_latency_quality_optimizer(request: HandlerRequest) -> HandlerResult:
    return _observability_algorithm_result(request, "cost-latency-quality-optimizer")


def handle_platform_template_generator(request: HandlerRequest) -> HandlerResult:
    return _k8_observability_plan(request, "platform-template-generator", plan_kind="platform-template", required=("template_contract", "organization_policy"))


EXACT_SKILL_HANDLERS: Mapping[str, ExactHandler] = MappingProxyType(
    {
        "universal-agent-skill-runtime": handle_universal_agent_skill_runtime,
        "progressive-skill-disclosure": handle_progressive_skill_disclosure,
        "context-aware-skill-source": handle_context_aware_skill_source,
        "skill-registry-ingestion": handle_skill_registry_ingestion,
        "skill-sandbox-runner": handle_skill_sandbox_runner,
        "skill-version-provenance": handle_skill_version_provenance,
        "model-tool-skill-router": handle_model_tool_skill_router,
        "human-approval-message-injection": handle_human_approval_message_injection,
        "durable-agent-workflow": handle_durable_agent_workflow,
        "task-checkpoint-time-travel": handle_task_checkpoint_time_travel,
        "polyglot-syntax-front-end": handle_polyglot_syntax_front_end,
        "semantic-symbol-index": handle_semantic_symbol_index,
        "repository-semantic-code-graph": handle_repository_semantic_code_graph,
        "cross-repository-impact-analysis": handle_cross_repository_impact_analysis,
        "dependency-build-graph-discovery": handle_dependency_build_graph_discovery,
        "runtime-evidence-graph": handle_runtime_evidence_graph,
        "repository-slicing-context-pack": handle_repository_slicing_context_pack,
        "affected-test-selection": handle_affected_test_selection,
        "software-catalog-ownership-graph": handle_software_catalog_ownership_graph,
        "change-risk-classifier": handle_change_risk_classifier,
        "multi-engine-rewrite-router": handle_multi_engine_rewrite_router,
        "compiler-api-rewrite": handle_compiler_api_rewrite,
        "semantic-ir-lift-lower": handle_semantic_ir_lift_lower,
        "behavioral-equivalence-migration": handle_behavioral_equivalence_migration,
        "framework-modernization-router": handle_framework_modernization_router,
        "api-contract-preserving-transform": handle_api_contract_preserving_transform,
        "concurrency-semantics-transform": handle_concurrency_semantics_transform,
        "build-system-migration": handle_build_system_migration,
        "configuration-iac-migration": handle_configuration_iac_migration,
        "transformation-explainability-ledger": handle_transformation_explainability_ledger,
        "hermetic-build-environment": handle_hermetic_build_environment,
        "untrusted-code-microvm-sandbox": handle_untrusted_code_microvm_sandbox,
        "reproducible-build-verifier": handle_reproducible_build_verifier,
        "remote-execution-cache-planner": handle_remote_execution_cache_planner,
        "resource-quota-budget-enforcer": handle_resource_quota_budget_enforcer,
        "deterministic-toolchain-lock": handle_deterministic_toolchain_lock,
        "environment-capture-replay": handle_environment_capture_replay,
        "native-runtime-lab": handle_native_runtime_lab,
        "fault-injection-chaos-execution": handle_fault_injection_chaos_execution,
        "compiler-grade-certification-gate": handle_compiler_grade_certification_gate,
        "differential-runtime-verification": handle_differential_runtime_verification,
        "continuous-fuzz-certification": handle_continuous_fuzz_certification,
        "property-based-test-generation": handle_property_based_test_generation,
        "api-schema-fuzz-testing": handle_api_schema_fuzz_testing,
        "contract-compatibility-verification": handle_contract_compatibility_verification,
        "browser-e2e-trace-verification": handle_browser_e2e_trace_verification,
        "static-dataflow-assurance": handle_static_dataflow_assurance,
        "formal-proof-router": handle_formal_proof_router,
        "metamorphic-equivalence-testing": handle_metamorphic_equivalence_testing,
        "mutation-strength-certification": handle_mutation_strength_certification,
        "performance-regression-certification": handle_performance_regression_certification,
        "golden-route-corpus-manager": handle_golden_route_corpus_manager,
        "evidence-gate-orchestrator": handle_evidence_gate_orchestrator,
        "policy-as-code-kernel": handle_policy_as_code_kernel,
        "fine-grained-authorization-engine": handle_fine_grained_authorization_engine,
        "secret-egress-control": handle_secret_egress_control,
        "prompt-injection-tool-boundary": handle_prompt_injection_tool_boundary,
        "sbom-vulnerability-attestation": handle_sbom_vulnerability_attestation,
        "slsa-in-toto-provenance": handle_slsa_in_toto_provenance,
        "artifact-signing-verification": handle_artifact_signing_verification,
        "license-compliance-scanner": handle_license_compliance_scanner,
        "multi-tenant-isolation-certifier": handle_multi_tenant_isolation_certifier,
        "kubernetes-policy-certification": handle_kubernetes_policy_certification,
        "database-semantic-compiler": handle_database_semantic_compiler,
        "schema-metadata-discovery": handle_schema_metadata_discovery,
        "sql-dialect-transpiler": handle_sql_dialect_transpiler,
        "stored-routine-migration": handle_stored_routine_migration,
        "transaction-semantic-equivalence": handle_transaction_semantic_equivalence,
        "query-plan-performance-equivalence": handle_query_plan_performance_equivalence,
        "data-lineage-impact-analysis": handle_data_lineage_impact_analysis,
        "data-migration-reconciliation": handle_data_migration_reconciliation,
        "cdc-shadow-compare": handle_cdc_shadow_compare,
        "database-security-policy-migration": handle_database_security_policy_migration,
        "otel-agent-execution-tracing": handle_otel_agent_execution_tracing,
        "agent-evidence-evaluation": handle_agent_evidence_evaluation,
        "trajectory-dataset-versioning": handle_trajectory_dataset_versioning,
        "failure-attribution-learning": handle_failure_attribution_learning,
        "self-evolving-skill-factory": handle_self_evolving_skill_factory,
        "automatic-task-corpus-generation": handle_automatic_task_corpus_generation,
        "skill-promotion-canary": handle_skill_promotion_canary,
        "software-catalog-production-scorecard": handle_software_catalog_production_scorecard,
        "feature-flag-progressive-rollout": handle_feature_flag_progressive_rollout,
        "incident-replay-root-cause": handle_incident_replay_root_cause,
        "cost-latency-quality-optimizer": handle_cost_latency_quality_optimizer,
        "platform-template-generator": handle_platform_template_generator,
    }
)

for _skill_id, _handler in EXACT_SKILL_HANDLERS.items():
    _handler.__elmos_exact_skill_id__ = _skill_id  # type: ignore[attr-defined]


def _build_input_contracts() -> Mapping[str, SkillInputContract]:
    contracts: dict[str, SkillInputContract] = {}

    def add(
        names: Iterable[str],
        required: Sequence[str],
        optional: Sequence[str] = (),
        ephemeral_sensitive_fields: Sequence[str] = (),
    ) -> None:
        contract = SkillInputContract(
            frozenset(required),
            frozenset(optional),
            frozenset(ephemeral_sensitive_fields),
        )
        for name in names:
            if name in contracts:
                raise ValueError(f"duplicate exact input contract: {name}")
            contracts[name] = contract

    k1 = {
        "universal-agent-skill-runtime": ("requested_skills", "policy"),
        "context-aware-skill-source": ("candidates", "filters"),
        "skill-registry-ingestion": ("entries", "registry_revision"),
        "skill-sandbox-runner": ("command", "sandbox_policy"),
        "model-tool-skill-router": ("candidates", "constraints"),
        "human-approval-message-injection": ("approval_request", "checkpoint"),
        "durable-agent-workflow": ("workflow_steps", "idempotency"),
        "task-checkpoint-time-travel": ("checkpoint", "target_step"),
    }
    for name, k1_required in k1.items():
        add((name,), k1_required)
    add(
        ("progressive-skill-disclosure",),
        ("skill_metadata", "query_terms", "context_token_budget", "candidate_permissions"),
    )
    add(
        ("skill-version-provenance",),
        ("version_bindings", "source_digests"),
        ("dependencies",),
    )

    k2 = {
        "polyglot-syntax-front-end": ("repository_snapshot", "parsed_units"),
        "semantic-symbol-index": ("repository_snapshot", "symbols"),
        "repository-semantic-code-graph": ("repository_snapshot", "graph"),
        "cross-repository-impact-analysis": ("repository_snapshot", "graph", "changed_paths"),
        "dependency-build-graph-discovery": ("repository_snapshot", "graph"),
        "runtime-evidence-graph": ("repository_snapshot", "graph", "runtime_evidence"),
        "repository-slicing-context-pack": (
            "repository_snapshot",
            "graph",
            "focus_nodes",
            "node_costs",
            "token_budget",
        ),
        "affected-test-selection": (
            "repository_snapshot",
            "graph",
            "changed_paths",
            "test_coverage",
            "critical_nodes",
        ),
        "software-catalog-ownership-graph": ("repository_snapshot", "graph", "ownership"),
        "change-risk-classifier": (
            "repository_snapshot",
            "graph",
            "changed_paths",
            "critical_nodes",
            "runtime_hot_paths",
            "security_boundaries",
            "historical_failures",
            "proof_coverage",
        ),
    }
    for name, k2_required in k2.items():
        add((name,), k2_required)

    add(
        (
            "multi-engine-rewrite-router",
            "compiler-api-rewrite",
            "semantic-ir-lift-lower",
            "behavioral-equivalence-migration",
            "framework-modernization-router",
            "api-contract-preserving-transform",
            "concurrency-semantics-transform",
            "build-system-migration",
            "configuration-iac-migration",
        ),
        ("source_snapshot", "target_profile", "change_intent"),
        ("proposed_edits", "apply_requested"),
    )
    add(("transformation-explainability-ledger",), ("edits",))
    add(
        (
            "hermetic-build-environment",
            "untrusted-code-microvm-sandbox",
            "reproducible-build-verifier",
            "remote-execution-cache-planner",
            "resource-quota-budget-enforcer",
            "deterministic-toolchain-lock",
            "environment-capture-replay",
            "native-runtime-lab",
            "fault-injection-chaos-execution",
        ),
        ("command", "input_digests", "quotas"),
        ("toolchain_lock",),
    )
    add(
        (
            "compiler-grade-certification-gate",
            "differential-runtime-verification",
            "continuous-fuzz-certification",
            "property-based-test-generation",
            "api-schema-fuzz-testing",
            "contract-compatibility-verification",
            "browser-e2e-trace-verification",
            "static-dataflow-assurance",
            "formal-proof-router",
            "metamorphic-equivalence-testing",
            "mutation-strength-certification",
            "performance-regression-certification",
            "golden-route-corpus-manager",
            "evidence-gate-orchestrator",
        ),
        ("evidence",),
    )

    k6: Mapping[str, tuple[Sequence[str], Sequence[str]]] = {
        "policy-as-code-kernel": (("policy", "requested_action", "resource"), ()),
        "fine-grained-authorization-engine": (("grants", "requested_action", "resource"), ()),
        "prompt-injection-tool-boundary": (("untrusted_content", "tool_policy"), ()),
        "sbom-vulnerability-attestation": (("components",), ()),
        "slsa-in-toto-provenance": (("subject_digest", "materials"), ()),
        "artifact-signing-verification": (("artifact_digest", "signature_ref", "trust_root_ref"), ()),
        "license-compliance-scanner": (("components", "license_policy"), ()),
        "multi-tenant-isolation-certifier": (("isolation_contract",), ("evidence",)),
        "kubernetes-policy-certification": (("manifests", "policy_bundle"), ("evidence",)),
    }
    for name, (k6_required, k6_optional) in k6.items():
        add((name,), k6_required, k6_optional)
    add(
        ("secret-egress-control",),
        ("text",),
        ephemeral_sensitive_fields=("text",),
    )

    k7: Mapping[str, tuple[Sequence[str], Sequence[str]]] = {
        "database-semantic-compiler": (
            ("source_engine", "source_version", "schema_metadata", "parsed_statements"),
            ("unsupported_constructs",),
        ),
        "schema-metadata-discovery": (
            ("source_engine", "source_version", "schema_metadata"),
            ("unsupported_constructs",),
        ),
        "sql-dialect-transpiler": (
            ("sql", "source_engine", "target_engine"),
            ("parser_adapter_result", "unsupported_constructs"),
        ),
        "stored-routine-migration": (
            ("routine_source", "source_engine", "target_engine"),
            ("parser_adapter_result", "unsupported_constructs"),
        ),
        "transaction-semantic-equivalence": (
            ("source_contract", "target_contract"),
            ("evidence", "unsupported_constructs"),
        ),
        "query-plan-performance-equivalence": (
            ("source_plan", "target_plan", "workload"),
            ("evidence", "unsupported_constructs"),
        ),
        "data-lineage-impact-analysis": (
            ("datasets", "lineage_edges", "changed_entities"),
            (),
        ),
        "data-migration-reconciliation": (
            ("source_rows", "target_rows", "key_fields"),
            ("decimal_fields",),
        ),
        "cdc-shadow-compare": (
            ("source_stream", "target_stream", "watermark"),
            ("evidence", "unsupported_constructs"),
        ),
        "database-security-policy-migration": (
            ("source_policies", "target_profile"),
            ("evidence", "unsupported_constructs"),
        ),
    }
    for name, (k7_required, k7_optional) in k7.items():
        add((name,), k7_required, k7_optional)

    k8: Mapping[str, tuple[Sequence[str], Sequence[str]]] = {
        "otel-agent-execution-tracing": (("trace_events", "resource_attributes"), ()),
        "agent-evidence-evaluation": (("observations", "rubric"), ()),
        "trajectory-dataset-versioning": (("trajectories", "dataset_version"), ()),
        "failure-attribution-learning": (("failure_events", "causal_dimensions"), ()),
        "self-evolving-skill-factory": (("trajectories", "candidate_policy"), ()),
        "automatic-task-corpus-generation": (("source_failures", "corpus_policy"), ()),
        "skill-promotion-canary": (("candidate_version", "canary_policy"), ("external_evidence",)),
        "software-catalog-production-scorecard": (("catalog_snapshot", "metric_definitions"), ()),
        "feature-flag-progressive-rollout": (("flag_contract", "rollout_policy"), ("external_evidence",)),
        "incident-replay-root-cause": (("expected_events", "observed_events"), ()),
        "cost-latency-quality-optimizer": (("candidates", "constraints"), ()),
        "platform-template-generator": (("template_contract", "organization_policy"), ()),
    }
    for name, (k8_required, k8_optional) in k8.items():
        add((name,), k8_required, k8_optional)

    if set(contracts) != set(EXACT_SKILL_HANDLERS):
        missing = sorted(set(EXACT_SKILL_HANDLERS) - set(contracts))
        unexpected = sorted(set(contracts) - set(EXACT_SKILL_HANDLERS))
        raise ValueError(f"exact input contract drift: missing={missing}, unexpected={unexpected}")
    return MappingProxyType(contracts)


EXACT_SKILL_INPUT_CONTRACTS = _build_input_contracts()


__all__: list[str] = []
