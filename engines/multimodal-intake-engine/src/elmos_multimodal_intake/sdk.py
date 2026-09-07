"""Small synchronous Python SDK for the versioned HTTP contract."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence, TypeGuard
from urllib.parse import quote, urlsplit

from .canonical import MAX_SAFE_JSON_INTEGER, canonical_digest, canonical_json
from .contracts import (
    MAX_COLLECTION_ITEMS,
    MAX_INPUT_DEPTH,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    SkillExecutionRequest,
)
from .errors import IntakeError
from .operation_registry import OPERATION_REGISTRY_DIGEST, require_operation


class SdkError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        retryable: bool,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
        self.trace_id = trace_id


@dataclass(frozen=True, slots=True)
class EvaluationSubject:
    subject_id: str
    subject_kind: str
    artifact_digest: str
    implementation_version: str
    configuration_digest: str

    def document(self) -> dict[str, str]:
        return {
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "artifact_digest": self.artifact_digest,
            "implementation_version": self.implementation_version,
            "configuration_digest": self.configuration_digest,
        }


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    case_id: str
    media_type: str
    content_base64: str

    def document(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "media_type": self.media_type,
            "content_base64": self.content_base64,
        }


@dataclass(frozen=True, slots=True)
class ProjectPackageEntry:
    path: str
    kind: str = "file"
    byte_count: int = 0
    content_digest: str | None = None
    role: str = "PRIMARY"
    model_read_allowed: bool = True
    metadata: Mapping[str, Any] | None = None

    def document(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "path": self.path,
            "kind": self.kind,
            "byte_count": self.byte_count,
            "role": self.role,
            "model_read_allowed": self.model_read_allowed,
            "metadata": dict(self.metadata or {}),
        }
        if self.content_digest is not None:
            value["content_digest"] = self.content_digest
        return value


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SKILL = re.compile(r"^elmos-[a-z0-9]+(?:-[a-z0-9]+)*$")
_OPERATION = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_HANDLER = re.compile(r"^execute_[a-z0-9_]+$")
_PUBLIC_CODE = re.compile(r"^[A-Z][A-Z0-9_:-]{0,127}$")
_JSON_SUFFIX_MEDIA_TYPE = re.compile(r"^application/[a-z0-9!#$%&'*.^_`|~-]+\+json$")
_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ACTOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")
_PROGRESS_CURSOR = re.compile(r"^p1-([1-9][0-9]{0,15})-([0-9a-f]{64})$")
_CONTENT_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
CAPABILITIES_PATH = "/api/v1/multimodal-intake/capabilities"
EXECUTE_PATH = "/api/v1/multimodal-intake/execute"
PROGRESS_TASK_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/tasks/"
PROGRESS_JOB_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/jobs/"
PROGRESS_TASK_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/tasks/"
PROGRESS_JOB_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/jobs/"
SUPPORTED_PROGRESS_TRANSPORTS = ("sse",)
WEBSOCKET_PROGRESS_SUPPORTED = False
SDK_OPERATION_REGISTRY_DIGEST = OPERATION_REGISTRY_DIGEST
MAX_PROGRESS_DOCUMENTS = 64
HUMAN_REVIEW_SKILL = "elmos-human-review-and-correction"
HUMAN_REVIEW_SOURCE_LIST_OPERATION = "source_list"
HUMAN_REVIEW_SOURCE_GET_OPERATION = "source_get"
HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION = "enqueue"
HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION = "enqueue_prepare"
HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION = "enqueue_execute"
HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT = "sha256:rfc8785-ijson-safeint-v1"
HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS = 200
HUMAN_REVIEW_SOURCE_COLLECTION_MAX_ITEMS = 1_000
HUMAN_REVIEW_SOURCE_REF_V2_FIELDS = frozenset(
    {
        "schema_version", "content_id", "content_version", "content_digest",
        "asset_sha256", "target_kind", "target_digest", "snapshot_id",
        "snapshot_digest", "head_version", "head_value_digest", "source_digest",
        "provenance_digest", "original_value_client_digest",
        "original_value_digest_contract",
    }
)
HUMAN_REVIEW_SOURCE_SUMMARY_FIELDS = frozenset(
    {
        "schema_version", "content_id", "content_version", "target_kind", "target",
        "target_digest", "confidence", "head_version", "head_direction",
        "head_correction_version", "original_value_client_digest",
        "original_value_digest_contract", "source_ref",
    }
)
HUMAN_REVIEW_SOURCE_DETAIL_FIELDS = (
    HUMAN_REVIEW_SOURCE_SUMMARY_FIELDS | {"original_value"}
)
HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_FIELDS = frozenset(
    {
        "content_id", "expected_asset_version", "target_kind", "target_digest",
        "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
        "expected_head_value_digest", "original_value_digest", "reason",
    }
)
HUMAN_REVIEW_ENQUEUE_PREPARE_FIELDS = (
    HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_FIELDS
    | {"recovery_handle", "execute_idempotency_key"}
)
HUMAN_REVIEW_ENQUEUE_EXECUTE_FIELDS = frozenset({"recovery_handle"})
HUMAN_REVIEW_ENQUEUE_PREPARATION_FIELDS = frozenset(
    {
        "schema_version", "recovery_handle", "request_digest", "state",
        "safe_to_clear", "expires_at", "prepared_at", "executed_at", "task_id",
        "enqueue_input",
    }
)
HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENCE_FIELDS = frozenset(
    {"schema_version", "recovery_handle", "state", "safe_to_clear"}
)
_HUMAN_REVIEW_TARGET_KINDS = frozenset(
    {"TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT"}
)
_HUMAN_REVIEW_HEAD_DIRECTIONS = frozenset({"SNAPSHOT", "APPLY", "REVERT"})
_HUMAN_REVIEW_TASK_STATES = frozenset(
    {
        "QUEUED", "CLAIMED", "EDITED", "APPROVED", "REJECTED", "REOPENED",
        "REVERTING", "REVERTED",
    }
)
_HUMAN_REVIEW_TASK_FIELDS = frozenset(
    {
        "task_id", "tenant_id", "project_id", "asset_id", "target_kind", "target",
        "original_value", "source_digest", "source_ref", "confidence", "reason", "state",
        "current_correction_version", "current_correction_digest", "effective_version",
        "effective_digest", "claim_actor_id", "claim_fence", "claim_expires_at", "version",
        "created_by", "created_at", "updated_at", "closed_at",
    }
)
_TASK_STATES = frozenset(
    {"PENDING", "RUNNING", "PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"}
)
_TASK_TRANSITIONS = {
    "PENDING": frozenset({"RUNNING", "CANCELLED"}),
    "RUNNING": frozenset({"PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"}),
    "PAUSED": frozenset({"RUNNING", "CANCELLED"}),
    "FAILED_RETRYABLE": frozenset({"RUNNING", "FAILED_FINAL", "CANCELLED"}),
    "SUCCEEDED": frozenset(),
    "FAILED_FINAL": frozenset(),
    "CANCELLED": frozenset(),
}
_JOB_STATES = frozenset(
    {"QUEUED", "RUNNING", "COMPLETED", "PARTIAL", "NEEDS_REVIEW", "BLOCKED", "FAILED", "CANCELLED"}
)
_RESULT_STATUSES = frozenset({"PASSED", "PARTIAL", "NEEDS_REVIEW", "NOT_RUN", "BLOCKED", "FAILED"})
_RESULT_FIELDS = frozenset(
    {
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
)
_RESULT_REQUIRED = _RESULT_FIELDS - {"code"}
_RESULT_STATES = frozenset(
    {"SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"}
)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward the bearer token to a redirect-selected origin."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoRedirectHandler(),
)


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _safe_json_int(value: str) -> int:
    parsed = int(value)
    if abs(parsed) > MAX_SAFE_JSON_INTEGER:
        raise ValueError("JSON integer exceeds the interoperable safe range")
    return parsed


def _safe_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number is not finite")
    if parsed.is_integer() and abs(parsed) > MAX_SAFE_JSON_INTEGER:
        raise ValueError("JSON integer exceeds the interoperable safe range")
    return parsed


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _validate_json_tree(
    value: Any,
    *,
    depth: int = 0,
    remaining: list[int] | None = None,
) -> None:
    if remaining is None:
        remaining = [MAX_COLLECTION_ITEMS]
    remaining[0] -= 1
    if remaining[0] < 0 or depth > MAX_INPUT_DEPTH:
        raise ValueError("JSON tree exceeds the SDK complexity limit")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ValueError("JSON integer exceeds the interoperable safe range")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON number is not finite")
        if value.is_integer() and abs(value) > MAX_SAFE_JSON_INTEGER:
            raise ValueError("JSON integer exceeds the interoperable safe range")
        return
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("JSON array exceeds the SDK complexity limit")
        for item in value:
            _validate_json_tree(item, depth=depth + 1, remaining=remaining)
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError("JSON object exceeds the SDK complexity limit")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key.encode("utf-8", errors="strict")) > 256:
                raise ValueError("JSON object key is invalid")
            _validate_json_tree(item, depth=depth + 1, remaining=remaining)
        return
    raise ValueError("value is not JSON compatible")


def _strict_json_loads(
    payload: bytes,
    *,
    invalid_code: str,
    canonical_code: str | None = None,
) -> Any:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            parse_constant=_reject_non_finite,
            parse_int=_safe_json_int,
            parse_float=_safe_json_float,
            object_pairs_hook=_unique_json_object,
        )
        _validate_json_tree(value)
        if canonical_code is not None and canonical_json(value).encode("utf-8") != payload:
            raise SdkError(502, canonical_code, False)
        return value
    except SdkError:
        raise
    except (UnicodeDecodeError, UnicodeEncodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise SdkError(502, invalid_code, False) from error


def _valid_bounded_text(value: Any, maximum: int) -> TypeGuard[str]:
    if not isinstance(value, str) or not value:
        return False
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return len(encoded) <= maximum and not any(
        ord(character) < 32 or ord(character) == 127 for character in value
    )


def _sdk_safe_version(value: Any, *, allow_zero: bool = False) -> TypeGuard[int]:
    minimum = 0 if allow_zero else 1
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= MAX_SAFE_JSON_INTEGER - 1
    )


def _sdk_timestamp(value: Any, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None and parsed.isoformat() == value


def _sdk_content_digest(value: Any) -> bool:
    return isinstance(value, str) and _CONTENT_DIGEST.fullmatch(value) is not None


def _validate_human_review_source_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != HUMAN_REVIEW_SOURCE_REF_V2_FIELDS:
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_REF_INVALID", False)
    digest_fields = {
        "content_digest", "asset_sha256", "target_digest", "snapshot_digest",
        "head_value_digest", "source_digest", "provenance_digest",
        "original_value_client_digest",
    }
    if (
        value.get("schema_version") != "human-review-source-ref-v2"
        or not isinstance(value.get("content_id"), str)
        or _RESOURCE_ID.fullmatch(value["content_id"]) is None
        or not _sdk_safe_version(value.get("content_version"))
        or value.get("target_kind") not in _HUMAN_REVIEW_TARGET_KINDS
        or not isinstance(value.get("snapshot_id"), str)
        or _RESOURCE_ID.fullmatch(value["snapshot_id"]) is None
        or not _sdk_safe_version(value.get("head_version"))
        or value.get("original_value_digest_contract")
        != HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT
        or any(not _sdk_content_digest(value.get(field)) for field in digest_fields)
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_REF_INVALID", False)
    return dict(value)


def _validate_human_review_source(
    value: Any,
    *,
    detail: bool,
    expected_input: Mapping[str, Any],
) -> dict[str, Any]:
    expected_fields = (
        HUMAN_REVIEW_SOURCE_DETAIL_FIELDS if detail else HUMAN_REVIEW_SOURCE_SUMMARY_FIELDS
    )
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID", False)
    source_ref = _validate_human_review_source_ref(value.get("source_ref"))
    confidence = value.get("confidence")
    if (
        value.get("schema_version")
        != ("human-review-source-detail-v1" if detail else "human-review-source-summary-v1")
        or value.get("content_id") != expected_input.get("content_id")
        or value.get("content_version") != expected_input.get("expected_asset_version")
        or value.get("target_kind") not in _HUMAN_REVIEW_TARGET_KINDS
        or not isinstance(value.get("target"), Mapping)
        or not _sdk_content_digest(value.get("target_digest"))
        or not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(float(confidence))
        or not 0 <= float(confidence) <= 1
        or not _sdk_safe_version(value.get("head_version"))
        or value.get("head_direction") not in _HUMAN_REVIEW_HEAD_DIRECTIONS
        or not _sdk_safe_version(value.get("head_correction_version"), allow_zero=True)
        or not _sdk_content_digest(value.get("original_value_client_digest"))
        or value.get("original_value_digest_contract")
        != HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT
        or source_ref["content_id"] != value.get("content_id")
        or source_ref["content_version"] != value.get("content_version")
        or source_ref["target_kind"] != value.get("target_kind")
        or source_ref["target_digest"] != value.get("target_digest")
        or source_ref["head_version"] != value.get("head_version")
        or source_ref["original_value_client_digest"]
        != value.get("original_value_client_digest")
        or source_ref["original_value_digest_contract"]
        != value.get("original_value_digest_contract")
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID", False)
    if detail:
        try:
            observed_digest = canonical_digest(value.get("original_value"))
        except IntakeError as error:
            raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID", False) from error
        if not hmac.compare_digest(
            f"sha256:{observed_digest}", str(value.get("original_value_client_digest"))
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_DIGEST_INVALID", False)
    return dict(value)


def _decode_human_review_source_cursor(
    value: Any, *, expected: SkillExecutionRequest
) -> dict[str, Any]:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 4_096
        or "=" in value
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID", False)
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        decoded = _strict_json_loads(
            raw,
            invalid_code="SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID",
            canonical_code="SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID",
        )
    except (ValueError, SdkError) as error:
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID", False) from error
    if (
        base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value
        or not isinstance(decoded, Mapping)
        or set(decoded)
        != {
            "version", "filter_digest", "collection_digest", "collection_generation",
            "target_kind", "target_digest",
        }
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID", False)
    kinds = expected.input.get("kinds")
    if (
        not isinstance(kinds, list)
        or any(kind not in _HUMAN_REVIEW_TARGET_KINDS for kind in kinds)
        or kinds != sorted(set(kinds))
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID", False)
    filter_digest = canonical_digest(
        {
            "schema_version": "human-review-source-filter-v1",
            "tenant_id": expected.context.tenant_id,
            "project_id": expected.context.project_id,
            "content_id": expected.input.get("content_id"),
            "content_version": expected.input.get("expected_asset_version"),
            "kinds": kinds,
        }
    )
    if (
        decoded.get("version") != "human-review-source-cursor-v1"
        or not isinstance(decoded.get("filter_digest"), str)
        or _DIGEST.fullmatch(decoded["filter_digest"]) is None
        or not hmac.compare_digest(decoded["filter_digest"], filter_digest)
        or not isinstance(decoded.get("collection_digest"), str)
        or _DIGEST.fullmatch(decoded["collection_digest"]) is None
        or not _sdk_safe_version(decoded.get("collection_generation"))
        or decoded.get("target_kind") not in _HUMAN_REVIEW_TARGET_KINDS
        or not _sdk_content_digest(decoded.get("target_digest"))
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID", False)
    return dict(decoded)


def _validate_human_review_task(
    value: Any,
    *,
    expected: SkillExecutionRequest,
    expected_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _HUMAN_REVIEW_TASK_FIELDS:
        raise SdkError(502, "SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID", False)
    source_ref = _validate_human_review_source_ref(value.get("source_ref"))
    binding = expected.input if expected_input is None else expected_input
    confidence = value.get("confidence")
    nullable_digests = ("current_correction_digest", "effective_digest")
    if (
        not isinstance(value.get("task_id"), str)
        or _RESOURCE_ID.fullmatch(value["task_id"]) is None
        or value.get("tenant_id") != expected.context.tenant_id
        or value.get("project_id") != expected.context.project_id
        or value.get("asset_id") != binding.get("content_id")
        or value.get("target_kind") != binding.get("target_kind")
        or not isinstance(value.get("target"), Mapping)
        or not _sdk_content_digest(value.get("source_digest"))
        or value.get("source_digest") != source_ref["source_digest"]
        or source_ref["content_id"] != value.get("asset_id")
        or source_ref["content_version"] != binding.get("expected_asset_version")
        or source_ref["target_kind"] != value.get("target_kind")
        or source_ref["target_digest"] != binding.get("target_digest")
        or source_ref["snapshot_id"] != binding.get("expected_snapshot_id")
        or source_ref["snapshot_digest"] != binding.get("expected_snapshot_digest")
        or source_ref["head_version"] != binding.get("expected_head_version")
        or source_ref["head_value_digest"] != binding.get("expected_head_value_digest")
        or source_ref["original_value_client_digest"]
        != binding.get("original_value_digest")
        or not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(float(confidence))
        or not 0 <= float(confidence) <= 1
        or not _valid_bounded_text(value.get("reason"), 2_000)
        or value.get("reason") != binding.get("reason")
        or value.get("state") not in _HUMAN_REVIEW_TASK_STATES
        or not _sdk_safe_version(value.get("current_correction_version"), allow_zero=True)
        or not _sdk_safe_version(value.get("effective_version"), allow_zero=True)
        or any(
            value.get(field) is not None and not _sdk_content_digest(value.get(field))
            for field in nullable_digests
        )
        or value.get("claim_actor_id") is not None
        and not _valid_bounded_text(value.get("claim_actor_id"), 200)
        or not _sdk_safe_version(value.get("claim_fence"), allow_zero=True)
        or not _sdk_timestamp(value.get("claim_expires_at"), nullable=True)
        or not _sdk_safe_version(value.get("version"))
        or value.get("created_by") != expected.context.actor_id
        or not _sdk_timestamp(value.get("created_at"))
        or not _sdk_timestamp(value.get("updated_at"))
        or not _sdk_timestamp(value.get("closed_at"), nullable=True)
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID", False)
    try:
        original_digest = canonical_digest(value.get("original_value"))
    except IntakeError as error:
        raise SdkError(502, "SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID", False) from error
    if f"sha256:{original_digest}" != source_ref["original_value_client_digest"]:
        raise SdkError(502, "SDK_HUMAN_REVIEW_TASK_DIGEST_INVALID", False)
    return dict(value)


def _validate_human_review_enqueue_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_FIELDS:
        raise SdkError(502, "SDK_HUMAN_REVIEW_ENQUEUE_INPUT_INVALID", False)
    if (
        not isinstance(value.get("content_id"), str)
        or _RESOURCE_ID.fullmatch(value["content_id"]) is None
        or not _sdk_safe_version(value.get("expected_asset_version"))
        or value.get("target_kind") not in _HUMAN_REVIEW_TARGET_KINDS
        or not _sdk_content_digest(value.get("target_digest"))
        or not _sdk_safe_version(value.get("expected_head_version"))
        or not isinstance(value.get("expected_snapshot_id"), str)
        or _RESOURCE_ID.fullmatch(value["expected_snapshot_id"]) is None
        or not _sdk_content_digest(value.get("expected_snapshot_digest"))
        or not _sdk_content_digest(value.get("expected_head_value_digest"))
        or not _sdk_content_digest(value.get("original_value_digest"))
        or not _valid_bounded_text(value.get("reason"), 2_000)
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_ENQUEUE_INPUT_INVALID", False)
    return dict(value)


def _validate_human_review_preparation(
    value: Any,
    *,
    expected: SkillExecutionRequest,
    allowed_states: frozenset[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != HUMAN_REVIEW_ENQUEUE_PREPARATION_FIELDS:
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False)
    enqueue_input = value.get("enqueue_input")
    state = value.get("state")
    if (
        value.get("schema_version") != "human-review-enqueue-preparation-v1"
        or value.get("recovery_handle") != expected.input.get("recovery_handle")
        or not isinstance(value.get("recovery_handle"), str)
        or not 32 <= len(value["recovery_handle"].encode("utf-8")) <= 200
        or not _sdk_content_digest(value.get("request_digest"))
        or state not in allowed_states
        or not isinstance(value.get("safe_to_clear"), bool)
        or not _sdk_timestamp(value.get("expires_at"))
        or not _sdk_timestamp(value.get("prepared_at"))
        or not _sdk_timestamp(value.get("executed_at"), nullable=True)
        or value.get("task_id") is not None
        and (
            not isinstance(value.get("task_id"), str)
            or _RESOURCE_ID.fullmatch(value["task_id"]) is None
        )
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False)
    enqueue_input = _validate_human_review_enqueue_input(enqueue_input)
    if (
        expected.operation.replace("-", "_") == HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION
        and any(expected.input.get(field) != enqueue_input[field] for field in enqueue_input)
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_BINDING_INVALID", False)
    try:
        input_digest = canonical_digest(enqueue_input)
    except IntakeError as error:
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False) from error
    if not hmac.compare_digest(
        f"sha256:{input_digest}", str(value.get("request_digest"))
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_DIGEST_INVALID", False)
    if state == "PREPARED" and (
        value["safe_to_clear"] or value["executed_at"] is not None or value["task_id"] is not None
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False)
    if state == "EXECUTED" and (
        not value["safe_to_clear"] or value["executed_at"] is None or value["task_id"] is None
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False)
    if state == "EXPIRED" and (
        not value["safe_to_clear"] or value["executed_at"] is not None or value["task_id"] is not None
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False)
    return dict(value), dict(enqueue_input)


def _validate_human_review_preparation_absence(
    value: Any, *, expected: SkillExecutionRequest
) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENCE_FIELDS
        or value.get("schema_version")
        != "human-review-enqueue-preparation-absence-v1"
        or value.get("recovery_handle") != expected.input.get("recovery_handle")
        or value.get("state") != "ABSENT"
        or value.get("safe_to_clear") is not True
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID", False)
    return dict(value)


def _validate_human_review_execution_output(
    output: Mapping[str, Any], expected: SkillExecutionRequest, result_code: Any
) -> None:
    metadata = {"handler_id", "phase", "metrics"}
    if (
        output.get("handler_id") != "execute_human_review_and_correction"
        or output.get("phase") != "review"
        or output.get("metrics") != {}
    ):
        raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
    expected_input = expected.input
    operation = expected.operation.replace("-", "_")
    if operation == HUMAN_REVIEW_SOURCE_LIST_OPERATION:
        if result_code != "HUMAN_REVIEW_SOURCES_LISTED":
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID", False)
        if (
            set(expected_input)
            != {"content_id", "expected_asset_version", "kinds", "limit", "cursor"}
            or set(output) != metadata | {"sources", "next_cursor", "total"}
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        sources = output.get("sources")
        total = output.get("total")
        next_cursor = output.get("next_cursor")
        limit = expected_input.get("limit")
        input_cursor = expected_input.get("cursor")
        if (
            not isinstance(sources, list)
            or not isinstance(expected_input.get("content_id"), str)
            or _RESOURCE_ID.fullmatch(expected_input["content_id"]) is None
            or not _sdk_safe_version(expected_input.get("expected_asset_version"))
            or not isinstance(expected_input.get("kinds"), list)
            or any(
                kind not in _HUMAN_REVIEW_TARGET_KINDS
                for kind in expected_input["kinds"]
            )
            or expected_input["kinds"] != sorted(set(expected_input["kinds"]))
            or not _sdk_safe_version(total, allow_zero=True)
            or total > HUMAN_REVIEW_SOURCE_COLLECTION_MAX_ITEMS
            or total < len(sources)
            or not _sdk_safe_version(limit)
            or limit > HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS
            or len(sources) > min(limit, HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS)
            or input_cursor is not None and not isinstance(input_cursor, str)
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        prior_cursor = (
            _decode_human_review_source_cursor(input_cursor, expected=expected)
            if input_cursor is not None
            else None
        )
        validated_sources = [
            _validate_human_review_source(
                source, detail=False, expected_input=expected_input
            )
            for source in sources
        ]
        pairs = [
            (str(source["target_kind"]), str(source["target_digest"]))
            for source in validated_sources
        ]
        kinds = expected_input.get("kinds")
        if (
            pairs != sorted(set(pairs))
            or isinstance(kinds, list)
            and kinds
            and any(source["target_kind"] not in kinds for source in validated_sources)
            or prior_cursor is not None
            and pairs
            and pairs[0]
            <= (prior_cursor["target_kind"], prior_cursor["target_digest"])
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        if next_cursor is None:
            if (
                input_cursor is None and total != len(sources)
                or input_cursor is not None and total <= len(sources)
            ):
                raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        else:
            next_document = _decode_human_review_source_cursor(
                next_cursor, expected=expected
            )
            if (
                len(sources) != limit
                or total <= len(sources)
                or not pairs
                or (
                    next_document["target_kind"], next_document["target_digest"]
                ) != pairs[-1]
                or prior_cursor is not None
                and (
                    next_document["collection_digest"]
                    != prior_cursor["collection_digest"]
                    or next_document["collection_generation"]
                    != prior_cursor["collection_generation"]
                )
            ):
                raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        return
    if operation == HUMAN_REVIEW_SOURCE_GET_OPERATION:
        if result_code != "HUMAN_REVIEW_SOURCE_RETRIEVED":
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID", False)
        if (
            set(expected_input)
            != {
                "content_id", "expected_asset_version", "target_kind",
                "target_digest", "expected_head_version",
            }
            or set(output) != metadata | {"source"}
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        source = _validate_human_review_source(
            output.get("source"), detail=True, expected_input=expected_input
        )
        if (
            source["target_kind"] != expected_input.get("target_kind")
            or source["target_digest"] != expected_input.get("target_digest")
            or source["head_version"] != expected_input.get("expected_head_version")
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_SOURCE_BINDING_INVALID", False)
        return
    if operation == HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION:
        if result_code != "HUMAN_REVIEW_TASK_ENQUEUED":
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID", False)
        if set(output) != metadata | {"task"}:
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        _validate_human_review_enqueue_input(expected_input)
        _validate_human_review_task(output.get("task"), expected=expected)
        return
    if operation == HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION:
        if (
            result_code != "HUMAN_REVIEW_ENQUEUE_PREPARED"
            or set(expected_input) != HUMAN_REVIEW_ENQUEUE_PREPARE_FIELDS
            or not _valid_bounded_text(
                expected_input.get("execute_idempotency_key"), 200
            )
            or len(expected_input["execute_idempotency_key"].encode("utf-8")) < 8
            or set(output) != metadata | {"preparation"}
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        _validate_human_review_preparation(
            output.get("preparation"),
            expected=expected,
            allowed_states=frozenset({"PREPARED"}),
        )
        return
    if operation == HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION:
        recovery_handle = expected_input.get("recovery_handle")
        if (
            set(expected_input) != HUMAN_REVIEW_ENQUEUE_EXECUTE_FIELDS
            or not _valid_bounded_text(recovery_handle, 200)
            or len(recovery_handle.encode("utf-8")) < 32
        ):
            raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
        preparation_value = output.get("preparation")
        if result_code == "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT":
            if set(output) != metadata | {"preparation"}:
                raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
            _validate_human_review_preparation_absence(
                preparation_value, expected=expected
            )
            return
        if result_code == "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED":
            if set(output) != metadata | {"preparation"}:
                raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
            _validate_human_review_preparation(
                preparation_value,
                expected=expected,
                allowed_states=frozenset({"EXPIRED"}),
            )
            return
        if result_code == "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION":
            if set(output) != metadata | {"preparation", "task"}:
                raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID", False)
            preparation, enqueue_input = _validate_human_review_preparation(
                preparation_value,
                expected=expected,
                allowed_states=frozenset({"EXECUTED"}),
            )
            task = _validate_human_review_task(
                output.get("task"), expected=expected, expected_input=enqueue_input
            )
            if preparation["task_id"] != task["task_id"]:
                raise SdkError(502, "SDK_HUMAN_REVIEW_PREPARATION_BINDING_INVALID", False)
            return
        raise SdkError(502, "SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID", False)


def _is_json_media_type(value: str) -> bool:
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or _JSON_SUFFIX_MEDIA_TYPE.fullmatch(media_type) is not None


def validate_execution_result(
    value: Mapping[str, Any],
    *,
    expected_request: SkillExecutionRequest | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SdkError(502, "SDK_RESPONSE_CONTRACT_INVALID", False)
    try:
        _validate_json_tree(value)
    except (UnicodeEncodeError, ValueError) as error:
        raise SdkError(502, "SDK_RESPONSE_CONTRACT_INVALID", False) from error
    fields = set(value)
    if fields - _RESULT_FIELDS or not _RESULT_REQUIRED.issubset(fields):
        raise SdkError(502, "SDK_RESPONSE_CONTRACT_INVALID", False)
    if (
        value.get("schema_version") != "1.0.0"
        or not isinstance(value.get("skill"), str)
        or not _SKILL.fullmatch(value["skill"])
        or not isinstance(value.get("operation"), str)
        or not _OPERATION.fullmatch(value["operation"])
        or value.get("status") not in _RESULT_STATES
        or not isinstance(value.get("retryable"), bool)
        or not _valid_bounded_text(value.get("trace_id"), 128)
        or not isinstance(value.get("request_digest"), str)
        or not _DIGEST.fullmatch(value["request_digest"])
        or value.get("implementation_state") not in {"CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED"}
        or value.get("external_evidence") != "NOT_RUN"
        or value.get("certification") != "NOT_CERTIFIED"
        or not isinstance(value.get("output"), dict)
        or value.get("status") in {"BLOCKED", "FAILED"} and "code" not in value
        or "code" in value
        and (not isinstance(value.get("code"), str) or not _PUBLIC_CODE.fullmatch(value["code"]))
        or not isinstance(value.get("result_digest"), str)
        or not _DIGEST.fullmatch(value["result_digest"])
    ):
        raise SdkError(502, "SDK_RESPONSE_CONTRACT_INVALID", False)
    supplied = value["result_digest"]
    unsigned = dict(value)
    unsigned.pop("result_digest")
    try:
        expected = canonical_digest(unsigned)
    except IntakeError as error:
        raise SdkError(502, "SDK_RESPONSE_CONTRACT_INVALID", False) from error
    if not hmac.compare_digest(supplied, expected):
        raise SdkError(502, "SDK_RESPONSE_DIGEST_INVALID", False)
    if expected_request is not None and (
        value.get("skill") != expected_request.skill
        or value.get("operation") != expected_request.operation
        or value.get("trace_id") != expected_request.trace_id
        or value.get("request_digest") != expected_request.request_digest
    ):
        raise SdkError(502, "SDK_RESPONSE_REQUEST_BINDING_INVALID", False)
    if (
        expected_request is not None
        and expected_request.skill == "elmos-multimodal-input-orchestrator"
        and expected_request.operation.replace("-", "_") == "bootstrap_project"
        and value.get("status") == "SUCCEEDED"
        and value["output"].get("project_id") != expected_request.context.project_id
    ):
        raise SdkError(502, "SDK_RESPONSE_PROJECT_BINDING_INVALID", False)
    if (
        expected_request is not None
        and expected_request.skill == HUMAN_REVIEW_SKILL
        and value.get("status") == "SUCCEEDED"
        and expected_request.operation.replace("-", "_")
        in {
            HUMAN_REVIEW_SOURCE_LIST_OPERATION,
            HUMAN_REVIEW_SOURCE_GET_OPERATION,
            HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION,
            HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION,
            HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION,
        }
    ):
        _validate_human_review_execution_output(
            value["output"], expected_request, value.get("code")
        )
    try:
        if len(canonical_json(value).encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
    except (TypeError, ValueError, UnicodeEncodeError, IntakeError) as error:
        raise SdkError(502, "SDK_RESPONSE_CONTRACT_INVALID", False) from error
    return dict(value)


def validate_error_response(value: Mapping[str, Any], status_code: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SdkError(502, "SDK_ERROR_RESPONSE_CONTRACT_INVALID", False)
    try:
        _validate_json_tree(value)
    except (UnicodeEncodeError, ValueError) as error:
        raise SdkError(502, "SDK_ERROR_RESPONSE_CONTRACT_INVALID", False) from error
    required = {"schema_version", "status", "code", "retryable", "trace_id"}
    if (
        set(value) != required
        or not required.issubset(value)
        or not isinstance(status_code, int)
        or isinstance(status_code, bool)
        or not 400 <= status_code <= 599
        or value.get("schema_version") != "1.0.0"
        or value.get("status") != ("FAILED" if status_code >= 500 else "BLOCKED")
        or not isinstance(value.get("code"), str)
        or not _PUBLIC_CODE.fullmatch(value["code"])
        or not isinstance(value.get("retryable"), bool)
        or not _valid_bounded_text(value.get("trace_id"), 128)
    ):
        raise SdkError(502, "SDK_ERROR_RESPONSE_CONTRACT_INVALID", False)
    return dict(value)


def validate_capability_response(value: Mapping[str, Any]) -> dict[str, Any]:
    # Import lazily so basic SDK configuration remains lightweight while an
    # advertised catalog is still checked against the exact local 50-Skill ABI.
    from .skill_runtime import SKILL_REGISTRY

    if not isinstance(value, Mapping):
        raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False)
    try:
        _validate_json_tree(value)
    except (UnicodeEncodeError, ValueError) as error:
        raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False) from error
    if set(value) != {
        "schema_version", "status", "skill_count", "skills", "external_evidence", "certification"
    }:
        raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False)
    skills = value.get("skills")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("status") != "CODE_IMPLEMENTED_LOCAL"
        or value.get("skill_count") != 50
        or not isinstance(skills, list)
        or len(skills) != 50
        or value.get("external_evidence") != "NOT_RUN"
        or value.get("certification") != "NOT_CERTIFIED"
    ):
        raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False)
    ordinals: set[int] = set()
    names: set[str] = set()
    expected_by_ordinal = {
        binding.ordinal: binding for binding in SKILL_REGISTRY.values()
    }
    expected_skills: list[dict[str, Any]] = []
    for expected_ordinal in range(1, 51):
        expected_binding = expected_by_ordinal[expected_ordinal]
        expected_skills.append(
            {
                "ordinal": expected_binding.ordinal,
                "skill": expected_binding.skill,
                "handler_id": expected_binding.handler_id,
                "phase": expected_binding.phase,
                "implementation_state": "CODE_IMPLEMENTED_LOCAL",
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "transport": {
                    "maximum_request_bytes": 2 * 1024 * 1024,
                    "maximum_json_part_bytes": 1024 * 1024,
                    "part_number_base": 0,
                },
            }
        )
    for item in skills:
        if not isinstance(item, dict):
            raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False)
        ordinal = item.get("ordinal")
        name = item.get("skill")
        transport = item.get("transport")
        expected = expected_by_ordinal.get(ordinal) if isinstance(ordinal, int) else None
        if (
            set(item) != {
                "ordinal", "skill", "handler_id", "phase", "implementation_state",
                "external_evidence", "certification", "transport",
            }
            or not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or not isinstance(name, str)
            or not _SKILL.fullmatch(name)
            or not isinstance(item.get("handler_id"), str)
            or not _HANDLER.fullmatch(item["handler_id"])
            or not _valid_bounded_text(item.get("phase"), 64)
            or expected is None
            or name != expected.skill
            or item.get("handler_id") != expected.handler_id
            or item.get("phase") != expected.phase
            or item.get("implementation_state") != "CODE_IMPLEMENTED_LOCAL"
            or item.get("external_evidence") != "NOT_RUN"
            or item.get("certification") != "NOT_CERTIFIED"
            or not isinstance(transport, dict)
            or transport != {
                "maximum_request_bytes": 2 * 1024 * 1024,
                "maximum_json_part_bytes": 1024 * 1024,
                "part_number_base": 0,
            }
            or ordinal in ordinals
            or name in names
        ):
            raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False)
        ordinals.add(ordinal)
        names.add(name)
    if ordinals != set(range(1, 51)):
        raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False)
    expected_document = {
        "schema_version": "1.0.0",
        "status": "CODE_IMPLEMENTED_LOCAL",
        "skill_count": 50,
        "skills": expected_skills,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    try:
        if (
            not hmac.compare_digest(canonical_digest(skills), canonical_digest(expected_skills))
            or not hmac.compare_digest(canonical_digest(value), canonical_digest(expected_document))
        ):
            raise SdkError(502, "SDK_CAPABILITIES_DIGEST_INVALID", False)
    except IntakeError as error:
        raise SdkError(502, "SDK_CAPABILITIES_CONTRACT_INVALID", False) from error
    return dict(value)


@dataclass(frozen=True, slots=True)
class ProgressBatch:
    resource_kind: str
    resource_id: str
    documents: tuple[Mapping[str, Any], ...]
    heartbeat: Mapping[str, Any] | None
    requested_cursor: str | None

    @property
    def next_cursor(self) -> str | None:
        if self.documents:
            cursor = self.documents[-1].get("cursor")
            return cursor if isinstance(cursor, str) else None
        if self.heartbeat is not None:
            cursor = self.heartbeat.get("cursor")
            return cursor if isinstance(cursor, str) else None
        return None


def _progress_resource_id(value: Any) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise SdkError(400, "SDK_PROGRESS_RESOURCE_ID_INVALID", False)
    return value


def _progress_cursor(value: Any) -> tuple[int, str] | None:
    if value is None:
        return None
    if not isinstance(value, str) or value != value.strip():
        raise SdkError(400, "SDK_PROGRESS_CURSOR_INVALID", False)
    matched = _PROGRESS_CURSOR.fullmatch(value)
    if matched is None:
        raise SdkError(400, "SDK_PROGRESS_CURSOR_INVALID", False)
    sequence = int(matched.group(1))
    if not 1 <= sequence <= MAX_SAFE_JSON_INTEGER:
        raise SdkError(400, "SDK_PROGRESS_CURSOR_INVALID", False)
    return sequence, matched.group(2)


def _progress_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_progress_document(
    value: Mapping[str, Any],
    *,
    resource_kind: str,
    resource_id: str,
    event_name: str,
    event_id: str | None,
    requested_cursor: str | None,
) -> dict[str, Any]:
    """Validate one canonical task/job progress or heartbeat document."""

    safe_resource_id = _progress_resource_id(resource_id)
    parsed_cursor = _progress_cursor(requested_cursor)
    if resource_kind not in {"task", "job"} or event_name not in {"progress", "heartbeat"}:
        raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False)
    if not isinstance(value, Mapping):
        raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False)
    common = {"schema_version", "kind", "resource_id", "sequence_number", "content_digest", "cursor"}
    kind = value.get("kind")
    sequence = value.get("sequence_number")
    digest_value = value.get("content_digest")
    digest_match = _CONTENT_DIGEST.fullmatch(digest_value) if isinstance(digest_value, str) else None
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("resource_id") != safe_resource_id
        or isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or not 0 <= sequence <= MAX_SAFE_JSON_INTEGER
        or digest_match is None
    ):
        raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False)
    if event_name == "heartbeat":
        expected_kind = f"{resource_kind.upper()}_PROGRESS_HEARTBEAT"
        if (
            set(value) != common | {"status"}
            or kind != expected_kind
            or value.get("status") != "NO_CHANGE"
            or event_id is not None
            or value.get("cursor") != requested_cursor
            or sequence != (parsed_cursor[0] if parsed_cursor is not None else 0)
        ):
            raise SdkError(502, "SDK_PROGRESS_HEARTBEAT_INVALID", False)
    elif resource_kind == "task":
        if (
            set(value) != common | {"event_type", "state", "previous_state", "occurred_at"}
            or kind != "TASK_PROGRESS"
            or value.get("event_type") != "durable.task.transitioned"
            or value.get("state") not in _TASK_STATES
            or value.get("previous_state") not in _TASK_STATES
            or value.get("state") not in _TASK_TRANSITIONS[value["previous_state"]]
            or not _progress_timestamp(value.get("occurred_at"))
        ):
            raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False)
    else:
        attempt = value.get("attempt")
        maximum_attempts = value.get("max_attempts")
        if (
            set(value) != common
            | {"event_type", "state", "result_status", "attempt", "max_attempts", "occurred_at"}
            or kind != "JOB_PROGRESS"
            or value.get("event_type") != "processing.job.snapshot"
            or value.get("state") not in _JOB_STATES
            or value.get("result_status") not in _RESULT_STATUSES
            or isinstance(attempt, bool)
            or not isinstance(attempt, int)
            or isinstance(maximum_attempts, bool)
            or not isinstance(maximum_attempts, int)
            or not 0 <= attempt <= maximum_attempts <= MAX_SAFE_JSON_INTEGER
            or maximum_attempts < 1
            or not _progress_timestamp(value.get("occurred_at"))
        ):
            raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False)
    unsigned = dict(value)
    unsigned.pop("content_digest")
    unsigned.pop("cursor")
    try:
        expected_digest = canonical_digest(unsigned)
    except IntakeError as error:
        raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False) from error
    if not hmac.compare_digest(digest_match.group(1), expected_digest):
        raise SdkError(502, "SDK_PROGRESS_DIGEST_INVALID", False)
    cursor_value = value.get("cursor")
    if event_name == "progress":
        expected_cursor = f"p1-{sequence}-{expected_digest}"
        if (
            not isinstance(cursor_value, str)
            or not hmac.compare_digest(cursor_value, expected_cursor)
            or not isinstance(event_id, str)
            or not hmac.compare_digest(event_id, expected_cursor)
            or parsed_cursor is not None
            and sequence <= parsed_cursor[0]
        ):
            raise SdkError(502, "SDK_PROGRESS_CURSOR_INVALID", False)
    return dict(value)


def parse_progress_sse(
    payload: bytes,
    *,
    resource_kind: str,
    resource_id: str,
    requested_cursor: str | None = None,
) -> ProgressBatch:
    """Parse the runtime's bounded one-shot SSE response, never a live command channel."""

    safe_resource_id = _progress_resource_id(resource_id)
    parsed_cursor = _progress_cursor(requested_cursor)
    if resource_kind not in {"task", "job"}:
        raise SdkError(400, "SDK_PROGRESS_RESOURCE_KIND_INVALID", False)
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_RESPONSE_BYTES:
        raise SdkError(502, "SDK_PROGRESS_RESPONSE_TOO_LARGE", False)
    if b"\r" in payload or b"\x00" in payload or not payload.endswith(b"\n\n"):
        raise SdkError(502, "SDK_PROGRESS_SSE_INVALID", False)
    raw_frames = payload[:-2].split(b"\n\n")
    if not 1 <= len(raw_frames) <= MAX_PROGRESS_DOCUMENTS:
        raise SdkError(502, "SDK_PROGRESS_SSE_INVALID", False)
    documents: list[Mapping[str, Any]] = []
    heartbeat: Mapping[str, Any] | None = None
    prior_sequence = parsed_cursor[0] if parsed_cursor is not None else 0
    prior_task_state: str | None = None
    for raw_frame in raw_frames:
        try:
            lines = raw_frame.decode("utf-8", errors="strict").split("\n")
        except UnicodeDecodeError as error:
            raise SdkError(502, "SDK_PROGRESS_SSE_INVALID", False) from error
        event_id: str | None = None
        if len(lines) == 3 and lines[0].startswith("id: "):
            event_id = lines.pop(0)[4:]
        if len(lines) != 2 or not lines[0].startswith("event: ") or not lines[1].startswith("data: "):
            raise SdkError(502, "SDK_PROGRESS_SSE_INVALID", False)
        event_name = lines[0][7:]
        raw_json = lines[1][6:].encode("utf-8")
        value = _strict_json_loads(raw_json, invalid_code="SDK_PROGRESS_JSON_INVALID")
        if not isinstance(value, Mapping):
            raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False)
        try:
            if canonical_json(value).encode("utf-8") != raw_json:
                raise SdkError(502, "SDK_PROGRESS_CANONICAL_JSON_REQUIRED", False)
        except IntakeError as error:
            raise SdkError(502, "SDK_PROGRESS_ENVELOPE_INVALID", False) from error
        document = validate_progress_document(
            value,
            resource_kind=resource_kind,
            resource_id=safe_resource_id,
            event_name=event_name,
            event_id=event_id,
            requested_cursor=requested_cursor,
        )
        if event_name == "heartbeat":
            if heartbeat is not None or documents or len(raw_frames) != 1:
                raise SdkError(502, "SDK_PROGRESS_HEARTBEAT_INVALID", False)
            heartbeat = document
            continue
        if resource_kind == "job" and documents:
            # The job endpoint is an exact one-snapshot-or-heartbeat contract,
            # not a task-like transition history.
            raise SdkError(502, "SDK_PROGRESS_HISTORY_INVALID", False)
        sequence = int(document["sequence_number"])
        if resource_kind == "task" and sequence != prior_sequence + 1:
            raise SdkError(502, "SDK_PROGRESS_SEQUENCE_INVALID", False)
        if sequence <= prior_sequence:
            raise SdkError(502, "SDK_PROGRESS_SEQUENCE_INVALID", False)
        prior_sequence = sequence
        if resource_kind == "task":
            previous_state = str(document["previous_state"])
            if prior_task_state is None and parsed_cursor is None and previous_state != "PENDING":
                raise SdkError(502, "SDK_PROGRESS_HISTORY_INVALID", False)
            if prior_task_state is not None and previous_state != prior_task_state:
                raise SdkError(502, "SDK_PROGRESS_HISTORY_INVALID", False)
            # A p1 cursor exposes only sequence and digest, not the prior task
            # state.  The first resumed document therefore cannot be inferred;
            # subsequent documents are bound to this observed state.
            prior_task_state = str(document["state"])
        documents.append(document)
    if not documents and heartbeat is None:
        raise SdkError(502, "SDK_PROGRESS_SSE_INVALID", False)
    return ProgressBatch(resource_kind, safe_resource_id, tuple(documents), heartbeat, requested_cursor)


