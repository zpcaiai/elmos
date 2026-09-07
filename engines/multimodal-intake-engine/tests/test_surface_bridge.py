from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake import TenantContext, create_runtime
from elmos_multimodal_intake.canonical import canonical_digest
from elmos_multimodal_intake.errors import AuthorizationError, ValidationError
from elmos_multimodal_intake.progress_stream import job_progress_sequence
from elmos_multimodal_intake.skill_runtime import RuntimeContext
from elmos_multimodal_intake.surface_bridge import ProgressDeliveryStore, SurfaceSkillBridge
from elmos_multimodal_intake.webhooks import WebhookSigner, WebhookVerifier


UI_SKILL = "elmos-multimodal-input-workbench-ui"
API_SKILL = "elmos-ingestion-api-and-sdk"
ENVELOPE_KEYS = {"state", "code", "outputs", "metrics", "retryable"}


def context(
    *,
    tenant: str = "tenant-a",
    project: str = "project-a",
    actor: str = "user:surface-reader",
    idempotency_key: str | None = "surface-request-0001",
) -> RuntimeContext:
    return RuntimeContext(
        tenant_id=tenant,
        project_id=project,
        actor_id=actor,
        request_id="request-surface-1",
        trace_id="trace-surface-1",
        idempotency_key=idempotency_key,
        policy={},
        capabilities={},
    )


def invoke(
    bridge: SurfaceSkillBridge,
    skill: str,
    operation: Any,
    **payload: Any,
) -> Mapping[str, Any]:
    result = bridge.handle(skill, context(), {"operation": operation, **payload})
    assert set(result) == ENVELOPE_KEYS
    assert result["retryable"] is False
    assert isinstance(result["outputs"], dict)
    assert isinstance(result["metrics"], dict)
    return result


def assert_file_bundle(bundle: Mapping[str, Any]) -> None:
    unsigned = dict(bundle)
    supplied = unsigned.pop("bundle_digest")
    assert supplied == canonical_digest(unsigned)
    assert bundle["files"]
    for record in bundle["files"]:
        assert set(record) == {"path", "bytes", "sha256"}
        assert record["bytes"] > 0
        assert len(record["sha256"]) == 64


def preview_entries() -> list[dict[str, Any]]:
    return [
        {
            "path": "src/main.py",
            "byte_count": 12,
            "content_digest": "a" * 64,
            "asset_id": "asset-main",
            "state": "READY",
            "role": "PRIMARY",
            "model_read_allowed": True,
        },
        {
            "path": "docs/notes.md",
            "byte_count": 8,
            "content_digest": "sha256:" + "b" * 64,
            "asset_id": None,
            "state": "SELECTED",
            "role": "IGNORE",
            "model_read_allowed": False,
        },
    ]


def progress_event(*, state: str = "RUNNING", sequence: int = 1) -> dict[str, Any]:
    completed = 1 if state == "RUNNING" else 2
    return {
        "job_id": "job-1",
        "sequence": sequence,
        "occurred_at": "2026-08-22T12:00:00+00:00",
        "trace_id": "trace-progress-1",
        "state": state,
        "progress": {
            "completed_units": completed,
            "total_units": 2,
            "percent": completed * 50.0,
        },
        "payload": {"code": "PROCESSING", "retryable": False},
    }


def test_ui_surface_and_preview_are_exact_content_addressed_and_deterministic() -> None:
    bridge = SurfaceSkillBridge()

    for operation in ("describe", "capabilities", "health"):
        result = invoke(bridge, UI_SKILL, operation)
        assert result["state"] == "SUCCEEDED"
        assert result["code"] == f"LOCAL_UI_SURFACE_{operation.upper()}"
        outputs = result["outputs"]
        assert outputs["page_route"] == "/intake"
        assert outputs["external_evidence"] == "NOT_RUN"
        assert outputs["certification"] == "NOT_CERTIFIED"
        assert outputs["capabilities"]["microphone_recording"] is True
        assert outputs["capabilities"]["safe_progress_polling"] is True
        assert outputs["capabilities"]["sse_or_websocket_sync"] is True
        assert outputs["skill_catalog"]["skill_count"] == 50
        assert_file_bundle(outputs["file_bundle"])

    left = invoke(bridge, UI_SKILL, "build_preview", entries=preview_entries())
    right = invoke(bridge, UI_SKILL, "build_preview", entries=list(reversed(preview_entries())))
    assert left["state"] == "SUCCEEDED"
    assert left["code"] == "DETERMINISTIC_PACKAGE_PREVIEW_BUILT"
    preview = left["outputs"]["preview"]
    unsigned = dict(preview)
    assert unsigned.pop("preview_digest") == canonical_digest(unsigned)
    assert preview["preview_digest"] == right["outputs"]["preview"]["preview_digest"]
    assert [item["path"] for item in preview["entries"]] == ["docs/notes.md", "src/main.py"]
    assert preview["entries"][0]["role"] == "IGNORE"
    assert preview["entries"][0]["model_read_allowed"] is False


