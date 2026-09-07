from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from elmos_multimodal_intake.canonical import canonical_digest
from elmos_multimodal_intake.errors import AuthorizationError, ConflictError, NotFoundError
from elmos_multimodal_intake.governance import GovernanceDeletionBridge, apply_retention_governance
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.store import IntakeStore


def sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def scoped_object(*, held: bool = False, not_before: str | None = None) -> dict[str, object]:
    return {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "object_id": "asset-a-derived-index",
        "store": "search-index",
        "object_version": "version-7",
        "object_digest": sha("immutable-object-bytes"),
        "byte_count": 23,
        "retention_hold": held,
        "backup_delete_not_before": not_before
        or (datetime.now(UTC) - timedelta(seconds=5)).replace(microsecond=0).isoformat(),
    }


def inventory(objects: list[dict[str, object]]) -> dict[str, object]:
    body = {
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "version": "inventory-v7",
        "complete": True,
        "objects": objects,
    }
    return {**body, "inventory_digest": "sha256:" + canonical_digest(body)}


def bridge_context(objects: list[dict[str, object]]) -> RuntimeContext:
    return RuntimeContext(
        tenant_id="tenant-a",
        project_id="project-a",
        actor_id="user:owner",
        request_id="request-a",
        trace_id="trace-a",
        idempotency_key="delete-request-a",
        policy={
            "retention": {
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "version": "retention-v3",
                "allowed_actions": ["delete", "evaluate", "export"],
                "retention_days": 30,
            }
        },
        capabilities={"governance_inventory": inventory(objects)},
    )


def test_host_inventory_deleted_flag_cannot_manufacture_proof() -> None:
    raw = scoped_object()
    raw["deletion_state"] = "DELETED_VERIFIED"
    raw["deletion_evidence_digest"] = sha("arbitrary-host-flag")
    capability = inventory([raw])
    result = apply_retention_governance(
        {
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "actor_id": "user:owner",
            "inputs": {"action": "delete"},
            "policy": {
                "retention": {
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "version": "retention-v3",
                    "allowed_actions": ["delete"],
                }
            },
            "capabilities": {"governance_inventory": capability},
        }
    )
    assert result["state"] == "BLOCKED"
    assert result["code"] == "DURABLE_DELETION_WORKFLOW_REQUIRED"
    assert result["outputs"]["host_deletion_flags_accepted_as_proof"] is False


def test_durable_delete_requires_separate_exact_worker_and_verifier_receipts(tmp_path) -> None:
    worker_capability = object()
    verifier_capability = object()
    store = IntakeStore(
        tmp_path / "intake.sqlite3",
        deletion_worker_capability=worker_capability,
        deletion_verifier_capability=verifier_capability,
    )
    owner = TenantContext("tenant-a", "project-a", "user:owner")
    store.bootstrap_project(owner)
    objects = [scoped_object()]
    bridge = GovernanceDeletionBridge(store)
    prepared = bridge.handle(
        bridge.SKILL,
        bridge_context(objects),
        {
            "operation": "delete",
            "idempotency_key": "delete-request-a",
            "trace_id": "trace-a",
        },
    )
    assert prepared["state"] == "BLOCKED"
    assert prepared["code"] == "DELETION_PROPAGATION_NOT_RUN"
    assert prepared["outputs"]["state"] == "PENDING"
    job_id = prepared["outputs"]["job_id"]

    with pytest.raises(AuthorizationError, match="GOVERNANCE_DELETION_WORKER_UNAUTHORIZED"):
        store.claim_governance_deletion_command(
            owner, job_id=job_id, claim_token="claim-a", capability=object()
        )

    claimed = store.claim_governance_deletion_command(
        owner, job_id=job_id, claim_token="claim-a", capability=worker_capability
    )
    replayed_claim = store.claim_governance_deletion_command(
        owner, job_id=job_id, claim_token="claim-a", capability=worker_capability
    )
    assert replayed_claim == claimed
    command = claimed["command"]
    unknown = store.record_governance_deletion_execution(
        owner,
        command_id=command["command_id"],
        claim_token=claimed["claim_token"],
        executor_id="workload:store-deleter",
        disposition="DELETED",
        observed_object_digest=command["object_digest"],
        deleted_byte_count=command["byte_count"],
        provider_evidence_digest=sha("provider-native-delete-receipt"),
        provider_evidence_byte_count=187,
        capability=worker_capability,
    )
    assert unknown["state"] == "UNKNOWN"
    assert unknown["proof"] is None
    assert unknown["commands"][0]["state"] == "UNKNOWN"
    with pytest.raises(ConflictError, match="GOVERNANCE_DELETION_EXECUTION_REPLAY_CONFLICT"):
        store.record_governance_deletion_execution(
            owner,
            command_id=command["command_id"],
            claim_token=claimed["claim_token"],
            executor_id="workload:store-deleter",
            disposition="DELETED",
            observed_object_digest=command["object_digest"],
            deleted_byte_count=command["byte_count"],
            provider_evidence_digest=sha("different-provider-receipt"),
            provider_evidence_byte_count=187,
            capability=worker_capability,
        )

    with pytest.raises(
        AuthorizationError, match="GOVERNANCE_DELETION_INDEPENDENT_VERIFIER_REQUIRED"
    ):
        store.verify_governance_deletion_command(
            owner,
            command_id=command["command_id"],
            verifier_id="workload:store-deleter",
            observed_absent=True,
            verification_evidence_digest=sha("independent-head-check"),
            verification_evidence_byte_count=91,
            capability=verifier_capability,
        )

    completed = store.verify_governance_deletion_command(
        owner,
        command_id=command["command_id"],
        verifier_id="workload:deletion-verifier",
        observed_absent=True,
        verification_evidence_digest=sha("independent-head-check"),
        verification_evidence_byte_count=91,
        capability=verifier_capability,
    )
    assert completed["state"] == "COMPLETED"
    assert completed["proof"]["verified_commands"][0] == {
        "command_id": command["command_id"],
        "command_digest": command["command_digest"],
        "execution_receipt_digest": completed["commands"][0]["execution_receipt_digest"],
        "verification_receipt_digest": completed["commands"][0]["verification_receipt_digest"],
    }
    assert completed["proof_digest"].startswith("sha256:")
    with pytest.raises(ConflictError, match="GOVERNANCE_DELETION_VERIFICATION_REPLAY_CONFLICT"):
        store.verify_governance_deletion_command(
            owner,
            command_id=command["command_id"],
            verifier_id="workload:deletion-verifier",
            observed_absent=True,
            verification_evidence_digest=sha("different-independent-check"),
            verification_evidence_byte_count=91,
            capability=verifier_capability,
        )

    foreign = TenantContext("tenant-b", "project-b", "user:owner")
    store.bootstrap_project(foreign)
    with pytest.raises(NotFoundError, match="GOVERNANCE_DELETION_JOB_NOT_FOUND"):
        store.governance_deletion_status(foreign, job_id=job_id)

    audit = store._connection.execute(
        "SELECT action,event_digest FROM governance_deletion_audit ORDER BY occurred_at,audit_id"
    ).fetchall()
    assert {row["action"] for row in audit} == {
        "DELETE_REQUESTED", "COMMAND_CLAIMED", "EXECUTION_RECORDED_UNKNOWN",
        "COMMAND_VERIFIED", "DELETION_COMPLETED",
    }
    assert all(len(row["event_digest"]) == 64 for row in audit)
    store.close()

    reopened = IntakeStore(tmp_path / "intake.sqlite3")
    persisted = reopened.governance_deletion_status(owner, job_id=job_id)
    assert persisted["state"] == "COMPLETED"
    assert persisted["proof_digest"] == completed["proof_digest"]
    reopened.close()


