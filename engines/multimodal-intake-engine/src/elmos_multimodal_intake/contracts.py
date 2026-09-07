"""Strict public request/result contracts for the multimodal Skill runtime."""

from __future__ import annotations

import hmac
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import (
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    canonical_json,
    canonical_value,
    require_idempotency_key,
)
from .errors import ValidationError
from .models import TenantContext
from .operation_registry import require_operation, require_operation_pair

REQUEST_SCHEMA_VERSION = "1.0.0"
EXECUTION_CONTRACT_VERSION = "multimodal-intake-execution-v2"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_INPUT_DEPTH = 32
MAX_COLLECTION_ITEMS = 200_000
_SKILL = re.compile(r"^elmos-[a-z0-9]+(?:-[a-z0-9]+)*$")
_OPERATION = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RESULT_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")
_REQUEST_FIELDS = {
    "schema_version",
    "skill",
    "operation",
    "tenant_id",
    "project_id",
    "actor_id",
    "idempotency_key",
    "trace_id",
    "input",
}


def _bounded_json(
    value: Any,
    *,
    depth: int = 0,
    remaining: list[int] | None = None,
) -> int:
    """Validate one request tree against a single, shared node budget."""

    if remaining is None:
        remaining = [MAX_COLLECTION_ITEMS]
    remaining[0] -= 1
    if remaining[0] < 0:
        raise ValidationError("REQUEST_JSON_TOO_COMPLEX")
    if depth > MAX_INPUT_DEPTH:
        raise ValidationError("REQUEST_JSON_DEPTH_EXCEEDED")
    if isinstance(value, bool) or value is None:
        return 1
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ValidationError("REQUEST_JSON_INTEGER_UNSAFE")
        return 1
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("REQUEST_JSON_NON_FINITE")
        if value.is_integer() and abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ValidationError("REQUEST_JSON_INTEGER_UNSAFE")
        return 1
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("REQUEST_JSON_UNICODE_INVALID") from error
        return 1
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValidationError("REQUEST_COLLECTION_TOO_LARGE")
        return 1 + sum(
            _bounded_json(item, depth=depth + 1, remaining=remaining)
            for item in value
        )
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValidationError("REQUEST_COLLECTION_TOO_LARGE")
        count = 1
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValidationError("REQUEST_OBJECT_KEY_INVALID")
            try:
                encoded_key = key.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise ValidationError("REQUEST_JSON_UNICODE_INVALID") from error
            if len(encoded_key) > 256:
                raise ValidationError("REQUEST_OBJECT_KEY_INVALID")
            count += _bounded_json(item, depth=depth + 1, remaining=remaining)
        return count
    raise ValidationError("REQUEST_JSON_TYPE_INVALID")


def _required_text(value: Any, code: str, maximum: int) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(code)
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValidationError(code) from error
    if len(encoded) > maximum or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError(code)
    return value


