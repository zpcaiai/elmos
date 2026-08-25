from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

import elmos_multimodal_intake.sdk as sdk_module
from elmos_multimodal_intake.api import MultimodalIntakeApi
from elmos_multimodal_intake.canonical import canonical_digest, canonical_json
from elmos_multimodal_intake.contracts import SkillExecutionRequest, execution_result
from elmos_multimodal_intake.errors import AuthorizationError, ValidationError
from elmos_multimodal_intake.sdk import (
    PROGRESS_JOB_EVENTS_PREFIX,
    PROGRESS_JOB_WEBSOCKET_PREFIX,
    PROGRESS_TASK_EVENTS_PREFIX,
    PROGRESS_TASK_WEBSOCKET_PREFIX,
    SUPPORTED_PROGRESS_TRANSPORTS,
    WEBSOCKET_PROGRESS_SUPPORTED,
    MultimodalIntakeClient,
    SdkError,
    parse_progress_sse,
    validate_capability_response,
    validate_error_response,
    validate_execution_result,
)
from elmos_multimodal_intake.webhooks import (
    SqliteWebhookReplayStore,
    WebhookSigner,
    WebhookVerifier,
)


def request_document(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": "1.0.0",
        "skill": "elmos-unified-multimodal-content-ir",
        "operation": "normalize",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "actor_id": "user:reviewer",
        "idempotency_key": "request-00000001",
        "trace_id": "trace-test",
        "input": {"blocks": []},
    }
    value.update(overrides)
    return value


def test_canonical_json_uses_interoperable_number_and_utf16_key_order() -> None:
    assert canonical_json(
        {
            "n": 1e-7,
            "tiny": 1e-27,
            "fixed": 1e-6,
            "fraction": 2e-3,
            "rounded": 333333333.33333329,
            "large": 1e15,
            "zero": -0.0,
        }
    ) == (
        '{"fixed":0.000001,"fraction":0.002,"large":1000000000000000,'
        '"n":1e-7,"rounded":333333333.3333333,"tiny":1e-27,"zero":0}'
    )
    assert canonical_json({"\ue000": 2, "😀": 1}) == '{"😀":1,"\ue000":2}'
    with pytest.raises(ValidationError) as raised:
        canonical_json({"unsafe_float_integer": float(2**53)})
    assert raised.value.code == "CANONICAL_JSON_INTEGER_UNSAFE"


def test_request_contract_is_exact_and_digest_bound() -> None:
    first = SkillExecutionRequest.parse(request_document())
    second = SkillExecutionRequest.parse(request_document())
    assert first.request_digest == second.request_digest
    assert json.loads(first.canonical_json())["tenant_id"] == "tenant-a"
    changed = SkillExecutionRequest.parse(request_document(input={"blocks": [{"text": "x"}]}))
    assert changed.request_digest != first.request_digest
    mutable = request_document(input={"blocks": [{"nested": {"value": 1}}]})
    isolated = SkillExecutionRequest.parse(mutable)
    mutable["input"]["blocks"][0]["nested"]["value"] = 2
    assert isolated.document()["input"] == {"blocks": [{"nested": {"value": 1}}]}
    with pytest.raises(ValidationError, match="REQUEST_FIELDS_INVALID"):
        SkillExecutionRequest.parse({**request_document(), "unexpected": True})
    with pytest.raises(ValidationError, match="REQUEST_SCHEMA_VERSION_UNSUPPORTED"):
        SkillExecutionRequest.parse(request_document(schema_version="2.0.0"))
    assert SkillExecutionRequest.parse(request_document(idempotency_key="a" * 200)).idempotency_key == "a" * 200
    with pytest.raises(ValidationError, match="REQUEST_IDEMPOTENCY_KEY_INVALID"):
        SkillExecutionRequest.parse(request_document(idempotency_key="a" * 201))
    with pytest.raises(ValidationError, match="REQUEST_IDEMPOTENCY_KEY_INVALID"):
        SkillExecutionRequest.parse(request_document(idempotency_key="界" * 67))
    with pytest.raises(ValidationError, match="REQUEST_TENANT_ID_INVALID"):
        SkillExecutionRequest.parse(request_document(tenant_id=123))
    with pytest.raises(ValidationError, match="REQUEST_TENANT_ID_INVALID"):
        SkillExecutionRequest.parse(request_document(tenant_id=" tenant-a"))
    with pytest.raises(ValidationError, match="REQUEST_IDEMPOTENCY_KEY_INVALID"):
        SkillExecutionRequest.parse(request_document(idempotency_key=" request-00000001"))
    with pytest.raises(ValidationError, match="REQUEST_SKILL_INVALID"):
        SkillExecutionRequest.parse(request_document(skill="elmos-É"))
    with pytest.raises(ValidationError, match="REQUEST_JSON_INTEGER_UNSAFE"):
        SkillExecutionRequest.parse(request_document(input={"unsafe": 2**53}))
    with pytest.raises(ValidationError, match="REQUEST_JSON_INTEGER_UNSAFE"):
        SkillExecutionRequest.parse(request_document(input={"unsafe": float(2**53)}))
    with pytest.raises(ValidationError, match="REQUEST_JSON_UNICODE_INVALID"):
        SkillExecutionRequest.parse(request_document(input={"text": "\ud800"}))


def test_api_maps_stable_result_and_validation_error() -> None:
    def execute(request: SkillExecutionRequest) -> dict[str, Any]:
        return execution_result(request, status="SUCCEEDED", output={"block_count": 0})

    api = MultimodalIntakeApi(execute, lambda: [{"skill": "x"}])
    capability = api.capabilities()
    assert capability.status_code == 200
    assert capability.body["skill_count"] == 1
    assert capability.body["external_evidence"] == "NOT_RUN"
    response = api.execute(request_document())
    assert response.status_code == 200
    assert response.body["implementation_state"] == "CODE_IMPLEMENTED_LOCAL"
    assert response.body["result_digest"]
    blocked = api.execute({**request_document(), "extra": "not allowed"})
    assert blocked.status_code == 422
    assert blocked.body["code"] == "REQUEST_FIELDS_INVALID"

    business_blocked = MultimodalIntakeApi(
        lambda request: execution_result(
            request,
            status="BLOCKED",
            code="REVIEW_REQUIRED",
            output={"reason": "ambiguous"},
        ),
        lambda: [],
    ).execute(request_document())
    assert business_blocked.status_code == 200
    assert business_blocked.body["status"] == "BLOCKED"

    legacy_boundary = MultimodalIntakeApi(
        lambda request: {
            **execution_result(
                request,
                status="BLOCKED",
                code="SKILL_EXECUTION_IDEMPOTENCY_CONFLICT",
                output={},
            ),
            "_http_status": 409,
        },
        lambda: [],
    ).execute(request_document())
    assert legacy_boundary.status_code == 409
    assert set(legacy_boundary.body) == {
        "schema_version", "status", "code", "retryable", "trace_id"
    }

    failed = MultimodalIntakeApi(
        lambda _request: (_ for _ in ()).throw(RuntimeError("secret internal detail")),
        lambda: [],
    ).execute(request_document())
    assert failed.status_code == 500
    assert failed.body["code"] == "MULTIMODAL_INTERNAL_ERROR"
    assert "secret internal detail" not in json.dumps(failed.body)

    with pytest.raises(ValidationError, match="RESULT_CODE_REQUIRED"):
        execution_result(
            SkillExecutionRequest.parse(request_document()),
            status="BLOCKED",
            output={},
        )