def test_legal_hold_backup_lag_and_idempotency_fail_closed(tmp_path) -> None:
    worker_capability = object()
    verifier_capability = object()
    store = IntakeStore(
        tmp_path / "intake.sqlite3",
        deletion_worker_capability=worker_capability,
        deletion_verifier_capability=verifier_capability,
    )
    owner = TenantContext("tenant-a", "project-a", "user:owner")
    store.bootstrap_project(owner)

    held = store.prepare_governance_deletion(
        owner,
        objects=[scoped_object(held=True)],
        policy_version="retention-v3",
        inventory_version="inventory-v7",
        inventory_digest=sha("held-inventory"),
        idempotency_key="held-delete",
    )
    assert held["state"] == "BLOCKED"
    with pytest.raises(ConflictError, match="GOVERNANCE_DELETION_LEGAL_HOLD_ACTIVE"):
        store.claim_governance_deletion_command(
            owner, job_id=held["job_id"], claim_token="claim-held", capability=worker_capability
        )

    future = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0).isoformat()
    delayed = store.prepare_governance_deletion(
        owner,
        objects=[scoped_object(not_before=future)],
        policy_version="retention-v3",
        inventory_version="inventory-v8",
        inventory_digest=sha("backup-inventory"),
        idempotency_key="backup-delete",
    )
    with pytest.raises(ConflictError, match="GOVERNANCE_DELETION_BACKUP_LAG_ACTIVE"):
        store.claim_governance_deletion_command(
            owner, job_id=delayed["job_id"], claim_token="claim-delayed", capability=worker_capability
        )

    with pytest.raises(ConflictError, match="GOVERNANCE_DELETION_IDEMPOTENCY_CONFLICT"):
        store.prepare_governance_deletion(
            owner,
            objects=[scoped_object(held=True)],
            policy_version="retention-v3",
            inventory_version="inventory-v8",
            inventory_digest=sha("different"),
            idempotency_key="backup-delete",
        )
    store.close()


def test_governance_deletion_migration_is_dual_root_and_version_18(tmp_path) -> None:
    engine_root = Path(__file__).resolve().parents[1]
    source = engine_root / "migrations" / "018_governance_deletion_workflow.sql"
    packaged = engine_root / "src/elmos_multimodal_intake/migrations/018_governance_deletion_workflow.sql"
    assert source.read_bytes() == packaged.read_bytes()
    connection = sqlite3.connect(tmp_path / "migration.sqlite3")
    connection.executescript(source.read_text())
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 18
    connection.close()
