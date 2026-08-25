from __future__ import annotations

import base64
import hashlib
import io
import json
import socket
import sqlite3
import threading
from http.server import HTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from elmos_multimodal_intake import (
    CommandReceipt,
    ToolCapability,
    UploadPolicy,
    create_runtime,
)
from elmos_multimodal_intake.cli import (
    TRUSTED_CONTEXT_FILENAME,
    capabilities_document,
    execute_document,
    runtime_execution_environment_digest,
    runtime_execution_environment_identity,
)
from elmos_multimodal_intake.canonical import canonical_json
from elmos_multimodal_intake.errors import ValidationError
from elmos_multimodal_intake.http_server import (
    CAPABILITIES_PATH,
    PROGRESS_JOB_EVENTS_PREFIX,
    PROGRESS_TASK_EVENTS_PREFIX,
    PROGRESS_TASK_WEBSOCKET_PREFIX,
    _BOUND_ACTOR_HEADER,
    _BOUND_PROJECT_HEADER,
    _BOUND_TENANT_HEADER,
    _server_class,
    serve,
)
from elmos_multimodal_intake.models import TenantContext


def request(
    skill: str,
    operation: str,
    inputs: dict[str, object],
    *,
    key: str,
    tenant: str = "tenant-a",
    project: str = "project-a",
    actor: str = "actor-a",
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "skill": skill,
        "operation": operation,
        "tenant_id": tenant,
        "project_id": project,
        "actor_id": actor,
        "idempotency_key": key,
        "trace_id": f"trace-{key}",
        "input": inputs,
    }


def execute(root: Path, document: dict[str, object]) -> dict[str, object]:
    status, body = execute_document(
        document,
        root,
        bound_context=TenantContext(
            str(document["tenant_id"]),
            str(document["project_id"]),
            str(document["actor_id"]),
        ),
    )
    assert status == 200, body
    return body


def _sse_records(body: bytes) -> list[tuple[str | None, str, dict[str, object]]]:
    records: list[tuple[str | None, str, dict[str, object]]] = []
    for block in body.decode("utf-8").strip().split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            name, separator, value = line.partition(": ")
            assert separator == ": "
            assert name not in fields
            fields[name] = value
        assert set(fields) in ({"id", "event", "data"}, {"event", "data"})
        records.append((fields.get("id"), fields["event"], json.loads(fields["data"])))
    return records


def test_composed_runtime_exposes_exact_50_skill_catalog(tmp_path: Path) -> None:
    status, body = capabilities_document(tmp_path / "runtime")
    assert status == 200
    assert body["skill_count"] == 50
    assert len(body["skills"]) == 50
    assert len({item["skill"] for item in body["skills"]}) == 50
    assert body["external_evidence"] == "NOT_RUN"
    assert body["certification"] == "NOT_CERTIFIED"


def test_outer_receipt_supports_read_only_execution_without_bypassing_mutation_acl(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="read-only-bootstrap-0001",
        ),
    )
    owner = TenantContext("tenant-a", "project-a", "actor-a")
    reader = TenantContext("tenant-a", "project-a", "reader-a")
    runtime = create_runtime(root / "intake.sqlite3", root / "cas")
    runtime.store.grant_permissions(owner, reader.actor_id, [runtime.store.READ])
    runtime.close()

    read_status, read_result = execute_document(
        request(
            "elmos-unified-multimodal-content-ir",
            "normalize",
            {"document_id": "read-only-document", "blocks": []},
            key="read-only-domain-0001",
            actor=reader.actor_id,
        ),
        root,
        bound_context=reader,
    )
    assert read_status == 200
    assert read_result["status"] == "PARTIAL"
    assert read_result["code"] == "CONTENT_IR_REVIEW_REQUIRED"

    mutation_status, mutation_result = execute_document(
        request(
            "elmos-multimodal-input-orchestrator",
            "create_session",
            {},
            key="read-only-mutation-0001",
            actor=reader.actor_id,
        ),
        root,
        bound_context=reader,
    )
    assert mutation_status == 403
    assert mutation_result["status"] == "BLOCKED"
    assert mutation_result["code"] == "INTAKE_PROJECT_ACCESS_DENIED"
    assert mutation_result["retryable"] is False


def test_trusted_host_can_inject_a_runtime_factory_without_request_authority(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path]] = []

    def factory(database: Path, cas_root: Path):
        calls.append((database, cas_root))
        return create_runtime(database, cas_root)

    root = tmp_path / "runtime"
    status, body = capabilities_document(root, runtime_factory=factory)
    assert status == 200
    assert body["skill_count"] == 50
    assert calls == [(root / "intake.sqlite3", root / "cas")]


@pytest.mark.parametrize("component_name", ["KnowledgeArchiveSkillBridge", "MultimodalIntakeApi"])
def test_composition_failure_closes_runtime_once_without_masking_original_error(
    tmp_path: Path,
    monkeypatch,
    component_name: str,
) -> None:
    import elmos_multimodal_intake.cli as cli

    close_calls: list[str] = []

    def factory(database: Path, cas_root: Path):
        runtime = create_runtime(database, cas_root)
        original_close = runtime.close

        def tracked_close() -> None:
            close_calls.append("closed")
            original_close()
            raise RuntimeError("cleanup failure must be suppressed")

        runtime.close = tracked_close  # type: ignore[method-assign]
        return runtime

    class BrokenCompositionComponent:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("composition failure is authoritative")

    monkeypatch.setattr(cli, component_name, BrokenCompositionComponent)
    with pytest.raises(RuntimeError, match="composition failure is authoritative"):
        capabilities_document(tmp_path / "runtime", runtime_factory=factory)
    assert close_calls == ["closed"]


