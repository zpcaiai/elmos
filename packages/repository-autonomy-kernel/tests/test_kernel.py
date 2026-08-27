from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from elmos_repository_autonomy.catalog import SKILL_NAMES
from elmos_repository_autonomy.dispatcher import AutonomyRuntime, DispatchContext
from elmos_repository_autonomy.errors import KernelError
from elmos_repository_autonomy.models import Status
from elmos_repository_autonomy.schema_registry import SCHEMA_NAMES, SchemaRegistry
from elmos_repository_autonomy.security import ExecutionAuthority, ToolDescriptor
from elmos_repository_autonomy.server import KernelHTTPServer, make_handler
from elmos_repository_autonomy.storage import DurableStore


def authority_payload(token: int = 1) -> dict:
    return {
        "environment": {"id": "env-1"},
        "workspace": {"id": "ws-1", "root": "/workspace"},
        "permission_profile": {"id": "profile-1", "policy_snapshot_hash": "sha256:policy", "allowed_tools": ["echo"], "network_scopes": [], "secret_scopes": []},
        "fencing_token": token,
    }


def snapshot() -> dict:
    return {"sha256": "sha256:snapshot", "files": [{"path": "src/app.py", "content": "def main():\n    return helper()\n\ndef helper():\n    return 1\n"}, {"path": "pyproject.toml", "content": "[project]\nname='demo'\n"}, {"path": "tests/test_app.py", "content": "def test_main(): pass\n"}]}


def test_catalog_is_closed_and_every_skill_has_a_handler():
    runtime = AutonomyRuntime()
    assert len(SKILL_NAMES) == 31
    assert set(runtime.skill_names) == set(SKILL_NAMES)
    assert runtime.execute("does-not-exist", {"value": 1}).error.code == "UNKNOWN_SKILL"


def test_task_spec_compiler_is_versioned_and_reports_ambiguity():
    result = AutonomyRuntime().execute("task-spec-delta-compiler", {"requirements": {"objective": "modernize", "scope": None}, "repository_snapshot": {"sha256": "sha256:s"}})
    assert result.status == Status.BLOCKED
    assert result.output["task_spec"]["immutable"] is True
    assert result.output["task_spec"]["hash"].startswith("sha256:")
    assert result.output["ambiguity_register"][0]["requires_approval"] is True


def test_durable_run_has_replayable_events_checkpoint_and_idempotency():
    store = DurableStore()
    runtime = AutonomyRuntime(store)
    payload = {"task_spec": {"hash": "sha256:task"}, "workflow_definition": {"version": "2.0.0", "tasks": [{"id": "discover", "owned_paths": [], "read_only": True}, {"id": "verify", "dependencies": ["discover"], "owned_paths": [], "read_only": True}]}, "idempotency_key": "run-1"}
    first = runtime.execute("durable-run-orchestrator", payload, context=DispatchContext(tenant_id="tenant-a", account_id="account-a", store=store))
    second = runtime.execute("durable-run-orchestrator", payload, context=DispatchContext(tenant_id="tenant-a", account_id="account-a", store=store))
    assert first.status == Status.LOCAL_ENGINEERING_VALIDATED
    assert first.output["run"]["state"] == "PLANNING"
    assert len(first.output["checkpoints"]) == 1
    assert second.output["run"]["run_id"] == first.output["run"]["run_id"]
    assert store.replay_state(first.output["run"]["run_id"], tenant_id="tenant-a") == "PLANNING"


def test_authority_and_lease_fencing_are_fail_closed():
    runtime = AutonomyRuntime()
    denied = runtime.execute("execution-authority-kernel", {**authority_payload(), "permission_profile": {**authority_payload()["permission_profile"], "authority_source": "conversation"}, "tool_request": {"tool_id": "echo", "environment_id": "env-1", "workspace_id": "ws-1", "fencing_token": 1}})
    assert denied.status == Status.BLOCKED
    store = DurableStore()
    first = store.acquire_lease("workspace", "ws-1", "worker-a")
    second = store.acquire_lease("workspace", "ws-1", "worker-b")
    try:
        store.assert_lease(first)
        assert False, "stale lease must be rejected"
    except KernelError as exc:
        assert getattr(exc, "info", None).code == "FENCING_REJECTED"
    store.assert_lease(second)