def test_webhook_signature_is_body_bound_time_bounded_and_replay_safe() -> None:
    secret = b"a" * 32
    signer = WebhookSigner(secret, clock=lambda: 1_700_000_000)
    verifier = WebhookVerifier(
        secret,
        clock=lambda: 1_700_000_005,
        allow_process_local_replay=True,
    )
    body = b'{"status":"READY"}'
    headers = signer.sign("delivery-1", body)
    assert verifier.verify(headers, body) == "delivery-1"
    with pytest.raises(AuthorizationError, match="WEBHOOK_REPLAY_BLOCKED"):
        verifier.verify(headers, body)
    changed = signer.sign("delivery-2", body)
    with pytest.raises(AuthorizationError, match="WEBHOOK_SIGNATURE_INVALID"):
        verifier.verify(changed, b'{"status":"FAILED"}')
    expired = signer.sign("delivery-3", body, timestamp=1_699_000_000)
    with pytest.raises(AuthorizationError, match="WEBHOOK_SIGNATURE_EXPIRED"):
        verifier.verify(expired, body)
    assert "a" * 32 not in repr(signer)
    assert "a" * 32 not in repr(verifier)
    with pytest.raises(ValidationError, match="WEBHOOK_DELIVERY_ID_INVALID"):
        signer.sign("delivery-4\r\nX-Injected:true", body)
    with pytest.raises(ValidationError, match="WEBHOOK_BODY_INVALID"):
        WebhookSigner(secret, maximum_body_bytes=1).sign("delivery-5", body)


def test_webhook_rejects_bool_limits_and_negative_clock() -> None:
    secret = b"z" * 32
    with pytest.raises(ValidationError, match="WEBHOOK_BODY_LIMIT_INVALID"):
        WebhookSigner(secret, maximum_body_bytes=True)
    with pytest.raises(ValidationError, match="WEBHOOK_TOLERANCE_INVALID"):
        WebhookVerifier(secret, tolerance_seconds=True, allow_process_local_replay=True)
    with pytest.raises(ValidationError, match="WEBHOOK_BODY_LIMIT_INVALID"):
        WebhookVerifier(secret, maximum_body_bytes=False, allow_process_local_replay=True)

    body = b"{}"
    headers = WebhookSigner(secret, clock=lambda: 0).sign("negative-clock", body)
    verifier = WebhookVerifier(
        secret,
        clock=lambda: -1,
        allow_process_local_replay=True,
    )
    with pytest.raises(ValidationError, match="WEBHOOK_CLOCK_INVALID"):
        verifier.verify(headers, body)


def test_webhook_replay_claim_survives_verifier_restart(tmp_path) -> None:
    secret = b"b" * 32
    body = b'{"status":"READY"}'
    signer = WebhookSigner(
        secret,
        clock=lambda: 1_700_000_000,
        scope_id="subscription-a",
    )
    store = SqliteWebhookReplayStore(tmp_path / "webhook-replay.sqlite3")
    headers = signer.sign("durable-delivery-1", body)

    first = WebhookVerifier(
        secret,
        clock=lambda: 1_700_000_001,
        scope_id="subscription-a",
        replay_store=store,
    )
    assert first.verify(headers, body) == "durable-delivery-1"

    restarted = WebhookVerifier(
        secret,
        clock=lambda: 1_700_000_002,
        scope_id="subscription-a",
        replay_store=SqliteWebhookReplayStore(tmp_path / "webhook-replay.sqlite3"),
    )
    with pytest.raises(AuthorizationError, match="WEBHOOK_REPLAY_BLOCKED"):
        restarted.verify(headers, body)


def test_webhook_v2_binds_scope_key_and_future_timestamp_replay_window(tmp_path) -> None:
    secret = b"c" * 32
    body = b'{"status":"READY"}'
    signer = WebhookSigner(
        secret,
        clock=lambda: 1_700_000_000,
        scope_id="tenant-a:subscription-a",
        key_id="key-2026-08",
    )
    headers = signer.sign("future-delivery", body, timestamp=1_700_000_100)
    database = tmp_path / "future-replay.sqlite3"
    verifier = WebhookVerifier(
        secret,
        tolerance_seconds=300,
        clock=lambda: 1_700_000_000,
        scope_id="tenant-a:subscription-a",
        key_id="key-2026-08",
        replay_store=SqliteWebhookReplayStore(database),
    )
    assert verifier.verify(headers, body) == "future-delivery"
    still_signed = WebhookVerifier(
        secret,
        tolerance_seconds=300,
        clock=lambda: 1_700_000_301,
        scope_id="tenant-a:subscription-a",
        key_id="key-2026-08",
        replay_store=SqliteWebhookReplayStore(database),
    )
    with pytest.raises(AuthorizationError, match="WEBHOOK_REPLAY_BLOCKED"):
        still_signed.verify(headers, body)

    wrong_scope = WebhookVerifier(
        secret,
        clock=lambda: 1_700_000_001,
        scope_id="tenant-b:subscription-a",
        key_id="key-2026-08",
        replay_store=SqliteWebhookReplayStore(tmp_path / "wrong-scope.sqlite3"),
    )
    with pytest.raises(AuthorizationError, match="WEBHOOK_SIGNATURE_INVALID"):
        wrong_scope.verify(headers, body)
    duplicate_headers = {**headers, "x-elmos-key-id": headers["X-ELMOS-Key-Id"]}
    with pytest.raises(AuthorizationError, match="WEBHOOK_SIGNATURE_HEADERS_INVALID"):
        verifier.verify(duplicate_headers, body)


def test_webhook_sqlite_replay_claim_is_atomic_across_store_instances(tmp_path) -> None:
    database = tmp_path / "atomic-replay.sqlite3"
    stores = [SqliteWebhookReplayStore(database), SqliteWebhookReplayStore(database)]

    def claim(store: SqliteWebhookReplayStore) -> bool:
        return store.claim(
            "tenant-a:subscription-a",
            "same-delivery",
            now=1_700_000_000,
            expires_at=1_700_000_301,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, stores))
    assert sorted(results) == [False, True]


