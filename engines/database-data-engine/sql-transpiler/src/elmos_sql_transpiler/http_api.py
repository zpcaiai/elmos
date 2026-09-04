from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, NoReturn, Protocol

import anyio
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from .commercial import assess_commercial, commercial_capabilities
from .commercial_request import (
    CommercialRequestError,
    CommercialRequestLimits,
    parse_commercial_request_json,
)
from .models import CommercialAssessRequest
from .production_qualification import (
    evaluate_production_qualification,
    parse_production_qualification_json,
    parse_production_trust_store_json,
    production_qualification_requirements,
    production_trust_store_digest,
)
from .skill_runtime import (
    MAX_REQUEST_BYTES,
    SKILLS_BY_ID,
    execute_skill,
    parse_skill_request_json,
    skill_capabilities,
)
from .transpiler import _require_pinned_parser

MAX_HTTP_ENVELOPE_BYTES = 1_310_720
MAX_HTTP_SQL_BYTES = 256 * 1024
MAX_HTTP_PARAMETERS = 256
MAX_HTTP_STATEMENTS = 256
MAX_HTTP_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_CONCURRENT_ASSESSMENTS = 1
MAX_CONCURRENT_SKILL_RUNS = 4
MAX_CONCURRENT_PRODUCTION_PLANS = 2
ASSESSMENT_TIMEOUT_SECONDS = 15.0
ASSESSMENT_MAX_NORMALIZED_LOAD = 1.5

_HTTP_REQUEST_LIMITS = CommercialRequestLimits(
    max_envelope_bytes=MAX_HTTP_ENVELOPE_BYTES,
    max_sql_bytes=MAX_HTTP_SQL_BYTES,
    max_parameters=MAX_HTTP_PARAMETERS,
)
_ASSESSMENT_PREFIX = b"A"
_REQUEST_ERROR_PREFIX = b"R"
_UNAVAILABLE_PREFIX = b"U"
_OUTPUT_LIMIT_PREFIX = b"L"
_INTERNAL_ERROR_PREFIX = b"I"


@dataclass
class SidecarFailure(Exception):
    status_code: int
    error_code: str
    message: str
    retryable: bool = False


class _ResponseLimitExceeded(RuntimeError):
    pass


class _ManagedProcess(Protocol):
    def is_alive(self) -> bool: ...

    def join(self, timeout: float | None = None) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class AssessmentConcurrencyGate:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("assessment concurrency limit must be positive")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._active < 1:
                raise RuntimeError("assessment concurrency gate release is unbalanced")
            self._active -= 1


def _bounded_json_bytes(value: object, *, maximum: int) -> bytes:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    rendered: list[bytes] = []
    size = 0
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8")
        size += len(encoded)
        if size > maximum:
            raise _ResponseLimitExceeded("JSON response exceeds the configured byte limit")
        rendered.append(encoded)
    return b"".join(rendered)


