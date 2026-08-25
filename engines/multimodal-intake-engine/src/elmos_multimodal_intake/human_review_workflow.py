"""Durable tenant-scoped review workflow and propagation control plane.

This module treats target/value payloads as untrusted JSON data.  It never
executes reviewed content and stores every correction, decision, and audit
record as an immutable digest-bound version.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any

from .canonical import (
    CANONICAL_JSON_SHA256_CONTRACT,
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    canonical_json,
    normalize_sha256,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
    utc_now,
)
from .content import content_contract_digest, content_contract_json
from .errors import AuthorizationError, ConflictError, IntegrityError, NotFoundError, ValidationError
from .models import (
    ReviewDecisionAction,
    ReviewHeadReservationState,
    ReviewPropagationDirection,
    ReviewPropagationState,
    ReviewTargetKind,
    ReviewTaskState,
    TenantContext,
)
from .store import IntakeStore


_MAX_REVIEW_JSON_DEPTH = 32
_MAX_REVIEW_JSON_NODES = 250_000
_MAX_REVIEW_JSON_BYTES = 2 * 1024 * 1024
_MAX_SOURCE_DISCOVERY_ROWS = 1_000
_ENQUEUE_PREPARATION_TTL = timedelta(hours=24)
_MAX_ACTIVE_ENQUEUE_PREPARATIONS = 100
_MAX_TOTAL_ENQUEUE_PREPARATIONS = 10_000
_PROPAGATION_CHANNELS = (
    "content-index",
    "requirements",
    "project-memory",
    "downstream",
)
_PROPAGATION_PAYLOAD_V2_FIELDS = frozenset(
    {
        "schema_version",
        "tenant_id",
        "project_id",
        "task_id",
        "decision_id",
        "correction_version",
        "correction_digest",
        "channel",
        "direction",
        "target_kind",
        "target",
        "effective_value",
        "effective_value_digest",
        "source_digest",
        "prior_effective_version",
        "prior_effective_value",
        "prior_effective_digest",
        "reservation_id",
        "reservation_fence",
        "reservation_binding_digest",
    }
)
_RESERVATION_TERMINAL_STATES = frozenset(
    {
        ReviewHeadReservationState.FAILED,
        ReviewHeadReservationState.APPLIED,
        ReviewHeadReservationState.REVERTED,
    }
)
_WORKER_ACTIONS = frozenset({"claim", "dispatch", "complete", "reconcile"})
_SOURCE_PROVENANCE_FIELDS = frozenset(
    {"schema_version", "source_kind", "source_id", "source_digest", "producer_version"}
)
_SOURCE_KINDS = frozenset(
    {
        "CONTENT_BLOCK",
        "SOURCE_ANCHOR",
        "REQUIREMENT",
        "CONFLICT",
        "TRUSTED_DERIVATION",
        "WHOLE_ASSET",
    }
)
_SOURCE_REF_V2_FIELDS = frozenset(
    {
        "schema_version",
        "content_id",
        "content_version",
        "content_digest",
        "asset_sha256",
        "target_kind",
        "target_digest",
        "snapshot_id",
        "snapshot_digest",
        "head_version",
        "head_value_digest",
        "source_digest",
        "provenance_digest",
        "original_value_client_digest",
        "original_value_digest_contract",
    }
)
_MISSING = object()


def bounded_review_json(value: Any, *, allow_none: bool = True) -> Any:
    """Return an exact JSON copy bounded for durable Content persistence."""

    remaining = [_MAX_REVIEW_JSON_NODES]

    def visit(item: Any, depth: int) -> Any:
        remaining[0] -= 1
        if remaining[0] < 0 or depth > _MAX_REVIEW_JSON_DEPTH:
            raise ValidationError("HUMAN_REVIEW_JSON_LIMIT_EXCEEDED")
        if isinstance(item, str):
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeEncodeError as error:
                raise ValidationError("HUMAN_REVIEW_JSON_INVALID") from error
            return item
        if item is None:
            if not allow_none:
                raise ValidationError("HUMAN_REVIEW_JSON_NULL_FORBIDDEN")
            return None
        if isinstance(item, bool):
            return item
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_JSON_INTEGER:
                raise ValidationError("HUMAN_REVIEW_JSON_INVALID")
            return item
        if isinstance(item, float):
            if (
                not math.isfinite(item)
                or item.is_integer() and abs(item) > MAX_SAFE_JSON_INTEGER
            ):
                raise ValidationError("HUMAN_REVIEW_JSON_INVALID")
            return item
        if isinstance(item, list):
            return [visit(child, depth + 1) for child in item]
        if isinstance(item, Mapping):
            copied: dict[str, Any] = {}
            for key, child in item.items():
                if not isinstance(key, str) or not key:
                    raise ValidationError("HUMAN_REVIEW_JSON_INVALID")
                try:
                    encoded_key = key.encode("utf-8", errors="strict")
                except UnicodeEncodeError as error:
                    raise ValidationError("HUMAN_REVIEW_JSON_INVALID") from error
                if len(encoded_key) > 256:
                    raise ValidationError("HUMAN_REVIEW_JSON_INVALID")
                copied[key] = visit(child, depth + 1)
            return copied
        raise ValidationError("HUMAN_REVIEW_JSON_INVALID")

    copied = visit(value, 0)
    try:
        rendered = content_contract_json(copied)
        byte_count = len(rendered.encode("utf-8", errors="strict"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("HUMAN_REVIEW_JSON_INVALID") from error
    if byte_count > _MAX_REVIEW_JSON_BYTES:
        raise ValidationError("HUMAN_REVIEW_JSON_LIMIT_EXCEEDED")
    return copied


def human_review_client_value_digest(value: Any) -> str:
    """Digest JSON exactly as the browser ``canonicalStrictJson`` contract.

    Durable content rows keep their existing ``content_contract_digest``.  This
    separate public echo digest is RFC 8785/I-JSON safe-integer canonical JSON
    followed by SHA-256, so a browser never needs Python serializer behavior.
    """

    return normalize_sha256(canonical_digest(bounded_review_json(value)))


def _required_text(value: Any, code: str, *, maximum: int = 2_000) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValidationError(code)
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValidationError(code) from error
    if len(encoded) > maximum:
        raise ValidationError(code)
    return value


def _safe_version(value: Any, code: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= MAX_SAFE_JSON_INTEGER - 1
    ):
        raise ValidationError(code)
    return int(value)


def _token_digest(value: Any, code: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValidationError(code)
    token = require_idempotency_key(value)
    if len(token.encode("utf-8")) < 16:
        raise ValidationError(code)
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


class HumanReviewWorkflow:
    """Transactional review state machine backed by ``IntakeStore`` SQLite."""

    def __init__(self, store: IntakeStore) -> None:
        self._store = store

    @staticmethod
    def _request_digest(value: str) -> str:
        return normalize_sha256(value)

    @staticmethod
    def _content_json(value: Any, code: str) -> tuple[Any, str, str]:
        try:
            copied = bounded_review_json(value)
            rendered = content_contract_json(copied)
            digest = normalize_sha256(content_contract_digest(copied))
        except ValidationError:
            raise
        except (TypeError, ValueError, UnicodeError, RecursionError) as error:
            raise ValidationError(code) from error
        return copied, rendered, digest

    @staticmethod
    def _decode_content(raw_json: Any, raw_digest: Any, code: str) -> Any:
        try:
            value = bounded_review_json(json.loads(raw_json))
            expected = normalize_sha256(raw_digest)
            if (
                content_contract_json(value) != raw_json
                or normalize_sha256(content_contract_digest(value)) != expected
            ):
                raise IntegrityError(code)
            return value
        except IntegrityError:
            raise
        except (TypeError, ValueError, UnicodeError, RecursionError, ValidationError) as error:
            raise IntegrityError(code) from error

    @staticmethod
    def _scoped_task(
        connection: sqlite3.Connection,
        context: TenantContext,
        task_id: str,
    ) -> sqlite3.Row:
        safe_task_id = require_resource_id(task_id, "task_id")
        row = connection.execute(
            """SELECT * FROM human_review_tasks
                WHERE tenant_id=? AND project_id=? AND task_id=?""",
            (context.tenant_id, context.project_id, safe_task_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise NotFoundError("HUMAN_REVIEW_TASK_NOT_FOUND")
        return row

    @staticmethod
    def _scoped_propagation(
        connection: sqlite3.Connection,
        context: TenantContext,
        propagation_id: str,
    ) -> sqlite3.Row:
        safe_id = require_resource_id(propagation_id, "propagation_id")
        row = connection.execute(
            """SELECT * FROM human_review_propagation_tasks
                WHERE tenant_id=? AND project_id=? AND propagation_id=?""",
            (context.tenant_id, context.project_id, safe_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise NotFoundError("HUMAN_REVIEW_PROPAGATION_NOT_FOUND")
        return row

    @staticmethod
    def _scoped_reservation_by_decision(
        connection: sqlite3.Connection,
        context: TenantContext,
        decision_id: str,
    ) -> sqlite3.Row:
        safe_id = require_resource_id(decision_id, "decision_id")
        row = connection.execute(
            """SELECT * FROM human_review_target_head_reservations
                WHERE tenant_id=? AND project_id=? AND decision_id=?""",
            (context.tenant_id, context.project_id, safe_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_MISSING")
        return row

    @classmethod
    def _reservation_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        code = "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CORRUPT"
        try:
            reservation_id = require_resource_id(row["reservation_id"], "reservation_id")
            tenant_id = require_resource_id(row["tenant_id"], "tenant_id")
            project_id = require_resource_id(row["project_id"], "project_id")
            asset_id = require_resource_id(row["asset_id"], "asset_id")
            asset_version = _safe_version(row["asset_version"], code)
            asset_content_digest = normalize_sha256(row["asset_content_digest"])
            asset_sha256 = normalize_sha256(row["asset_sha256"])
            target_kind = ReviewTargetKind(row["target_kind"]).value
            target_digest = normalize_sha256(row["target_digest"])
            snapshot_id = require_resource_id(row["snapshot_id"], "snapshot_id")
            snapshot_digest = normalize_sha256(row["snapshot_digest"])
            reserved_head_version = _safe_version(row["reserved_head_version"], code)
            reserved_head_value_digest = normalize_sha256(
                row["reserved_head_value_digest"]
            )
            task_id = require_resource_id(row["task_id"], "task_id")
            decision_id = require_resource_id(row["decision_id"], "decision_id")
            decision_action = ReviewDecisionAction(row["decision_action"])
            if decision_action not in {
                ReviewDecisionAction.APPROVE,
                ReviewDecisionAction.REVERT,
            }:
                raise IntegrityError(code)
            correction_version = _safe_version(row["correction_version"], code)
            correction_digest = normalize_sha256(row["correction_digest"])
            source_digest = normalize_sha256(row["source_digest"])
            source_ref_digest = normalize_sha256(row["source_ref_digest"])
            parent_reservation_id = (
                require_resource_id(row["parent_reservation_id"], "reservation_id")
                if row["parent_reservation_id"] is not None
                else None
            )
            reservation_fence = _safe_version(row["reservation_fence"], code)
            binding_digest = normalize_sha256(row["binding_digest"])
            state = ReviewHeadReservationState(row["state"])
            state_version = _safe_version(row["state_version"], code)
            materialized_head_version = (
                _safe_version(row["materialized_head_version"], code)
                if row["materialized_head_version"] is not None
                else None
            )
            failure_code = (
                require_resource_id(row["failure_code"], "failure_code")
                if row["failure_code"] is not None
                else None
            )
            created_at = row["created_at"]
            updated_at = row["updated_at"]
            completed_at = row["completed_at"]
            timestamps = [created_at, updated_at]
            if completed_at is not None:
                timestamps.append(completed_at)
            parsed = [datetime.fromisoformat(value) for value in timestamps]
            if any(
                value.tzinfo is None
                or value.utcoffset() is None
                or value.isoformat() != rendered
                for value, rendered in zip(parsed, timestamps, strict=True)
            ):
                raise IntegrityError(code)
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        if (
            reservation_fence != reserved_head_version
            or updated_at < created_at
            or (completed_at is not None and completed_at < updated_at)
            or (
                decision_action is ReviewDecisionAction.APPROVE
                and parent_reservation_id is not None
            )
            or (
                decision_action is ReviewDecisionAction.REVERT
                and parent_reservation_id is None
            )
            or (
                state in _RESERVATION_TERMINAL_STATES
                and completed_at is None
            )
            or (
                state not in _RESERVATION_TERMINAL_STATES
                and completed_at is not None
            )
            or (
                state in {
                    ReviewHeadReservationState.APPLIED,
                    ReviewHeadReservationState.REVERTED,
                }
                and materialized_head_version != reserved_head_version + 1
            )
            or (
                state not in {
                    ReviewHeadReservationState.APPLIED,
                    ReviewHeadReservationState.REVERTED,
                }
                and materialized_head_version is not None
            )
            or (state is ReviewHeadReservationState.FAILED) != (failure_code is not None)
            or (
                state is ReviewHeadReservationState.APPLIED
                and decision_action is not ReviewDecisionAction.APPROVE
            )
            or (
                state is ReviewHeadReservationState.REVERTED
                and decision_action is not ReviewDecisionAction.REVERT
            )
        ):
            raise IntegrityError(code)
        binding = {
            "schema_version": "human-review-target-head-reservation-binding-v1",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "asset_id": asset_id,
            "asset_version": asset_version,
            "asset_content_digest": f"sha256:{asset_content_digest}",
            "asset_sha256": f"sha256:{asset_sha256}",
            "target_kind": target_kind,
            "target_digest": f"sha256:{target_digest}",
            "snapshot_id": snapshot_id,
            "snapshot_digest": f"sha256:{snapshot_digest}",
            "reserved_head_version": reserved_head_version,
            "reserved_head_value_digest": f"sha256:{reserved_head_value_digest}",
            "task_id": task_id,
            "decision_id": decision_id,
            "decision_action": decision_action.value,
            "correction_version": correction_version,
            "correction_digest": f"sha256:{correction_digest}",
            "source_digest": f"sha256:{source_digest}",
            "source_ref_digest": f"sha256:{source_ref_digest}",
            "parent_reservation_id": parent_reservation_id,
            "reservation_fence": reservation_fence,
        }
        expected_binding_digest = normalize_sha256(canonical_digest(binding))
        expected_reservation_id = (
            "review-reservation-" + expected_binding_digest[:32]
        )
        if (
            not hmac.compare_digest(binding_digest, expected_binding_digest)
            or reservation_id != expected_reservation_id
        ):
            raise IntegrityError(code)
        return {
            "schema_version": "human-review-target-head-reservation-v1",
            "reservation_id": reservation_id,
            **{key: value for key, value in binding.items() if key != "schema_version"},
            "binding_digest": f"sha256:{binding_digest}",
            "state": state.value,
            "state_version": state_version,
            "materialized_head_version": materialized_head_version,
            "failure_code": failure_code,
            "created_at": created_at,
            "updated_at": updated_at,
            "completed_at": completed_at,
        }

    @classmethod
    def _task_version(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        task_id: str,
    ) -> int:
        return int(cls._scoped_task(connection, context, task_id)["version"])

    @classmethod
    def _task_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        target = cls._decode_content(
            row["target_json"], row["target_digest"], "HUMAN_REVIEW_TASK_CORRUPT"
        )
        original = cls._decode_content(
            row["original_value_json"],
            row["original_value_digest"],
            "HUMAN_REVIEW_TASK_CORRUPT",
        )
        source_ref = cls._decode_content(
            row["source_ref_json"],
            row["source_ref_digest"],
            "HUMAN_REVIEW_TASK_CORRUPT",
        )
        try:
            state = ReviewTaskState(row["state"]).value
            target_kind = ReviewTargetKind(row["target_kind"]).value
            source_digest = normalize_sha256(row["source_digest"])
            current_digest = (
                normalize_sha256(row["current_correction_digest"])
                if row["current_correction_digest"] is not None
                else None
            )
            effective_digest = (
                normalize_sha256(row["effective_digest"])
                if row["effective_digest"] is not None
                else None
            )
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_TASK_CORRUPT") from error
        return {
            "task_id": row["task_id"],
            "tenant_id": row["tenant_id"],
            "project_id": row["project_id"],
            "asset_id": row["asset_id"],
            "target_kind": target_kind,
            "target": target,
            "original_value": original,
            "source_digest": f"sha256:{source_digest}",
            "source_ref": source_ref,
            "confidence": float(row["confidence"]),
            "reason": row["reason"],
            "state": state,
            "current_correction_version": int(row["current_correction_version"]),
            "current_correction_digest": (
                f"sha256:{current_digest}" if current_digest is not None else None
            ),
            "effective_version": int(row["effective_version"]),
            "effective_digest": (
                f"sha256:{effective_digest}" if effective_digest is not None else None
            ),
            "claim_actor_id": row["claim_actor_id"],
            "claim_fence": int(row["claim_fence"]),
            "claim_expires_at": row["claim_expires_at"],
            "version": int(row["version"]),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "closed_at": row["closed_at"],
        }

    @staticmethod
    def _task_summary(row: sqlite3.Row) -> dict[str, Any]:
        """Materialize the fixed, bounded list contract without large JSON values."""

        try:
            task_id = require_resource_id(row["task_id"], "task_id")
            asset_id = require_resource_id(row["asset_id"], "asset_id")
            target_kind = ReviewTargetKind(row["target_kind"]).value
            state = ReviewTaskState(row["state"]).value
            source_digest = normalize_sha256(row["source_digest"])
            current_digest = (
                normalize_sha256(row["current_correction_digest"])
                if row["current_correction_digest"] is not None
                else None
            )
            effective_digest = (
                normalize_sha256(row["effective_digest"])
                if row["effective_digest"] is not None
                else None
            )
            confidence = float(row["confidence"])
            reason = _required_text(
                row["reason"], "HUMAN_REVIEW_TASK_CORRUPT", maximum=2_000
            )
            claim_actor_id = (
                require_actor_id(row["claim_actor_id"])
                if row["claim_actor_id"] is not None
                else None
            )
            current_version = _safe_version(
                int(row["current_correction_version"]),
                "HUMAN_REVIEW_TASK_CORRUPT",
                allow_zero=True,
            )
            effective_version = _safe_version(
                int(row["effective_version"]),
                "HUMAN_REVIEW_TASK_CORRUPT",
                allow_zero=True,
            )
            claim_fence = _safe_version(
                int(row["claim_fence"]),
                "HUMAN_REVIEW_TASK_CORRUPT",
                allow_zero=True,
            )
            version = _safe_version(int(row["version"]), "HUMAN_REVIEW_TASK_CORRUPT")
            for timestamp_field in (
                "created_at",
                "updated_at",
                "claim_expires_at",
                "closed_at",
            ):
                timestamp = row[timestamp_field]
                if timestamp is not None:
                    parsed = datetime.fromisoformat(timestamp)
                    if parsed.tzinfo is None or parsed.isoformat() != timestamp:
                        raise ValueError(timestamp_field)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("confidence")
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_TASK_CORRUPT") from error
        return {
            "schema_version": "human-review-task-summary-v1",
            "task_id": task_id,
            "asset_id": asset_id,
            "target_kind": target_kind,
            "source_digest": f"sha256:{source_digest}",
            "confidence": confidence,
            "reason": reason,
            "state": state,
            "current_correction_version": current_version,
            "current_correction_digest": (
                f"sha256:{current_digest}" if current_digest is not None else None
            ),
            "effective_version": effective_version,
            "effective_digest": (
                f"sha256:{effective_digest}" if effective_digest is not None else None
            ),
            "claim_actor_id": claim_actor_id,
            "claim_fence": claim_fence,
            "claim_expires_at": row["claim_expires_at"],
            "version": version,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "closed_at": row["closed_at"],
        }

    @classmethod
    def _correction_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        code = "HUMAN_REVIEW_CORRECTION_VERSION_CORRUPT"
        try:
            target = bounded_review_json(json.loads(row["target_json"]), allow_none=False)
            if content_contract_json(target) != row["target_json"]:
                raise IntegrityError(code)
            original = cls._decode_content(
                row["original_value_json"], row["original_value_digest"], code
            )
            corrected = cls._decode_content(
                row["corrected_value_json"], row["corrected_value_digest"], code
            )
            correction_id = require_resource_id(row["correction_id"], "correction_id")
            tenant_id = require_resource_id(row["tenant_id"], "tenant_id")
            project_id = require_resource_id(row["project_id"], "project_id")
            task_id = require_resource_id(row["task_id"], "task_id")
            correction_version = _safe_version(row["correction_version"], code)
            parent_correction_version = _safe_version(
                row["parent_correction_version"], code, allow_zero=True
            )
            if correction_version != parent_correction_version + 1:
                raise IntegrityError(code)
            target_kind = ReviewTargetKind(row["target_kind"]).value
            source_digest = normalize_sha256(row["source_digest"])
            actor_id = require_actor_id(row["actor_id"])
            reason = _required_text(row["reason"], code, maximum=2_000)
            created_at = row["created_at"]
            if not isinstance(created_at, str):
                raise IntegrityError(code)
            parsed_created_at = datetime.fromisoformat(created_at)
            if parsed_created_at.tzinfo is None or parsed_created_at.isoformat() != created_at:
                raise IntegrityError(code)
        except IntegrityError:
            raise
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
            RecursionError,
            ValidationError,
        ) as error:
            raise IntegrityError(code) from error
        body = {
            "correction_id": correction_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "task_id": task_id,
            "correction_version": correction_version,
            "parent_correction_version": parent_correction_version,
            "target_kind": target_kind,
            "target": target,
            "original_value": original,
            "corrected_value": corrected,
            "source_digest": f"sha256:{source_digest}",
            "actor_id": actor_id,
            "reason": reason,
            "created_at": created_at,
        }
        try:
            expected = normalize_sha256(content_contract_digest(body))
            observed = normalize_sha256(row["correction_digest"])
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        if not hmac.compare_digest(expected, observed):
            raise IntegrityError(code)
        return {**body, "correction_digest": f"sha256:{observed}"}

    @classmethod
    def _decision_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        try:
            correction_digest = (
                normalize_sha256(row["correction_digest"])
                if row["correction_digest"] is not None
                else None
            )
            return {
                "decision_id": row["decision_id"],
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "task_id": row["task_id"],
                "decision_version": int(row["decision_version"]),
                "decision": ReviewDecisionAction(row["decision"]).value,
                "prior_state": ReviewTaskState(row["prior_state"]).value,
                "next_state": ReviewTaskState(row["next_state"]).value,
                "correction_version": row["correction_version"],
                "correction_digest": (
                    f"sha256:{correction_digest}" if correction_digest is not None else None
                ),
                "source_digest": f"sha256:{normalize_sha256(row['source_digest'])}",
                "actor_id": row["actor_id"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_DECISION_CORRUPT") from error

    @classmethod
    def _propagation_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        payload = cls._decode_content(
            row["payload_json"],
            row["payload_digest"],
            "HUMAN_REVIEW_PROPAGATION_CORRUPT",
        )
        result = None
        if row["result_json"] is not None:
            result = cls._decode_content(
                row["result_json"],
                row["result_digest"],
                "HUMAN_REVIEW_PROPAGATION_CORRUPT",
            )
        try:
            return {
                "propagation_id": row["propagation_id"],
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "task_id": row["task_id"],
                "decision_id": row["decision_id"],
                "correction_version": int(row["correction_version"]),
                "channel": row["channel"],
                "direction": ReviewPropagationDirection(row["direction"]).value,
                "payload": payload,
                "state": ReviewPropagationState(row["state"]).value,
                "claim_capability_id": row["claim_capability_id"],
                "claim_fence": int(row["claim_fence"]),
                "claim_expires_at": row["claim_expires_at"],
                "dispatch_started_at": row["dispatch_started_at"],
                "result": result,
                "failure_code": row["failure_code"],
                "reconciliation_required": bool(row["reconciliation_required"]),
                "version": int(row["version"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row["completed_at"],
                "reconciled_at": row["reconciled_at"],
            }
        except (TypeError, ValueError) as error:
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT") from error

    @classmethod
    def _propagation_summary(cls, row: sqlite3.Row) -> dict[str, Any]:
        payload = cls._decode_content(
            row["payload_json"],
            row["payload_digest"],
            "HUMAN_REVIEW_PROPAGATION_CORRUPT",
        )
        if not isinstance(payload, dict):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
        return {
            "propagation_id": row["propagation_id"],
            "task_id": row["task_id"],
            "decision_id": row["decision_id"],
            "correction_version": int(row["correction_version"]),
            "channel": row["channel"],
            "direction": ReviewPropagationDirection(row["direction"]).value,
            "payload_digest": f"sha256:{normalize_sha256(row['payload_digest'])}",
            "effective_value_digest": payload.get("effective_value_digest"),
            "state": ReviewPropagationState(row["state"]).value,
            "claim_fence": int(row["claim_fence"]),
            "claim_expires_at": row["claim_expires_at"],
            "dispatch_started_at": row["dispatch_started_at"],
            "failure_code": row["failure_code"],
            "reconciliation_required": bool(row["reconciliation_required"]),
            "version": int(row["version"]),
            "updated_at": row["updated_at"],
        }

    @classmethod
    def _receipt(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT * FROM human_review_operation_receipts
                WHERE tenant_id=? AND project_id=? AND actor_id=?
                  AND operation=? AND idempotency_key=?""",
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                operation,
                idempotency_key,
            ),
        ).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(row["request_digest"], request_digest):
            raise ConflictError("HUMAN_REVIEW_IDEMPOTENCY_CONFLICT")
        response = cls._decode_content(
            row["response_json"],
            row["response_digest"],
            "HUMAN_REVIEW_RECEIPT_CORRUPT",
        )
        if not isinstance(response, dict):
            raise IntegrityError("HUMAN_REVIEW_RECEIPT_CORRUPT")
        return response

    @classmethod
    def _record_receipt(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
        response: Mapping[str, Any],
    ) -> dict[str, Any]:
        copied, response_json, response_digest = cls._content_json(
            response, "HUMAN_REVIEW_RESPONSE_INVALID"
        )
        if not isinstance(copied, dict):
            raise IntegrityError("HUMAN_REVIEW_RESPONSE_INVALID")
        connection.execute(
            """INSERT INTO human_review_operation_receipts (
                tenant_id,project_id,actor_id,operation,idempotency_key,
                request_digest,response_json,response_digest,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                operation,
                idempotency_key,
                request_digest,
                response_json,
                response_digest,
                utc_now(),
            ),
        )
        return copied

    @classmethod
    def _audit(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        task_id: str,
        event_type: str,
        prior_state: str | None,
        next_state: str | None,
        task_version: int,
        details: Mapping[str, Any],
    ) -> str:
        copied, details_json, details_digest = cls._content_json(
            details, "HUMAN_REVIEW_AUDIT_INVALID"
        )
        audit_id = "review-audit-" + canonical_digest(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "task_id": task_id,
                "event_type": event_type,
                "actor_id": context.actor_id,
                "task_version": task_version,
                "details_digest": f"sha256:{details_digest}",
            }
        )[:32]
        connection.execute(
            """INSERT INTO human_review_audit_log (
                audit_id,tenant_id,project_id,task_id,event_type,actor_id,
                prior_state,next_state,task_version,details_json,details_digest,occurred_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                audit_id,
                context.tenant_id,
                context.project_id,
                task_id,
                event_type,
                context.actor_id,
                prior_state,
                next_state,
                task_version,
                details_json,
                details_digest,
                utc_now(),
            ),
        )
        if not isinstance(copied, dict):
            raise IntegrityError("HUMAN_REVIEW_AUDIT_INVALID")
        return audit_id

    @staticmethod
    def _validate_target(kind: ReviewTargetKind, value: Any) -> dict[str, Any]:
        target = bounded_review_json(value, allow_none=False)
        if not isinstance(target, dict):
            raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
        if kind is ReviewTargetKind.TEXT:
            if set(target) != {"path"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            _required_text(target["path"], "HUMAN_REVIEW_TARGET_INVALID", maximum=1_024)
        elif kind is ReviewTargetKind.SPEAKER:
            if set(target) != {"segment_id"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            require_resource_id(target["segment_id"], "segment_id")
        elif kind is ReviewTargetKind.TIME_RANGE:
            if set(target) != {"start_ms", "end_ms"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            start = _safe_version(target["start_ms"], "HUMAN_REVIEW_TARGET_INVALID", allow_zero=True)
            end = _safe_version(target["end_ms"], "HUMAN_REVIEW_TARGET_INVALID", allow_zero=True)
            if end < start:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
        elif kind is ReviewTargetKind.BBOX:
            if set(target) != {"page", "x", "y", "width", "height"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            _safe_version(target["page"], "HUMAN_REVIEW_TARGET_INVALID")
            for field in ("x", "y", "width", "height"):
                number = target[field]
                if (
                    isinstance(number, bool)
                    or not isinstance(number, (int, float))
                    or not math.isfinite(float(number))
                    or number < 0
                    or field in {"width", "height"} and number == 0
                ):
                    raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
        elif kind is ReviewTargetKind.TABLE:
            if set(target) != {"table_id", "row", "column"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            require_resource_id(target["table_id"], "table_id")
            _safe_version(target["row"], "HUMAN_REVIEW_TARGET_INVALID", allow_zero=True)
            _safe_version(target["column"], "HUMAN_REVIEW_TARGET_INVALID", allow_zero=True)
        elif kind is ReviewTargetKind.REQUIREMENT:
            if set(target) != {"requirement_id"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            require_resource_id(target["requirement_id"], "requirement_id")
        elif kind is ReviewTargetKind.CONFLICT:
            if set(target) != {"conflict_id"}:
                raise ValidationError("HUMAN_REVIEW_TARGET_INVALID")
            require_resource_id(target["conflict_id"], "conflict_id")
        return target

    @classmethod
    def _source_snapshot_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        target = cls._decode_content(
            row["target_json"], row["target_digest"],
            "HUMAN_REVIEW_SOURCE_SNAPSHOT_CORRUPT",
        )
        original = cls._decode_content(
            row["original_value_json"], row["original_value_digest"],
            "HUMAN_REVIEW_SOURCE_SNAPSHOT_CORRUPT",
        )
        provenance = cls._decode_content(
            row["provenance_json"], row["provenance_digest"],
            "HUMAN_REVIEW_SOURCE_SNAPSHOT_CORRUPT",
        )
        body = {
            "schema_version": "human-review-source-snapshot-v1",
            "snapshot_id": row["snapshot_id"],
            "tenant_id": row["tenant_id"],
            "project_id": row["project_id"],
            "asset_id": row["asset_id"],
            "asset_version": int(row["asset_version"]),
            "target_kind": ReviewTargetKind(row["target_kind"]).value,
            "target": target,
            "original_value": original,
            "confidence": float(row["confidence"]),
            "asset_sha256": f"sha256:{normalize_sha256(row['asset_sha256'])}",
            "source_digest": f"sha256:{normalize_sha256(row['source_digest'])}",
            "provenance": provenance,
            "producer_capability_id": row["producer_capability_id"],
            "producer_actor_id": row["producer_actor_id"],
            "idempotency_key": row["idempotency_key"],
            "request_digest": f"sha256:{normalize_sha256(row['request_digest'])}",
            "created_at": row["created_at"],
        }
        expected = normalize_sha256(content_contract_digest(body))
        observed = normalize_sha256(row["snapshot_digest"])
        if not hmac.compare_digest(expected, observed):
            raise IntegrityError("HUMAN_REVIEW_SOURCE_SNAPSHOT_CORRUPT")
        return {**body, "snapshot_digest": f"sha256:{observed}"}

    @staticmethod
    def _validate_source_provenance(value: Any) -> tuple[dict[str, Any], str, str]:
        provenance = bounded_review_json(value, allow_none=False)
        if not isinstance(provenance, dict) or set(provenance) != _SOURCE_PROVENANCE_FIELDS:
            raise ValidationError("HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID")
        if provenance.get("schema_version") != "human-review-source-provenance-v1":
            raise ValidationError("HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID")
        source_kind = provenance.get("source_kind")
        if source_kind not in _SOURCE_KINDS:
            raise ValidationError("HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID")
        raw_source_id = provenance.get("source_id")
        raw_source_digest = provenance.get("source_digest")
        if not isinstance(raw_source_id, str) or not isinstance(raw_source_digest, str):
            raise ValidationError("HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID")
        source_id = require_resource_id(raw_source_id, "source_id")
        producer_version = _required_text(
            provenance.get("producer_version"),
            "HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID",
            maximum=256,
        )
        try:
            source_digest = normalize_sha256(raw_source_digest)
        except ValidationError as error:
            raise ValidationError("HUMAN_REVIEW_SOURCE_PROVENANCE_INVALID") from error
        normalized = {
            "schema_version": "human-review-source-provenance-v1",
            "source_kind": source_kind,
            "source_id": source_id,
            "source_digest": f"sha256:{source_digest}",
            "producer_version": producer_version,
        }
        return normalized, source_digest, content_contract_json(normalized)

    def register_source_producer_capability(
        self,
        context: TenantContext,
        *,
        producer_id: str,
        capability_token: str,
        source_kinds: Sequence[str],
        expires_at: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_producer = require_actor_id(producer_id)
        _token, token_digest = _token_digest(
            capability_token, "HUMAN_REVIEW_SOURCE_PRODUCER_TOKEN_INVALID"
        )
        if (
            isinstance(source_kinds, (str, bytes))
            or not isinstance(source_kinds, Sequence)
            or not source_kinds
            or any(not isinstance(kind, str) for kind in source_kinds)
        ):
            raise ValidationError("HUMAN_REVIEW_SOURCE_KINDS_INVALID")
        safe_source_kinds = tuple(sorted(set(source_kinds)))
        if (
            len(safe_source_kinds) != len(source_kinds)
            or not set(safe_source_kinds) <= _SOURCE_KINDS
        ):
            raise ValidationError("HUMAN_REVIEW_SOURCE_KINDS_INVALID")
        safe_expiry = self._parse_future_expiry(
            expires_at, "HUMAN_REVIEW_SOURCE_PRODUCER_EXPIRY_INVALID"
        )
        safe_key = require_idempotency_key(idempotency_key)
        caller_request_digest = self._request_digest(request_digest)
        kinds_value = list(safe_source_kinds)
        _kinds_copy, kinds_json, kinds_digest = self._content_json(
            kinds_value, "HUMAN_REVIEW_SOURCE_KINDS_INVALID"
        )
        safe_request_digest = canonical_digest(
            {
                "schema_version": "human-review-source-producer-register-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "producer_id": safe_producer,
                "source_kinds_digest": f"sha256:{kinds_digest}",
                "expires_at": safe_expiry,
                "caller_request_digest": f"sha256:{caller_request_digest}",
            }
        )
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.ADMIN)
            replay = self._receipt(
                connection,
                context,
                operation="register_source_producer",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            existing = connection.execute(
                """SELECT * FROM human_review_source_producer_capabilities
                    WHERE tenant_id=? AND project_id=? AND producer_id=?
                      AND token_digest=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_producer,
                    token_digest,
                ),
            ).fetchone()
            if existing is not None:
                if (
                    existing["source_kinds_json"] != kinds_json
                    or existing["source_kinds_digest"] != kinds_digest
                    or existing["expires_at"] != safe_expiry
                    or existing["revoked_at"] is not None
                ):
                    raise ConflictError(
                        "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_CONFLICT"
                    )
                capability_id = existing["capability_id"]
            else:
                capability_id = "review-source-producer-" + canonical_digest(
                    {
                        "tenant_id": context.tenant_id,
                        "project_id": context.project_id,
                        "producer_id": safe_producer,
                        "token_digest": f"sha256:{token_digest}",
                    }
                )[:32]
                now = utc_now()
                connection.execute(
                    """INSERT INTO human_review_source_producer_capabilities (
                        capability_id,tenant_id,project_id,producer_id,token_digest,
                        source_kinds_json,source_kinds_digest,expires_at,revoked_at,
                        version,created_by,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,NULL,1,?,?)""",
                    (
                        capability_id,
                        context.tenant_id,
                        context.project_id,
                        safe_producer,
                        token_digest,
                        kinds_json,
                        kinds_digest,
                        safe_expiry,
                        context.actor_id,
                        now,
                    ),
                )
            response = {
                "capability": {
                    "capability_id": capability_id,
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "producer_id": safe_producer,
                    "source_kinds": kinds_value,
                    "expires_at": safe_expiry,
                    "revoked": False,
                }
            }
            self._store._event(
                connection,
                context,
                "human_review_source_producer_capability",
                capability_id,
                "human_review.source_producer.registered",
                f"human-review-source-producer:{context.actor_id}:{safe_key}",
                {
                    "capability_id": capability_id,
                    "producer_id": safe_producer,
                    "source_kinds": kinds_value,
                    "expires_at": safe_expiry,
                    "request_digest": f"sha256:{safe_request_digest}",
                },
            )
            return self._record_receipt(
                connection,
                context,
                operation="register_source_producer",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def revoke_source_producer_capability(
        self,
        context: TenantContext,
        *,
        capability_id: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_id = require_resource_id(capability_id, "capability_id")
        safe_version = _safe_version(
            expected_version, "HUMAN_REVIEW_EXPECTED_VERSION_INVALID"
        )
        safe_reason = _required_text(reason, "HUMAN_REVIEW_REASON_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        caller_request_digest = self._request_digest(request_digest)
        safe_request_digest = canonical_digest(
            {
                "schema_version": "human-review-source-producer-revoke-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "capability_id": safe_id,
                "expected_version": safe_version,
                "reason": safe_reason,
                "caller_request_digest": f"sha256:{caller_request_digest}",
            }
        )
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.ADMIN)
            replay = self._receipt(
                connection,
                context,
                operation="revoke_source_producer",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            row = connection.execute(
                """SELECT * FROM human_review_source_producer_capabilities
                    WHERE tenant_id=? AND project_id=? AND capability_id=?""",
                (context.tenant_id, context.project_id, safe_id),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_NOT_FOUND"
                )
            if int(row["version"]) != safe_version:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_VERSION_CONFLICT"
                )
            now = utc_now()
            if row["revoked_at"] is None:
                changed = connection.execute(
                    """UPDATE human_review_source_producer_capabilities
                          SET revoked_at=?,version=version+1
                        WHERE tenant_id=? AND project_id=? AND capability_id=?
                          AND version=? AND revoked_at IS NULL""",
                    (
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_id,
                        safe_version,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError(
                        "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_VERSION_CONFLICT"
                    )
            response = {
                "capability_id": safe_id,
                "revoked": True,
                "revoked_at": row["revoked_at"] or now,
                "reason": safe_reason,
            }
            self._store._event(
                connection,
                context,
                "human_review_source_producer_capability",
                safe_id,
                "human_review.source_producer.revoked",
                f"human-review-source-producer-revoke:{context.actor_id}:{safe_key}",
                {
                    "capability_id": safe_id,
                    "producer_id": row["producer_id"],
                    "revoked_at": row["revoked_at"] or now,
                    "reason": safe_reason,
                    "request_digest": f"sha256:{safe_request_digest}",
                },
            )
            return self._record_receipt(
                connection,
                context,
                operation="revoke_source_producer",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def register_source_snapshot(
        self,
        context: TenantContext,
        *,
        asset_id: str,
        expected_asset_version: int,
        target_kind: str,
        target: Any,
        original_value: Any,
        confidence: float,
        provenance: Any,
        capability_id: str,
        capability_token: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_asset_id = require_resource_id(asset_id, "asset_id")
        safe_asset_version = _safe_version(
            expected_asset_version, "HUMAN_REVIEW_EXPECTED_ASSET_VERSION_INVALID"
        )
        try:
            safe_kind = ReviewTargetKind(target_kind)
        except (TypeError, ValueError) as error:
            raise ValidationError("HUMAN_REVIEW_TARGET_KIND_INVALID") from error
        safe_target = self._validate_target(safe_kind, target)
        _target_copy, target_json, target_digest = self._content_json(
            safe_target, "HUMAN_REVIEW_TARGET_INVALID"
        )
        safe_original, original_json, original_digest = self._content_json(
            original_value, "HUMAN_REVIEW_ORIGINAL_VALUE_INVALID"
        )
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            raise ValidationError("HUMAN_REVIEW_CONFIDENCE_INVALID")
        safe_provenance, source_digest, provenance_json = self._validate_source_provenance(
            provenance
        )
        provenance_digest = normalize_sha256(content_contract_digest(safe_provenance))
        safe_capability_id = require_resource_id(capability_id, "capability_id")
        safe_key = require_idempotency_key(idempotency_key)
        caller_request_digest = self._request_digest(request_digest)
        safe_request_digest = canonical_digest(
            {
                "schema_version": "human-review-source-register-receipt-v2",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "asset_id": safe_asset_id,
                "expected_asset_version": safe_asset_version,
                "target_kind": safe_kind.value,
                "target_digest": f"sha256:{target_digest}",
                "original_value_digest": f"sha256:{original_digest}",
                "confidence": float(confidence),
                "source_digest": f"sha256:{source_digest}",
                "provenance_digest": f"sha256:{provenance_digest}",
                "producer_capability_id": safe_capability_id,
                "caller_request_digest": f"sha256:{caller_request_digest}",
            }
        )
        with self._store.transaction() as connection:
            producer_capability = self._source_producer_identity(
                connection,
                context,
                capability_id=safe_capability_id,
                capability_token=capability_token,
                source_kind=safe_provenance["source_kind"],
            )
            replay = self._receipt(
                connection,
                context,
                operation="source_register",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            self._require_source_producer_active(producer_capability)
            asset = self._store._scoped_asset(connection, context, safe_asset_id)
            self._store._require_human_review_asset_state(asset)
            if int(asset["version"]) != safe_asset_version:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_ASSET_VERSION_DRIFT",
                    details={
                        "expected_version": safe_asset_version,
                        "actual_version": int(asset["version"]),
                    },
                )
            asset_sha256 = normalize_sha256(asset["sha256"])
            existing = connection.execute(
                """SELECT snapshot_id,snapshot_digest
                     FROM human_review_source_snapshots
                    WHERE tenant_id=? AND project_id=? AND asset_id=?
                      AND asset_version=? AND target_kind=? AND target_digest=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_asset_version,
                    safe_kind.value,
                    target_digest,
                ),
            ).fetchone()
            if existing is not None:
                raise ConflictError("HUMAN_REVIEW_SOURCE_SNAPSHOT_CONFLICT")
            created_at = utc_now()
            snapshot_id = "review-source-" + canonical_digest(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "asset_id": safe_asset_id,
                    "asset_version": safe_asset_version,
                    "target_kind": safe_kind.value,
                    "target_digest": f"sha256:{target_digest}",
                    "source_digest": f"sha256:{source_digest}",
                    "request_digest": f"sha256:{safe_request_digest}",
                }
            )[:32]
            snapshot_body = {
                "schema_version": "human-review-source-snapshot-v1",
                "snapshot_id": snapshot_id,
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "asset_id": safe_asset_id,
                "asset_version": safe_asset_version,
                "target_kind": safe_kind.value,
                "target": safe_target,
                "original_value": safe_original,
                "confidence": float(confidence),
                "asset_sha256": f"sha256:{asset_sha256}",
                "source_digest": f"sha256:{source_digest}",
                "provenance": safe_provenance,
                "producer_capability_id": safe_capability_id,
                "producer_actor_id": context.actor_id,
                "idempotency_key": safe_key,
                "request_digest": f"sha256:{safe_request_digest}",
                "created_at": created_at,
            }
            snapshot_digest = normalize_sha256(content_contract_digest(snapshot_body))
            connection.execute(
                """INSERT INTO human_review_source_snapshots (
                    snapshot_id,tenant_id,project_id,asset_id,asset_version,target_kind,
                    target_json,target_digest,original_value_json,original_value_digest,
                    confidence,asset_sha256,source_digest,provenance_json,provenance_digest,
                    producer_capability_id,producer_actor_id,idempotency_key,request_digest,
                    snapshot_digest,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_asset_version,
                    safe_kind.value,
                    target_json,
                    target_digest,
                    original_json,
                    original_digest,
                    float(confidence),
                    asset_sha256,
                    source_digest,
                    provenance_json,
                    provenance_digest,
                    safe_capability_id,
                    context.actor_id,
                    safe_key,
                    safe_request_digest,
                    snapshot_digest,
                    created_at,
                ),
            )
            connection.execute(
                """INSERT INTO human_review_target_heads (
                    tenant_id,project_id,asset_id,asset_version,target_kind,target_json,
                    target_digest,base_snapshot_id,current_value_json,current_value_digest,
                    source_digest,provenance_digest,source_decision_id,correction_version,
                    direction,version,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,0,'SNAPSHOT',1,?)""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_asset_version,
                    safe_kind.value,
                    target_json,
                    target_digest,
                    snapshot_id,
                    original_json,
                    original_digest,
                    source_digest,
                    provenance_digest,
                    created_at,
                ),
            )
            self._store._event(
                connection,
                context,
                "human_review_source_snapshot",
                snapshot_id,
                "human_review.source.registered",
                f"human-review-source:{context.actor_id}:{safe_key}",
                {
                    "snapshot_id": snapshot_id,
                    "asset_id": safe_asset_id,
                    "asset_version": safe_asset_version,
                    "target_kind": safe_kind.value,
                    "target_digest": f"sha256:{target_digest}",
                    "original_value_digest": f"sha256:{original_digest}",
                    "source_digest": f"sha256:{source_digest}",
                    "provenance_digest": f"sha256:{provenance_digest}",
                    "snapshot_digest": f"sha256:{snapshot_digest}",
                    "producer_capability_id": safe_capability_id,
                    "producer_actor_id": context.actor_id,
                    "request_digest": f"sha256:{safe_request_digest}",
                },
            )
            response = {
                "snapshot": {**snapshot_body, "snapshot_digest": f"sha256:{snapshot_digest}"},
                "head": {
                    "asset_id": safe_asset_id,
                    "asset_version": safe_asset_version,
                    "target_kind": safe_kind.value,
                    "target_digest": f"sha256:{target_digest}",
                    "current_value_digest": f"sha256:{original_digest}",
                    "direction": "SNAPSHOT",
                    "version": 1,
                },
            }
            return self._record_receipt(
                connection,
                context,
                operation="source_register",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @classmethod
    def _authoritative_head(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        asset_id: str,
        asset_version: int,
        target_kind: ReviewTargetKind,
        target_json: str,
        target_digest: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row, Any]:
        head = connection.execute(
            """SELECT * FROM human_review_target_heads
                WHERE tenant_id=? AND project_id=? AND asset_id=? AND asset_version=?
                  AND target_kind=? AND target_digest=?""",
            (
                context.tenant_id,
                context.project_id,
                asset_id,
                asset_version,
                target_kind.value,
                target_digest,
            ),
        ).fetchone()
        if head is None:
            if target_kind in {ReviewTargetKind.REQUIREMENT, ReviewTargetKind.CONFLICT}:
                raise ConflictError("REQUIRES_SOURCE_PRODUCER")
            raise ConflictError("HUMAN_REVIEW_TARGET_UNRESOLVABLE")
        if head["target_json"] != target_json:
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_CORRUPT")
        snapshot = connection.execute(
            """SELECT * FROM human_review_source_snapshots
                WHERE tenant_id=? AND project_id=? AND snapshot_id=?""",
            (context.tenant_id, context.project_id, head["base_snapshot_id"]),
        ).fetchone()
        if snapshot is None:
            raise IntegrityError("HUMAN_REVIEW_SOURCE_SNAPSHOT_MISSING")
        cls._source_snapshot_payload(snapshot)
        current_value = cls._decode_content(
            head["current_value_json"],
            head["current_value_digest"],
            "HUMAN_REVIEW_TARGET_HEAD_CORRUPT",
        )
        return head, snapshot, current_value

    @classmethod
    def _source_head_documents(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        asset: sqlite3.Row,
        current: Mapping[str, Any],
        head: sqlite3.Row,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return bounded summary and full detail after exact lineage validation."""

        code = "HUMAN_REVIEW_SOURCE_HEAD_CORRUPT"
        try:
            asset_id = require_resource_id(head["asset_id"], "asset_id")
            content_version = _safe_version(head["asset_version"], code)
            target_kind = ReviewTargetKind(head["target_kind"])
            target = cls._decode_content(
                head["target_json"], head["target_digest"], code
            )
            target = cls._validate_target(target_kind, target)
            target_digest = normalize_sha256(head["target_digest"])
            current_value = cls._decode_content(
                head["current_value_json"], head["current_value_digest"], code
            )
            head_value_digest = normalize_sha256(head["current_value_digest"])
            source_digest = normalize_sha256(head["source_digest"])
            provenance_digest = normalize_sha256(head["provenance_digest"])
            snapshot_id = require_resource_id(
                head["base_snapshot_id"], "snapshot_id"
            )
            head_version = _safe_version(head["version"], code)
            head_correction_version = _safe_version(
                head["correction_version"], code, allow_zero=True
            )
            head_direction = str(head["direction"])
            if head_direction not in {"SNAPSHOT", "APPLY", "REVERT"}:
                raise IntegrityError(code)
            updated_at = str(head["updated_at"])
            parsed_updated_at = datetime.fromisoformat(updated_at)
            if (
                parsed_updated_at.tzinfo is None
                or parsed_updated_at.utcoffset() is None
                or parsed_updated_at.isoformat() != updated_at
            ):
                raise IntegrityError(code)
            asset_sha256 = normalize_sha256(asset["sha256"])
            content_digest = normalize_sha256(current["digest"])
            if (
                head["tenant_id"] != context.tenant_id
                or head["project_id"] != context.project_id
                or asset_id != asset["asset_id"]
                or content_version != int(asset["version"])
                or current.get("content_id") != asset_id
                or current.get("version") != content_version
                or current.get("tenant_id") != context.tenant_id
                or current.get("project_id") != context.project_id
            ):
                raise IntegrityError(code)
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error

        snapshot = connection.execute(
            """SELECT * FROM human_review_source_snapshots
                WHERE tenant_id=? AND project_id=? AND snapshot_id=?""",
            (context.tenant_id, context.project_id, snapshot_id),
        ).fetchone()
        if snapshot is None:
            raise IntegrityError("HUMAN_REVIEW_SOURCE_SNAPSHOT_MISSING")
        snapshot_payload = cls._source_snapshot_payload(snapshot)
        snapshot_digest = normalize_sha256(snapshot["snapshot_digest"])
        try:
            validated_provenance, provenance_source_digest, provenance_json = (
                cls._validate_source_provenance(snapshot_payload["provenance"])
            )
            confidence = float(snapshot["confidence"])
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise IntegrityError(code)
            if (
                snapshot["asset_id"] != asset_id
                or int(snapshot["asset_version"]) != content_version
                or snapshot["target_kind"] != target_kind.value
                or snapshot["target_json"] != head["target_json"]
                or not hmac.compare_digest(
                    normalize_sha256(snapshot["target_digest"]), target_digest
                )
                or not hmac.compare_digest(
                    normalize_sha256(snapshot["asset_sha256"]), asset_sha256
                )
                or not hmac.compare_digest(
                    normalize_sha256(snapshot["source_digest"]), source_digest
                )
                or not hmac.compare_digest(
                    normalize_sha256(snapshot["provenance_digest"]),
                    provenance_digest,
                )
                or validated_provenance != snapshot_payload["provenance"]
                or provenance_json != snapshot["provenance_json"]
                or not hmac.compare_digest(
                    provenance_source_digest, source_digest
                )
                or snapshot_payload["snapshot_digest"]
                != f"sha256:{snapshot_digest}"
            ):
                raise IntegrityError(code)
        except IntegrityError:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error

        capability = connection.execute(
            """SELECT * FROM human_review_source_producer_capabilities
                WHERE tenant_id=? AND project_id=? AND capability_id=?""",
            (
                context.tenant_id,
                context.project_id,
                snapshot["producer_capability_id"],
            ),
        ).fetchone()
        if capability is None:
            raise IntegrityError(code)
        try:
            source_kinds = cls._decode_content(
                capability["source_kinds_json"],
                capability["source_kinds_digest"],
                code,
            )
            if (
                not isinstance(source_kinds, list)
                or not source_kinds
                or any(not isinstance(value, str) for value in source_kinds)
                or source_kinds != sorted(set(source_kinds))
                or not set(source_kinds) <= _SOURCE_KINDS
            ):
                raise IntegrityError(code)
            capability_created_at = datetime.fromisoformat(capability["created_at"])
            capability_expires_at = datetime.fromisoformat(capability["expires_at"])
            snapshot_created_at = datetime.fromisoformat(snapshot["created_at"])
            capability_revoked_at = (
                datetime.fromisoformat(capability["revoked_at"])
                if capability["revoked_at"] is not None
                else None
            )
            timestamps = [
                (capability_created_at, capability["created_at"]),
                (capability_expires_at, capability["expires_at"]),
                (snapshot_created_at, snapshot["created_at"]),
            ]
            if capability_revoked_at is not None:
                timestamps.append((capability_revoked_at, capability["revoked_at"]))
            if any(
                parsed.tzinfo is None
                or parsed.utcoffset() is None
                or parsed.isoformat() != rendered
                for parsed, rendered in timestamps
            ):
                raise IntegrityError(code)
        except IntegrityError:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        if (
            capability["producer_id"] != snapshot["producer_actor_id"]
            or capability["capability_id"] != snapshot["producer_capability_id"]
            or validated_provenance["source_kind"] not in source_kinds
            or snapshot_created_at < capability_created_at
            or snapshot_created_at >= capability_expires_at
            or (
                capability_revoked_at is not None
                and snapshot_created_at > capability_revoked_at
            )
        ):
            raise IntegrityError(code)

        source_decision_id = head["source_decision_id"]
        if head_direction == "SNAPSHOT":
            if (
                source_decision_id is not None
                or head_correction_version != 0
                or head["current_value_json"] != snapshot["original_value_json"]
                or not hmac.compare_digest(
                    head_value_digest,
                    normalize_sha256(snapshot["original_value_digest"]),
                )
            ):
                raise IntegrityError(code)
        else:
            try:
                safe_decision_id = require_resource_id(
                    source_decision_id, "decision_id"
                )
            except (TypeError, ValidationError) as error:
                raise IntegrityError(code) from error
            decision = connection.execute(
                """SELECT * FROM human_review_decisions
                    WHERE tenant_id=? AND project_id=? AND decision_id=?""",
                (context.tenant_id, context.project_id, safe_decision_id),
            ).fetchone()
            task = (
                connection.execute(
                    """SELECT * FROM human_review_tasks
                        WHERE tenant_id=? AND project_id=? AND task_id=?""",
                    (context.tenant_id, context.project_id, decision["task_id"]),
                ).fetchone()
                if decision is not None
                else None
            )
            expected_decision = "APPROVE" if head_direction == "APPLY" else "REVERT"
            try:
                if decision is None or task is None:
                    raise IntegrityError(code)
                decision_correction_version = _safe_version(
                    decision["correction_version"], code
                )
                decision_correction_digest = normalize_sha256(
                    decision["correction_digest"]
                )
                task_target_digest = normalize_sha256(task["target_digest"])
                task_source_digest = normalize_sha256(task["source_digest"])
                decision_source_digest = normalize_sha256(
                    decision["source_digest"]
                )
                task_source_ref = cls._decode_content(
                    task["source_ref_json"], task["source_ref_digest"], code
                )
                task_effective_version = _safe_version(
                    task["effective_version"], code, allow_zero=True
                )
                task_effective_digest = normalize_sha256(task["effective_digest"])
                if not isinstance(task_source_ref, dict):
                    raise IntegrityError(code)
            except IntegrityError:
                raise
            except (KeyError, TypeError, ValueError, ValidationError) as error:
                raise IntegrityError(code) from error
            if (
                decision["decision"] != expected_decision
                or task["asset_id"] != asset_id
                or task["target_kind"] != target_kind.value
                or task["target_json"] != head["target_json"]
                or not hmac.compare_digest(task_target_digest, target_digest)
                or not hmac.compare_digest(
                    decision_source_digest, task_source_digest
                )
                or set(task_source_ref) != _SOURCE_REF_V2_FIELDS
                or task_source_ref.get("schema_version")
                != "human-review-source-ref-v2"
                or task_source_ref.get("content_id") != asset_id
                or task_source_ref.get("content_version") != content_version
                or task_source_ref.get("asset_sha256")
                != f"sha256:{asset_sha256}"
                or task_source_ref.get("target_kind") != target_kind.value
                or task_source_ref.get("target_digest")
                != f"sha256:{target_digest}"
                or task_source_ref.get("snapshot_id") != snapshot_id
                or task_source_ref.get("snapshot_digest")
                != f"sha256:{snapshot_digest}"
                or task_source_ref.get("source_digest")
                != f"sha256:{source_digest}"
                or task_source_ref.get("provenance_digest")
                != f"sha256:{provenance_digest}"
                or task_source_ref.get("original_value_digest_contract")
                != CANONICAL_JSON_SHA256_CONTRACT
                or task_effective_version != head_correction_version
                or not hmac.compare_digest(
                    task_effective_digest, head_value_digest
                )
                or (
                    head_direction == "APPLY"
                    and head_correction_version != decision_correction_version
                )
                or (
                    head_direction == "REVERT"
                    and head_correction_version >= decision_correction_version
                )
            ):
                raise IntegrityError(code)

            reservation = cls._decision_reservation(
                connection,
                context,
                decision_id=safe_decision_id,
            )
            reservation_payload = cls._reservation_payload(reservation)
            expected_reservation_state = (
                ReviewHeadReservationState.APPLIED.value
                if head_direction == ReviewPropagationDirection.APPLY.value
                else ReviewHeadReservationState.REVERTED.value
            )
            if (
                reservation_payload["state"] != expected_reservation_state
                or reservation_payload["task_id"] != task["task_id"]
                or reservation_payload["decision_id"] != safe_decision_id
                or reservation_payload["asset_id"] != asset_id
                or reservation_payload["asset_version"] != content_version
                or reservation_payload["target_kind"] != target_kind.value
                or reservation_payload["target_digest"]
                != f"sha256:{target_digest}"
                or reservation_payload["snapshot_id"] != snapshot_id
                or reservation_payload["snapshot_digest"]
                != f"sha256:{snapshot_digest}"
                or reservation_payload["materialized_head_version"]
                != head_version
                or reservation_payload["reserved_head_version"] + 1
                != head_version
            ):
                raise IntegrityError(code)

            correction = connection.execute(
                """SELECT * FROM human_review_correction_versions
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                      AND correction_version=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    task["task_id"],
                    decision_correction_version,
                ),
            ).fetchone()
            if (
                correction is None
                or correction["target_kind"] != target_kind.value
                or correction["target_json"] != head["target_json"]
                or not hmac.compare_digest(
                    normalize_sha256(correction["correction_digest"]),
                    decision_correction_digest,
                )
                or not hmac.compare_digest(
                    normalize_sha256(correction["source_digest"]),
                    decision_source_digest,
                )
                or (
                    head_direction == "APPLY"
                    and (
                        correction["corrected_value_json"]
                        != head["current_value_json"]
                        or not hmac.compare_digest(
                            normalize_sha256(correction["corrected_value_digest"]),
                            head_value_digest,
                        )
                    )
                )
            ):
                raise IntegrityError(code)

            projections = connection.execute(
                """SELECT * FROM human_review_effective_projections
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                      AND source_decision_id=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    task["task_id"],
                    safe_decision_id,
                ),
            ).fetchall()
            try:
                projection_valid = (
                    len(projections) == len(_PROPAGATION_CHANNELS)
                    and {row["channel"] for row in projections}
                    == set(_PROPAGATION_CHANNELS)
                    and all(
                        row["source_decision_id"] == safe_decision_id
                        and int(row["correction_version"])
                        == decision_correction_version
                        and row["direction"] == head_direction
                        and row["target_kind"] == target_kind.value
                        and row["target_json"] == head["target_json"]
                        and row["effective_value_json"]
                        == head["current_value_json"]
                        and hmac.compare_digest(
                            normalize_sha256(row["effective_value_digest"]),
                            head_value_digest,
                        )
                        and hmac.compare_digest(
                            normalize_sha256(row["source_digest"]),
                            decision_source_digest,
                        )
                        for row in projections
                    )
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise IntegrityError(code) from error
            if not projection_valid:
                raise IntegrityError(code)

            propagation_rows = connection.execute(
                """SELECT * FROM human_review_propagation_tasks
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                      AND decision_id=? ORDER BY channel""",
                (
                    context.tenant_id,
                    context.project_id,
                    task["task_id"],
                    safe_decision_id,
                ),
            ).fetchall()
            if (
                len(propagation_rows) != len(_PROPAGATION_CHANNELS)
                or {row["channel"] for row in propagation_rows}
                != set(_PROPAGATION_CHANNELS)
                or any(
                    row["state"] != ReviewPropagationState.SUCCEEDED.value
                    for row in propagation_rows
                )
            ):
                raise IntegrityError(code)
            for propagation_row in propagation_rows:
                payload = cls._decode_content(
                    propagation_row["payload_json"],
                    propagation_row["payload_digest"],
                    code,
                )
                try:
                    payload_effective = bounded_review_json(
                        payload["effective_value"]
                    )
                    payload_prior = bounded_review_json(
                        payload["prior_effective_value"]
                    )
                    payload_effective_digest = normalize_sha256(
                        payload["effective_value_digest"]
                    )
                    payload_prior_digest = normalize_sha256(
                        payload["prior_effective_digest"]
                    )
                    payload_source_digest = normalize_sha256(
                        payload["source_digest"]
                    )
                    payload_correction_digest = normalize_sha256(
                        payload["correction_digest"]
                    )
                    payload_target_json = content_contract_json(payload["target"])
                    payload_effective_json = content_contract_json(payload_effective)
                    payload_effective_content_digest = normalize_sha256(
                        content_contract_digest(payload_effective)
                    )
                    payload_prior_content_digest = normalize_sha256(
                        content_contract_digest(payload_prior)
                    )
                    propagation_correction_version = _safe_version(
                        propagation_row["correction_version"], code
                    )
                except (KeyError, TypeError, ValueError, ValidationError) as error:
                    raise IntegrityError(code) from error
                if (
                    not isinstance(payload, dict)
                    or set(payload) != _PROPAGATION_PAYLOAD_V2_FIELDS
                    or payload.get("schema_version")
                    != "human-review-propagation-v2"
                    or payload.get("tenant_id") != context.tenant_id
                    or payload.get("project_id") != context.project_id
                    or payload.get("task_id") != task["task_id"]
                    or payload.get("decision_id") != safe_decision_id
                    or payload.get("channel") != propagation_row["channel"]
                    or payload.get("direction") != head_direction
                    or payload.get("correction_version")
                    != decision_correction_version
                    or payload.get("target_kind") != target_kind.value
                    or payload_target_json != head["target_json"]
                    or payload_effective_json != head["current_value_json"]
                    or not hmac.compare_digest(
                        payload_effective_digest, head_value_digest
                    )
                    or not hmac.compare_digest(
                        payload_effective_content_digest, payload_effective_digest
                    )
                    or not hmac.compare_digest(
                        payload_prior_content_digest, payload_prior_digest
                    )
                    or not hmac.compare_digest(
                        payload_source_digest, decision_source_digest
                    )
                    or not hmac.compare_digest(
                        payload_correction_digest, decision_correction_digest
                    )
                    or propagation_correction_version != decision_correction_version
                    or propagation_row["direction"] != head_direction
                    or payload.get("reservation_id")
                    != reservation_payload["reservation_id"]
                    or payload.get("reservation_fence")
                    != reservation_payload["reservation_fence"]
                    or payload.get("reservation_binding_digest")
                    != reservation_payload["binding_digest"]
                ):
                    raise IntegrityError(code)

        original_value_client_digest = human_review_client_value_digest(current_value)
        source_ref = {
            "schema_version": "human-review-source-ref-v2",
            "content_id": asset_id,
            "content_version": content_version,
            "content_digest": f"sha256:{content_digest}",
            "asset_sha256": f"sha256:{asset_sha256}",
            "target_kind": target_kind.value,
            "target_digest": f"sha256:{target_digest}",
            "snapshot_id": snapshot_id,
            "snapshot_digest": f"sha256:{snapshot_digest}",
            "head_version": head_version,
            "head_value_digest": f"sha256:{head_value_digest}",
            "source_digest": f"sha256:{source_digest}",
            "provenance_digest": f"sha256:{provenance_digest}",
            "original_value_client_digest": (
                f"sha256:{original_value_client_digest}"
            ),
            "original_value_digest_contract": CANONICAL_JSON_SHA256_CONTRACT,
        }
        if set(source_ref) != _SOURCE_REF_V2_FIELDS:
            raise IntegrityError(code)
        summary = {
            "schema_version": "human-review-source-summary-v1",
            "content_id": asset_id,
            "content_version": content_version,
            "target_kind": target_kind.value,
            "target": target,
            "target_digest": f"sha256:{target_digest}",
            "confidence": confidence,
            "head_version": head_version,
            "head_direction": head_direction,
            "head_correction_version": head_correction_version,
            "original_value_client_digest": (
                f"sha256:{original_value_client_digest}"
            ),
            "original_value_digest_contract": CANONICAL_JSON_SHA256_CONTRACT,
            "source_ref": source_ref,
        }
        detail = {
            **summary,
            "schema_version": "human-review-source-detail-v1",
            "original_value": current_value,
        }
        return summary, detail

    @staticmethod
    def _source_collection_digest(
        summaries: Iterable[Mapping[str, Any]], *, filter_digest: str, total: int
    ) -> str:
        digest = hashlib.sha256()
        digest.update(
            content_contract_json(
                {
                    "schema_version": "human-review-source-collection-v1",
                    "filter_digest": f"sha256:{filter_digest}",
                    "total": total,
                }
            ).encode("utf-8")
        )
        for summary in summaries:
            try:
                rendered = content_contract_json(summary).encode("utf-8")
            except (TypeError, ValueError, ValidationError) as error:
                raise IntegrityError("HUMAN_REVIEW_SOURCE_HEAD_CORRUPT") from error
            digest.update(len(rendered).to_bytes(8, "big"))
            digest.update(rendered)
        return digest.hexdigest()

    def list_source_heads(
        self,
        context: TenantContext,
        *,
        asset_id: str,
        expected_asset_version: int,
        kinds: Sequence[str],
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        """List bounded authoritative source heads without returning large values."""

        safe_asset_id = require_resource_id(asset_id, "asset_id")
        safe_asset_version = _safe_version(
            expected_asset_version, "HUMAN_REVIEW_EXPECTED_ASSET_VERSION_INVALID"
        )
        if isinstance(kinds, (str, bytes)) or not isinstance(kinds, Sequence):
            raise ValidationError("HUMAN_REVIEW_SOURCE_FILTER_INVALID")
        try:
            supplied_kinds = tuple(ReviewTargetKind(value).value for value in kinds)
        except (TypeError, ValueError) as error:
            raise ValidationError("HUMAN_REVIEW_SOURCE_FILTER_INVALID") from error
        safe_kinds = tuple(sorted(set(supplied_kinds)))
        if supplied_kinds != safe_kinds:
            raise ValidationError("HUMAN_REVIEW_SOURCE_FILTER_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValidationError("HUMAN_REVIEW_SOURCE_LIST_LIMIT_INVALID")
        filter_binding = {
            "schema_version": "human-review-source-filter-v1",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "content_id": safe_asset_id,
            "content_version": safe_asset_version,
            "kinds": list(safe_kinds),
        }
        filter_digest = canonical_digest(filter_binding)
        after: tuple[str, str] | None = None
        decoded_cursor: dict[str, Any] | None = None
        cursor_collection_digest: str | None = None
        cursor_collection_generation: int | None = None
        if cursor is not None:
            try:
                decoded_cursor = self._decode_cursor(cursor)
            except ValidationError as error:
                raise ValidationError("HUMAN_REVIEW_SOURCE_CURSOR_INVALID") from error
            if set(decoded_cursor) != {
                "version",
                "filter_digest",
                "collection_digest",
                "collection_generation",
                "target_kind",
                "target_digest",
            }:
                raise ValidationError("HUMAN_REVIEW_SOURCE_CURSOR_INVALID")
            if (
                decoded_cursor.get("version") != "human-review-source-cursor-v1"
                or not hmac.compare_digest(
                    str(decoded_cursor.get("filter_digest", "")), filter_digest
                )
            ):
                raise ValidationError("HUMAN_REVIEW_SOURCE_CURSOR_SCOPE_INVALID")
            try:
                cursor_collection_digest = normalize_sha256(
                    decoded_cursor["collection_digest"]
                )
                cursor_collection_generation = _safe_version(
                    decoded_cursor["collection_generation"],
                    "HUMAN_REVIEW_SOURCE_CURSOR_INVALID",
                )
                after = (
                    ReviewTargetKind(decoded_cursor["target_kind"]).value,
                    normalize_sha256(decoded_cursor["target_digest"]),
                )
            except (KeyError, TypeError, ValueError, ValidationError) as error:
                raise ValidationError("HUMAN_REVIEW_SOURCE_CURSOR_INVALID") from error

        where = [
            "tenant_id=?",
            "project_id=?",
            "asset_id=?",
            "asset_version=?",
        ]
        parameters: list[Any] = [
            context.tenant_id,
            context.project_id,
            safe_asset_id,
            safe_asset_version,
        ]
        if safe_kinds:
            where.append("target_kind IN (" + ",".join("?" for _ in safe_kinds) + ")")
            parameters.extend(safe_kinds)
        base_where_sql = " AND ".join(where)

        with self._store.read_transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            asset = self._store._scoped_asset(connection, context, safe_asset_id)
            self._store._require_human_review_asset_state(asset)
            if int(asset["version"]) != safe_asset_version:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_ASSET_VERSION_DRIFT",
                    details={
                        "expected_version": safe_asset_version,
                        "actual_version": int(asset["version"]),
                    },
                )
            current = self._store._human_review_current(connection, context, asset)
            generation_row = connection.execute(
                """SELECT generation
                     FROM human_review_source_collection_generations
                    WHERE tenant_id=? AND project_id=? AND asset_id=?
                      AND asset_version=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_asset_version,
                ),
            ).fetchone()
            collection_generation = (
                _safe_version(
                    generation_row["generation"],
                    "HUMAN_REVIEW_SOURCE_GENERATION_CORRUPT",
                )
                if generation_row is not None
                else 0
            )
            if cursor_collection_generation is not None:
                if cursor_collection_generation != collection_generation:
                    raise ConflictError("HUMAN_REVIEW_SOURCE_COLLECTION_DRIFT")
                assert cursor_collection_digest is not None
                collection_digest = cursor_collection_digest
                total = int(
                    connection.execute(
                        f"""SELECT count(*) FROM human_review_target_heads
                              WHERE {base_where_sql}""",
                        parameters,
                    ).fetchone()[0]
                )
                if total > _MAX_SOURCE_DISCOVERY_ROWS:
                    raise ValidationError(
                        "HUMAN_REVIEW_SOURCE_COLLECTION_LIMIT_EXCEEDED"
                    )
            else:
                collection_rows = connection.execute(
                    f"""SELECT * FROM human_review_target_heads
                          WHERE {base_where_sql}
                          ORDER BY target_kind,target_digest
                          LIMIT ?""",
                    (*parameters, _MAX_SOURCE_DISCOVERY_ROWS + 1),
                ).fetchall()
                if len(collection_rows) > _MAX_SOURCE_DISCOVERY_ROWS:
                    raise ValidationError(
                        "HUMAN_REVIEW_SOURCE_COLLECTION_LIMIT_EXCEEDED"
                    )
                total = len(collection_rows)
                collection_digest = self._source_collection_digest(
                    (
                        self._source_head_documents(
                            connection,
                            context,
                            asset=asset,
                            current=current,
                            head=collection_row,
                        )[0]
                        for collection_row in collection_rows
                    ),
                    filter_digest=filter_digest,
                    total=total,
                )

            page_where = list(where)
            page_parameters = list(parameters)
            if after is not None:
                page_where.append(
                    "(target_kind>? OR (target_kind=? AND target_digest>?))"
                )
                page_parameters.extend((after[0], after[0], after[1]))
            page_rows = connection.execute(
                f"""SELECT * FROM human_review_target_heads
                      WHERE {' AND '.join(page_where)}
                      ORDER BY target_kind,target_digest LIMIT ?""",
                (*page_parameters, limit + 1),
            ).fetchall()
            page = page_rows[:limit]
            summaries = [
                self._source_head_documents(
                    connection, context, asset=asset, current=current, head=row
                )[0]
                for row in page
            ]

        next_cursor = None
        if len(page_rows) > limit and page:
            if collection_generation < 1:
                raise IntegrityError("HUMAN_REVIEW_SOURCE_GENERATION_CORRUPT")
            last = page[-1]
            next_cursor = self._encode_cursor(
                {
                    "version": "human-review-source-cursor-v1",
                    "filter_digest": filter_digest,
                    "collection_digest": collection_digest,
                    "collection_generation": collection_generation,
                    "target_kind": last["target_kind"],
                    "target_digest": (
                        f"sha256:{normalize_sha256(last['target_digest'])}"
                    ),
                }
            )
        return {
            "sources": summaries,
            "next_cursor": next_cursor,
            "total": total,
        }

    def get_source_head(
        self,
        context: TenantContext,
        *,
        asset_id: str,
        expected_asset_version: int,
        target_kind: str,
        target_digest: str,
        expected_head_version: int,
    ) -> dict[str, Any]:
        """Get one exact current source head and its authoritative value."""

        safe_asset_id = require_resource_id(asset_id, "asset_id")
        safe_asset_version = _safe_version(
            expected_asset_version, "HUMAN_REVIEW_EXPECTED_ASSET_VERSION_INVALID"
        )
        safe_head_version = _safe_version(
            expected_head_version, "HUMAN_REVIEW_EXPECTED_HEAD_VERSION_INVALID"
        )
        try:
            safe_kind = ReviewTargetKind(target_kind)
            safe_target_digest = normalize_sha256(target_digest)
        except (TypeError, ValueError, ValidationError) as error:
            raise ValidationError("HUMAN_REVIEW_SOURCE_IDENTITY_INVALID") from error
        with self._store.read_transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            asset = self._store._scoped_asset(connection, context, safe_asset_id)
            self._store._require_human_review_asset_state(asset)
            if int(asset["version"]) != safe_asset_version:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_ASSET_VERSION_DRIFT",
                    details={
                        "expected_version": safe_asset_version,
                        "actual_version": int(asset["version"]),
                    },
                )
            current = self._store._human_review_current(connection, context, asset)
            head = connection.execute(
                """SELECT * FROM human_review_target_heads
                    WHERE tenant_id=? AND project_id=? AND asset_id=?
                      AND asset_version=? AND target_kind=? AND target_digest=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_asset_version,
                    safe_kind.value,
                    safe_target_digest,
                ),
            ).fetchone()
            if head is None:
                raise NotFoundError("HUMAN_REVIEW_SOURCE_NOT_FOUND")
            _summary, detail = self._source_head_documents(
                connection, context, asset=asset, current=current, head=head
            )
            if int(head["version"]) != safe_head_version:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_HEAD_VERSION_DRIFT",
                    details={
                        "expected_version": safe_head_version,
                        "actual_version": int(head["version"]),
                    },
                )
            return {"source": detail}

    @staticmethod
    def _normalize_source_bound_enqueue_input(
        *,
        asset_id: str,
        expected_asset_version: int,
        target_kind: str,
        target_digest: str,
        expected_head_version: int,
        expected_snapshot_id: str,
        expected_snapshot_digest: str,
        expected_head_value_digest: str,
        original_value_digest: str,
        reason: str,
    ) -> dict[str, Any]:
        safe_asset_id = require_resource_id(asset_id, "asset_id")
        safe_asset_version = _safe_version(
            expected_asset_version, "HUMAN_REVIEW_EXPECTED_ASSET_VERSION_INVALID"
        )
        try:
            safe_kind = ReviewTargetKind(target_kind).value
        except (TypeError, ValueError) as error:
            raise ValidationError("HUMAN_REVIEW_TARGET_KIND_INVALID") from error
        safe_head_version = _safe_version(
            expected_head_version, "HUMAN_REVIEW_EXPECTED_HEAD_VERSION_INVALID"
        )
        safe_snapshot_id = require_resource_id(expected_snapshot_id, "snapshot_id")
        try:
            safe_target_digest = normalize_sha256(target_digest)
            safe_snapshot_digest = normalize_sha256(expected_snapshot_digest)
            safe_head_value_digest = normalize_sha256(expected_head_value_digest)
            echo_client_digest = normalize_sha256(original_value_digest)
        except ValidationError as error:
            raise ValidationError("HUMAN_REVIEW_EXPECTED_SOURCE_BINDING_INVALID") from error
        return {
            "content_id": safe_asset_id,
            "expected_asset_version": safe_asset_version,
            "target_kind": safe_kind,
            "target_digest": f"sha256:{safe_target_digest}",
            "expected_head_version": safe_head_version,
            "expected_snapshot_id": safe_snapshot_id,
            "expected_snapshot_digest": f"sha256:{safe_snapshot_digest}",
            "expected_head_value_digest": f"sha256:{safe_head_value_digest}",
            "original_value_digest": f"sha256:{echo_client_digest}",
            "reason": _required_text(reason, "HUMAN_REVIEW_REASON_INVALID"),
        }

    def enqueue_review_task(
        self,
        context: TenantContext,
        *,
        asset_id: str,
        expected_asset_version: int,
        target_kind: str,
        target_digest: str,
        expected_head_version: int,
        expected_snapshot_id: str,
        expected_snapshot_digest: str,
        expected_head_value_digest: str,
        original_value_digest: str,
        reason: str,
        idempotency_key: str,
        request_digest: str,
        _connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        enqueue_input = self._normalize_source_bound_enqueue_input(
            asset_id=asset_id,
            expected_asset_version=expected_asset_version,
            target_kind=target_kind,
            target_digest=target_digest,
            expected_head_version=expected_head_version,
            expected_snapshot_id=expected_snapshot_id,
            expected_snapshot_digest=expected_snapshot_digest,
            expected_head_value_digest=expected_head_value_digest,
            original_value_digest=original_value_digest,
            reason=reason,
        )
        safe_asset_id = enqueue_input["content_id"]
        safe_asset_version = enqueue_input["expected_asset_version"]
        safe_kind = ReviewTargetKind(enqueue_input["target_kind"])
        safe_target_digest = normalize_sha256(enqueue_input["target_digest"])
        safe_head_version = enqueue_input["expected_head_version"]
        safe_snapshot_id = enqueue_input["expected_snapshot_id"]
        safe_snapshot_digest = normalize_sha256(
            enqueue_input["expected_snapshot_digest"]
        )
        safe_head_value_digest = normalize_sha256(
            enqueue_input["expected_head_value_digest"]
        )
        echo_client_digest = normalize_sha256(enqueue_input["original_value_digest"])
        safe_reason = enqueue_input["reason"]
        safe_key = require_idempotency_key(idempotency_key)
        caller_request_digest = self._request_digest(request_digest)
        safe_request_digest = canonical_digest(
            {
                "schema_version": "human-review-source-bound-enqueue-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "asset_id": safe_asset_id,
                "expected_asset_version": safe_asset_version,
                "target_kind": safe_kind.value,
                "target_digest": f"sha256:{safe_target_digest}",
                "expected_head_version": safe_head_version,
                "expected_snapshot_id": safe_snapshot_id,
                "expected_snapshot_digest": f"sha256:{safe_snapshot_digest}",
                "expected_head_value_digest": f"sha256:{safe_head_value_digest}",
                "original_value_digest": f"sha256:{echo_client_digest}",
                "original_value_digest_contract": CANONICAL_JSON_SHA256_CONTRACT,
                "reason": safe_reason,
                "caller_request_digest": f"sha256:{caller_request_digest}",
            }
        )
        if _connection is not None and (
            not isinstance(_connection, sqlite3.Connection)
            or not _connection.in_transaction
        ):
            raise IntegrityError("HUMAN_REVIEW_ENQUEUE_TRANSACTION_INVALID")
        transaction_scope = (
            nullcontext(_connection)
            if _connection is not None
            else self._store.transaction()
        )
        with transaction_scope as connection:
            assert connection is not None
            self._store._require(connection, context, self._store.REVIEW)
            replay = self._receipt(
                connection,
                context,
                operation="enqueue",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            asset = self._store._scoped_asset(connection, context, safe_asset_id)
            self._store._require_human_review_asset_state(asset)
            if int(asset["version"]) != safe_asset_version:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_ASSET_VERSION_DRIFT",
                    details={
                        "expected_version": safe_asset_version,
                        "actual_version": int(asset["version"]),
                    },
                )
            current = self._store._human_review_current(connection, context, asset)
            head = connection.execute(
                """SELECT * FROM human_review_target_heads
                    WHERE tenant_id=? AND project_id=? AND asset_id=?
                      AND asset_version=? AND target_kind=? AND target_digest=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_asset_version,
                    safe_kind.value,
                    safe_target_digest,
                ),
            ).fetchone()
            if head is None:
                if safe_kind in {
                    ReviewTargetKind.REQUIREMENT,
                    ReviewTargetKind.CONFLICT,
                }:
                    raise ConflictError("REQUIRES_SOURCE_PRODUCER")
                raise ConflictError("HUMAN_REVIEW_TARGET_UNRESOLVABLE")
            _summary, source_detail = self._source_head_documents(
                connection, context, asset=asset, current=current, head=head
            )
            source_ref = dict(source_detail["source_ref"])
            try:
                actual_head_version = _safe_version(
                    head["version"], "HUMAN_REVIEW_SOURCE_HEAD_CORRUPT"
                )
                actual_snapshot_id = require_resource_id(
                    source_ref["snapshot_id"], "snapshot_id"
                )
                actual_snapshot_digest = normalize_sha256(
                    source_ref["snapshot_digest"]
                )
                actual_head_value_digest = normalize_sha256(
                    head["current_value_digest"]
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise IntegrityError("HUMAN_REVIEW_SOURCE_HEAD_CORRUPT") from error
            if (
                actual_head_version != safe_head_version
                or actual_snapshot_id != safe_snapshot_id
                or not hmac.compare_digest(
                    actual_snapshot_digest, safe_snapshot_digest
                )
                or not hmac.compare_digest(
                    actual_head_value_digest, safe_head_value_digest
                )
            ):
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_HEAD_DRIFT",
                    details={
                        "expected_head_version": safe_head_version,
                        "actual_head_version": actual_head_version,
                        "expected_snapshot_id": safe_snapshot_id,
                        "actual_snapshot_id": actual_snapshot_id,
                        "expected_snapshot_digest": (
                            f"sha256:{safe_snapshot_digest}"
                        ),
                        "actual_snapshot_digest": (
                            f"sha256:{actual_snapshot_digest}"
                        ),
                        "expected_head_value_digest": (
                            f"sha256:{safe_head_value_digest}"
                        ),
                        "actual_head_value_digest": (
                            f"sha256:{actual_head_value_digest}"
                        ),
                    },
                )
            original_json = str(head["current_value_json"])
            original_digest = normalize_sha256(head["current_value_digest"])
            authoritative_client_digest = normalize_sha256(
                source_detail["original_value_client_digest"]
            )
            if not hmac.compare_digest(
                echo_client_digest, authoritative_client_digest
            ):
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_DRIFT",
                    details={
                        "expected_original_digest": (
                            f"sha256:{authoritative_client_digest}"
                        ),
                        "original_value_digest_contract": (
                            CANONICAL_JSON_SHA256_CONTRACT
                        ),
                    },
                )
            source_digest = original_digest
            target_json = str(head["target_json"])
            _source_copy, source_json, source_ref_digest = self._content_json(
                source_ref, "HUMAN_REVIEW_SOURCE_REF_INVALID"
            )
            task_id = "review-" + canonical_digest(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "asset_id": safe_asset_id,
                    "target_digest": f"sha256:{safe_target_digest}",
                    "source_digest": f"sha256:{source_digest}",
                    "snapshot_digest": source_ref["snapshot_digest"],
                    "head_version": actual_head_version,
                    "idempotency_key": safe_key,
                }
            )[:32]
            now = utc_now()
            connection.execute(
                """INSERT INTO human_review_tasks (
                    task_id,tenant_id,project_id,asset_id,target_kind,target_json,
                    target_digest,original_value_json,original_value_digest,
                    source_digest,source_ref_json,source_ref_digest,confidence,reason,
                    state,current_correction_version,current_correction_digest,
                    effective_version,effective_digest,claim_actor_id,claim_token_digest,
                    claim_fence,claim_expires_at,version,created_by,created_at,updated_at,
                    closed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'QUEUED',0,NULL,0,NULL,NULL,NULL,0,NULL,1,?,?,?,NULL)""",
                (
                    task_id,
                    context.tenant_id,
                    context.project_id,
                    safe_asset_id,
                    safe_kind.value,
                    target_json,
                    safe_target_digest,
                    original_json,
                    original_digest,
                    source_digest,
                    source_json,
                    source_ref_digest,
                    float(source_detail["confidence"]),
                    safe_reason,
                    context.actor_id,
                    now,
                    now,
                ),
            )
            self._audit(
                connection,
                context,
                task_id=task_id,
                event_type="review.requested",
                prior_state=None,
                next_state=ReviewTaskState.QUEUED.value,
                task_version=1,
                details={
                    "content_id": safe_asset_id,
                    "content_version": safe_asset_version,
                    "target_kind": safe_kind.value,
                    "target_digest": f"sha256:{safe_target_digest}",
                    "source_digest": f"sha256:{source_digest}",
                    "snapshot_digest": source_ref["snapshot_digest"],
                    "original_value_client_digest": (
                        source_ref["original_value_client_digest"]
                    ),
                    "original_value_digest_contract": (
                        CANONICAL_JSON_SHA256_CONTRACT
                    ),
                    "confidence": float(source_detail["confidence"]),
                },
            )
            self._store._event(
                connection,
                context,
                "human_review_task",
                task_id,
                "review.requested",
                f"review-requested:{task_id}",
                {
                    "task_id": task_id,
                    "content_id": safe_asset_id,
                    "content_version": safe_asset_version,
                    "target_kind": safe_kind.value,
                    "source_digest": f"sha256:{source_digest}",
                    "snapshot_digest": source_ref["snapshot_digest"],
                },
            )
            row = self._scoped_task(connection, context, task_id)
            response = {"task": self._task_payload(row)}
            return self._record_receipt(
                connection,
                context,
                operation="enqueue",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @staticmethod
    def _recovery_handle(value: Any) -> tuple[str, str]:
        handle, handle_digest = _token_digest(
            value, "HUMAN_REVIEW_RECOVERY_HANDLE_INVALID"
        )
        if len(handle.encode("utf-8")) < 32:
            raise ValidationError("HUMAN_REVIEW_RECOVERY_HANDLE_INVALID")
        return handle, handle_digest

    def _preparation_document(
        self,
        row: sqlite3.Row,
        *,
        recovery_handle: str,
        state: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        code = "HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT"
        try:
            require_resource_id(
                row["preparation_id"], "preparation_id"
            )
            input_digest = normalize_sha256(row["enqueue_input_digest"])
            normalize_sha256(row["recovery_handle_digest"])
            normalize_sha256(row["execute_idempotency_key_digest"])
            normalize_sha256(row["prepare_request_digest"])
            enqueue_input = bounded_review_json(
                json.loads(row["enqueue_input_json"]), allow_none=False
            )
            if (
                not isinstance(enqueue_input, dict)
                or set(enqueue_input)
                != {
                    "content_id", "expected_asset_version", "target_kind",
                    "target_digest", "expected_head_version", "expected_snapshot_id",
                    "expected_snapshot_digest", "expected_head_value_digest",
                    "original_value_digest", "reason",
                }
                or canonical_json(enqueue_input) != row["enqueue_input_json"]
                or not hmac.compare_digest(
                    canonical_digest(enqueue_input), input_digest
                )
            ):
                raise IntegrityError(code)
            normalized = self._normalize_source_bound_enqueue_input(
                asset_id=enqueue_input["content_id"],
                expected_asset_version=enqueue_input["expected_asset_version"],
                target_kind=enqueue_input["target_kind"],
                target_digest=enqueue_input["target_digest"],
                expected_head_version=enqueue_input["expected_head_version"],
                expected_snapshot_id=enqueue_input["expected_snapshot_id"],
                expected_snapshot_digest=enqueue_input["expected_snapshot_digest"],
                expected_head_value_digest=enqueue_input["expected_head_value_digest"],
                original_value_digest=enqueue_input["original_value_digest"],
                reason=enqueue_input["reason"],
            )
            if normalized != enqueue_input:
                raise IntegrityError(code)
            for field in ("expires_at", "prepared_at", "executed_at"):
                timestamp = row[field]
                if timestamp is None and field == "executed_at":
                    continue
                parsed = datetime.fromisoformat(timestamp)
                if parsed.tzinfo is None or parsed.isoformat() != timestamp:
                    raise IntegrityError(code)
            stored_state = row["state"]
            if stored_state not in {"PREPARED", "EXECUTED"}:
                raise IntegrityError(code)
            if (stored_state == "PREPARED") != (
                row["executed_at"] is None and row["task_id"] is None
            ):
                raise IntegrityError(code)
            if stored_state == "EXECUTED":
                require_resource_id(row["task_id"], "task_id")
        except IntegrityError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            raise IntegrityError(code) from error
        effective_state = state or stored_state
        if effective_state not in {"PREPARED", "EXECUTED", "EXPIRED"}:
            raise IntegrityError(code)
        return enqueue_input, {
            "schema_version": "human-review-enqueue-preparation-v1",
            "recovery_handle": recovery_handle,
            "request_digest": f"sha256:{input_digest}",
            "state": effective_state,
            "safe_to_clear": effective_state in {"EXECUTED", "EXPIRED"},
            "expires_at": row["expires_at"],
            "prepared_at": row["prepared_at"],
            "executed_at": row["executed_at"],
            "task_id": row["task_id"],
            "enqueue_input": enqueue_input,
        }

    def prepare_enqueue_review_task(
        self,
        context: TenantContext,
        *,
        recovery_handle: str,
        execute_idempotency_key: str,
        asset_id: str,
        expected_asset_version: int,
        target_kind: str,
        target_digest: str,
        expected_head_version: int,
        expected_snapshot_id: str,
        expected_snapshot_digest: str,
        expected_head_value_digest: str,
        original_value_digest: str,
        reason: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_handle, handle_digest = self._recovery_handle(recovery_handle)
        safe_execute_key = require_idempotency_key(execute_idempotency_key)
        safe_prepare_key = require_idempotency_key(idempotency_key)
        if safe_execute_key == safe_prepare_key:
            raise ValidationError("HUMAN_REVIEW_RECOVERY_IDEMPOTENCY_KEYS_INVALID")
        execute_key_digest = hashlib.sha256(
            safe_execute_key.encode("utf-8")
        ).hexdigest()
        enqueue_input = self._normalize_source_bound_enqueue_input(
            asset_id=asset_id,
            expected_asset_version=expected_asset_version,
            target_kind=target_kind,
            target_digest=target_digest,
            expected_head_version=expected_head_version,
            expected_snapshot_id=expected_snapshot_id,
            expected_snapshot_digest=expected_snapshot_digest,
            expected_head_value_digest=expected_head_value_digest,
            original_value_digest=original_value_digest,
            reason=reason,
        )
        enqueue_input_json = canonical_json(enqueue_input)
        enqueue_input_digest = canonical_digest(enqueue_input)
        caller_request_digest = self._request_digest(request_digest)
        safe_request_digest = canonical_digest(
            {
                "schema_version": "human-review-enqueue-prepare-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "recovery_handle_digest": f"sha256:{handle_digest}",
                "execute_idempotency_key_digest": f"sha256:{execute_key_digest}",
                "enqueue_input_digest": f"sha256:{enqueue_input_digest}",
                "caller_request_digest": f"sha256:{caller_request_digest}",
            }
        )
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        expires_at = (now_dt + _ENQUEUE_PREPARATION_TTL).isoformat()
        preparation_id = "review-enqueue-preparation-" + canonical_digest(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "recovery_handle_digest": f"sha256:{handle_digest}",
            }
        )[:32]
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            replay = self._receipt(
                connection,
                context,
                operation="enqueue_prepare",
                idempotency_key=safe_prepare_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            existing = connection.execute(
                """SELECT * FROM human_review_enqueue_preparations
                    WHERE tenant_id=? AND project_id=? AND actor_id=?
                      AND recovery_handle_digest=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    handle_digest,
                ),
            ).fetchone()
            if existing is not None:
                _stored_input, preparation = self._preparation_document(
                    existing, recovery_handle=safe_handle
                )
                if (
                    not hmac.compare_digest(
                        existing["execute_idempotency_key_digest"],
                        execute_key_digest,
                    )
                    or not hmac.compare_digest(
                        existing["enqueue_input_digest"], enqueue_input_digest
                    )
                    or not hmac.compare_digest(
                        existing["prepare_request_digest"], safe_request_digest
                    )
                ):
                    raise ConflictError(
                        "HUMAN_REVIEW_ENQUEUE_PREPARATION_CONFLICT"
                    )
                response = {"preparation": preparation}
                return self._record_receipt(
                    connection,
                    context,
                    operation="enqueue_prepare",
                    idempotency_key=safe_prepare_key,
                    request_digest=safe_request_digest,
                    response=response,
                )
            counts = connection.execute(
                """SELECT count(*) AS total,
                          sum(CASE WHEN state='PREPARED' AND expires_at>? THEN 1 ELSE 0 END)
                              AS active
                     FROM human_review_enqueue_preparations
                    WHERE tenant_id=? AND project_id=? AND actor_id=?""",
                (now, context.tenant_id, context.project_id, context.actor_id),
            ).fetchone()
            if (
                int(counts["total"]) >= _MAX_TOTAL_ENQUEUE_PREPARATIONS
                or int(counts["active"] or 0) >= _MAX_ACTIVE_ENQUEUE_PREPARATIONS
            ):
                raise ConflictError(
                    "HUMAN_REVIEW_ENQUEUE_PREPARATION_QUOTA_EXCEEDED"
                )
            connection.execute(
                """INSERT INTO human_review_enqueue_preparations (
                    preparation_id,tenant_id,project_id,actor_id,
                    recovery_handle_digest,execute_idempotency_key_digest,
                    enqueue_input_json,enqueue_input_digest,prepare_request_digest,
                    state,expires_at,prepared_at,executed_at,task_id
                ) VALUES (?,?,?,?,?,?,?,?,?,'PREPARED',?,?,NULL,NULL)""",
                (
                    preparation_id,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    handle_digest,
                    execute_key_digest,
                    enqueue_input_json,
                    enqueue_input_digest,
                    safe_request_digest,
                    expires_at,
                    now,
                ),
            )
            row = connection.execute(
                """SELECT * FROM human_review_enqueue_preparations
                    WHERE tenant_id=? AND project_id=? AND actor_id=?
                      AND preparation_id=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    preparation_id,
                ),
            ).fetchone()
            if row is None:
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT")
            _stored_input, preparation = self._preparation_document(
                row, recovery_handle=safe_handle
            )
            response = {"preparation": preparation}
            return self._record_receipt(
                connection,
                context,
                operation="enqueue_prepare",
                idempotency_key=safe_prepare_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def execute_prepared_review_task(
        self,
        context: TenantContext,
        *,
        recovery_handle: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_handle, handle_digest = self._recovery_handle(recovery_handle)
        safe_execute_key = require_idempotency_key(idempotency_key)
        execute_key_digest = hashlib.sha256(
            safe_execute_key.encode("utf-8")
        ).hexdigest()
        caller_request_digest = self._request_digest(request_digest)
        safe_request_digest = canonical_digest(
            {
                "schema_version": "human-review-enqueue-execute-receipt-v1",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "actor_id": context.actor_id,
                "recovery_handle_digest": f"sha256:{handle_digest}",
                "execute_idempotency_key_digest": f"sha256:{execute_key_digest}",
                "caller_request_digest": f"sha256:{caller_request_digest}",
            }
        )
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            replay = self._receipt(
                connection,
                context,
                operation="enqueue_execute",
                idempotency_key=safe_execute_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            row = connection.execute(
                """SELECT * FROM human_review_enqueue_preparations
                    WHERE tenant_id=? AND project_id=? AND actor_id=?
                      AND recovery_handle_digest=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    handle_digest,
                ),
            ).fetchone()
            if row is None:
                response = {
                    "preparation": {
                        "schema_version": "human-review-enqueue-preparation-absence-v1",
                        "recovery_handle": safe_handle,
                        "state": "ABSENT",
                        "safe_to_clear": True,
                    }
                }
                return self._record_receipt(
                    connection,
                    context,
                    operation="enqueue_execute",
                    idempotency_key=safe_execute_key,
                    request_digest=safe_request_digest,
                    response=response,
                )
            if not hmac.compare_digest(
                row["execute_idempotency_key_digest"], execute_key_digest
            ):
                raise AuthorizationError(
                    "HUMAN_REVIEW_ENQUEUE_PREPARATION_CAPABILITY_DENIED"
                )
            enqueue_input, preparation = self._preparation_document(
                row, recovery_handle=safe_handle
            )
            if row["state"] == "EXECUTED":
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_EXECUTE_RECEIPT_MISSING")
            now = utc_now()
            if str(row["expires_at"]) <= now:
                _enqueue_input, expired = self._preparation_document(
                    row, recovery_handle=safe_handle, state="EXPIRED"
                )
                response = {"preparation": expired}
                return self._record_receipt(
                    connection,
                    context,
                    operation="enqueue_execute",
                    idempotency_key=safe_execute_key,
                    request_digest=safe_request_digest,
                    response=response,
                )
            inner_request_digest = canonical_digest(
                {
                    "schema_version": "human-review-prepared-enqueue-inner-v1",
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "actor_id": context.actor_id,
                    "preparation_id": row["preparation_id"],
                    "enqueue_input_digest": (
                        f"sha256:{row['enqueue_input_digest']}"
                    ),
                    "execute_request_digest": f"sha256:{safe_request_digest}",
                }
            )
            enqueued = self.enqueue_review_task(
                context,
                asset_id=enqueue_input["content_id"],
                expected_asset_version=enqueue_input["expected_asset_version"],
                target_kind=enqueue_input["target_kind"],
                target_digest=enqueue_input["target_digest"],
                expected_head_version=enqueue_input["expected_head_version"],
                expected_snapshot_id=enqueue_input["expected_snapshot_id"],
                expected_snapshot_digest=enqueue_input["expected_snapshot_digest"],
                expected_head_value_digest=enqueue_input["expected_head_value_digest"],
                original_value_digest=enqueue_input["original_value_digest"],
                reason=enqueue_input["reason"],
                idempotency_key=safe_execute_key,
                request_digest=inner_request_digest,
                _connection=connection,
            )
            task = enqueued.get("task")
            if not isinstance(task, dict):
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT")
            raw_task_id = task.get("task_id")
            if not isinstance(raw_task_id, str):
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT")
            task_id = require_resource_id(raw_task_id, "task_id")
            changed = connection.execute(
                """UPDATE human_review_enqueue_preparations
                      SET state='EXECUTED',executed_at=?,task_id=?
                    WHERE tenant_id=? AND project_id=? AND actor_id=?
                      AND preparation_id=? AND state='PREPARED'
                      AND executed_at IS NULL AND task_id IS NULL""",
                (
                    now,
                    task_id,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    row["preparation_id"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CONFLICT")
            executed_row = connection.execute(
                """SELECT * FROM human_review_enqueue_preparations
                    WHERE tenant_id=? AND project_id=? AND actor_id=?
                      AND preparation_id=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    row["preparation_id"],
                ),
            ).fetchone()
            if executed_row is None:
                raise IntegrityError("HUMAN_REVIEW_ENQUEUE_PREPARATION_CORRUPT")
            _executed_input, executed = self._preparation_document(
                executed_row, recovery_handle=safe_handle
            )
            response = {"preparation": executed, "task": task}
            return self._record_receipt(
                connection,
                context,
                operation="enqueue_execute",
                idempotency_key=safe_execute_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @staticmethod
    def _encode_cursor(payload: Mapping[str, Any]) -> str:
        raw = content_contract_json(payload).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(value: str) -> dict[str, Any]:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 4_096
            or "=" in value
            or not all(
                character.isascii()
                and (character.isalnum() or character in "-_")
                for character in value
            )
        ):
            raise ValidationError("HUMAN_REVIEW_CURSOR_INVALID")
        try:
            padded = value + "=" * (-len(value) % 4)
            raw = base64.b64decode(padded, altchars=b"-_", validate=True)
            payload = bounded_review_json(json.loads(raw.decode("utf-8")))
        except (ValueError, UnicodeError, json.JSONDecodeError, ValidationError) as error:
            raise ValidationError("HUMAN_REVIEW_CURSOR_INVALID") from error
        if not isinstance(payload, dict):
            raise ValidationError("HUMAN_REVIEW_CURSOR_INVALID")
        if (
            content_contract_json(payload).encode("utf-8") != raw
            or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value
        ):
            raise ValidationError("HUMAN_REVIEW_CURSOR_INVALID")
        return payload

    def list_review_tasks(
        self,
        context: TenantContext,
        *,
        kinds: Sequence[str] = (),
        states: Sequence[str] = (),
        confidence_lte: float | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        try:
            safe_kinds = tuple(sorted({ReviewTargetKind(value).value for value in kinds}))
            safe_states = tuple(sorted({ReviewTaskState(value).value for value in states}))
        except (TypeError, ValueError) as error:
            raise ValidationError("HUMAN_REVIEW_LIST_FILTER_INVALID") from error
        if len(safe_kinds) != len(kinds) or len(safe_states) != len(states):
            raise ValidationError("HUMAN_REVIEW_LIST_FILTER_INVALID")
        if confidence_lte is not None and (
            isinstance(confidence_lte, bool)
            or not isinstance(confidence_lte, (int, float))
            or not math.isfinite(float(confidence_lte))
            or not 0 <= float(confidence_lte) <= 1
        ):
            raise ValidationError("HUMAN_REVIEW_CONFIDENCE_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValidationError("HUMAN_REVIEW_LIST_LIMIT_INVALID")
        filter_binding = {
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "kinds": list(safe_kinds),
            "states": list(safe_states),
            "confidence_lte": float(confidence_lte) if confidence_lte is not None else None,
        }
        filter_digest = canonical_digest(filter_binding)
        after: tuple[float, str, str] | None = None
        if cursor is not None:
            decoded = self._decode_cursor(cursor)
            if set(decoded) != {"version", "filter_digest", "confidence", "created_at", "task_id"}:
                raise ValidationError("HUMAN_REVIEW_CURSOR_INVALID")
            if decoded.get("version") != "human-review-cursor-v1" or not hmac.compare_digest(
                str(decoded.get("filter_digest", "")), filter_digest
            ):
                raise ValidationError("HUMAN_REVIEW_CURSOR_SCOPE_INVALID")
            confidence = decoded.get("confidence")
            created_at = decoded.get("created_at")
            task_id = decoded.get("task_id")
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not isinstance(created_at, str)
                or not isinstance(task_id, str)
            ):
                raise ValidationError("HUMAN_REVIEW_CURSOR_INVALID")
            after = (float(confidence), created_at, require_resource_id(task_id, "task_id"))
        where = ["tenant_id=?", "project_id=?"]
        parameters: list[Any] = [context.tenant_id, context.project_id]
        if safe_kinds:
            where.append("target_kind IN (" + ",".join("?" for _ in safe_kinds) + ")")
            parameters.extend(safe_kinds)
        if safe_states:
            where.append("state IN (" + ",".join("?" for _ in safe_states) + ")")
            parameters.extend(safe_states)
        if confidence_lte is not None:
            where.append("confidence<=?")
            parameters.append(float(confidence_lte))
        if after is not None:
            where.append(
                "(confidence>? OR (confidence=? AND created_at>?) "
                "OR (confidence=? AND created_at=? AND task_id>?))"
            )
            parameters.extend((after[0], after[0], after[1], after[0], after[1], after[2]))
        where_sql = " AND ".join(where)
        with self._store._lock:
            self._store._require(self._store._connection, context, self._store.REVIEW)
            rows = self._store._connection.execute(
                f"""SELECT task_id,asset_id,target_kind,source_digest,confidence,
                           reason,state,current_correction_version,
                           current_correction_digest,effective_version,effective_digest,
                           claim_actor_id,claim_fence,claim_expires_at,version,
                           created_at,updated_at,closed_at
                      FROM human_review_tasks WHERE {where_sql}
                    ORDER BY confidence,created_at,task_id LIMIT ?""",
                (*parameters, limit + 1),
            ).fetchall()
            count_where = [item for item in where if not item.startswith("(confidence>?")]
            count_parameter_count = len(parameters) - (6 if after is not None else 0)
            total = int(
                self._store._connection.execute(
                    "SELECT count(*) FROM human_review_tasks WHERE " + " AND ".join(count_where),
                    tuple(parameters[:count_parameter_count]),
                ).fetchone()[0]
            )
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = self._encode_cursor(
                {
                    "version": "human-review-cursor-v1",
                    "filter_digest": filter_digest,
                    "confidence": float(last["confidence"]),
                    "created_at": last["created_at"],
                    "task_id": last["task_id"],
                }
            )
        return {
            "tasks": [self._task_summary(row) for row in page],
            "next_cursor": next_cursor,
            "total": total,
        }

    def get_review_task(
        self,
        context: TenantContext,
        *,
        task_id: str,
    ) -> dict[str, Any]:
        """Return one tenant-scoped full task; bulk list never carries large values."""

        safe_task_id = require_resource_id(task_id, "task_id")
        with self._store._lock:
            self._store._require(self._store._connection, context, self._store.REVIEW)
            task = self._scoped_task(self._store._connection, context, safe_task_id)
            return {"task": self._task_payload(task)}

    def get_current_correction(
        self,
        context: TenantContext,
        *,
        task_id: str,
    ) -> dict[str, Any]:
        """Return the exact current immutable correction after lineage checks.

        This is the authoritative response-loss recovery read for an ``edit``
        whose durable commit may have succeeded after the caller lost its
        response. Absence of a committed correction is an explicit conflict;
        callers must never infer a correction from task state alone.
        """

        safe_task_id = require_resource_id(task_id, "task_id")
        with self._store._lock:
            connection = self._store._connection
            self._store._require(connection, context, self._store.REVIEW)
            task = self._scoped_task(connection, context, safe_task_id)
            try:
                current_version = _safe_version(
                    task["current_correction_version"],
                    "HUMAN_REVIEW_CORRECTION_VERSION_DRIFT",
                    allow_zero=True,
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_VERSION_DRIFT") from error
            if current_version < 1:
                raise ConflictError("HUMAN_REVIEW_CURRENT_CORRECTION_NOT_AVAILABLE")
            correction = self._current_correction(connection, context, task)
            return {"correction": self._correction_payload(correction)}

    @staticmethod
    def _require_expected_task_version(row: sqlite3.Row, expected_version: int) -> None:
        if int(row["version"]) != expected_version:
            raise ConflictError(
                "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
                details={"expected_version": expected_version, "actual_version": int(row["version"])},
            )

    @staticmethod
    def _require_task_claim(
        row: sqlite3.Row,
        context: TenantContext,
        *,
        token_digest: str,
        claim_fence: int,
    ) -> None:
        now = utc_now()
        if (
            row["state"] not in {ReviewTaskState.CLAIMED.value, ReviewTaskState.EDITED.value}
            or row["claim_actor_id"] != context.actor_id
            or not isinstance(row["claim_token_digest"], str)
            or not hmac.compare_digest(row["claim_token_digest"], token_digest)
            or int(row["claim_fence"]) != claim_fence
            or str(row["claim_expires_at"] or "") <= now
        ):
            raise ConflictError("HUMAN_REVIEW_CLAIM_NOT_OWNED")

    def claim_review_task(
        self,
        context: TenantContext,
        *,
        task_id: str,
        expected_version: int,
        claim_token: str,
        lease_seconds: int,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_task_id = require_resource_id(task_id, "task_id")
        safe_version = _safe_version(expected_version, "HUMAN_REVIEW_EXPECTED_VERSION_INVALID")
        _raw_token, claim_digest = _token_digest(claim_token, "HUMAN_REVIEW_CLAIM_TOKEN_INVALID")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3_600:
            raise ValidationError("HUMAN_REVIEW_CLAIM_LEASE_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            replay = self._receipt(
                connection,
                context,
                operation="claim",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                row = self._scoped_task(connection, context, safe_task_id)
                replayed_task = replay.get("task")
                if (
                    not isinstance(replayed_task, dict)
                    or replayed_task.get("task_id") != safe_task_id
                    or row["claim_actor_id"] != context.actor_id
                    or not isinstance(row["claim_token_digest"], str)
                    or not hmac.compare_digest(row["claim_token_digest"], claim_digest)
                    or int(row["claim_fence"]) != replayed_task.get("claim_fence")
                    or str(row["claim_expires_at"] or "") <= now
                ):
                    raise ConflictError("HUMAN_REVIEW_CLAIM_REPLAY_STALE")
                return replay
            row = self._scoped_task(connection, context, safe_task_id)
            self._require_expected_task_version(row, safe_version)
            state = ReviewTaskState(row["state"])
            live = row["claim_actor_id"] is not None and str(row["claim_expires_at"] or "") > now
            same_owner = (
                live
                and row["claim_actor_id"] == context.actor_id
                and isinstance(row["claim_token_digest"], str)
                and hmac.compare_digest(row["claim_token_digest"], claim_digest)
            )
            if live and not same_owner:
                raise ConflictError(
                    "HUMAN_REVIEW_TASK_ALREADY_CLAIMED",
                    retryable=True,
                    details={"claim_expires_at": row["claim_expires_at"]},
                )
            if state not in {
                ReviewTaskState.QUEUED,
                ReviewTaskState.REOPENED,
                ReviewTaskState.CLAIMED,
                ReviewTaskState.EDITED,
            }:
                raise ConflictError("HUMAN_REVIEW_TASK_NOT_CLAIMABLE")
            if state in {ReviewTaskState.CLAIMED, ReviewTaskState.EDITED} and live and not same_owner:
                raise ConflictError("HUMAN_REVIEW_TASK_ALREADY_CLAIMED", retryable=True)
            next_state = (
                ReviewTaskState.EDITED.value
                if state is ReviewTaskState.EDITED
                else ReviewTaskState.CLAIMED.value
            )
            next_fence = int(row["claim_fence"]) + 1
            next_version = int(row["version"]) + 1
            changed = connection.execute(
                """UPDATE human_review_tasks
                      SET state=?,claim_actor_id=?,claim_token_digest=?,claim_fence=?,
                          claim_expires_at=?,version=?,updated_at=?
                    WHERE tenant_id=? AND project_id=? AND task_id=? AND version=?""",
                (
                    next_state,
                    context.actor_id,
                    claim_digest,
                    next_fence,
                    expires_at,
                    next_version,
                    now,
                    context.tenant_id,
                    context.project_id,
                    safe_task_id,
                    safe_version,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
            self._audit(
                connection,
                context,
                task_id=safe_task_id,
                event_type="review.claimed",
                prior_state=state.value,
                next_state=next_state,
                task_version=next_version,
                details={"claim_fence": next_fence, "claim_expires_at": expires_at},
            )
            updated = self._scoped_task(connection, context, safe_task_id)
            response = {"task": self._task_payload(updated)}
            return self._record_receipt(
                connection,
                context,
                operation="claim",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def edit_review_task(
        self,
        context: TenantContext,
        *,
        task_id: str,
        expected_version: int,
        expected_correction_version: int,
        claim_token: str,
        claim_fence: int,
        corrected_value: Any,
        reason: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_task_id = require_resource_id(task_id, "task_id")
        safe_version = _safe_version(expected_version, "HUMAN_REVIEW_EXPECTED_VERSION_INVALID")
        safe_parent = _safe_version(
            expected_correction_version,
            "HUMAN_REVIEW_EXPECTED_CORRECTION_VERSION_INVALID",
            allow_zero=True,
        )
        _safe_fence = _safe_version(claim_fence, "HUMAN_REVIEW_CLAIM_FENCE_INVALID")
        _raw_token, claim_digest = _token_digest(claim_token, "HUMAN_REVIEW_CLAIM_TOKEN_INVALID")
        safe_value, corrected_json, corrected_digest = self._content_json(
            corrected_value, "HUMAN_REVIEW_CORRECTED_VALUE_INVALID"
        )
        safe_reason = _required_text(reason, "HUMAN_REVIEW_REASON_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            replay = self._receipt(
                connection,
                context,
                operation="edit",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            task = self._scoped_task(connection, context, safe_task_id)
            self._require_expected_task_version(task, safe_version)
            self._require_task_claim(
                task,
                context,
                token_digest=claim_digest,
                claim_fence=_safe_fence,
            )
            if int(task["current_correction_version"]) != safe_parent:
                raise ConflictError(
                    "HUMAN_REVIEW_CORRECTION_VERSION_CONFLICT",
                    details={
                        "expected_version": safe_parent,
                        "actual_version": int(task["current_correction_version"]),
                    },
                )
            next_correction_version = safe_parent + 1
            original_value = self._decode_content(
                task["original_value_json"],
                task["original_value_digest"],
                "HUMAN_REVIEW_TASK_CORRUPT",
            )
            source_digest = normalize_sha256(task["source_digest"])
            if int(task["effective_version"]) > 0:
                projection = connection.execute(
                    """SELECT * FROM human_review_effective_projections
                        WHERE tenant_id=? AND project_id=? AND task_id=?
                        ORDER BY channel LIMIT 1""",
                    (context.tenant_id, context.project_id, safe_task_id),
                ).fetchone()
                if projection is None:
                    raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_MISSING")
                original_value = self._decode_content(
                    projection["effective_value_json"],
                    projection["effective_value_digest"],
                    "HUMAN_REVIEW_EFFECTIVE_PROJECTION_CORRUPT",
                )
                source_digest = normalize_sha256(projection["effective_value_digest"])
            _original_copy, original_json, original_digest = self._content_json(
                original_value, "HUMAN_REVIEW_ORIGINAL_VALUE_INVALID"
            )
            target = self._decode_content(
                task["target_json"], task["target_digest"], "HUMAN_REVIEW_TASK_CORRUPT"
            )
            created_at = utc_now()
            correction_id = "review-correction-" + canonical_digest(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "task_id": safe_task_id,
                    "correction_version": next_correction_version,
                    "request_digest": f"sha256:{safe_request_digest}",
                }
            )[:32]
            correction_body = {
                "correction_id": correction_id,
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "task_id": safe_task_id,
                "correction_version": next_correction_version,
                "parent_correction_version": safe_parent,
                "target_kind": task["target_kind"],
                "target": target,
                "original_value": original_value,
                "corrected_value": safe_value,
                "source_digest": f"sha256:{source_digest}",
                "actor_id": context.actor_id,
                "reason": safe_reason,
                "created_at": created_at,
            }
            correction_digest = normalize_sha256(content_contract_digest(correction_body))
            connection.execute(
                """INSERT INTO human_review_correction_versions (
                    correction_id,tenant_id,project_id,task_id,correction_version,
                    parent_correction_version,target_kind,target_json,original_value_json,
                    original_value_digest,corrected_value_json,corrected_value_digest,
                    source_digest,correction_digest,actor_id,reason,request_digest,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    correction_id,
                    context.tenant_id,
                    context.project_id,
                    safe_task_id,
                    next_correction_version,
                    safe_parent,
                    task["target_kind"],
                    task["target_json"],
                    original_json,
                    original_digest,
                    corrected_json,
                    corrected_digest,
                    source_digest,
                    correction_digest,
                    context.actor_id,
                    safe_reason,
                    safe_request_digest,
                    created_at,
                ),
            )
            next_task_version = safe_version + 1
            changed = connection.execute(
                """UPDATE human_review_tasks
                      SET state='EDITED',current_correction_version=?,
                          current_correction_digest=?,version=?,updated_at=?
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                      AND version=? AND claim_fence=? AND claim_token_digest=?""",
                (
                    next_correction_version,
                    correction_digest,
                    next_task_version,
                    created_at,
                    context.tenant_id,
                    context.project_id,
                    safe_task_id,
                    safe_version,
                    _safe_fence,
                    claim_digest,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
            self._audit(
                connection,
                context,
                task_id=safe_task_id,
                event_type="correction.edited",
                prior_state=task["state"],
                next_state=ReviewTaskState.EDITED.value,
                task_version=next_task_version,
                details={
                    "correction_id": correction_id,
                    "correction_version": next_correction_version,
                    "source_digest": f"sha256:{source_digest}",
                    "correction_digest": f"sha256:{correction_digest}",
                },
            )
            correction_row = connection.execute(
                "SELECT * FROM human_review_correction_versions WHERE correction_id=?",
                (correction_id,),
            ).fetchone()
            updated_task = self._scoped_task(connection, context, safe_task_id)
            response = {
                "correction": self._correction_payload(correction_row),
                "task": self._task_payload(updated_task),
            }
            return self._record_receipt(
                connection,
                context,
                operation="edit",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @classmethod
    def _current_correction(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        task: sqlite3.Row,
    ) -> sqlite3.Row:
        code = "HUMAN_REVIEW_CORRECTION_VERSION_DRIFT"
        try:
            version = _safe_version(task["current_correction_version"], code)
            task_digest = normalize_sha256(task["current_correction_digest"])
            task_source_digest = normalize_sha256(task["source_digest"])
            task_payload = cls._task_payload(task)
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        if version < 1:
            raise ConflictError("HUMAN_REVIEW_CORRECTION_REQUIRED")
        row = connection.execute(
            """SELECT * FROM human_review_correction_versions
                WHERE tenant_id=? AND project_id=? AND task_id=?
                  AND correction_version=?""",
            (context.tenant_id, context.project_id, task["task_id"], version),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise IntegrityError(code)
        correction_payload = cls._correction_payload(row)
        try:
            correction_digest = normalize_sha256(correction_payload["correction_digest"])
            correction_source_digest = normalize_sha256(correction_payload["source_digest"])
            correction_original_json = content_contract_json(
                correction_payload["original_value"]
            )
            correction_original_digest = normalize_sha256(
                content_contract_digest(correction_payload["original_value"])
            )
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        if (
            not hmac.compare_digest(correction_digest, task_digest)
            or correction_payload["tenant_id"] != context.tenant_id
            or correction_payload["project_id"] != context.project_id
            or correction_payload["task_id"] != task["task_id"]
            or correction_payload["correction_version"] != version
            or correction_payload["target_kind"] != task_payload["target_kind"]
            or content_contract_json(correction_payload["target"]) != task["target_json"]
        ):
            raise IntegrityError(code)

        # An edit may use either the immutable initial source or a previously
        # materialized correction as its source. Do not trust an arbitrary
        # digest merely because it was included in the correction body.
        if hmac.compare_digest(correction_source_digest, task_source_digest):
            try:
                task_original_digest = normalize_sha256(
                    task["original_value_digest"]
                )
            except (TypeError, ValueError, ValidationError) as error:
                raise IntegrityError(code) from error
            if (
                correction_original_json != task["original_value_json"]
                or not hmac.compare_digest(
                    correction_original_digest, task_original_digest
                )
            ):
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_DRIFT")
        else:
            prior_rows = connection.execute(
                """SELECT * FROM human_review_correction_versions
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                      AND correction_version<? AND corrected_value_digest=?
                    ORDER BY correction_version DESC""",
                (
                    context.tenant_id,
                    context.project_id,
                    task["task_id"],
                    version,
                    correction_source_digest,
                ),
            ).fetchall()
            lineage_valid = False
            for prior_row in prior_rows:
                prior_payload = cls._correction_payload(prior_row)
                if (
                    prior_payload["target_kind"] != task_payload["target_kind"]
                    or content_contract_json(prior_payload["target"])
                    != task["target_json"]
                    or prior_row["corrected_value_json"]
                    != correction_original_json
                    or normalize_sha256(prior_row["corrected_value_digest"])
                    != correction_source_digest
                    or not hmac.compare_digest(
                        correction_original_digest, correction_source_digest
                    )
                ):
                    continue
                approvals = connection.execute(
                    """SELECT * FROM human_review_decisions
                        WHERE tenant_id=? AND project_id=? AND task_id=?
                          AND decision='APPROVE' AND correction_version=?
                          AND correction_digest=?
                        ORDER BY decision_version""",
                    (
                        context.tenant_id,
                        context.project_id,
                        task["task_id"],
                        prior_payload["correction_version"],
                        normalize_sha256(prior_payload["correction_digest"]),
                    ),
                ).fetchall()
                for approval in approvals:
                    approval_payload = cls._decision_payload(approval)
                    try:
                        approval_reservation = cls._decision_reservation(
                            connection,
                            context,
                            decision_id=approval_payload["decision_id"],
                        )
                    except (IntegrityError, NotFoundError):
                        continue
                    if (
                        cls._reservation_payload(approval_reservation)["state"]
                        != ReviewHeadReservationState.APPLIED.value
                    ):
                        continue
                    propagation_rows = connection.execute(
                        """SELECT * FROM human_review_propagation_tasks
                            WHERE tenant_id=? AND project_id=? AND task_id=?
                              AND decision_id=? ORDER BY channel""",
                        (
                            context.tenant_id,
                            context.project_id,
                            task["task_id"],
                            approval_payload["decision_id"],
                        ),
                    ).fetchall()
                    if (
                        len(propagation_rows) != len(_PROPAGATION_CHANNELS)
                        or tuple(row["channel"] for row in propagation_rows)
                        != tuple(sorted(_PROPAGATION_CHANNELS))
                    ):
                        continue
                    propagations_valid = True
                    for propagation_row in propagation_rows:
                        propagation = cls._propagation_payload(propagation_row)
                        payload = propagation["payload"]
                        if (
                            not isinstance(payload, dict)
                            or propagation["state"]
                            != ReviewPropagationState.SUCCEEDED.value
                            or propagation["direction"]
                            != ReviewPropagationDirection.APPLY.value
                            or propagation["correction_version"]
                            != prior_payload["correction_version"]
                            or payload.get("task_id") != task["task_id"]
                            or payload.get("decision_id")
                            != approval_payload["decision_id"]
                            or payload.get("correction_digest")
                            != prior_payload["correction_digest"]
                            or payload.get("target_kind")
                            != task_payload["target_kind"]
                            or content_contract_json(payload.get("target"))
                            != task["target_json"]
                            or payload.get("effective_value_digest")
                            != f"sha256:{correction_source_digest}"
                            or payload.get("source_digest")
                            != prior_payload["source_digest"]
                        ):
                            propagations_valid = False
                            break
                    if propagations_valid:
                        lineage_valid = True
                        break
                if lineage_valid:
                    break
            if not lineage_valid:
                raise IntegrityError("HUMAN_REVIEW_CORRECTION_SOURCE_DRIFT")
        return row

    @classmethod
    def _effective_source(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        task: sqlite3.Row,
    ) -> tuple[int, Any, str]:
        if int(task["effective_version"]) == 0:
            value = cls._decode_content(
                task["original_value_json"],
                task["original_value_digest"],
                "HUMAN_REVIEW_TASK_CORRUPT",
            )
            return 0, value, normalize_sha256(task["original_value_digest"])
        rows = connection.execute(
            """SELECT * FROM human_review_effective_projections
                WHERE tenant_id=? AND project_id=? AND task_id=? ORDER BY channel""",
            (context.tenant_id, context.project_id, task["task_id"]),
        ).fetchall()
        if len(rows) != len(_PROPAGATION_CHANNELS):
            raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_INCOMPLETE")
        first = rows[0]
        value = cls._decode_content(
            first["effective_value_json"],
            first["effective_value_digest"],
            "HUMAN_REVIEW_EFFECTIVE_PROJECTION_CORRUPT",
        )
        digest = normalize_sha256(first["effective_value_digest"])
        if any(
            int(row["correction_version"]) != int(task["effective_version"])
            or row["effective_value_json"] != first["effective_value_json"]
            or row["effective_value_digest"] != first["effective_value_digest"]
            for row in rows
        ):
            raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_DRIFT")
        if task["effective_digest"] is None or not hmac.compare_digest(
            normalize_sha256(task["effective_digest"]), digest
        ):
            raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_DRIFT")
        return int(task["effective_version"]), value, digest

    def _reserve_target_head(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        task: sqlite3.Row,
        correction: sqlite3.Row,
        action: ReviewDecisionAction,
        decision_id: str,
        parent_reservation: sqlite3.Row | None = None,
    ) -> sqlite3.Row:
        """Acquire the one durable fence for an exact authoritative head.

        This insert is deliberately performed before the decision and its four
        propagation rows.  The deferred decision foreign key makes the entire
        transaction atomic while the unique head-version key elects one winner.
        """

        code = "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_BINDING_INVALID"
        if action not in {ReviewDecisionAction.APPROVE, ReviewDecisionAction.REVERT}:
            raise IntegrityError(code)
        task_payload = self._task_payload(task)
        correction_payload = self._correction_payload(correction)
        source_ref = self._decode_content(
            task["source_ref_json"], task["source_ref_digest"], code
        )
        if (
            not isinstance(source_ref, dict)
            or set(source_ref) != _SOURCE_REF_V2_FIELDS
            or source_ref.get("schema_version") != "human-review-source-ref-v2"
            or source_ref.get("content_id") != task["asset_id"]
            or source_ref.get("target_kind") != task["target_kind"]
            or source_ref.get("target_digest")
            != f"sha256:{normalize_sha256(task['target_digest'])}"
            or source_ref.get("original_value_digest_contract")
            != CANONICAL_JSON_SHA256_CONTRACT
            or correction_payload["task_id"] != task["task_id"]
            or correction_payload["target_kind"] != task_payload["target_kind"]
            or content_contract_json(correction_payload["target"])
            != task["target_json"]
        ):
            raise IntegrityError(code)
        asset = self._store._scoped_asset(
            connection, context, require_resource_id(task["asset_id"], "asset_id")
        )
        self._store._require_human_review_asset_state(asset)
        current = self._store._human_review_current(connection, context, asset)
        try:
            content_version = _safe_version(source_ref["content_version"], code)
            if int(asset["version"]) != content_version:
                raise ConflictError("HUMAN_REVIEW_SOURCE_DRIFT")
            target_kind = ReviewTargetKind(task["target_kind"])
            target_digest = normalize_sha256(task["target_digest"])
        except ConflictError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        head, _snapshot, _value = self._authoritative_head(
            connection,
            context,
            asset_id=task["asset_id"],
            asset_version=content_version,
            target_kind=target_kind,
            target_json=task["target_json"],
            target_digest=target_digest,
        )
        _summary, detail = self._source_head_documents(
            connection,
            context,
            asset=asset,
            current=current,
            head=head,
        )
        current_ref = detail["source_ref"]
        if action is ReviewDecisionAction.APPROVE:
            if parent_reservation is not None:
                raise IntegrityError(code)
            if content_contract_json(current_ref) != task["source_ref_json"]:
                raise ConflictError(
                    "HUMAN_REVIEW_SOURCE_DRIFT",
                    details={
                        "expected_head_version": source_ref["head_version"],
                        "actual_head_version": current_ref["head_version"],
                    },
                )
            parent_reservation_id: str | None = None
        else:
            if parent_reservation is None:
                raise IntegrityError(code)
            parent = self._reservation_payload(parent_reservation)
            if (
                parent["decision_action"] != ReviewDecisionAction.APPROVE.value
                or parent["state"] != ReviewHeadReservationState.APPLIED.value
                or parent["task_id"] != task["task_id"]
                or parent["correction_version"]
                != int(correction["correction_version"])
                or parent["correction_digest"]
                != f"sha256:{normalize_sha256(correction['correction_digest'])}"
                or parent["materialized_head_version"]
                != int(current_ref["head_version"])
                or head["source_decision_id"] != parent["decision_id"]
                or head["direction"] != ReviewPropagationDirection.APPLY.value
            ):
                raise ConflictError("HUMAN_REVIEW_REVERT_RESERVATION_INVALID")
            parent_reservation_id = parent["reservation_id"]
        try:
            asset_content_digest = normalize_sha256(current_ref["content_digest"])
            asset_sha256 = normalize_sha256(current_ref["asset_sha256"])
            snapshot_id = require_resource_id(current_ref["snapshot_id"], "snapshot_id")
            snapshot_digest = normalize_sha256(current_ref["snapshot_digest"])
            reserved_head_version = _safe_version(current_ref["head_version"], code)
            reserved_head_value_digest = normalize_sha256(
                current_ref["head_value_digest"]
            )
            correction_version = _safe_version(correction["correction_version"], code)
            correction_digest = normalize_sha256(correction["correction_digest"])
            correction_source_digest = normalize_sha256(correction["source_digest"])
            source_ref_digest = normalize_sha256(task["source_ref_digest"])
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise IntegrityError(code) from error
        reservation_fence = reserved_head_version
        binding = {
            "schema_version": "human-review-target-head-reservation-binding-v1",
            "tenant_id": context.tenant_id,
            "project_id": context.project_id,
            "asset_id": task["asset_id"],
            "asset_version": content_version,
            "asset_content_digest": f"sha256:{asset_content_digest}",
            "asset_sha256": f"sha256:{asset_sha256}",
            "target_kind": target_kind.value,
            "target_digest": f"sha256:{target_digest}",
            "snapshot_id": snapshot_id,
            "snapshot_digest": f"sha256:{snapshot_digest}",
            "reserved_head_version": reserved_head_version,
            "reserved_head_value_digest": f"sha256:{reserved_head_value_digest}",
            "task_id": task["task_id"],
            "decision_id": decision_id,
            "decision_action": action.value,
            "correction_version": correction_version,
            "correction_digest": f"sha256:{correction_digest}",
            "source_digest": f"sha256:{correction_source_digest}",
            "source_ref_digest": f"sha256:{source_ref_digest}",
            "parent_reservation_id": parent_reservation_id,
            "reservation_fence": reservation_fence,
        }
        binding_digest = normalize_sha256(canonical_digest(binding))
        reservation_id = "review-reservation-" + binding_digest[:32]
        occupied = connection.execute(
            """SELECT reservation_id,reservation_fence,state
                 FROM human_review_target_head_reservations
                WHERE tenant_id=? AND project_id=? AND asset_id=? AND asset_version=?
                  AND target_kind=? AND target_digest=? AND reserved_head_version=?""",
            (
                context.tenant_id,
                context.project_id,
                task["asset_id"],
                content_version,
                target_kind.value,
                target_digest,
                reserved_head_version,
            ),
        ).fetchone()
        if occupied is not None:
            raise ConflictError(
                "HUMAN_REVIEW_TARGET_HEAD_RESERVED",
                details={
                    "head_version": reserved_head_version,
                    "reservation_fence": int(occupied["reservation_fence"]),
                    "reservation_state": occupied["state"],
                },
            )
        now = utc_now()
        try:
            connection.execute(
                """INSERT INTO human_review_target_head_reservations (
                    reservation_id,tenant_id,project_id,asset_id,asset_version,
                    asset_content_digest,asset_sha256,target_kind,target_digest,
                    snapshot_id,snapshot_digest,reserved_head_version,
                    reserved_head_value_digest,task_id,decision_id,decision_action,
                    correction_version,correction_digest,source_digest,source_ref_digest,
                    parent_reservation_id,reservation_fence,binding_digest,state,
                    state_version,materialized_head_version,failure_code,created_at,
                    updated_at,completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                          'PROPAGATING',1,NULL,NULL,?,?,NULL)""",
                (
                    reservation_id,
                    context.tenant_id,
                    context.project_id,
                    task["asset_id"],
                    content_version,
                    asset_content_digest,
                    asset_sha256,
                    target_kind.value,
                    target_digest,
                    snapshot_id,
                    snapshot_digest,
                    reserved_head_version,
                    reserved_head_value_digest,
                    task["task_id"],
                    decision_id,
                    action.value,
                    correction_version,
                    correction_digest,
                    correction_source_digest,
                    source_ref_digest,
                    parent_reservation_id,
                    reservation_fence,
                    binding_digest,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ConflictError("HUMAN_REVIEW_TARGET_HEAD_RESERVED") from error
        reservation = connection.execute(
            """SELECT * FROM human_review_target_head_reservations
                WHERE tenant_id=? AND project_id=? AND reservation_id=?""",
            (context.tenant_id, context.project_id, reservation_id),
        ).fetchone()
        if not isinstance(reservation, sqlite3.Row):
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_MISSING")
        self._reservation_payload(reservation)
        return reservation

    @classmethod
    def _decision_id(
        cls,
        context: TenantContext,
        *,
        task_id: str,
        action: ReviewDecisionAction,
        decision_version: int,
        request_digest: str,
    ) -> str:
        return "review-decision-" + canonical_digest(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "task_id": task_id,
                "decision": action.value,
                "decision_version": decision_version,
                "request_digest": f"sha256:{request_digest}",
            }
        )[:32]

    @classmethod
    def _insert_decision(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        task: sqlite3.Row,
        action: ReviewDecisionAction,
        next_state: ReviewTaskState,
        correction: sqlite3.Row | None,
        reason: str,
        request_digest: str,
        decision_version: int,
    ) -> sqlite3.Row:
        correction_version = int(correction["correction_version"]) if correction is not None else None
        correction_digest = (
            normalize_sha256(correction["correction_digest"])
            if correction is not None
            else None
        )
        source_digest = (
            normalize_sha256(correction["source_digest"])
            if correction is not None
            else normalize_sha256(task["source_digest"])
        )
        decision_id = cls._decision_id(
            context,
            task_id=task["task_id"],
            action=action,
            decision_version=decision_version,
            request_digest=request_digest,
        )
        connection.execute(
            """INSERT INTO human_review_decisions (
                decision_id,tenant_id,project_id,task_id,decision_version,decision,
                prior_state,next_state,correction_version,correction_digest,
                source_digest,actor_id,reason,request_digest,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                decision_id,
                context.tenant_id,
                context.project_id,
                task["task_id"],
                decision_version,
                action.value,
                task["state"],
                next_state.value,
                correction_version,
                correction_digest,
                source_digest,
                context.actor_id,
                reason,
                request_digest,
                utc_now(),
            ),
        )
        decision = connection.execute(
            "SELECT * FROM human_review_decisions WHERE decision_id=?",
            (decision_id,),
        ).fetchone()
        if not isinstance(decision, sqlite3.Row):
            raise IntegrityError("HUMAN_REVIEW_DECISION_MISSING")
        return decision

    @classmethod
    def _create_propagations(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        task: sqlite3.Row,
        decision: sqlite3.Row,
        correction: sqlite3.Row,
        reservation: sqlite3.Row,
        direction: ReviewPropagationDirection,
        effective_value: Any,
        effective_digest: str,
        prior_effective_version: int,
        prior_effective_value: Any,
        prior_effective_digest: str,
    ) -> list[sqlite3.Row]:
        target = cls._decode_content(
            task["target_json"], task["target_digest"], "HUMAN_REVIEW_TASK_CORRUPT"
        )
        reservation_payload = cls._reservation_payload(reservation)
        if (
            reservation_payload["task_id"] != task["task_id"]
            or reservation_payload["decision_id"] != decision["decision_id"]
            or reservation_payload["correction_version"]
            != int(correction["correction_version"])
            or reservation_payload["correction_digest"]
            != f"sha256:{normalize_sha256(correction['correction_digest'])}"
            or reservation_payload["decision_action"]
            != (
                ReviewDecisionAction.APPROVE.value
                if direction is ReviewPropagationDirection.APPLY
                else ReviewDecisionAction.REVERT.value
            )
            or reservation_payload["state"]
            != ReviewHeadReservationState.PROPAGATING.value
        ):
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CORRUPT")
        now = utc_now()
        rows: list[sqlite3.Row] = []
        for channel in _PROPAGATION_CHANNELS:
            payload = {
                "schema_version": "human-review-propagation-v2",
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "task_id": task["task_id"],
                "decision_id": decision["decision_id"],
                "correction_version": int(correction["correction_version"]),
                "correction_digest": f"sha256:{normalize_sha256(correction['correction_digest'])}",
                "channel": channel,
                "direction": direction.value,
                "target_kind": task["target_kind"],
                "target": target,
                "effective_value": bounded_review_json(effective_value),
                "effective_value_digest": f"sha256:{normalize_sha256(effective_digest)}",
                "source_digest": f"sha256:{normalize_sha256(correction['source_digest'])}",
                "prior_effective_version": prior_effective_version,
                "prior_effective_value": bounded_review_json(prior_effective_value),
                "prior_effective_digest": f"sha256:{normalize_sha256(prior_effective_digest)}",
                "reservation_id": reservation_payload["reservation_id"],
                "reservation_fence": reservation_payload["reservation_fence"],
                "reservation_binding_digest": reservation_payload["binding_digest"],
            }
            _payload_copy, payload_json, payload_digest = cls._content_json(
                payload, "HUMAN_REVIEW_PROPAGATION_PAYLOAD_INVALID"
            )
            propagation_id = "review-propagation-" + canonical_digest(
                {
                    "decision_id": decision["decision_id"],
                    "channel": channel,
                    "direction": direction.value,
                    "payload_digest": f"sha256:{payload_digest}",
                }
            )[:32]
            connection.execute(
                """INSERT INTO human_review_propagation_tasks (
                    propagation_id,tenant_id,project_id,task_id,decision_id,
                    correction_version,channel,direction,payload_json,payload_digest,
                    state,claim_capability_id,claim_owner_digest,claim_fence,
                    claim_expires_at,dispatch_started_at,result_json,result_digest,
                    failure_code,reconciliation_required,version,created_at,updated_at,
                    completed_at,reconciled_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',NULL,NULL,0,NULL,NULL,NULL,NULL,
                          NULL,0,1,?,?,NULL,NULL)""",
                (
                    propagation_id,
                    context.tenant_id,
                    context.project_id,
                    task["task_id"],
                    decision["decision_id"],
                    int(correction["correction_version"]),
                    channel,
                    direction.value,
                    payload_json,
                    payload_digest,
                    now,
                    now,
                ),
            )
            rows.append(
                connection.execute(
                    "SELECT * FROM human_review_propagation_tasks WHERE propagation_id=?",
                    (propagation_id,),
                ).fetchone()
            )
        return rows

    @classmethod
    def _decision_reservation(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        decision_id: str,
        require_propagations: bool = True,
    ) -> sqlite3.Row:
        """Validate one reservation against its decision, task and propagation batch."""

        code = "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CORRUPT"
        reservation = cls._scoped_reservation_by_decision(
            connection, context, decision_id
        )
        reservation_payload = cls._reservation_payload(reservation)
        decision = connection.execute(
            """SELECT * FROM human_review_decisions
                WHERE tenant_id=? AND project_id=? AND decision_id=?""",
            (context.tenant_id, context.project_id, decision_id),
        ).fetchone()
        task = (
            cls._scoped_task(connection, context, reservation_payload["task_id"])
            if decision is not None
            else None
        )
        correction = (
            connection.execute(
                """SELECT * FROM human_review_correction_versions
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                      AND correction_version=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    reservation_payload["task_id"],
                    reservation_payload["correction_version"],
                ),
            ).fetchone()
            if task is not None
            else None
        )
        expected_direction = (
            ReviewPropagationDirection.APPLY.value
            if reservation_payload["decision_action"]
            == ReviewDecisionAction.APPROVE.value
            else ReviewPropagationDirection.REVERT.value
        )
        if (
            decision is None
            or task is None
            or correction is None
            or decision["task_id"] != reservation_payload["task_id"]
            or decision["decision"] != reservation_payload["decision_action"]
            or int(decision["correction_version"])
            != reservation_payload["correction_version"]
            or normalize_sha256(decision["correction_digest"])
            != normalize_sha256(reservation_payload["correction_digest"])
            or normalize_sha256(decision["source_digest"])
            != normalize_sha256(reservation_payload["source_digest"])
            or correction["task_id"] != reservation_payload["task_id"]
            or normalize_sha256(correction["correction_digest"])
            != normalize_sha256(reservation_payload["correction_digest"])
            or normalize_sha256(correction["source_digest"])
            != normalize_sha256(reservation_payload["source_digest"])
            or normalize_sha256(task["source_ref_digest"])
            != normalize_sha256(reservation_payload["source_ref_digest"])
            or task["asset_id"] != reservation_payload["asset_id"]
            or task["target_kind"] != reservation_payload["target_kind"]
            or normalize_sha256(task["target_digest"])
            != normalize_sha256(reservation_payload["target_digest"])
        ):
            raise IntegrityError(code)
        if reservation_payload["parent_reservation_id"] is not None:
            parent = connection.execute(
                """SELECT * FROM human_review_target_head_reservations
                    WHERE tenant_id=? AND project_id=? AND reservation_id=?""",
                (
                    context.tenant_id,
                    context.project_id,
                    reservation_payload["parent_reservation_id"],
                ),
            ).fetchone()
            if parent is None:
                raise IntegrityError(code)
            parent_payload = cls._reservation_payload(parent)
            if (
                parent_payload["decision_action"]
                != ReviewDecisionAction.APPROVE.value
                or parent_payload["task_id"] != reservation_payload["task_id"]
                or parent_payload["correction_version"]
                != reservation_payload["correction_version"]
                or parent_payload["materialized_head_version"]
                != reservation_payload["reserved_head_version"]
                or parent_payload["state"]
                != ReviewHeadReservationState.APPLIED.value
            ):
                raise IntegrityError(code)
        if not require_propagations:
            return reservation
        rows = connection.execute(
            """SELECT * FROM human_review_propagation_tasks
                WHERE tenant_id=? AND project_id=? AND decision_id=? ORDER BY channel""",
            (context.tenant_id, context.project_id, decision_id),
        ).fetchall()
        if (
            len(rows) != len(_PROPAGATION_CHANNELS)
            or {row["channel"] for row in rows} != set(_PROPAGATION_CHANNELS)
        ):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_SET_INVALID")
        for row in rows:
            payload = cls._decode_content(
                row["payload_json"],
                row["payload_digest"],
                "HUMAN_REVIEW_PROPAGATION_CORRUPT",
            )
            if (
                not isinstance(payload, dict)
                or set(payload) != _PROPAGATION_PAYLOAD_V2_FIELDS
                or payload.get("schema_version") != "human-review-propagation-v2"
                or payload.get("tenant_id") != context.tenant_id
                or payload.get("project_id") != context.project_id
                or payload.get("task_id") != reservation_payload["task_id"]
                or payload.get("decision_id") != decision_id
                or payload.get("channel") != row["channel"]
                or payload.get("direction") != expected_direction
                or row["direction"] != expected_direction
                or payload.get("correction_version")
                != reservation_payload["correction_version"]
                or int(row["correction_version"])
                != reservation_payload["correction_version"]
                or payload.get("correction_digest")
                != reservation_payload["correction_digest"]
                or payload.get("source_digest")
                != reservation_payload["source_digest"]
                or payload.get("reservation_id")
                != reservation_payload["reservation_id"]
                or payload.get("reservation_fence")
                != reservation_payload["reservation_fence"]
                or payload.get("reservation_binding_digest")
                != reservation_payload["binding_digest"]
            ):
                raise IntegrityError("HUMAN_REVIEW_PROPAGATION_RESERVATION_DRIFT")
        return reservation

    @classmethod
    def _propagation_reservation(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        propagation: sqlite3.Row,
    ) -> sqlite3.Row:
        reservation = cls._decision_reservation(
            connection,
            context,
            decision_id=propagation["decision_id"],
        )
        payload = cls._decode_content(
            propagation["payload_json"],
            propagation["payload_digest"],
            "HUMAN_REVIEW_PROPAGATION_CORRUPT",
        )
        reservation_payload = cls._reservation_payload(reservation)
        if (
            payload.get("reservation_id") != reservation_payload["reservation_id"]
            or payload.get("reservation_fence")
            != reservation_payload["reservation_fence"]
            or payload.get("reservation_binding_digest")
            != reservation_payload["binding_digest"]
        ):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_RESERVATION_DRIFT")
        return reservation

    @classmethod
    def _set_reservation_state(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        reservation: sqlite3.Row,
        state: ReviewHeadReservationState,
        failure_code: str | None = None,
        materialized_head_version: int | None = None,
    ) -> sqlite3.Row:
        current = cls._reservation_payload(reservation)
        current_state = ReviewHeadReservationState(current["state"])
        if current_state in _RESERVATION_TERMINAL_STATES:
            if (
                current_state is not state
                or current["failure_code"] != failure_code
                or current["materialized_head_version"]
                != materialized_head_version
            ):
                raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_TERMINAL")
            return reservation
        safe_failure: str | None
        completed_at: str | None
        if state is ReviewHeadReservationState.FAILED:
            if failure_code is None:
                raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATE_INVALID")
            safe_failure = require_resource_id(failure_code, "failure_code")
            completed_at = utc_now()
        else:
            if failure_code is not None:
                raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATE_INVALID")
            safe_failure = None
            completed_at = (
                utc_now()
                if state
                in {
                    ReviewHeadReservationState.APPLIED,
                    ReviewHeadReservationState.REVERTED,
                }
                else None
            )
        if state in {
            ReviewHeadReservationState.APPLIED,
            ReviewHeadReservationState.REVERTED,
        }:
            expected_terminal = (
                ReviewHeadReservationState.APPLIED
                if current["decision_action"] == ReviewDecisionAction.APPROVE.value
                else ReviewHeadReservationState.REVERTED
            )
            if (
                state is not expected_terminal
                or materialized_head_version
                != current["reserved_head_version"] + 1
            ):
                raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATE_INVALID")
        elif materialized_head_version is not None:
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_STATE_INVALID")
        if (
            current_state is state
            and current["failure_code"] == safe_failure
            and current["materialized_head_version"] == materialized_head_version
        ):
            return reservation
        now = completed_at or utc_now()
        changed = connection.execute(
            """UPDATE human_review_target_head_reservations
                  SET state=?,state_version=state_version+1,
                      materialized_head_version=?,failure_code=?,updated_at=?,
                      completed_at=?
                WHERE tenant_id=? AND project_id=? AND reservation_id=?
                  AND state_version=? AND state=?""",
            (
                state.value,
                materialized_head_version,
                safe_failure,
                now,
                completed_at,
                context.tenant_id,
                context.project_id,
                current["reservation_id"],
                current["state_version"],
                current_state.value,
            ),
        ).rowcount
        if changed != 1:
            raise ConflictError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CONFLICT")
        updated = connection.execute(
            """SELECT * FROM human_review_target_head_reservations
                WHERE tenant_id=? AND project_id=? AND reservation_id=?""",
            (
                context.tenant_id,
                context.project_id,
                current["reservation_id"],
            ),
        ).fetchone()
        if not isinstance(updated, sqlite3.Row):
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_MISSING")
        cls._reservation_payload(updated)
        return updated

    @classmethod
    def _sync_reservation_state(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        decision_id: str,
    ) -> sqlite3.Row:
        reservation = cls._decision_reservation(
            connection, context, decision_id=decision_id
        )
        current = cls._reservation_payload(reservation)
        if ReviewHeadReservationState(current["state"]) in {
            ReviewHeadReservationState.FAILED,
            ReviewHeadReservationState.APPLIED,
            ReviewHeadReservationState.REVERTED,
        }:
            return reservation
        rows = connection.execute(
            """SELECT * FROM human_review_propagation_tasks
                WHERE tenant_id=? AND project_id=? AND decision_id=? ORDER BY channel""",
            (context.tenant_id, context.project_id, decision_id),
        ).fetchall()
        failed = next(
            (row for row in rows if row["state"] == ReviewPropagationState.FAILED.value),
            None,
        )
        if failed is not None:
            return cls._set_reservation_state(
                connection,
                context,
                reservation=reservation,
                state=ReviewHeadReservationState.FAILED,
                failure_code=failed["failure_code"] or "PROPAGATION_FAILED",
            )
        next_state = (
            ReviewHeadReservationState.UNKNOWN
            if any(
                row["state"] == ReviewPropagationState.UNKNOWN.value for row in rows
            )
            else ReviewHeadReservationState.PROPAGATING
        )
        return cls._set_reservation_state(
            connection,
            context,
            reservation=reservation,
            state=next_state,
        )

    def decide_review_task(
        self,
        context: TenantContext,
        *,
        task_id: str,
        action: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        request_digest: str,
        claim_token: str | None = None,
        claim_fence: int | None = None,
    ) -> dict[str, Any]:
        safe_task_id = require_resource_id(task_id, "task_id")
        try:
            safe_action = ReviewDecisionAction(action)
        except (TypeError, ValueError) as error:
            raise ValidationError("HUMAN_REVIEW_DECISION_INVALID") from error
        safe_version = _safe_version(expected_version, "HUMAN_REVIEW_EXPECTED_VERSION_INVALID")
        safe_reason = _required_text(reason, "HUMAN_REVIEW_REASON_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        operation = safe_action.value.lower()
        claim_digest: str | None = None
        safe_fence: int | None = None
        if safe_action in {ReviewDecisionAction.APPROVE, ReviewDecisionAction.REJECT}:
            _raw_token, claim_digest = _token_digest(
                claim_token, "HUMAN_REVIEW_CLAIM_TOKEN_INVALID"
            )
            safe_fence = _safe_version(claim_fence, "HUMAN_REVIEW_CLAIM_FENCE_INVALID")
        elif claim_token is not None or claim_fence is not None:
            raise ValidationError("HUMAN_REVIEW_DECISION_FIELDS_INVALID")
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.REVIEW)
            replay = self._receipt(
                connection,
                context,
                operation=operation,
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            task = self._scoped_task(connection, context, safe_task_id)
            self._require_expected_task_version(task, safe_version)
            state = ReviewTaskState(task["state"])
            correction: sqlite3.Row | None = None
            reservation: sqlite3.Row | None = None
            propagations: list[sqlite3.Row] = []
            now = utc_now()
            next_task_version = safe_version + 1
            if safe_action is ReviewDecisionAction.APPROVE:
                if state is not ReviewTaskState.EDITED:
                    raise ConflictError("HUMAN_REVIEW_APPROVE_STATE_INVALID")
                assert claim_digest is not None and safe_fence is not None
                self._require_task_claim(
                    task,
                    context,
                    token_digest=claim_digest,
                    claim_fence=safe_fence,
                )
                correction = self._current_correction(connection, context, task)
                prior_version, prior_value, prior_digest = self._effective_source(
                    connection, context, task
                )
                corrected_value = self._decode_content(
                    correction["corrected_value_json"],
                    correction["corrected_value_digest"],
                    "HUMAN_REVIEW_CORRECTION_VERSION_CORRUPT",
                )
                decision_id = self._decision_id(
                    context,
                    task_id=task["task_id"],
                    action=safe_action,
                    decision_version=next_task_version,
                    request_digest=safe_request_digest,
                )
                reservation = self._reserve_target_head(
                    connection,
                    context,
                    task=task,
                    correction=correction,
                    action=safe_action,
                    decision_id=decision_id,
                )
                decision = self._insert_decision(
                    connection,
                    context,
                    task=task,
                    action=safe_action,
                    next_state=ReviewTaskState.APPROVED,
                    correction=correction,
                    reason=safe_reason,
                    request_digest=safe_request_digest,
                    decision_version=next_task_version,
                )
                if decision["decision_id"] != decision_id:
                    raise IntegrityError("HUMAN_REVIEW_DECISION_DRIFT")
                changed = connection.execute(
                    """UPDATE human_review_tasks
                          SET state='APPROVED',claim_actor_id=NULL,claim_token_digest=NULL,
                              claim_expires_at=NULL,version=?,updated_at=?,closed_at=?
                        WHERE tenant_id=? AND project_id=? AND task_id=?
                          AND version=? AND claim_fence=? AND claim_token_digest=?""",
                    (
                        next_task_version,
                        now,
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_task_id,
                        safe_version,
                        safe_fence,
                        claim_digest,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
                propagations = self._create_propagations(
                    connection,
                    context,
                    task=task,
                    decision=decision,
                    correction=correction,
                    reservation=reservation,
                    direction=ReviewPropagationDirection.APPLY,
                    effective_value=corrected_value,
                    effective_digest=correction["corrected_value_digest"],
                    prior_effective_version=prior_version,
                    prior_effective_value=prior_value,
                    prior_effective_digest=prior_digest,
                )
                event_type = "correction.approved"
                next_state = ReviewTaskState.APPROVED
            elif safe_action is ReviewDecisionAction.REJECT:
                if state not in {ReviewTaskState.CLAIMED, ReviewTaskState.EDITED}:
                    raise ConflictError("HUMAN_REVIEW_REJECT_STATE_INVALID")
                assert claim_digest is not None and safe_fence is not None
                self._require_task_claim(
                    task,
                    context,
                    token_digest=claim_digest,
                    claim_fence=safe_fence,
                )
                correction = (
                    self._current_correction(connection, context, task)
                    if int(task["current_correction_version"]) > 0
                    else None
                )
                decision = self._insert_decision(
                    connection,
                    context,
                    task=task,
                    action=safe_action,
                    next_state=ReviewTaskState.REJECTED,
                    correction=correction,
                    reason=safe_reason,
                    request_digest=safe_request_digest,
                    decision_version=next_task_version,
                )
                changed = connection.execute(
                    """UPDATE human_review_tasks
                          SET state='REJECTED',claim_actor_id=NULL,claim_token_digest=NULL,
                              claim_expires_at=NULL,version=?,updated_at=?,closed_at=?
                        WHERE tenant_id=? AND project_id=? AND task_id=?
                          AND version=? AND claim_fence=? AND claim_token_digest=?""",
                    (
                        next_task_version,
                        now,
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_task_id,
                        safe_version,
                        safe_fence,
                        claim_digest,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
                event_type = "correction.rejected"
                next_state = ReviewTaskState.REJECTED
            elif safe_action is ReviewDecisionAction.REOPEN:
                if state not in {ReviewTaskState.REJECTED, ReviewTaskState.REVERTED}:
                    raise ConflictError("HUMAN_REVIEW_REOPEN_STATE_INVALID")
                correction = (
                    self._current_correction(connection, context, task)
                    if int(task["current_correction_version"]) > 0
                    else None
                )
                decision = self._insert_decision(
                    connection,
                    context,
                    task=task,
                    action=safe_action,
                    next_state=ReviewTaskState.REOPENED,
                    correction=correction,
                    reason=safe_reason,
                    request_digest=safe_request_digest,
                    decision_version=next_task_version,
                )
                changed = connection.execute(
                    """UPDATE human_review_tasks
                          SET state='REOPENED',claim_actor_id=NULL,claim_token_digest=NULL,
                              claim_expires_at=NULL,version=?,updated_at=?,closed_at=NULL
                        WHERE tenant_id=? AND project_id=? AND task_id=? AND version=?""",
                    (
                        next_task_version,
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_task_id,
                        safe_version,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
                event_type = "review.reopened"
                next_state = ReviewTaskState.REOPENED
            else:
                if state is not ReviewTaskState.APPROVED:
                    raise ConflictError("HUMAN_REVIEW_REVERT_STATE_INVALID")
                correction = self._current_correction(connection, context, task)
                if int(task["effective_version"]) != int(correction["correction_version"]):
                    raise ConflictError("HUMAN_REVIEW_REVERT_PROPAGATION_INCOMPLETE")
                approval = connection.execute(
                    """SELECT * FROM human_review_decisions
                        WHERE tenant_id=? AND project_id=? AND task_id=?
                          AND decision='APPROVE' AND correction_version=?
                        ORDER BY decision_version DESC LIMIT 1""",
                    (
                        context.tenant_id,
                        context.project_id,
                        safe_task_id,
                        correction["correction_version"],
                    ),
                ).fetchone()
                if approval is None:
                    raise IntegrityError("HUMAN_REVIEW_APPROVAL_MISSING")
                parent_reservation = self._decision_reservation(
                    connection,
                    context,
                    decision_id=approval["decision_id"],
                )
                if (
                    self._reservation_payload(parent_reservation)["state"]
                    != ReviewHeadReservationState.APPLIED.value
                ):
                    raise ConflictError("HUMAN_REVIEW_REVERT_RESERVATION_INVALID")
                applied = connection.execute(
                    """SELECT * FROM human_review_propagation_tasks
                        WHERE tenant_id=? AND project_id=? AND decision_id=?
                        ORDER BY channel""",
                    (context.tenant_id, context.project_id, approval["decision_id"]),
                ).fetchall()
                if len(applied) != len(_PROPAGATION_CHANNELS) or any(
                    row["state"] != ReviewPropagationState.SUCCEEDED.value for row in applied
                ):
                    raise ConflictError("HUMAN_REVIEW_REVERT_PROPAGATION_INCOMPLETE")
                applied_payload = self._decode_content(
                    applied[0]["payload_json"],
                    applied[0]["payload_digest"],
                    "HUMAN_REVIEW_PROPAGATION_CORRUPT",
                )
                if not isinstance(applied_payload, dict):
                    raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
                prior_version = _safe_version(
                    applied_payload.get("prior_effective_version"),
                    "HUMAN_REVIEW_PROPAGATION_CORRUPT",
                    allow_zero=True,
                )
                prior_value = bounded_review_json(applied_payload.get("prior_effective_value"))
                prior_digest_value = applied_payload.get("prior_effective_digest")
                if not isinstance(prior_digest_value, str):
                    raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
                prior_digest = normalize_sha256(prior_digest_value)
                if normalize_sha256(content_contract_digest(prior_value)) != prior_digest:
                    raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
                decision_id = self._decision_id(
                    context,
                    task_id=task["task_id"],
                    action=safe_action,
                    decision_version=next_task_version,
                    request_digest=safe_request_digest,
                )
                reservation = self._reserve_target_head(
                    connection,
                    context,
                    task=task,
                    correction=correction,
                    action=safe_action,
                    decision_id=decision_id,
                    parent_reservation=parent_reservation,
                )
                decision = self._insert_decision(
                    connection,
                    context,
                    task=task,
                    action=safe_action,
                    next_state=ReviewTaskState.REVERTING,
                    correction=correction,
                    reason=safe_reason,
                    request_digest=safe_request_digest,
                    decision_version=next_task_version,
                )
                if decision["decision_id"] != decision_id:
                    raise IntegrityError("HUMAN_REVIEW_DECISION_DRIFT")
                changed = connection.execute(
                    """UPDATE human_review_tasks
                          SET state='REVERTING',version=?,updated_at=?,closed_at=NULL
                        WHERE tenant_id=? AND project_id=? AND task_id=? AND version=?""",
                    (
                        next_task_version,
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_task_id,
                        safe_version,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
                propagations = self._create_propagations(
                    connection,
                    context,
                    task=task,
                    decision=decision,
                    correction=correction,
                    reservation=reservation,
                    direction=ReviewPropagationDirection.REVERT,
                    effective_value=prior_value,
                    effective_digest=prior_digest,
                    prior_effective_version=prior_version,
                    prior_effective_value=prior_value,
                    prior_effective_digest=prior_digest,
                )
                event_type = "correction.revert_requested"
                next_state = ReviewTaskState.REVERTING
            self._audit(
                connection,
                context,
                task_id=safe_task_id,
                event_type=event_type,
                prior_state=state.value,
                next_state=next_state.value,
                task_version=next_task_version,
                details={
                    "decision_id": decision["decision_id"],
                    "decision": safe_action.value,
                    "correction_version": (
                        int(correction["correction_version"]) if correction is not None else None
                    ),
                    "propagation_count": len(propagations),
                    "reservation_id": (
                        self._reservation_payload(reservation)["reservation_id"]
                        if reservation is not None
                        else None
                    ),
                    "reservation_fence": (
                        self._reservation_payload(reservation)["reservation_fence"]
                        if reservation is not None
                        else None
                    ),
                },
            )
            self._store._event(
                connection,
                context,
                "human_review_task",
                safe_task_id,
                event_type,
                f"{event_type}:{decision['decision_id']}",
                {
                    "task_id": safe_task_id,
                    "decision_id": decision["decision_id"],
                    "decision": safe_action.value,
                    "propagation_count": len(propagations),
                },
            )
            updated = self._scoped_task(connection, context, safe_task_id)
            response = {
                "decision": self._decision_payload(decision),
                "task": self._task_payload(updated),
                "propagations": [self._propagation_summary(row) for row in propagations],
            }
            return self._record_receipt(
                connection,
                context,
                operation=operation,
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @staticmethod
    def _parse_future_expiry(
        value: Any,
        code: str = "HUMAN_REVIEW_WORKER_EXPIRY_INVALID",
    ) -> str:
        if not isinstance(value, str):
            raise ValidationError(code)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValidationError(code) from error
        now = datetime.now(UTC).replace(microsecond=0)
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() is None
            or parsed <= now
            or parsed > now + timedelta(days=30)
        ):
            raise ValidationError(code)
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat()

    def register_worker_capability(
        self,
        context: TenantContext,
        *,
        worker_id: str,
        capability_token: str,
        actions: Sequence[str],
        expires_at: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_worker = require_actor_id(worker_id)
        _token, token_digest = _token_digest(
            capability_token, "HUMAN_REVIEW_WORKER_TOKEN_INVALID"
        )
        if (
            isinstance(actions, (str, bytes))
            or not isinstance(actions, Sequence)
            or not actions
            or any(not isinstance(action, str) for action in actions)
        ):
            raise ValidationError("HUMAN_REVIEW_WORKER_ACTIONS_INVALID")
        safe_actions = tuple(sorted(set(actions)))
        if len(safe_actions) != len(actions) or not set(safe_actions) <= _WORKER_ACTIONS:
            raise ValidationError("HUMAN_REVIEW_WORKER_ACTIONS_INVALID")
        safe_expiry = self._parse_future_expiry(expires_at)
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        actions_value = list(safe_actions)
        _actions_copy, actions_json, actions_digest = self._content_json(
            actions_value, "HUMAN_REVIEW_WORKER_ACTIONS_INVALID"
        )
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.ADMIN)
            replay = self._receipt(
                connection,
                context,
                operation="register_worker",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            existing = connection.execute(
                """SELECT * FROM human_review_worker_capabilities
                    WHERE tenant_id=? AND project_id=? AND worker_id=? AND token_digest=?""",
                (context.tenant_id, context.project_id, safe_worker, token_digest),
            ).fetchone()
            if existing is not None:
                if (
                    existing["actions_json"] != actions_json
                    or existing["actions_digest"] != actions_digest
                    or existing["expires_at"] != safe_expiry
                    or existing["revoked_at"] is not None
                ):
                    raise ConflictError("HUMAN_REVIEW_WORKER_CAPABILITY_CONFLICT")
                capability_id = existing["capability_id"]
            else:
                capability_id = "review-worker-" + canonical_digest(
                    {
                        "tenant_id": context.tenant_id,
                        "project_id": context.project_id,
                        "worker_id": safe_worker,
                        "token_digest": f"sha256:{token_digest}",
                    }
                )[:32]
                connection.execute(
                    """INSERT INTO human_review_worker_capabilities (
                        capability_id,tenant_id,project_id,worker_id,token_digest,
                        actions_json,actions_digest,expires_at,revoked_at,version,
                        created_by,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,NULL,1,?,?)""",
                    (
                        capability_id,
                        context.tenant_id,
                        context.project_id,
                        safe_worker,
                        token_digest,
                        actions_json,
                        actions_digest,
                        safe_expiry,
                        context.actor_id,
                        utc_now(),
                    ),
                )
            response = {
                "capability": {
                    "capability_id": capability_id,
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "worker_id": safe_worker,
                    "actions": actions_value,
                    "expires_at": safe_expiry,
                    "revoked": False,
                }
            }
            return self._record_receipt(
                connection,
                context,
                operation="register_worker",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def revoke_worker_capability(
        self,
        context: TenantContext,
        *,
        capability_id: str,
        expected_version: int,
        reason: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_id = require_resource_id(capability_id, "capability_id")
        safe_version = _safe_version(expected_version, "HUMAN_REVIEW_EXPECTED_VERSION_INVALID")
        safe_reason = _required_text(reason, "HUMAN_REVIEW_REASON_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        with self._store.transaction() as connection:
            self._store._require(connection, context, self._store.ADMIN)
            replay = self._receipt(
                connection,
                context,
                operation="revoke_worker",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            row = connection.execute(
                """SELECT * FROM human_review_worker_capabilities
                    WHERE tenant_id=? AND project_id=? AND capability_id=?""",
                (context.tenant_id, context.project_id, safe_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("HUMAN_REVIEW_WORKER_CAPABILITY_NOT_FOUND")
            if int(row["version"]) != safe_version:
                raise ConflictError("HUMAN_REVIEW_WORKER_CAPABILITY_VERSION_CONFLICT")
            now = utc_now()
            if row["revoked_at"] is None:
                changed = connection.execute(
                    """UPDATE human_review_worker_capabilities
                          SET revoked_at=?,version=version+1
                        WHERE tenant_id=? AND project_id=? AND capability_id=?
                          AND version=? AND revoked_at IS NULL""",
                    (
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_id,
                        safe_version,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("HUMAN_REVIEW_WORKER_CAPABILITY_VERSION_CONFLICT")
            response = {
                "capability_id": safe_id,
                "revoked": True,
                "revoked_at": row["revoked_at"] or now,
                "reason": safe_reason,
            }
            return self._record_receipt(
                connection,
                context,
                operation="revoke_worker",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @classmethod
    def _source_producer_identity(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        capability_id: str,
        capability_token: str,
        source_kind: str,
    ) -> sqlite3.Row:
        safe_id = require_resource_id(capability_id, "capability_id")
        _token, token_digest = _token_digest(
            capability_token, "HUMAN_REVIEW_SOURCE_PRODUCER_TOKEN_INVALID"
        )
        row = connection.execute(
            """SELECT * FROM human_review_source_producer_capabilities
                WHERE tenant_id=? AND project_id=? AND capability_id=?""",
            (context.tenant_id, context.project_id, safe_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise AuthorizationError(
                "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
            )
        source_kinds = cls._decode_content(
            row["source_kinds_json"],
            row["source_kinds_digest"],
            "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_CORRUPT",
        )
        if (
            row["producer_id"] != context.actor_id
            or not hmac.compare_digest(row["token_digest"], token_digest)
            or not isinstance(source_kinds, list)
            or source_kinds != sorted(set(source_kinds))
            or not source_kinds
            or not set(source_kinds) <= _SOURCE_KINDS
            or source_kind not in source_kinds
        ):
            raise AuthorizationError(
                "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
            )
        return row

    @staticmethod
    def _require_source_producer_active(row: sqlite3.Row) -> None:
        if row["revoked_at"] is not None or str(row["expires_at"]) <= utc_now():
            raise AuthorizationError(
                "HUMAN_REVIEW_SOURCE_PRODUCER_CAPABILITY_DENIED"
            )

    @classmethod
    def _worker_identity(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        capability_id: str,
        capability_token: str,
        action: str,
    ) -> sqlite3.Row:
        safe_id = require_resource_id(capability_id, "capability_id")
        _token, token_digest = _token_digest(
            capability_token, "HUMAN_REVIEW_WORKER_TOKEN_INVALID"
        )
        row = connection.execute(
            """SELECT * FROM human_review_worker_capabilities
                WHERE tenant_id=? AND project_id=? AND capability_id=?""",
            (context.tenant_id, context.project_id, safe_id),
        ).fetchone()
        if not isinstance(row, sqlite3.Row):
            raise AuthorizationError("HUMAN_REVIEW_WORKER_CAPABILITY_DENIED")
        try:
            actions = cls._decode_content(
                row["actions_json"],
                row["actions_digest"],
                "HUMAN_REVIEW_WORKER_CAPABILITY_CORRUPT",
            )
        except IntegrityError:
            raise
        if (
            row["worker_id"] != context.actor_id
            or not hmac.compare_digest(row["token_digest"], token_digest)
            or not isinstance(actions, list)
            or actions != sorted(set(actions))
            or action not in actions
            or not set(actions) <= _WORKER_ACTIONS
        ):
            raise AuthorizationError("HUMAN_REVIEW_WORKER_CAPABILITY_DENIED")
        return row

    @staticmethod
    def _require_worker_active(row: sqlite3.Row) -> None:
        if row["revoked_at"] is not None or str(row["expires_at"]) <= utc_now():
            raise AuthorizationError("HUMAN_REVIEW_WORKER_CAPABILITY_DENIED")

    @staticmethod
    def _require_propagation_claim(
        row: sqlite3.Row,
        *,
        capability_id: str,
        owner_digest: str,
        claim_fence: int,
        require_dispatched: bool,
    ) -> None:
        if (
            row["state"] != ReviewPropagationState.CLAIMED.value
            or row["claim_capability_id"] != capability_id
            or not isinstance(row["claim_owner_digest"], str)
            or not hmac.compare_digest(row["claim_owner_digest"], owner_digest)
            or int(row["claim_fence"]) != claim_fence
            or str(row["claim_expires_at"] or "") <= utc_now()
            or require_dispatched and row["dispatch_started_at"] is None
        ):
            raise ConflictError("HUMAN_REVIEW_PROPAGATION_CLAIM_NOT_OWNED")

    def claim_propagation(
        self,
        context: TenantContext,
        *,
        propagation_id: str,
        capability_id: str,
        capability_token: str,
        owner_token: str,
        lease_seconds: int,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_propagation_id = require_resource_id(propagation_id, "propagation_id")
        safe_capability_id = require_resource_id(capability_id, "capability_id")
        _owner, owner_digest = _token_digest(owner_token, "HUMAN_REVIEW_OWNER_TOKEN_INVALID")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 3_600:
            raise ValidationError("HUMAN_REVIEW_PROPAGATION_LEASE_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        now_dt = datetime.now(UTC).replace(microsecond=0)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self._store.transaction() as connection:
            worker_capability = self._worker_identity(
                connection,
                context,
                capability_id=safe_capability_id,
                capability_token=capability_token,
                action="claim",
            )
            replay = self._receipt(
                connection,
                context,
                operation="propagation_claim",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                current = self._scoped_propagation(connection, context, safe_propagation_id)
                self._propagation_reservation(connection, context, current)
                replayed = replay.get("propagation")
                if (
                    not isinstance(replayed, dict)
                    or replayed.get("propagation_id") != safe_propagation_id
                    or current["state"] != ReviewPropagationState.CLAIMED.value
                    or current["claim_capability_id"] != safe_capability_id
                    or not isinstance(current["claim_owner_digest"], str)
                    or not hmac.compare_digest(current["claim_owner_digest"], owner_digest)
                    or int(current["claim_fence"]) != replayed.get("claim_fence")
                    or str(current["claim_expires_at"] or "") <= now
                ):
                    raise ConflictError("HUMAN_REVIEW_PROPAGATION_CLAIM_REPLAY_STALE")
                return replay
            self._require_worker_active(worker_capability)
            row = self._scoped_propagation(connection, context, safe_propagation_id)
            reservation = self._propagation_reservation(connection, context, row)
            reservation_state = ReviewHeadReservationState(
                self._reservation_payload(reservation)["state"]
            )
            state = ReviewPropagationState(row["state"])
            if state is ReviewPropagationState.UNKNOWN:
                raise ConflictError(
                    "HUMAN_REVIEW_PROPAGATION_RECONCILIATION_REQUIRED",
                    details={"automatic_retry_allowed": False},
                )
            if state in {ReviewPropagationState.SUCCEEDED, ReviewPropagationState.FAILED}:
                response = {"propagation": self._propagation_payload(row)}
                return self._record_receipt(
                    connection,
                    context,
                    operation="propagation_claim",
                    idempotency_key=safe_key,
                    request_digest=safe_request_digest,
                    response=response,
                )
            if reservation_state is not ReviewHeadReservationState.PROPAGATING:
                raise ConflictError(
                    "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_NOT_OPERATIONAL",
                    details={"reservation_state": reservation_state.value},
                )
            if state is ReviewPropagationState.CLAIMED:
                live = str(row["claim_expires_at"] or "") > now
                same_owner = (
                    live
                    and row["claim_capability_id"] == safe_capability_id
                    and isinstance(row["claim_owner_digest"], str)
                    and hmac.compare_digest(row["claim_owner_digest"], owner_digest)
                )
                if live and not same_owner:
                    raise ConflictError(
                        "HUMAN_REVIEW_PROPAGATION_ALREADY_CLAIMED",
                        retryable=True,
                        details={"claim_expires_at": row["claim_expires_at"]},
                    )
                if not live and row["dispatch_started_at"] is not None:
                    next_version = int(row["version"]) + 1
                    connection.execute(
                        """UPDATE human_review_propagation_tasks
                              SET state='UNKNOWN',claim_capability_id=NULL,
                                  claim_owner_digest=NULL,claim_expires_at=NULL,
                                  failure_code='LEASE_EXPIRED_AFTER_DISPATCH',
                                  reconciliation_required=1,version=?,updated_at=?
                            WHERE tenant_id=? AND project_id=? AND propagation_id=?
                              AND version=? AND state='CLAIMED'""",
                        (
                            next_version,
                            now,
                            context.tenant_id,
                            context.project_id,
                            safe_propagation_id,
                            row["version"],
                        ),
                    )
                    unknown = self._scoped_propagation(
                        connection, context, safe_propagation_id
                    )
                    self._sync_reservation_state(
                        connection,
                        context,
                        decision_id=unknown["decision_id"],
                    )
                    self._audit(
                        connection,
                        context,
                        task_id=unknown["task_id"],
                        event_type="propagation.unknown",
                        prior_state=ReviewPropagationState.CLAIMED.value,
                        next_state=ReviewPropagationState.UNKNOWN.value,
                        task_version=self._task_version(
                            connection, context, unknown["task_id"]
                        ),
                        details={
                            "propagation_id": safe_propagation_id,
                            "automatic_retry_allowed": False,
                            "failure_code": "LEASE_EXPIRED_AFTER_DISPATCH",
                        },
                    )
                    response = {"propagation": self._propagation_payload(unknown)}
                    return self._record_receipt(
                        connection,
                        context,
                        operation="propagation_claim",
                        idempotency_key=safe_key,
                        request_digest=safe_request_digest,
                        response=response,
                    )
            next_fence = int(row["claim_fence"]) + 1
            next_version = int(row["version"]) + 1
            changed = connection.execute(
                """UPDATE human_review_propagation_tasks
                      SET state='CLAIMED',claim_capability_id=?,claim_owner_digest=?,
                          claim_fence=?,claim_expires_at=?,dispatch_started_at=NULL,
                          failure_code=NULL,reconciliation_required=0,version=?,updated_at=?
                    WHERE tenant_id=? AND project_id=? AND propagation_id=? AND version=?
                      AND state IN ('PENDING','CLAIMED')""",
                (
                    safe_capability_id,
                    owner_digest,
                    next_fence,
                    expires_at,
                    next_version,
                    now,
                    context.tenant_id,
                    context.project_id,
                    safe_propagation_id,
                    row["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("HUMAN_REVIEW_PROPAGATION_VERSION_CONFLICT")
            claimed = self._scoped_propagation(connection, context, safe_propagation_id)
            self._audit(
                connection,
                context,
                task_id=claimed["task_id"],
                event_type="propagation.claimed",
                prior_state=state.value,
                next_state=ReviewPropagationState.CLAIMED.value,
                task_version=self._task_version(connection, context, claimed["task_id"]),
                details={
                    "propagation_id": safe_propagation_id,
                    "claim_fence": next_fence,
                    "claim_expires_at": expires_at,
                    "capability_id": safe_capability_id,
                },
            )
            response = {"propagation": self._propagation_payload(claimed)}
            return self._record_receipt(
                connection,
                context,
                operation="propagation_claim",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def mark_propagation_dispatched(
        self,
        context: TenantContext,
        *,
        propagation_id: str,
        capability_id: str,
        capability_token: str,
        owner_token: str,
        claim_fence: int,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_propagation_id = require_resource_id(propagation_id, "propagation_id")
        safe_capability_id = require_resource_id(capability_id, "capability_id")
        _owner, owner_digest = _token_digest(owner_token, "HUMAN_REVIEW_OWNER_TOKEN_INVALID")
        safe_fence = _safe_version(claim_fence, "HUMAN_REVIEW_CLAIM_FENCE_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        with self._store.transaction() as connection:
            worker_capability = self._worker_identity(
                connection,
                context,
                capability_id=safe_capability_id,
                capability_token=capability_token,
                action="dispatch",
            )
            replay = self._receipt(
                connection,
                context,
                operation="propagation_dispatch",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            self._require_worker_active(worker_capability)
            row = self._scoped_propagation(connection, context, safe_propagation_id)
            reservation = self._propagation_reservation(connection, context, row)
            if (
                self._reservation_payload(reservation)["state"]
                != ReviewHeadReservationState.PROPAGATING.value
            ):
                raise ConflictError(
                    "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_NOT_OPERATIONAL"
                )
            self._require_propagation_claim(
                row,
                capability_id=safe_capability_id,
                owner_digest=owner_digest,
                claim_fence=safe_fence,
                require_dispatched=False,
            )
            now = utc_now()
            if row["dispatch_started_at"] is None:
                changed = connection.execute(
                    """UPDATE human_review_propagation_tasks
                          SET dispatch_started_at=?,version=version+1,updated_at=?
                        WHERE tenant_id=? AND project_id=? AND propagation_id=?
                          AND version=? AND state='CLAIMED' AND claim_fence=?""",
                    (
                        now,
                        now,
                        context.tenant_id,
                        context.project_id,
                        safe_propagation_id,
                        row["version"],
                        safe_fence,
                    ),
                ).rowcount
                if changed != 1:
                    raise ConflictError("HUMAN_REVIEW_PROPAGATION_VERSION_CONFLICT")
            dispatched = self._scoped_propagation(connection, context, safe_propagation_id)
            self._audit(
                connection,
                context,
                task_id=dispatched["task_id"],
                event_type="propagation.dispatched",
                prior_state=ReviewPropagationState.CLAIMED.value,
                next_state=ReviewPropagationState.CLAIMED.value,
                task_version=self._task_version(
                    connection, context, dispatched["task_id"]
                ),
                details={
                    "propagation_id": safe_propagation_id,
                    "claim_fence": safe_fence,
                    "dispatch_started_at": dispatched["dispatch_started_at"],
                },
            )
            response = {"propagation": self._propagation_payload(dispatched)}
            return self._record_receipt(
                connection,
                context,
                operation="propagation_dispatch",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    @classmethod
    def _projection_payload(cls, row: sqlite3.Row) -> dict[str, Any]:
        try:
            target = bounded_review_json(json.loads(row["target_json"]))
            effective_value = cls._decode_content(
                row["effective_value_json"],
                row["effective_value_digest"],
                "HUMAN_REVIEW_EFFECTIVE_PROJECTION_CORRUPT",
            )
            return {
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "task_id": row["task_id"],
                "channel": row["channel"],
                "source_decision_id": row["source_decision_id"],
                "correction_version": int(row["correction_version"]),
                "direction": ReviewPropagationDirection(row["direction"]).value,
                "target_kind": ReviewTargetKind(row["target_kind"]).value,
                "target": target,
                "effective_value": effective_value,
                "effective_value_digest": (
                    f"sha256:{normalize_sha256(row['effective_value_digest'])}"
                ),
                "source_digest": f"sha256:{normalize_sha256(row['source_digest'])}",
                "version": int(row["version"]),
                "updated_at": row["updated_at"],
            }
        except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_CORRUPT") from error

    @classmethod
    def _status_payload(
        cls,
        connection: sqlite3.Connection,
        context: TenantContext,
        task: sqlite3.Row,
    ) -> dict[str, Any]:
        propagation_rows = connection.execute(
            """SELECT * FROM human_review_propagation_tasks
                WHERE tenant_id=? AND project_id=? AND task_id=?
                ORDER BY created_at,decision_id,channel""",
            (context.tenant_id, context.project_id, task["task_id"]),
        ).fetchall()
        for decision_id in sorted({row["decision_id"] for row in propagation_rows}):
            cls._decision_reservation(
                connection,
                context,
                decision_id=decision_id,
            )
        projection_rows = connection.execute(
            """SELECT * FROM human_review_effective_projections
                WHERE tenant_id=? AND project_id=? AND task_id=? ORDER BY channel""",
            (context.tenant_id, context.project_id, task["task_id"]),
        ).fetchall()
        projections = [cls._projection_payload(row) for row in projection_rows]
        materialized = len(projections) == len(_PROPAGATION_CHANNELS)
        effective_value: Any = None
        effective_digest: str | None = None
        if materialized:
            first = projections[0]
            if (
                {projection["channel"] for projection in projections}
                != set(_PROPAGATION_CHANNELS)
                or any(
                    projection["effective_value"] != first["effective_value"]
                    or projection["effective_value_digest"]
                    != first["effective_value_digest"]
                    or projection["correction_version"]
                    != first["correction_version"]
                    or projection["direction"] != first["direction"]
                    for projection in projections
                )
            ):
                raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_DRIFT")
            effective_value = first["effective_value"]
            effective_digest = first["effective_value_digest"]
            if (
                task["effective_digest"] is None
                or not hmac.compare_digest(
                    normalize_sha256(task["effective_digest"]),
                    normalize_sha256(effective_digest),
                )
            ):
                raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_DRIFT")
        elif projection_rows:
            raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_PROJECTION_INCOMPLETE")
        return {
            "task": cls._task_payload(task),
            "propagations": [cls._propagation_summary(row) for row in propagation_rows],
            "effective": {
                "materialized": materialized,
                "state": "CURRENT" if materialized else "NOT_RUN",
                "effective_version": int(task["effective_version"]),
                "effective_value": effective_value,
                "effective_value_digest": effective_digest,
                "channels": [
                    {
                        "channel": projection["channel"],
                        "source_decision_id": projection["source_decision_id"],
                        "correction_version": projection["correction_version"],
                        "direction": projection["direction"],
                        "effective_value_digest": projection["effective_value_digest"],
                        "version": projection["version"],
                        "updated_at": projection["updated_at"],
                    }
                    for projection in projections
                ],
            },
        }

    def _materialize_target_head(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        task: sqlite3.Row,
        reservation: sqlite3.Row,
        decision_id: str,
        direction: ReviewPropagationDirection,
        correction_version: int,
        materialized_version: int,
        effective_json: str,
        effective_digest: str,
        prior_effective_version: int,
        prior_effective_digest: str,
        now: str,
    ) -> int:
        reservation_payload = self._reservation_payload(reservation)
        expected_action = (
            ReviewDecisionAction.APPROVE.value
            if direction is ReviewPropagationDirection.APPLY
            else ReviewDecisionAction.REVERT.value
        )
        if (
            reservation_payload["decision_id"] != decision_id
            or reservation_payload["task_id"] != task["task_id"]
            or reservation_payload["decision_action"] != expected_action
            or reservation_payload["correction_version"] != correction_version
            or reservation_payload["state"]
            != ReviewHeadReservationState.PROPAGATING.value
        ):
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CORRUPT")
        source_ref = self._decode_content(
            task["source_ref_json"],
            task["source_ref_digest"],
            "HUMAN_REVIEW_SOURCE_REF_CORRUPT",
        )
        try:
            if (
                not isinstance(source_ref, dict)
                or set(source_ref) != _SOURCE_REF_V2_FIELDS
                or source_ref.get("schema_version") != "human-review-source-ref-v2"
                or source_ref.get("content_id") != task["asset_id"]
                or source_ref.get("target_kind") != task["target_kind"]
                or source_ref.get("original_value_digest_contract")
                != CANONICAL_JSON_SHA256_CONTRACT
            ):
                raise IntegrityError("HUMAN_REVIEW_SOURCE_REF_CORRUPT")
            asset_version = _safe_version(
                source_ref["content_version"], "HUMAN_REVIEW_SOURCE_REF_CORRUPT"
            )
            source_head_version = _safe_version(
                source_ref["head_version"], "HUMAN_REVIEW_SOURCE_REF_CORRUPT"
            )
            snapshot_id = require_resource_id(source_ref["snapshot_id"], "snapshot_id")
            task_target_digest = normalize_sha256(task["target_digest"])
            source_target_digest = normalize_sha256(source_ref["target_digest"])
            source_snapshot_digest = normalize_sha256(source_ref["snapshot_digest"])
            source_head_digest = normalize_sha256(source_ref["head_value_digest"])
            source_asset_sha256 = normalize_sha256(source_ref["asset_sha256"])
            source_fact_digest = normalize_sha256(source_ref["source_digest"])
            source_provenance_digest = normalize_sha256(
                source_ref["provenance_digest"]
            )
            source_client_digest = normalize_sha256(
                source_ref["original_value_client_digest"]
            )
            normalize_sha256(source_ref["content_digest"])
            task_target_kind = ReviewTargetKind(task["target_kind"])
            task_original = self._decode_content(
                task["original_value_json"],
                task["original_value_digest"],
                "HUMAN_REVIEW_SOURCE_REF_CORRUPT",
            )
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_SOURCE_REF_CORRUPT") from error
        if (
            not hmac.compare_digest(task_target_digest, source_target_digest)
            or not hmac.compare_digest(
                source_client_digest,
                human_review_client_value_digest(task_original),
            )
        ):
            raise IntegrityError("HUMAN_REVIEW_SOURCE_REF_CORRUPT")

        head, snapshot, _current_value = self._authoritative_head(
            connection,
            context,
            asset_id=task["asset_id"],
            asset_version=asset_version,
            target_kind=task_target_kind,
            target_json=task["target_json"],
            target_digest=task_target_digest,
        )
        snapshot_payload = self._source_snapshot_payload(snapshot)
        try:
            bindings_valid = (
                head["base_snapshot_id"] == snapshot_id
                and snapshot["snapshot_id"] == snapshot_id
                and snapshot["asset_id"] == task["asset_id"]
                and int(snapshot["asset_version"]) == asset_version
                and snapshot["target_kind"] == task["target_kind"]
                and snapshot["target_json"] == task["target_json"]
                and hmac.compare_digest(
                    normalize_sha256(snapshot["target_digest"]), task_target_digest
                )
                and hmac.compare_digest(
                    normalize_sha256(snapshot["snapshot_digest"]),
                    source_snapshot_digest,
                )
                and hmac.compare_digest(
                    normalize_sha256(snapshot["asset_sha256"]), source_asset_sha256
                )
                and hmac.compare_digest(
                    normalize_sha256(snapshot["source_digest"]), source_fact_digest
                )
                and hmac.compare_digest(
                    normalize_sha256(snapshot["provenance_digest"]),
                    source_provenance_digest,
                )
                and hmac.compare_digest(
                    normalize_sha256(head["source_digest"]), source_fact_digest
                )
                and hmac.compare_digest(
                    normalize_sha256(head["provenance_digest"]),
                    source_provenance_digest,
                )
                and snapshot_payload["snapshot_digest"]
                == f"sha256:{source_snapshot_digest}"
                and int(head["version"]) >= source_head_version
                and (
                    int(head["version"]) != source_head_version
                    or hmac.compare_digest(
                        normalize_sha256(head["current_value_digest"]),
                        source_head_digest,
                    )
                )
            )
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_CORRUPT") from error
        if not bindings_valid:
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_CORRUPT")
        if (
            reservation_payload["asset_id"] != task["asset_id"]
            or reservation_payload["asset_version"] != asset_version
            or reservation_payload["target_kind"] != task["target_kind"]
            or reservation_payload["target_digest"]
            != f"sha256:{task_target_digest}"
            or reservation_payload["snapshot_id"] != snapshot_id
            or reservation_payload["snapshot_digest"]
            != f"sha256:{source_snapshot_digest}"
            or reservation_payload["reserved_head_version"] != int(head["version"])
            or reservation_payload["reserved_head_value_digest"]
            != f"sha256:{normalize_sha256(head['current_value_digest'])}"
            or reservation_payload["reservation_fence"] != int(head["version"])
        ):
            raise ConflictError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_DRIFT")

        decision = connection.execute(
            """SELECT * FROM human_review_decisions
                WHERE tenant_id=? AND project_id=? AND decision_id=?""",
            (context.tenant_id, context.project_id, decision_id),
        ).fetchone()
        expected_decision = (
            ReviewDecisionAction.APPROVE
            if direction is ReviewPropagationDirection.APPLY
            else ReviewDecisionAction.REVERT
        )
        if (
            decision is None
            or decision["task_id"] != task["task_id"]
            or decision["decision"] != expected_decision.value
            or int(decision["correction_version"]) != correction_version
        ):
            raise IntegrityError("HUMAN_REVIEW_DECISION_DRIFT")

        if direction is ReviewPropagationDirection.APPLY:
            expected_current_digest = prior_effective_digest
            expected_current_version = prior_effective_version
            task_current_digest = (
                normalize_sha256(task["effective_digest"])
                if int(task["effective_version"]) > 0
                else normalize_sha256(task["original_value_digest"])
            )
            if (
                int(task["effective_version"]) != prior_effective_version
                or not hmac.compare_digest(task_current_digest, prior_effective_digest)
            ):
                raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_SOURCE_DRIFT")
        else:
            if task["effective_digest"] is None:
                raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_SOURCE_DRIFT")
            expected_current_digest = normalize_sha256(task["effective_digest"])
            expected_current_version = int(task["effective_version"])
            if expected_current_version != correction_version:
                raise IntegrityError("HUMAN_REVIEW_EFFECTIVE_SOURCE_DRIFT")
        if (
            int(head["correction_version"]) != expected_current_version
            or not hmac.compare_digest(
                normalize_sha256(head["current_value_digest"]),
                expected_current_digest,
            )
        ):
            raise ConflictError(
                "HUMAN_REVIEW_SOURCE_DRIFT",
                details={
                    "expected_original_digest": f"sha256:{expected_current_digest}",
                    "actual_original_digest": (
                        f"sha256:{normalize_sha256(head['current_value_digest'])}"
                    ),
                    "head_version": int(head["version"]),
                },
            )
        reserved_head_version = reservation_payload["reserved_head_version"]
        if isinstance(reserved_head_version, bool) or not isinstance(reserved_head_version, int):
            raise IntegrityError("HUMAN_REVIEW_TARGET_HEAD_RESERVATION_CORRUPT")
        next_head_version = int(reserved_head_version) + 1
        changed = connection.execute(
            """UPDATE human_review_target_heads
                  SET current_value_json=?,current_value_digest=?,source_decision_id=?,
                      correction_version=?,direction=?,version=?,updated_at=?
                WHERE tenant_id=? AND project_id=? AND asset_id=? AND asset_version=?
                  AND target_kind=? AND target_digest=? AND version=?
                  AND current_value_digest=?""",
            (
                effective_json,
                effective_digest,
                decision_id,
                materialized_version,
                direction.value,
                next_head_version,
                now,
                context.tenant_id,
                context.project_id,
                task["asset_id"],
                asset_version,
                task["target_kind"],
                task_target_digest,
                reservation_payload["reserved_head_version"],
                expected_current_digest,
            ),
        ).rowcount
        if changed != 1:
            raise ConflictError("HUMAN_REVIEW_SOURCE_DRIFT")
        return next_head_version

    def _materialize_if_complete(
        self,
        connection: sqlite3.Connection,
        context: TenantContext,
        *,
        decision_id: str,
    ) -> dict[str, Any] | None:
        reservation = self._decision_reservation(
            connection, context, decision_id=decision_id
        )
        reservation_payload = self._reservation_payload(reservation)
        if (
            reservation_payload["state"]
            != ReviewHeadReservationState.PROPAGATING.value
        ):
            raise ConflictError(
                "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_NOT_OPERATIONAL"
            )
        rows = connection.execute(
            """SELECT * FROM human_review_propagation_tasks
                WHERE tenant_id=? AND project_id=? AND decision_id=? ORDER BY channel""",
            (context.tenant_id, context.project_id, decision_id),
        ).fetchall()
        if len(rows) != len(_PROPAGATION_CHANNELS):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_SET_INCOMPLETE")
        if any(row["state"] != ReviewPropagationState.SUCCEEDED.value for row in rows):
            return None
        if {row["channel"] for row in rows} != set(_PROPAGATION_CHANNELS):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_SET_INVALID")
        payloads = [
            self._decode_content(
                row["payload_json"],
                row["payload_digest"],
                "HUMAN_REVIEW_PROPAGATION_CORRUPT",
            )
            for row in rows
        ]
        if any(not isinstance(payload, dict) for payload in payloads):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
        first = payloads[0]
        required_fields = _PROPAGATION_PAYLOAD_V2_FIELDS
        if (
            set(first) != required_fields
            or first.get("schema_version") != "human-review-propagation-v2"
            or first.get("tenant_id") != context.tenant_id
            or first.get("project_id") != context.project_id
            or first.get("decision_id") != decision_id
        ):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
        try:
            correction_version = _safe_version(
                first["correction_version"], "HUMAN_REVIEW_PROPAGATION_CORRUPT"
            )
            correction_digest = normalize_sha256(first["correction_digest"])
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT") from error
        if (
            correction_version != reservation_payload["correction_version"]
            or f"sha256:{correction_digest}"
            != reservation_payload["correction_digest"]
        ):
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_RESERVATION_DRIFT")
        for row, payload in zip(rows, payloads, strict=True):
            if (
                set(payload) != required_fields
                or payload.get("schema_version") != "human-review-propagation-v2"
                or payload.get("tenant_id") != context.tenant_id
                or payload.get("project_id") != context.project_id
                or payload.get("task_id") != first.get("task_id")
                or payload.get("decision_id") != decision_id
                or payload.get("channel") != row["channel"]
                or payload.get("direction") != first.get("direction")
                or payload.get("correction_version") != first.get("correction_version")
                or payload.get("correction_digest") != first.get("correction_digest")
                or payload.get("target_kind") != first.get("target_kind")
                or payload.get("target") != first.get("target")
                or payload.get("effective_value") != first.get("effective_value")
                or payload.get("effective_value_digest")
                != first.get("effective_value_digest")
                or payload.get("source_digest") != first.get("source_digest")
                or payload.get("prior_effective_version")
                != first.get("prior_effective_version")
                or payload.get("prior_effective_value")
                != first.get("prior_effective_value")
                or payload.get("prior_effective_digest")
                != first.get("prior_effective_digest")
                or payload.get("reservation_id")
                != reservation_payload["reservation_id"]
                or payload.get("reservation_fence")
                != reservation_payload["reservation_fence"]
                or payload.get("reservation_binding_digest")
                != reservation_payload["binding_digest"]
                or row["task_id"] != first.get("task_id")
                or row["direction"] != first.get("direction")
                or int(row["correction_version"]) != correction_version
            ):
                raise IntegrityError("HUMAN_REVIEW_PROPAGATION_DRIFT")
        try:
            direction = ReviewPropagationDirection(first["direction"])
            prior_effective_version = _safe_version(
                first["prior_effective_version"],
                "HUMAN_REVIEW_PROPAGATION_CORRUPT",
                allow_zero=True,
            )
            prior_effective_value = bounded_review_json(first["prior_effective_value"])
            prior_effective_digest = normalize_sha256(first["prior_effective_digest"])
            if (
                normalize_sha256(content_contract_digest(prior_effective_value))
                != prior_effective_digest
            ):
                raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
            effective_value = bounded_review_json(first["effective_value"])
            effective_digest = normalize_sha256(first["effective_value_digest"])
            if normalize_sha256(content_contract_digest(effective_value)) != effective_digest:
                raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT")
            target_kind = ReviewTargetKind(first["target_kind"])
            target = bounded_review_json(first["target"], allow_none=False)
            target_json = content_contract_json(target)
            source_digest = normalize_sha256(first["source_digest"])
        except IntegrityError:
            raise
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("HUMAN_REVIEW_PROPAGATION_CORRUPT") from error
        effective_json = content_contract_json(effective_value)
        now = utc_now()
        for row in rows:
            connection.execute(
                """INSERT INTO human_review_effective_projections (
                    tenant_id,project_id,task_id,channel,source_decision_id,
                    correction_version,direction,target_kind,target_json,
                    effective_value_json,effective_value_digest,source_digest,version,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?)
                ON CONFLICT(tenant_id,project_id,task_id,channel) DO UPDATE SET
                    source_decision_id=excluded.source_decision_id,
                    correction_version=excluded.correction_version,
                    direction=excluded.direction,
                    target_kind=excluded.target_kind,
                    target_json=excluded.target_json,
                    effective_value_json=excluded.effective_value_json,
                    effective_value_digest=excluded.effective_value_digest,
                    source_digest=excluded.source_digest,
                    version=human_review_effective_projections.version+1,
                    updated_at=excluded.updated_at""",
                (
                    context.tenant_id,
                    context.project_id,
                    first["task_id"],
                    row["channel"],
                    decision_id,
                    correction_version,
                    direction.value,
                    target_kind.value,
                    target_json,
                    effective_json,
                    effective_digest,
                    source_digest,
                    now,
                ),
            )
        task = self._scoped_task(connection, context, first["task_id"])
        expected_state = (
            ReviewTaskState.APPROVED
            if direction is ReviewPropagationDirection.APPLY
            else ReviewTaskState.REVERTING
        )
        next_state = (
            ReviewTaskState.APPROVED
            if direction is ReviewPropagationDirection.APPLY
            else ReviewTaskState.REVERTED
        )
        if ReviewTaskState(task["state"]) is not expected_state:
            raise ConflictError("HUMAN_REVIEW_MATERIALIZATION_STATE_CONFLICT")
        materialized_version = (
            correction_version
            if direction is ReviewPropagationDirection.APPLY
            else prior_effective_version
        )
        head_version = self._materialize_target_head(
            connection,
            context,
            task=task,
            reservation=reservation,
            decision_id=decision_id,
            direction=direction,
            correction_version=correction_version,
            materialized_version=materialized_version,
            effective_json=effective_json,
            effective_digest=effective_digest,
            prior_effective_version=prior_effective_version,
            prior_effective_digest=prior_effective_digest,
            now=now,
        )
        next_task_version = int(task["version"]) + 1
        changed = connection.execute(
            """UPDATE human_review_tasks
                  SET state=?,effective_version=?,effective_digest=?,version=?,
                      updated_at=?,closed_at=?
                WHERE tenant_id=? AND project_id=? AND task_id=? AND version=?""",
            (
                next_state.value,
                materialized_version,
                effective_digest,
                next_task_version,
                now,
                now,
                context.tenant_id,
                context.project_id,
                task["task_id"],
                task["version"],
            ),
        ).rowcount
        if changed != 1:
            raise ConflictError("HUMAN_REVIEW_TASK_VERSION_CONFLICT")
        terminal_reservation_state = (
            ReviewHeadReservationState.APPLIED
            if direction is ReviewPropagationDirection.APPLY
            else ReviewHeadReservationState.REVERTED
        )
        reservation = self._set_reservation_state(
            connection,
            context,
            reservation=reservation,
            state=terminal_reservation_state,
            materialized_head_version=head_version,
        )
        terminal_reservation = self._reservation_payload(reservation)
        event_type = (
            "correction.propagated"
            if direction is ReviewPropagationDirection.APPLY
            else "correction.reverted"
        )
        self._audit(
            connection,
            context,
            task_id=task["task_id"],
            event_type=event_type,
            prior_state=task["state"],
            next_state=next_state.value,
            task_version=next_task_version,
            details={
                "decision_id": decision_id,
                "direction": direction.value,
                "effective_version": materialized_version,
                "effective_value_digest": f"sha256:{effective_digest}",
                "target_head_version": head_version,
                "reservation_id": terminal_reservation["reservation_id"],
                "reservation_fence": terminal_reservation["reservation_fence"],
                "channels": list(_PROPAGATION_CHANNELS),
            },
        )
        self._store._event(
            connection,
            context,
            "human_review_task",
            task["task_id"],
            event_type,
            f"{event_type}:{decision_id}",
            {
                "task_id": task["task_id"],
                "decision_id": decision_id,
                "effective_version": materialized_version,
                "effective_digest": f"sha256:{effective_digest}",
                "target_head_version": head_version,
            },
        )
        updated = self._scoped_task(connection, context, task["task_id"])
        effective = self._status_payload(connection, context, updated).get("effective")
        if not isinstance(effective, dict):
            raise IntegrityError("HUMAN_REVIEW_TASK_CORRUPT")
        return effective

    def complete_propagation(
        self,
        context: TenantContext,
        *,
        propagation_id: str,
        capability_id: str,
        capability_token: str,
        owner_token: str,
        claim_fence: int,
        outcome: str,
        result: Any,
        failure_code: str | None,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_propagation_id = require_resource_id(propagation_id, "propagation_id")
        safe_capability_id = require_resource_id(capability_id, "capability_id")
        _owner, owner_digest = _token_digest(owner_token, "HUMAN_REVIEW_OWNER_TOKEN_INVALID")
        safe_fence = _safe_version(claim_fence, "HUMAN_REVIEW_CLAIM_FENCE_INVALID")
        if outcome not in {
            ReviewPropagationState.SUCCEEDED.value,
            ReviewPropagationState.FAILED.value,
            ReviewPropagationState.UNKNOWN.value,
        }:
            raise ValidationError("HUMAN_REVIEW_PROPAGATION_OUTCOME_INVALID")
        safe_result = bounded_review_json(result)
        safe_failure: str | None = None
        if outcome == ReviewPropagationState.SUCCEEDED.value:
            if failure_code is not None:
                raise ValidationError("HUMAN_REVIEW_PROPAGATION_FAILURE_CODE_INVALID")
        else:
            if not isinstance(failure_code, str):
                raise ValidationError("HUMAN_REVIEW_PROPAGATION_FAILURE_CODE_REQUIRED")
            safe_failure = require_resource_id(failure_code, "failure_code")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        with self._store.transaction() as connection:
            worker_capability = self._worker_identity(
                connection,
                context,
                capability_id=safe_capability_id,
                capability_token=capability_token,
                action="complete",
            )
            replay = self._receipt(
                connection,
                context,
                operation="propagation_complete",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            self._require_worker_active(worker_capability)
            row = self._scoped_propagation(connection, context, safe_propagation_id)
            reservation = self._propagation_reservation(connection, context, row)
            reservation_state = ReviewHeadReservationState(
                self._reservation_payload(reservation)["state"]
            )
            if reservation_state in {
                ReviewHeadReservationState.APPLIED,
                ReviewHeadReservationState.REVERTED,
            }:
                raise ConflictError(
                    "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_TERMINAL"
                )
            self._require_propagation_claim(
                row,
                capability_id=safe_capability_id,
                owner_digest=owner_digest,
                claim_fence=safe_fence,
                require_dispatched=True,
            )
            result_document = {
                "schema_version": "human-review-propagation-result-v1",
                "outcome": outcome,
                "worker_result": safe_result,
                "capability_id": safe_capability_id,
                "worker_id": context.actor_id,
                "claim_fence": safe_fence,
            }
            _result_copy, result_json, result_digest = self._content_json(
                result_document, "HUMAN_REVIEW_PROPAGATION_RESULT_INVALID"
            )
            now = utc_now()
            next_version = int(row["version"]) + 1
            reconciliation_required = int(outcome == ReviewPropagationState.UNKNOWN.value)
            completed_at = (
                None if outcome == ReviewPropagationState.UNKNOWN.value else now
            )
            changed = connection.execute(
                """UPDATE human_review_propagation_tasks
                      SET state=?,claim_capability_id=NULL,claim_owner_digest=NULL,
                          claim_expires_at=NULL,result_json=?,result_digest=?,failure_code=?,
                          reconciliation_required=?,version=?,updated_at=?,completed_at=?
                    WHERE tenant_id=? AND project_id=? AND propagation_id=?
                      AND version=? AND state='CLAIMED' AND claim_fence=?""",
                (
                    outcome,
                    result_json,
                    result_digest,
                    safe_failure,
                    reconciliation_required,
                    next_version,
                    now,
                    completed_at,
                    context.tenant_id,
                    context.project_id,
                    safe_propagation_id,
                    row["version"],
                    safe_fence,
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("HUMAN_REVIEW_PROPAGATION_VERSION_CONFLICT")
            completed = self._scoped_propagation(connection, context, safe_propagation_id)
            synced_reservation = self._sync_reservation_state(
                connection,
                context,
                decision_id=completed["decision_id"],
            )
            self._audit(
                connection,
                context,
                task_id=completed["task_id"],
                event_type=f"propagation.{outcome.lower()}",
                prior_state=ReviewPropagationState.CLAIMED.value,
                next_state=outcome,
                task_version=self._task_version(connection, context, completed["task_id"]),
                details={
                    "propagation_id": safe_propagation_id,
                    "claim_fence": safe_fence,
                    "result_digest": f"sha256:{result_digest}",
                    "failure_code": safe_failure,
                    "automatic_retry_allowed": False
                    if outcome == ReviewPropagationState.UNKNOWN.value
                    else None,
                },
            )
            effective = None
            if (
                outcome == ReviewPropagationState.SUCCEEDED.value
                and self._reservation_payload(synced_reservation)["state"]
                == ReviewHeadReservationState.PROPAGATING.value
            ):
                effective = self._materialize_if_complete(
                    connection,
                    context,
                    decision_id=completed["decision_id"],
                )
            response = {
                "propagation": self._propagation_summary(completed),
                "effective": effective,
            }
            return self._record_receipt(
                connection,
                context,
                operation="propagation_complete",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def reconcile_propagation(
        self,
        context: TenantContext,
        *,
        propagation_id: str,
        capability_id: str,
        capability_token: str,
        outcome: str,
        result: Any,
        failure_code: str | None,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        safe_propagation_id = require_resource_id(propagation_id, "propagation_id")
        safe_capability_id = require_resource_id(capability_id, "capability_id")
        if outcome not in {"SUCCEEDED", "FAILED", "NOT_APPLIED"}:
            raise ValidationError("HUMAN_REVIEW_RECONCILIATION_OUTCOME_INVALID")
        safe_result = bounded_review_json(result)
        safe_failure: str | None = None
        if outcome == "FAILED":
            if not isinstance(failure_code, str):
                raise ValidationError("HUMAN_REVIEW_PROPAGATION_FAILURE_CODE_REQUIRED")
            safe_failure = require_resource_id(failure_code, "failure_code")
        elif failure_code is not None:
            raise ValidationError("HUMAN_REVIEW_PROPAGATION_FAILURE_CODE_INVALID")
        safe_key = require_idempotency_key(idempotency_key)
        safe_request_digest = self._request_digest(request_digest)
        with self._store.transaction() as connection:
            worker_capability = self._worker_identity(
                connection,
                context,
                capability_id=safe_capability_id,
                capability_token=capability_token,
                action="reconcile",
            )
            replay = self._receipt(
                connection,
                context,
                operation="propagation_reconcile",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
            )
            if replay is not None:
                return replay
            self._require_worker_active(worker_capability)
            row = self._scoped_propagation(connection, context, safe_propagation_id)
            reservation = self._propagation_reservation(connection, context, row)
            reservation_state = ReviewHeadReservationState(
                self._reservation_payload(reservation)["state"]
            )
            if reservation_state not in {
                ReviewHeadReservationState.UNKNOWN,
                ReviewHeadReservationState.FAILED,
            }:
                raise ConflictError(
                    "HUMAN_REVIEW_TARGET_HEAD_RESERVATION_NOT_RECONCILABLE"
                )
            if (
                row["state"] != ReviewPropagationState.UNKNOWN.value
                or int(row["reconciliation_required"]) != 1
            ):
                raise ConflictError("HUMAN_REVIEW_PROPAGATION_NOT_RECONCILABLE")
            result_document = {
                "schema_version": "human-review-reconciliation-v1",
                "verified_outcome": outcome,
                "evidence": safe_result,
                "capability_id": safe_capability_id,
                "worker_id": context.actor_id,
            }
            _result_copy, result_json, result_digest = self._content_json(
                result_document, "HUMAN_REVIEW_RECONCILIATION_RESULT_INVALID"
            )
            next_state = (
                ReviewPropagationState.PENDING.value
                if outcome == "NOT_APPLIED"
                else outcome
            )
            now = utc_now()
            next_version = int(row["version"]) + 1
            if outcome == "NOT_APPLIED":
                stored_result_json = None
                stored_result_digest = None
                dispatch_started_at = None
                completed_at = None
            else:
                stored_result_json = result_json
                stored_result_digest = result_digest
                dispatch_started_at = row["dispatch_started_at"]
                completed_at = now
            changed = connection.execute(
                """UPDATE human_review_propagation_tasks
                      SET state=?,claim_capability_id=NULL,claim_owner_digest=NULL,
                          claim_expires_at=NULL,dispatch_started_at=?,result_json=?,
                          result_digest=?,failure_code=?,reconciliation_required=0,
                          version=?,updated_at=?,completed_at=?,reconciled_at=?
                    WHERE tenant_id=? AND project_id=? AND propagation_id=?
                      AND version=? AND state='UNKNOWN' AND reconciliation_required=1""",
                (
                    next_state,
                    dispatch_started_at,
                    stored_result_json,
                    stored_result_digest,
                    safe_failure,
                    next_version,
                    now,
                    completed_at,
                    now,
                    context.tenant_id,
                    context.project_id,
                    safe_propagation_id,
                    row["version"],
                ),
            ).rowcount
            if changed != 1:
                raise ConflictError("HUMAN_REVIEW_PROPAGATION_VERSION_CONFLICT")
            reconciled = self._scoped_propagation(connection, context, safe_propagation_id)
            synced_reservation = self._sync_reservation_state(
                connection,
                context,
                decision_id=reconciled["decision_id"],
            )
            self._audit(
                connection,
                context,
                task_id=reconciled["task_id"],
                event_type="propagation.reconciled",
                prior_state=ReviewPropagationState.UNKNOWN.value,
                next_state=next_state,
                task_version=self._task_version(connection, context, reconciled["task_id"]),
                details={
                    "propagation_id": safe_propagation_id,
                    "verified_outcome": outcome,
                    "evidence_digest": f"sha256:{result_digest}",
                    "automatic_retry_allowed": outcome == "NOT_APPLIED",
                },
            )
            effective = None
            if (
                outcome == "SUCCEEDED"
                and self._reservation_payload(synced_reservation)["state"]
                == ReviewHeadReservationState.PROPAGATING.value
            ):
                effective = self._materialize_if_complete(
                    connection,
                    context,
                    decision_id=reconciled["decision_id"],
                )
            response = {
                "propagation": self._propagation_summary(reconciled),
                "effective": effective,
            }
            return self._record_receipt(
                connection,
                context,
                operation="propagation_reconcile",
                idempotency_key=safe_key,
                request_digest=safe_request_digest,
                response=response,
            )

    def review_status(
        self,
        context: TenantContext,
        *,
        task_id: str,
    ) -> dict[str, Any]:
        safe_task_id = require_resource_id(task_id, "task_id")
        with self._store._lock:
            self._store._require(self._store._connection, context, self._store.REVIEW)
            task = self._scoped_task(self._store._connection, context, safe_task_id)
            return self._status_payload(self._store._connection, context, task)

    def reservation_status(
        self,
        context: TenantContext,
        *,
        task_id: str,
    ) -> dict[str, Any]:
        """Return the exact durable reservation history for one scoped task."""

        safe_task_id = require_resource_id(task_id, "task_id")
        with self._store._lock:
            connection = self._store._connection
            self._store._require(connection, context, self._store.REVIEW)
            self._scoped_task(connection, context, safe_task_id)
            rows = connection.execute(
                """SELECT * FROM human_review_target_head_reservations
                    WHERE tenant_id=? AND project_id=? AND task_id=?
                    ORDER BY reserved_head_version,created_at,reservation_id LIMIT ?""",
                (
                    context.tenant_id,
                    context.project_id,
                    safe_task_id,
                    _MAX_SOURCE_DISCOVERY_ROWS + 1,
                ),
            ).fetchall()
            if len(rows) > _MAX_SOURCE_DISCOVERY_ROWS:
                raise IntegrityError("HUMAN_REVIEW_RESERVATION_LIMIT_EXCEEDED")
            reservations: list[dict[str, Any]] = []
            for row in rows:
                self._decision_reservation(
                    connection,
                    context,
                    decision_id=row["decision_id"],
                )
                reservations.append(self._reservation_payload(row))
            return {
                "schema_version": "human-review-target-head-reservation-status-v1",
                "task_id": safe_task_id,
                "reservations": reservations,
            }