def test_execution_environment_identity_is_path_secret_free_and_binds_tool_and_provider_drift(
    tmp_path: Path,
) -> None:
    tool_digest = {"value": "a" * 64}
    tool_path = {"value": "/private/host-secret-bin/elmos-malware-scan"}
    password_provider_digest = {"value": "c" * 64}

    class PasswordProvider:
        @property
        def execution_identity_digest(self) -> str:
            return password_provider_digest["value"]

        def resolve_archive_password(self, **_request: object) -> object:
            raise AssertionError("identity qualification must not resolve a secret")

    def factory(database: Path, cas_root: Path):
        return create_runtime(
            database,
            cas_root,
            provisioned_tools={
                "MALWARE_SCAN": {
                    "path": tool_path["value"],
                    "sha256": tool_digest["value"],
                }
            },
            archive_password_provider=PasswordProvider(),
        )

    probe = factory(tmp_path / "probe.sqlite3", tmp_path / "probe-cas")
    try:
        identity = runtime_execution_environment_identity(probe, runtime_factory=factory)
        identity_digest = runtime_execution_environment_digest(probe, runtime_factory=factory)
    finally:
        probe.close()
    encoded_identity = canonical_json(identity)
    assert len(identity_digest) == 64
    assert tool_digest["value"] in encoded_identity
    assert password_provider_digest["value"] in encoded_identity
    assert "/private/host-secret-bin" not in encoded_identity
    assert "elmos-malware-scan" not in encoded_identity

    root = tmp_path / "runtime"
    context = TenantContext("tenant-a", "project-a", "actor-a")
    bootstrap_status, _ = execute_document(
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="environment-bootstrap-0001",
        ),
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert bootstrap_status == 200

    tool_request = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "tool-environment", "blocks": []},
        key="tool-environment-0001",
    )
    first_status, _ = execute_document(
        tool_request,
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert first_status == 200
    tool_digest["value"] = "b" * 64
    drift_status, drift = execute_document(
        tool_request,
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert drift_status == 409
    assert drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"

    tool_digest["value"] = "a" * 64
    path_request = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "tool-path-environment", "blocks": []},
        key="tool-path-environment-0001",
    )
    path_status, _ = execute_document(
        path_request,
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert path_status == 200
    tool_path["value"] = "/private/alternate-host-bin/elmos-malware-scan"
    path_drift_status, path_drift = execute_document(
        path_request,
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert path_drift_status == 409
    assert path_drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"

    tool_path["value"] = "/private/host-secret-bin/elmos-malware-scan"
    provider_request = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "password-provider-environment", "blocks": []},
        key="provider-environment-0001",
    )
    provider_status, _ = execute_document(
        provider_request,
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert provider_status == 200
    password_provider_digest["value"] = "d" * 64
    provider_drift_status, provider_drift = execute_document(
        provider_request,
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert provider_drift_status == 409
    assert provider_drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"


def test_execution_api_never_serializes_provider_host_executable_paths(tmp_path: Path) -> None:
    host_tool_root = "/private/host-only/provider-tools"

    class ApiSandbox:
        def execute(self, **invocation: object) -> CommandReceipt:
            tool = str(invocation["tool"])
            if tool == ToolCapability.MALWARE_SCAN.value:
                output = {"verdict": "CLEAN", "findings": []}
            else:
                output = {
                    "regions": [
                        {
                            "text": "API receipt",
                            "bbox": [1, 2, 30, 10],
                            "confidence": 0.9,
                        }
                    ]
                }
            return CommandReceipt(
                tool=tool,
                executable_sha256="a" * 64,
                exit_code=0,
                stdout=json.dumps(output).encode(),
                sandboxed=True,
                network_allowed=False,
            )

    sandbox = ApiSandbox()

    def factory(database: Path, cas_root: Path):
        return create_runtime(
            database,
            cas_root,
            sandbox_executor=sandbox,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: {
                    "path": f"{host_tool_root}/elmos-malware-scan",
                    "sha256": "a" * 64,
                },
                ToolCapability.OCR: {
                    "path": f"{host_tool_root}/tesseract",
                    "sha256": "a" * 64,
                },
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )

    root = tmp_path / "runtime"
    context = TenantContext("tenant-a", "project-a", "actor-a")
    runtime = factory(root / "intake.sqlite3", root / "cas")
    try:
        runtime.handle(
            "elmos-multimodal-input-orchestrator",
            context,
            {"operation": "bootstrap_project", "idempotency_key": "api-path-bootstrap"},
        )
        session = runtime.handle(
            "elmos-multimodal-input-orchestrator",
            context,
            {"operation": "create_session", "idempotency_key": "api-path-session"},
        )
        content = b"\x89PNG\r\n\x1a\n" + b"x" * 8
        digest = hashlib.sha256(content).hexdigest()
        started = runtime.handle(
            "elmos-secure-resumable-upload",
            context,
            {
                "operation": "start",
                "session_id": session["session_id"],
                "display_name": "api.png",
                "declared_media_type": "image/png",
                "expected_size": len(content),
                "expected_sha256": digest,
                "part_size": len(content),
                "idempotency_key": "api-path-upload-start",
            },
        )
        runtime.handle(
            "elmos-secure-resumable-upload",
            context,
            {
                "operation": "upload_part",
                "upload_session_id": started["upload_session_id"],
                "part_number": 0,
                "byte_offset": 0,
                "data_base64": base64.b64encode(content).decode("ascii"),
                "sha256": digest,
                "idempotency_key": "api-path-upload-part",
            },
        )
        runtime.handle(
            "elmos-secure-resumable-upload",
            context,
            {
                "operation": "commit",
                "upload_session_id": started["upload_session_id"],
                "idempotency_key": "api-path-upload-commit",
            },
        )
        asset_id = started["asset_id"]
    finally:
        runtime.close()

    status, body = execute_document(
        request(
            "elmos-image-ocr-and-preprocessing",
            "process_asset",
            {"asset_id": asset_id},
            key="api-path-process",
        ),
        root,
        bound_context=context,
        runtime_factory=factory,
    )
    assert status == 200
    encoded = canonical_json(body)
    assert host_tool_root not in encoded
    assert body["output"]["report"]["provider_receipt"]["executable"] == "tesseract"
    assert (
        body["output"]["report"]["metadata"]["malware_scan"]["receipt"]["executable"]
        == "elmos-malware-scan"
    )


def test_execution_receipt_is_bound_to_runtime_factory_identity(tmp_path: Path) -> None:
    def first_factory(database: Path, cas_root: Path):
        return create_runtime(database, cas_root)

    def second_factory(database: Path, cas_root: Path):
        return create_runtime(database, cas_root)

    root = tmp_path / "runtime"
    context = TenantContext("tenant-a", "project-a", "actor-a")
    bootstrap_status, _ = execute_document(
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="factory-bootstrap-0001",
        ),
        root,
        bound_context=context,
        runtime_factory=first_factory,
    )
    assert bootstrap_status == 200
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "factory-environment", "blocks": []},
        key="factory-environment-0001",
    )
    first_status, _ = execute_document(
        document,
        root,
        bound_context=context,
        runtime_factory=first_factory,
    )
    assert first_status == 200
    drift_status, drift = execute_document(
        document,
        root,
        bound_context=context,
        runtime_factory=second_factory,
    )
    assert drift_status == 409
    assert drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"


def test_execute_document_requires_exact_trusted_identity_binding(tmp_path: Path) -> None:
    document = request(
        "elmos-multimodal-input-orchestrator",
        "bootstrap_project",
        {},
        key="bound-context-0001",
    )
    status, body = execute_document(
        document,
        tmp_path / "runtime",
        bound_context=TenantContext("tenant-b", "project-a", "actor-a"),
    )
    assert status == 403
    assert body["status"] == "BLOCKED"
    assert body["code"] == "BOUND_IDENTITY_MISMATCH"