def _assert_fail_closed_assessment(value: dict[str, Any]) -> None:
    expected_fields = {
        "schemaVersion",
        "queryId",
        "sourceProfile",
        "target",
        "routeId",
        "state",
        "sourceDigest",
        "capabilitySnapshotDigest",
        "statements",
        "blockers",
        "targetSql",
        "verification",
        "certification",
    }
    if set(value) != expected_fields or "targetSql" not in value:
        raise AssertionError("commercial assessment fields escaped the exact contract")
    verification = value.get("verification")
    if not isinstance(verification, dict):
        raise AssertionError("commercial assessment verification is absent")
    source_parse = verification.get("sourceParse")
    execution_not_run = {
        "sourceExecution",
        "targetExecution",
        "resultEquivalence",
        "externalExecution",
    }
    required_verification = execution_not_run | {
        "sourceParse",
        "targetAdapter",
        "targetEmit",
        "targetReparse",
    }
    if set(verification) != required_verification:
        raise AssertionError("commercial assessment verification fields are not exact")
    state = value.get("state")
    target_sql = value.get("targetSql")
    if value.get("certification") != "NOT_CERTIFIED" or source_parse not in {"PASSED", "FAILED"}:
        raise AssertionError("commercial assessment escaped fail-closed boundaries")
    if any(verification.get(field) != "NOT_RUN" for field in execution_not_run):
        raise AssertionError("commercial assessment escaped fail-closed boundaries")
    statements = value.get("statements")
    blockers = value.get("blockers")
    if not isinstance(statements, list) or not isinstance(blockers, list) or not blockers:
        raise AssertionError("commercial assessment statements are absent")
    error_blockers = [
        item for item in blockers if isinstance(item, dict) and item.get("severity") == "ERROR"
    ]
    if state == "BLOCKED":
        if target_sql is not None:
            raise AssertionError("commercial assessment escaped fail-closed boundaries")
    elif state == "LOCAL_EMITTED":
        if not isinstance(target_sql, str) or not target_sql.strip():
            raise AssertionError("commercial assessment escaped fail-closed boundaries")
        if (
            source_parse != "PASSED"
            or verification.get("targetAdapter") != "PASSED"
            or verification.get("targetEmit") != "PASSED"
            or verification.get("targetReparse") != "PASSED"
            or error_blockers
        ):
            raise AssertionError("commercial assessment escaped fail-closed boundaries")
    else:
        raise AssertionError("commercial assessment escaped fail-closed boundaries")
    if (source_parse == "PASSED" and not statements) or (source_parse == "FAILED" and statements):
        raise AssertionError("commercial assessment parse evidence is inconsistent")
    for statement in statements:
        if (
            not isinstance(statement, dict)
            or set(statement) != {"index", "kind", "sourceAst", "obligations"}
            or not isinstance(statement.get("sourceAst"), (dict, list))
            or not statement["sourceAst"]
            or not isinstance(statement.get("obligations"), list)
            or not statement["obligations"]
        ):
            raise AssertionError("commercial assessment typed statements are invalid")


def _assert_fail_closed_skill_result(value: dict[str, Any]) -> None:
    required = {
        "schemaVersion",
        "package",
        "runtimeVersion",
        "skillId",
        "alias",
        "handlerId",
        "scope",
        "state",
        "localCodeStatus",
        "requestDigest",
        "artifactDigest",
        "artifacts",
        "checks",
        "blockers",
        "effects",
        "verification",
        "certification",
        "resultDigest",
    }
    if set(value) != required:
        raise AssertionError("commercial Skill result fields escaped the exact contract")
    effects = value.get("effects")
    verification = value.get("verification")
    if not isinstance(effects, dict) or not isinstance(verification, dict):
        raise AssertionError("commercial Skill result evidence boundary is absent")
    if (
        value.get("localCodeStatus") != "CODE_IMPLEMENTED"
        or value.get("certification") != "NOT_CERTIFIED"
        or effects.get("externalEffectsExecuted") != []
        or verification.get("externalExecution") != "NOT_RUN"
        or verification.get("independentVerification") != "NOT_RUN"
    ):
        raise AssertionError("commercial Skill result escaped fail-closed boundaries")


def _assert_production_qualification_result(value: dict[str, Any]) -> None:
    summary = value.get("summary")
    effects = value.get("effects")
    targets = value.get("targets")
    if (
        value.get("targetSql") is not None
        or not isinstance(summary, dict)
        or not isinstance(effects, dict)
        or effects.get("externalCallsExecuted") != []
        or not isinstance(targets, list)
        or len(targets) != 13
    ):
        raise AssertionError("production qualification result escaped its no-effect boundary")
    certified = sum(
        isinstance(target, dict) and target.get("certification") == "CERTIFIED"
        for target in targets
    )
    if summary.get("productionDefinitionOfDoneCount") != certified:
        raise AssertionError("production qualification count is not evidence-derived")
    if value.get("productionDefinitionOfDoneCount") != certified:
        raise AssertionError("top-level production qualification count is not evidence-derived")


