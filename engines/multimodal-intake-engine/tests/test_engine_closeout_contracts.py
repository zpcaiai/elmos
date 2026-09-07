from __future__ import annotations

import hashlib
import io
import json
import warnings
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from elmos_multimodal_intake import (
    SKILL_MULTIMODAL_INPUT_ORCHESTRATOR,
    MultimodalIntakeRuntime,
)
from elmos_multimodal_intake.canonical import canonical_digest
from elmos_multimodal_intake.errors import AuthorizationError, ValidationError
from elmos_multimodal_intake.http_server import (
    CAPABILITIES_PATH,
    EXECUTE_PATH,
    PROGRESS_JOB_EVENTS_PREFIX,
    PROGRESS_JOB_WEBSOCKET_PREFIX,
    PROGRESS_TASK_EVENTS_PREFIX,
    PROGRESS_TASK_WEBSOCKET_PREFIX,
)
from elmos_multimodal_intake.models import (
    AssetKind,
    AssetStatus,
    ContentBlock,
    ContentBlockKind,
    InputAsset,
    SecurityDecision,
    SourceAnchor,
    TenantContext,
    UNTRUSTED_CONTENT,
)
from elmos_multimodal_intake.security import FileSecurityInspector


def _asset(name: str = "payload.zip") -> InputAsset:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    return InputAsset(
        asset_id="asset-security-contract",
        session_id="session-security-contract",
        tenant_id="tenant-a",
        project_id="project-a",
        display_name=name,
        declared_media_type="application/zip",
        detected_media_type=None,
        kind=AssetKind.UNKNOWN,
        byte_size=0,
        sha256=None,
        cas_digest=None,
        status=AssetStatus.UPLOADED,
        security_decision=None,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, value in entries:
                archive.writestr(name, value)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("entries", "finding"),
    (
        ([('same.txt', b"one"), ('same.txt', b"two")], "ARCHIVE_MEMBER_NAME_COLLISION"),
        ([('Readme.txt', b"one"), ('README.TXT', b"two")], "ARCHIVE_MEMBER_NAME_COLLISION"),
        ([('caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt', b"one"), ('cafe\N{COMBINING ACUTE ACCENT}.txt', b"two")], "ARCHIVE_MEMBER_NAME_INVALID"),
        ([('safe\\child.txt', b"one")], "ARCHIVE_MEMBER_NAME_INVALID"),
        ([('../escape.txt', b"one")], "ARCHIVE_PATH_TRAVERSAL"),
    ),
)
def test_archive_member_aliases_and_noncanonical_paths_fail_closed(
    entries: list[tuple[str, bytes]],
    finding: str,
) -> None:
    payload = _zip(entries)
    detection = FileSecurityInspector().inspect(_asset(), payload)
    assert detection.decision is SecurityDecision.QUARANTINE
    assert "ARCHIVE_UNSAFE" in detection.findings
    assert finding in detection.findings


def test_docx_requires_exact_unambiguous_member_identity() -> None:
    payload = _zip(
        [
            ("[Content_Types].xml", b"<Types/>") ,
            ("word/document.xml", b"<document/>") ,
            ("WORD/DOCUMENT.XML", b"<spoof/>") ,
        ]
    )
    detection = FileSecurityInspector().inspect(_asset("ambiguous.docx"), payload)
    assert detection.kind is AssetKind.DOCX
    assert detection.decision is SecurityDecision.QUARANTINE
    assert "ARCHIVE_MEMBER_NAME_COLLISION" in detection.findings


def _runtime_request(operation: str, key: str, **values: object) -> dict[str, object]:
    return {"operation": operation, "idempotency_key": key, **values}


def test_operation_acl_denies_before_receipts_or_child_effects(tmp_path: Path) -> None:
    runtime = MultimodalIntakeRuntime(tmp_path / "intake.sqlite3", tmp_path / "cas")
    owner = TenantContext("tenant-a", "project-a", "owner-a")
    try:
        runtime.handle(
            SKILL_MULTIMODAL_INPUT_ORCHESTRATOR,
            owner,
            _runtime_request("bootstrap_project", "bootstrap-owner-0001"),
        )
        runtime.store.grant_permissions(owner, "reader-a", [runtime.store.READ])
        runtime.store.grant_permissions(owner, "writer-a", [runtime.store.WRITE])
        reader = TenantContext(owner.tenant_id, owner.project_id, "reader-a")
        writer = TenantContext(owner.tenant_id, owner.project_id, "writer-a")

        with pytest.raises(AuthorizationError, match="INTAKE_PROJECT_ACCESS_DENIED"):
            runtime.handle(
                SKILL_MULTIMODAL_INPUT_ORCHESTRATOR,
                reader,
                _runtime_request(
                    "create_session",
                    "reader-escalation-0001",
                    requested_role="PRIMARY",
                    permission="intake:admin",
                    tenant_id="tenant-b",
                ),
            )
        assert runtime.store._connection.execute(
            "SELECT count(*) FROM skill_execution_receipts WHERE idempotency_key=?",
            ("reader-escalation-0001",),
        ).fetchone()[0] == 0
        assert runtime.store._connection.execute(
            "SELECT count(*) FROM input_sessions"
        ).fetchone()[0] == 0

        created = runtime.handle(
            SKILL_MULTIMODAL_INPUT_ORCHESTRATOR,
            writer,
            _runtime_request("create_session", "writer-session-0001"),
        )
        with pytest.raises(AuthorizationError, match="INTAKE_PROJECT_ACCESS_DENIED"):
            runtime.handle(
                SKILL_MULTIMODAL_INPUT_ORCHESTRATOR,
                writer,
                {"operation": "get_session", "session_id": created["session_id"]},
            )

        outsider = TenantContext(owner.tenant_id, owner.project_id, "outsider-a")
        with pytest.raises(AuthorizationError, match="INTAKE_PROJECT_ACCESS_DENIED"):
            runtime.handle(
                SKILL_MULTIMODAL_INPUT_ORCHESTRATOR,
                outsider,
                _runtime_request("bootstrap_project", "bootstrap-outsider-0001"),
            )
        assert runtime.store._connection.execute(
            "SELECT count(*) FROM project_acl WHERE principal_id=?",
            (outsider.actor_id,),
        ).fetchone()[0] == 0
        assert runtime.store._connection.execute(
            "SELECT count(*) FROM skill_execution_receipts WHERE idempotency_key=?",
            ("bootstrap-outsider-0001",),
        ).fetchone()[0] == 0
    finally:
        runtime.close()


