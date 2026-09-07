from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake.canonical import canonical_digest
from elmos_multimodal_intake.content import content_contract_digest, content_contract_json
from elmos_multimodal_intake.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
    ValidationError,
)
from elmos_multimodal_intake.human_review import HumanReviewCorrectionBridge
from elmos_multimodal_intake.human_review_workflow import (
    HumanReviewWorkflow,
    human_review_client_value_digest,
)
from elmos_multimodal_intake.models import AssetStatus, TenantContext
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.store import IntakeStore


def _request_digest(label: str, value: Any = None) -> str:
    return canonical_digest({"label": label, "value": value})


def _ready_asset(store: IntakeStore, context: TenantContext):
    store.bootstrap_project(context)
    session = store.create_session(
        context,
        idempotency_key="workflow-session-0001",
        requested_role="PRIMARY",
    )
    content = b"trusted review workflow source\n"
    digest = hashlib.sha256(content).hexdigest()
    asset, upload = store.create_upload(
        context,
        session_id=session.session_id,
        display_name="review/workflow-source.txt",
        declared_media_type="text/plain",
        expected_size=len(content),
        expected_sha256=digest,
        part_size=len(content),
        idempotency_key="workflow-upload-0001",
        request_digest=_request_digest("workflow-upload", digest),
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    store.record_part(
        context,
        upload.upload_id,
        part_number=0,
        idempotency_key="workflow-part-0001",
        byte_offset=0,
        byte_size=len(content),
        sha256=digest,
        cas_digest=digest,
    )
    uploaded = store.complete_upload(
        context,
        upload.upload_id,
        commit_idempotency_key="workflow-commit-0001",
        digest=digest,
        byte_size=len(content),
    )
    return store.set_asset_result(
        context,
        asset.asset_id,
        status=AssetStatus.READY,
        expected_version=uploaded.version,
    )


@pytest.fixture
def workflow_fixture(tmp_path: Path):
    store = IntakeStore(tmp_path / "human-review-workflow.sqlite3")
    owner = TenantContext("tenant-a", "project-a", "review-owner")
    asset = _ready_asset(store, owner)
    workflow = HumanReviewWorkflow(store)
    source_token = "trusted-source-producer-token-0001"
    source_capability = workflow.register_source_producer_capability(
        owner,
        producer_id=owner.actor_id,
        capability_token=source_token,
        source_kinds=[
            "CONTENT_BLOCK",
            "SOURCE_ANCHOR",
            "REQUIREMENT",
            "CONFLICT",
            "TRUSTED_DERIVATION",
            "WHOLE_ASSET",
        ],
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        idempotency_key="workflow-source-producer-register-0001",
        request_digest=_request_digest("workflow-source-producer-register-0001"),
    )["capability"]["capability_id"]
    try:
        yield store, workflow, owner, asset, source_capability, source_token
    finally:
        store.close()


def _enqueue(
    workflow: HumanReviewWorkflow,
    context: TenantContext,
    asset_id: str,
    *,
    ordinal: int,
    target_kind: str = "TEXT",
    target: dict[str, Any] | None = None,
    original_value: Any = "machine value",
    confidence: float = 0.1,
    source_capability_id: str,
    source_capability_token: str,
    digest_only: bool = False,
) -> dict[str, Any]:
    safe_target = target or {"path": f"blocks/{ordinal}/text"}
    with workflow._store._lock:
        asset_row = workflow._store._scoped_asset(
            workflow._store._connection, context, asset_id
        )
    source_key = f"workflow-source-register-{ordinal:04d}"
    source_fact_digest = canonical_digest(
        {
            "asset_id": asset_id,
            "asset_version": int(asset_row["version"]),
            "target_kind": target_kind,
            "target": safe_target,
            "original_value": original_value,
            "confidence": confidence,
        }
    )
    registered = workflow.register_source_snapshot(
        context,
        asset_id=asset_id,
        expected_asset_version=int(asset_row["version"]),
        target_kind=target_kind,
        target=safe_target,
        original_value=original_value,
        confidence=confidence,
        provenance={
            "schema_version": "human-review-source-provenance-v1",
            "source_kind": "TRUSTED_DERIVATION",
            "source_id": f"test-source-{ordinal}",
            "source_digest": f"sha256:{source_fact_digest}",
            "producer_version": "test-source-producer-v1",
        },
        capability_id=source_capability_id,
        capability_token=source_capability_token,
        idempotency_key=source_key,
        request_digest=_request_digest(source_key, source_fact_digest),
    )
    key = f"workflow-enqueue-{ordinal:04d}"
    return workflow.enqueue_review_task(
        context,
        asset_id=asset_id,
        expected_asset_version=int(asset_row["version"]),
        target_kind=target_kind,
        target_digest=registered["head"]["target_digest"],
        expected_head_version=registered["head"]["version"],
        expected_snapshot_id=registered["snapshot"]["snapshot_id"],
        expected_snapshot_digest=registered["snapshot"]["snapshot_digest"],
        expected_head_value_digest=registered["head"]["current_value_digest"],
        original_value_digest=(
            f"sha256:{human_review_client_value_digest(original_value)}"
        ),
        reason="low confidence extraction",
        idempotency_key=key,
        request_digest=_request_digest(key),
    )


def _source_bound_args(source_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_digest": source_ref["target_digest"],
        "expected_head_version": source_ref["head_version"],
        "expected_snapshot_id": source_ref["snapshot_id"],
        "expected_snapshot_digest": source_ref["snapshot_digest"],
        "expected_head_value_digest": source_ref["head_value_digest"],
        "original_value_digest": source_ref["original_value_client_digest"],
    }


def _claim_and_edit(
    workflow: HumanReviewWorkflow,
    context: TenantContext,
    task: dict[str, Any],
    *,
    ordinal: int,
    corrected_value: Any = "verified value",
) -> tuple[dict[str, Any], str]:
    token = f"review-claim-token-{ordinal:04d}"
    claim_key = f"workflow-claim-{ordinal:04d}"
    claimed = workflow.claim_review_task(
        context,
        task_id=task["task_id"],
        expected_version=task["version"],
        claim_token=token,
        lease_seconds=600,
        idempotency_key=claim_key,
        request_digest=_request_digest(claim_key),
    )["task"]
    edit_key = f"workflow-edit-{ordinal:04d}"
    edited = workflow.edit_review_task(
        context,
        task_id=task["task_id"],
        expected_version=claimed["version"],
        expected_correction_version=claimed["current_correction_version"],
        claim_token=token,
        claim_fence=claimed["claim_fence"],
        corrected_value=corrected_value,
        reason="reviewer verified source",
        idempotency_key=edit_key,
        request_digest=_request_digest(edit_key),
    )
    return edited, token


def _approve(
    workflow: HumanReviewWorkflow,
    context: TenantContext,
    edited: dict[str, Any],
    token: str,
    *,
    ordinal: int,
) -> dict[str, Any]:
    task = edited["task"]
    key = f"workflow-approve-{ordinal:04d}"
    return workflow.decide_review_task(
        context,
        task_id=task["task_id"],
        action="APPROVE",
        expected_version=task["version"],
        claim_token=token,
        claim_fence=task["claim_fence"],
        reason="approved by accountable reviewer",
        idempotency_key=key,
        request_digest=_request_digest(key),
    )


def _register_worker(
    workflow: HumanReviewWorkflow,
    owner: TenantContext,
    *,
    ordinal: int,
) -> tuple[TenantContext, str, str]:
    worker = TenantContext(owner.tenant_id, owner.project_id, f"review-worker-{ordinal}")
    token = f"worker-capability-token-{ordinal:04d}"
    key = f"workflow-worker-register-{ordinal:04d}"
    registered = workflow.register_worker_capability(
        owner,
        worker_id=worker.actor_id,
        capability_token=token,
        actions=["claim", "complete", "dispatch", "reconcile"],
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        idempotency_key=key,
        request_digest=_request_digest(key),
    )
    return worker, registered["capability"]["capability_id"], token


def _succeed_propagations(
    workflow: HumanReviewWorkflow,
    worker: TenantContext,
    capability_id: str,
    capability_token: str,
    propagations: list[dict[str, Any]],
    *,
    ordinal: int,
) -> dict[str, Any] | None:
    effective = None
    for position, propagation in enumerate(propagations):
        suffix = f"{ordinal:04d}-{position:02d}"
        owner_token = f"propagation-owner-token-{suffix}"
        claim = workflow.claim_propagation(
            worker,
            propagation_id=propagation["propagation_id"],
            capability_id=capability_id,
            capability_token=capability_token,
            owner_token=owner_token,
            lease_seconds=600,
            idempotency_key=f"propagation-claim-{suffix}",
            request_digest=_request_digest(f"propagation-claim-{suffix}"),
        )["propagation"]
        workflow.mark_propagation_dispatched(
            worker,
            propagation_id=propagation["propagation_id"],
            capability_id=capability_id,
            capability_token=capability_token,
            owner_token=owner_token,
            claim_fence=claim["claim_fence"],
            idempotency_key=f"propagation-dispatch-{suffix}",
            request_digest=_request_digest(f"propagation-dispatch-{suffix}"),
        )
        completed = workflow.complete_propagation(
            worker,
            propagation_id=propagation["propagation_id"],
            capability_id=capability_id,
            capability_token=capability_token,
            owner_token=owner_token,
            claim_fence=claim["claim_fence"],
            outcome="SUCCEEDED",
            result={"receipt": f"verified-{suffix}"},
            failure_code=None,
            idempotency_key=f"propagation-complete-{suffix}",
            request_digest=_request_digest(f"propagation-complete-{suffix}"),
        )
        if completed["effective"] is not None:
            effective = completed["effective"]
    return effective


def test_queue_filters_paginates_and_enforces_exact_target_and_scope(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    first = _enqueue(
        workflow, owner, asset.asset_id, ordinal=1, confidence=0.1,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )
    second = _enqueue(
        workflow, owner, asset.asset_id, ordinal=2, confidence=0.2,
        source_capability_id=source_capability,
        source_capability_token=source_token,
        digest_only=True,
    )
    _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=3,
        target_kind="SPEAKER",
        target={"segment_id": "segment-3"},
        confidence=0.8,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )

    page_one = workflow.list_review_tasks(
        owner,
        kinds=["TEXT"],
        states=["QUEUED"],
        confidence_lte=0.25,
        limit=1,
    )
    assert page_one["total"] == 2
    assert [item["task_id"] for item in page_one["tasks"]] == [
        first["task"]["task_id"]
    ]
    assert set(page_one["tasks"][0]) == {
        "schema_version",
        "task_id",
        "asset_id",
        "target_kind",
        "source_digest",
        "confidence",
        "reason",
        "state",
        "current_correction_version",
        "current_correction_digest",
        "effective_version",
        "effective_digest",
        "claim_actor_id",
        "claim_fence",
        "claim_expires_at",
        "version",
        "created_at",
        "updated_at",
        "closed_at",
    }
    assert page_one["tasks"][0]["schema_version"] == "human-review-task-summary-v1"
    assert "target" not in page_one["tasks"][0]
    assert "original_value" not in page_one["tasks"][0]
    assert "source_ref" not in page_one["tasks"][0]
    assert workflow.get_review_task(
        owner, task_id=first["task"]["task_id"]
    ) == first
    assert page_one["next_cursor"] is not None
    page_two = workflow.list_review_tasks(
        owner,
        kinds=["TEXT"],
        states=["QUEUED"],
        confidence_lte=0.25,
        limit=1,
        cursor=page_one["next_cursor"],
    )
    assert [item["task_id"] for item in page_two["tasks"]] == [
        second["task"]["task_id"]
    ]
    assert page_two["next_cursor"] is None

    with pytest.raises(ValidationError) as generic_target:
        _enqueue(
            workflow,
            owner,
            asset.asset_id,
            ordinal=4,
            target={
                "asset_id": asset.asset_id,
                "relative_path": "blocks/4",
                "field": "text",
            },
            source_capability_id=source_capability,
            source_capability_token=source_token,
        )
    assert generic_target.value.code == "HUMAN_REVIEW_TARGET_INVALID"

    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """UPDATE human_review_tasks SET original_value_json='\"rewritten\"'
                    WHERE task_id=?""",
                (first["task"]["task_id"],),
            )

    store.grant_permissions(owner, "read-only-reviewer", [store.READ])
    read_only = TenantContext(owner.tenant_id, owner.project_id, "read-only-reviewer")
    with pytest.raises(AuthorizationError) as missing_review_acl:
        workflow.list_review_tasks(read_only)
    assert missing_review_acl.value.code == "INTAKE_PROJECT_ACCESS_DENIED"
    with pytest.raises(AuthorizationError) as missing_get_acl:
        workflow.get_review_task(read_only, task_id=first["task"]["task_id"])
    assert missing_get_acl.value.code == "INTAKE_PROJECT_ACCESS_DENIED"

    other = TenantContext("tenant-b", "project-b", "review-owner-b")
    store.bootstrap_project(other)
    assert workflow.list_review_tasks(other)["tasks"] == []
    with pytest.raises(NotFoundError) as cross_tenant:
        workflow.review_status(other, task_id=first["task"]["task_id"])
    assert cross_tenant.value.code == "HUMAN_REVIEW_TASK_NOT_FOUND"
    with pytest.raises(NotFoundError) as cross_tenant_get:
        workflow.get_review_task(other, task_id=first["task"]["task_id"])
    assert cross_tenant_get.value.code == "HUMAN_REVIEW_TASK_NOT_FOUND"


