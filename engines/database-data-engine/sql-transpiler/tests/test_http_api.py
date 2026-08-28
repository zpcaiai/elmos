from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

import elmos_sql_transpiler.http_api as http_api
from elmos_sql_transpiler.commercial import assess_commercial, commercial_capabilities
from elmos_sql_transpiler.commercial_request import parse_commercial_request_json


def _request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": "1.0",
        "queryId": "http-commercial-preflight",
        "sourceProfile": "oracle-26ai-ee",
        "targetId": "dm8",
        "targetVersion": "8.1.3.140",
        "targetEdition": "enterprise",
        "compatibilityMode": "oracle-compatible-explicit",
        "targetDriver": "dm-jdbc-8.1.3.140",
        "targetCharset": "UTF-8",
        "targetCollation": "BINARY",
        "targetTimeZone": "Asia/Shanghai",
        "capabilitySnapshotDigest": commercial_capabilities()["capabilitySnapshotDigest"],
        "sql": "SELECT id FROM orders WHERE tenant_id = :tenant_id ORDER BY id",
        "parameters": [{"name": "tenant_id", "logicalType": "unicode-text", "nullable": False}],
    }
    value.update(changes)
    return value


def _skill_request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "scope": {
            "tenantId": "tenant-1",
            "projectId": "project-1",
            "actorId": "actor-1",
        },
        "objects": [],
    }
    value.update(changes)
    return value


def _inline_isolated(request: Any) -> bytes:
    result = assess_commercial(
        request,
        max_statements=http_api.MAX_HTTP_STATEMENTS,
    ).to_dict()
    http_api._assert_fail_closed_assessment(result)
    return http_api._bounded_json_bytes(
        result,
        maximum=http_api.MAX_HTTP_RESPONSE_BYTES,
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(http_api, "_run_assessment_isolated", _inline_isolated)
    return TestClient(http_api.app, raise_server_exceptions=False)


def test_health_and_capabilities_are_bounded_fail_closed_contracts(
    client: TestClient,
) -> None:
    live = client.get("/livez")
    assert live.status_code == 200
    assert live.json() == {"status": "UP", "service": "chinadb-sql-preflight"}

    health = client.get("/readyz")
    assert health.status_code == 200
    assert health.json() == {
        "status": "READY",
        "service": "chinadb-sql-preflight",
        "targetCount": 13,
        "plannedRouteCount": 78,
        "skillHandlerCount": 47,
    }
    assert health.headers["cache-control"] == "private, no-store"

    response = client.get("/internal/v1/chinadb-sql/capabilities")
    value = response.json()
    assert response.status_code == 200
    assert len(response.content) <= http_api.MAX_HTTP_RESPONSE_BYTES
    assert value["targetCount"] == 13
    assert value["plannedRouteCount"] == 78
    assert value["implementationStatus"] == "SPEC_ONLY"
    assert value["externalExecution"] == "NOT_RUN"
    assert value["certification"] == "NOT_CERTIFIED"
    assert value["boundaries"]["targetSqlMayBeEmitted"] is False

    skill_response = client.get("/internal/v1/chinadb-skills/capabilities")
    skills = skill_response.json()
    assert skill_response.status_code == 200
    assert skills["skillCount"] == skills["codeImplementedCount"] == 47
    assert skills["boundedLocalHandlerCoverage"]["rate"] == 1.0
    assert skills["productionDefinitionOfDoneCount"] == 0
    assert skills["externalExecution"] == "NOT_RUN"
    assert skills["independentVerification"] == "NOT_RUN"
    assert skills["certification"] == "NOT_CERTIFIED"


def test_skill_http_execution_is_scope_bound_and_fail_closed(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/chinadb-skills/01-estate-inventory-assessment/execute",
        json=_skill_request(),
    )
    value = response.json()

    assert response.status_code == 200
    assert value["skillId"] == "01-estate-inventory-assessment"
    assert value["state"] == "LOCAL_COMPLETED"
    assert value["scope"]["tenantId"] == "tenant-1"
    assert value["effects"]["externalEffectsExecuted"] == []
    assert value["verification"]["externalExecution"] == "NOT_RUN"
    assert value["verification"]["independentVerification"] == "NOT_RUN"
    assert value["certification"] == "NOT_CERTIFIED"


def test_skill_http_rejects_unknown_duplicate_secret_and_stale_inputs(
    client: TestClient,
) -> None:
    unknown = client.post(
        "/internal/v1/chinadb-skills/not-a-skill/execute",
        json=_skill_request(),
    )
    assert unknown.status_code == 404
    assert unknown.json()["errorCode"] == "CHINADB_SKILL_UNKNOWN"

    secret = client.post(
        "/internal/v1/chinadb-skills/01-estate-inventory-assessment/execute",
        json=_skill_request(password="inline-secret"),
    )
    assert secret.status_code == 422
    assert secret.json()["errorCode"] == "CHINADB_SKILL_EXECUTION_REJECTED"

    duplicate = (
        '{"scope":{"tenantId":"tenant-1","projectId":"project-1",'
        '"actorId":"actor-1"},"objects":[],"objects":[]}'
    )
    duplicate_response = client.post(
        "/internal/v1/chinadb-skills/01-estate-inventory-assessment/execute",
        content=duplicate.encode(),
        headers={"content-type": "application/json"},
    )
    assert duplicate_response.status_code == 422
    assert duplicate_response.json()["errorCode"] == "CHINADB_SKILL_REQUEST_REJECTED"

    stale_target = client.post(
        "/internal/v1/chinadb-skills/40-target-dm8/execute",
        json={
            "scope": _skill_request()["scope"],
            "target": {
                "id": "dm8",
                "version": "8.1.3.140",
                "edition": "enterprise",
                "compatibilityMode": "native-explicit",
                "driver": "dm-jdbc-8.1.3.140",
                "capabilitySnapshotDigest": "sha256:" + "0" * 64,
            },
        },
    )
    assert stale_target.status_code == 422
    assert stale_target.json()["errorCode"] == "CHINADB_SKILL_EXECUTION_REJECTED"


def test_valid_typed_preflight_returns_http_200_but_never_target_sql(
    client: TestClient,
) -> None:
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        json=_request(),
    )
    value = response.json()

    assert response.status_code == 200
    assert value["state"] == "BLOCKED"
    assert value["targetSql"] is None
    assert value["verification"]["sourceParse"] == "PASSED"
    assert all(
        value["verification"][field] == "NOT_RUN"
        for field in (
            "targetAdapter",
            "targetEmit",
            "targetReparse",
            "sourceExecution",
            "targetExecution",
            "resultEquivalence",
            "externalExecution",
        )
    )
    assert value["certification"] == "NOT_CERTIFIED"
    assert value["statements"][0]["sourceAst"]
    assert value["blockers"]