def test_sdk_allows_https_or_exact_loopback_without_url_credentials() -> None:
    token = "t" * 32
    assert MultimodalIntakeClient("https://intake.example.test", token).base_url == "https://intake.example.test"
    assert MultimodalIntakeClient("http://127.0.0.1:8787/", token).base_url == "http://127.0.0.1:8787"
    assert MultimodalIntakeClient("http://127.0.0.2:8787/", token).base_url == "http://127.0.0.2:8787"
    with pytest.raises(ValueError, match="SDK_BASE_URL_HTTPS_OR_LOOPBACK_REQUIRED"):
        MultimodalIntakeClient("http://localhost:8787", token)
    with pytest.raises(ValueError, match="SDK_BASE_URL_HTTPS_OR_LOOPBACK_REQUIRED"):
        MultimodalIntakeClient("http://intake.example.test", token)
    with pytest.raises(ValueError, match="SDK_BASE_URL_INVALID"):
        MultimodalIntakeClient("https://user:secret@intake.example.test", token)


def test_sdk_rejects_non_finite_or_non_json_request_before_network() -> None:
    client = MultimodalIntakeClient("https://intake.example.test", "t" * 32)
    with pytest.raises(SdkError, match="SDK_REQUEST_INVALID"):
        client.execute({"value": float("nan")})
    with pytest.raises(SdkError, match="SDK_REQUEST_INVALID"):
        client.execute(request_document(input={"unsafe": 2**53}))
    with pytest.raises(SdkError, match="SDK_REQUEST_INVALID"):
        client.execute(request_document(input={"unsafe": float(2**53)}))
    with pytest.raises(SdkError, match="SDK_REQUEST_INVALID"):
        client.execute(request_document(input={"text": "\ud800"}))


def test_sdk_validates_execution_digest_and_exact_capability_identity() -> None:
    from elmos_multimodal_intake.skill_runtime import SKILL_REGISTRY

    request = SkillExecutionRequest.parse(request_document())
    result = execution_result(request, status="SUCCEEDED", output={"block_count": 0})
    assert validate_execution_result(result)["result_digest"] == result["result_digest"]
    tampered = {**result, "output": {"block_count": 1}}
    with pytest.raises(SdkError, match="SDK_RESPONSE_DIGEST_INVALID"):
        validate_execution_result(tampered)
    with pytest.raises(SdkError, match="SDK_RESPONSE_CONTRACT_INVALID"):
        validate_execution_result({**result, "unexpected": True})
    with pytest.raises(SdkError, match="SDK_RESPONSE_CONTRACT_INVALID"):
        validate_execution_result({**result, "retryable": 0})
    different_request = SkillExecutionRequest.parse(
        request_document(idempotency_key="request-00000002", trace_id="trace-other")
    )
    with pytest.raises(SdkError, match="SDK_RESPONSE_REQUEST_BINDING_INVALID"):
        validate_execution_result(result, expected_request=different_request)

    bootstrap_request = SkillExecutionRequest.parse(
        request_document(
            skill="elmos-multimodal-input-orchestrator",
            operation="bootstrap_project",
            input={},
        )
    )
    bound_bootstrap = execution_result(
        bootstrap_request,
        status="SUCCEEDED",
        output={"project_id": "project-a"},
    )
    assert validate_execution_result(
        bound_bootstrap,
        expected_request=bootstrap_request,
    )["output"]["project_id"] == "project-a"
    wrong_project = execution_result(
        bootstrap_request,
        status="SUCCEEDED",
        output={"project_id": "project-b"},
    )
    with pytest.raises(SdkError, match="SDK_RESPONSE_PROJECT_BINDING_INVALID"):
        validate_execution_result(wrong_project, expected_request=bootstrap_request)

    bindings = sorted(SKILL_REGISTRY.values(), key=lambda item: item.ordinal)
    skills = [
        {
            "ordinal": binding.ordinal,
            "skill": binding.skill,
            "handler_id": binding.handler_id,
            "phase": binding.phase,
            "implementation_state": "CODE_IMPLEMENTED_LOCAL",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "transport": {
                "maximum_request_bytes": 2 * 1024 * 1024,
                "maximum_json_part_bytes": 1024 * 1024,
                "part_number_base": 0,
            },
        }
        for binding in bindings
    ]
    capabilities = {
        "schema_version": "1.0.0",
        "status": "CODE_IMPLEMENTED_LOCAL",
        "skill_count": 50,
        "skills": skills,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    assert len(validate_capability_response(capabilities)["skills"]) == 50
    drifted = [dict(item) for item in skills]
    drifted[0]["skill"] = "elmos-drifted-skill"
    with pytest.raises(SdkError, match="SDK_CAPABILITIES_CONTRACT_INVALID"):
        validate_capability_response({**capabilities, "skills": drifted})
    capabilities["skills"] = [*skills[:-1], dict(skills[-2])]
    with pytest.raises(SdkError, match="SDK_CAPABILITIES_CONTRACT_INVALID"):
        validate_capability_response(capabilities)
    reordered = {**capabilities, "skills": list(reversed(skills))}
    with pytest.raises(SdkError, match="SDK_CAPABILITIES_DIGEST_INVALID"):
        validate_capability_response(reordered)


def test_sdk_normal_json_parser_rejects_duplicates_noncanonical_and_unsafe_numbers() -> None:
    canonical = canonical_json({"safe": 1, "text": "ok"}).encode()
    assert sdk_module._strict_json_loads(  # noqa: SLF001
        canonical,
        invalid_code="SDK_RESPONSE_INVALID",
        canonical_code="SDK_RESPONSE_CANONICAL_JSON_REQUIRED",
    ) == {"safe": 1, "text": "ok"}
    with pytest.raises(SdkError, match="SDK_RESPONSE_INVALID"):
        sdk_module._strict_json_loads(  # noqa: SLF001
            b'{"safe":1,"safe":2}',
            invalid_code="SDK_RESPONSE_INVALID",
            canonical_code="SDK_RESPONSE_CANONICAL_JSON_REQUIRED",
        )
    with pytest.raises(SdkError, match="SDK_RESPONSE_CANONICAL_JSON_REQUIRED"):
        sdk_module._strict_json_loads(  # noqa: SLF001
            b'{"safe": 1}',
            invalid_code="SDK_RESPONSE_INVALID",
            canonical_code="SDK_RESPONSE_CANONICAL_JSON_REQUIRED",
        )
    with pytest.raises(SdkError, match="SDK_RESPONSE_INVALID"):
        sdk_module._strict_json_loads(  # noqa: SLF001
            b'{"unsafe":9007199254740992}',
            invalid_code="SDK_RESPONSE_INVALID",
            canonical_code="SDK_RESPONSE_CANONICAL_JSON_REQUIRED",
        )


def test_typescript_and_java_normal_sdk_paths_are_contract_validating() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    typescript_sdk = (repository_root / "sdk/multimodal-intake/typescript/client.ts").read_text(
        encoding="utf-8"
    )
    java_sdk = (
        repository_root
        / "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java"
    ).read_text(encoding="utf-8")
    error_boundary = typescript_sdk.split("async function rejectRemoteError", 1)[1].split(
        "export async function parseProgressSse", 1
    )[0]
    normal_boundary = typescript_sdk.split("private async request", 1)[1]
    assert "JSON.parse" not in error_boundary
    assert "JSON.parse" not in normal_boundary
    assert "class StrictJsonParser" in typescript_sdk
    assert "validateExecutionResult" in typescript_sdk
    assert "validateCapabilityResponse" in typescript_sdk
    assert "expectedCapabilityDocumentDigest" in typescript_sdk
    assert "SDK_RESPONSE_PROJECT_BINDING_INVALID" in typescript_sdk
    assert "private static Map<String, Object> validateExecutionResult" in java_sdk
    assert "private static Map<String, Object> validateCapabilityResponse" in java_sdk
    assert "parseExecutionRequest(strictJsonRequest)" in java_sdk
    assert "SDK_RESPONSE_CANONICAL_JSON_REQUIRED" in java_sdk
    assert "SDK_RESPONSE_PROJECT_BINDING_INVALID" in java_sdk
    assert "return canonicalJson(value).getBytes(StandardCharsets.UTF_8);" in java_sdk


def test_sdk_error_response_is_exact_and_never_coerces_types() -> None:
    valid = {
        "schema_version": "1.0.0",
        "status": "BLOCKED",
        "code": "BOUND_IDENTITY_MISMATCH",
        "retryable": False,
        "trace_id": "trace-error",
    }
    assert validate_error_response(valid, 403) == valid
    with pytest.raises(SdkError, match="SDK_ERROR_RESPONSE_CONTRACT_INVALID"):
        validate_error_response({**valid, "retryable": 0}, 403)
    with pytest.raises(SdkError, match="SDK_ERROR_RESPONSE_CONTRACT_INVALID"):
        validate_error_response({**valid, "status": "FAILED"}, 403)
    with pytest.raises(SdkError, match="SDK_ERROR_RESPONSE_CONTRACT_INVALID"):
        validate_error_response({**valid, "code": "secret detail"}, 403)
    with pytest.raises(SdkError, match="SDK_ERROR_RESPONSE_CONTRACT_INVALID"):
        validate_error_response({**valid, "trace_id": None}, 403)


def _progress_document(unsigned: dict[str, Any], *, cursor: str | None = None) -> dict[str, Any]:
    digest = canonical_digest(unsigned)
    sequence = unsigned["sequence_number"]
    return {
        **unsigned,
        "content_digest": f"sha256:{digest}",
        "cursor": cursor if cursor is not None else f"p1-{sequence}-{digest}",
    }


def test_sdk_parses_canonical_one_shot_task_sse_and_validates_cursor_digest() -> None:
    document = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-1",
            "sequence_number": 1,
            "event_type": "durable.task.transitioned",
            "state": "RUNNING",
            "previous_state": "PENDING",
            "occurred_at": "2026-08-22T08:00:00+00:00",
        }
    )
    cursor = document["cursor"]
    payload = (
        f"id: {cursor}\nevent: progress\ndata: {canonical_json(document)}\n\n"
    ).encode("utf-8")
    batch = parse_progress_sse(
        payload,
        resource_kind="task",
        resource_id="task-1",
    )
    assert batch.next_cursor == cursor
    assert batch.heartbeat is None
    assert batch.documents == (document,)

    tampered = {**document, "occurred_at": "2026-08-22T08:00:01+00:00"}
    with pytest.raises(SdkError, match="SDK_PROGRESS_DIGEST_INVALID"):
        parse_progress_sse(
            f"id: {cursor}\nevent: progress\ndata: {canonical_json(tampered)}\n\n".encode(),
            resource_kind="task",
            resource_id="task-1",
        )
    with pytest.raises(SdkError, match="SDK_PROGRESS_CANONICAL_JSON_REQUIRED"):
        parse_progress_sse(
            f"id: {cursor}\nevent: progress\ndata: {json.dumps(document)}\n\n".encode(),
            resource_kind="task",
            resource_id="task-1",
        )