@pytest.mark.parametrize(
    "entries,code",
    [
        ([], "PREVIEW_ENTRIES_INVALID"),
        ([{**preview_entries()[0], "path": "../escape"}], "PREVIEW_ENTRY_PATH_INVALID"),
        (
            [preview_entries()[0], {**preview_entries()[1], "path": "SRC/main.py"}],
            "PREVIEW_ENTRY_PATH_COLLISION",
        ),
        ([{**preview_entries()[0], "role": "IGNORE"}], "PREVIEW_ENTRY_ACCESS_INVALID"),
    ],
)
def test_preview_fails_closed_for_invalid_or_portably_colliding_entries(
    entries: list[dict[str, Any]],
    code: str,
) -> None:
    with pytest.raises(ValidationError) as caught:
        SurfaceSkillBridge().handle(
            UI_SKILL,
            context(),
            {"operation": "build_preview", "entries": entries},
        )
    assert caught.value.code == code


def test_api_contract_binds_openapi_asyncapi_and_three_sdk_languages() -> None:
    bridge = SurfaceSkillBridge()
    described = invoke(bridge, API_SKILL, "describe")
    contract = described["outputs"]["contract_bundle"]
    unsigned = dict(contract)
    assert unsigned.pop("contract_digest") == canonical_digest(unsigned)
    assert contract["contract_kind"] == "CONTENT_ADDRESSED_HTTP_ASYNCAPI_AND_SDK_BUNDLE"
    assert contract["sdk_languages"] == ["java", "python", "typescript"]
    assert contract["progress_transports"] == [
        "safe-polling",
        "authenticated-sse",
        "authenticated-read-only-websocket",
        "signed-webhook",
    ]
    assert contract["external_delivery_default"] == "DISABLED"
    assert contract["external_evidence"] == "NOT_RUN"
    assert contract["certification"] == "NOT_CERTIFIED"
    assert_file_bundle(contract["file_bundle"])
    assert invoke(bridge, API_SKILL, "build_contract")["outputs"]["contract_bundle"] == contract

    unavailable = invoke(
        bridge,
        API_SKILL,
        "prepare_progress_delivery",
    )
    assert unavailable["state"] == "BLOCKED"
    assert unavailable["code"] == "SURFACE_OPERATION_UNSUPPORTED"
    assert "prepare_progress_delivery" not in unavailable["outputs"]["allowed_operations"]


def test_surface_bridge_unknown_operation_skill_and_missing_files_fail_closed(
    tmp_path: Path,
) -> None:
    invalid = invoke(SurfaceSkillBridge(), UI_SKILL, None)
    assert invalid["state"] == "BLOCKED"
    assert invalid["outputs"]["operation"] == "INVALID"

    unknown = invoke(SurfaceSkillBridge(), "elmos-unknown-surface", "describe")
    assert unknown["state"] == "BLOCKED"
    assert unknown["code"] == "SURFACE_SKILL_UNKNOWN"

    missing = invoke(SurfaceSkillBridge(tmp_path), API_SKILL, "health")
    assert missing == {
        "state": "FAILED",
        "code": "LOCAL_SURFACE_INTEGRITY_FAILED",
        "outputs": {"skill": API_SKILL},
        "metrics": {},
        "retryable": False,
    }


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def deliver(
        self,
        *,
        endpoint_ref: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {"endpoint_ref": endpoint_ref, "headers": dict(headers), "body": body}
        )
        return {
            "schema_version": "1.0.0",
            "delivery_id": headers["x-elmos-delivery-id"],
            "body_digest": headers["x-elmos-body-sha256"],
            "delivery_state": "DELIVERED",
            "provider_message_id": "provider-message-1",
            "failure_code": None,
            "retryable": False,
        }