def test_source_parse_failure_is_still_a_typed_http_200_blocked_result(
    client: TestClient,
) -> None:
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        json=_request(sql="SELECT 'unterminated", parameters=[]),
    )
    value = response.json()

    assert response.status_code == 200
    assert value["state"] == "BLOCKED"
    assert value["targetSql"] is None
    assert value["verification"]["sourceParse"] == "FAILED"
    assert value["statements"] == []
    assert [item["code"] for item in value["blockers"]] == ["SOURCE_PARSE_FAILED"]


@pytest.mark.parametrize(
    ("headers", "expected_status", "expected_code"),
    [
        ({"content-type": "text/plain"}, 415, "CHINADB_PREFLIGHT_JSON_REQUIRED"),
        (
            {"content-type": "application/json", "content-encoding": "gzip"},
            415,
            "CHINADB_PREFLIGHT_CONTENT_ENCODING_REJECTED",
        ),
        (
            {"content-type": "application/json", "transfer-encoding": "chunked"},
            400,
            "CHINADB_PREFLIGHT_TRANSFER_ENCODING_REJECTED",
        ),
    ],
)
def test_transport_contract_rejects_ambiguous_or_encoded_bodies(
    client: TestClient,
    headers: dict[str, str],
    expected_status: int,
    expected_code: str,
) -> None:
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        content=json.dumps(_request()).encode(),
        headers=headers,
    )
    value = response.json()

    assert response.status_code == expected_status
    assert value["status"] == "BLOCKED"
    assert value["errorCode"] == expected_code
    assert value["targetSql"] is None
    assert value["certification"] == "NOT_CERTIFIED"


