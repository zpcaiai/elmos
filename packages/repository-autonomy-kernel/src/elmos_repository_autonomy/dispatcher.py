"""Closed-world dispatcher binding all 31 v2 Skills to real handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from . import kernel_bridge
from .adapters import ConformanceHarness
from .analysis import census, change_graph, compile_ir, contract_diff, semantic_index, validation_plan
from .catalog import SKILL_NAMES, SKILL_SPECS
from .certification import CertificationEngine, EvidenceTrustStore, TestMatrixEvaluator
from .errors import ContractError, ErrorInfo, KernelError
from .evidence import create_artifact, release_gate, security_assurance, verification_mesh
from .external import AuthorizationVerifier, ExternalAdapter, ExternalOperationCoordinator
from .golden import CustomerAcceptanceRegistry, GoldenRouteEvaluator
from .learning import arena, demonstration, elo, gym, improvement, package_registry
from .models import (
    DispatchResult,
    Status,
    digest,
    error_result,
    paths_overlap,
    require_mapping,
    require_string,
    utc_now,
)
from .orchestration import cache_key, context_plan, continuity, cost_eta, dag, route, task_spec, time_travel
from .schema_registry import SchemaRegistry
from .security import Decision, ExecutionAuthority, PolicyEngine, ToolDescriptor, ToolRuntime, sandbox_plan
from .storage import DurableStore


@dataclass(slots=True)
class DispatchContext:
    tenant_id: str = "local"
    account_id: str = "local"
    run_id: str | None = None
    store: DurableStore | None = None
    tool_runtime: ToolRuntime | None = None
    policy_engine: PolicyEngine | None = None
    authority: ExecutionAuthority | None = None
    schema_registry: SchemaRegistry | None = None
    trusted: bool = False


class AutonomyRuntime:
    def __init__(
        self,
        store: DurableStore | None = None,
        *,
        control_store: Any | None = None,
        authorizer: AuthorizationVerifier | None = None,
        evidence_trust_store: EvidenceTrustStore | None = None,
        conformance_receipt_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
        external_receipt_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
        customer_acceptance_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
        golden_evidence_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    ) -> None:
        self.store = store or DurableStore()
        self.control_store = control_store or self.store
        self.policy_engine = PolicyEngine()
        self.tool_runtime = ToolRuntime(self.store)
        self.schema_registry = SchemaRegistry()
        self.external = ExternalOperationCoordinator(
            self.control_store, authorizer=authorizer, receipt_verifier=external_receipt_verifier
        )
        self.certification = CertificationEngine(self.control_store, evidence_trust_store)
        self.golden_routes = GoldenRouteEvaluator(customer_acceptance_verifier, golden_evidence_verifier)
        self.customer_acceptance = CustomerAcceptanceRegistry(
            self.control_store, customer_acceptance_verifier
        )
        self.conformance_harness = ConformanceHarness(conformance_receipt_verifier)
        self._handlers = {name: getattr(self, "_handle_" + name.replace("-", "_")) for name in SKILL_NAMES}
        if len(self._handlers) != 31:
            raise RuntimeError("all 31 autonomy handlers must be bound")

    @property
    def skill_names(self) -> tuple[str, ...]:
        return SKILL_NAMES

    def conformance(self, adapter_id: str, adapter_version: str = "2.0.0", responses: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.conformance_harness.evaluate(adapter_id, adapter_version, responses)

    def register_external_adapter(self, adapter: ExternalAdapter) -> None:
        self.external.register(adapter)

    def certification_matrix(self, *, tenant_id: str) -> dict[str, Any]:
        return TestMatrixEvaluator().evaluate(
            self.control_store.list_certification_evidence(tenant_id=tenant_id)
        )

    def execute(self, skill: str, payload: Mapping[str, Any] | None = None, *, context: DispatchContext | None = None) -> DispatchResult:
        if skill not in self._handlers:
            info = ErrorInfo("UNKNOWN_SKILL", details={"message": "skill is not in the closed v2 catalog", "skill": skill})
            return error_result(skill, info)
        value = dict(payload or {})
        if not value:
            return error_result(skill, ErrorInfo("INVALID_INPUT", details={"message": "input must contain at least one typed field"}))
        ctx = context or DispatchContext(store=self.store, tool_runtime=self.tool_runtime, policy_engine=self.policy_engine)
        if ctx.store is None:
            ctx.store = self.store
        if ctx.tool_runtime is None:
            ctx.tool_runtime = self.tool_runtime
        if ctx.policy_engine is None:
            ctx.policy_engine = self.policy_engine
        if ctx.schema_registry is None:
            ctx.schema_registry = self.schema_registry
        try:
            served = kernel_bridge.serve(skill, value, ctx)
            if served.served:
                status, output, reasons = served.status, dict(served.output or {}), list(served.reasons)
                side_effects = False
            else:
                status, output, reasons, side_effects = self._handlers[skill](value, ctx)
                reasons = [*reasons, *served.reasons, "ENGINE:legacy"]
            unknown_outputs = sorted(set(output) - set(SKILL_SPECS[skill].outputs))
            if unknown_outputs:
                raise ContractError("SCHEMA_MISMATCH", f"handler emitted undeclared output fields: {unknown_outputs}")
            if not output:
                raise ContractError("SCHEMA_MISMATCH", "handler emitted an empty output")
            return DispatchResult(skill=skill, status=status, output=output, reasons=tuple(reasons), side_effects_performed=side_effects)
        except KernelError as exc:
            return error_result(skill, exc.info)
        except (TypeError, ValueError, KeyError) as exc:
            return error_result(skill, ErrorInfo("INVALID_INPUT", details={"type": type(exc).__name__, "message": str(exc)}))
        except Exception as exc:  # noqa: BLE001 - runtime boundary must return a structured failure
            return error_result(skill, ErrorInfo("INTERNAL_ERROR", details={"type": type(exc).__name__}, recommended_action="Inspect the correlated server log."))

    def _local(self, output: dict[str, Any], *, reasons: list[str] | None = None, side_effects: bool = False) -> tuple[Status, dict[str, Any], list[str], bool]:
        return Status.LOCAL_ENGINEERING_VALIDATED, output, reasons or [], side_effects

    def _handle_task_spec_delta_compiler(self, p: dict[str, Any], c: DispatchContext):
        result = task_spec(p.get("requirements"), p.get("repository_snapshot"), p.get("previous_task_spec"), p.get("policy_profile"))
        blocked = any(item.get("severity") == "HIGH" for item in result["ambiguity_register"])
        return (Status.BLOCKED if blocked else Status.LOCAL_ENGINEERING_VALIDATED, result, ["AMBIGUITY_BLOCKED"] if blocked else [], False)

    def _handle_durable_run_orchestrator(self, p: dict[str, Any], c: DispatchContext):
        spec = require_mapping(p.get("task_spec"), "task_spec")
        workflow = require_mapping(p.get("workflow_definition"), "workflow_definition")
        tasks = workflow.get("tasks", p.get("tasks"))
        plan = dag(tasks)
        run = c.store.create_run(tenant_id=c.tenant_id, account_id=c.account_id, task_spec_hash=str(spec.get("hash", digest(spec))), workflow_version=str(workflow.get("version", "2.0.0")), repo_snapshot_sha=p.get("repository_snapshot", {}).get("sha256") if isinstance(p.get("repository_snapshot"), Mapping) else None, payload={"task_spec": spec, "workflow": workflow}, idempotency_key=p.get("idempotency_key"))
        if run["state"] == "CREATED":
            for state in ("DISCOVERING", "SPECIFYING", "PLANNING"):
                run = c.store.transition_run(run["run_id"], state, tenant_id=c.tenant_id)
        for task in plan["tasks"]:
            c.store.upsert_step(run_id=run["run_id"], step_id=task["id"], step_type=str(task.get("type", "skill")), tenant_id=c.tenant_id)
        checkpoint = c.store.create_checkpoint(run["run_id"], {"state": run["state"], "dag_digest": plan["digest"], "completed": []}, tenant_id=c.tenant_id)
        events = c.store.events_since(run["run_id"], tenant_id=c.tenant_id)
        output = {"run": run, "step_runs": [{"step_id": row["id"], "state": "PENDING", "attempt_no": 0} for row in plan["tasks"]], "run_events": events, "checkpoints": [checkpoint], "rollback_plan": {"status": "PLANNED", "safe_point": checkpoint["checkpoint_id"]}, "progress_snapshot": {"completed": 0, "total": len(plan["tasks"]), "machine_wall_clock_seconds": 0}}
        return self._local(output, side_effects=True)

    def _handle_execution_authority_kernel(self, p: dict[str, Any], c: DispatchContext):
        authority = ExecutionAuthority.from_payload(p)
        request = require_mapping(p.get("tool_request"), "tool_request")
        # The request is intentionally copied into the authority boundary; no prompt field is consulted.
        decision = authority.authorize({**request, "fencing_token": p.get("fencing_token", request.get("fencing_token"))})
        c.authority = authority
        audit = {"event_id": digest({"authority": authority.snapshot(), "request": request}), "event_type": "AUTHORIZATION_DECISION", "decision": decision["decision"], "occurred_at": utc_now()}
        return self._local({"execution_authority": authority.snapshot(), "authority_snapshot": authority.snapshot(), "authorization_decision": decision, "audit_event": audit})

    def _handle_typed_tool_runtime(self, p: dict[str, Any], c: DispatchContext):
        descriptor = ToolDescriptor.from_payload(require_mapping(p.get("tool_descriptor"), "tool_descriptor"))
        request = require_mapping(p.get("tool_call_request"), "tool_call_request")
        authority = c.authority or ExecutionAuthority.from_payload(require_mapping(p.get("execution_authority"), "execution_authority"))
        c.tool_runtime.register(descriptor)
        record = c.tool_runtime.invoke({**request, "tenant_id": c.tenant_id, "run_id": c.run_id}, authority, p.get("policy_snapshot"))
        status = Status.SUCCEEDED if record["state"] == Status.SUCCEEDED.value else Status.NOT_RUN if record["state"] == Status.NOT_RUN.value else Status.BLOCKED
        output = {"tool_call_record": record, "typed_result": record.get("typed_result"), "structured_error": record.get("structured_error"), "side_effect_record": {"performed": False, "tool_id": descriptor.tool_id}, "compensation_record": {"status": "NOT_REQUIRED"}}
        return status, output, [] if status == Status.SUCCEEDED else [str((record.get("structured_error") or {}).get("code", "TOOL_NOT_RUN"))], False

    def _handle_policy_hook_kernel(self, p: dict[str, Any], c: DispatchContext):
        event = require_mapping(p.get("hook_event"), "hook_event")
        layers = p.get("policy_layers", [])
        if not isinstance(layers, list):
            raise ContractError("POLICY_CONFLICT", "policy_layers must be an array")
        result = c.policy_engine.evaluate(event, [require_mapping(item, "policy_layers[]") for item in layers], p.get("run_context", {}))
        if c.store and p.get("tenant_id", c.tenant_id):
            # This is a durable audit record; it does not grant authority.
            c.store.record_policy_decision(tenant_id=c.tenant_id, run_id=c.run_id, event_type=str(event.get("type", "HOOK")), decision=result["decision"], reason="; ".join(result["reasons"]) or "policy evaluated", policy_hash=result["policy_snapshot_hash"], payload=result)
            if c.run_id:
                c.store.append_event(c.run_id, "POLICY_DECISION", result, tenant_id=c.tenant_id)
        return (Status.LOCAL_ENGINEERING_VALIDATED if result["decision"] != Decision.DENY else Status.BLOCKED, {"policy_decision": result, "modified_input": result["modified_input"], "approval_request": {"required": result["decision"] in {Decision.ASK_USER, Decision.REQUIRE_ESCALATION, Decision.REQUIRE_SECOND_REVIEW}}, "policy_evidence": {"hash": result["policy_snapshot_hash"]}, "audit_event": {"event_type": "POLICY_EVALUATED", "occurred_at": result["decided_at"]}}, [] if result["decision"] != Decision.DENY else ["POLICY_DENIED"], False)

    def _handle_two_phase_secretless_sandbox(self, p: dict[str, Any], c: DispatchContext):
        return self._local(sandbox_plan(require_mapping(p.get("repository_snapshot"), "repository_snapshot"), require_mapping(p.get("workspace_profile"), "workspace_profile"), require_mapping(p.get("network_policy"), "network_policy"), require_mapping(p.get("secret_binding_plan", {}), "secret_binding_plan")))

    def _handle_workspace_lease_fencing(self, p: dict[str, Any], c: DispatchContext):
        workspace = require_mapping(p.get("workspace"), "workspace")
        worker = require_string(p.get("worker_identity"), "worker_identity")
        lease_policy = require_mapping(p.get("lease_policy", {}), "lease_policy")
        lease = c.store.acquire_lease("workspace", require_string(workspace.get("id"), "workspace.id"), worker, ttl_seconds=int(lease_policy.get("ttl_seconds", 60)))
        return self._local({"lease": lease, "fencing_token": lease["fencing_token"], "heartbeat": {"required": True, "interval_seconds": max(1, int(lease_policy.get("heartbeat_seconds", 10)))}, "takeover_event": {"status": "AVAILABLE", "new_token_on_takeover": True}, "recovery_plan": {"checkpoint": p.get("checkpoint"), "unknown_side_effect_policy": "RECONCILE_BEFORE_REPLAY"}}, side_effects=True)

    def _handle_artifact_evidence_protocol(self, p: dict[str, Any], c: DispatchContext):
        return self._local(create_artifact(p, store=c.store, tenant_id=c.tenant_id, run_id=c.run_id), side_effects=True)

    def _handle_repository_census(self, p: dict[str, Any], c: DispatchContext):
        snapshot = require_mapping(p.get("immutable_repository_snapshot"), "immutable_repository_snapshot")
        return self._local(census(snapshot, p.get("build_files"), snapshot_sha=snapshot.get("sha256")))

    def _handle_incremental_semantic_index(self, p: dict[str, Any], c: DispatchContext):
        return self._local(semantic_index(require_mapping(p.get("repository_snapshot"), "repository_snapshot"), p.get("previous_index"), p.get("change_set"), p.get("compiler_metadata")))

    def _handle_semantic_ir_compiler(self, p: dict[str, Any], c: DispatchContext):
        return self._local(compile_ir(require_mapping(p.get("repository_semantic_index"), "repository_semantic_index"), require_mapping(p.get("task_spec"), "task_spec"), require_mapping(p.get("source_framework_profile", {}), "source_framework_profile"), require_mapping(p.get("target_profile", {}), "target_profile")))

    def _handle_changegraph_vcs(self, p: dict[str, Any], c: DispatchContext):
        return self._local(change_graph(require_mapping(p.get("task_spec"), "task_spec"), require_mapping(p.get("repository_snapshot"), "repository_snapshot"), p.get("patches"), p.get("artifact_lineage"), p.get("validation_results")))

    def _handle_validation_dag(self, p: dict[str, Any], c: DispatchContext):
        result = validation_plan(require_mapping(p.get("task_spec"), "task_spec"), require_mapping(p.get("change_graph"), "change_graph"), require_mapping(p.get("repository_profile"), "repository_profile"), require_mapping(p.get("risk_profile", {}), "risk_profile"), p.get("test_catalog"))
        return (Status.LOCAL_ENGINEERING_VALIDATED if result["validation_budget"]["status"] == "VALID" else Status.BLOCKED, result, [] if result["validation_budget"]["status"] == "VALID" else ["VALIDATION_PLAN_INCOMPLETE"], False)

    def _handle_independent_verification_mesh(self, p: dict[str, Any], c: DispatchContext):
        result = verification_mesh(p.get("change_set"), p.get("validation_dag"), require_mapping(p.get("task_spec"), "task_spec"), require_mapping(p.get("repository_snapshot"), "repository_snapshot"), p.get("policies"))
        status = Status.LOCAL_ENGINEERING_VALIDATED if result["release_recommendation"]["status"] == "PASS" else Status.BLOCKED
        return status, result, [] if status == Status.LOCAL_ENGINEERING_VALIDATED else ["FINDING_UNVALIDATED"], False

    def _handle_evidence_release_gate(self, p: dict[str, Any], c: DispatchContext):
        result = release_gate(p)
        decision = result["acceptance_decision"]["decision"]
        status = Status.REJECTED if decision == Status.REJECTED.value else Status.BLOCKED
        return status, result, result["acceptance_decision"]["reasons"], False

    def _handle_contract_compatibility_engine(self, p: dict[str, Any], c: DispatchContext):
        result = contract_diff(require_mapping(p.get("baseline_contracts"), "baseline_contracts"), require_mapping(p.get("candidate_contracts"), "candidate_contracts"), p.get("consumer_inventory"), require_mapping(p.get("compatibility_policy", {}), "compatibility_policy"))
        status = Status.BLOCKED if result["compatibility_report"]["status"] == "BLOCKED" else Status.LOCAL_ENGINEERING_VALIDATED
        return status, result, ["UNKNOWN_CONSUMER"] if status == Status.BLOCKED else [], False

    def _handle_prefix_stable_context_planner(self, p: dict[str, Any], c: DispatchContext):
        return self._local(context_plan(require_mapping(p.get("task_spec"), "task_spec"), require_mapping(p.get("repository_index"), "repository_index"), require_mapping(p.get("current_step"), "current_step"), require_mapping(p.get("skill_metadata", {}), "skill_metadata"), int(p.get("token_budget", 1)), p.get("previous_ledger")))

    def _handle_lazy_tool_loader(self, p: dict[str, Any], c: DispatchContext):
        catalog = p.get("tool_catalog", [])
        required = set(p.get("step_requirements", [])) if isinstance(p.get("step_requirements", []), list) else set()
        authority = c.authority
        allowed = set(authority.allowed_tools) if authority else set()
        loaded, denied = [], []
        for item in catalog if isinstance(catalog, list) else []:
            row = require_mapping(item, "tool_catalog[]")
            tool_id = str(row.get("tool_id"))
            capabilities = set(row.get("capabilities", []))
            if required and not required.intersection(capabilities):
                continue
            if tool_id in allowed:
                loaded.append(row)
            else:
                denied.append({"tool_id": tool_id, "reason": "not authorized"})
        result = {"tool_load_plan": {"required_capabilities": sorted(required), "lazy": True}, "loaded_tool_set": loaded, "tool_schema_bundle": [{"tool_id": item.get("tool_id"), "version": item.get("version")} for item in loaded], "denied_tool_set": denied, "load_metrics": {"catalog_count": len(catalog) if isinstance(catalog, list) else 0, "loaded_count": len(loaded)}}
        return self._local(result, reasons=["TOOL_NOT_AUTHORIZED"] if denied else [])

    def _handle_model_state_continuity(self, p: dict[str, Any], c: DispatchContext):
        return self._local(continuity(require_mapping(p.get("context_ledger"), "context_ledger"), require_mapping(p.get("run_state"), "run_state"), require_mapping(p.get("agent_state", {}), "agent_state"), p.get("tool_results"), p.get("open_findings"), require_mapping(p.get("provider_event", {}), "provider_event")))

    def _handle_multi_agent_worktree_coordinator(self, p: dict[str, Any], c: DispatchContext):
        plan = dag(require_mapping(p.get("task_dag"), "task_dag").get("tasks"))
        conflicts = []
        rows = plan["tasks"]
        for index, left in enumerate(rows):
            for right in rows[index + 1:]:
                if any(any(paths_overlap(a, b) for b in right["owned_paths"]) for a in left["owned_paths"]):
                    conflicts.append({"left": left["id"], "right": right["id"], "reason": "overlapping write set"})
        contracts = p.get("agent_contracts", []) if isinstance(p.get("agent_contracts"), list) else []
        assignments = [{"task_id": task["id"], "agent_id": (contracts[index % len(contracts)].get("agent_id") if contracts else None), "write_set": task["owned_paths"], "lease_required": True} for index, task in enumerate(rows)]
        result = {"agent_assignments": assignments, "agent_runs": [], "artifact_handoffs": [], "conflict_report": {"conflicts": conflicts, "status": "BLOCKED" if conflicts else "PASS"}, "merge_plan": {"status": "BLOCKED" if conflicts else "READY_FOR_REVIEW", "verification_required": True}}
        return (Status.BLOCKED if conflicts else Status.LOCAL_ENGINEERING_VALIDATED, result, ["AGENT_CONFLICT"] if conflicts else [], False)

    def _handle_phase_aware_model_router(self, p: dict[str, Any], c: DispatchContext):
        result = route(require_mapping(p.get("step_profile"), "step_profile"), p.get("model_capability_profiles"), require_mapping(p.get("risk_profile", {}), "risk_profile"), require_mapping(p.get("budget", {}), "budget"), require_mapping(p.get("provider_policy", {}), "provider_policy"), p.get("recent_evals"))
        return (Status.LOCAL_ENGINEERING_VALIDATED if result["routing_decision"]["status"] == "ROUTED" else Status.BLOCKED, result, [] if result["routing_decision"]["status"] == "ROUTED" else ["MODEL_ROUTE_UNAVAILABLE"], False)

    def _handle_layered_cache_fabric(self, p: dict[str, Any], c: DispatchContext):
        key = cache_key(p)
        tenant = c.tenant_id
        hit = c.store.cache_get(tenant_id=tenant, layer=str(p.get("cache_layer", "context")), key_hash=key)
        value = p.get("value")
        if hit is None and "value" in p:
            entry = c.store.cache_put(tenant_id=tenant, layer=str(p.get("cache_layer", "context")), key_hash=key, value=value, provenance={"snapshot_hash": p["snapshot_hash"], "policy_hash": p["policy_hash"]}, expires_at=p.get("expires_at"))
        else:
            entry = hit
        return self._local({"cache_key": key, "cache_entry": entry, "hit_miss": "HIT" if hit else "MISS", "invalidation_set": p.get("invalidation_set", []), "provenance": {"tenant_id": tenant, "key_hash": key}, "cache_metrics": {"hit": bool(hit), "sensitive_cross_tenant_reuse": False}})

    def _handle_cost_eta_observability(self, p: dict[str, Any], c: DispatchContext):
        return self._local(cost_eta(p.get("run_events"), p.get("historical_runs"), require_mapping(p.get("repo_features", {}), "repo_features"), p.get("model_tool_usage"), require_mapping(p.get("cache_metrics", {}), "cache_metrics"), require_mapping(p.get("pricing_profile", {}), "pricing_profile")))

    def _handle_tiered_security_assurance(self, p: dict[str, Any], c: DispatchContext):
        result = security_assurance(require_mapping(p.get("tool_or_file_change", {}), "tool_or_file_change"), p.get("diff"), require_mapping(p.get("semantic_index", {}), "semantic_index"), require_mapping(p.get("security_policy", {}), "security_policy"), p.get("deployment_artifact"))
        return (Status.BLOCKED if result["security_gate"]["status"] in {"FAIL", "BLOCKED"} else Status.LOCAL_ENGINEERING_VALIDATED, result, ["SECURITY_GATE_FAILED"] if result["security_gate"]["status"] != "PASS" else [], False)

    def _handle_session_time_travel(self, p: dict[str, Any], c: DispatchContext):
        return self._local(time_travel(p.get("run_event_stream"), p.get("checkpoints"), p.get("context_ledgers"), p.get("change_graph"), p.get("artifacts")))

    def _handle_capability_package_registry(self, p: dict[str, Any], c: DispatchContext):
        result = package_registry(require_mapping(p.get("package_manifest"), "package_manifest"), p.get("components"), p.get("dependency_lock"), p.get("signature"), p.get("test_results"))
        return (Status.LOCAL_ENGINEERING_VALIDATED if result["registered_package"]["state"] == "REGISTERED" else Status.BLOCKED, result, [] if result["registered_package"]["state"] == "REGISTERED" else ["PACKAGE_INVALID"], False)

    def _handle_demonstration_to_skill(self, p: dict[str, Any], c: DispatchContext):
        return self._local(demonstration(require_mapping(p.get("validated_demonstration"), "validated_demonstration"), p.get("run_artifacts"), p.get("expert_annotations"), require_mapping(p.get("privacy_policy", {}), "privacy_policy")))

    def _handle_auto_improvement_inbox_and_skill_curator(self, p: dict[str, Any], c: DispatchContext):
        return self._local(improvement(p.get("run_incidents"), p.get("user_corrections"), p.get("findings"), p.get("telemetry"), p.get("benchmark_results")))

    def _handle_agent_arena(self, p: dict[str, Any], c: DispatchContext):
        return self._local(arena(p.get("arena_task_set"), p.get("agent_candidates"), p.get("fixed_environments"), p.get("budgets"), require_mapping(p.get("evaluation_protocol"), "evaluation_protocol")))

    def _handle_repository_model_elo(self, p: dict[str, Any], c: DispatchContext):
        return self._local(elo(p.get("arena_results"), p.get("production_evals"), p.get("task_taxonomy"), p.get("model_cost_latency")))

    def _handle_repository_gym_golden_routes(self, p: dict[str, Any], c: DispatchContext):
        return self._local(gym(p.get("benchmark_repositories"), p.get("golden_task_specs"), p.get("fixed_images"), p.get("expected_contracts"), p.get("chaos_scenarios")))


def dispatch(skill: str, payload: Mapping[str, Any] | None = None, *, context: DispatchContext | None = None) -> dict[str, Any]:
    runtime = context and context.store and AutonomyRuntime(context.store) or AutonomyRuntime()
    return runtime.execute(skill, payload, context=context).to_dict()