def test_progress_delivery_is_scoped_idempotent_and_transport_injected(tmp_path: Path) -> None:
    capability = object()
    producer_capability = object()
    transport = RecordingTransport()
    store = ProgressDeliveryStore(
        tmp_path / "progress.sqlite3",
        worker_capability=capability,
        producer_capability=producer_capability,
        transport=transport,
        signer=WebhookSigner(
            b"s" * 32,
            clock=lambda: 1_700_000_000,
            scope_id="tenant-a:project-a",
            key_id="progress-key-1",
        ),
    )
    try:
        ctx = context(idempotency_key="progress-prepare-0001")
        preparation = {
            "endpoint_ref": "endpoint-ref:project-progress",
            "event_type": "intake.job.progress",
            "event": progress_event(),
            "idempotency_key": "progress-prepare-0001",
            "capability": producer_capability,
        }
        delivery = store.prepare(ctx, **preparation)
        assert delivery["state"] == "PENDING"
        replayed = store.prepare(ctx, **preparation)
        assert replayed["delivery_id"] == delivery["delivery_id"]

        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_IDEMPOTENCY_CONFLICT"):
            store.prepare(
                ctx,
                **{
                    **preparation,
                    "event": progress_event(state="SUCCEEDED", sequence=2),
                },
            )
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_IDEMPOTENCY_CONFLICT"):
            store.prepare(
                ctx,
                **{**preparation, "endpoint_ref": "endpoint-ref:different"},
            )
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_PRODUCER_UNAUTHORIZED"):
            store.prepare(ctx, **{**preparation, "capability": object()})
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_WORKER_UNAUTHORIZED"):
            store.claim(
                ctx,
                delivery_id=delivery["delivery_id"],
                claim_token="claim-token-00000001",
                capability=object(),
            )
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_NOT_CLAIMABLE"):
            store.claim(
                context(tenant="tenant-b"),
                delivery_id=delivery["delivery_id"],
                claim_token="claim-token-00000001",
                capability=capability,
            )

        delivered = store.claim_and_deliver(
            ctx,
            delivery_id=delivery["delivery_id"],
            claim_token="claim-token-00000001",
            capability=capability,
        )
        assert delivered["state"] == "DELIVERED"
        assert len(transport.calls) == 1
        call = transport.calls[0]
        assert call["endpoint_ref"] == "endpoint-ref:project-progress"
        assert call["headers"]["x-elmos-body-sha256"] == delivery["body_digest"]
        assert call["headers"]["x-elmos-delivery-id"] == delivery["delivery_id"]
        assert call["headers"]["x-elmos-delivery-attempt"] == "1"
        assert WebhookVerifier(
            b"s" * 32,
            clock=lambda: 1_700_000_000,
            scope_id="tenant-a:project-a",
            key_id="progress-key-1",
            allow_process_local_replay=True,
        ).verify(call["headers"], call["body"]) == delivery["delivery_id"]
        body = json.loads(call["body"])
        assert body["tenant_id"] == "tenant-a"
        assert body["project_id"] == "project-a"
        assert body["job_id"] == "job-1"
        assert body["event_digest"] == canonical_digest(
            {key: value for key, value in body.items() if key != "event_digest"}
        )
        assert "actor_id" not in body
        assert delivered["transport_receipt"]["provider_message_id"] == "provider-message-1"
        assert delivered["transport_receipt_digest"] == canonical_digest(
            delivered["transport_receipt"]
        )
    finally:
        store.close()


def test_progress_delivery_defaults_to_no_external_side_effect(tmp_path: Path) -> None:
    capability = object()
    producer_capability = object()
    store = ProgressDeliveryStore(
        tmp_path / "progress.sqlite3",
        worker_capability=capability,
        producer_capability=producer_capability,
    )
    try:
        ctx = context()
        delivery = store.prepare(
            ctx,
            endpoint_ref="endpoint-ref:no-transport",
            event_type="intake.progress",
            event=progress_event(),
            idempotency_key="progress-no-transport-0001",
            capability=producer_capability,
        )
        with pytest.raises(ValidationError, match="PROGRESS_WEBHOOK_TRANSPORT_NOT_CONFIGURED"):
            store.claim_and_deliver(
                ctx,
                delivery_id=delivery["delivery_id"],
                claim_token="claim-token-00000002",
                capability=capability,
            )
        claimed = store.claim(
            ctx,
            delivery_id=delivery["delivery_id"],
            claim_token="claim-token-00000002",
            capability=capability,
        )
        assert claimed["state"] == "CLAIMED"
    finally:
        store.close()