def _send_child_message(connection: Connection, value: bytes) -> None:
    try:
        connection.send_bytes(value)
    finally:
        connection.close()


def _assessment_child(
    connection: Connection,
    request: CommercialAssessRequest,
) -> None:
    try:
        result = assess_commercial(
            request,
            max_statements=MAX_HTTP_STATEMENTS,
        ).to_dict()
        _assert_fail_closed_assessment(result)
        payload = _bounded_json_bytes(result, maximum=MAX_HTTP_RESPONSE_BYTES)
        _send_child_message(connection, _ASSESSMENT_PREFIX + payload)
    except _ResponseLimitExceeded:
        _send_child_message(connection, _OUTPUT_LIMIT_PREFIX)
    except (KeyError, TypeError, ValueError):
        _send_child_message(connection, _REQUEST_ERROR_PREFIX)
    except RuntimeError:
        _send_child_message(connection, _UNAVAILABLE_PREFIX)
    except BaseException:
        _send_child_message(connection, _INTERNAL_ERROR_PREFIX)


def _stop_process(process: _ManagedProcess) -> None:
    if not process.is_alive():
        process.join(timeout=0.1)
        return
    process.terminate()
    process.join(timeout=0.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=0.5)


def _raise_child_failure(prefix: bytes) -> NoReturn:
    if prefix == _REQUEST_ERROR_PREFIX:
        raise SidecarFailure(
            422,
            "CHINADB_PREFLIGHT_REQUEST_REJECTED",
            "ChinaDB SQL preflight rejected the exact request contract.",
        )
    if prefix == _OUTPUT_LIMIT_PREFIX:
        raise SidecarFailure(
            413,
            "CHINADB_PREFLIGHT_RESULT_TOO_LARGE",
            "ChinaDB SQL preflight result exceeds the bounded response limit.",
        )
    if prefix == _UNAVAILABLE_PREFIX:
        raise SidecarFailure(
            503,
            "CHINADB_PREFLIGHT_UNAVAILABLE",
            "ChinaDB SQL preflight is unavailable and no target operation ran.",
            retryable=True,
        )
    raise SidecarFailure(
        500,
        "CHINADB_PREFLIGHT_INTERNAL_ERROR",
        "ChinaDB SQL preflight failed closed and no target operation ran.",
    )


def _assessment_host_admitted() -> bool:
    raw_threshold = os.environ.get(
        "ELMOS_CHINADB_MAX_NORMALIZED_LOAD",
        str(ASSESSMENT_MAX_NORMALIZED_LOAD),
    )
    try:
        threshold = float(raw_threshold)
    except ValueError:
        return False
    if not 0.1 <= threshold <= 4.0 or not hasattr(os, "getloadavg"):
        return False
    cpu_count = max(1, os.cpu_count() or 1)
    normalized_load = os.getloadavg()[0] / cpu_count
    return normalized_load <= threshold


def _run_assessment_isolated(request: CommercialAssessRequest) -> bytes:
    if not _assessment_host_admitted():
        raise SidecarFailure(
            503,
            "CHINADB_PREFLIGHT_HOST_OVERLOADED",
            "ChinaDB SQL preflight host load exceeds the bounded admission threshold.",
            retryable=True,
        )
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_assessment_child,
        args=(child_connection, request),
        daemon=True,
        name="chinadb-sql-preflight-assessment",
    )
    try:
        process.start()
    except Exception as error:
        parent_connection.close()
        child_connection.close()
        raise SidecarFailure(
            503,
            "CHINADB_PREFLIGHT_PROCESS_UNAVAILABLE",
            "ChinaDB SQL preflight isolation process could not start.",
            retryable=True,
        ) from error
    child_connection.close()
    deadline = time.monotonic() + ASSESSMENT_TIMEOUT_SECONDS
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_process(process)
                raise SidecarFailure(
                    504,
                    "CHINADB_PREFLIGHT_TIMEOUT",
                    "ChinaDB SQL preflight exceeded the bounded execution deadline.",
                    retryable=True,
                )
            if parent_connection.poll(min(remaining, 0.05)):
                try:
                    message = parent_connection.recv_bytes(MAX_HTTP_RESPONSE_BYTES + 1)
                except (EOFError, OSError) as error:
                    _stop_process(process)
                    raise SidecarFailure(
                        500,
                        "CHINADB_PREFLIGHT_CHILD_RESPONSE_INVALID",
                        "ChinaDB SQL preflight returned an invalid bounded response.",
                    ) from error
                process.join(timeout=0.5)
                if process.is_alive():
                    _stop_process(process)
                if not message:
                    _raise_child_failure(_INTERNAL_ERROR_PREFIX)
                if message[:1] != _ASSESSMENT_PREFIX:
                    _raise_child_failure(message[:1])
                return message[1:]
            if not process.is_alive():
                process.join(timeout=0.1)
                _raise_child_failure(_INTERNAL_ERROR_PREFIX)
    finally:
        parent_connection.close()
        if process.is_alive():
            _stop_process(process)