def test_current_correction_is_authoritative_scoped_response_loss_recovery(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=5,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    with pytest.raises(ConflictError) as absent:
        workflow.get_current_correction(owner, task_id=queued["task_id"])
    assert absent.value.code == "HUMAN_REVIEW_CURRENT_CORRECTION_NOT_AVAILABLE"

    edited, _claim_token = _claim_and_edit(
        workflow,
        owner,
        queued,
        ordinal=5,
        corrected_value={"text": "committed even if the response was lost"},
    )
    recovered = workflow.get_current_correction(owner, task_id=queued["task_id"])
    assert recovered == {"correction": edited["correction"]}
    assert set(recovered["correction"]) == {
        "correction_id",
        "tenant_id",
        "project_id",
        "task_id",
        "correction_version",
        "parent_correction_version",
        "target_kind",
        "target",
        "original_value",
        "corrected_value",
        "source_digest",
        "actor_id",
        "reason",
        "created_at",
        "correction_digest",
    }
    assert recovered["correction"]["correction_digest"] == edited["task"][
        "current_correction_digest"
    ]

    store.grant_permissions(owner, "current-correction-reader", [store.READ])
    read_only = TenantContext(owner.tenant_id, owner.project_id, "current-correction-reader")
    with pytest.raises(AuthorizationError) as missing_review_acl:
        workflow.get_current_correction(read_only, task_id=queued["task_id"])
    assert missing_review_acl.value.code == "INTAKE_PROJECT_ACCESS_DENIED"

    other = TenantContext("tenant-current-other", "project-current-other", "review-owner")
    store.bootstrap_project(other)
    with pytest.raises(NotFoundError) as cross_tenant:
        workflow.get_current_correction(other, task_id=queued["task_id"])
    assert cross_tenant.value.code == "HUMAN_REVIEW_TASK_NOT_FOUND"


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    (
        ("digest", "HUMAN_REVIEW_CORRECTION_VERSION_DRIFT"),
        ("target", "HUMAN_REVIEW_CORRECTION_VERSION_DRIFT"),
        ("original", "HUMAN_REVIEW_CORRECTION_SOURCE_DRIFT"),
        ("source", "HUMAN_REVIEW_CORRECTION_SOURCE_DRIFT"),
    ),
)
def test_current_correction_revalidates_digest_target_and_source_lineage(
    workflow_fixture,
    tamper: str,
    expected_code: str,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=6,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    edited, _claim_token = _claim_and_edit(workflow, owner, queued, ordinal=6)
    correction = dict(edited["correction"])
    correction.pop("correction_digest")
    if tamper == "target":
        correction["target"] = {"path": "blocks/tampered/text"}
    elif tamper == "original":
        correction["original_value"] = "browser-forged-original-value"
    elif tamper == "source":
        correction["source_digest"] = "sha256:" + "f" * 64
    tampered_digest = (
        "e" * 64
        if tamper == "digest"
        else content_contract_digest(correction).removeprefix("sha256:")
    )
    with store.transaction() as connection:
        if tamper != "digest":
            connection.execute("DROP TRIGGER human_review_correction_versions_no_update")
            connection.execute(
                """UPDATE human_review_correction_versions
                      SET target_json=?,original_value_json=?,
                          original_value_digest=?,source_digest=?,correction_digest=?
                    WHERE correction_id=?""",
                (
                    content_contract_json(correction["target"]),
                    content_contract_json(correction["original_value"]),
                    content_contract_digest(correction["original_value"]).removeprefix(
                        "sha256:"
                    ),
                    correction["source_digest"].removeprefix("sha256:"),
                    tampered_digest,
                    correction["correction_id"],
                ),
            )
        connection.execute(
            """UPDATE human_review_tasks SET current_correction_digest=?
                WHERE tenant_id=? AND project_id=? AND task_id=?""",
            (tampered_digest, owner.tenant_id, owner.project_id, queued["task_id"]),
        )
    with pytest.raises(IntegrityError) as corrupt:
        workflow.get_current_correction(owner, task_id=queued["task_id"])
    assert corrupt.value.code == expected_code


def test_enqueue_resolves_authoritative_source_and_rejects_echo_drift(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    missing_target = {"path": "blocks/unregistered/text"}
    with pytest.raises(ConflictError) as unresolved:
        workflow.enqueue_review_task(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind="TEXT",
            target_digest=content_contract_digest(missing_target),
            expected_head_version=1,
            expected_snapshot_id="missing-source-snapshot",
            expected_snapshot_digest="sha256:" + "0" * 64,
            expected_head_value_digest="sha256:" + "0" * 64,
            original_value_digest=(
                f"sha256:{human_review_client_value_digest('machine value')}"
            ),
            reason="must resolve from trusted producer",
            idempotency_key="workflow-enqueue-unresolvable-0001",
            request_digest=_request_digest("workflow-enqueue-unresolvable-0001"),
        )
    assert unresolved.value.code == "HUMAN_REVIEW_TARGET_UNRESOLVABLE"
    for ordinal, (target_kind, target) in enumerate(
        (
            ("REQUIREMENT", {"requirement_id": "requirement-unpublished"}),
            ("CONFLICT", {"conflict_id": "conflict-unpublished"}),
        ),
        start=1,
    ):
        with pytest.raises(ConflictError) as missing_source_producer:
            workflow.enqueue_review_task(
                owner,
                asset_id=asset.asset_id,
                expected_asset_version=asset.version,
                target_kind=target_kind,
                target_digest=content_contract_digest(target),
                expected_head_version=1,
                expected_snapshot_id="missing-domain-source-snapshot",
                expected_snapshot_digest="sha256:" + "0" * 64,
                expected_head_value_digest="sha256:" + "0" * 64,
                original_value_digest=(
                    f"sha256:{human_review_client_value_digest('browser echo is not source')}"
                ),
                reason="domain target requires a trusted producer",
                idempotency_key=f"workflow-enqueue-missing-domain-producer-{ordinal}",
                request_digest=_request_digest(
                    f"workflow-enqueue-missing-domain-producer-{ordinal}"
                ),
            )
        assert missing_source_producer.value.code == "REQUIRES_SOURCE_PRODUCER"

    queued = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=5,
        original_value={"text": "trusted machine value"},
        confidence=0.2,
        source_capability_id=source_capability,
        source_capability_token=source_token,
        digest_only=True,
    )
    assert queued["task"]["original_value"] == {"text": "trusted machine value"}
    assert queued["task"]["source_ref"] == {
        "schema_version": "human-review-source-ref-v2",
        "content_id": asset.asset_id,
        "content_version": asset.version,
        "content_digest": queued["task"]["source_ref"]["content_digest"],
        "asset_sha256": f"sha256:{asset.sha256}",
        "target_kind": "TEXT",
        "target_digest": queued["task"]["source_ref"]["target_digest"],
        "snapshot_id": queued["task"]["source_ref"]["snapshot_id"],
        "snapshot_digest": queued["task"]["source_ref"]["snapshot_digest"],
        "head_version": 1,
        "head_value_digest": (
            content_contract_digest({"text": "trusted machine value"})
        ),
        "source_digest": queued["task"]["source_ref"]["source_digest"],
        "provenance_digest": queued["task"]["source_ref"]["provenance_digest"],
        "original_value_client_digest": (
            "sha256:"
            + human_review_client_value_digest({"text": "trusted machine value"})
        ),
        "original_value_digest_contract": "sha256:rfc8785-ijson-safeint-v1",
    }
    with pytest.raises(ConflictError) as asset_version_drift:
        workflow.enqueue_review_task(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version + 1,
            target_kind="TEXT",
            reason="stale authoritative generation",
            idempotency_key="workflow-enqueue-asset-drift-0005",
            request_digest=_request_digest("workflow-enqueue-asset-drift-0005"),
            **_source_bound_args(queued["task"]["source_ref"]),
        )
    assert (
        asset_version_drift.value.code
        == "HUMAN_REVIEW_SOURCE_ASSET_VERSION_DRIFT"
    )
    with store._lock:
        source_row = store._connection.execute(
            """SELECT * FROM human_review_source_snapshots
                WHERE tenant_id=? AND project_id=? AND asset_id=?
                  AND target_kind='TEXT'""",
            (owner.tenant_id, owner.project_id, asset.asset_id),
        ).fetchone()
        source_event = store._connection.execute(
            """SELECT event_type,payload_digest FROM outbox_events
                WHERE tenant_id=? AND project_id=? AND aggregate_type=?
                  AND aggregate_id=?""",
            (
                owner.tenant_id,
                owner.project_id,
                "human_review_source_snapshot",
                source_row["snapshot_id"],
            ),
        ).fetchone()
    assert source_row["producer_actor_id"] == owner.actor_id
    assert len(source_row["request_digest"]) == 64
    assert len(source_row["snapshot_digest"]) == 64
    assert source_event["event_type"] == "human_review.source.registered"
    assert len(source_event["payload_digest"]) == 64
    with pytest.raises(ConflictError) as drift:
        workflow.enqueue_review_task(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind="TEXT",
            original_value_digest="0" * 64,
            reason="spoofed browser echo",
            idempotency_key="workflow-enqueue-drift-0005",
            request_digest=_request_digest("workflow-enqueue-drift-0005"),
            **{
                key: value
                for key, value in _source_bound_args(
                    queued["task"]["source_ref"]
                ).items()
                if key != "original_value_digest"
            },
        )
    assert drift.value.code == "HUMAN_REVIEW_SOURCE_DRIFT"

    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """UPDATE human_review_source_snapshots SET confidence=0.9
                    WHERE tenant_id=? AND project_id=? AND asset_id=?""",
                (owner.tenant_id, owner.project_id, asset.asset_id),
            )
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """DELETE FROM human_review_source_snapshots
                    WHERE tenant_id=? AND project_id=? AND asset_id=?""",
                (owner.tenant_id, owner.project_id, asset.asset_id),
            )

    other = TenantContext("tenant-other", "project-other", owner.actor_id)
    with pytest.raises(AuthorizationError) as cross_tenant_source:
        workflow.register_source_snapshot(
            other,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind="TEXT",
            target={"path": "blocks/cross-tenant/text"},
            original_value="forged",
            confidence=0.1,
            provenance={
                "schema_version": "human-review-source-provenance-v1",
                "source_kind": "TRUSTED_DERIVATION",
                "source_id": "cross-tenant-source",
                "source_digest": f"sha256:{canonical_digest('forged')}",
                "producer_version": "test-source-producer-v1",
            },
            capability_id=source_capability,
            capability_token=source_token,
            idempotency_key="workflow-source-cross-tenant-0001",
            request_digest=_request_digest("workflow-source-cross-tenant-0001"),
        )
    assert (
        cross_tenant_source.value.code
        == "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
    )

    propagation_token = "propagation-only-token-0005"
    propagation_capability = workflow.register_worker_capability(
        owner,
        worker_id=owner.actor_id,
        capability_token=propagation_token,
        actions=["claim"],
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        idempotency_key="workflow-propagation-only-register-0005",
        request_digest=_request_digest("workflow-propagation-only-register-0005"),
    )["capability"]["capability_id"]
    with pytest.raises(AuthorizationError) as propagation_cannot_produce:
        workflow.register_source_snapshot(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind="TEXT",
            target={"path": "blocks/propagation-spoof/text"},
            original_value="forged by propagation worker",
            confidence=0.1,
            provenance={
                "schema_version": "human-review-source-provenance-v1",
                "source_kind": "TRUSTED_DERIVATION",
                "source_id": "propagation-spoof-source",
                "source_digest": f"sha256:{canonical_digest('propagation-spoof')}",
                "producer_version": "not-a-source-producer-v1",
            },
            capability_id=propagation_capability,
            capability_token=propagation_token,
            idempotency_key="workflow-source-propagation-spoof-0005",
            request_digest=_request_digest("workflow-source-propagation-spoof-0005"),
        )
    assert (
        propagation_cannot_produce.value.code
        == "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
    )

    deleted = store.set_asset_result(
        owner,
        asset.asset_id,
        status=AssetStatus.DELETED,
        expected_version=asset.version,
    )
    assert deleted.status is AssetStatus.DELETED
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """DELETE FROM input_assets
                    WHERE tenant_id=? AND project_id=? AND asset_id=?""",
                (owner.tenant_id, owner.project_id, asset.asset_id),
            )
    with store._lock:
        retained_sources = store._connection.execute(
            """SELECT count(*) FROM human_review_source_snapshots
                WHERE tenant_id=? AND project_id=? AND asset_id=?""",
            (owner.tenant_id, owner.project_id, asset.asset_id),
        ).fetchone()[0]
    assert retained_sources == 1
    revoked = workflow.revoke_source_producer_capability(
        owner,
        capability_id=source_capability,
        expected_version=1,
        reason="producer credential retired",
        idempotency_key="workflow-source-producer-revoke-0005",
        request_digest=_request_digest("workflow-source-producer-revoke-0005"),
    )
    assert revoked["revoked"] is True
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """UPDATE human_review_source_producer_capabilities
                      SET revoked_at=NULL,version=version+1
                    WHERE tenant_id=? AND project_id=? AND capability_id=?""",
                (owner.tenant_id, owner.project_id, source_capability),
            )
    with pytest.raises(AuthorizationError) as revoked_producer:
        workflow.register_source_snapshot(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=deleted.version,
            target_kind="TEXT",
            target={"path": "blocks/revoked-producer/text"},
            original_value="must not persist",
            confidence=0.1,
            provenance={
                "schema_version": "human-review-source-provenance-v1",
                "source_kind": "TRUSTED_DERIVATION",
                "source_id": "revoked-source",
                "source_digest": f"sha256:{canonical_digest('revoked-source')}",
                "producer_version": "test-source-producer-v1",
            },
            capability_id=source_capability,
            capability_token=source_token,
            idempotency_key="workflow-source-revoked-0005",
            request_digest=_request_digest("workflow-source-revoked-0005"),
        )
    assert (
        revoked_producer.value.code
        == "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
    )
    store._validate_human_review_workflow_schema()