def _progress_frames(*documents: dict[str, Any]) -> bytes:
    return "".join(
        f"id: {document['cursor']}\nevent: progress\ndata: {canonical_json(document)}\n\n"
        for document in documents
    ).encode("utf-8")


def test_all_three_sdks_reject_digest_valid_task_history_fork() -> None:
    first = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-history",
            "sequence_number": 1,
            "event_type": "durable.task.transitioned",
            "state": "RUNNING",
            "previous_state": "PENDING",
            "occurred_at": "2026-08-22T08:00:00+00:00",
        }
    )
    forked = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-history",
            "sequence_number": 2,
            "event_type": "durable.task.transitioned",
            "state": "RUNNING",
            # This transition is valid in isolation but forks from first.state.
            "previous_state": "PAUSED",
            "occurred_at": "2026-08-22T08:00:01+00:00",
        }
    )
    with pytest.raises(SdkError, match="SDK_PROGRESS_HISTORY_INVALID"):
        parse_progress_sse(
            _progress_frames(first, forked),
            resource_kind="task",
            resource_id="task-history",
        )

    false_origin = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-history",
            "sequence_number": 1,
            "event_type": "durable.task.transitioned",
            # Locally valid, but RUNNING cannot be the prior state at sequence 1.
            "state": "SUCCEEDED",
            "previous_state": "RUNNING",
            "occurred_at": "2026-08-22T08:00:00+00:00",
        }
    )
    with pytest.raises(SdkError, match="SDK_PROGRESS_HISTORY_INVALID"):
        parse_progress_sse(
            _progress_frames(false_origin),
            resource_kind="task",
            resource_id="task-history",
        )

    repository_root = Path(__file__).resolve().parents[3]
    typescript_sdk = (
        repository_root / "sdk/multimodal-intake/typescript/client.ts"
    ).read_text(encoding="utf-8")
    java_sdk = (
        repository_root
        / "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java"
    ).read_text(encoding="utf-8")
    assert 'throw new Error("SDK_PROGRESS_HISTORY_INVALID")' in typescript_sdk
    assert "documentPreviousState !== previousTaskState" in typescript_sdk
    assert (
        'previousTaskState === null && requestedCursor === null && documentPreviousState !== "PENDING"'
        in typescript_sdk
    )
    assert 'throw new IOException("SDK_PROGRESS_HISTORY_INVALID")' in java_sdk
    assert "!previousTaskState.equals(documentPreviousState)" in java_sdk
    assert "previousTaskState == null && parsedRequested == null" in java_sdk
    assert '!"PENDING".equals(documentPreviousState)' in java_sdk


