"""Trusted durable bridge for Skill 17 human-review corrections."""

from __future__ import annotations

import hmac
import math
from collections.abc import Mapping
from typing import Any

from .canonical import (
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    normalize_sha256,
    require_idempotency_key,
    require_resource_id,
)
from .content import apply_human_correction, content_contract_json
from .errors import AuthorizationError, ConflictError, IntegrityError, ValidationError
from .human_review_workflow import HumanReviewWorkflow, bounded_review_json
from .models import TenantContext
from .skill_runtime import RuntimeContext
from .store import IntakeStore


_MAX_CORRECTION_JSON_DEPTH = 32
_MAX_CORRECTION_JSON_NODES = 250_000
_MAX_CORRECTION_JSON_BYTES = 2 * 1024 * 1024


def _bounded_correction_json(value: Any) -> Any:
    """Copy an exact, persistence-safe JSON value with deterministic limits."""

    remaining = [_MAX_CORRECTION_JSON_NODES]

    def visit(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_LIMIT_EXCEEDED")
        if depth > _MAX_CORRECTION_JSON_DEPTH:
            raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_LIMIT_EXCEEDED")
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID") from error
            return item
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_JSON_INTEGER:
                raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")
            return item
        if isinstance(item, float):
            if (
                not math.isfinite(item)
                or item.is_integer() and abs(item) > MAX_SAFE_JSON_INTEGER
            ):
                raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")
            return item
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, Mapping):
            copied: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")
                try:
                    encoded_key = key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as error:
                    raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID") from error
                if len(encoded_key) > 256:
                    raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")
                copied[key] = visit(child, depth + 1)
            return copied
        raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")

    copied = visit(value, 0)
    try:
        byte_count = len(content_contract_json(copied).encode("utf-8", errors="strict"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID") from error
    if byte_count > _MAX_CORRECTION_JSON_BYTES:
        raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_LIMIT_EXCEEDED")
    return copied


class HumanReviewCorrectionBridge:
    """Build trusted correction inputs from the durable scoped asset state."""

    SKILL = "elmos-human-review-and-correction"
    _CORRECT_FIELDS = frozenset(
        {
            "operation",
            "content_id",
            "expected_version",
            "value",
            "reason",
            "idempotency_key",
            "trace_id",
        }
    )
    _CORRECTION_FIELDS = frozenset({"value", "reason"})
    _COMMON_FIELDS = frozenset({"operation", "idempotency_key", "trace_id"})
    _OPERATION_FIELDS = {
        "correct": (_CORRECT_FIELDS, _CORRECT_FIELDS | frozenset({"expected_digest"})),
        "enqueue": _COMMON_FIELDS
        | frozenset(
            {
                "content_id",
                "expected_asset_version",
                "target_kind",
                "target_digest",
                "expected_head_version",
                "expected_snapshot_id",
                "expected_snapshot_digest",
                "expected_head_value_digest",
                "original_value_digest",
                "reason",
            }
        ),
        "enqueue_prepare": _COMMON_FIELDS
        | frozenset(
            {
                "recovery_handle",
                "execute_idempotency_key",
                "content_id",
                "expected_asset_version",
                "target_kind",
                "target_digest",
                "expected_head_version",
                "expected_snapshot_id",
                "expected_snapshot_digest",
                "expected_head_value_digest",
                "original_value_digest",
                "reason",
            }
        ),
        "enqueue_execute": _COMMON_FIELDS | frozenset({"recovery_handle"}),
        "source_register": _COMMON_FIELDS
        | frozenset(
            {
                "content_id",
                "expected_asset_version",
                "target_kind",
                "target",
                "original_value",
                "confidence",
                "provenance",
            }
        ),
        "source_list": _COMMON_FIELDS
        | frozenset(
            {
                "content_id",
                "expected_asset_version",
                "kinds",
                "limit",
                "cursor",
            }
        ),
        "source_get": _COMMON_FIELDS
        | frozenset(
            {
                "content_id",
                "expected_asset_version",
                "target_kind",
                "target_digest",
                "expected_head_version",
            }
        ),
        "list": _COMMON_FIELDS
        | frozenset({"kinds", "states", "confidence_lte", "limit", "cursor"}),
        "get": _COMMON_FIELDS | frozenset({"task_id"}),
        "current_correction": _COMMON_FIELDS | frozenset({"task_id"}),
        "claim": _COMMON_FIELDS
        | frozenset({"task_id", "expected_version", "claim_token", "lease_seconds"}),
        "edit": _COMMON_FIELDS
        | frozenset(
            {
                "task_id",
                "expected_version",
                "expected_correction_version",
                "claim_token",
                "claim_fence",
                "correction",
            }
        ),
        "approve": _COMMON_FIELDS
        | frozenset({"task_id", "expected_version", "claim_token", "claim_fence", "reason"}),
        "reject": _COMMON_FIELDS
        | frozenset({"task_id", "expected_version", "claim_token", "claim_fence", "reason"}),
        "reopen": _COMMON_FIELDS | frozenset({"task_id", "expected_version", "reason"}),
        "revert": _COMMON_FIELDS | frozenset({"task_id", "expected_version", "reason"}),
        "propagation_status": _COMMON_FIELDS | frozenset({"task_id"}),
        "reservation_status": _COMMON_FIELDS | frozenset({"task_id"}),
        "propagation_claim": _COMMON_FIELDS
        | frozenset({"propagation_id", "owner_token", "lease_seconds"}),
        "propagation_dispatch": _COMMON_FIELDS
        | frozenset({"propagation_id", "owner_token", "claim_fence"}),
        "propagation_complete": _COMMON_FIELDS
        | frozenset(
            {
                "propagation_id",
                "owner_token",
                "claim_fence",
                "outcome",
                "result",
                "failure_code",
            }
        ),
        "propagation_reconcile": _COMMON_FIELDS
        | frozenset({"propagation_id", "outcome", "result", "failure_code"}),
    }
    _WORKER_CAPABILITY_FIELDS = frozenset(
        {"version", "tenant_id", "project_id", "capability_id", "token"}
    )

    def __init__(self, store: IntakeStore) -> None:
        self._store = store
        self._workflow = HumanReviewWorkflow(store)

    @staticmethod
    def _envelope(result: Mapping[str, Any]) -> dict[str, Any]:
        if set(result) != {"state", "code", "outputs"}:
            raise IntegrityError("HUMAN_REVIEW_DOMAIN_RESULT_INVALID")
        return {
            "state": result["state"],
            "code": result["code"],
            "outputs": result["outputs"],
            "metrics": {},
            "retryable": False,
        }

    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if skill_name != self.SKILL:
            raise ValidationError("HUMAN_REVIEW_BRIDGE_SKILL_INVALID")
        operation = payload.get("operation")
        if not isinstance(operation, str):
            raise ValidationError("HUMAN_REVIEW_OPERATION_INVALID")
        expected_fields = self._OPERATION_FIELDS.get(operation)
        if expected_fields is None:
            raise ValidationError("HUMAN_REVIEW_OPERATION_INVALID")
        allowed_field_sets = (
            expected_fields
            if isinstance(expected_fields, tuple)
            else (expected_fields,)
        )
        payload_fields = frozenset(payload)
        if payload_fields not in allowed_field_sets:
            closest = min(
                allowed_field_sets,
                key=lambda fields: len(fields - payload_fields) + len(payload_fields - fields),
            )
            raise ValidationError(
                "HUMAN_REVIEW_INPUT_FIELDS_INVALID",
                details={
                    "missing_fields": sorted(closest - payload_fields),
                    "unexpected_fields": sorted(payload_fields - closest),
                },
            )
        if ctx.idempotency_key is None:
            raise ValidationError("HUMAN_REVIEW_IDEMPOTENCY_KEY_REQUIRED")
        idempotency_key = require_idempotency_key(ctx.idempotency_key)
        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationError("HUMAN_REVIEW_IDEMPOTENCY_BINDING_INVALID")
        if payload.get("trace_id") != ctx.trace_id:
            raise ValidationError("HUMAN_REVIEW_TRACE_BINDING_INVALID")
        if operation != "correct":
            return self._handle_workflow(
                ctx,
                payload,
                operation=operation,
                idempotency_key=idempotency_key,
            )

        raw_content_id = payload.get("content_id")
        if not isinstance(raw_content_id, str):
            raise ValidationError("HUMAN_REVIEW_CONTENT_ID_INVALID")
        content_id = require_resource_id(raw_content_id, "content_id")
        if content_id != raw_content_id:
            raise ValidationError("HUMAN_REVIEW_CONTENT_ID_INVALID")
        expected_version = payload.get("expected_version")
        if (
            not isinstance(expected_version, int)
            or isinstance(expected_version, bool)
            or not 1 <= expected_version <= MAX_SAFE_JSON_INTEGER - 1
        ):
            raise ValidationError("HUMAN_REVIEW_EXPECTED_VERSION_INVALID")
        correction_document = _bounded_correction_json(
            {"value": payload.get("value"), "reason": payload.get("reason")}
        )
        if not isinstance(correction_document, dict):
            raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")
        reason = correction_document.get("reason")
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or reason != reason.strip()
            or len(reason.encode("utf-8")) > 2_000
        ):
            raise ValidationError("HUMAN_REVIEW_CORRECTION_REASON_INVALID")
        if correction_document.get("value") is None:
            raise ValidationError("HUMAN_REVIEW_CORRECTION_VALUE_REQUIRED")

        request_digest = canonical_digest(
            {
                "schema_version": "elmos-human-review-correction-request-v1",
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "actor_id": ctx.actor_id,
                "skill": self.SKILL,
                "operation": "correct",
                "content_id": content_id,
                "expected_version": expected_version,
                "value": correction_document["value"],
                "reason": correction_document["reason"],
                "expected_digest": payload.get("expected_digest"),
                "idempotency_key": idempotency_key,
                "policy_digest": f"sha256:{canonical_digest(ctx.policy)}",
            }
        )
        context = TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)
        current, review_state, replay = self._store.prepare_human_review_correction(
            context,
            asset_id=content_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        if replay is not None:
            return replay
        if current is None or review_state is None:
            raise IntegrityError("HUMAN_REVIEW_CURRENT_STATE_UNAVAILABLE")
        if current.get("version") != expected_version:
            raise ConflictError(
                "OPTIMISTIC_LOCK_CONFLICT",
                details={
                    "expected_version": expected_version,
                    "actual_version": current.get("version"),
                },
            )

        expected_digest = payload.get("expected_digest")
        if expected_digest is not None:
            if not isinstance(expected_digest, str):
                raise ValidationError("HUMAN_REVIEW_EXPECTED_DIGEST_INVALID")
            try:
                normalized_expected_digest = normalize_sha256(expected_digest)
                current_digest = current.get("digest")
                if not isinstance(current_digest, str):
                    raise ValidationError("HUMAN_REVIEW_EXPECTED_DIGEST_INVALID")
                normalized_current_digest = normalize_sha256(current_digest)
            except ValidationError as error:
                raise ValidationError("HUMAN_REVIEW_EXPECTED_DIGEST_INVALID") from error
            if expected_digest != f"sha256:{normalized_expected_digest}":
                raise ValidationError("HUMAN_REVIEW_EXPECTED_DIGEST_INVALID")
            if not hmac.compare_digest(
                normalized_expected_digest,
                normalized_current_digest,
            ):
                raise ConflictError("HUMAN_REVIEW_CURRENT_DRIFT")

        trusted_capabilities = dict(ctx.capabilities)
        trusted_capabilities["human_review_state"] = review_state
        domain_result = apply_human_correction(
            {
                "schema_version": "1.0",
                "request_id": ctx.request_id,
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "actor_id": ctx.actor_id,
                "idempotency_key": idempotency_key,
                "trace_id": ctx.trace_id,
                "inputs": {
                    "current": current,
                    "correction": {
                        "expected_version": expected_version,
                        **correction_document,
                    },
                },
                # Authorization remains host-owned.  Only the mutable state
                # capability is replaced with the store-derived exact snapshot.
                "policy": dict(ctx.policy),
                "capabilities": trusted_capabilities,
            }
        )
        if domain_result.get("state") != "SUCCEEDED":
            return self._envelope(domain_result)
        return self._store.commit_human_review_correction(
            context,
            asset_id=content_id,
            expected_version=expected_version,
            expected_current_digest=str(current["digest"]),
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            domain_result=domain_result,
        )

    @staticmethod
    def _success(code: str, outputs: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "state": "SUCCEEDED",
            "code": code,
            "outputs": dict(outputs),
            "metrics": {},
            "retryable": False,
        }

    @staticmethod
    def _require_review_policy(ctx: RuntimeContext, operation: str) -> None:
        policy = ctx.policy.get("human_review") if isinstance(ctx.policy, Mapping) else None
        if (
            not isinstance(policy, Mapping)
            or not str(policy.get("version", "")).strip()
            or policy.get("tenant_id") != ctx.tenant_id
            or policy.get("project_id") != ctx.project_id
        ):
            raise AuthorizationError("HUMAN_REVIEW_POLICY_UNAVAILABLE")
        allowed_actions = policy.get("allowed_actions")
        allowed_actors = policy.get("allowed_actor_ids")
        if (
            not isinstance(allowed_actions, list)
            or operation not in allowed_actions
            or not isinstance(allowed_actors, list)
            or allowed_actors and ctx.actor_id not in allowed_actors
        ):
            raise AuthorizationError("HUMAN_REVIEW_NOT_AUTHORIZED")

    @classmethod
    def _worker_capability(cls, ctx: RuntimeContext) -> tuple[str, str]:
        capability = (
            ctx.capabilities.get("human_review_propagation_worker")
            if isinstance(ctx.capabilities, Mapping)
            else None
        )
        if (
            not isinstance(capability, Mapping)
            or set(capability) != cls._WORKER_CAPABILITY_FIELDS
            or not str(capability.get("version", "")).strip()
            or capability.get("tenant_id") != ctx.tenant_id
            or capability.get("project_id") != ctx.project_id
            or not isinstance(capability.get("capability_id"), str)
            or not isinstance(capability.get("token"), str)
        ):
            raise AuthorizationError("HUMAN_REVIEW_WORKER_CAPABILITY_DENIED")
        capability_id = require_resource_id(str(capability["capability_id"]), "capability_id")
        token = require_idempotency_key(str(capability["token"]))
        return capability_id, token

    @classmethod
    def _source_producer_capability(cls, ctx: RuntimeContext) -> tuple[str, str]:
        capability = (
            ctx.capabilities.get("human_review_source_producer")
            if isinstance(ctx.capabilities, Mapping)
            else None
        )
        if (
            not isinstance(capability, Mapping)
            or set(capability) != cls._WORKER_CAPABILITY_FIELDS
            or capability.get("version") != "human-review-source-producer-v1"
            or capability.get("tenant_id") != ctx.tenant_id
            or capability.get("project_id") != ctx.project_id
            or not isinstance(capability.get("capability_id"), str)
            or not isinstance(capability.get("token"), str)
        ):
            raise AuthorizationError("HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED")
        capability_id = require_resource_id(str(capability["capability_id"]), "capability_id")
        token = require_idempotency_key(str(capability["token"]))
        return capability_id, token

    @staticmethod
    def _workflow_request_digest(
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        *,
        operation: str,
        worker_capability_id: str | None = None,
    ) -> str:
        safe_payload = bounded_review_json(payload)
        return canonical_digest(
            {
                "schema_version": "elmos-human-review-workflow-request-v1",
                "tenant_id": ctx.tenant_id,
                "project_id": ctx.project_id,
                "actor_id": ctx.actor_id,
                "skill": HumanReviewCorrectionBridge.SKILL,
                "operation": operation,
                "payload": safe_payload,
                "policy_digest": f"sha256:{canonical_digest(ctx.policy)}",
                "worker_capability_id": worker_capability_id,
            }
        )

    def _handle_workflow(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        *,
        operation: str,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        context = TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)
        worker_capability_id: str | None = None
        worker_capability_token: str | None = None
        if operation == "source_register":
            worker_capability_id, worker_capability_token = (
                self._source_producer_capability(ctx)
            )
        elif operation.startswith("propagation_") and operation != "propagation_status":
            worker_capability_id, worker_capability_token = self._worker_capability(ctx)
        elif operation not in {
            "source_list",
            "source_get",
            "list",
            "get",
            "current_correction",
            "propagation_status",
            "reservation_status",
        }:
            self._require_review_policy(ctx, operation)
        request_digest = self._workflow_request_digest(
            ctx,
            payload,
            operation=operation,
            worker_capability_id=worker_capability_id,
        )
        if operation == "source_register":
            assert worker_capability_id is not None and worker_capability_token is not None
            result = self._workflow.register_source_snapshot(
                context,
                asset_id=payload["content_id"],
                expected_asset_version=payload["expected_asset_version"],
                target_kind=payload["target_kind"],
                target=payload["target"],
                original_value=payload["original_value"],
                confidence=payload["confidence"],
                provenance=payload["provenance"],
                capability_id=worker_capability_id,
                capability_token=worker_capability_token,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_SOURCE_REGISTERED", result)
        if operation == "source_list":
            result = self._workflow.list_source_heads(
                context,
                asset_id=payload["content_id"],
                expected_asset_version=payload["expected_asset_version"],
                kinds=payload["kinds"],
                limit=payload["limit"],
                cursor=payload["cursor"],
            )
            return self._success("HUMAN_REVIEW_SOURCES_LISTED", result)
        if operation == "source_get":
            result = self._workflow.get_source_head(
                context,
                asset_id=payload["content_id"],
                expected_asset_version=payload["expected_asset_version"],
                target_kind=payload["target_kind"],
                target_digest=payload["target_digest"],
                expected_head_version=payload["expected_head_version"],
            )
            return self._success("HUMAN_REVIEW_SOURCE_RETRIEVED", result)
        if operation == "enqueue_prepare":
            result = self._workflow.prepare_enqueue_review_task(
                context,
                recovery_handle=payload["recovery_handle"],
                execute_idempotency_key=payload["execute_idempotency_key"],
                asset_id=payload["content_id"],
                expected_asset_version=payload["expected_asset_version"],
                target_kind=payload["target_kind"],
                target_digest=payload["target_digest"],
                expected_head_version=payload["expected_head_version"],
                expected_snapshot_id=payload["expected_snapshot_id"],
                expected_snapshot_digest=payload["expected_snapshot_digest"],
                expected_head_value_digest=payload["expected_head_value_digest"],
                original_value_digest=payload["original_value_digest"],
                reason=payload["reason"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_ENQUEUE_PREPARED", result)
        if operation == "enqueue_execute":
            result = self._workflow.execute_prepared_review_task(
                context,
                recovery_handle=payload["recovery_handle"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            preparation = result.get("preparation")
            if not isinstance(preparation, Mapping):
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT")
            state = preparation.get("state")
            if state == "ABSENT":
                code = "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT"
            elif state == "EXPIRED":
                code = "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED"
            elif state == "EXECUTED" and "task" in result:
                code = "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION"
            else:
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT")
            return self._success(code, result)
        if operation == "enqueue":
            result = self._workflow.enqueue_review_task(
                context,
                asset_id=payload["content_id"],
                expected_asset_version=payload["expected_asset_version"],
                target_kind=payload["target_kind"],
                target_digest=payload["target_digest"],
                expected_head_version=payload["expected_head_version"],
                expected_snapshot_id=payload["expected_snapshot_id"],
                expected_snapshot_digest=payload["expected_snapshot_digest"],
                expected_head_value_digest=payload["expected_head_value_digest"],
                original_value_digest=payload["original_value_digest"],
                reason=payload["reason"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_TASK_ENQUEUED", result)
        if operation == "list":
            result = self._workflow.list_review_tasks(
                context,
                kinds=payload["kinds"],
                states=payload["states"],
                confidence_lte=payload["confidence_lte"],
                limit=payload["limit"],
                cursor=payload["cursor"],
            )
            return self._success("HUMAN_REVIEW_TASKS_LISTED", result)
        if operation == "get":
            result = self._workflow.get_review_task(
                context,
                task_id=payload["task_id"],
            )
            return self._success("HUMAN_REVIEW_TASK_RETRIEVED", result)
        if operation == "current_correction":
            result = self._workflow.get_current_correction(
                context,
                task_id=payload["task_id"],
            )
            return self._success("HUMAN_REVIEW_CURRENT_CORRECTION_RETRIEVED", result)
        if operation == "claim":
            result = self._workflow.claim_review_task(
                context,
                task_id=payload["task_id"],
                expected_version=payload["expected_version"],
                claim_token=payload["claim_token"],
                lease_seconds=payload["lease_seconds"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_TASK_CLAIMED", result)
        if operation == "edit":
            correction = payload["correction"]
            if not isinstance(correction, Mapping) or set(correction) != self._CORRECTION_FIELDS:
                raise ValidationError("HUMAN_REVIEW_CORRECTION_FIELDS_INVALID")
            correction_document = bounded_review_json(correction)
            if not isinstance(correction_document, dict):
                raise ValidationError("HUMAN_REVIEW_CORRECTION_JSON_INVALID")
            result = self._workflow.edit_review_task(
                context,
                task_id=payload["task_id"],
                expected_version=payload["expected_version"],
                expected_correction_version=payload["expected_correction_version"],
                claim_token=payload["claim_token"],
                claim_fence=payload["claim_fence"],
                corrected_value=correction_document["value"],
                reason=correction_document["reason"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_CORRECTION_EDITED", result)
        if operation in {"approve", "reject"}:
            result = self._workflow.decide_review_task(
                context,
                task_id=payload["task_id"],
                action=operation.upper(),
                expected_version=payload["expected_version"],
                claim_token=payload["claim_token"],
                claim_fence=payload["claim_fence"],
                reason=payload["reason"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            code = (
                "HUMAN_REVIEW_CORRECTION_APPROVED"
                if operation == "approve"
                else "HUMAN_REVIEW_CORRECTION_REJECTED"
            )
            return self._success(code, result)
        if operation in {"reopen", "revert"}:
            result = self._workflow.decide_review_task(
                context,
                task_id=payload["task_id"],
                action=operation.upper(),
                expected_version=payload["expected_version"],
                reason=payload["reason"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            code = (
                "HUMAN_REVIEW_TASK_REOPENED"
                if operation == "reopen"
                else "HUMAN_REVIEW_REVERT_QUEUED"
            )
            return self._success(code, result)
        if operation == "propagation_status":
            return self._success(
                "HUMAN_REVIEW_PROPAGATION_STATUS",
                self._workflow.review_status(context, task_id=payload["task_id"]),
            )
        if operation == "reservation_status":
            return self._success(
                "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATUS",
                self._workflow.reservation_status(
                    context, task_id=payload["task_id"]
                ),
            )
        assert worker_capability_id is not None and worker_capability_token is not None
        if operation == "propagation_claim":
            result = self._workflow.claim_propagation(
                context,
                propagation_id=payload["propagation_id"],
                capability_id=worker_capability_id,
                capability_token=worker_capability_token,
                owner_token=payload["owner_token"],
                lease_seconds=payload["lease_seconds"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if result["propagation"]["state"] == "UNKNOWN":
                return {
                    "state": "BLOCKED",
                    "code": "HUMAN_REVIEW_PROPAGATION_RECONCILIATION_REQUIRED",
                    "outputs": result,
                    "metrics": {},
                    "retryable": False,
                }
            return self._success("HUMAN_REVIEW_PROPAGATION_CLAIMED", result)
        if operation == "propagation_dispatch":
            result = self._workflow.mark_propagation_dispatched(
                context,
                propagation_id=payload["propagation_id"],
                capability_id=worker_capability_id,
                capability_token=worker_capability_token,
                owner_token=payload["owner_token"],
                claim_fence=payload["claim_fence"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_PROPAGATION_DISPATCHED", result)
        if operation == "propagation_complete":
            result = self._workflow.complete_propagation(
                context,
                propagation_id=payload["propagation_id"],
                capability_id=worker_capability_id,
                capability_token=worker_capability_token,
                owner_token=payload["owner_token"],
                claim_fence=payload["claim_fence"],
                outcome=payload["outcome"],
                result=payload["result"],
                failure_code=payload["failure_code"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            if result["propagation"]["state"] == "UNKNOWN":
                return {
                    "state": "BLOCKED",
                    "code": "HUMAN_REVIEW_PROPAGATION_RECONCILIATION_REQUIRED",
                    "outputs": result,
                    "metrics": {},
                    "retryable": False,
                }
            return self._success("HUMAN_REVIEW_PROPAGATION_COMPLETED", result)
        if operation == "propagation_reconcile":
            result = self._workflow.reconcile_propagation(
                context,
                propagation_id=payload["propagation_id"],
                capability_id=worker_capability_id,
                capability_token=worker_capability_token,
                outcome=payload["outcome"],
                result=payload["result"],
                failure_code=payload["failure_code"],
                idempotency_key=idempotency_key,
                request_digest=request_digest,
            )
            return self._success("HUMAN_REVIEW_PROPAGATION_RECONCILED", result)
        raise ValidationError("HUMAN_REVIEW_OPERATION_INVALID")


__all__ = ["HumanReviewCorrectionBridge"]