def _content_type_is_json(value: str | None) -> bool:
    if value is None:
        return False
    parts = [part.strip() for part in value.split(";")]
    if not parts or parts[0].lower() != "application/json":
        return False
    parameters = parts[1:]
    return not parameters or (
        len(parameters) == 1 and parameters[0].lower().replace(" ", "") == "charset=utf-8"
    )


def _declared_content_length(value: str | None) -> int:
    if value is None or value == "":
        raise SidecarFailure(
            411,
            "CHINADB_PREFLIGHT_CONTENT_LENGTH_REQUIRED",
            "ChinaDB SQL preflight requires a declared request length.",
        )
    if not value.isascii() or not value.isdigit():
        raise SidecarFailure(
            400,
            "CHINADB_PREFLIGHT_CONTENT_LENGTH_INVALID",
            "ChinaDB SQL preflight request length is invalid.",
        )
    length = int(value)
    if length > MAX_HTTP_ENVELOPE_BYTES:
        raise SidecarFailure(
            413,
            "CHINADB_PREFLIGHT_ENVELOPE_TOO_LARGE",
            "ChinaDB SQL preflight request exceeds the bounded envelope limit.",
        )
    return length


async def _read_request_body(request: Request, declared_length: int) -> bytes:
    body = bytearray()
    try:
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_HTTP_ENVELOPE_BYTES:
                raise SidecarFailure(
                    413,
                    "CHINADB_PREFLIGHT_ENVELOPE_TOO_LARGE",
                    "ChinaDB SQL preflight request exceeds the bounded envelope limit.",
                )
            body.extend(chunk)
    except ClientDisconnect as error:
        raise SidecarFailure(
            400,
            "CHINADB_PREFLIGHT_CLIENT_DISCONNECTED",
            "ChinaDB SQL preflight request ended before its body was complete.",
        ) from error
    if len(body) != declared_length:
        raise SidecarFailure(
            400,
            "CHINADB_PREFLIGHT_CONTENT_LENGTH_MISMATCH",
            "ChinaDB SQL preflight request length does not match its body.",
        )
    return bytes(body)


def _error_payload(failure: SidecarFailure) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "status": "BLOCKED",
        "errorCode": failure.error_code,
        "message": failure.message,
        "retryable": failure.retryable,
        "targetSql": None,
        "verification": {
            "sourceParse": "NOT_RUN",
            "targetAdapter": "NOT_RUN",
            "targetEmit": "NOT_RUN",
            "targetReparse": "NOT_RUN",
            "sourceExecution": "NOT_RUN",
            "targetExecution": "NOT_RUN",
            "resultEquivalence": "NOT_RUN",
            "externalExecution": "NOT_RUN",
        },
        "certification": "NOT_CERTIFIED",
    }


def _error_response(failure: SidecarFailure) -> JSONResponse:
    return JSONResponse(
        _error_payload(failure),
        status_code=failure.status_code,
        headers={"cache-control": "private, no-store"},
    )