def test_progress_sse_rejects_duplicate_json_keys_in_all_sdk_parsers() -> None:
    document = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-duplicate",
            "sequence_number": 1,
            "event_type": "durable.task.transitioned",
            "state": "RUNNING",
            "previous_state": "PENDING",
            "occurred_at": "2026-08-22T08:00:00+00:00",
        }
    )
    duplicate_json = canonical_json(document).replace(
        '"kind":"TASK_PROGRESS"',
        '"kind":"TASK_PROGRESS","kind":"TASK_PROGRESS"',
        1,
    )
    payload = (
        f"id: {document['cursor']}\nevent: progress\ndata: {duplicate_json}\n\n"
    ).encode("utf-8")
    with pytest.raises(SdkError, match="SDK_PROGRESS_JSON_INVALID"):
        parse_progress_sse(
            payload,
            resource_kind="task",
            resource_id="task-duplicate",
        )

    repository_root = Path(__file__).resolve().parents[3]
    typescript_sdk = (
        repository_root / "sdk/multimodal-intake/typescript/client.ts"
    ).read_text(encoding="utf-8")
    java_sdk = (
        repository_root
        / "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java"
    ).read_text(encoding="utf-8")
    assert "parsed = new StrictJsonParser(rawJson).parse();" in typescript_sdk
    assert "var parsed = new StrictJsonParser(rawJson).parse();" in java_sdk


def test_job_progress_batch_is_exactly_one_snapshot_not_task_history() -> None:
    queued = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "JOB_PROGRESS",
            "resource_id": "job-history",
            "sequence_number": 1,
            "event_type": "processing.job.snapshot",
            "state": "QUEUED",
            "result_status": "NOT_RUN",
            "attempt": 0,
            "max_attempts": 3,
            "occurred_at": "2026-08-22T08:00:00+00:00",
        }
    )
    running = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "JOB_PROGRESS",
            "resource_id": "job-history",
            "sequence_number": 2,
            "event_type": "processing.job.snapshot",
            "state": "RUNNING",
            "result_status": "NOT_RUN",
            "attempt": 1,
            "max_attempts": 3,
            "occurred_at": "2026-08-22T08:00:01+00:00",
        }
    )
    with pytest.raises(SdkError, match="SDK_PROGRESS_HISTORY_INVALID"):
        parse_progress_sse(
            _progress_frames(queued, running),
            resource_kind="job",
            resource_id="job-history",
        )


def test_sdk_accepts_resume_batch_without_inventing_cursor_prior_state() -> None:
    requested_cursor = "p1-4-" + "a" * 64
    resumed = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-resume",
            "sequence_number": 5,
            "event_type": "durable.task.transitioned",
            # The cursor cannot reveal this prior state, so the first resumed
            # document is validated only as a self-contained transition.
            "state": "RUNNING",
            "previous_state": "FAILED_RETRYABLE",
            "occurred_at": "2026-08-22T08:00:05+00:00",
        }
    )
    continued = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": "task-resume",
            "sequence_number": 6,
            "event_type": "durable.task.transitioned",
            "state": "SUCCEEDED",
            "previous_state": "RUNNING",
            "occurred_at": "2026-08-22T08:00:06+00:00",
        }
    )
    batch = parse_progress_sse(
        _progress_frames(resumed, continued),
        resource_kind="task",
        resource_id="task-resume",
        requested_cursor=requested_cursor,
    )
    assert batch.documents == (resumed, continued)
    assert batch.requested_cursor == requested_cursor
    assert batch.next_cursor == continued["cursor"]


def test_sdk_progress_heartbeat_is_non_advancing_and_inputs_are_exact() -> None:
    prior_digest = "a" * 64
    cursor = f"p1-7-{prior_digest}"
    heartbeat = _progress_document(
        {
            "schema_version": "1.0.0",
            "kind": "JOB_PROGRESS_HEARTBEAT",
            "resource_id": "job-1",
            "sequence_number": 7,
            "status": "NO_CHANGE",
        },
        cursor=cursor,
    )
    batch = parse_progress_sse(
        f"event: heartbeat\ndata: {canonical_json(heartbeat)}\n\n".encode(),
        resource_kind="job",
        resource_id="job-1",
        requested_cursor=cursor,
    )
    assert batch.documents == ()
    assert batch.heartbeat == heartbeat
    assert batch.next_cursor == cursor
    with pytest.raises(SdkError, match="SDK_PROGRESS_RESOURCE_ID_INVALID"):
        parse_progress_sse(b"x\n\n", resource_kind="task", resource_id="../task")
    with pytest.raises(SdkError, match="SDK_PROGRESS_CURSOR_INVALID"):
        parse_progress_sse(
            b"x\n\n",
            resource_kind="task",
            resource_id="task-1",
            requested_cursor="p1-0-" + "a" * 64,
        )


def test_python_progress_error_envelope_matches_strict_sdk_error_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_error = {
        "schema_version": "1.0.0",
        "status": "BLOCKED",
        "code": "PROGRESS_CURSOR_DIVERGED",
        "retryable": False,
        "trace_id": "trace-progress-error",
    }
    client = MultimodalIntakeClient(
        "http://127.0.0.1:8765",
        "t" * 32,
    )
    progress_scope = {
        "tenant_id": "tenant-progress",
        "project_id": "project-progress",
        "actor_id": "actor-progress",
    }
    observed_requests: list[urllib.request.Request] = []

    class _ErrorOpener:
        def __init__(self, error: urllib.error.HTTPError) -> None:
            self.error = error

        def open(self, *_args: Any, **_kwargs: Any) -> Any:
            if _args and isinstance(_args[0], urllib.request.Request):
                observed_requests.append(_args[0])
            raise self.error

    def install_error(payload: bytes, headers: list[tuple[str, str]]) -> None:
        message = Message()
        for name, value in headers:
            message.add_header(name, value)
        error = urllib.error.HTTPError(
            "http://127.0.0.1:8765/progress",
            409,
            "Conflict",
            message,
            io.BytesIO(payload),
        )
        monkeypatch.setattr(sdk_module, "_NO_REDIRECT_OPENER", _ErrorOpener(error))

    canonical_payload = canonical_json(valid_error).encode("utf-8")
    install_error(
        canonical_payload,
        [
            ("Content-Type", "application/problem+json"),
            ("Content-Length", str(len(canonical_payload))),
        ],
    )
    with pytest.raises(SdkError, match="PROGRESS_CURSOR_DIVERGED") as remote:
        client.task_progress("task-error", **progress_scope)
    assert remote.value.trace_id == "trace-progress-error"
    assert observed_requests[-1].get_header("X-elmos-bound-tenant") == "tenant-progress"
    assert observed_requests[-1].get_header("X-elmos-bound-project") == "project-progress"
    assert observed_requests[-1].get_header("X-elmos-bound-actor") == "actor-progress"

    duplicate_json = (
        b'{"code":"PROGRESS_CURSOR_DIVERGED","code":"OTHER",'
        b'"retryable":false,"schema_version":"1.0.0","status":"BLOCKED"}'
    )
    cases = [
        (
            json.dumps(valid_error).encode("utf-8"),
            [("Content-Type", "application/json")],
            "SDK_ERROR_RESPONSE_CANONICAL_JSON_REQUIRED",
        ),
        (
            duplicate_json,
            [("Content-Type", "application/json")],
            "SDK_ERROR_RESPONSE_INVALID",
        ),
        (
            canonical_payload,
            [
                ("Content-Type", "application/json"),
                ("Content-Type", "application/problem+json"),
            ],
            "SDK_ERROR_RESPONSE_CONTENT_TYPE_INVALID",
        ),
        (
            canonical_payload,
            [("Content-Type", "application/json; charset=utf-8, application/problem+json")],
            "SDK_ERROR_RESPONSE_CONTENT_TYPE_INVALID",
        ),
        (
            canonical_payload,
            [("Content-Type", "application/json"), ("Content-Encoding", "gzip")],
            "SDK_ERROR_RESPONSE_CONTENT_ENCODING_INVALID",
        ),
        (
            canonical_payload,
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(canonical_payload) + 1)),
            ],
            "SDK_ERROR_RESPONSE_SIZE_INVALID",
        ),
    ]
    for payload, headers, expected_code in cases:
        install_error(payload, headers)
        with pytest.raises(SdkError, match=expected_code):
            client.task_progress("task-error", **progress_scope)

    with pytest.raises(SdkError, match="SDK_PROGRESS_BOUND_IDENTITY_INVALID"):
        client.task_progress(
            "task-error",
            tenant_id="tenant-progress",
            project_id="../project-progress",
            actor_id="actor-progress",
        )


