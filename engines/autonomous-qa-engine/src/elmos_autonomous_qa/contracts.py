"""Strict request and result contracts for the autonomous QA Skill runtime.

The source Skill archive is specification input.  Runtime callers therefore
cross this small, bounded JSON boundary before any repository-owned handler is
invoked.  Arbitrary Python objects, non-finite numbers, implicit commands, and
unscoped identities are rejected deterministically.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from .canonical import canonical_json_bytes as _canonical_json_bytes


class ContractError(ValueError):
    """Raised when a caller or trusted handler violates a runtime contract."""


class HandlerOutputError(ContractError):
    """Raised when repository-owned handler output is malformed."""


RESULT_STATES: Final = frozenset(
    {"SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN"}
)
REQUEST_FIELDS: Final = frozenset(
    {
        "schema_version",
        "request_id",
        "tenant_id",
        "project_id",
        "actor_id",
        "idempotency_key",
        "trace_id",
        "inputs",
        "policy",
        "capabilities",
    }
)
_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_DEPTH = 32
_MAX_NODES = 200_000
_MAX_BYTES = 16 * 1024 * 1024
_FORBIDDEN_TEXT_CATEGORIES = frozenset({"Cf", "Zl", "Zp"})


def _has_forbidden_text(value: str, *, multiline: bool) -> bool:
    for character in value:
        category = unicodedata.category(character)
        if category in _FORBIDDEN_TEXT_CATEGORIES:
            return True
        if category == "Cc" and not (
            multiline and character in {"\t", "\n"}
        ):
            return True
    return False


def canonical_json(value: Any) -> str:
    """Return the only serialization used for hashes and idempotency."""

    try:
        # Reuse the engine-wide portable JSON validator so request/result
        # digests cannot disagree about NFC text, safe integer range, negative
        # zero, duplicate path identities, or non-finite values.  The canonical
        # primitive terminates documents with a newline; the runtime's historic
        # ``sha256:`` digest contract hashes the same encoding without it.
        encoded = _canonical_json_bytes(value)
        return encoded[:-1].decode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not finite canonical JSON") from exc


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def require_text(value: Any, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-blank string")
    normalized = value.strip()
    try:
        encoded = normalized.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContractError(f"{field} contains invalid Unicode") from exc
    if len(encoded) > maximum or _has_forbidden_text(normalized, multiline=False):
        raise ContractError(f"{field} must be printable and at most {maximum} UTF-8 bytes")
    return normalized


def require_exact_text(value: Any, field: str, *, maximum: int) -> str:
    """Validate bounded multiline text without silently rewriting its bytes.

    Executable-looking material such as patches and generated test source is
    data at this boundary.  LF and horizontal TAB are permitted because they
    are required by common text formats; CR and every other C0/C1 control are
    rejected so the digest has one unambiguous representation.
    """

    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-blank string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ContractError(f"{field} contains invalid Unicode") from exc
    if len(encoded) > maximum:
        raise ContractError(f"{field} exceeds {maximum} UTF-8 bytes")
    if _has_forbidden_text(value, multiline=True):
        raise ContractError(f"{field} contains a forbidden control character")
    return value


def require_resource_id(value: Any, field: str) -> str:
    normalized = require_text(value, field, maximum=128)
    if not _RESOURCE_ID.fullmatch(normalized):
        raise ContractError(f"{field} has an invalid resource identifier")
    return normalized


def strict_json(value: Any, field: str, *, output: bool = False) -> Any:
    """Copy JSON values while enforcing bounded shape and exact key types."""

    error_type = HandlerOutputError if output else ContractError
    remaining = [_MAX_NODES]

    def visit(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise error_type(f"{field} exceeds the JSON node limit")
        if depth > _MAX_DEPTH:
            raise error_type(f"{field} exceeds the JSON depth limit")
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise error_type(f"{field} contains a non-finite number")
            return item
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise error_type(f"{field} contains invalid Unicode") from exc
            if _has_forbidden_text(item, multiline=True):
                raise error_type(f"{field} contains a forbidden Unicode control")
            return item
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, Mapping):
            copied: dict[str, Any] = {}
            for key, child in item.items():
                if type(key) is not str or not key:
                    raise error_type(f"{field} contains an invalid object key")
                try:
                    encoded_key = key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise error_type(f"{field} contains an invalid object key") from exc
                if len(encoded_key) > 256 or _has_forbidden_text(
                    key, multiline=False
                ):
                    raise error_type(f"{field} contains an invalid object key")
                copied[key] = visit(child, depth + 1)
            return copied
        raise error_type(f"{field} contains unsupported JSON type: {type(item).__name__}")

    copied = visit(value, 0)
    try:
        encoded = canonical_json(copied).encode("utf-8")
    except ContractError as exc:
        raise error_type(str(exc)) from exc
    if len(encoded) > _MAX_BYTES:
        raise error_type(f"{field} exceeds the JSON byte limit")
    return copied


@dataclass(frozen=True)
class RuntimeRequest:
    request_id: str
    tenant_id: str
    project_id: str
    actor_id: str | None
    idempotency_key: str | None
    trace_id: str
    inputs: Mapping[str, Any]
    policy: Mapping[str, Any]
    capabilities: Mapping[str, Any]

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "RuntimeRequest":
        if not isinstance(value, Mapping):
            raise ContractError("request must be an object")
        if any(not isinstance(key, str) for key in value):
            raise ContractError("request field names must be strings")
        unknown = set(value) - REQUEST_FIELDS
        if unknown:
            raise ContractError(f"request contains unsupported fields: {sorted(unknown)}")
        if value.get("schema_version") != "1.0":
            raise ContractError("schema_version must equal 1.0")
        inputs = value.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ContractError("inputs must be an object")
        policy = value.get("policy", {})
        capabilities = value.get("capabilities", {})
        if not isinstance(policy, Mapping) or not isinstance(capabilities, Mapping):
            raise ContractError("policy and capabilities must be objects")
        request_id = require_resource_id(value.get("request_id"), "request_id")
        tenant_id = require_resource_id(value.get("tenant_id"), "tenant_id")
        project_id = require_resource_id(value.get("project_id"), "project_id")
        raw_actor = value.get("actor_id")
        actor_id = require_resource_id(raw_actor, "actor_id") if raw_actor is not None else None
        raw_key = value.get("idempotency_key")
        idempotency_key = require_text(raw_key, "idempotency_key", maximum=200) if raw_key is not None else None
        raw_trace = value.get("trace_id")
        trace_id = (
            require_resource_id(raw_trace, "trace_id")
            if raw_trace is not None
            else "trace-" + digest_json({"tenant": tenant_id, "request": request_id})[7:31]
        )
        return cls(
            request_id=request_id,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            inputs=strict_json(inputs, "inputs"),
            policy=strict_json(policy, "policy"),
            capabilities=strict_json(capabilities, "capabilities"),
        )


def normalize_result(
    *,
    skill: str,
    source_id: str,
    handler_id: str,
    operation_id: str,
    phase: str,
    mutating: bool,
    request: RuntimeRequest,
    operation: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        normalized_skill = require_resource_id(skill, "result.skill")
        normalized_source_id = require_resource_id(source_id, "result.source_id")
        normalized_handler_id = require_resource_id(handler_id, "result.handler_id")
        normalized_phase = require_resource_id(phase, "result.phase")
        normalized_operation_id = require_text(
            operation_id, "result.operation_id", maximum=1024
        )
    except ContractError as exc:
        raise HandlerOutputError(str(exc)) from exc
    if not isinstance(mutating, bool):
        raise HandlerOutputError("result.mutating must be boolean")
    if not isinstance(operation, Mapping):
        raise HandlerOutputError("handler result must be an object")
    allowed_operation_fields = {
        "state",
        "code",
        "outputs",
        "metrics",
        "retryable",
        "implementation_state",
    }
    unknown_operation_fields = sorted(set(operation).difference(allowed_operation_fields))
    if unknown_operation_fields:
        raise HandlerOutputError(
            f"handler result has unsupported fields: {unknown_operation_fields}"
        )
    if "state" not in operation or "code" not in operation or "implementation_state" not in operation:
        raise HandlerOutputError(
            "handler result must explicitly declare state, code, and implementation_state"
        )
    raw_state = operation["state"]
    if not isinstance(raw_state, str) or raw_state.upper() not in RESULT_STATES:
        raise HandlerOutputError("handler result has an invalid state")
    state = raw_state.upper()
    raw_code = operation["code"]
    if not isinstance(raw_code, str) or not raw_code.strip():
        raise HandlerOutputError("handler result code must be a non-blank string")
    try:
        code = require_text(raw_code, "result.code")
    except ContractError as exc:
        raise HandlerOutputError(str(exc)) from exc
    outputs = operation.get("outputs", {})
    metrics = operation.get("metrics", {})
    if not isinstance(outputs, Mapping) or not isinstance(metrics, Mapping):
        raise HandlerOutputError("handler outputs and metrics must be objects")
    retryable = operation.get("retryable", False)
    if not isinstance(retryable, bool):
        raise HandlerOutputError("handler retryable must be boolean")
    implementation = operation["implementation_state"]
    if implementation not in {"LOCAL_EXECUTED", "LOCAL_VALIDATED", "EXTERNAL_ADAPTER_REQUIRED"}:
        raise HandlerOutputError("handler implementation_state is invalid")
    request_digest = digest_json(
        {
            "schema_version": "1.0",
            "request_id": request.request_id,
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "actor_id": request.actor_id,
            "idempotency_key": request.idempotency_key,
            "trace_id": request.trace_id,
            "inputs": request.inputs,
            "policy": request.policy,
            "capabilities": request.capabilities,
        }
    )
    result = {
        "schema_version": "1.0",
        "skill": normalized_skill,
        "source_id": normalized_source_id,
        "handler_id": normalized_handler_id,
        "operation_id": normalized_operation_id,
        "phase": normalized_phase,
        "mutating": mutating,
        "request_id": request.request_id,
        "trace_id": request.trace_id,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "request_digest": request_digest,
        "state": state,
        "code": code,
        "retryable": retryable,
        "outputs": strict_json(outputs, "handler outputs", output=True),
        "metrics": strict_json(metrics, "handler metrics", output=True),
        "implementation_state": implementation,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    result["result_digest"] = digest_json(result)
    return result