def _json_response(payload: bytes, *, status_code: int = 200) -> Response:
    return Response(
        content=payload,
        status_code=status_code,
        media_type="application/json",
        headers={"cache-control": "private, no-store"},
    )


app = FastAPI(
    title="ELMOS ChinaDB SQL preflight",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
_assessment_gate = AssessmentConcurrencyGate(MAX_CONCURRENT_ASSESSMENTS)
_skill_gate = AssessmentConcurrencyGate(MAX_CONCURRENT_SKILL_RUNS)
_production_plan_gate = AssessmentConcurrencyGate(MAX_CONCURRENT_PRODUCTION_PLANS)


def _configured_production_trust_store() -> dict[str, Any] | None:
    raw_path = os.environ.get("ELMOS_CHINADB_QUALIFICATION_TRUST_STORE")
    expected_digest = os.environ.get("ELMOS_CHINADB_QUALIFICATION_TRUST_STORE_DIGEST")
    if raw_path is None and expected_digest is None:
        return None
    if not raw_path or not expected_digest:
        raise RuntimeError(
            "ChinaDB qualification trust store path and digest must be configured together"
        )
    path = Path(raw_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError("ChinaDB qualification trust store must be an absolute regular file")
    if path.stat().st_size > MAX_REQUEST_BYTES:
        raise RuntimeError("ChinaDB qualification trust store exceeds the bounded size")
    trust_store = parse_production_trust_store_json(path.read_bytes())
    if production_trust_store_digest(trust_store) != expected_digest:
        raise RuntimeError("ChinaDB qualification trust store digest mismatch")
    return trust_store


@app.middleware("http")
async def _security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["cache-control"] = "private, no-store"
    response.headers["x-content-type-options"] = "nosniff"
    return response


@app.exception_handler(Exception)
async def _unexpected_exception(_: Request, __: Exception) -> JSONResponse:
    return _error_response(
        SidecarFailure(
            500,
            "CHINADB_PREFLIGHT_INTERNAL_ERROR",
            "ChinaDB SQL preflight failed closed and no target operation ran.",
        )
    )


@app.exception_handler(StarletteHTTPException)
async def _http_exception(_: Request, error: StarletteHTTPException) -> JSONResponse:
    return _error_response(
        SidecarFailure(
            error.status_code,
            "CHINADB_PREFLIGHT_HTTP_REJECTED",
            "ChinaDB SQL preflight rejected the HTTP route or method.",
        )
    )


@app.get("/livez")
async def livez() -> dict[str, str]:
    return {
        "status": "UP",
        "service": "chinadb-sql-preflight",
    }


def _readiness() -> dict[str, str | int]:
    _require_pinned_parser()
    capabilities = commercial_capabilities()
    skills = skill_capabilities()
    production = production_qualification_requirements()
    if (
        capabilities.get("targetCount") != 13
        or capabilities.get("plannedRouteCount") != 78
        or capabilities.get("implementationStatus") != "LOCAL_ADAPTER"
        or capabilities.get("externalExecution") != "NOT_RUN"
        or capabilities.get("certification") != "NOT_CERTIFIED"
        or skills.get("skillCount") != 47
        or skills.get("codeImplementedCount") != 47
        or skills.get("externalExecution") != "NOT_RUN"
        or skills.get("certification") != "NOT_CERTIFIED"
        or production.get("targetCount") != 13
        or production.get("productionBoundaries", {}).get("externalExecution") != "NOT_RUN"
        or production.get("productionBoundaries", {}).get("certification") != "NOT_CERTIFIED"
    ):
        raise RuntimeError("ChinaDB commercial capability registry is not fail closed")
    return {
        "status": "READY",
        "service": "chinadb-sql-preflight",
        "targetCount": 13,
        "plannedRouteCount": 78,
        "skillHandlerCount": 47,
    }


@app.get("/readyz")
@app.get("/health")
async def readyz() -> Response:
    try:
        return JSONResponse(_readiness())
    except (KeyError, RuntimeError, TypeError, ValueError):
        return _error_response(
            SidecarFailure(
                503,
                "CHINADB_PREFLIGHT_NOT_READY",
                "ChinaDB SQL preflight parser or capability registry is not ready.",
                retryable=True,
            )
        )


@app.get("/internal/v1/chinadb-sql/capabilities")
async def capabilities_endpoint() -> Response:
    try:
        _require_pinned_parser()
        payload = _bounded_json_bytes(
            commercial_capabilities(),
            maximum=MAX_HTTP_RESPONSE_BYTES,
        )
        return _json_response(payload)
    except _ResponseLimitExceeded:
        return _error_response(
            SidecarFailure(
                500,
                "CHINADB_PREFLIGHT_CAPABILITIES_TOO_LARGE",
                "ChinaDB SQL capability response exceeds its bounded limit.",
            )
        )
    except (KeyError, RuntimeError, TypeError, ValueError):
        return _error_response(
            SidecarFailure(
                503,
                "CHINADB_PREFLIGHT_CAPABILITIES_UNAVAILABLE",
                "ChinaDB SQL capabilities are unavailable.",
                retryable=True,
            )
        )


@app.get("/internal/v1/chinadb-skills/capabilities")
async def skill_capabilities_endpoint() -> Response:
    try:
        payload = _bounded_json_bytes(
            skill_capabilities(),
            maximum=MAX_HTTP_RESPONSE_BYTES,
        )
        return _json_response(payload)
    except _ResponseLimitExceeded:
        return _error_response(
            SidecarFailure(
                500,
                "CHINADB_SKILL_CAPABILITIES_TOO_LARGE",
                "ChinaDB Skill capability response exceeds its bounded limit.",
            )
        )
    except (KeyError, RuntimeError, TypeError, ValueError):
        return _error_response(
            SidecarFailure(
                503,
                "CHINADB_SKILL_CAPABILITIES_UNAVAILABLE",
                "ChinaDB Skill capabilities are unavailable.",
                retryable=True,
            )
        )


@app.get("/internal/v1/chinadb-production/requirements")
async def production_requirements_endpoint() -> Response:
    try:
        payload = _bounded_json_bytes(
            production_qualification_requirements(),
            maximum=MAX_HTTP_RESPONSE_BYTES,
        )
        return _json_response(payload)
    except _ResponseLimitExceeded:
        return _error_response(
            SidecarFailure(
                500,
                "CHINADB_PRODUCTION_REQUIREMENTS_TOO_LARGE",
                "ChinaDB production requirements exceed the bounded response limit.",
            )
        )
    except (KeyError, RuntimeError, TypeError, ValueError):
        return _error_response(
            SidecarFailure(
                503,
                "CHINADB_PRODUCTION_REQUIREMENTS_UNAVAILABLE",
                "ChinaDB production requirements are unavailable.",
                retryable=True,
            )
        )


@app.post("/internal/v1/chinadb-production/plan")
async def production_plan_endpoint(request: Request) -> Response:
    try:
        if not _content_type_is_json(request.headers.get("content-type")):
            raise SidecarFailure(
                415,
                "CHINADB_PRODUCTION_JSON_REQUIRED",
                "ChinaDB production planning accepts only UTF-8 application/json.",
            )
        if request.headers.get("content-encoding") not in {None, "", "identity"}:
            raise SidecarFailure(
                415,
                "CHINADB_PRODUCTION_CONTENT_ENCODING_REJECTED",
                "ChinaDB production planning does not accept encoded request bodies.",
            )
        if request.headers.get("transfer-encoding") not in {None, ""}:
            raise SidecarFailure(
                400,
                "CHINADB_PRODUCTION_TRANSFER_ENCODING_REJECTED",
                "ChinaDB production planning requires one bounded content-length body.",
            )
        declared_length = _declared_content_length(request.headers.get("content-length"))
        if declared_length > MAX_REQUEST_BYTES:
            raise SidecarFailure(
                413,
                "CHINADB_PRODUCTION_REQUEST_TOO_LARGE",
                "ChinaDB production planning request exceeds the bounded input limit.",
            )
        raw_payload = await _read_request_body(request, declared_length)
        try:
            qualification_request = parse_production_qualification_json(raw_payload)
            trust_store = _configured_production_trust_store()
        except (OSError, RuntimeError, ValueError) as error:
            raise SidecarFailure(
                422,
                "CHINADB_PRODUCTION_REQUEST_REJECTED",
                "ChinaDB production planning rejected the strict request or trust binding.",
            ) from error
        if not await _production_plan_gate.try_acquire():
            raise SidecarFailure(
                429,
                "CHINADB_PRODUCTION_CAPACITY_EXHAUSTED",
                "ChinaDB production planning has reached its bounded concurrency limit.",
                retryable=True,
            )
        try:
            result = await anyio.to_thread.run_sync(
                lambda: evaluate_production_qualification(
                    qualification_request,
                    trust_store=trust_store,
                ),
                abandon_on_cancel=False,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as error:
            raise SidecarFailure(
                422,
                "CHINADB_PRODUCTION_PLAN_REJECTED",
                "ChinaDB production planning failed closed and no external effect ran.",
            ) from error
        finally:
            await _production_plan_gate.release()
        _assert_production_qualification_result(result)
        return _json_response(_bounded_json_bytes(result, maximum=MAX_HTTP_RESPONSE_BYTES))
    except _ResponseLimitExceeded:
        return _error_response(
            SidecarFailure(
                413,
                "CHINADB_PRODUCTION_RESULT_TOO_LARGE",
                "ChinaDB production qualification result exceeds the bounded limit.",
            )
        )
    except SidecarFailure as failure:
        return _error_response(failure)


@app.post("/internal/v1/chinadb-skills/{skill_id}/execute")
async def execute_skill_endpoint(skill_id: str, request: Request) -> Response:
    try:
        if skill_id not in SKILLS_BY_ID:
            raise SidecarFailure(
                404,
                "CHINADB_SKILL_UNKNOWN",
                "The requested exact ChinaDB Skill identity is not registered.",
            )
        if not _content_type_is_json(request.headers.get("content-type")):
            raise SidecarFailure(
                415,
                "CHINADB_SKILL_JSON_REQUIRED",
                "ChinaDB Skill execution accepts only UTF-8 application/json.",
            )
        content_encoding = request.headers.get("content-encoding")
        if content_encoding not in {None, "", "identity"}:
            raise SidecarFailure(
                415,
                "CHINADB_SKILL_CONTENT_ENCODING_REJECTED",
                "ChinaDB Skill execution does not accept encoded request bodies.",
            )
        if request.headers.get("transfer-encoding") not in {None, ""}:
            raise SidecarFailure(
                400,
                "CHINADB_SKILL_TRANSFER_ENCODING_REJECTED",
                "ChinaDB Skill execution requires one bounded content-length body.",
            )
        declared_length = _declared_content_length(request.headers.get("content-length"))
        if declared_length > MAX_REQUEST_BYTES:
            raise SidecarFailure(
                413,
                "CHINADB_SKILL_REQUEST_TOO_LARGE",
                "ChinaDB Skill request exceeds the bounded input limit.",
            )
        raw_payload = await _read_request_body(request, declared_length)
        try:
            skill_request = parse_skill_request_json(raw_payload)
        except ValueError as error:
            raise SidecarFailure(
                422,
                "CHINADB_SKILL_REQUEST_REJECTED",
                "ChinaDB Skill request violates its strict bounded contract.",
            ) from error
        if not await _skill_gate.try_acquire():
            raise SidecarFailure(
                429,
                "CHINADB_SKILL_CAPACITY_EXHAUSTED",
                "ChinaDB Skill execution has reached its bounded concurrency limit.",
                retryable=True,
            )
        try:
            result = await anyio.to_thread.run_sync(
                lambda: execute_skill(skill_id, skill_request),
                abandon_on_cancel=False,
            )
        except (KeyError, RuntimeError, TypeError, ValueError) as error:
            raise SidecarFailure(
                422,
                "CHINADB_SKILL_EXECUTION_REJECTED",
                "ChinaDB Skill handler rejected the typed request and no external effect ran.",
            ) from error
        finally:
            await _skill_gate.release()
        _assert_fail_closed_skill_result(result)
        response = _bounded_json_bytes(result, maximum=MAX_HTTP_RESPONSE_BYTES)
        return _json_response(response)
    except _ResponseLimitExceeded:
        return _error_response(
            SidecarFailure(
                413,
                "CHINADB_SKILL_RESULT_TOO_LARGE",
                "ChinaDB Skill result exceeds the bounded response limit.",
            )
        )
    except SidecarFailure as failure:
        return _error_response(failure)


@app.post("/internal/v1/chinadb-sql/assess")
async def assess_endpoint(request: Request) -> Response:
    try:
        if not _content_type_is_json(request.headers.get("content-type")):
            raise SidecarFailure(
                415,
                "CHINADB_PREFLIGHT_JSON_REQUIRED",
                "ChinaDB SQL preflight accepts only UTF-8 application/json.",
            )
        content_encoding = request.headers.get("content-encoding")
        if content_encoding not in {None, "", "identity"}:
            raise SidecarFailure(
                415,
                "CHINADB_PREFLIGHT_CONTENT_ENCODING_REJECTED",
                "ChinaDB SQL preflight does not accept encoded request bodies.",
            )
        if request.headers.get("transfer-encoding") not in {None, ""}:
            raise SidecarFailure(
                400,
                "CHINADB_PREFLIGHT_TRANSFER_ENCODING_REJECTED",
                "ChinaDB SQL preflight requires one bounded content-length body.",
            )
        declared_length = _declared_content_length(request.headers.get("content-length"))
        payload = await _read_request_body(request, declared_length)
        try:
            assessment_request = parse_commercial_request_json(
                payload,
                limits=_HTTP_REQUEST_LIMITS,
            )
        except CommercialRequestError as error:
            status = 413 if error.code.endswith("TOO_LARGE") else 400
            raise SidecarFailure(
                status,
                error.code,
                "ChinaDB SQL preflight request violates its strict bounded contract.",
            ) from error

        current_snapshot = str(commercial_capabilities()["capabilitySnapshotDigest"])
        if assessment_request.capability_snapshot_digest != current_snapshot:
            raise SidecarFailure(
                409,
                "CHINADB_PREFLIGHT_CAPABILITY_SNAPSHOT_STALE",
                "ChinaDB SQL preflight capability snapshot is stale.",
            )

        if not await _assessment_gate.try_acquire():
            raise SidecarFailure(
                429,
                "CHINADB_PREFLIGHT_CAPACITY_EXHAUSTED",
                "ChinaDB SQL preflight has reached its bounded concurrency limit.",
                retryable=True,
            )
        try:
            result = await anyio.to_thread.run_sync(
                _run_assessment_isolated,
                assessment_request,
                abandon_on_cancel=False,
            )
        finally:
            await _assessment_gate.release()
        return _json_response(result)
    except SidecarFailure as failure:
        return _error_response(failure)


def _configured_port() -> int:
    raw = os.environ.get("ELMOS_CHINADB_PREFLIGHT_PORT", "8101")
    if not raw.isascii() or not raw.isdigit():
        raise RuntimeError("ELMOS_CHINADB_PREFLIGHT_PORT must be a numeric TCP port")
    port = int(raw)
    if port < 1024 or port > 65535:
        raise RuntimeError("ELMOS_CHINADB_PREFLIGHT_PORT is outside the allowed range")
    return port


def main() -> None:
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=_configured_port(),
        access_log=False,
        server_header=False,
        date_header=False,
        workers=1,
        limit_concurrency=16,
        timeout_keep_alive=5,
    )