def test_progress_contract_declares_sse_only_sdks_and_runtime_read_only_websocket() -> None:
    assert SUPPORTED_PROGRESS_TRANSPORTS == ("sse",)
    assert WEBSOCKET_PROGRESS_SUPPORTED is False
    assert PROGRESS_TASK_EVENTS_PREFIX.endswith("/progress/tasks/")
    assert PROGRESS_JOB_EVENTS_PREFIX.endswith("/progress/jobs/")
    assert PROGRESS_TASK_WEBSOCKET_PREFIX.endswith("/progress/ws/tasks/")
    assert PROGRESS_JOB_WEBSOCKET_PREFIX.endswith("/progress/ws/jobs/")
    contract = (Path(__file__).resolve().parents[1] / "openapi/multimodal-intake-v1.openapi.yaml").read_text(
        encoding="utf-8"
    )
    assert "/api/v1/multimodal-intake/progress/tasks/{task_id}/events:" in contract
    assert "/api/v1/multimodal-intake/progress/jobs/{job_id}/events:" in contract
    assert 'pattern: "^p1-[1-9][0-9]{0,15}-[0-9a-f]{64}$"' in contract
    task_websocket_path = "/api/v1/multimodal-intake/progress/ws/tasks/{task_id}:"
    job_websocket_path = "/api/v1/multimodal-intake/progress/ws/jobs/{job_id}:"
    assert task_websocket_path in contract
    assert job_websocket_path in contract
    assert "x-elmos-websocket-mode: read-only-one-shot-server-to-client" in contract
    assert "typescript: { sse: true, websocket: false }" in contract
    task_websocket = contract.split(task_websocket_path, 1)[1].split(job_websocket_path, 1)[0]
    job_websocket = contract.split(job_websocket_path, 1)[1].split("\ncomponents:", 1)[0]
    for websocket_operation in (task_websocket, job_websocket):
        assert all(f'        "{status}":' in websocket_operation for status in (404, 409, 426, 500))

    repository_root = Path(__file__).resolve().parents[3]
    typescript_sdk = (repository_root / "sdk/multimodal-intake/typescript/client.ts").read_text(
        encoding="utf-8"
    )
    java_sdk = (
        repository_root
        / "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java"
    ).read_text(encoding="utf-8")
    assert 'bytes.byteLength > maximumResponseBytes' in typescript_sdk
    assert 'const safeResourceId = strictResourceId(resourceId);' in typescript_sdk
    assert 'resourceKind !== "task" && resourceKind !== "job"' in typescript_sdk
    assert 'await rejectRemoteError(response)' in typescript_sdk
    for header in (
        "X-ELMOS-Bound-Tenant",
        "X-ELMOS-Bound-Project",
        "X-ELMOS-Bound-Actor",
    ):
        assert header in typescript_sdk
        assert header in java_sdk
    assert "context: ProgressContext" in typescript_sdk
    assert "public record ProgressContext" in java_sdk
    typescript_error_boundary = typescript_sdk.split("async function rejectRemoteError", 1)[1].split(
        "export async function parseProgressSse", 1
    )[0]
    assert 'errorContentType.includes(",")' in typescript_error_boundary
    assert 'parseStrictJsonBytes(bytes, "SDK_ERROR_RESPONSE_INVALID")' in typescript_error_boundary
    assert "validateErrorEnvelope(parsed, response.status, rawJson)" in typescript_error_boundary
    assert '"localhost"' not in typescript_sdk
    assert "private static RemoteError parseRemoteError" in java_sdk
    assert "private static final class BoundedBodySubscriber" in java_sdk
    assert "boundedBodyHandler(\"SDK_PROGRESS_RESPONSE_TOO_LARGE\")" in java_sdk
    assert "boundedBodyHandler(\"SDK_RESPONSE_TOO_LARGE\")" in java_sdk
    assert "BodyHandlers.ofInputStream" not in java_sdk
    java_error_boundary = java_sdk.split("private static RemoteError parseRemoteError", 1)[1].split(
        "private static boolean numericLoopbackHost", 1
    )[0]
    assert 'allValues("Content-Type")' in java_error_boundary
    assert 'allValues("Content-Encoding")' in java_error_boundary
    assert 'allValues("Content-Length")' in java_error_boundary
    assert 'contentTypes.get(0).contains(",")' in java_error_boundary
    assert "new StrictJsonParser(rawJson).parse()" in java_error_boundary
    assert "SDK_ERROR_RESPONSE_CANONICAL_JSON_REQUIRED" in java_error_boundary
    assert 'var loopback = numericLoopbackHost(host);' in java_sdk
    assert '"localhost".equals(host)' not in java_sdk


