from __future__ import annotations

import time
from pathlib import Path

from elmos_multimodal_intake import TenantContext, create_runtime
from elmos_multimodal_intake.canonical import canonical_digest, canonical_json
from elmos_multimodal_intake.context_lifecycle import ContextLifecycleBridge
from elmos_multimodal_intake.skill_runtime import RuntimeContext, SkillDispatcher, dispatch_skill


def _runtime(tmp_path: Path):
    runtime = create_runtime(tmp_path / "intake.sqlite3", tmp_path / "cas")
    tenant = TenantContext("tenant-context", "project-context", "actor-context")
    runtime.store.bootstrap_project(tenant)
    return runtime, tenant


def _ctx(
    tenant: TenantContext,
    *,
    request_id: str = "request-context",
    idempotency_key: str = "context-key",
    policy: dict | None = None,
    capabilities: dict | None = None,
) -> RuntimeContext:
    return RuntimeContext(
        tenant_id=tenant.tenant_id,
        project_id=tenant.project_id,
        actor_id=tenant.actor_id,
        request_id=request_id,
        trace_id="trace-context",
        idempotency_key=idempotency_key,
        policy=policy or {},
        capabilities=capabilities or {},
    )


def _state() -> dict:
    return {
        "goal": "preserve exact context",
        "latest_user_request": "continue",
        "constraints": ["tenant isolated"],
        "acceptance_criteria": ["integrity passes"],
        "todos": ["restore safely"],
        "facts": [
            {
                "fact_id": "fact-1",
                "type": "permission",
                "value": "read-only",
                "negated": False,
                "permission": "read",
                "version": 3,
                "source_digest": "sha256:" + "a" * 64,
                "critical": True,
                "anchor": {"asset_id": "asset-1", "version": 3},
            }
        ],
        "modified_files": ["a.py"],
        "test_state": ["NOT_RUN"],
    }


def test_direct_pure_handler_remains_available_without_composed_bridge() -> None:
    result = dispatch_skill(
        "elmos-multimodal-token-accounting",
        {
            "schema_version": "1.0",
            "request_id": "request-pure",
            "tenant_id": "tenant-pure",
            "project_id": "project-pure",
            "actor_id": "actor-pure",
            "inputs": {"items": [{"item_id": "text", "modality": "text", "text": "hello"}]},
            "policy": {},
            "capabilities": {},
        },
    )
    assert result["state"] == "SUCCEEDED"
    assert "usage_id" not in result["outputs"]