@dataclass(frozen=True, slots=True)
class SkillExecutionRequest:
    schema_version: str
    skill: str
    operation: str
    context: TenantContext
    idempotency_key: str
    trace_id: str
    input: Mapping[str, Any]
    request_digest: str

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "SkillExecutionRequest":
        if not isinstance(value, Mapping):
            raise ValidationError("REQUEST_INVALID")
        if set(value) != _REQUEST_FIELDS:
            raise ValidationError("REQUEST_FIELDS_INVALID")
        _bounded_json(value)
        if value.get("schema_version") != REQUEST_SCHEMA_VERSION:
            raise ValidationError("REQUEST_SCHEMA_VERSION_UNSUPPORTED")
        skill = _required_text(value.get("skill"), "REQUEST_SKILL_INVALID", 96)
        if not _SKILL.fullmatch(skill):
            raise ValidationError("REQUEST_SKILL_INVALID")
        operation = _required_text(value.get("operation"), "REQUEST_OPERATION_INVALID", 64)
        if not _OPERATION.fullmatch(operation):
            raise ValidationError("REQUEST_OPERATION_INVALID")
        raw_idempotency_key = _required_text(
            value.get("idempotency_key"),
            "REQUEST_IDEMPOTENCY_KEY_INVALID",
            200,
        )
        try:
            idempotency_key = require_idempotency_key(raw_idempotency_key)
        except ValidationError as error:
            raise ValidationError("REQUEST_IDEMPOTENCY_KEY_INVALID") from error
        if idempotency_key != raw_idempotency_key or len(idempotency_key.encode("utf-8")) < 8:
            raise ValidationError("REQUEST_IDEMPOTENCY_KEY_INVALID")
        trace_id = _required_text(value.get("trace_id"), "REQUEST_TRACE_ID_INVALID", 128)
        payload = value.get("input")
        if not isinstance(payload, Mapping):
            raise ValidationError("REQUEST_INPUT_INVALID")
        normalized_payload = canonical_value(payload)
        if not isinstance(normalized_payload, dict):
            raise ValidationError("REQUEST_INPUT_INVALID")
        # Registry validation precedes authorization, receipt creation and
        # dispatch.  An unknown pair is an explicit adapter gap; an operation
        # can never smuggle unowned fields through the generic transport.
        require_operation(skill, operation, normalized_payload)
        tenant_id = _required_text(value.get("tenant_id"), "REQUEST_TENANT_ID_INVALID", 128)
        project_id = _required_text(value.get("project_id"), "REQUEST_PROJECT_ID_INVALID", 128)
        actor_id = _required_text(value.get("actor_id"), "REQUEST_ACTOR_ID_INVALID", 200)
        context = TenantContext(
            tenant_id,
            project_id,
            actor_id,
        )
        if context.tenant_id != tenant_id:
            raise ValidationError("REQUEST_TENANT_ID_INVALID")
        if context.project_id != project_id:
            raise ValidationError("REQUEST_PROJECT_ID_INVALID")
        if context.actor_id != actor_id:
            raise ValidationError("REQUEST_ACTOR_ID_INVALID")
        if len(canonical_json(dict(value)).encode("utf-8")) > MAX_REQUEST_BYTES:
            raise ValidationError("REQUEST_TOO_LARGE")
        normalized = {
            "execution_contract": EXECUTION_CONTRACT_VERSION,
            "schema_version": REQUEST_SCHEMA_VERSION,
            "skill": skill,
            "operation": operation,
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "actor_id": context.actor_id,
            "idempotency_key": idempotency_key,
            "input": normalized_payload,
        }
        return cls(
            REQUEST_SCHEMA_VERSION,
            skill,
            operation,
            context,
            idempotency_key,
            trace_id,
            normalized_payload,
            canonical_digest(normalized),
        )

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "skill": self.skill,
            "operation": self.operation,
            "tenant_id": self.context.tenant_id,
            "project_id": self.context.project_id,
            "actor_id": self.context.actor_id,
            "idempotency_key": self.idempotency_key,
            "trace_id": self.trace_id,
            "input": canonical_value(self.input),
        }

    def canonical_json(self) -> str:
        return canonical_json(self.document())


def execution_result(
    request: SkillExecutionRequest,
    *,
    status: str,
    output: Mapping[str, Any],
    code: str | None = None,
    retryable: bool = False,
    implementation_state: str = "CODE_IMPLEMENTED_LOCAL",
) -> dict[str, Any]:
    if status not in {"SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"}:
        raise ValidationError("RESULT_STATUS_INVALID")
    if implementation_state not in {"CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED"}:
        raise ValidationError("RESULT_IMPLEMENTATION_STATE_INVALID")
    if not isinstance(retryable, bool):
        raise ValidationError("RESULT_RETRYABLE_INVALID")
    if not isinstance(output, Mapping):
        raise ValidationError("RESULT_OUTPUT_INVALID")
    if status in {"BLOCKED", "FAILED"} and code is None:
        raise ValidationError("RESULT_CODE_REQUIRED")
    if code is not None and (not isinstance(code, str) or not _RESULT_CODE.fullmatch(code)):
        raise ValidationError("RESULT_CODE_INVALID")
    normalized_output = canonical_value(output)
    if not isinstance(normalized_output, dict):
        raise ValidationError("RESULT_OUTPUT_INVALID")
    result: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "skill": request.skill,
        "operation": request.operation,
        "status": status,
        "retryable": retryable,
        "trace_id": request.trace_id,
        "request_digest": request.request_digest,
        "implementation_state": implementation_state,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "output": normalized_output,
    }
    if code is not None:
        result["code"] = code
    result["result_digest"] = canonical_digest(result)
    return result