def test_openapi_declares_authoritative_current_correction_recovery_contract() -> None:
    contract = (
        Path(__file__).resolve().parents[1]
        / "openapi/multimodal-intake-v1.openapi.yaml"
    ).read_text(encoding="utf-8")
    assert "x-elmos-human-review-current-correction:" in contract
    assert "operation: current_correction" in contract
    assert "authorization: tenant-project-bound REVIEW ACL" in contract
    assert "HumanReviewCurrentCorrectionInput:" in contract
    assert "HumanReviewCurrentCorrectionOutput:" in contract
    assert "HumanReviewCorrection:" in contract
    assert "HumanReviewTarget:" in contract
    assert "successCode: HUMAN_REVIEW_CURRENT_CORRECTION_RETRIEVED" in contract
    assert "absentCode: HUMAN_REVIEW_CURRENT_CORRECTION_NOT_AVAILABLE" in contract


def _human_review_sdk_source_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    original_value = "authoritative source value"
    original_value_digest = f"sha256:{canonical_digest(original_value)}"
    source_ref = {
        "schema_version": "human-review-source-ref-v2",
        "content_id": "asset-sdk-1",
        "content_version": 1,
        "content_digest": f"sha256:{'1' * 64}",
        "asset_sha256": f"sha256:{'2' * 64}",
        "target_kind": "TEXT",
        "target_digest": f"sha256:{'3' * 64}",
        "snapshot_id": "snapshot-sdk-1",
        "snapshot_digest": f"sha256:{'4' * 64}",
        "head_version": 1,
        "head_value_digest": f"sha256:{'5' * 64}",
        "source_digest": f"sha256:{'6' * 64}",
        "provenance_digest": f"sha256:{'7' * 64}",
        "original_value_client_digest": original_value_digest,
        "original_value_digest_contract": "sha256:rfc8785-ijson-safeint-v1",
    }
    summary = {
        "schema_version": "human-review-source-summary-v1",
        "content_id": source_ref["content_id"],
        "content_version": source_ref["content_version"],
        "target_kind": source_ref["target_kind"],
        "target": {"path": "content_blocks/sdk/text"},
        "target_digest": source_ref["target_digest"],
        "confidence": 0.25,
        "head_version": source_ref["head_version"],
        "head_direction": "SNAPSHOT",
        "head_correction_version": 0,
        "original_value_client_digest": original_value_digest,
        "original_value_digest_contract": "sha256:rfc8785-ijson-safeint-v1",
        "source_ref": source_ref,
    }
    detail = {
        **summary,
        "schema_version": "human-review-source-detail-v1",
        "original_value": original_value,
    }
    return summary, detail


def _human_review_sdk_enqueue_input(
    source_ref: dict[str, Any],
) -> dict[str, Any]:
    return {
        "content_id": source_ref["content_id"],
        "expected_asset_version": source_ref["content_version"],
        "target_kind": source_ref["target_kind"],
        "target_digest": source_ref["target_digest"],
        "expected_head_version": source_ref["head_version"],
        "expected_snapshot_id": source_ref["snapshot_id"],
        "expected_snapshot_digest": source_ref["snapshot_digest"],
        "expected_head_value_digest": source_ref["head_value_digest"],
        "original_value_digest": source_ref["original_value_client_digest"],
        "reason": "SDK exact contract review",
    }


def _human_review_sdk_task(
    source: dict[str, Any], enqueue_input: dict[str, Any]
) -> dict[str, Any]:
    source_ref = source["source_ref"]
    timestamp = "2026-08-22T00:00:00+00:00"
    return {
        "task_id": "review-task-sdk-1",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "asset_id": enqueue_input["content_id"],
        "target_kind": enqueue_input["target_kind"],
        "target": source["target"],
        "original_value": source["original_value"],
        "source_digest": source_ref["source_digest"],
        "source_ref": source_ref,
        "confidence": source["confidence"],
        "reason": enqueue_input["reason"],
        "state": "QUEUED",
        "current_correction_version": 0,
        "current_correction_digest": None,
        "effective_version": 0,
        "effective_digest": None,
        "claim_actor_id": None,
        "claim_fence": 0,
        "claim_expires_at": None,
        "version": 1,
        "created_by": "user:reviewer",
        "created_at": timestamp,
        "updated_at": timestamp,
        "closed_at": None,
    }


