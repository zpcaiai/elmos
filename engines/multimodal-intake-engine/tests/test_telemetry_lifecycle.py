from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake import create_runtime
from elmos_multimodal_intake.canonical import canonical_digest
from elmos_multimodal_intake.errors import AuthorizationError, ConflictError
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.observability import estimate_processing_cost_eta
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.telemetry_lifecycle import (
    COST_SKILL,
    OBSERVABILITY_SKILL,
    TelemetryLifecycleBridge,
)


def json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def runtime_context(
    *,
    policy: dict[str, Any],
    capabilities: dict[str, Any] | None = None,
    tenant_id: str = "tenant-a",
    project_id: str = "project-a",
    actor_id: str = "actor-a",
    idempotency_key: str = "telemetry-attempt-0001",
) -> RuntimeContext:
    return RuntimeContext(
        tenant_id=tenant_id,
        project_id=project_id,
        actor_id=actor_id,
        request_id="request-telemetry-0001",
        trace_id="trace-telemetry-0001",
        idempotency_key=idempotency_key,
        policy=policy,
        capabilities=capabilities or {},
    )


def estimate_payload() -> dict[str, Any]:
    return {
        "operation": "estimate",
        "stages": [
            {
                "task_id": "task-a",
                "asset_id": "asset-a",
                "stage_id": "ocr-a",
                "stage": "ocr",
                "provider": "provider-a",
                "file_type": "image/png",
                "progress": 0.5,
                "elapsed_machine_seconds": 4,
                "declared_upper_bound_seconds": 12,
                "quantity": "2",
                "unit": "page",
                "depends_on": [],
            }
        ],
        "history": [],
        "prices": [
            {
                "provider": "provider-a",
                "unit": "page",
                "price_per_unit": "0.125",
                "currency": "USD",
            }
        ],
        "currency": "USD",
    }


def estimate_policy(payload: dict[str, Any], *, reconciled: bool = False) -> dict[str, Any]:
    return {
        "observability": {
            "history_digest": json_digest(payload["history"]),
            "prices_digest": json_digest(payload["prices"]),
            "calibration_version": "calibration-v1",
            "default_currency": "USD",
            "provider_actuals_reconciled": reconciled,
        }
    }


def create_bridge(tmp_path: Path) -> tuple[Any, TelemetryLifecycleBridge]:
    runtime = create_runtime(tmp_path / "intake.sqlite3", tmp_path / "cas")
    runtime.store.bootstrap_project(TenantContext("tenant-a", "project-a", "actor-a"))
    return runtime, TelemetryLifecycleBridge(runtime.store)


def test_estimate_is_durable_idempotent_and_actuals_remain_separate(tmp_path: Path) -> None:
    runtime, bridge = create_bridge(tmp_path)
    try:
        payload = estimate_payload()
        ctx = runtime_context(policy=estimate_policy(payload))
        first = bridge.handle(COST_SKILL, ctx, payload)
        replay = bridge.handle(COST_SKILL, ctx, payload)

        assert first == replay
        assert first["state"] == "PARTIAL"
        assert first["code"] == "PROCESSING_COST_ESTIMATE_RECORDED_ACTUALS_PENDING"
        assert first["outputs"]["ledger"] == {
            "schema_version": "multimodal-cost-ledger-v1",
            "subject_kind": "TASK",
            "subject_id": "task-a",
            "estimate_sequence": 1,
            "persistence": "DURABLE",
            "actuals_state": "PENDING",
            "estimated_and_actual_separated": True,
            "machine_wall_clock_only": True,
        }
        with runtime.store.read_transaction() as connection:
            assert connection.execute("SELECT count(*) FROM multimodal_cost_estimates").fetchone()[0] == 1
            line = connection.execute("SELECT * FROM multimodal_cost_line_items").fetchone()
            assert line["asset_id"] == "asset-a"
            assert line["estimated_cost"] == "0.250000"
            assert line["actual_cost"] is None
    finally:
        runtime.close()