def test_duplicate_json_fields_and_type_coercion_are_rejected(
    client: TestClient,
) -> None:
    payload = json.dumps(_request(), separators=(",", ":"))
    duplicate = payload.replace(
        '"schemaVersion":"1.0",',
        '"schemaVersion":"1.0","schemaVersion":"1.0",',
        1,
    )
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        content=duplicate.encode(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "COMMERCIAL_REQUEST_DUPLICATE_FIELD"

    coerced = _request()
    coerced["targetVersion"] = 813140
    response = client.post("/internal/v1/chinadb-sql/assess", json=coerced)
    assert response.status_code == 400
    assert response.json()["errorCode"] == "COMMERCIAL_REQUEST_STRING_REQUIRED"

    stale = _request(capabilitySnapshotDigest="sha256:" + "0" * 64)
    response = client.post("/internal/v1/chinadb-sql/assess", json=stale)
    assert response.status_code == 409
    assert response.json()["errorCode"] == "CHINADB_PREFLIGHT_CAPABILITY_SNAPSHOT_STALE"

    lone_surrogate_request = _request(sql="SELECT 1")
    lone_surrogate = json.dumps(lone_surrogate_request, separators=(",", ":")).replace(
        '"sql":"SELECT 1"',
        '"sql":"SELECT \\ud800"',
        1,
    )
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        content=lone_surrogate.encode(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "COMMERCIAL_REQUEST_UTF8_REQUIRED"


def test_http_sql_and_parameter_limits_fail_closed(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        json=_request(sql="X" * (http_api.MAX_HTTP_SQL_BYTES + 1)),
    )
    assert response.status_code == 413
    assert response.json()["errorCode"] == "COMMERCIAL_REQUEST_SQL_TOO_LARGE"

    parameters = [
        {"name": f"p{index}", "logicalType": "text", "nullable": False}
        for index in range(http_api.MAX_HTTP_PARAMETERS + 1)
    ]
    response = client.post(
        "/internal/v1/chinadb-sql/assess",
        json=_request(parameters=parameters),
    )
    assert response.status_code == 413
    assert response.json()["errorCode"] == "COMMERCIAL_REQUEST_PARAMETERS_TOO_LARGE"


def test_declared_length_and_fail_closed_result_guards_reject_drift() -> None:
    with pytest.raises(http_api.SidecarFailure) as missing:
        http_api._declared_content_length(None)
    assert missing.value.status_code == 411

    with pytest.raises(http_api.SidecarFailure) as oversized:
        http_api._declared_content_length(str(http_api.MAX_HTTP_ENVELOPE_BYTES + 1))
    assert oversized.value.status_code == 413

    fabricated = {
        "state": "SYNTAX_READY",
        "targetSql": "SELECT 1",
        "certification": "CERTIFIED",
        "statements": [],
        "verification": {"sourceParse": "PASSED"},
    }
    with pytest.raises(AssertionError, match="contract|fail-closed"):
        http_api._assert_fail_closed_assessment(fabricated)

    missing_target_sql = _inline_isolated(
        parse_commercial_request_json(json.dumps(_request()).encode())
    )
    missing_value = json.loads(missing_target_sql)
    missing_value.pop("targetSql")
    with pytest.raises(AssertionError, match="fields"):
        http_api._assert_fail_closed_assessment(missing_value)


def test_sidecar_failure_preserves_original_exception_through_context_manager() -> None:
    @contextmanager
    def boundary() -> Iterator[None]:
        yield

    with pytest.raises(http_api.SidecarFailure) as captured, boundary():
        raise http_api.SidecarFailure(504, "TIMEOUT", "bounded timeout", True)

    assert captured.value.status_code == 504
    assert captured.value.error_code == "TIMEOUT"


def test_unknown_http_route_uses_fail_closed_error_envelope(client: TestClient) -> None:
    response = client.get("/internal/v1/chinadb-sql/not-found")
    value = response.json()

    assert response.status_code == 404
    assert value["status"] == "BLOCKED"
    assert value["targetSql"] is None
    assert value["verification"]["externalExecution"] == "NOT_RUN"
    assert value["certification"] == "NOT_CERTIFIED"


def test_isolated_assessment_process_returns_only_bounded_blocked_json() -> None:
    request = parse_commercial_request_json(json.dumps(_request(), separators=(",", ":")).encode())
    payload = http_api._run_assessment_isolated(request)
    value = json.loads(payload)

    assert len(payload) <= http_api.MAX_HTTP_RESPONSE_BYTES
    assert value["state"] == "BLOCKED"
    assert value["targetSql"] is None
    assert value["certification"] == "NOT_CERTIFIED"