@dataclass(frozen=True, slots=True)
class MultimodalIntakeClient:
    base_url: str
    token: str
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str) or not isinstance(self.token, str):
            raise ValueError("SDK_CONFIGURATION_INVALID")
        try:
            parsed = urlsplit(self.base_url)
            parsed.port
        except ValueError as error:
            raise ValueError("SDK_BASE_URL_INVALID") from error
        try:
            loopback = (
                parsed.hostname is not None
                and ipaddress.ip_address(parsed.hostname).is_loopback
            )
        except ValueError:
            loopback = False
        if not parsed.hostname or parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("SDK_BASE_URL_HTTPS_OR_LOOPBACK_REQUIRED")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("SDK_BASE_URL_INVALID")
        if (
            not 32 <= len(self.token) <= 4096
            or any(ord(character) < 33 or ord(character) > 126 for character in self.token)
        ):
            raise ValueError("SDK_TOKEN_TOO_SHORT")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or not math.isfinite(float(self.timeout_seconds))
            or not 0 < self.timeout_seconds <= 300
        ):
            raise ValueError("SDK_TIMEOUT_INVALID")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", CAPABILITIES_PATH, None)

    def execute(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise SdkError(400, "SDK_REQUEST_INVALID", False)
        try:
            expected_request = SkillExecutionRequest.parse(request)
        except IntakeError as error:
            raise SdkError(400, "SDK_REQUEST_INVALID", False) from error
        return self._request(
            "POST",
            EXECUTE_PATH,
            expected_request.document(),
            expected_request=expected_request,
        )

    def execute_operation(
        self,
        *,
        skill: str,
        operation: str,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        idempotency_key: str,
        trace_id: str,
        input: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Typed-registry entry point; unsupported pairs never reach HTTP."""

        if not isinstance(input, Mapping):
            raise SdkError(400, "SDK_OPERATION_INPUT_INVALID", False, trace_id)
        try:
            require_operation(skill, operation, input)
        except IntakeError as error:
            raise SdkError(400, error.code, False, trace_id) from error
        return self.execute(
            {
                "schema_version": "1.0.0",
                "skill": skill,
                "operation": operation,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "trace_id": trace_id,
                "input": dict(input),
            }
        )

    def evaluate(
        self, *, subject: EvaluationSubject, evidence: Sequence[EvaluationEvidence],
        tenant_id: str, project_id: str, actor_id: str, idempotency_key: str, trace_id: str,
    ) -> dict[str, Any]:
        return self.execute_operation(
            skill="elmos-multimodal-evaluation-framework", operation="evaluate",
            tenant_id=tenant_id, project_id=project_id, actor_id=actor_id,
            idempotency_key=idempotency_key, trace_id=trace_id,
            input={"subject": subject.document(), "evidence": [item.document() for item in evidence]},
        )

    def verify_evaluation(
        self, *, run_id: str, tenant_id: str, project_id: str, actor_id: str,
        idempotency_key: str, trace_id: str,
    ) -> dict[str, Any]:
        return self.execute_operation(
            skill="elmos-multimodal-evaluation-framework", operation="verify",
            tenant_id=tenant_id, project_id=project_id, actor_id=actor_id,
            idempotency_key=idempotency_key, trace_id=trace_id, input={"run_id": run_id},
        )

    def get_evaluation_run(
        self, *, run_id: str, tenant_id: str, project_id: str, actor_id: str,
        idempotency_key: str, trace_id: str,
    ) -> dict[str, Any]:
        return self.execute_operation(
            skill="elmos-multimodal-evaluation-framework", operation="get_run",
            tenant_id=tenant_id, project_id=project_id, actor_id=actor_id,
            idempotency_key=idempotency_key, trace_id=trace_id, input={"run_id": run_id},
        )

    def evaluation_catalog(
        self, *, tenant_id: str, project_id: str, actor_id: str,
        idempotency_key: str, trace_id: str,
    ) -> dict[str, Any]:
        return self.execute_operation(
            skill="elmos-multimodal-evaluation-framework", operation="catalog",
            tenant_id=tenant_id, project_id=project_id, actor_id=actor_id,
            idempotency_key=idempotency_key, trace_id=trace_id, input={},
        )

    def begin_project_package(
        self, *, expected_entry_count: int, tenant_id: str, project_id: str, actor_id: str,
        idempotency_key: str, trace_id: str, session_id: str | None = None,
    ) -> dict[str, Any]:
        input: dict[str, Any] = {"expected_entry_count": expected_entry_count}
        if session_id is not None:
            input["session_id"] = session_id
        return self.execute_operation(
            skill="elmos-folder-tree-input", operation="begin", tenant_id=tenant_id,
            project_id=project_id, actor_id=actor_id, idempotency_key=idempotency_key,
            trace_id=trace_id, input=input,
        )

    def append_project_package(
        self, *, session_id: str, chunk_index: int, entries: Sequence[ProjectPackageEntry],
        tenant_id: str, project_id: str, actor_id: str, idempotency_key: str, trace_id: str,
    ) -> dict[str, Any]:
        return self.execute_operation(
            skill="elmos-folder-tree-input", operation="append", tenant_id=tenant_id,
            project_id=project_id, actor_id=actor_id, idempotency_key=idempotency_key,
            trace_id=trace_id,
            input={"session_id": session_id, "chunk_index": chunk_index, "entries": [item.document() for item in entries]},
        )

    def project_package_page(
        self, *, package_version: int, tenant_id: str, project_id: str, actor_id: str,
        idempotency_key: str, trace_id: str, limit: int = 100, cursor: str | None = None,
    ) -> dict[str, Any]:
        input: dict[str, Any] = {"package_version": package_version, "limit": limit}
        if cursor is not None:
            input["cursor"] = cursor
        return self.execute_operation(
            skill="elmos-project-package-preview-and-review-ui", operation="page",
            tenant_id=tenant_id, project_id=project_id, actor_id=actor_id,
            idempotency_key=idempotency_key, trace_id=trace_id, input=input,
        )

    def confirm_project_package_part(
        self, *, session_id: str, path: str, part_number: int, data: bytes,
        tenant_id: str, project_id: str, actor_id: str, idempotency_key: str, trace_id: str,
    ) -> dict[str, Any]:
        if not isinstance(data, bytes):
            raise SdkError(400, "SDK_OPERATION_INPUT_INVALID", False, trace_id)
        return self.execute_operation(
            skill="elmos-resumable-multi-file-folder-upload", operation="confirm_part",
            tenant_id=tenant_id, project_id=project_id, actor_id=actor_id,
            idempotency_key=idempotency_key, trace_id=trace_id,
            input={
                "session_id": session_id,
                "path": path,
                "part_number": part_number,
                "byte_count": len(data),
                "part_digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                "data_base64": base64.b64encode(data).decode("ascii"),
            },
        )

    def task_progress(
        self,
        task_id: str,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        cursor: str | None = None,
    ) -> ProgressBatch:
        return self._progress(
            "task",
            task_id,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            cursor=cursor,
        )

    def job_progress(
        self,
        job_id: str,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        cursor: str | None = None,
    ) -> ProgressBatch:
        return self._progress(
            "job",
            job_id,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            cursor=cursor,
        )

    def _progress(
        self,
        resource_kind: str,
        resource_id: str,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        cursor: str | None,
    ) -> ProgressBatch:
        safe_resource_id = _progress_resource_id(resource_id)
        _progress_cursor(cursor)
        if (
            not isinstance(tenant_id, str)
            or _RESOURCE_ID.fullmatch(tenant_id) is None
            or not isinstance(project_id, str)
            or _RESOURCE_ID.fullmatch(project_id) is None
            or not isinstance(actor_id, str)
            or _ACTOR_ID.fullmatch(actor_id) is None
        ):
            raise SdkError(400, "SDK_PROGRESS_BOUND_IDENTITY_INVALID", False)
        prefix = PROGRESS_TASK_EVENTS_PREFIX if resource_kind == "task" else PROGRESS_JOB_EVENTS_PREFIX
        target = prefix + safe_resource_id + "/events"
        if cursor is not None:
            target += "?cursor=" + quote(cursor, safe="")
        request = urllib.request.Request(
            self.base_url + target,
            method="GET",
            data=None,
            headers={
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {self.token}",
                "X-ELMOS-Bound-Tenant": tenant_id,
                "X-ELMOS-Bound-Project": project_id,
                "X-ELMOS-Bound-Actor": actor_id,
            },
        )
        try:
            with _NO_REDIRECT_OPENER.open(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                if response.getcode() != 200:
                    raise SdkError(502, "SDK_PROGRESS_HTTP_STATUS_INVALID", False)
                content_types = response.headers.get_all("Content-Type", [])
                if (
                    len(content_types) != 1
                    or content_types[0].split(";", 1)[0].strip().lower() != "text/event-stream"
                ):
                    raise SdkError(502, "SDK_PROGRESS_CONTENT_TYPE_INVALID", False)
                encodings = response.headers.get_all("Content-Encoding", [])
                if len(encodings) > 1 or encodings and encodings[0].strip().lower() != "identity":
                    raise SdkError(502, "SDK_PROGRESS_CONTENT_ENCODING_INVALID", False)
                lengths = response.headers.get_all("Content-Length", [])
                if len(lengths) > 1 or lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    raise SdkError(502, "SDK_PROGRESS_SIZE_INVALID", False)
                declared = int(lengths[0]) if lengths else None
                if declared is not None and (declared <= 0 or declared > MAX_RESPONSE_BYTES):
                    raise SdkError(502, "SDK_PROGRESS_RESPONSE_TOO_LARGE", False)
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise SdkError(502, "SDK_PROGRESS_RESPONSE_TOO_LARGE", False)
                if declared is not None and len(payload) != declared:
                    raise SdkError(502, "SDK_PROGRESS_SIZE_INVALID", False)
        except urllib.error.HTTPError as error:
            try:
                content_types = error.headers.get_all("Content-Type", []) if error.headers else []
                if (
                    len(content_types) != 1
                    or "," in content_types[0]
                    or not _is_json_media_type(content_types[0])
                ):
                    raise SdkError(502, "SDK_ERROR_RESPONSE_CONTENT_TYPE_INVALID", False)
                encodings = error.headers.get_all("Content-Encoding", []) if error.headers else []
                if len(encodings) > 1 or encodings and encodings[0].strip().lower() != "identity":
                    raise SdkError(502, "SDK_ERROR_RESPONSE_CONTENT_ENCODING_INVALID", False)
                lengths = error.headers.get_all("Content-Length", []) if error.headers else []
                if len(lengths) > 1 or lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    raise SdkError(502, "SDK_ERROR_RESPONSE_SIZE_INVALID", False)
                declared = int(lengths[0]) if lengths else None
                if declared is not None and (declared <= 0 or declared > MAX_RESPONSE_BYTES):
                    raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
                error_payload = error.read(MAX_RESPONSE_BYTES + 1)
                if not error_payload or len(error_payload) > MAX_RESPONSE_BYTES:
                    raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
                if declared is not None and len(error_payload) != declared:
                    raise SdkError(502, "SDK_ERROR_RESPONSE_SIZE_INVALID", False)
                error_value = _strict_json_loads(
                    error_payload,
                    invalid_code="SDK_ERROR_RESPONSE_INVALID",
                    canonical_code="SDK_ERROR_RESPONSE_CANONICAL_JSON_REQUIRED",
                )
                if not isinstance(error_value, Mapping):
                    raise SdkError(502, "SDK_ERROR_RESPONSE_CONTRACT_INVALID", False)
                error_document = validate_error_response(error_value, error.code)
            except OSError as read_error:
                raise SdkError(502, "SDK_ERROR_RESPONSE_INVALID", False) from read_error
            raise SdkError(
                error.code,
                error_document["code"],
                error_document["retryable"],
                error_document.get("trace_id"),
            ) from error
        except urllib.error.URLError as error:
            raise SdkError(503, "SDK_ENDPOINT_UNAVAILABLE", True) from error
        return parse_progress_sse(
            payload,
            resource_kind=resource_kind,
            resource_id=safe_resource_id,
            requested_cursor=cursor,
        )

    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None,
        *,
        expected_request: SkillExecutionRequest | None = None,
    ) -> dict[str, Any]:
        try:
            if body is not None:
                _validate_json_tree(body)
            # Emit the same RFC 8785/I-JSON profile that request digests and
            # the TypeScript/Java clients use.  Python's stock encoder renders
            # some exponent forms differently (for example ``1e-07``), which
            # would make the on-the-wire contract language-dependent.
            data = None if body is None else canonical_json(body).encode("utf-8")
            if data is not None and len(data) > MAX_REQUEST_BYTES:
                raise ValueError("request exceeds the transport limit")
        except (TypeError, ValueError, UnicodeEncodeError) as error:
            raise SdkError(400, "SDK_REQUEST_INVALID", False) from error
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            method=method,
            data=data,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with _NO_REDIRECT_OPENER.open(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                if response.getcode() != 200:
                    raise SdkError(502, "SDK_HTTP_STATUS_INVALID", False)
                content_types = response.headers.get_all("Content-Type", [])
                if (
                    len(content_types) != 1
                    or not _is_json_media_type(content_types[0])
                ):
                    raise SdkError(502, "SDK_RESPONSE_CONTENT_TYPE_INVALID", False)
                encodings = response.headers.get_all("Content-Encoding", [])
                if len(encodings) > 1 or encodings and encodings[0].strip().lower() != "identity":
                    raise SdkError(502, "SDK_RESPONSE_CONTENT_ENCODING_INVALID", False)
                lengths = response.headers.get_all("Content-Length", [])
                if len(lengths) > 1 or lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    raise SdkError(502, "SDK_RESPONSE_SIZE_INVALID", False)
                declared = int(lengths[0]) if lengths else None
                if declared is not None and (declared <= 0 or declared > MAX_RESPONSE_BYTES):
                    raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if not payload or len(payload) > MAX_RESPONSE_BYTES:
                    raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
                if declared is not None and len(payload) != declared:
                    raise SdkError(502, "SDK_RESPONSE_SIZE_INVALID", False)
                value = _strict_json_loads(
                    payload,
                    invalid_code="SDK_RESPONSE_INVALID",
                    canonical_code="SDK_RESPONSE_CANONICAL_JSON_REQUIRED",
                )
        except urllib.error.HTTPError as error:
            try:
                content_types = error.headers.get_all("Content-Type", []) if error.headers else []
                if (
                    len(content_types) != 1
                    or not _is_json_media_type(content_types[0])
                ):
                    raise SdkError(502, "SDK_ERROR_RESPONSE_CONTENT_TYPE_INVALID", False)
                encodings = error.headers.get_all("Content-Encoding", []) if error.headers else []
                if len(encodings) > 1 or encodings and encodings[0].strip().lower() != "identity":
                    raise SdkError(502, "SDK_ERROR_RESPONSE_CONTENT_ENCODING_INVALID", False)
                lengths = error.headers.get_all("Content-Length", []) if error.headers else []
                if len(lengths) > 1 or lengths and not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
                    raise SdkError(502, "SDK_ERROR_RESPONSE_SIZE_INVALID", False)
                declared = int(lengths[0]) if lengths else None
                if declared is not None and (declared <= 0 or declared > MAX_RESPONSE_BYTES):
                    raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
                payload = error.read(MAX_RESPONSE_BYTES + 1)
                if not payload or len(payload) > MAX_RESPONSE_BYTES:
                    raise SdkError(502, "SDK_RESPONSE_TOO_LARGE", False)
                if declared is not None and len(payload) != declared:
                    raise SdkError(502, "SDK_ERROR_RESPONSE_SIZE_INVALID", False)
                value = _strict_json_loads(
                    payload,
                    invalid_code="SDK_ERROR_RESPONSE_INVALID",
                    canonical_code="SDK_ERROR_RESPONSE_CANONICAL_JSON_REQUIRED",
                )
                if not isinstance(value, Mapping):
                    raise SdkError(502, "SDK_ERROR_RESPONSE_CONTRACT_INVALID", False)
                error_document = validate_error_response(value, error.code)
            except OSError as read_error:
                raise SdkError(502, "SDK_ERROR_RESPONSE_INVALID", False) from read_error
            raise SdkError(
                error.code,
                error_document["code"],
                error_document["retryable"],
                error_document.get("trace_id"),
            ) from error
        except urllib.error.URLError as error:
            raise SdkError(503, "SDK_ENDPOINT_UNAVAILABLE", True) from error
        if not isinstance(value, Mapping):
            raise SdkError(502, "SDK_RESPONSE_INVALID", False)
        if path == CAPABILITIES_PATH:
            return validate_capability_response(value)
        if path == EXECUTE_PATH:
            return validate_execution_result(value, expected_request=expected_request)
        raise SdkError(502, "SDK_RESPONSE_ROUTE_INVALID", False)