def test_client_original_value_digest_matches_canonical_strict_json_contract() -> None:
    value = {
        "\ue000": 2,
        "😀": 1,
        "numbers": {
            "fixed": 1e-6,
            "fraction": 2e-3,
            "n": 1e-7,
            "zero": -0.0,
        },
    }
    canonical_strict_json = (
        '{"numbers":{"fixed":0.000001,"fraction":0.002,"n":1e-7,"zero":0},'
        '"😀":1,"\ue000":2}'
    )
    expected = hashlib.sha256(canonical_strict_json.encode("utf-8")).hexdigest()
    assert human_review_client_value_digest(value) == expected
    assert human_review_client_value_digest(value) != content_contract_digest(value)


def test_digest_only_enqueue_keeps_client_and_internal_digests_separate(
    workflow_fixture,
) -> None:
    _store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    value = {"\ue000": 2, "😀": 1, "n": 1e-7, "zero": -0.0}
    task = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=8,
        original_value=value,
        source_capability_id=source_capability,
        source_capability_token=source_token,
        digest_only=True,
    )["task"]
    assert task["original_value"] == value
    assert task["source_ref"]["original_value_client_digest"] == (
        f"sha256:{human_review_client_value_digest(value)}"
    )
    assert task["source_ref"]["head_value_digest"] == (
            content_contract_digest(value)
    )
    assert (
        task["source_ref"]["original_value_client_digest"]
        != task["source_ref"]["head_value_digest"]
    )


def test_enqueue_receipt_binds_authoritative_asset_generation(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    target = {"path": "blocks/7/text"}
    first = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=7,
        target=target,
        original_value="same machine value",
        source_capability_id=source_capability,
        source_capability_token=source_token,
        digest_only=True,
    )
    assert first["task"]["source_ref"]["content_version"] == asset.version

    advanced = store.set_asset_result(
        owner,
        asset.asset_id,
        status=AssetStatus.READY,
        expected_version=asset.version,
    )
    source_fact_digest = canonical_digest(
        {
            "asset_id": advanced.asset_id,
            "asset_version": advanced.version,
            "target_kind": "TEXT",
            "target": target,
            "original_value": "same machine value",
            "confidence": 0.1,
        }
    )
    advanced_source = workflow.register_source_snapshot(
        owner,
        asset_id=advanced.asset_id,
        expected_asset_version=advanced.version,
        target_kind="TEXT",
        target=target,
        original_value="same machine value",
        confidence=0.1,
        provenance={
            "schema_version": "human-review-source-provenance-v1",
            "source_kind": "TRUSTED_DERIVATION",
            "source_id": "test-source-generation-7",
            "source_digest": f"sha256:{source_fact_digest}",
            "producer_version": "test-source-producer-v2",
        },
        capability_id=source_capability,
        capability_token=source_token,
        idempotency_key="workflow-source-register-generation-0007",
        request_digest=_request_digest(
            "workflow-source-register-generation-0007", source_fact_digest
        ),
    )
    advanced_source_ref = workflow.get_source_head(
        owner,
        asset_id=advanced.asset_id,
        expected_asset_version=advanced.version,
        target_kind="TEXT",
        target_digest=advanced_source["head"]["target_digest"],
        expected_head_version=advanced_source["head"]["version"],
    )["source"]["source_ref"]
    with pytest.raises(ConflictError) as stale_replay:
        workflow.enqueue_review_task(
            owner,
            asset_id=advanced.asset_id,
            expected_asset_version=advanced.version,
            target_kind="TEXT",
            reason="low confidence extraction",
            idempotency_key="workflow-enqueue-0007",
            request_digest=_request_digest("workflow-enqueue-0007"),
            **_source_bound_args(advanced_source_ref),
        )
    assert stale_replay.value.code == "HUMAN_REVIEW_IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize(
    ("ordinal", "target_kind", "target"),
    [
        (60, "TEXT", {"path": "blocks/60/text"}),
        (61, "SPEAKER", {"segment_id": "segment-61"}),
        (62, "TIME_RANGE", {"start_ms": 0, "end_ms": 1250}),
        (63, "BBOX", {"page": 1, "x": 1.5, "y": 2, "width": 3, "height": 4}),
        (64, "TABLE", {"table_id": "table-64", "row": 0, "column": 2}),
        (65, "REQUIREMENT", {"requirement_id": "requirement-65"}),
        (66, "CONFLICT", {"conflict_id": "conflict-66"}),
    ],
)
def test_authoritative_source_supports_all_exact_locators(
    workflow_fixture,
    ordinal: int,
    target_kind: str,
    target: dict[str, Any],
) -> None:
    _store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=ordinal,
        target_kind=target_kind,
        target=target,
        original_value={"ordinal": ordinal},
        source_capability_id=source_capability,
        source_capability_token=source_token,
        digest_only=True,
    )["task"]
    assert queued["target_kind"] == target_kind
    assert queued["target"] == target