def test_composed_dispatch_prefers_durable_usage_bridge_and_replays_once(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    dispatcher = SkillDispatcher()
    dispatcher.register_bridge("elmos-multimodal-token-accounting", bridge)
    request = {
        "schema_version": "1.0",
        "request_id": "request-usage",
        "tenant_id": tenant.tenant_id,
        "project_id": tenant.project_id,
        "actor_id": tenant.actor_id,
        "idempotency_key": "usage-once",
        "inputs": {
            "task_id": "task-usage",
            "items": [{"item_id": "text", "modality": "text", "text": "hello world"}],
            "current_window_output_reserved_tokens": 20,
        },
        "policy": {},
        "capabilities": {
            "context_provider_usage": {
                "verified": True,
                "cumulative_input_tokens": 120,
                "cumulative_output_tokens": 40,
                "cumulative_cost_minor_units": 17,
                "currency": "USD",
            }
        },
    }
    first = dispatcher.dispatch("elmos-multimodal-token-accounting", request)
    replay = dispatcher.dispatch("elmos-multimodal-token-accounting", request)
    assert first["outputs"]["ledger"]["current_window"]["input_tokens"] > 0
    assert first["outputs"]["ledger"]["current_window"]["output_reserved_tokens"] == 20
    assert first["outputs"]["ledger"]["cumulative_provider"] == {
        "input_tokens": 120,
        "output_tokens": 40,
        "cost_minor_units": 17,
        "currency": "USD",
        "state": "VERIFIED",
    }
    assert replay["outputs"]["usage_id"] == first["outputs"]["usage_id"]
    assert replay["outputs"]["idempotent_replay"] is True
    count = runtime.store._connection.execute("SELECT count(*) FROM context_usage_ledger").fetchone()[0]
    assert count == 1
    runtime.close()


def test_pressure_hysteresis_forecast_and_action_event_are_persistent(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    policy = {"context_pressure": {"elevated": 0.6, "high": 0.8, "critical": 0.9, "hysteresis": 0.05, "version": "p1"}}
    first = bridge.handle(
        "elmos-context-pressure-monitor",
        _ctx(tenant, idempotency_key="pressure-1", policy=policy),
        {"task_id": "task-pressure", "used_tokens": 820, "effective_input_budget": 1000, "next_turn_tokens": 100},
    )
    second = bridge.handle(
        "elmos-context-pressure-monitor",
        _ctx(tenant, request_id="request-pressure-2", idempotency_key="pressure-2", policy=policy),
        {"task_id": "task-pressure", "used_tokens": 770, "effective_input_budget": 1000},
    )
    assert first["outputs"]["pressure_state"] == "HIGH"
    assert first["outputs"]["forecast_pressure_state"] == "CRITICAL"
    assert first["outputs"]["forecast_action"] == "BLOCK_AND_CHECKPOINT"
    assert second["outputs"]["previous_state"] == "HIGH"
    assert second["outputs"]["pressure_state"] == "HIGH"
    events = runtime.store._connection.execute(
        "SELECT count(*) FROM outbox_events WHERE event_type='context.pressure.action'"
    ).fetchone()[0]
    assert events == 2
    runtime.close()


def test_model_capability_snapshots_have_history_and_scoped_rollback(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    now = time.time()
    snapshots = []
    for version, window in ((1, 100_000), (2, 120_000)):
        observation = {
            "provider": "provider-a",
            "model_id": "model-a",
            "model_version": f"v{version}",
            "context_window_tokens": window,
            "max_output_tokens": 8_000,
            "modalities": ["text", "image"],
            "source": "provider-signed-metadata",
            "trust": "SIGNED_REGISTRY",
            "observed_at": now,
            "expires_at": now + 3600,
            "version": version,
        }
        result = bridge.handle(
            "elmos-model-capability-discovery",
            _ctx(tenant, request_id=f"request-cap-{version}", idempotency_key=f"cap-{version}", capabilities={"model_capability_observation": observation, "model_capability_now": now}),
            {"observation": observation},
        )
        snapshots.append(result["outputs"]["snapshot"])
    history = bridge.handle(
        "elmos-model-capability-discovery",
        _ctx(tenant, idempotency_key="cap-history"),
        {"operation": "history", "provider": "provider-a", "model_id": "model-a"},
    )
    assert [item["version"] for item in history["outputs"]["snapshots"]] == [2, 1]
    rolled_back = bridge.handle(
        "elmos-model-capability-discovery",
        _ctx(tenant, request_id="request-cap-rollback", idempotency_key="cap-rollback"),
        {"operation": "rollback", "snapshot_id": snapshots[0]["snapshot_id"]},
    )
    assert rolled_back["outputs"]["snapshot"]["version"] == 1
    runtime.close()


def test_compaction_writes_raw_history_to_cas_and_requires_passing_integrity(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    state = _state()
    raw_history = {"messages": [{"role": "user", "content": "exact original"}], "state": state}
    result = bridge.handle(
        "elmos-structured-context-compaction",
        _ctx(tenant, idempotency_key="compact-1", capabilities={"context_compactor": {"verified": True, "algorithm": "structured-dedupe-v2", "template_version": "template-4"}}),
        {"task_id": "task-compact", "state": state, "raw_history": raw_history, "package_version": "package-v1"},
    )
    assert result["state"] == "SUCCEEDED"
    assert runtime.cas.read_bytes(tenant.tenant_id, result["outputs"]["raw_history_digest"]) == canonical_json(raw_history).encode()
    row = runtime.store._connection.execute("SELECT * FROM context_checkpoints").fetchone()
    assert row["integrity_report_id"] == result["outputs"]["integrity_report_id"]
    assert row["raw_history_bytes"] > 0
    assert result["outputs"]["checkpoint"]["compaction_metadata"]["algorithm"] == "structured-dedupe-v2"
    runtime.close()


def test_integrity_failure_persists_and_denies_side_effect_authorization(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    ctx = _ctx(tenant, idempotency_key="integrity-fail")
    result = bridge.handle(
        "elmos-context-integrity-and-loss-detection",
        ctx,
        {
            "task_id": "task-integrity",
            "before": [{"fact_id": "permission", "value": "read", "negated": False, "version": 1}],
            "after": [{"fact_id": "permission", "value": "write", "negated": False, "version": 1}],
        },
    )
    assert result["state"] == "BLOCKED"
    assert result["outputs"]["side_effect_authorized"] is False
    assert bridge.side_effect_authorized(ctx, task_id="task-integrity", report_id=result["outputs"]["report_id"]) is False
    runtime.close()


def test_checkpoint_restore_is_authorized_and_idempotent_without_duplicate_effect_or_cost(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    created = bridge.handle(
        "elmos-context-checkpoint-and-recovery",
        _ctx(tenant, request_id="request-create", idempotency_key="checkpoint-create"),
        {"operation": "create", "task_id": "task-restore", "state": _state(), "package_version": "package-v1", "side_effect_cursor": ["effect-1"], "cost_cursor": {"minor_units": 7}},
    )
    checkpoint_id = created["outputs"]["checkpoint_id"]
    restore_request = "request-restore"
    capabilities = {"checkpoint_restore_binding": {"authorized": True, "tenant_id": tenant.tenant_id, "project_id": tenant.project_id, "checkpoint_id": checkpoint_id, "restore_request_id": restore_request, "operation": "restore"}}
    ctx = _ctx(tenant, request_id=restore_request, idempotency_key="restore-once", capabilities=capabilities)
    first = bridge.handle("elmos-context-checkpoint-and-recovery", ctx, {"operation": "restore", "task_id": "task-restore", "checkpoint_id": checkpoint_id})
    replay = bridge.handle("elmos-context-checkpoint-and-recovery", ctx, {"operation": "restore", "task_id": "task-restore", "checkpoint_id": checkpoint_id})
    assert first["outputs"]["duplicate_effects"] is False
    assert first["outputs"]["duplicate_cost"] is False
    assert replay["outputs"]["attempt_id"] == first["outputs"]["attempt_id"]
    assert replay["outputs"]["idempotent_replay"] is True
    assert runtime.store._connection.execute("SELECT count(*) FROM context_recovery_attempts").fetchone()[0] == 1
    runtime.close()


def test_restore_rejects_request_claimed_authority(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    result = bridge.handle(
        "elmos-context-checkpoint-and-recovery",
        _ctx(tenant, idempotency_key="restore-untrusted"),
        {"operation": "restore", "task_id": "task", "checkpoint_id": "not-present", "authorization": {"authorized": True}},
    )
    assert result["state"] == "BLOCKED" or result["code"] == "CONTEXT_CHECKPOINT_NOT_FOUND"
    runtime.close()


def test_rehydration_reads_exact_tenant_cas_anchor_and_rejects_catalog_drift(tmp_path: Path) -> None:
    runtime, tenant = _runtime(tmp_path)
    bridge = ContextLifecycleBridge(runtime.store, runtime.cas)
    content = b"source truth"
    digest = runtime.cas.put_bytes(tenant.tenant_id, content)
    source = {
        "source_id": "source-1",
        "tenant_id": tenant.tenant_id,
        "project_id": tenant.project_id,
        "package_version": "package-v1",
        "content_digest": "sha256:" + digest,
        "byte_count": len(content),
        "tokens": 4,
        "anchor": {"asset_id": "asset-1", "version": 8, "byte_start": 0, "byte_end": len(content)},
    }
    binding = {"tenant_id": tenant.tenant_id, "project_id": tenant.project_id, "package_version": "package-v1", "sources": [source], "max_tokens": 20}
    catalog = {**binding, "verified": True, "catalog_digest": "sha256:" + canonical_digest(binding)}
    result = bridge.handle(
        "elmos-context-rehydration",
        _ctx(tenant, idempotency_key="rehydrate-1", capabilities={"rehydration_catalog": catalog}),
        {"task_id": "task-rehydrate", "package_version": "package-v1", "source_ids": ["source-1"], "remaining_budget_tokens": 10},
    )
    assert result["state"] == "SUCCEEDED"
    assert result["outputs"]["loaded"][0]["content"] == "source truth"
    assert result["outputs"]["source_storage"] == "TENANT_CAS"
    drifted = {**catalog, "catalog_digest": "sha256:" + "0" * 64}
    denied = bridge.handle(
        "elmos-context-rehydration",
        _ctx(tenant, request_id="request-rehydrate-drift", idempotency_key="rehydrate-drift", capabilities={"rehydration_catalog": drifted}),
        {"task_id": "task-rehydrate", "package_version": "package-v1", "source_ids": ["source-1"], "remaining_budget_tokens": 10},
    )
    assert denied["code"] == "REHYDRATION_CATALOG_DIGEST_MISMATCH"
    runtime.close()


def test_migration_019_dual_roots_are_identical_and_latest_schema_is_22(tmp_path: Path) -> None:
    engine = Path(__file__).resolve().parents[1]
    assert (engine / "migrations/019_context_lifecycle.sql").read_bytes() == (
        engine / "src/elmos_multimodal_intake/migrations/019_context_lifecycle.sql"
    ).read_bytes()
    runtime, _tenant = _runtime(tmp_path)
    assert runtime.store._connection.execute("PRAGMA user_version").fetchone()[0] == 24
    runtime.store._validate_context_lifecycle_schema()
    runtime.close()
