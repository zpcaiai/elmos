"""Framework-neutral API facade with stable error mapping."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .canonical import canonical_json
from .contracts import (
    MAX_RESPONSE_BYTES,
    SkillExecutionRequest,
    validate_execution_result_document,
)
from .errors import IntakeError, InternalError, ValidationError

Execute = Callable[[SkillExecutionRequest], Mapping[str, Any]]
_PUBLIC_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status_code: int
    body: Mapping[str, Any]
    headers: Mapping[str, str]


class MultimodalIntakeApi:
    """Strict API boundary; authentication is owned by the hosting adapter."""

    def __init__(self, execute: Execute, catalog: Callable[[], list[dict[str, Any]]]) -> None:
        self._execute = execute
        self._catalog = catalog

    def capabilities(self) -> ApiResponse:
        try:
            skills = self._catalog()
            if not isinstance(skills, list):
                raise InternalError("CAPABILITY_CATALOG_INVALID")
            body = {
                "schema_version": "1.0.0",
                "status": "CODE_IMPLEMENTED_LOCAL",
                "skill_count": len(skills),
                "skills": skills,
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
            if len(canonical_json(body).encode("utf-8")) > MAX_RESPONSE_BYTES:
                raise InternalError("MULTIMODAL_RESPONSE_TOO_LARGE")
            return ApiResponse(200, body, self._headers())
        except IntakeError as error:
            return self._error_response(error, None)
        except Exception:
            return self._internal_error(None)

    def execute(self, document: Mapping[str, Any]) -> ApiResponse:
        trace_id = document.get("trace_id") if isinstance(document, Mapping) else None
        try:
            request = SkillExecutionRequest.parse(document)
            try:
                raw_result = self._execute(request)
            except ValidationError as error:
                if error.code.startswith(("CANONICAL_JSON_", "RESULT_")):
                    raise InternalError("EXECUTION_RESULT_CONTRACT_INVALID") from error
                raise
            if not isinstance(raw_result, Mapping):
                raise InternalError("EXECUTION_RESULT_CONTRACT_INVALID")
            result = dict(raw_result)
            internal_status = result.pop("_http_status", 200)
            if (
                not isinstance(internal_status, int)
                or isinstance(internal_status, bool)
                or internal_status != 200 and not 400 <= internal_status <= 599
            ):
                raise InternalError("INTERNAL_HTTP_STATUS_INVALID")
            if internal_status != 200:
                code = result.get("code")
                return self._strict_error(
                    internal_status,
                    code if isinstance(code, str) else "MULTIMODAL_BOUNDARY_ERROR",
                    result.get("retryable") is True,
                    request.trace_id,
                )
            try:
                validated = validate_execution_result_document(result, expected_request=request)
            except ValidationError as error:
                raise InternalError("EXECUTION_RESULT_CONTRACT_INVALID") from error
            return ApiResponse(200, validated, self._headers())
        except IntakeError as error:
            return self._error_response(error, trace_id)
        except Exception:
            return self._internal_error(trace_id)

    def _error_response(self, error: IntakeError, trace_id: Any) -> ApiResponse:
        if isinstance(error, InternalError):
            # Internal failures raised deliberately by this boundary expose
            # only their stable, allowlisted machine code.  The exception
            # message, cause and host details remain private; unexpected
            # exceptions still use MULTIMODAL_INTERNAL_ERROR.
            return self._strict_error(500, error.code, error.retryable, trace_id)
        status_code = getattr(error, "http_status", 500)
        if (
            not isinstance(status_code, int)
            or isinstance(status_code, bool)
            or not 400 <= status_code <= 599
        ):
            return self._internal_error(trace_id)
        code = getattr(error, "code", "MULTIMODAL_BOUNDARY_ERROR")
        retryable = getattr(error, "retryable", False)
        return self._strict_error(
            status_code,
            code if isinstance(code, str) else "MULTIMODAL_BOUNDARY_ERROR",
            retryable if isinstance(retryable, bool) else False,
            trace_id,
        )

    def _internal_error(self, trace_id: Any) -> ApiResponse:
        return self._strict_error(500, "MULTIMODAL_INTERNAL_ERROR", True, trace_id)

    def _strict_error(
        self,
        status_code: int,
        code: str,
        retryable: bool,
        trace_id: Any,
    ) -> ApiResponse:
        if not _PUBLIC_ERROR_CODE.fullmatch(code):
            code = "MULTIMODAL_INTERNAL_ERROR" if status_code >= 500 else "MULTIMODAL_BOUNDARY_ERROR"
        body: dict[str, Any] = {
            "schema_version": "1.0.0",
            "status": "FAILED" if status_code >= 500 else "BLOCKED",
            "code": code,
            "retryable": retryable,
            "trace_id": "error-" + secrets.token_hex(16),
        }
        if isinstance(trace_id, str):
            try:
                encoded_trace = trace_id.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                encoded_trace = b""
            if encoded_trace and len(encoded_trace) <= 128 and not any(
                ord(character) < 32 or ord(character) == 127 for character in trace_id
            ):
                body["trace_id"] = trace_id
        return ApiResponse(status_code, body, self._headers())

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        }