def test_claim_edit_reject_reopen_uses_cas_fence_and_immutable_versions(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow, owner, asset.asset_id, ordinal=10,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    store.grant_permissions(owner, "second-reviewer", [store.REVIEW])
    second_reviewer = TenantContext(owner.tenant_id, owner.project_id, "second-reviewer")
    claim_token = "review-claim-token-0010"
    claimed = workflow.claim_review_task(
        owner,
        task_id=queued["task_id"],
        expected_version=queued["version"],
        claim_token=claim_token,
        lease_seconds=600,
        idempotency_key="workflow-claim-0010",
        request_digest=_request_digest("workflow-claim-0010"),
    )["task"]
    with pytest.raises(ConflictError) as concurrent_claim:
        workflow.claim_review_task(
            second_reviewer,
            task_id=queued["task_id"],
            expected_version=claimed["version"],
            claim_token="second-reviewer-token-0010",
            lease_seconds=600,
            idempotency_key="workflow-second-claim-0010",
            request_digest=_request_digest("workflow-second-claim-0010"),
        )
    assert concurrent_claim.value.code == "HUMAN_REVIEW_TASK_ALREADY_CLAIMED"

    edited = workflow.edit_review_task(
        owner,
        task_id=queued["task_id"],
        expected_version=claimed["version"],
        expected_correction_version=0,
        claim_token=claim_token,
        claim_fence=claimed["claim_fence"],
        corrected_value={"text": "first human correction"},
        reason="first reviewer edit",
        idempotency_key="workflow-edit-0010",
        request_digest=_request_digest("workflow-edit-0010"),
    )
    with pytest.raises(ConflictError) as stale_edit:
        workflow.edit_review_task(
            owner,
            task_id=queued["task_id"],
            expected_version=edited["task"]["version"],
            expected_correction_version=0,
            claim_token=claim_token,
            claim_fence=claimed["claim_fence"],
            corrected_value={"text": "lost update"},
            reason="must not overwrite version one",
            idempotency_key="workflow-edit-stale-0010",
            request_digest=_request_digest("workflow-edit-stale-0010"),
        )
    assert stale_edit.value.code == "HUMAN_REVIEW_CORRECTION_VERSION_CONFLICT"

    correction_id = edited["correction"]["correction_id"]
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                "UPDATE human_review_correction_versions SET reason='rewritten' WHERE correction_id=?",
                (correction_id,),
            )

    rejected = workflow.decide_review_task(
        owner,
        task_id=queued["task_id"],
        action="REJECT",
        expected_version=edited["task"]["version"],
        claim_token=claim_token,
        claim_fence=claimed["claim_fence"],
        reason="correction needs another review",
        idempotency_key="workflow-reject-0010",
        request_digest=_request_digest("workflow-reject-0010"),
    )
    assert rejected["task"]["state"] == "REJECTED"
    reopened = workflow.decide_review_task(
        owner,
        task_id=queued["task_id"],
        action="REOPEN",
        expected_version=rejected["task"]["version"],
        reason="new source evidence is available",
        idempotency_key="workflow-reopen-0010",
        request_digest=_request_digest("workflow-reopen-0010"),
    )
    assert reopened["task"]["state"] == "REOPENED"
    with pytest.raises(ConflictError) as stale_fence:
        workflow.edit_review_task(
            owner,
            task_id=queued["task_id"],
            expected_version=reopened["task"]["version"],
            expected_correction_version=1,
            claim_token=claim_token,
            claim_fence=claimed["claim_fence"],
            corrected_value={"text": "must reclaim first"},
            reason="stale lease cannot mutate",
            idempotency_key="workflow-stale-fence-0010",
            request_digest=_request_digest("workflow-stale-fence-0010"),
        )
    assert stale_fence.value.code == "HUMAN_REVIEW_CLAIM_NOT_OWNED"