class UnknownOutcomeTransport:
    def deliver(
        self,
        *,
        endpoint_ref: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Mapping[str, Any]:
        del endpoint_ref, headers, body
        raise TimeoutError("remote acceptance is unknown")


class InvalidReceiptTransport:
    def deliver(
        self,
        *,
        endpoint_ref: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Mapping[str, Any]:
        del endpoint_ref, headers, body
        # A remote endpoint could already have accepted the body.  This value
        # deliberately cannot prove either delivery or non-delivery.
        return {"accepted": True}


def test_progress_invalid_transport_receipt_remains_unknown_and_reconcilable(
    tmp_path: Path,
) -> None:
    capability = object()
    producer_capability = object()
    store = ProgressDeliveryStore(
        tmp_path / "invalid-receipt.sqlite3",
        worker_capability=capability,
        producer_capability=producer_capability,
        transport=InvalidReceiptTransport(),
        signer=WebhookSigner(
            b"i" * 32,
            clock=lambda: 1_700_000_000,
            scope_id="tenant-a:project-a",
            key_id="progress-key-invalid-receipt",
        ),
    )
    try:
        ctx = context()
        delivery = store.prepare(
            ctx,
            endpoint_ref="endpoint-ref:invalid-receipt",
            event_type="intake.job.progress",
            event=progress_event(),
            idempotency_key="progress-invalid-receipt-0001",
            capability=producer_capability,
        )
        unknown = store.claim_and_deliver(
            ctx,
            delivery_id=delivery["delivery_id"],
            claim_token="claim-token-invalid-receipt-01",
            capability=capability,
        )
        assert unknown["state"] == "UNKNOWN"
        assert unknown["failure_code"] == "PROGRESS_TRANSPORT_RECEIPT_INVALID"
        assert unknown["transport_receipt"]["delivery_state"] == "UNKNOWN"
        reconciled = store.reconcile(
            ctx,
            delivery_id=delivery["delivery_id"],
            capability=capability,
            transport_receipt={
                "schema_version": "1.0.0",
                "delivery_id": delivery["delivery_id"],
                "body_digest": delivery["body_digest"],
                "delivery_state": "FAILED",
                "provider_message_id": None,
                "failure_code": "PROVIDER_CONFIRMED_NOT_DELIVERED",
                "retryable": False,
            },
        )
        assert reconciled["state"] == "FAILED"
    finally:
        store.close()


def test_progress_unknown_outcome_requires_exact_reconciliation(tmp_path: Path) -> None:
    capability = object()
    producer_capability = object()
    signer = WebhookSigner(
        b"u" * 32,
        clock=lambda: 1_700_000_000,
        scope_id="tenant-a:project-a",
        key_id="progress-key-unknown",
    )
    store = ProgressDeliveryStore(
        tmp_path / "unknown.sqlite3",
        worker_capability=capability,
        producer_capability=producer_capability,
        transport=UnknownOutcomeTransport(),
        signer=signer,
    )
    try:
        ctx = context()
        delivery = store.prepare(
            ctx,
            endpoint_ref="endpoint-ref:unknown",
            event_type="intake.job.progress",
            event=progress_event(),
            idempotency_key="progress-unknown-0001",
            capability=producer_capability,
        )
        unknown = store.claim_and_deliver(
            ctx,
            delivery_id=delivery["delivery_id"],
            claim_token="claim-token-unknown-001",
            capability=capability,
        )
        assert unknown["state"] == "UNKNOWN"
        assert unknown["failure_code"] == "PROGRESS_TRANSPORT_OUTCOME_UNKNOWN"
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_NOT_CLAIMABLE"):
            store.claim(
                ctx,
                delivery_id=delivery["delivery_id"],
                claim_token="claim-token-unknown-002",
                capability=capability,
            )

        reconciled = store.reconcile(
            ctx,
            delivery_id=delivery["delivery_id"],
            capability=capability,
            transport_receipt={
                "schema_version": "1.0.0",
                "delivery_id": delivery["delivery_id"],
                "body_digest": delivery["body_digest"],
                "delivery_state": "DELIVERED",
                "provider_message_id": "provider-reconciled-1",
                "failure_code": None,
                "retryable": False,
            },
        )
        assert reconciled["state"] == "DELIVERED"
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_NOT_RECONCILABLE"):
            store.reconcile(
                ctx,
                delivery_id=delivery["delivery_id"],
                capability=capability,
                transport_receipt=reconciled["transport_receipt"],
            )
    finally:
        store.close()


def test_progress_transport_cannot_run_without_runtime_owned_signer(tmp_path: Path) -> None:
    capability = object()
    producer_capability = object()
    transport = RecordingTransport()
    store = ProgressDeliveryStore(
        tmp_path / "unsigned.sqlite3",
        worker_capability=capability,
        producer_capability=producer_capability,
        transport=transport,
    )
    try:
        ctx = context()
        delivery = store.prepare(
            ctx,
            endpoint_ref="endpoint-ref:unsigned",
            event_type="intake.job.progress",
            event=progress_event(),
            idempotency_key="progress-unsigned-0001",
            capability=producer_capability,
        )
        with pytest.raises(ValidationError, match="PROGRESS_WEBHOOK_SIGNER_NOT_CONFIGURED"):
            store.claim_and_deliver(
                ctx,
                delivery_id=delivery["delivery_id"],
                claim_token="claim-token-unsigned-01",
                capability=capability,
            )
        assert transport.calls == []
        assert store.claim(
            ctx,
            delivery_id=delivery["delivery_id"],
            claim_token="claim-token-unsigned-01",
            capability=capability,
        )["state"] == "CLAIMED"
    finally:
        store.close()


def test_runtime_owns_progress_producer_worker_signer_and_acl(tmp_path: Path) -> None:
    transport = RecordingTransport()
    runtime = create_runtime(
        tmp_path / "runtime.sqlite3",
        tmp_path / "cas",
        progress_webhook_transport=transport,
        progress_webhook_signer=WebhookSigner(
            b"r" * 32,
            clock=lambda: 1_700_000_000,
            scope_id="tenant-a:project-a",
            key_id="runtime-progress-key-1",
        ),
    )
    tenant_context = TenantContext("tenant-a", "project-a", "user:surface-reader")
    try:
        runtime.store.bootstrap_project(tenant_context)
        session = runtime.store.create_session(
            tenant_context,
            idempotency_key="runtime-progress-session-0001",
        )
        job = runtime.store.create_job(
            tenant_context,
            session.session_id,
            idempotency_key="runtime-progress-job-0001",
            request_digest="c" * 64,
        )
        event = {
            **progress_event(state="PENDING", sequence=job_progress_sequence(job)),
            "job_id": job.job_id,
            "occurred_at": job.updated_at,
            "progress": {
                "completed_units": 0,
                "total_units": 1,
                "percent": 0.0,
            },
        }
        delivery = runtime.prepare_progress_webhook(
            tenant_context,
            endpoint_ref="endpoint-ref:runtime-owned",
            event_type="intake.job.progress",
            event=event,
            idempotency_key="runtime-progress-prepare-0001",
        )
        with pytest.raises(ValidationError, match="PROGRESS_EVENT_SOURCE_MISMATCH"):
            runtime.prepare_progress_webhook(
                tenant_context,
                endpoint_ref="endpoint-ref:runtime-owned",
                event_type="intake.job.progress",
                event={**event, "state": "SUCCEEDED"},
                idempotency_key="runtime-progress-forged-0001",
            )
        delivered = runtime.deliver_progress_webhook(
            tenant_context,
            delivery_id=delivery["delivery_id"],
            claim_token="runtime-owned-claim-token-01",
        )
        assert delivered["state"] == "DELIVERED"
        assert len(transport.calls) == 1

        with pytest.raises(AuthorizationError):
            runtime.deliver_progress_webhook(
                TenantContext("tenant-a", "project-a", "user:not-authorized"),
                delivery_id=delivery["delivery_id"],
                claim_token="runtime-owned-claim-token-02",
            )
        with pytest.raises(ValidationError, match="PROGRESS_DELIVERY_PRODUCER_UNAUTHORIZED"):
            runtime.progress_deliveries.prepare(
                context(),
                endpoint_ref="endpoint-ref:forged-producer",
                event_type="intake.job.progress",
                event=progress_event(),
                idempotency_key="forged-producer-key-0001",
                capability=object(),
            )
    finally:
        runtime.close()
        runtime.close()