def test_typed_tool_runtime_requires_authority_and_replays_idempotent_success():
    store = DurableStore()
    runtime = AutonomyRuntime(store)
    authority = ExecutionAuthority.from_payload(authority_payload())
    runtime.tool_runtime.register(ToolDescriptor.from_payload({"tool_id": "echo", "version": "1", "input_schema": {}, "output_schema": {}, "side_effects": False, "allowed_operations": ["run"]}), lambda args: {"echo": args})
    context = DispatchContext(store=store, authority=authority)
    payload = {"tool_descriptor": {"tool_id": "echo", "version": "1", "input_schema": {}, "output_schema": {}, "side_effects": False, "allowed_operations": ["run"]}, "tool_call_request": {"tool_id": "echo", "version": "1", "operation": "run", "input": {"x": 1}, "environment_id": "env-1", "workspace_id": "ws-1", "fencing_token": 1, "idempotency_key": "call-1"}, "policy_snapshot": {"decision": "ALLOW"}}
    first = runtime.execute("typed-tool-runtime", payload, context=context)
    second = runtime.execute("typed-tool-runtime", payload, context=context)
    assert first.status == Status.SUCCEEDED
    assert second.output["tool_call_record"]["replayed"] is True


def test_repository_intelligence_pipeline_is_snapshot_bound():
    runtime = AutonomyRuntime()
    census = runtime.execute("repository-census", {"immutable_repository_snapshot": snapshot()})
    assert census.status == Status.LOCAL_ENGINEERING_VALIDATED
    index = runtime.execute("incremental-semantic-index", {"repository_snapshot": snapshot(), "change_set": ["src/app.py"]})
    assert index.output["semantic_index"]["snapshot_sha"] == "sha256:snapshot"
    ir = runtime.execute("semantic-ir-compiler", {"repository_semantic_index": index.output["semantic_index"], "task_spec": {"id": "t"}, "source_framework_profile": {"language": "Python"}, "target_profile": {"language": "Python"}})
    assert ir.output["semantic_ir"]["status"] == "PARTIAL"


def test_dag_conflict_and_validation_coverage_are_explicit():
    runtime = AutonomyRuntime()
    graph = runtime.execute("changegraph-vcs", {"task_spec": {"id": "t"}, "repository_snapshot": snapshot(), "patches": [{"path": "src/app.py", "status": "UNVERIFIED"}], "validation_results": []})
    assert graph.output["merge_plan"]["status"] == "BLOCKED"
    validation = runtime.execute("validation-dag", {"task_spec": {"acceptance_criteria": [{"id": "build"}, {"id": "security"}]}, "change_graph": graph.output["change_graph"], "repository_profile": {"snapshot_sha": "sha256:s"}, "risk_profile": {"level": "HIGH"}, "test_catalog": []})
    assert validation.status == Status.LOCAL_ENGINEERING_VALIDATED
    assert set(validation.output["coverage_map"]) == {"build", "security"}
    coordination = runtime.execute("multi-agent-worktree-coordinator", {"task_dag": {"tasks": [{"id": "a", "owned_paths": ["src"], "read_only": False}, {"id": "b", "owned_paths": ["src/app.py"], "read_only": False}]}, "agent_contracts": [{"agent_id": "a1"}]})
    assert coordination.status == Status.BLOCKED


def test_release_gate_never_certifies_missing_external_evidence():
    result = AutonomyRuntime().execute("evidence-release-gate", {"completion_claim": {"status": "SUCCEEDED"}, "acceptance_criteria": [{"id": "build"}], "validation_results": [{"id": "build", "status": "PASS"}], "artifacts": [], "approvals": [], "deployment_results": {}})
    assert result.status == Status.BLOCKED
    assert result.output["deployment_complete_attestation"]["attested"] is False
    assert result.output["acceptance_decision"]["decision"] != "P05_DEPLOYMENT_COMPLETE"


def test_artifact_tenant_isolation_and_security_scan():
    runtime = AutonomyRuntime()
    result = runtime.execute("artifact-evidence-protocol", {"producer_step": {"id": "step"}, "content": {"ok": True}}, context=DispatchContext(tenant_id="tenant-a", store=runtime.store))
    assert result.status == Status.LOCAL_ENGINEERING_VALIDATED
    artifact_id = result.output["artifact"]["artifact_id"]
    try:
        runtime.store.read_artifact(artifact_id, tenant_id="tenant-b")
        assert False, "cross-tenant artifact read must fail"
    except KernelError as exc:
        assert getattr(exc, "info", None).code == "ARTIFACT_CORRUPT"
    security = runtime.execute("tiered-security-assurance", {"tool_or_file_change": {}, "diff": "password='leaked'", "semantic_index": {}, "security_policy": {}, "deployment_artifact": {}})
    assert security.status == Status.BLOCKED