def test_approve_propagates_materializes_and_revert_preserves_history(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=20,
        original_value={"text": "machine value"},
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    edited, claim_token = _claim_and_edit(
        workflow,
        owner,
        queued,
        ordinal=20,
        corrected_value={"text": "approved human value"},
    )
    approved = _approve(workflow, owner, edited, claim_token, ordinal=20)
    assert approved["task"]["state"] == "APPROVED"
    assert len(approved["propagations"]) == 4
    assert {item["channel"] for item in approved["propagations"]} == {
        "content-index",
        "requirements",
        "project-memory",
        "downstream",
    }
    assert {item["state"] for item in approved["propagations"]} == {"PENDING"}
    assert workflow.review_status(owner, task_id=queued["task_id"])["effective"][
        "state"
    ] == "NOT_RUN"

    worker, capability_id, capability_token = _register_worker(
        workflow, owner, ordinal=20
    )
    effective = _succeed_propagations(
        workflow,
        worker,
        capability_id,
        capability_token,
        approved["propagations"],
        ordinal=20,
    )
    assert effective is not None
    status = workflow.review_status(owner, task_id=queued["task_id"])
    assert status["task"]["state"] == "APPROVED"
    assert status["task"]["effective_version"] == 1
    assert status["effective"]["materialized"] is True
    assert status["effective"]["effective_value"] == {"text": "approved human value"}
    assert len(status["effective"]["channels"]) == 4
    with store._lock:
        applied_head = store._connection.execute(
            """SELECT * FROM human_review_target_heads
                WHERE tenant_id=? AND project_id=? AND asset_id=?""",
            (owner.tenant_id, owner.project_id, asset.asset_id),
        ).fetchone()
    assert applied_head is not None
    assert applied_head["direction"] == "APPLY"
    assert int(applied_head["correction_version"]) == 1
    assert int(applied_head["version"]) == 2
    assert json.loads(applied_head["current_value_json"]) == {
        "text": "approved human value"
    }

    revert = workflow.decide_review_task(
        owner,
        task_id=queued["task_id"],
        action="REVERT",
        expected_version=status["task"]["version"],
        reason="approved change must be reversed",
        idempotency_key="workflow-revert-0020",
        request_digest=_request_digest("workflow-revert-0020"),
    )
    assert revert["task"]["state"] == "REVERTING"
    assert {item["direction"] for item in revert["propagations"]} == {"REVERT"}
    reverse_effective = _succeed_propagations(
        workflow,
        worker,
        capability_id,
        capability_token,
        revert["propagations"],
        ordinal=21,
    )
    assert reverse_effective is not None
    reverted = workflow.review_status(owner, task_id=queued["task_id"])
    assert reverted["task"]["state"] == "REVERTED"
    assert reverted["task"]["effective_version"] == 0
    assert reverted["effective"]["effective_value"] == {"text": "machine value"}
    assert {item["direction"] for item in reverted["effective"]["channels"]} == {
        "REVERT"
    }
    with store._lock:
        reverted_head = store._connection.execute(
            """SELECT * FROM human_review_target_heads
                WHERE tenant_id=? AND project_id=? AND asset_id=?""",
            (owner.tenant_id, owner.project_id, asset.asset_id),
        ).fetchone()
    assert reverted_head is not None
    assert reverted_head["direction"] == "REVERT"
    assert int(reverted_head["correction_version"]) == 0
    assert int(reverted_head["version"]) == 3
    assert json.loads(reverted_head["current_value_json"]) == {
        "text": "machine value"
    }
    reservation_history = workflow.reservation_status(
        owner, task_id=queued["task_id"]
    )["reservations"]
    assert [item["state"] for item in reservation_history] == ["APPLIED", "REVERTED"]
    assert reservation_history[1]["parent_reservation_id"] == reservation_history[0][
        "reservation_id"
    ]
    assert reservation_history[1]["reserved_head_version"] == reservation_history[0][
        "materialized_head_version"
    ]
    with pytest.raises(ConflictError) as aba_drift:
        workflow.enqueue_review_task(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind="TEXT",
            reason="stale source discovery after A to B to A",
            idempotency_key="workflow-enqueue-stale-aba-0020",
            request_digest=_request_digest("workflow-enqueue-stale-aba-0020"),
            **_source_bound_args(queued["source_ref"]),
        )
    assert aba_drift.value.code == "HUMAN_REVIEW_SOURCE_HEAD_DRIFT"

    with store._lock:
        correction_count = store._connection.execute(
            "SELECT count(*) FROM human_review_correction_versions WHERE task_id=?",
            (queued["task_id"],),
        ).fetchone()[0]
        decision_count = store._connection.execute(
            "SELECT count(*) FROM human_review_decisions WHERE task_id=?",
            (queued["task_id"],),
        ).fetchone()[0]
        propagation_count = store._connection.execute(
            "SELECT count(*) FROM human_review_propagation_tasks WHERE task_id=?",
            (queued["task_id"],),
        ).fetchone()[0]
        source_snapshot_count = store._connection.execute(
            "SELECT count(*) FROM human_review_source_snapshots WHERE asset_id=?",
            (asset.asset_id,),
        ).fetchone()[0]
    assert correction_count == 1
    assert decision_count == 2
    assert propagation_count == 8
    assert source_snapshot_count == 1
    store._validate_human_review_workflow_schema()


def test_concurrent_approvals_use_target_head_cas(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    target = {"path": "blocks/25/text"}
    first = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=25,
        target=target,
        original_value="shared machine value",
        source_capability_id=source_capability,
        source_capability_token=source_token,
        digest_only=True,
    )["task"]
    second = workflow.enqueue_review_task(
        owner,
        asset_id=asset.asset_id,
        expected_asset_version=asset.version,
        target_kind="TEXT",
        reason="independent reviewer queue entry",
        idempotency_key="workflow-enqueue-concurrent-0025",
        request_digest=_request_digest("workflow-enqueue-concurrent-0025"),
        **_source_bound_args(first["source_ref"]),
    )["task"]
    first_edit, first_token = _claim_and_edit(
        workflow, owner, first, ordinal=25, corrected_value="first approved value"
    )
    second_edit, second_token = _claim_and_edit(
        workflow, owner, second, ordinal=26, corrected_value="stale approved value"
    )
    candidates = (
        (first, first_edit, first_token, 25, "first approved value"),
        (second, second_edit, second_token, 26, "stale approved value"),
    )
    start = threading.Barrier(len(candidates))

    def approve_candidate(index: int) -> tuple[str, int, Any]:
        _task, edited, token, ordinal, _corrected_value = candidates[index]
        start.wait()
        try:
            return "APPROVED", index, _approve(
                workflow, owner, edited, token, ordinal=ordinal
            )
        except ConflictError as error:
            return "BLOCKED", index, error

    with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
        attempts = tuple(executor.map(approve_candidate, range(len(candidates))))
    approved_attempts = [item for item in attempts if item[0] == "APPROVED"]
    blocked_attempts = [item for item in attempts if item[0] == "BLOCKED"]
    assert len(approved_attempts) == 1
    assert len(blocked_attempts) == 1
    _, winner_index, winner_approval = approved_attempts[0]
    _, loser_index, blocked_error = blocked_attempts[0]
    assert isinstance(winner_approval, dict)
    assert isinstance(blocked_error, ConflictError)
    assert blocked_error.code == "HUMAN_REVIEW_TARGET_HEAD_RESERVED"
    winner_task, winner_edit, winner_token, winner_ordinal, winner_value = candidates[
        winner_index
    ]
    loser_task = candidates[loser_index][0]
    winner_replay = _approve(
        workflow,
        owner,
        winner_edit,
        winner_token,
        ordinal=winner_ordinal,
    )
    assert winner_replay == winner_approval
    winner_reservations = workflow.reservation_status(
        owner, task_id=winner_task["task_id"]
    )
    assert winner_reservations["schema_version"] == (
        "human-review-target-head-reservation-status-v1"
    )
    assert len(winner_reservations["reservations"]) == 1
    reservation = winner_reservations["reservations"][0]
    assert reservation["state"] == "PROPAGATING"
    assert reservation["decision_id"] == winner_approval["decision"]["decision_id"]
    assert reservation["reservation_fence"] == first["source_ref"]["head_version"]
    with store._lock:
        loser_decisions = store._connection.execute(
            """SELECT count(*) FROM human_review_decisions
                WHERE tenant_id=? AND project_id=? AND task_id=?""",
            (owner.tenant_id, owner.project_id, loser_task["task_id"]),
        ).fetchone()[0]
        loser_propagations = store._connection.execute(
            """SELECT count(*) FROM human_review_propagation_tasks
                WHERE tenant_id=? AND project_id=? AND task_id=?""",
            (owner.tenant_id, owner.project_id, loser_task["task_id"]),
        ).fetchone()[0]
        total_reservations = store._connection.execute(
            """SELECT count(*) FROM human_review_target_head_reservations
                WHERE tenant_id=? AND project_id=?""",
            (owner.tenant_id, owner.project_id),
        ).fetchone()[0]
    assert loser_decisions == 0
    assert loser_propagations == 0
    assert total_reservations == 1
    worker, capability_id, capability_token = _register_worker(
        workflow, owner, ordinal=25
    )
    _succeed_propagations(
        workflow,
        worker,
        capability_id,
        capability_token,
        winner_approval["propagations"],
        ordinal=25,
    )
    applied_reservation = workflow.reservation_status(
        owner, task_id=winner_task["task_id"]
    )["reservations"][0]
    assert applied_reservation["state"] == "APPLIED"
    assert applied_reservation["materialized_head_version"] == 2
    with store._lock:
        head = store._connection.execute(
            """SELECT current_value_json,version FROM human_review_target_heads
                WHERE tenant_id=? AND project_id=? AND asset_id=?""",
            (owner.tenant_id, owner.project_id, asset.asset_id),
        ).fetchone()
    assert json.loads(head["current_value_json"]) == winner_value
    assert int(head["version"]) == 2


def test_expired_dispatched_claim_becomes_unknown_and_requires_reconciliation(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow, owner, asset.asset_id, ordinal=30,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    edited, claim_token = _claim_and_edit(workflow, owner, queued, ordinal=30)
    approved = _approve(workflow, owner, edited, claim_token, ordinal=30)
    propagation = approved["propagations"][0]
    worker, capability_id, capability_token = _register_worker(
        workflow, owner, ordinal=30
    )
    owner_token = "crashed-propagation-owner-0030"
    claimed = workflow.claim_propagation(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        owner_token=owner_token,
        lease_seconds=600,
        idempotency_key="propagation-claim-0030",
        request_digest=_request_digest("propagation-claim-0030"),
    )["propagation"]
    workflow.mark_propagation_dispatched(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        owner_token=owner_token,
        claim_fence=claimed["claim_fence"],
        idempotency_key="propagation-dispatch-0030",
        request_digest=_request_digest("propagation-dispatch-0030"),
    )
    with store.transaction() as connection:
        connection.execute(
            """UPDATE human_review_propagation_tasks
                  SET claim_expires_at='2000-01-01T00:00:00+00:00'
                WHERE propagation_id=?""",
            (propagation["propagation_id"],),
        )

    unknown = workflow.claim_propagation(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        owner_token="replacement-owner-token-0030",
        lease_seconds=600,
        idempotency_key="propagation-expired-claim-0030",
        request_digest=_request_digest("propagation-expired-claim-0030"),
    )["propagation"]
    assert unknown["state"] == "UNKNOWN"
    assert unknown["reconciliation_required"] is True
    assert workflow.reservation_status(
        owner, task_id=queued["task_id"]
    )["reservations"][0]["state"] == "UNKNOWN"
    with pytest.raises(ConflictError) as retry_blocked:
        workflow.claim_propagation(
            worker,
            propagation_id=propagation["propagation_id"],
            capability_id=capability_id,
            capability_token=capability_token,
            owner_token="automatic-retry-owner-0030",
            lease_seconds=600,
            idempotency_key="propagation-automatic-retry-0030",
            request_digest=_request_digest("propagation-automatic-retry-0030"),
        )
    assert retry_blocked.value.code == "HUMAN_REVIEW_PROPAGATION_RECONCILIATION_REQUIRED"
    assert retry_blocked.value.details["automatic_retry_allowed"] is False

    reconciled = workflow.reconcile_propagation(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        outcome="NOT_APPLIED",
        result={"provider_receipt": "verified-not-applied"},
        failure_code=None,
        idempotency_key="propagation-reconcile-0030",
        request_digest=_request_digest("propagation-reconcile-0030"),
    )
    assert reconciled["propagation"]["state"] == "PENDING"
    assert reconciled["propagation"]["reconciliation_required"] is False
    assert workflow.reservation_status(
        owner, task_id=queued["task_id"]
    )["reservations"][0]["state"] == "PROPAGATING"


def test_reservation_is_tenant_scoped_immutable_and_digest_bound(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    queued = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=35,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    edited, claim_token = _claim_and_edit(workflow, owner, queued, ordinal=35)
    approved = _approve(workflow, owner, edited, claim_token, ordinal=35)
    status = workflow.reservation_status(owner, task_id=queued["task_id"])
    reservation = status["reservations"][0]
    assert reservation["decision_id"] == approved["decision"]["decision_id"]
    assert reservation["binding_digest"].startswith("sha256:")

    other = TenantContext("tenant-reservation-b", "project-reservation-b", "review-owner")
    store.bootstrap_project(other)
    with pytest.raises(NotFoundError) as cross_tenant:
        workflow.reservation_status(other, task_id=queued["task_id"])
    assert cross_tenant.value.code == "HUMAN_REVIEW_TASK_NOT_FOUND"

    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """UPDATE human_review_target_head_reservations
                      SET state='APPLIED',state_version=state_version+1,
                          materialized_head_version=reserved_head_version+1,
                          updated_at='2099-01-01T00:00:00+00:00',
                          completed_at='2099-01-01T00:00:00+00:00'
                    WHERE reservation_id=?""",
                (reservation["reservation_id"],),
            )

    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction() as connection:
            connection.execute(
                """UPDATE human_review_target_head_reservations
                      SET binding_digest=? WHERE reservation_id=?""",
                ("0" * 64, reservation["reservation_id"]),
            )

    with store.transaction() as connection:
        connection.execute(
            "DROP TRIGGER human_review_target_head_reservations_identity_no_update"
        )
        connection.execute(
            """UPDATE human_review_target_head_reservations
                  SET binding_digest=? WHERE reservation_id=?""",
            ("0" * 64, reservation["reservation_id"]),
        )
    with pytest.raises(IntegrityError) as tampered:
        workflow.reservation_status(owner, task_id=queued["task_id"])
    assert tampered.value.code == "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CORRUPT"


def test_failed_reservation_remains_owned_and_blocks_other_side_effects(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    first = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=36,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    second = workflow.enqueue_review_task(
        owner,
        asset_id=asset.asset_id,
        expected_asset_version=asset.version,
        target_kind="TEXT",
        reason="same head independent review",
        idempotency_key="workflow-enqueue-failed-reservation-0036",
        request_digest=_request_digest("workflow-enqueue-failed-reservation-0036"),
        **_source_bound_args(first["source_ref"]),
    )["task"]
    first_edit, first_token = _claim_and_edit(workflow, owner, first, ordinal=36)
    second_edit, second_token = _claim_and_edit(workflow, owner, second, ordinal=37)
    approved = _approve(workflow, owner, first_edit, first_token, ordinal=36)
    worker, capability_id, capability_token = _register_worker(
        workflow, owner, ordinal=36
    )
    propagation = approved["propagations"][0]
    owner_token = "failed-reservation-owner-0036"
    claim = workflow.claim_propagation(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        owner_token=owner_token,
        lease_seconds=600,
        idempotency_key="failed-reservation-claim-0036",
        request_digest=_request_digest("failed-reservation-claim-0036"),
    )["propagation"]
    workflow.mark_propagation_dispatched(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        owner_token=owner_token,
        claim_fence=claim["claim_fence"],
        idempotency_key="failed-reservation-dispatch-0036",
        request_digest=_request_digest("failed-reservation-dispatch-0036"),
    )
    workflow.complete_propagation(
        worker,
        propagation_id=propagation["propagation_id"],
        capability_id=capability_id,
        capability_token=capability_token,
        owner_token=owner_token,
        claim_fence=claim["claim_fence"],
        outcome="FAILED",
        result={"receipt": "verified-failure"},
        failure_code="DOWNSTREAM_REJECTED",
        idempotency_key="failed-reservation-complete-0036",
        request_digest=_request_digest("failed-reservation-complete-0036"),
    )
    reservation = workflow.reservation_status(
        owner, task_id=first["task_id"]
    )["reservations"][0]
    assert reservation["state"] == "FAILED"
    assert reservation["failure_code"] == "DOWNSTREAM_REJECTED"
    with pytest.raises(ConflictError) as competing:
        _approve(workflow, owner, second_edit, second_token, ordinal=37)
    assert competing.value.code == "HUMAN_REVIEW_TARGET_HEAD_RESERVED"
    with pytest.raises(ConflictError) as further_side_effect:
        workflow.claim_propagation(
            worker,
            propagation_id=approved["propagations"][1]["propagation_id"],
            capability_id=capability_id,
            capability_token=capability_token,
            owner_token="blocked-after-failure-owner-0036",
            lease_seconds=600,
            idempotency_key="blocked-after-failure-claim-0036",
            request_digest=_request_digest("blocked-after-failure-claim-0036"),
        )
    assert further_side_effect.value.code == (
        "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_NOT_OPERATIONAL"
    )
    with store._lock:
        assert store._connection.execute(
            "SELECT count(*) FROM human_review_propagation_tasks WHERE task_id=?",
            (second["task_id"],),
        ).fetchone()[0] == 0


def _runtime_context(
    context: TenantContext,
    *,
    key: str,
    actions: list[str],
    capabilities: dict[str, Any] | None = None,
) -> RuntimeContext:
    return RuntimeContext(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        actor_id=context.actor_id,
        request_id=f"request-{key}",
        trace_id=f"trace-{key}",
        idempotency_key=key,
        policy={
            "human_review": {
                "version": "review-policy-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "allowed_actions": actions,
                "allowed_actor_ids": [context.actor_id],
            }
        },
        capabilities=capabilities or {},
    )


def test_runtime_bridge_uses_exact_browser_and_worker_envelopes(
    workflow_fixture,
) -> None:
    _store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    bridge = HumanReviewCorrectionBridge(workflow._store)
    target = {"path": "blocks/40/text"}
    original_value = "machine text"
    source_fact_digest = canonical_digest(
        {
            "asset_id": asset.asset_id,
            "asset_version": asset.version,
            "target_kind": "TEXT",
            "target": target,
            "original_value": original_value,
            "confidence": 0.15,
        }
    )
    source_key = "bridge-source-register-0040"
    source_payload = {
        "operation": "source_register",
        "content_id": asset.asset_id,
        "expected_asset_version": asset.version,
        "target_kind": "TEXT",
        "target": target,
        "original_value": original_value,
        "confidence": 0.15,
        "provenance": {
            "schema_version": "human-review-source-provenance-v1",
            "source_kind": "TRUSTED_DERIVATION",
            "source_id": "bridge-source-40",
            "source_digest": f"sha256:{source_fact_digest}",
            "producer_version": "bridge-test-producer-v1",
        },
        "idempotency_key": source_key,
        "trace_id": f"trace-{source_key}",
    }
    source_context = _runtime_context(
        owner,
        key=source_key,
        actions=[],
        capabilities={
            "human_review_source_producer": {
                "version": "human-review-source-producer-v1",
                "tenant_id": owner.tenant_id,
                "project_id": owner.project_id,
                "capability_id": source_capability,
                "token": source_token,
            }
        },
    )
    registered = bridge.handle(
        HumanReviewCorrectionBridge.SKILL, source_context, source_payload
    )
    assert registered["code"] == "HUMAN_REVIEW_SOURCE_REGISTERED"
    assert bridge.handle(
        HumanReviewCorrectionBridge.SKILL, source_context, source_payload
    ) == registered
    source_drift = dict(source_payload)
    source_drift["original_value"] = "different machine text"
    with pytest.raises(ConflictError) as producer_idempotency_drift:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL, source_context, source_drift
        )
    assert (
        producer_idempotency_drift.value.code
        == "HUMAN_REVIEW_IDEMPOTENCY_CONFLICT"
    )
    source_spoof = dict(source_payload)
    source_spoof["capability_id"] = source_capability
    with pytest.raises(ValidationError) as producer_spoof:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL, source_context, source_spoof
        )
    assert producer_spoof.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"

    list_key = "bridge-source-list-0040"
    listed_sources = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=list_key, actions=[]),
        {
            "operation": "source_list",
            "content_id": asset.asset_id,
            "expected_asset_version": asset.version,
            "kinds": ["TEXT"],
            "limit": 1,
            "cursor": None,
            "idempotency_key": list_key,
            "trace_id": f"trace-{list_key}",
        },
    )
    assert listed_sources["code"] == "HUMAN_REVIEW_SOURCES_LISTED"
    source_summary = listed_sources["outputs"]["sources"][0]
    assert "original_value" not in source_summary

    source_get_key = "bridge-source-get-0040"
    source_detail = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=source_get_key, actions=[]),
        {
            "operation": "source_get",
            "content_id": asset.asset_id,
            "expected_asset_version": asset.version,
            "target_kind": source_summary["target_kind"],
            "target_digest": source_summary["target_digest"],
            "expected_head_version": source_summary["head_version"],
            "idempotency_key": source_get_key,
            "trace_id": f"trace-{source_get_key}",
        },
    )
    assert source_detail["code"] == "HUMAN_REVIEW_SOURCE_RETRIEVED"
    source_ref = source_detail["outputs"]["source"]["source_ref"]

    key = "bridge-enqueue-0040"
    payload = {
        "operation": "enqueue",
        "content_id": asset.asset_id,
        "expected_asset_version": asset.version,
        "target_kind": "TEXT",
        "target_digest": source_ref["target_digest"],
        "expected_head_version": source_ref["head_version"],
        "expected_snapshot_id": source_ref["snapshot_id"],
        "expected_snapshot_digest": source_ref["snapshot_digest"],
        "expected_head_value_digest": source_ref["head_value_digest"],
        "original_value_digest": source_ref["original_value_client_digest"],
        "reason": "browser submits review intent",
        "idempotency_key": key,
        "trace_id": f"trace-{key}",
    }
    result = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=key, actions=["enqueue"]),
        payload,
    )
    assert result["state"] == "SUCCEEDED"
    assert result["code"] == "HUMAN_REVIEW_TASK_ENQUEUED"
    assert result["outputs"]["task"]["asset_id"] == asset.asset_id

    get_key = "bridge-get-0040"
    retrieved = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=get_key, actions=[]),
        {
            "operation": "get",
            "task_id": result["outputs"]["task"]["task_id"],
            "idempotency_key": get_key,
            "trace_id": f"trace-{get_key}",
        },
    )
    assert retrieved["code"] == "HUMAN_REVIEW_TASK_RETRIEVED"
    assert retrieved["outputs"] == result["outputs"]

    current_missing_key = "bridge-current-correction-missing-0040"
    with pytest.raises(ConflictError) as current_missing:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(owner, key=current_missing_key, actions=[]),
            {
                "operation": "current_correction",
                "task_id": result["outputs"]["task"]["task_id"],
                "idempotency_key": current_missing_key,
                "trace_id": f"trace-{current_missing_key}",
            },
        )
    assert (
        current_missing.value.code
        == "HUMAN_REVIEW_CURRENT_CORRECTION_NOT_AVAILABLE"
    )

    claim_key = "bridge-claim-0040"
    claimed = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=claim_key, actions=["claim"]),
        {
            "operation": "claim",
            "task_id": result["outputs"]["task"]["task_id"],
            "expected_version": result["outputs"]["task"]["version"],
            "claim_token": "bridge-review-claim-token-0040",
            "lease_seconds": 600,
            "idempotency_key": claim_key,
            "trace_id": f"trace-{claim_key}",
        },
    )
    edit_key = "bridge-edit-0040"
    edited = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=edit_key, actions=["edit"]),
        {
            "operation": "edit",
            "task_id": result["outputs"]["task"]["task_id"],
            "expected_version": claimed["outputs"]["task"]["version"],
            "expected_correction_version": 0,
            "claim_token": "bridge-review-claim-token-0040",
            "claim_fence": claimed["outputs"]["task"]["claim_fence"],
            "correction": {
                "value": "authoritative recovered correction",
                "reason": "recover an edit whose response was lost",
            },
            "idempotency_key": edit_key,
            "trace_id": f"trace-{edit_key}",
        },
    )
    current_key = "bridge-current-correction-0040"
    current = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=current_key, actions=[]),
        {
            "operation": "current_correction",
            "task_id": result["outputs"]["task"]["task_id"],
            "idempotency_key": current_key,
            "trace_id": f"trace-{current_key}",
        },
    )
    assert current["code"] == "HUMAN_REVIEW_CURRENT_CORRECTION_RETRIEVED"
    assert current["outputs"] == {"correction": edited["outputs"]["correction"]}

    approve_key = "bridge-approve-0040"
    approved = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=approve_key, actions=["approve"]),
        {
            "operation": "approve",
            "task_id": result["outputs"]["task"]["task_id"],
            "expected_version": edited["outputs"]["task"]["version"],
            "claim_token": "bridge-review-claim-token-0040",
            "claim_fence": edited["outputs"]["task"]["claim_fence"],
            "reason": "approve the exact source-bound correction",
            "idempotency_key": approve_key,
            "trace_id": f"trace-{approve_key}",
        },
    )
    assert approved["code"] == "HUMAN_REVIEW_CORRECTION_APPROVED"
    reservation_key = "bridge-reservation-status-0040"
    reservation_status = bridge.handle(
        HumanReviewCorrectionBridge.SKILL,
        _runtime_context(owner, key=reservation_key, actions=[]),
        {
            "operation": "reservation_status",
            "task_id": result["outputs"]["task"]["task_id"],
            "idempotency_key": reservation_key,
            "trace_id": f"trace-{reservation_key}",
        },
    )
    assert reservation_status["code"] == (
        "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATUS"
    )
    assert reservation_status["outputs"]["reservations"][0]["state"] == (
        "PROPAGATING"
    )

    current_with_extra = {
        "operation": "current_correction",
        "task_id": result["outputs"]["task"]["task_id"],
        "expected_version": edited["outputs"]["task"]["version"],
        "idempotency_key": current_key,
        "trace_id": f"trace-{current_key}",
    }
    with pytest.raises(ValidationError) as current_extra_field:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(owner, key=current_key, actions=[]),
            current_with_extra,
        )
    assert current_extra_field.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"

    ambiguous_echo = dict(payload)
    ambiguous_echo["original_value"] = original_value
    with pytest.raises(ValidationError) as ambiguous:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(owner, key=key, actions=["enqueue"]),
            ambiguous_echo,
        )
    assert ambiguous.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"

    missing_echo = dict(payload)
    missing_echo.pop("original_value_digest")
    with pytest.raises(ValidationError) as missing:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(owner, key=key, actions=["enqueue"]),
            missing_echo,
        )
    assert missing.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"

    missing_generation = dict(payload)
    missing_generation.pop("expected_asset_version")
    with pytest.raises(ValidationError) as missing_version:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(owner, key=key, actions=["enqueue"]),
            missing_generation,
        )
    assert missing_version.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"

    spoofed = dict(payload)
    spoofed["tenant_id"] = owner.tenant_id
    with pytest.raises(ValidationError) as browser_scope_spoof:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            _runtime_context(owner, key=key, actions=["enqueue"]),
            spoofed,
        )
    assert browser_scope_spoof.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"

    worker, capability_id, capability_token = _register_worker(
        workflow, owner, ordinal=40
    )
    worker_key = "bridge-worker-claim-0040"
    worker_payload = {
        "operation": "propagation_claim",
        "propagation_id": "review-propagation-does-not-exist",
        "owner_token": "bridge-owner-token-0040",
        "lease_seconds": 60,
        "idempotency_key": worker_key,
        "trace_id": f"trace-{worker_key}",
    }
    source_as_worker_context = _runtime_context(
        owner,
        key=worker_key,
        actions=[],
        capabilities={
            "human_review_propagation_worker": {
                "version": "human-review-worker-capability-v1",
                "tenant_id": owner.tenant_id,
                "project_id": owner.project_id,
                "capability_id": source_capability,
                "token": source_token,
            }
        },
    )
    with pytest.raises(AuthorizationError) as producer_cannot_propagate:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            source_as_worker_context,
            worker_payload,
        )
    assert (
        producer_cannot_propagate.value.code
        == "HUMAN_REVIEW_WORKER_CAPABILITY_DENIED"
    )
    worker_context = _runtime_context(
        worker,
        key=worker_key,
        actions=[],
        capabilities={
            "human_review_propagation_worker": {
                "version": "human-review-worker-capability-v1",
                "tenant_id": worker.tenant_id,
                "project_id": worker.project_id,
                "capability_id": capability_id,
                "token": capability_token,
            }
        },
    )
    with pytest.raises(NotFoundError):
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            worker_context,
            worker_payload,
        )
    self_reported_capability = dict(worker_payload)
    self_reported_capability["capability_id"] = capability_id
    with pytest.raises(ValidationError) as worker_spoof:
        bridge.handle(
            HumanReviewCorrectionBridge.SKILL,
            worker_context,
            self_reported_capability,
        )
    assert worker_spoof.value.code == "HUMAN_REVIEW_INPUT_FIELDS_INVALID"