def test_estimate_idempotency_drift_is_rejected(tmp_path: Path) -> None:
    runtime, bridge = create_bridge(tmp_path)
    try:
        payload = estimate_payload()
        ctx = runtime_context(policy=estimate_policy(payload))
        bridge.handle(COST_SKILL, ctx, payload)
        changed = estimate_payload()
        changed["stages"][0]["quantity"] = "3"
        with pytest.raises(ConflictError, match="COST_ESTIMATE_IDEMPOTENCY_CONFLICT"):
            bridge.handle(COST_SKILL, ctx, changed)
    finally:
        runtime.close()


def test_reconciled_actuals_require_exact_independent_receipt(tmp_path: Path) -> None:
    runtime, bridge = create_bridge(tmp_path)
    try:
        payload = estimate_payload()
        policy = estimate_policy(payload, reconciled=True)
        domain = estimate_processing_cost_eta(
            {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "trace_id": "trace-telemetry-0001",
                "inputs": {key: value for key, value in payload.items() if key != "operation"},
                "policy": policy,
                "capabilities": {},
            }
        )
        estimate_digest = canonical_digest(domain["outputs"])
        receipt = {
            "verified": True,
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "subject_kind": "TASK",
            "subject_id": "task-a",
            "estimate_digest": f"sha256:{estimate_digest}",
            "evidence_digest": "sha256:" + "a" * 64,
            "evidence_byte_count": 512,
        }
        result = bridge.handle(
            COST_SKILL,
            runtime_context(
                policy=policy,
                capabilities={"verified_provider_actuals_receipt": receipt},
                idempotency_key="telemetry-actuals-0001",
            ),
            payload,
        )
        assert result["state"] == "SUCCEEDED"
        assert result["outputs"]["ledger"]["actuals_state"] == "RECONCILED"
    finally:
        runtime.close()


def test_observability_persists_only_redacted_events_and_exact_replay(tmp_path: Path) -> None:
    runtime, bridge = create_bridge(tmp_path)
    try:
        policy = {
            "observability": {
                "required_stages": ["upload"],
                "label_cardinality_limit": 100,
                "policy_version": "telemetry-v1",
            }
        }
        payload = {
            "operation": "observe",
            "trace_id": "trace-telemetry-0001",
            "events": [
                {
                    "job_id": "job-a",
                    "event_id": "event-a",
                    "event_type": "stage.progress",
                    "labels": {
                        "stage": "upload",
                        "provider": "local",
                        "file_type": "application/pdf",
                        "status": "running",
                    },
                    "attributes": {"message": "private source prose", "progress": 0.5},
                }
            ],
        }
        ctx = runtime_context(policy=policy, idempotency_key="telemetry-trace-0001")
        first = bridge.handle(OBSERVABILITY_SKILL, ctx, payload)
        replay = bridge.handle(OBSERVABILITY_SKILL, ctx, payload)
        assert first == replay
        assert first["state"] == "SUCCEEDED"
        assert first["outputs"]["events"][0]["attributes"]["message"] == "[REDACTED]"
        assert first["outputs"]["ledger"]["raw_content_persisted"] is False
        with runtime.store.read_transaction() as connection:
            row = connection.execute("SELECT * FROM multimodal_telemetry_events").fetchone()
            assert "private source prose" not in row["event_json"]
            assert "REDACTED" in row["event_json"]
    finally:
        runtime.close()


def test_telemetry_is_tenant_project_scoped_and_immutable(tmp_path: Path) -> None:
    runtime, bridge = create_bridge(tmp_path)
    try:
        payload = estimate_payload()
        bridge.handle(COST_SKILL, runtime_context(policy=estimate_policy(payload)), payload)
        with pytest.raises(AuthorizationError):
            bridge.handle(
                COST_SKILL,
                runtime_context(
                    policy=estimate_policy(payload),
                    tenant_id="tenant-b",
                    project_id="project-b",
                    actor_id="actor-b",
                ),
                payload,
            )
        with pytest.raises(sqlite3.IntegrityError, match="cost estimate immutable"):
            with runtime.store.transaction() as connection:
                connection.execute(
                    "UPDATE multimodal_cost_estimates SET result_code='TAMPERED'"
                )
    finally:
        runtime.close()