def test_p1_p2_handlers_have_real_structured_outputs():
    runtime = AutonomyRuntime()
    cases = {
        "prefix-stable-context-planner": {"task_spec": {"objective": "x"}, "repository_index": {"symbols": []}, "current_step": {"id": "s"}, "token_budget": 1000},
        "lazy-tool-loader": {"step_requirements": ["read"], "tool_catalog": [{"tool_id": "read", "capabilities": ["read"], "version": "1"}]},
        "model-state-continuity": {"context_ledger": {"objective": "x"}, "run_state": {"state": "PAUSED"}, "provider_event": {}},
        "phase-aware-model-router": {"step_profile": {}, "model_capability_profiles": [{"model_id": "m", "eval_status": "PASS", "max_context": 1000, "privacy_mode": "private", "quality": 1, "cost_per_call": 1, "latency_ms": 1}], "provider_policy": {"allowed_privacy_modes": ["private"]}},
        "layered-cache-fabric": {"snapshot_hash": "s", "task_spec_hash": "t", "workflow_version": "1", "skill_versions": {}, "policy_hash": "p", "tool_schema_versions": {}, "model_profile": "m", "value": {"ok": True}},
        "cost-eta-observability": {"run_events": [{"wall_clock_ms": 10, "status": "PASS"}], "repo_features": {}, "cache_metrics": {}, "pricing_profile": {}},
        "session-time-travel": {"run_event_stream": [{"sequence_no": 1}], "checkpoints": [], "context_ledgers": [], "change_graph": {}, "artifacts": []},
        "capability-package-registry": {"package_manifest": {"name": "x", "version": "1"}, "components": [{"id": "c", "path": "skill.md"}], "dependency_lock": {}, "signature": {"valid": True, "key_id": "k"}, "test_results": [{"status": "PASS"}]},
        "auto-improvement-inbox-and-skill-curator": {"run_incidents": [{"code": "x"}]},
        "repository-model-elo": {"arena_results": [{"candidate_id": "m", "status": "PASS"}]},
        "repository-gym-golden-routes": {"benchmark_repositories": [{"id": "r"}], "golden_task_specs": [{"id": "t"}]},
    }
    for skill, payload in cases.items():
        result = runtime.execute(skill, payload)
        assert result.output, skill
        assert result.error is None, (skill, result.to_dict())


def test_schema_registry_and_adapter_conformance_are_closed_world():
    registry = SchemaRegistry()
    assert len(SCHEMA_NAMES) == 20
    assert registry.validate("task-spec", {"version": "2.0.0"}).valid is True
    try:
        registry.validate("task-spec", {"unexpected": True})
        assert False, "unknown schema fields must be rejected"
    except KernelError as exc:
        assert getattr(exc, "info", None).code == "SCHEMA_MISMATCH"
    result = AutonomyRuntime().conformance("openai-codex")
    assert result["status"] == "BLOCKED"
    assert len(result["cases"]) == 12


def test_http_control_plane_enforces_identity_and_run_lifecycle():
    runtime = AutonomyRuntime()
    server = KernelHTTPServer(("127.0.0.1", 0), make_handler(runtime))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path: str, *, payload: dict | None = None, identity: bool = True):
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        if identity:
            headers.update({"X-Elmos-Tenant-Id": "tenant-http", "X-Elmos-Account-Id": "account-http", "X-Elmos-Identity-Verified": "true"})
        body = json.dumps(payload).encode() if payload is not None else None
        method = "POST" if body is not None else "GET"
        return urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=headers, method=method), timeout=3)

    try:
        with request("/v1/skills") as response:
            assert response.status == 200
            assert len(json.loads(response.read())["skills"]) == 31
        payload = {"task_spec": {"hash": "sha256:task"}, "workflow_definition": {"tasks": [{"id": "s1", "read_only": True}]}, "idempotency_key": "http-1"}
        try:
            request("/v2/runs", payload=payload, identity=False)
            assert False, "missing identity must be rejected"
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        with request("/v2/runs", payload=payload) as response:
            created = json.loads(response.read())
            assert response.status == 202
            run_id = created["output"]["run"]["run_id"]
        with request(f"/v2/runs/{run_id}/pause", payload={}) as response:
            assert response.status == 202
            assert json.loads(response.read())["run"]["state"] == "PAUSED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_durable_store_backup_and_restore_are_atomic(tmp_path):
    store = DurableStore()
    run = store.create_run(tenant_id="tenant-a", account_id="account-a", task_spec_hash="sha256:t", workflow_version="2.0.0", repo_snapshot_sha=None, payload={})
    backup = tmp_path / "backup.sqlite"
    restored = tmp_path / "restored.sqlite"
    backup_info = store.backup_to(str(backup))
    assert backup_info["content_hash"].startswith("sha256:")
    restore_info = DurableStore.restore_from(str(backup), str(restored))
    assert restore_info["content_hash"].startswith("sha256:")
    restored_store = DurableStore(str(restored))
    try:
        assert restored_store.get_run(run["run_id"], tenant_id="tenant-a")["state"] == "CREATED"
    finally:
        restored_store.close()