def test_source_discovery_exact_pagination_scope_and_collection_drift(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture

    def register(
        ordinal: int,
        *,
        target_kind: str,
        target: dict[str, Any],
        original_value: Any,
        confidence: float,
    ) -> dict[str, Any]:
        source_fact_digest = canonical_digest(
            {
                "ordinal": ordinal,
                "asset_id": asset.asset_id,
                "asset_version": asset.version,
                "target_kind": target_kind,
                "target": target,
                "original_value": original_value,
                "confidence": confidence,
            }
        )
        key = f"workflow-source-discovery-{ordinal:04d}"
        return workflow.register_source_snapshot(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind=target_kind,
            target=target,
            original_value=original_value,
            confidence=confidence,
            provenance={
                "schema_version": "human-review-source-provenance-v1",
                "source_kind": "SOURCE_ANCHOR",
                "source_id": f"source-anchor-{ordinal}",
                "source_digest": f"sha256:{source_fact_digest}",
                "producer_version": "source-discovery-test-v1",
            },
            capability_id=source_capability,
            capability_token=source_token,
            idempotency_key=key,
            request_digest=_request_digest(key, source_fact_digest),
        )

    register(
        70,
        target_kind="TEXT",
        target={"path": "content_blocks/70/text"},
        original_value="authoritative text",
        confidence=0.4,
    )
    register(
        71,
        target_kind="BBOX",
        target={"page": 1, "x": 0.0, "y": 2.0, "width": 3.0, "height": 4.0},
        original_value={"label": "box"},
        confidence=0.8,
    )

    first = workflow.list_source_heads(
        owner,
        asset_id=asset.asset_id,
        expected_asset_version=asset.version,
        kinds=[],
        limit=1,
        cursor=None,
    )
    assert set(first) == {"sources", "next_cursor", "total"}
    assert first["total"] == 2
    assert first["next_cursor"] is not None
    summary = first["sources"][0]
    assert set(summary) == {
        "schema_version", "content_id", "content_version", "target_kind", "target",
        "target_digest", "confidence", "head_version", "head_direction",
        "head_correction_version", "original_value_client_digest",
        "original_value_digest_contract", "source_ref",
    }
    assert "original_value" not in summary
    assert set(summary["source_ref"]) == {
        "schema_version", "content_id", "content_version", "content_digest",
        "asset_sha256", "target_kind", "target_digest", "snapshot_id",
        "snapshot_digest", "head_version", "head_value_digest", "source_digest",
        "provenance_digest", "original_value_client_digest",
        "original_value_digest_contract",
    }
    with pytest.raises(ValidationError) as noncanonical_kinds:
        workflow.list_source_heads(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            kinds=["TEXT", "BBOX"],
            limit=1,
            cursor=None,
        )
    assert noncanonical_kinds.value.code == "HUMAN_REVIEW_SOURCE_FILTER_INVALID"

    detail = workflow.get_source_head(
        owner,
        asset_id=asset.asset_id,
        expected_asset_version=asset.version,
        target_kind=summary["target_kind"],
        target_digest=summary["target_digest"],
        expected_head_version=summary["head_version"],
    )["source"]
    assert set(detail) == set(summary) | {"original_value"}
    assert detail["schema_version"] == "human-review-source-detail-v1"
    if detail["target_kind"] == "BBOX":
        assert isinstance(detail["target"]["x"], float)

    second = workflow.list_source_heads(
        owner,
        asset_id=asset.asset_id,
        expected_asset_version=asset.version,
        kinds=[],
        limit=1,
        cursor=first["next_cursor"],
    )
    assert len(second["sources"]) == 1
    assert second["next_cursor"] is None

    with pytest.raises(ValidationError) as cursor_scope:
        workflow.list_source_heads(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            kinds=["TEXT"],
            limit=1,
            cursor=first["next_cursor"],
        )
    assert cursor_scope.value.code == "HUMAN_REVIEW_SOURCE_CURSOR_SCOPE_INVALID"

    with pytest.raises(ConflictError) as head_drift:
        workflow.get_source_head(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            target_kind=summary["target_kind"],
            target_digest=summary["target_digest"],
            expected_head_version=summary["head_version"] + 1,
        )
    assert head_drift.value.code == "HUMAN_REVIEW_SOURCE_HEAD_VERSION_DRIFT"

    outsider = TenantContext("tenant-b", "project-b", "review-outsider")
    store.bootstrap_project(outsider)
    with pytest.raises(NotFoundError):
        workflow.list_source_heads(
            outsider,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            kinds=[],
            limit=1,
            cursor=None,
        )

    register(
        72,
        target_kind="TEXT",
        target={"path": "content_blocks/72/text"},
        original_value="later source",
        confidence=0.2,
    )
    with pytest.raises(ConflictError) as collection_drift:
        workflow.list_source_heads(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            kinds=[],
            limit=1,
            cursor=first["next_cursor"],
        )
    assert collection_drift.value.code == "HUMAN_REVIEW_SOURCE_COLLECTION_DRIFT"

    with store.transaction() as connection:
        connection.execute("DROP TRIGGER human_review_target_heads_state_transition")
        connection.execute("DROP TRIGGER human_review_target_heads_lineage_guard")
        connection.execute(
            """UPDATE human_review_target_heads
                  SET current_value_json=?,current_value_digest=?
                WHERE tenant_id=? AND project_id=? AND asset_id=?
                  AND target_kind='TEXT'""",
            (
                content_contract_json("tampered source"),
                content_contract_digest("tampered source").removeprefix("sha256:"),
                owner.tenant_id,
                owner.project_id,
                asset.asset_id,
            ),
        )
    with pytest.raises(IntegrityError) as corrupt_collection:
        workflow.list_source_heads(
            owner,
            asset_id=asset.asset_id,
            expected_asset_version=asset.version,
            kinds=[],
            limit=1,
            cursor=None,
        )
    assert corrupt_collection.value.code == "HUMAN_REVIEW_SOURCE_HEAD_CORRUPT"


def test_capability_revocation_preserves_exact_receipt_replay_only(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    target = {"path": "content_blocks/receipt-replay/text"}
    provenance = {
        "schema_version": "human-review-source-provenance-v1",
        "source_kind": "TRUSTED_DERIVATION",
        "source_id": "receipt-replay-source",
        "source_digest": f"sha256:{canonical_digest('receipt-replay-source')}",
        "producer_version": "receipt-replay-v1",
    }
    source_arguments = {
        "asset_id": asset.asset_id,
        "expected_asset_version": asset.version,
        "target_kind": "TEXT",
        "target": target,
        "original_value": "receipt replay value",
        "confidence": 0.2,
        "provenance": provenance,
        "capability_id": source_capability,
        "capability_token": source_token,
        "idempotency_key": "source-receipt-replay-0001",
        "request_digest": _request_digest("source-receipt-replay-0001"),
    }
    registered = workflow.register_source_snapshot(owner, **source_arguments)
    workflow.revoke_source_producer_capability(
        owner,
        capability_id=source_capability,
        expected_version=1,
        reason="rotate producer capability",
        idempotency_key="source-capability-revoke-replay-0001",
        request_digest=_request_digest("source-capability-revoke-replay-0001"),
    )
    assert workflow.register_source_snapshot(owner, **source_arguments) == registered
    with pytest.raises(AuthorizationError) as wrong_token:
        workflow.register_source_snapshot(
            owner, **{**source_arguments, "capability_token": "wrong-source-token-000000000000"}
        )
    assert wrong_token.value.code == "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
    with pytest.raises(AuthorizationError) as revoked_new_request:
        workflow.register_source_snapshot(
            owner,
            **{
                **source_arguments,
                "target": {"path": "content_blocks/revoked-new/text"},
                "idempotency_key": "source-revoked-new-0001",
                "request_digest": _request_digest("source-revoked-new-0001"),
            },
        )
    assert (
        revoked_new_request.value.code
        == "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
    )

    queued = workflow.enqueue_review_task(
        owner,
        asset_id=asset.asset_id,
        expected_asset_version=asset.version,
        target_kind="TEXT",
        reason="review receipt replay",
        idempotency_key="receipt-worker-enqueue-0001",
        request_digest=_request_digest("receipt-worker-enqueue-0001"),
        target_digest=registered["head"]["target_digest"],
        expected_head_version=registered["head"]["version"],
        expected_snapshot_id=registered["snapshot"]["snapshot_id"],
        expected_snapshot_digest=registered["snapshot"]["snapshot_digest"],
        expected_head_value_digest=registered["head"]["current_value_digest"],
        original_value_digest=(
            f"sha256:{human_review_client_value_digest('receipt replay value')}"
        ),
    )["task"]
    edited, claim_token = _claim_and_edit(
        workflow, owner, queued, ordinal=91, corrected_value="receipt corrected"
    )
    approved = _approve(workflow, owner, edited, claim_token, ordinal=91)
    worker, worker_capability, worker_token = _register_worker(
        workflow, owner, ordinal=91
    )

    first = approved["propagations"][0]
    first_owner_token = "receipt-worker-owner-0001"
    first_claim = workflow.claim_propagation(
        worker,
        propagation_id=first["propagation_id"],
        capability_id=worker_capability,
        capability_token=worker_token,
        owner_token=first_owner_token,
        lease_seconds=600,
        idempotency_key="receipt-worker-claim-0001",
        request_digest=_request_digest("receipt-worker-claim-0001"),
    )["propagation"]
    dispatch_arguments = {
        "propagation_id": first["propagation_id"],
        "capability_id": worker_capability,
        "capability_token": worker_token,
        "owner_token": first_owner_token,
        "claim_fence": first_claim["claim_fence"],
        "idempotency_key": "receipt-worker-dispatch-0001",
        "request_digest": _request_digest("receipt-worker-dispatch-0001"),
    }
    dispatched = workflow.mark_propagation_dispatched(worker, **dispatch_arguments)
    complete_arguments = {
        **{key: value for key, value in dispatch_arguments.items() if key != "idempotency_key" and key != "request_digest"},
        "outcome": "SUCCEEDED",
        "result": {"provider_receipt": "receipt-worker-complete-0001"},
        "failure_code": None,
        "idempotency_key": "receipt-worker-complete-0001",
        "request_digest": _request_digest("receipt-worker-complete-0001"),
    }
    completed = workflow.complete_propagation(worker, **complete_arguments)

    second = approved["propagations"][1]
    second_owner_token = "receipt-worker-owner-0002"
    second_claim = workflow.claim_propagation(
        worker,
        propagation_id=second["propagation_id"],
        capability_id=worker_capability,
        capability_token=worker_token,
        owner_token=second_owner_token,
        lease_seconds=600,
        idempotency_key="receipt-worker-claim-0002",
        request_digest=_request_digest("receipt-worker-claim-0002"),
    )["propagation"]
    workflow.mark_propagation_dispatched(
        worker,
        propagation_id=second["propagation_id"],
        capability_id=worker_capability,
        capability_token=worker_token,
        owner_token=second_owner_token,
        claim_fence=second_claim["claim_fence"],
        idempotency_key="receipt-worker-dispatch-0002",
        request_digest=_request_digest("receipt-worker-dispatch-0002"),
    )
    workflow.complete_propagation(
        worker,
        propagation_id=second["propagation_id"],
        capability_id=worker_capability,
        capability_token=worker_token,
        owner_token=second_owner_token,
        claim_fence=second_claim["claim_fence"],
        outcome="UNKNOWN",
        result={"provider_receipt": "response-lost"},
        failure_code="PROVIDER_OUTCOME_UNKNOWN",
        idempotency_key="receipt-worker-unknown-0002",
        request_digest=_request_digest("receipt-worker-unknown-0002"),
    )
    reconcile_arguments = {
        "propagation_id": second["propagation_id"],
        "capability_id": worker_capability,
        "capability_token": worker_token,
        "outcome": "NOT_APPLIED",
        "result": {"provider_receipt": "verified-not-applied"},
        "failure_code": None,
        "idempotency_key": "receipt-worker-reconcile-0002",
        "request_digest": _request_digest("receipt-worker-reconcile-0002"),
    }
    reconciled = workflow.reconcile_propagation(worker, **reconcile_arguments)
    workflow.revoke_worker_capability(
        owner,
        capability_id=worker_capability,
        expected_version=1,
        reason="rotate worker capability",
        idempotency_key="receipt-worker-revoke-0001",
        request_digest=_request_digest("receipt-worker-revoke-0001"),
    )
    assert workflow.mark_propagation_dispatched(worker, **dispatch_arguments) == dispatched
    assert workflow.complete_propagation(worker, **complete_arguments) == completed
    assert workflow.reconcile_propagation(worker, **reconcile_arguments) == reconciled
    with pytest.raises(AuthorizationError) as revoked_worker_new_request:
        workflow.claim_propagation(
            worker,
            propagation_id=approved["propagations"][2]["propagation_id"],
            capability_id=worker_capability,
            capability_token=worker_token,
            owner_token="receipt-worker-owner-0003",
            lease_seconds=600,
            idempotency_key="receipt-worker-claim-0003",
            request_digest=_request_digest("receipt-worker-claim-0003"),
        )
    assert revoked_worker_new_request.value.code == "HUMAN_REVIEW_WORKER_CAPABILITY_DENIED"


def test_opaque_enqueue_preparation_is_scoped_digest_only_and_atomic(
    workflow_fixture,
) -> None:
    store, workflow, owner, asset, source_capability, source_token = workflow_fixture
    source_task = _enqueue(
        workflow,
        owner,
        asset.asset_id,
        ordinal=92,
        source_capability_id=source_capability,
        source_capability_token=source_token,
    )["task"]
    source_ref = source_task["source_ref"]
    handle = "opaque-recovery-handle-" + "h" * 32
    prepare_key = "opaque-enqueue-prepare-0001"
    execute_key = "opaque-enqueue-execute-0001"
    prepare_arguments = {
        "recovery_handle": handle,
        "execute_idempotency_key": execute_key,
        "asset_id": asset.asset_id,
        "expected_asset_version": asset.version,
        "target_kind": source_task["target_kind"],
        "reason": "private recovery reason",
        "idempotency_key": prepare_key,
        "request_digest": _request_digest(prepare_key),
        **_source_bound_args(source_ref),
    }
    prepared = workflow.prepare_enqueue_review_task(owner, **prepare_arguments)
    preparation = prepared["preparation"]
    assert preparation["schema_version"] == "human-review-enqueue-preparation-v1"
    assert preparation["state"] == "PREPARED"
    assert preparation["safe_to_clear"] is False
    assert preparation["request_digest"].startswith("sha256:")
    with store._lock:
        stored = store._connection.execute(
            "SELECT * FROM human_review_enqueue_preparations WHERE preparation_id=?",
            ("review-enqueue-preparation-" + canonical_digest({
                "tenant_id": owner.tenant_id,
                "project_id": owner.project_id,
                "actor_id": owner.actor_id,
                "recovery_handle_digest": f"sha256:{hashlib.sha256(handle.encode()).hexdigest()}",
            })[:32],),
        ).fetchone()
    assert stored is not None
    assert handle not in tuple(str(value) for value in stored)
    assert execute_key not in tuple(str(value) for value in stored)

    executed = workflow.execute_prepared_review_task(
        owner,
        recovery_handle=handle,
        idempotency_key=execute_key,
        request_digest=_request_digest(execute_key),
    )
    assert executed["preparation"]["state"] == "EXECUTED"
    assert executed["preparation"]["safe_to_clear"] is True
    assert executed["preparation"]["task_id"] == executed["task"]["task_id"]
    with store.transaction() as connection:
        connection.execute(
            "DROP TRIGGER trg_human_review_enqueue_preparations_immutable_identity"
        )
        connection.execute(
            "DROP TRIGGER trg_human_review_enqueue_preparations_transition_guard"
        )
        connection.execute(
            "UPDATE human_review_enqueue_preparations SET expires_at=? WHERE preparation_id=?",
            ("2000-01-01T00:00:00+00:00", stored["preparation_id"]),
        )
    assert workflow.execute_prepared_review_task(
        owner,
        recovery_handle=handle,
        idempotency_key=execute_key,
        request_digest=_request_digest(execute_key),
    ) == executed
    with pytest.raises(AuthorizationError) as wrong_execute_key:
        workflow.execute_prepared_review_task(
            owner,
            recovery_handle=handle,
            idempotency_key="opaque-enqueue-wrong-key-0001",
            request_digest=_request_digest("opaque-enqueue-wrong-key-0001"),
        )
    assert (
        wrong_execute_key.value.code
        == "HUMAN_REVIEW_ENQUEUE_PREPARATION_CAPABILITY_DENIED"
    )

    absent_handle = "opaque-absent-recovery-" + "a" * 32
    absent = workflow.execute_prepared_review_task(
        owner,
        recovery_handle=absent_handle,
        idempotency_key="opaque-enqueue-absent-0001",
        request_digest=_request_digest("opaque-enqueue-absent-0001"),
    )
    assert absent == {
        "preparation": {
            "schema_version": "human-review-enqueue-preparation-absence-v1",
            "recovery_handle": absent_handle,
            "state": "ABSENT",
            "safe_to_clear": True,
        }
    }

    expired_handle = "opaque-expired-recovery-" + "e" * 32
    expired_execute_key = "opaque-enqueue-expired-execute-0001"
    workflow.prepare_enqueue_review_task(
        owner,
        **{
            **prepare_arguments,
            "recovery_handle": expired_handle,
            "execute_idempotency_key": expired_execute_key,
            "idempotency_key": "opaque-enqueue-expired-prepare-0001",
            "request_digest": _request_digest("opaque-enqueue-expired-prepare-0001"),
        },
    )
    expired_handle_digest = hashlib.sha256(expired_handle.encode()).hexdigest()
    with store._lock:
        expired_row = store._connection.execute(
            """SELECT preparation_id FROM human_review_enqueue_preparations
                WHERE tenant_id=? AND project_id=? AND actor_id=?
                  AND recovery_handle_digest=?""",
            (
                owner.tenant_id,
                owner.project_id,
                owner.actor_id,
                expired_handle_digest,
            ),
        ).fetchone()
    assert expired_row is not None
    with store.transaction() as connection:
        connection.execute(
            "UPDATE human_review_enqueue_preparations SET expires_at=? WHERE preparation_id=?",
            ("2000-01-01T00:00:00+00:00", expired_row["preparation_id"]),
        )
    expired_result = workflow.execute_prepared_review_task(
        owner,
        recovery_handle=expired_handle,
        idempotency_key=expired_execute_key,
        request_digest=_request_digest(expired_execute_key),
    )
    assert expired_result["preparation"]["state"] == "EXPIRED"
    assert expired_result["preparation"]["safe_to_clear"] is True