_RESULT_FIELDS = {
    "schema_version",
    "skill",
    "operation",
    "status",
    "retryable",
    "trace_id",
    "request_digest",
    "implementation_state",
    "external_evidence",
    "certification",
    "output",
    "code",
    "result_digest",
}
_RESULT_REQUIRED = _RESULT_FIELDS - {"code"}
_RESULT_STATES = {
    "SUCCEEDED",
    "PARTIAL",
    "BLOCKED",
    "FAILED",
    "NOT_APPLICABLE",
    "NOT_RUN_EXTERNAL",
}


def validate_execution_result_document(
    value: Mapping[str, Any],
    *,
    expected_request: SkillExecutionRequest | None = None,
) -> dict[str, Any]:
    """Validate the exact public result envelope and its content digest."""

    if not isinstance(value, Mapping):
        raise ValidationError("RESULT_CONTRACT_INVALID")
    try:
        normalized_value = canonical_value(value)
    except ValidationError as error:
        raise ValidationError("RESULT_CONTRACT_INVALID") from error
    if not isinstance(normalized_value, dict):
        raise ValidationError("RESULT_CONTRACT_INVALID")
    fields = set(normalized_value)
    if fields - _RESULT_FIELDS or not _RESULT_REQUIRED.issubset(fields):
        raise ValidationError("RESULT_CONTRACT_INVALID")
    _bounded_json(normalized_value)
    skill = normalized_value.get("skill")
    operation = normalized_value.get("operation")
    trace_id = normalized_value.get("trace_id")
    request_digest = normalized_value.get("request_digest")
    result_digest = normalized_value.get("result_digest")
    code = normalized_value.get("code")
    if (
        normalized_value.get("schema_version") != REQUEST_SCHEMA_VERSION
        or not isinstance(skill, str)
        or not _SKILL.fullmatch(skill)
        or not isinstance(operation, str)
        or not _OPERATION.fullmatch(operation)
        or normalized_value.get("status") not in _RESULT_STATES
        or not isinstance(normalized_value.get("retryable"), bool)
        or not isinstance(trace_id, str)
        or not trace_id
        or len(trace_id.encode("utf-8")) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in trace_id)
        or not isinstance(request_digest, str)
        or not _DIGEST.fullmatch(request_digest)
        or normalized_value.get("implementation_state") not in {"CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED"}
        or normalized_value.get("external_evidence") != "NOT_RUN"
        or normalized_value.get("certification") != "NOT_CERTIFIED"
        or not isinstance(normalized_value.get("output"), Mapping)
        or normalized_value.get("status") in {"BLOCKED", "FAILED"} and "code" not in normalized_value
        or ("code" in normalized_value and (not isinstance(code, str) or not _RESULT_CODE.fullmatch(code)))
        or not isinstance(result_digest, str)
        or not _DIGEST.fullmatch(result_digest)
    ):
        raise ValidationError("RESULT_CONTRACT_INVALID")
    require_operation_pair(skill, operation)
    if expected_request is not None and (
        skill != expected_request.skill
        or operation != expected_request.operation
        or trace_id != expected_request.trace_id
        or request_digest != expected_request.request_digest
    ):
        raise ValidationError("RESULT_REQUEST_BINDING_INVALID")
    unsigned = dict(normalized_value)
    unsigned.pop("result_digest")
    expected_digest = canonical_digest(unsigned)
    if not hmac.compare_digest(result_digest, expected_digest):
        raise ValidationError("RESULT_DIGEST_INVALID")
    normalized = dict(normalized_value)
    if len(canonical_json(normalized).encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValidationError("RESULT_TOO_LARGE")
    return normalized