def test_human_review_sdk_validates_discovery_enqueue_and_opaque_recovery() -> None:
    summary, detail = _human_review_sdk_source_documents()
    source_ref = summary["source_ref"]
    list_input = {
        "content_id": source_ref["content_id"],
        "expected_asset_version": source_ref["content_version"],
        "kinds": ["TEXT"],
        "limit": 1,
        "cursor": None,
    }
    list_request = SkillExecutionRequest.parse(
        request_document(
            skill="elmos-human-review-and-correction",
            operation="source_list",
            idempotency_key="sdk-source-list-0001",
            input=list_input,
        )
    )
    cursor_document = {
        "version": "human-review-source-cursor-v1",
        "filter_digest": canonical_digest(
            {
                "schema_version": "human-review-source-filter-v1",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "content_id": source_ref["content_id"],
                "content_version": source_ref["content_version"],
                "kinds": ["TEXT"],
            }
        ),
        "collection_digest": "8" * 64,
        "collection_generation": 1,
        "target_kind": source_ref["target_kind"],
        "target_digest": source_ref["target_digest"],
    }
    next_cursor = base64.urlsafe_b64encode(
        canonical_json(cursor_document).encode("utf-8")
    ).decode("ascii").rstrip("=")
    metadata = {
        "handler_id": "execute_human_review_and_correction",
        "phase": "review",
        "metrics": {},
    }
    list_output = {
        **metadata,
        "sources": [summary],
        "next_cursor": next_cursor,
        "total": 2,
    }
    listed = execution_result(
        list_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_SOURCES_LISTED",
        output=list_output,
    )
    assert validate_execution_result(
        listed, expected_request=list_request
    )["output"]["next_cursor"] == next_cursor

    invalid_cursor = execution_result(
        list_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_SOURCES_LISTED",
        output={**list_output, "next_cursor": next_cursor + "="},
    )
    with pytest.raises(SdkError, match="SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID"):
        validate_execution_result(invalid_cursor, expected_request=list_request)
    extra_cursor = base64.urlsafe_b64encode(
        canonical_json({**cursor_document, "unexpected": True}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    invalid_extra_cursor = execution_result(
        list_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_SOURCES_LISTED",
        output={**list_output, "next_cursor": extra_cursor},
    )
    with pytest.raises(SdkError, match="SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID"):
        validate_execution_result(
            invalid_extra_cursor, expected_request=list_request
        )
    invalid_terminal_total = execution_result(
        list_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_SOURCES_LISTED",
        output={**list_output, "next_cursor": None},
    )
    with pytest.raises(
        SdkError, match="SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID"
    ):
        validate_execution_result(
            invalid_terminal_total, expected_request=list_request
        )
    invalid_ref = execution_result(
        list_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_SOURCES_LISTED",
        output={
            **list_output,
            "sources": [
                {**summary, "source_ref": {**source_ref, "unexpected": True}}
            ],
        },
    )
    with pytest.raises(SdkError, match="SDK_HUMAN_REVIEW_SOURCE_REF_INVALID"):
        validate_execution_result(invalid_ref, expected_request=list_request)

    get_input = {
        "content_id": source_ref["content_id"],
        "expected_asset_version": source_ref["content_version"],
        "target_kind": source_ref["target_kind"],
        "target_digest": source_ref["target_digest"],
        "expected_head_version": source_ref["head_version"],
    }
    get_request = SkillExecutionRequest.parse(
        request_document(
            skill="elmos-human-review-and-correction",
            operation="source_get",
            idempotency_key="sdk-source-get-0001",
            input=get_input,
        )
    )
    retrieved = execution_result(
        get_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_SOURCE_RETRIEVED",
        output={**metadata, "source": detail},
    )
    assert validate_execution_result(
        retrieved, expected_request=get_request
    )["output"]["source"]["original_value"] == detail["original_value"]

    enqueue_input = _human_review_sdk_enqueue_input(source_ref)
    task = _human_review_sdk_task(detail, enqueue_input)
    enqueue_request = SkillExecutionRequest.parse(
        request_document(
            skill="elmos-human-review-and-correction",
            operation="enqueue",
            idempotency_key="sdk-enqueue-0001",
            input=enqueue_input,
        )
    )
    enqueued = execution_result(
        enqueue_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_TASK_ENQUEUED",
        output={**metadata, "task": task},
    )
    assert validate_execution_result(
        enqueued, expected_request=enqueue_request
    )["output"]["task"]["task_id"] == task["task_id"]

    recovery_handle = "sdk-opaque-recovery-handle-" + "h" * 32
    prepare_input = {
        "recovery_handle": recovery_handle,
        "execute_idempotency_key": "sdk-enqueue-execute-0001",
        **enqueue_input,
    }
    prepare_request = SkillExecutionRequest.parse(
        request_document(
            skill="elmos-human-review-and-correction",
            operation="enqueue_prepare",
            idempotency_key="sdk-enqueue-prepare-0001",
            input=prepare_input,
        )
    )
    preparation = {
        "schema_version": "human-review-enqueue-preparation-v1",
        "recovery_handle": recovery_handle,
        "request_digest": f"sha256:{canonical_digest(enqueue_input)}",
        "state": "PREPARED",
        "safe_to_clear": False,
        "expires_at": "2026-08-23T00:00:00+00:00",
        "prepared_at": "2026-08-22T00:00:00+00:00",
        "executed_at": None,
        "task_id": None,
        "enqueue_input": enqueue_input,
    }
    prepared = execution_result(
        prepare_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_ENQUEUE_PREPARED",
        output={**metadata, "preparation": preparation},
    )
    assert validate_execution_result(
        prepared, expected_request=prepare_request
    )["output"]["preparation"]["safe_to_clear"] is False

    execute_request = SkillExecutionRequest.parse(
        request_document(
            skill="elmos-human-review-and-correction",
            operation="enqueue_execute",
            idempotency_key="sdk-enqueue-execute-0001",
            input={"recovery_handle": recovery_handle},
        )
    )
    absence = {
        "schema_version": "human-review-enqueue-preparation-absence-v1",
        "recovery_handle": recovery_handle,
        "state": "ABSENT",
        "safe_to_clear": True,
    }
    absent = execution_result(
        execute_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT",
        output={**metadata, "preparation": absence},
    )
    assert validate_execution_result(
        absent, expected_request=execute_request
    )["output"]["preparation"]["state"] == "ABSENT"

    expired_preparation = {
        **preparation,
        "state": "EXPIRED",
        "safe_to_clear": True,
    }
    expired = execution_result(
        execute_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED",
        output={**metadata, "preparation": expired_preparation},
    )
    assert validate_execution_result(
        expired, expected_request=execute_request
    )["output"]["preparation"]["state"] == "EXPIRED"
    unsafe_expired = execution_result(
        execute_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED",
        output={
            **metadata,
            "preparation": {**expired_preparation, "safe_to_clear": False},
        },
    )
    with pytest.raises(
        SdkError, match="SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID"
    ):
        validate_execution_result(unsafe_expired, expected_request=execute_request)

    executed_preparation = {
        **preparation,
        "state": "EXECUTED",
        "safe_to_clear": True,
        "executed_at": "2026-08-22T00:00:01+00:00",
        "task_id": task["task_id"],
    }
    executed = execution_result(
        execute_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        output={**metadata, "preparation": executed_preparation, "task": task},
    )
    assert validate_execution_result(
        executed, expected_request=execute_request
    )["output"]["task"]["task_id"] == task["task_id"]
    forged_task = {**task, "tenant_id": "tenant-b"}
    forged = execution_result(
        execute_request,
        status="SUCCEEDED",
        code="HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        output={
            **metadata,
            "preparation": executed_preparation,
            "task": forged_task,
        },
    )
    with pytest.raises(SdkError, match="SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID"):
        validate_execution_result(forged, expected_request=execute_request)


def test_typescript_and_java_wire_exact_human_review_response_validators() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    typescript_sdk = (
        repository_root / "sdk/multimodal-intake/typescript/client.ts"
    ).read_text(encoding="utf-8")
    java_sdk = (
        repository_root
        / "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java"
    ).read_text(encoding="utf-8")
    for marker in (
        "validateHumanReviewExecutionOutput",
        "validateHumanReviewSourceCursor",
        "validateHumanReviewSourceRef",
        "validateHumanReviewPreparation",
        "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT",
        "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED",
    ):
        assert marker in typescript_sdk
    for marker in (
        "validateHumanReviewExecutionOutput",
        "humanReviewSourceCursor",
        "humanReviewSourceRef",
        "humanReviewPreparation",
        "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT",
        "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED",
    ):
        assert marker in java_sdk
    assert "validateHumanReviewExecutionOutput(output, expected, value.code)" in typescript_sdk
    assert "validateHumanReviewExecutionOutput(output, expected, value.get(\"code\"))" in java_sdk


def test_openapi_declares_opaque_enqueue_recovery_and_source_cursor_caps() -> None:
    contract = (
        Path(__file__).resolve().parents[1]
        / "openapi/multimodal-intake-v1.openapi.yaml"
    ).read_text(encoding="utf-8")
    for marker in (
        "x-elmos-human-review-enqueue-prepare:",
        "x-elmos-human-review-enqueue-execute:",
        "HumanReviewEnqueuePrepareInput:",
        "HumanReviewEnqueueExecuteInput:",
        "HumanReviewEnqueuePreparation:",
        "HumanReviewEnqueuePreparationAbsence:",
        "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION",
        "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT",
        "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED",
        "ttlSeconds: 86400",
        "activeQuotaPerActor: 100",
        "retainedQuotaPerActor: 10000",
        "total: { type: integer, minimum: 0, maximum: 1000 }",
    ):
        assert marker in contract