def test_domain_skill_cannot_bypass_project_acl(tmp_path: Path) -> None:
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"blocks": []},
        key="domain-acl-0001",
    )
    status, body = execute_document(
        document,
        tmp_path / "runtime",
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert status == 403
    assert body["status"] == "BLOCKED"
    assert body["code"] == "INTAKE_PROJECT_ACCESS_DENIED"


def test_execution_receipt_replays_exact_request_and_rejects_payload_drift(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="receipt-bootstrap-0001",
        ),
    )
    original = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {
            "document_id": "document-a",
            "blocks": [{"id": "block-a", "type": "paragraph", "text": "first", "order": 0}],
        },
        key="receipt-domain-0001",
    )
    first_status, first = execute_document(
        original,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    replay_status, replay = execute_document(
        {**original, "trace_id": "trace-retry-after-response-loss"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == replay_status == 200
    assert replay["trace_id"] == "trace-retry-after-response-loss"
    assert first["trace_id"] != replay["trace_id"]
    assert first["request_digest"] == replay["request_digest"]
    assert first["output"] == replay["output"]
    assert first["result_digest"] != replay["result_digest"]

    drifted = dict(original)
    drifted["input"] = {
        "document_id": "document-a",
        "blocks": [{"id": "block-a", "type": "paragraph", "text": "changed", "order": 0}],
    }
    drift_status, drift = execute_document(
        drifted,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert drift_status == 409
    assert drift["status"] == "BLOCKED"
    assert drift["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"


def test_execution_receipt_tamper_and_legacy_rows_are_never_resigned(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="receipt-integrity-bootstrap-0001",
        ),
    )
    original = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "receipt-integrity-document", "blocks": []},
        key="receipt-integrity-domain-0001",
    )
    first_status, first = execute_document(
        original,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == 200
    database = root / "intake.sqlite3"
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            """
            SELECT response_json,response_digest FROM skill_execution_receipts
             WHERE skill=? AND idempotency_key=?
            """,
            (
                "elmos-unified-multimodal-content-ir",
                "receipt-integrity-domain-0001",
            ),
        ).fetchone()
        assert stored is not None
        original_json, original_response_digest = stored
        assert original_json == canonical_json(first)
        assert original_response_digest == hashlib.sha256(original_json.encode()).hexdigest()

        # Recompute only the storage digest, leaving the public result_digest
        # stale.  The CLI must validate the stored public envelope before it
        # changes trace_id and must not bless these bytes with a fresh digest.
        tampered = json.loads(original_json)
        tampered["output"]["tampered_after_completion"] = True
        tampered_json = canonical_json(tampered)
        connection.execute(
            """
            UPDATE skill_execution_receipts
               SET response_json=?,response_digest=?
             WHERE skill=? AND idempotency_key=?
            """,
            (
                tampered_json,
                hashlib.sha256(tampered_json.encode()).hexdigest(),
                "elmos-unified-multimodal-content-ir",
                "receipt-integrity-domain-0001",
            ),
        )

    tampered_status, tampered_replay = execute_document(
        {**original, "trace_id": "trace-receipt-tampered-replay"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert tampered_status == 500
    assert tampered_replay["code"] == "EXECUTION_RESULT_CONTRACT_INVALID"

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE skill_execution_receipts
               SET response_json=?,response_digest=NULL
             WHERE skill=? AND idempotency_key=?
            """,
            (
                original_json,
                "elmos-unified-multimodal-content-ir",
                "receipt-integrity-domain-0001",
            ),
        )
    legacy_status, legacy_replay = execute_document(
        {**original, "trace_id": "trace-receipt-legacy-replay"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert legacy_status == 200
    assert legacy_replay["status"] == "BLOCKED"
    assert legacy_replay["code"] == "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED"
    assert legacy_replay["retryable"] is False


def test_bootstrap_has_outer_durable_receipt_and_execution_heartbeat(tmp_path: Path, monkeypatch) -> None:
    from elmos_multimodal_intake.store import IntakeStore

    renewals: list[tuple[str, str]] = []
    original_renew = IntakeStore.renew_skill_execution

    def observed_renew(self: IntakeStore, context, **values):
        renewals.append((str(values["skill"]), str(values["idempotency_key"])))
        return original_renew(self, context, **values)

    monkeypatch.setattr(IntakeStore, "renew_skill_execution", observed_renew)
    root = tmp_path / "runtime"
    original = request(
        "elmos-multimodal-input-orchestrator",
        "bootstrap_project",
        {},
        key="durable-bootstrap-0001",
    )
    first_status, first = execute_document(
        original,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    replay_status, replay = execute_document(
        {**original, "trace_id": "trace-bootstrap-response-loss"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == replay_status == 200
    assert replay["trace_id"] == "trace-bootstrap-response-loss"
    assert first["trace_id"] != replay["trace_id"]
    assert first["request_digest"] == replay["request_digest"]
    assert first["output"] == replay["output"]
    assert first["result_digest"] != replay["result_digest"]
    assert renewals == [
        ("elmos-multimodal-input-orchestrator", "durable-bootstrap-0001")
    ]

    drifted_status, drifted = execute_document(
        {**original, "input": {"unexpected": True}},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert drifted_status == 422
    assert drifted["code"] == "OPERATION_INPUT_FIELDS_INVALID"


def test_outer_receipt_releases_a_side_effect_free_claim_when_initial_renewal_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from elmos_multimodal_intake.store import IntakeStore

    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="renew-release-bootstrap-0001",
        ),
    )
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "renew-release-document", "blocks": []},
        key="renew-release-domain-0001",
    )
    original_renew = IntakeStore.renew_skill_execution
    original_release = IntakeStore.release_skill_execution
    renewal_attempts = 0
    releases = 0

    def fail_first_renewal(self: IntakeStore, context, **values):
        nonlocal renewal_attempts
        renewal_attempts += 1
        if renewal_attempts == 1:
            raise ValidationError("TEST_INITIAL_RENEWAL_FAILED")
        return original_renew(self, context, **values)

    def observe_release(self: IntakeStore, context, **values):
        nonlocal releases
        releases += 1
        return original_release(self, context, **values)

    monkeypatch.setattr(IntakeStore, "renew_skill_execution", fail_first_renewal)
    monkeypatch.setattr(IntakeStore, "release_skill_execution", observe_release)
    failed_status, failed = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert failed_status == 422
    assert failed["code"] == "TEST_INITIAL_RENEWAL_FAILED"
    assert releases == 1

    retry_status, retry = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert retry_status == 200
    assert retry["status"] == "PARTIAL"
    assert retry["code"] == "CONTENT_IR_REVIEW_REQUIRED"
    assert renewal_attempts == 2


def test_outer_receipt_terminally_reconciles_an_exception_after_dispatch_starts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from elmos_multimodal_intake.skill_runtime import SkillDispatcher

    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="dispatch-reconcile-bootstrap-0001",
        ),
    )
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "dispatch-reconcile-document", "blocks": []},
        key="dispatch-reconcile-domain-0001",
    )
    dispatch_calls = 0

    def fail_after_dispatch_started(self: SkillDispatcher, skill, internal_request):
        nonlocal dispatch_calls
        dispatch_calls += 1
        raise RuntimeError("provider response was lost")

    monkeypatch.setattr(SkillDispatcher, "dispatch", fail_after_dispatch_started)
    first_status, first = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == 200
    assert first["status"] == "BLOCKED"
    assert first["code"] == "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED"
    assert first["retryable"] is False
    assert first["output"]["reconciliation"] == {
        "state": "REQUIRED",
        "automatic_retry_allowed": False,
        "reason": "DISPATCH_OUTCOME_UNCONFIRMED",
    }

    replay_status, replay = execute_document(
        {**document, "trace_id": "trace-dispatch-reconcile-retry"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert replay_status == 200
    assert replay["status"] == "BLOCKED"
    assert replay["code"] == "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED"
    assert replay["trace_id"] == "trace-dispatch-reconcile-retry"
    assert dispatch_calls == 1


def test_outer_receipt_terminally_reconciles_heartbeat_uncertainty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import elmos_multimodal_intake.cli as cli
    from elmos_multimodal_intake.skill_runtime import SkillDispatcher
    from elmos_multimodal_intake.store import IntakeStore

    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="heartbeat-reconcile-bootstrap-0001",
        ),
    )
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "heartbeat-reconcile-document", "blocks": []},
        key="heartbeat-reconcile-domain-0001",
    )
    original_renew = IntakeStore.renew_skill_execution
    original_dispatch = SkillDispatcher.dispatch
    heartbeat_failed = threading.Event()
    renewals = 0
    dispatch_calls = 0

    def fail_heartbeat(self: IntakeStore, context, **values):
        nonlocal renewals
        renewals += 1
        if renewals > 1:
            heartbeat_failed.set()
            raise ValidationError("TEST_HEARTBEAT_FAILED")
        return original_renew(self, context, **values)

    def wait_for_heartbeat(self: SkillDispatcher, skill, internal_request):
        nonlocal dispatch_calls
        dispatch_calls += 1
        assert heartbeat_failed.wait(timeout=2)
        return original_dispatch(self, skill, internal_request)

    monkeypatch.setattr(cli, "EXECUTION_HEARTBEAT_SECONDS", 0.001)
    monkeypatch.setattr(IntakeStore, "renew_skill_execution", fail_heartbeat)
    monkeypatch.setattr(SkillDispatcher, "dispatch", wait_for_heartbeat)
    first_status, first = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == 200
    assert first["status"] == "BLOCKED"
    assert first["code"] == "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED"
    assert first["output"]["reconciliation"]["reason"] == "DISPATCH_OUTCOME_UNCONFIRMED"
    assert dispatch_calls == 1

    replay_status, replay = execute_document(
        {**document, "trace_id": "trace-heartbeat-reconcile-retry"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert replay_status == 200
    assert replay["code"] == "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED"
    assert dispatch_calls == 1


def test_outer_receipt_retries_only_fenced_completion_after_commit_response_loss(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from elmos_multimodal_intake.skill_runtime import SkillDispatcher
    from elmos_multimodal_intake.store import IntakeStore

    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="completion-loss-bootstrap-0001",
        ),
    )
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "completion-loss-document", "blocks": []},
        key="completion-loss-domain-0001",
    )
    original_complete = IntakeStore.complete_skill_execution
    original_dispatch = SkillDispatcher.dispatch
    completion_calls = 0
    dispatch_calls = 0

    def commit_then_lose_response(self: IntakeStore, context, **values):
        nonlocal completion_calls
        completion_calls += 1
        stored = original_complete(self, context, **values)
        if completion_calls == 1:
            raise RuntimeError("committed SQLite response was lost")
        return stored

    def observe_dispatch(self: SkillDispatcher, skill, internal_request):
        nonlocal dispatch_calls
        dispatch_calls += 1
        return original_dispatch(self, skill, internal_request)

    monkeypatch.setattr(IntakeStore, "complete_skill_execution", commit_then_lose_response)
    monkeypatch.setattr(SkillDispatcher, "dispatch", observe_dispatch)
    first_status, first = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == 200
    assert first["status"] == "PARTIAL"
    assert first["code"] == "CONTENT_IR_REVIEW_REQUIRED"
    assert completion_calls == 2
    assert dispatch_calls == 1

    replay_status, replay = execute_document(
        {**document, "trace_id": "trace-completion-loss-replay"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert replay_status == 200
    assert replay["status"] == "PARTIAL"
    assert replay["code"] == "CONTENT_IR_REVIEW_REQUIRED"
    assert replay["trace_id"] == "trace-completion-loss-replay"
    assert dispatch_calls == 1


def test_outer_receipt_persistent_completion_failure_never_redispatches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from elmos_multimodal_intake.skill_runtime import SkillDispatcher
    from elmos_multimodal_intake.store import IntakeStore

    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="completion-failure-bootstrap-0001",
        ),
    )
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "completion-failure-document", "blocks": []},
        key="completion-failure-domain-0001",
    )
    original_complete = IntakeStore.complete_skill_execution
    original_dispatch = SkillDispatcher.dispatch
    dispatch_calls = 0

    def fail_completion(self: IntakeStore, context, **values):
        raise RuntimeError("persistent SQLite completion failure")

    def observe_dispatch(self: SkillDispatcher, skill, internal_request):
        nonlocal dispatch_calls
        dispatch_calls += 1
        return original_dispatch(self, skill, internal_request)

    monkeypatch.setattr(IntakeStore, "complete_skill_execution", fail_completion)
    monkeypatch.setattr(SkillDispatcher, "dispatch", observe_dispatch)
    failed_status, _failed = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert failed_status == 500
    assert dispatch_calls == 1

    monkeypatch.setattr(IntakeStore, "complete_skill_execution", original_complete)
    replay_status, replay = execute_document(
        {**document, "trace_id": "trace-completion-failure-replay"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert replay_status == 200
    assert replay["status"] == "BLOCKED"
    assert replay["code"] == "EXECUTION_OUTCOME_RECONCILIATION_REQUIRED"
    assert replay["output"]["reconciliation"]["reason"] == (
        "PRIOR_DISPATCH_OUTCOME_UNCONFIRMED"
    )
    assert replay["retryable"] is False
    assert dispatch_calls == 1


def test_host_owned_trusted_context_reaches_domain_handler_and_rejects_writable_config(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="trusted-bootstrap-0001",
        ),
    )
    config = root / TRUSTED_CONTEXT_FILENAME
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "bindings": [
                    {
                        "tenant_id": "tenant-a",
                        "project_id": "project-a",
                        "actor_id": "actor-a",
                        "context_epoch": "telemetry-policy-1",
                        "policy": {
                            "observability": {
                                "required_stages": ["upload"],
                                "label_cardinality_limit": 10,
                                "policy_version": "telemetry-v1",
                            }
                        },
                        "capabilities": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config.chmod(0o600)
    observed = execute(
        root,
        request(
            "elmos-multimodal-observability",
            "observe",
            {
                "events": [
                    {
                        "event_id": "event-a",
                        "event_type": "upload.complete",
                        "labels": {"stage": "upload", "status": "ready"},
                        "attributes": {},
                    }
                ]
            },
            key="trusted-observe-0001",
        ),
    )
    assert observed["status"] == "SUCCEEDED"
    assert observed["output"]["policy_version"] == "telemetry-v1"

    config.chmod(0o666)
    rejected_status, rejected = execute_document(
        request(
            "elmos-multimodal-observability",
            "observe",
            {"events": []},
            key="trusted-observe-0002",
        ),
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert rejected_status == 422
    assert rejected["code"] == "TRUSTED_CONTEXT_FILE_INVALID"


def test_execution_receipt_is_invalidated_by_trusted_context_epoch_change(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="epoch-bootstrap-0001",
        ),
    )
    config = root / TRUSTED_CONTEXT_FILENAME

    def write_epoch(epoch: str) -> None:
        config.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "bindings": [
                        {
                            "tenant_id": "tenant-a",
                            "project_id": "project-a",
                            "actor_id": "actor-a",
                            "context_epoch": epoch,
                            "policy": {},
                            "capabilities": {},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        config.chmod(0o600)

    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {
            "document_id": "epoch-document",
            "blocks": [
                {
                    "id": "epoch-block",
                    "type": "paragraph",
                    "text": "epoch-bound result",
                    "anchors": [
                        {
                            "anchor_id": "epoch-anchor",
                            "asset_id": "epoch-asset",
                            "asset_digest": "sha256:" + "a" * 64,
                            "asset_version": 1,
                            "locator": {
                                "kind": "text_range",
                                "start_line": 1,
                                "end_line": 1,
                            },
                        }
                    ],
                }
            ],
        },
        key="epoch-domain-0001",
    )
    write_epoch("epoch-1")
    first_status, _ = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == 200

    write_epoch("epoch-2")
    replay_status, replay = execute_document(
        {**document, "trace_id": "trace-after-policy-epoch-change"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert replay_status == 409
    assert replay["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"


def test_trusted_context_rejects_coerced_identity_and_broken_symlink(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="strict-trust-bootstrap-0001",
        ),
    )
    config = root / TRUSTED_CONTEXT_FILENAME
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "bindings": [
                    {
                        "tenant_id": 123,
                        "project_id": "project-a",
                        "actor_id": "actor-a",
                        "context_epoch": "strict-trust-v1",
                        "policy": {},
                        "capabilities": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config.chmod(0o600)
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "strict-trust-document", "blocks": []},
        key="strict-trust-domain-0001",
    )

    status, rejected = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert status == 422
    assert rejected["code"] == "TRUSTED_CONTEXT_SCHEMA_INVALID"

    config.unlink()
    config.symlink_to(root / "missing-trusted-context.json")
    status, rejected = execute_document(
        {**document, "idempotency_key": "strict-trust-domain-0002"},
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert status == 422
    assert rejected["code"] == "TRUSTED_CONTEXT_FILE_INVALID"


def test_execution_receipt_is_bound_to_runtime_build_digest(tmp_path: Path, monkeypatch) -> None:
    import elmos_multimodal_intake.cli as cli

    root = tmp_path / "runtime"
    execute(
        root,
        request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="build-bootstrap-0001",
        ),
    )
    document = request(
        "elmos-unified-multimodal-content-ir",
        "normalize",
        {"document_id": "build-document", "blocks": []},
        key="build-domain-0001",
    )
    first_status, _ = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert first_status == 200

    monkeypatch.setattr(cli, "_runtime_build_digest", lambda: "f" * 64)
    replay_status, replay = execute_document(
        document,
        root,
        bound_context=TenantContext("tenant-a", "project-a", "actor-a"),
    )
    assert replay_status == 409
    assert replay["code"] == "SKILL_EXECUTION_IDEMPOTENCY_CONFLICT"


def test_instance_dispatchers_do_not_cross_contaminate_bridges() -> None:
    from elmos_multimodal_intake.skill_runtime import RuntimeContext, SkillDispatcher

    class Bridge:
        def __init__(self, root_id: str) -> None:
            self.root_id = root_id

        def handle(
            self,
            _skill_name: str,
            _ctx: RuntimeContext,
            _payload: dict[str, object],
        ) -> dict[str, object]:
            return {
                "state": "SUCCEEDED",
                "code": "OK",
                "outputs": {"root_id": self.root_id},
                "metrics": {},
                "retryable": False,
            }

    skill = "elmos-multimodal-input-orchestrator"
    first = SkillDispatcher()
    second = SkillDispatcher()
    first.register_bridge(skill, Bridge("root-a"))
    second.register_bridge(skill, Bridge("root-b"))
    internal = {
        "schema_version": "1.0",
        "request_id": "request-0001",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
        "idempotency_key": "idempotency-0001",
        "trace_id": "trace-0001",
        "inputs": {"operation": "bootstrap_project"},
        "policy": {},
        "capabilities": {},
    }
    assert first.dispatch(skill, internal)["outputs"]["root_id"] == "root-a"
    assert second.dispatch(skill, internal)["outputs"]["root_id"] == "root-b"
    assert first.dispatch(skill, internal)["outputs"]["root_id"] == "root-a"


def test_instance_dispatchers_keep_contextvar_bridges_isolated_concurrently() -> None:
    from elmos_multimodal_intake.skill_runtime import RuntimeContext, SkillDispatcher

    rendezvous = threading.Barrier(2)

    class Bridge:
        def __init__(self, root_id: str) -> None:
            self.root_id = root_id

        def handle(
            self,
            _skill_name: str,
            _ctx: RuntimeContext,
            _payload: dict[str, object],
        ) -> dict[str, object]:
            rendezvous.wait(timeout=2)
            return {
                "state": "SUCCEEDED",
                "code": "OK",
                "outputs": {"root_id": self.root_id},
                "metrics": {},
                "retryable": False,
            }

    skill = "elmos-multimodal-input-orchestrator"
    dispatchers = [SkillDispatcher(), SkillDispatcher()]
    dispatchers[0].register_bridge(skill, Bridge("root-a"))
    dispatchers[1].register_bridge(skill, Bridge("root-b"))
    results: list[str | None] = [None, None]
    errors: list[BaseException] = []

    def run(index: int) -> None:
        try:
            internal = {
                "schema_version": "1.0",
                "request_id": f"request-concurrent-{index}",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "actor_id": "actor-a",
                "idempotency_key": f"idempotency-concurrent-{index}",
                "trace_id": f"trace-concurrent-{index}",
                "inputs": {"operation": "bootstrap_project"},
                "policy": {},
                "capabilities": {},
            }
            results[index] = str(dispatchers[index].dispatch(skill, internal)["outputs"]["root_id"])
        except BaseException as error:
            errors.append(error)

    workers = [threading.Thread(target=run, args=(index,)) for index in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)
    assert all(not worker.is_alive() for worker in workers)
    assert errors == []
    assert results == ["root-a", "root-b"]


def test_markdown_upload_and_durable_processing_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    orchestrator = "elmos-multimodal-input-orchestrator"
    upload = "elmos-secure-resumable-upload"
    bootstrapped = execute(root, request(orchestrator, "bootstrap_project", {}, key="bootstrap-0001"))
    assert bootstrapped["status"] == "SUCCEEDED"

    created = execute(
        root,
        request(orchestrator, "create_session", {"requested_role": "PRIMARY"}, key="session-0001"),
    )
    session_id = created["output"]["session_id"]
    content = b"# Requirement\nUploads must resume.\n"
    digest = hashlib.sha256(content).hexdigest()
    started = execute(
        root,
        request(
            upload,
            "start",
            {
                "session_id": session_id,
                "display_name": "requirements/input.md",
                "declared_media_type": "text/markdown",
                "expected_size": len(content),
                "expected_sha256": digest,
                "part_size": len(content),
            },
            key="upload-start-0001",
        ),
    )
    upload_id = started["output"]["upload_session_id"]
    asset_id = started["output"]["asset_id"]
    part = execute(
        root,
        request(
            upload,
            "upload_part",
            {
                "upload_session_id": upload_id,
                "part_number": 0,
                "byte_offset": 0,
                "sha256": digest,
                "data_b64": base64.b64encode(content).decode("ascii"),
            },
            key="upload-part-0001",
        ),
    )
    assert part["output"]["status"] == "ACCEPTED"
    committed = execute(
        root,
        request(upload, "commit", {"upload_session_id": upload_id}, key="upload-commit-0001"),
    )
    assert committed["output"]["asset_id"] == asset_id

    processed = execute(
        root,
        request(
            orchestrator,
            "process_session",
            {
                "session_id": session_id,
                "max_attempts": 3,
                "expected_asset_generation_digest": hashlib.sha256(asset_id.encode("utf-8")).hexdigest(),
            },
            key="process-session-0001",
        ),
    )
    assert processed["status"] == "PARTIAL"
    assert processed["output"]["job"]["result_status"] == "NEEDS_REVIEW"
    assert processed["output"]["assets"][0]["status"] == "NEEDS_REVIEW"
    report_summary = processed["output"]["reports"][asset_id]
    assert report_summary["block_count"] > 0
    assert report_summary["anchor_count"] > 0
    assert "blocks" not in report_summary
    assert processed["output"]["assets_truncated"] is False
    assert processed["output"]["reports_truncated"] is False
    job_id = processed["output"]["job_id"]
    resumed = execute(
        root,
        request(orchestrator, "resume_job", {"job_id": job_id}, key="resume-job-0001"),
    )
    assert resumed["output"]["reports"][asset_id]["block_count"] > 0
    assert "blocks" not in resumed["output"]["reports"][asset_id]
    cancelled_terminal = execute(
        root,
        request(orchestrator, "cancel_job", {"job_id": job_id}, key="cancel-job-0001"),
    )
    assert "blocks" not in cancelled_terminal["output"]["reports"][asset_id]
    assert processed["external_evidence"] == "NOT_RUN"
    assert processed["certification"] == "NOT_CERTIFIED"


def test_http_adapter_requires_token_and_exact_bound_identity(tmp_path: Path) -> None:
    token = "test-token-which-is-at-least-thirty-two-characters"
    handler = _server_class(
        data_root=tmp_path / "runtime",
        bearer_token=token,
        tenant_id="tenant-a",
        project_id="project-a",
        actor_id="actor-a",
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            urlopen(base + CAPABILITIES_PATH, timeout=2)
        except HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("unauthenticated capabilities request unexpectedly succeeded")

        capabilities = Request(
            base + CAPABILITIES_PATH,
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(capabilities, timeout=2) as response:
            body = json.loads(response.read())
        assert body["skill_count"] == 50

        mismatched = request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {},
            key="http-boundary-0001",
            tenant="tenant-b",
        )
        post = Request(
            base + "/api/v1/multimodal-intake/execute",
            data=json.dumps(mismatched).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            urlopen(post, timeout=2)
        except HTTPError as error:
            assert error.code == 403
            assert json.loads(error.read())["code"] == "BOUND_IDENTITY_MISMATCH"
        else:
            raise AssertionError("cross-bound identity request unexpectedly succeeded")

        def assert_rejected(raw: bytes, status: int, code: str, *, content_type: str = "application/json") -> None:
            invalid = Request(
                base + "/api/v1/multimodal-intake/execute",
                data=raw,
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type,
                },
            )
            with pytest.raises(HTTPError) as caught:
                urlopen(invalid, timeout=2)
            assert caught.value.code == status
            assert json.loads(caught.value.read())["code"] == code

        unsafe_integer = request(
            "elmos-multimodal-input-orchestrator",
            "bootstrap_project",
            {"unsafe": 2**53},
            key="http-unsafe-integer-0001",
        )
        assert_rejected(
            json.dumps(unsafe_integer).encode("utf-8"),
            400,
            "MULTIMODAL_REQUEST_JSON_INVALID",
        )
        assert_rejected(
            b'{"schema_version":"1.0.0","schema_version":"1.0.0"}',
            400,
            "MULTIMODAL_REQUEST_JSON_INVALID",
        )
        assert_rejected(
            json.dumps(request(
                "elmos-multimodal-input-orchestrator",
                "bootstrap_project",
                {"text": "\ud800"},
                key="http-unicode-0001",
            )).encode("utf-8"),
            422,
            "REQUEST_JSON_UNICODE_INVALID",
        )
        assert_rejected(b"{}", 415, "JSON_CONTENT_TYPE_REQUIRED", content_type="application/jsonp")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_progress_sse_is_scoped_canonical_resumable_and_has_no_client_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime"
    context_a = TenantContext("tenant-a", "project-a", "actor-a")
    context_b = TenantContext("tenant-b", "project-b", "actor-b")
    runtime = create_runtime(root / "intake.sqlite3", root / "cas")
    try:
        runtime.store.bootstrap_project(context_a)
        runtime.store.bootstrap_project(context_b)
        runtime.store.apply_durable_transition(
            context_a,
            task_id="task-visible-a",
            idempotency_key="progress-running-a",
            target_state="RUNNING",
            payload={"private": "must-never-enter-progress"},
        )
        runtime.store.apply_durable_transition(
            context_a,
            task_id="task-visible-a",
            idempotency_key="progress-paused-a",
            current_state="RUNNING",
            target_state="PAUSED",
            payload={"private": "must-never-enter-progress-either"},
        )
        runtime.store.apply_durable_transition(
            context_b,
            task_id="task-private-b",
            idempotency_key="progress-running-b",
            target_state="RUNNING",
            payload={"tenant_secret": "cross-tenant-secret"},
        )
        session = runtime.store.create_session(
            context_a,
            idempotency_key="progress-job-session-a",
        )
        job = runtime.store.create_job(
            context_a,
            session.session_id,
            idempotency_key="progress-job-a",
            request_digest="a" * 64,
        )
        private_session = runtime.store.create_session(
            context_b,
            idempotency_key="progress-job-session-b",
        )
        private_job = runtime.store.create_job(
            context_b,
            private_session.session_id,
            idempotency_key="progress-job-b",
            request_digest="b" * 64,
        )
    finally:
        runtime.close()

    token = "progress-sse-token-which-is-at-least-thirty-two"
    handler = _server_class(
        data_root=root,
        bearer_token=token,
        tenant_id=context_a.tenant_id,
        project_id=context_a.project_id,
        actor_id=context_a.actor_id,
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    task_path = f"{PROGRESS_TASK_EVENTS_PREFIX}task-visible-a/events"
    scope_headers = {
        "Authorization": f"Bearer {token}",
        _BOUND_TENANT_HEADER: context_a.tenant_id,
        _BOUND_PROJECT_HEADER: context_a.project_id,
        _BOUND_ACTOR_HEADER: context_a.actor_id,
        "Accept": "text/event-stream",
    }
    try:
        unauthenticated = Request(
            base + task_path,
            headers={"Accept": "text/event-stream"},
        )
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(unauthenticated, timeout=2)
        assert unauthorized.value.code == 401

        initial = Request(
            base + task_path,
            headers=scope_headers,
        )
        with urlopen(initial, timeout=2) as response:
            initial_body = response.read()
            assert response.headers.get_content_type() == "text/event-stream"
            assert response.headers["Cache-Control"] == "private, no-store, max-age=0"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Accel-Buffering"] == "no"
            assert response.headers["Connection"].lower() == "close"
        records = _sse_records(initial_body)
        assert [item[1] for item in records] == ["progress", "progress"]
        assert [item[2]["state"] for item in records] == ["RUNNING", "PAUSED"]
        assert [item[2]["sequence_number"] for item in records] == [1, 2]
        assert all(item[0] == item[2]["cursor"] for item in records)
        serialized = initial_body.decode("utf-8")
        assert "actor-a" not in serialized
        assert "tenant-a" not in serialized
        assert "project-a" not in serialized
        assert "must-never-enter-progress" not in serialized
        first_cursor = records[0][0]
        assert first_cursor is not None
        first_document = records[0][2]
        digest_document = {
            key: value
            for key, value in first_document.items()
            if key not in {"content_digest", "cursor"}
        }
        assert first_document["content_digest"] == (
            "sha256:" + hashlib.sha256(canonical_json(digest_document).encode("utf-8")).hexdigest()
        )

        resumed = Request(
            base + task_path,
            headers={
                **scope_headers,
                "Last-Event-ID": first_cursor,
            },
        )
        with urlopen(resumed, timeout=2) as response:
            resumed_records = _sse_records(response.read())
        assert len(resumed_records) == 1
        assert resumed_records[0][2]["state"] == "PAUSED"
        assert resumed_records[0][2]["sequence_number"] == 2

        query_resumed = Request(
            base + task_path + f"?cursor={first_cursor}",
            headers=scope_headers,
        )
        with urlopen(query_resumed, timeout=2) as response:
            assert _sse_records(response.read())[0][2]["state"] == "PAUSED"

        tampered_cursor = first_cursor[:-1] + ("0" if first_cursor[-1] != "0" else "1")
        diverged = Request(
            base + task_path,
            headers={
                **scope_headers,
                "Last-Event-ID": tampered_cursor,
            },
        )
        with pytest.raises(HTTPError) as diverged_error:
            urlopen(diverged, timeout=2)
        assert diverged_error.value.code == 409
        assert json.loads(diverged_error.value.read())["code"] == "PROGRESS_CURSOR_DIVERGED"

        invented_zero_cursor = Request(
            base + task_path + "?cursor=p1-0-" + "0" * 64,
            headers=scope_headers,
        )
        with pytest.raises(HTTPError) as zero_cursor_error:
            urlopen(invented_zero_cursor, timeout=2)
        assert zero_cursor_error.value.code == 400
        assert json.loads(zero_cursor_error.value.read())["code"] == "PROGRESS_CURSOR_INVALID"

        cross_tenant = Request(
            base + f"{PROGRESS_TASK_EVENTS_PREFIX}task-private-b/events",
            headers=scope_headers,
        )
        with urlopen(cross_tenant, timeout=2) as response:
            cross_body = response.read()
        cross_records = _sse_records(cross_body)
        assert len(cross_records) == 1
        assert cross_records[0][0] is None
        assert cross_records[0][1] == "heartbeat"
        assert cross_records[0][2]["status"] == "NO_CHANGE"
        assert b"tenant-b" not in cross_body
        assert b"actor-b" not in cross_body
        assert b"cross-tenant-secret" not in cross_body

        job_request = Request(
            base + f"{PROGRESS_JOB_EVENTS_PREFIX}{job.job_id}/events",
            headers=scope_headers,
        )
        with urlopen(job_request, timeout=2) as response:
            job_records = _sse_records(response.read())
        assert len(job_records) == 1
        assert job_records[0][2]["kind"] == "JOB_PROGRESS"
        assert job_records[0][2]["state"] == "QUEUED"
        job_cursor = job_records[0][0]
        assert job_cursor is not None
        job_heartbeat = Request(
            base + f"{PROGRESS_JOB_EVENTS_PREFIX}{job.job_id}/events",
            headers={
                **scope_headers,
                "Last-Event-ID": job_cursor,
            },
        )
        with urlopen(job_heartbeat, timeout=2) as response:
            heartbeat_records = _sse_records(response.read())
        assert heartbeat_records[0][0] is None
        assert heartbeat_records[0][1] == "heartbeat"
        assert heartbeat_records[0][2]["cursor"] == job_cursor

        private_job_request = Request(
            base + f"{PROGRESS_JOB_EVENTS_PREFIX}{private_job.job_id}/events",
            headers=scope_headers,
        )
        with pytest.raises(HTTPError) as private_job_error:
            urlopen(private_job_request, timeout=2)
        assert private_job_error.value.code == 404
        private_job_body = private_job_error.value.read()
        assert b"tenant-b" not in private_job_body
        assert b"actor-b" not in private_job_body

        no_authority = Request(
            base + task_path + "?tenant_id=tenant-b",
            headers=scope_headers,
        )
        with pytest.raises(HTTPError) as invalid_query:
            urlopen(no_authority, timeout=2)
        assert invalid_query.value.code == 400
        assert json.loads(invalid_query.value.read())["code"] == "PROGRESS_QUERY_INVALID"

        forbidden_post = Request(
            base + task_path,
            data=b"{}",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with pytest.raises(HTTPError) as wrong_method:
            urlopen(forbidden_post, timeout=2)
        assert wrong_method.value.code == 405
        assert wrong_method.value.headers["Allow"] == "GET"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_progress_websocket_is_strict_read_only_bounded_and_closes(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    context = TenantContext("tenant-a", "project-a", "actor-a")
    runtime = create_runtime(root / "intake.sqlite3", root / "cas")
    try:
        runtime.store.bootstrap_project(context)
        runtime.store.apply_durable_transition(
            context,
            task_id="task-websocket-a",
            idempotency_key="progress-websocket-running-a",
            target_state="RUNNING",
            payload={"client_command": "must-not-be-forwarded"},
        )
    finally:
        runtime.close()

    token = "progress-websocket-token-at-least-thirty-two"
    handler = _server_class(
        data_root=root,
        bearer_token=token,
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        actor_id=context.actor_id,
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def exchange(request_bytes: bytes) -> bytes:
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as connection:
            connection.sendall(request_bytes)
            connection.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = connection.recv(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks)

    path = f"{PROGRESS_TASK_WEBSOCKET_PREFIX}task-websocket-a"
    key = base64.b64encode(b"0123456789abcdef").decode("ascii")
    try:
        valid = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server.server_port}\r\n"
            f"Authorization: Bearer {token}\r\n"
            f"{_BOUND_TENANT_HEADER}: {context.tenant_id}\r\n"
            f"{_BOUND_PROJECT_HEADER}: {context.project_id}\r\n"
            f"{_BOUND_ACTOR_HEADER}: {context.actor_id}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {key}\r\n\r\n"
        ).encode("ascii")
        raw = exchange(valid)
        headers, frames = raw.split(b"\r\n\r\n", 1)
        assert headers.startswith(b"HTTP/1.1 101 ")
        expected_accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        )
        assert b"Sec-WebSocket-Accept: " + expected_accept in headers
        assert frames[0] == 0x81
        length_marker = frames[1] & 0x7F
        if length_marker <= 125:
            payload_offset = 2
            payload_length = length_marker
        else:
            assert length_marker == 126
            payload_offset = 4
            payload_length = int.from_bytes(frames[2:4], "big")
        document = json.loads(frames[payload_offset : payload_offset + payload_length])
        assert document["kind"] == "TASK_PROGRESS"
        assert document["state"] == "RUNNING"
        assert "actor_id" not in document
        assert "client_command" not in document
        assert frames[payload_offset + payload_length :] == b"\x88\x02\x03\xe8"

        malformed_key = valid.replace(
            f"Sec-WebSocket-Key: {key}".encode("ascii"),
            b"Sec-WebSocket-Key: not-base64",
        )
        invalid = exchange(malformed_key)
        invalid_headers, invalid_body = invalid.split(b"\r\n\r\n", 1)
        assert b" 400 " in invalid_headers.splitlines()[0]
        assert json.loads(invalid_body)["code"] == "PROGRESS_WEBSOCKET_KEY_INVALID"

        malformed_upgrade = valid.replace(b"Upgrade: websocket", b"Upgrade: h2c")
        invalid_upgrade = exchange(malformed_upgrade)
        upgrade_headers, upgrade_body = invalid_upgrade.split(b"\r\n\r\n", 1)
        assert b" 400 " in upgrade_headers.splitlines()[0]
        assert json.loads(upgrade_body)["code"] == "PROGRESS_WEBSOCKET_HANDSHAKE_INVALID"

        client_authority = valid.replace(
            f"GET {path} HTTP/1.1".encode("ascii"),
            f"GET {path}?provider=client-selected HTTP/1.1".encode("ascii"),
        )
        rejected = exchange(client_authority)
        rejected_headers, rejected_body = rejected.split(b"\r\n\r\n", 1)
        assert b" 400 " in rejected_headers.splitlines()[0]
        assert json.loads(rejected_body)["code"] == "PROGRESS_QUERY_INVALID"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_raw_http_server_rejects_non_loopback_bind_and_bool_port(tmp_path: Path) -> None:
    arguments = {
        "data_root": tmp_path / "runtime",
        "bearer_token": "t" * 32,
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "actor-a",
    }
    with pytest.raises(ValidationError, match="HTTP_BIND_LOOPBACK_REQUIRED"):
        serve(bind="0.0.0.0", port=8787, **arguments)
    with pytest.raises(ValidationError, match="HTTP_PORT_INVALID"):
        serve(bind="127.0.0.1", port=True, **arguments)


def test_http_adapter_uses_strict_json_for_unsupported_methods_and_short_bodies(
    tmp_path: Path,
) -> None:
    token = "strict-http-token-which-is-at-least-thirty-two"
    handler = _server_class(
        data_root=tmp_path / "runtime",
        bearer_token=token,
        tenant_id="tenant-a",
        project_id="project-a",
        actor_id="actor-a",
    )
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        unsupported = Request(
            base + CAPABILITIES_PATH,
            data=b"{}",
            method="PUT",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with pytest.raises(HTTPError) as caught:
            urlopen(unsupported, timeout=2)
        assert caught.value.code == 405
        assert caught.value.headers["Allow"] == "GET"
        assert caught.value.headers.get_content_type() == "application/json"
        unsupported_body = json.loads(caught.value.read())
        assert set(unsupported_body) == {
            "schema_version",
            "status",
            "code",
            "retryable",
            "trace_id",
        }
        assert unsupported_body.pop("trace_id").startswith("http-")
        assert unsupported_body == {
            "schema_version": "1.0.0",
            "status": "BLOCKED",
            "code": "MULTIMODAL_METHOD_NOT_ALLOWED",
            "retryable": False,
        }

        head = Request(
            base + CAPABILITIES_PATH,
            method="HEAD",
            headers={"Authorization": f"Bearer {token}"},
        )
        with pytest.raises(HTTPError) as caught_head:
            urlopen(head, timeout=2)
        assert caught_head.value.code == 405
        assert caught_head.value.headers["Allow"] == "GET"
        assert int(caught_head.value.headers["Content-Length"]) > 0
        assert caught_head.value.read() == b""

        unknown_method = Request(
            base + CAPABILITIES_PATH,
            method="PROPFIND",
            headers={"Authorization": f"Bearer {token}"},
        )
        with pytest.raises(HTTPError) as caught_unknown_method:
            urlopen(unknown_method, timeout=2)
        assert caught_unknown_method.value.code == 405
        assert caught_unknown_method.value.headers["Allow"] == "GET"
        assert json.loads(caught_unknown_method.value.read())["code"] == "MULTIMODAL_METHOD_NOT_ALLOWED"

        encoded_request = Request(
            base + "/api/v1/multimodal-intake/execute",
            data=b"not-actually-gzip",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )
        with pytest.raises(HTTPError) as caught_encoding:
            urlopen(encoded_request, timeout=2)
        assert caught_encoding.value.code == 415
        assert json.loads(caught_encoding.value.read())["code"] == (
            "MULTIMODAL_CONTENT_ENCODING_UNSUPPORTED"
        )

        short_document = canonical_json(
            request(
                "elmos-multimodal-input-orchestrator",
                "bootstrap_project",
                {},
                key="short-http-body-0001",
            )
        ).encode("utf-8")
        raw_request = (
            f"POST /api/v1/multimodal-intake/execute HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{server.server_port}\r\n"
            f"Authorization: Bearer {token}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(short_document) + 7}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii") + short_document
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as connection:
            connection.sendall(raw_request)
            connection.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while True:
                chunk = connection.recv(64 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        headers, body = b"".join(chunks).split(b"\r\n\r\n", 1)
        assert headers.startswith(b"HTTP/1.0 400 ")
        assert json.loads(body)["code"] == "MULTIMODAL_REQUEST_SIZE_INVALID"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cli_emit_keeps_newline_inside_cap_and_distinguishes_encoding_failure(
    monkeypatch,
) -> None:
    import elmos_multimodal_intake.cli as cli

    class Sink:
        def __init__(self) -> None:
            self.buffer = io.BytesIO()

    limit = 256
    baseline = {"payload": "", "_http_status": 200}
    padding = limit - len(canonical_json(baseline).encode("utf-8"))
    assert padding > 0
    exact_body = {"payload": "x" * padding}
    assert len(canonical_json({**exact_body, "_http_status": 200}).encode("utf-8")) == limit

    first = Sink()
    monkeypatch.setattr(cli, "MAX_RESPONSE_BYTES", limit)
    monkeypatch.setattr(cli.sys, "stdout", first)
    assert cli._emit(200, exact_body) == 500
    oversized = first.buffer.getvalue()
    assert len(oversized) <= limit
    assert json.loads(oversized)["code"] == "MULTIMODAL_RESPONSE_TOO_LARGE"

    second = Sink()
    monkeypatch.setattr(cli.sys, "stdout", second)
    assert cli._emit(200, {"unsupported": object()}) == 500
    invalid = json.loads(second.buffer.getvalue())
    assert invalid["code"] == "MULTIMODAL_INTERNAL_ERROR"
    assert invalid["retryable"] is True