def test_anonymous_identity_is_rejected_before_runtime_dispatch() -> None:
    with pytest.raises(ValidationError):
        TenantContext("tenant-a", "project-a", "")


def _ready_asset(runtime: MultimodalIntakeRuntime, context: TenantContext) -> InputAsset:
    session = runtime.store.create_session(
        context,
        idempotency_key="trust-session-0001",
    )
    content = b"untrusted source bytes"
    digest = hashlib.sha256(content).hexdigest()
    asset, upload = runtime.store.create_upload(
        context,
        session_id=session.session_id,
        display_name="source.txt",
        declared_media_type="text/plain",
        expected_size=len(content),
        expected_sha256=digest,
        part_size=len(content),
        idempotency_key="trust-upload-0001",
        request_digest=canonical_digest({"digest": digest}),
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )
    runtime.store.record_part(
        context,
        upload.upload_id,
        part_number=0,
        idempotency_key="trust-part-0001",
        byte_offset=0,
        byte_size=len(content),
        sha256=digest,
        cas_digest=digest,
    )
    uploaded = runtime.store.complete_upload(
        context,
        upload.upload_id,
        commit_idempotency_key="trust-commit-0001",
        digest=digest,
        byte_size=len(content),
    )
    return runtime.store.set_asset_result(
        context,
        asset.asset_id,
        status=AssetStatus.READY,
        expected_version=uploaded.version,
    )


def test_untrusted_content_label_is_persisted_and_emitted(tmp_path: Path) -> None:
    runtime = MultimodalIntakeRuntime(tmp_path / "intake.sqlite3", tmp_path / "cas")
    context = TenantContext("tenant-a", "project-a", "owner-a")
    try:
        runtime.store.bootstrap_project(context)
        asset = _ready_asset(runtime, context)
        anchor = SourceAnchor(
            anchor_id="anchor-trust-1",
            asset_id=asset.asset_id,
            source_sha256=asset.sha256 or "",
            locator_type="LINE_RANGE",
            line_start=1,
            line_end=1,
        )
        block = ContentBlock(
            block_id="block-trust-1",
            asset_id=asset.asset_id,
            kind=ContentBlockKind.TEXT,
            ordinal=0,
            text="source remains data",
            payload={"format": "plain"},
            anchors=(anchor,),
        )
        runtime.store.replace_content_blocks(context, asset, [block])

        row = runtime.store._connection.execute(
            "SELECT payload_json FROM content_blocks WHERE block_id=?",
            (block.block_id,),
        ).fetchone()
        assert row is not None
        assert json.loads(row["payload_json"])["_elmos_trust_label"] == UNTRUSTED_CONTENT
        [reloaded] = runtime.store.content_blocks(context, asset.asset_id)
        assert reloaded.trust_label == UNTRUSTED_CONTENT
        assert runtime._json(reloaded)["trust_label"] == UNTRUSTED_CONTENT
        assert dict(reloaded.payload) == {"format": "plain"}
    finally:
        runtime.close()


def test_openapi_routes_match_runtime_routes_exactly() -> None:
    contract = (
        Path(__file__).parents[1]
        / "openapi"
        / "multimodal-intake-v1.openapi.yaml"
    ).read_text(encoding="utf-8")
    expected = {
        CAPABILITIES_PATH,
        EXECUTE_PATH,
        PROGRESS_TASK_EVENTS_PREFIX + "{task_id}/events",
        PROGRESS_JOB_EVENTS_PREFIX + "{job_id}/events",
        PROGRESS_TASK_WEBSOCKET_PREFIX + "{task_id}",
        PROGRESS_JOB_WEBSOCKET_PREFIX + "{job_id}",
    }
    declared = {
        line.strip()[:-1]
        for line in contract.splitlines()
        if line.startswith("  /api/v1/multimodal-intake/") and line.strip().endswith(":")
    }
    assert declared == expected

