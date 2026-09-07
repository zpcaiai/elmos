"""Read-only, resumable progress snapshots for local HTTP transports.

This module deliberately has no network, provider, path, or command surface.
The caller supplies a host-owned :class:`IntakeStore` and an authenticated
tenant context; clients may select only one safe job/task identifier and an
opaque cursor produced by this module.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .canonical import (
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    normalize_sha256,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
)
from .errors import ConflictError, IntegrityError, ValidationError
from .models import ProcessingJob, TenantContext
from .store import IntakeStore


MAX_PROGRESS_BATCH = 64
_CURSOR = re.compile(r"^p1-([0-9]{1,16})-([0-9a-f]{64})$")
_TASK_EVENT_FIELDS = frozenset(
    {
        "tenant_id",
        "project_id",
        "skill",
        "actor_id",
        "task_id",
        "sequence_number",
        "from_state",
        "target_state",
        "idempotency_key",
        "request_digest",
        "payload_digest",
        "checkpoint_digest",
        "effects_to_skip",
        "effects_to_reconcile",
        "recorded_at",
        "event_id",
    }
)
_TASK_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "PENDING": frozenset({"RUNNING", "CANCELLED"}),
    "RUNNING": frozenset(
        {"PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"}
    ),
    "PAUSED": frozenset({"RUNNING", "CANCELLED"}),
    "FAILED_RETRYABLE": frozenset({"RUNNING", "FAILED_FINAL", "CANCELLED"}),
    "SUCCEEDED": frozenset(),
    "FAILED_FINAL": frozenset(),
    "CANCELLED": frozenset(),
}


@dataclass(frozen=True, slots=True)
class ProgressCursor:
    sequence_number: int
    content_digest: str | None


@dataclass(frozen=True, slots=True)
class ProgressBatch:
    documents: tuple[Mapping[str, Any], ...]
    heartbeat: Mapping[str, Any] | None


def parse_progress_cursor(value: str | None) -> ProgressCursor:
    """Parse only cursors emitted by this exact protocol version."""

    if value is None:
        return ProgressCursor(0, None)
    if not isinstance(value, str) or value != value.strip():
        raise ValidationError("PROGRESS_CURSOR_INVALID")
    matched = _CURSOR.fullmatch(value)
    if matched is None:
        raise ValidationError("PROGRESS_CURSOR_INVALID")
    sequence_number = int(matched.group(1))
    if not 1 <= sequence_number <= MAX_SAFE_JSON_INTEGER:
        raise ValidationError("PROGRESS_CURSOR_INVALID")
    return ProgressCursor(sequence_number, matched.group(2))


def _exact_resource_id(value: str, field: str) -> str:
    safe = require_resource_id(value, field)
    if safe != value:
        raise ValidationError("RESOURCE_ID_INVALID")
    return safe


def _finalize(document: Mapping[str, Any]) -> dict[str, Any]:
    digest = canonical_digest(document)
    sequence_number = document.get("sequence_number")
    if (
        isinstance(sequence_number, bool)
        or not isinstance(sequence_number, int)
        or not 0 <= sequence_number <= MAX_SAFE_JSON_INTEGER
    ):
        raise IntegrityError("PROGRESS_SEQUENCE_INVALID")
    return {
        **document,
        "content_digest": f"sha256:{digest}",
        "cursor": f"p1-{sequence_number}-{digest}",
    }


def _heartbeat(kind: str, resource_id: str, cursor: ProgressCursor) -> dict[str, Any]:
    document = {
        "schema_version": "1.0.0",
        "kind": f"{kind}_PROGRESS_HEARTBEAT",
        "resource_id": resource_id,
        "sequence_number": cursor.sequence_number,
        "status": "NO_CHANGE",
    }
    digest = canonical_digest(document)
    resume_cursor = (
        f"p1-{cursor.sequence_number}-{cursor.content_digest}"
        if cursor.content_digest is not None
        else None
    )
    return {
        **document,
        "content_digest": f"sha256:{digest}",
        # A heartbeat never advances the durable cursor.
        "cursor": resume_cursor,
    }


def _task_document(
    context: TenantContext,
    task_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if set(payload) != _TASK_EVENT_FIELDS:
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    if (
        payload.get("tenant_id") != context.tenant_id
        or payload.get("project_id") != context.project_id
        or payload.get("task_id") != task_id
        or payload.get("skill") != "elmos-durable-processing-and-recovery"
    ):
        raise IntegrityError("PROGRESS_TASK_EVENT_SCOPE_MISMATCH")
    sequence_number = payload.get("sequence_number")
    from_state = payload.get("from_state")
    target_state = payload.get("target_state")
    recorded_at = payload.get("recorded_at")
    if (
        isinstance(sequence_number, bool)
        or not isinstance(sequence_number, int)
        or not 1 <= sequence_number <= MAX_SAFE_JSON_INTEGER
        or not isinstance(from_state, str)
        or not isinstance(target_state, str)
        or not isinstance(recorded_at, str)
    ):
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    if from_state not in _TASK_TRANSITIONS or target_state not in _TASK_TRANSITIONS[from_state]:
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    raw_actor_id = payload.get("actor_id")
    raw_idempotency_key = payload.get("idempotency_key")
    raw_request_digest = payload.get("request_digest")
    raw_payload_digest = payload.get("payload_digest")
    raw_checkpoint_digest = payload.get("checkpoint_digest")
    if (
        not isinstance(raw_actor_id, str)
        or not isinstance(raw_idempotency_key, str)
        or not isinstance(raw_request_digest, str)
        or not isinstance(raw_payload_digest, str)
        or raw_checkpoint_digest is not None
        and not isinstance(raw_checkpoint_digest, str)
    ):
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    try:
        actor_id = require_actor_id(raw_actor_id)
        idempotency_key = require_idempotency_key(raw_idempotency_key)
        request_digest = normalize_sha256(raw_request_digest)
        payload_digest = normalize_sha256(raw_payload_digest)
        checkpoint_digest = None
        if raw_checkpoint_digest is not None:
            checkpoint_digest = normalize_sha256(raw_checkpoint_digest)
        for field in ("effects_to_skip", "effects_to_reconcile"):
            effects = payload.get(field)
            if not isinstance(effects, list) or len(effects) > 1000:
                raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
            normalized_effects = [
                require_resource_id(value, "effect_receipt_id") for value in effects
            ]
            if effects != sorted(set(normalized_effects)):
                raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
        recorded = datetime.fromisoformat(recorded_at)
        if (
            actor_id != payload.get("actor_id")
            or idempotency_key != payload.get("idempotency_key")
            or request_digest != payload.get("request_digest")
            or payload_digest != payload.get("payload_digest")
            or checkpoint_digest != payload.get("checkpoint_digest")
        ):
            raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    except IntegrityError:
        raise
    except (TypeError, ValueError, ValidationError) as error:
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT") from error
    if recorded.tzinfo is None or recorded.utcoffset() is None:
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    source_event_id = payload.get("event_id")
    expected_event_id = (
        "transition-"
        + canonical_digest({key: value for key, value in payload.items() if key != "event_id"})[:32]
    )
    if (
        not isinstance(source_event_id, str)
        or not hmac.compare_digest(source_event_id, expected_event_id)
    ):
        raise IntegrityError("PROGRESS_TASK_EVENT_CORRUPT")
    # Do not expose actor_id, idempotency keys, request/payload digests, raw
    # payloads, effect identifiers, or any other potentially sensitive input.
    return _finalize(
        {
            "schema_version": "1.0.0",
            "kind": "TASK_PROGRESS",
            "resource_id": task_id,
            "sequence_number": sequence_number,
            "event_type": "durable.task.transitioned",
            "state": target_state,
            "previous_state": from_state,
            "occurred_at": recorded_at,
        }
    )


def job_progress_sequence(job: ProcessingJob) -> int:
    """Return the database-owned monotone version carried by a stored job."""

    version = getattr(job, "version", None)
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or not 1 <= version <= MAX_SAFE_JSON_INTEGER
    ):
        raise IntegrityError("PROGRESS_JOB_VERSION_UNAVAILABLE")
    return version


def _job_document(job: ProcessingJob) -> dict[str, Any]:
    result_by_state = {
        "QUEUED": "NOT_RUN",
        "RUNNING": "NOT_RUN",
        "COMPLETED": "PASSED",
        "PARTIAL": "PARTIAL",
        "NEEDS_REVIEW": "NEEDS_REVIEW",
        "BLOCKED": "BLOCKED",
        "FAILED": "FAILED",
        "CANCELLED": "BLOCKED",
    }
    try:
        resource_id = _exact_resource_id(job.job_id, "job_id")
        updated = datetime.fromisoformat(job.updated_at)
    except (TypeError, ValueError, ValidationError) as error:
        raise IntegrityError("PROGRESS_JOB_STATE_CORRUPT") from error
    if (
        resource_id != job.job_id
        or updated.tzinfo is None
        or updated.utcoffset() is None
        or isinstance(job.attempt, bool)
        or not isinstance(job.attempt, int)
        or isinstance(job.max_attempts, bool)
        or not isinstance(job.max_attempts, int)
        or not 0 <= job.attempt <= job.max_attempts <= 20
        or job.max_attempts < 1
        or job.status.value not in result_by_state
        or job.result_status.value != result_by_state[job.status.value]
    ):
        raise IntegrityError("PROGRESS_JOB_STATE_CORRUPT")
    return _finalize(
        {
            "schema_version": "1.0.0",
            "kind": "JOB_PROGRESS",
            "resource_id": resource_id,
            "sequence_number": job_progress_sequence(job),
            "event_type": "processing.job.snapshot",
            "state": job.status.value,
            "result_status": job.result_status.value,
            "attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "occurred_at": job.updated_at,
        }
    )


class ProgressStreamReader:
    """Build canonical, bounded documents from tenant-scoped durable state."""

    def __init__(self, store: IntakeStore) -> None:
        if not isinstance(store, IntakeStore):
            raise TypeError("store must be an IntakeStore")
        self._store = store

    @staticmethod
    def _matches_cursor(document: Mapping[str, Any], cursor: ProgressCursor) -> bool:
        raw_digest = document.get("content_digest")
        return (
            document.get("sequence_number") == cursor.sequence_number
            and isinstance(raw_digest, str)
            and raw_digest.startswith("sha256:")
            and cursor.content_digest is not None
            and hmac.compare_digest(raw_digest[7:], cursor.content_digest)
        )

    def task_events(
        self,
        context: TenantContext,
        task_id: str,
        *,
        cursor: str | None,
    ) -> ProgressBatch:
        safe_task_id = _exact_resource_id(task_id, "task_id")
        parsed_cursor = parse_progress_cursor(cursor)
        snapshot = self._store.durable_task_progress_page(
            context,
            safe_task_id,
            after_sequence=parsed_cursor.sequence_number,
            limit=MAX_PROGRESS_BATCH,
        )
        latest_sequence = snapshot.get("latest_sequence")
        if (
            isinstance(latest_sequence, bool)
            or not isinstance(latest_sequence, int)
            or latest_sequence < 0
        ):
            raise IntegrityError("PROGRESS_TASK_STATE_CORRUPT")
        if parsed_cursor.sequence_number > latest_sequence:
            raise ConflictError("PROGRESS_CURSOR_AHEAD")

        after_sequence = 0
        if parsed_cursor.content_digest is not None:
            verification_event = snapshot.get("cursor_event")
            if not isinstance(verification_event, Mapping):
                raise ConflictError("PROGRESS_CURSOR_DIVERGED")
            verification = _task_document(
                context,
                safe_task_id,
                verification_event,
            )
            if not self._matches_cursor(verification, parsed_cursor):
                raise ConflictError("PROGRESS_CURSOR_DIVERGED")
            after_sequence = parsed_cursor.sequence_number

        raw_events = snapshot.get("events")
        if not isinstance(raw_events, list):
            raise IntegrityError("PROGRESS_TASK_STATE_CORRUPT")
        candidates: list[dict[str, Any]] = []
        expected_sequence = after_sequence + 1
        for payload in raw_events:
            document = _task_document(context, safe_task_id, payload)
            sequence = int(document["sequence_number"])
            if sequence != expected_sequence:
                raise IntegrityError("PROGRESS_TASK_SEQUENCE_INVALID")
            expected_sequence += 1
            candidates.append(document)

        if latest_sequence > after_sequence and not candidates:
            raise IntegrityError("PROGRESS_TASK_EVENT_MISSING")
        if candidates and len(candidates) < MAX_PROGRESS_BATCH:
            observed_latest = int(candidates[-1]["sequence_number"])
            if observed_latest != latest_sequence:
                raise IntegrityError("PROGRESS_TASK_SEQUENCE_INVALID")

        if candidates:
            return ProgressBatch(tuple(candidates), None)
        return ProgressBatch((), _heartbeat("TASK", safe_task_id, parsed_cursor))

    def job_events(
        self,
        context: TenantContext,
        job_id: str,
        *,
        cursor: str | None,
    ) -> ProgressBatch:
        safe_job_id = _exact_resource_id(job_id, "job_id")
        parsed_cursor = parse_progress_cursor(cursor)
        job = self._store.get_job(context, safe_job_id)
        document = _job_document(job)
        sequence_number = int(document["sequence_number"])
        if parsed_cursor.sequence_number > sequence_number:
            raise ConflictError("PROGRESS_CURSOR_AHEAD")
        if parsed_cursor.content_digest is not None:
            # processing_jobs keeps the current durable version, not a mutable
            # reconstruction of historical rows.  Any old or cross-resource
            # cursor therefore fails closed instead of silently skipping an
            # update or being accepted for a different job.
            if parsed_cursor.sequence_number != sequence_number:
                raise ConflictError("PROGRESS_CURSOR_DIVERGED")
            if self._matches_cursor(document, parsed_cursor):
                return ProgressBatch((), _heartbeat("JOB", safe_job_id, parsed_cursor))
            raise ConflictError("PROGRESS_CURSOR_DIVERGED")
        return ProgressBatch((document,), None)


__all__ = [
    "MAX_PROGRESS_BATCH",
    "ProgressBatch",
    "ProgressCursor",
    "ProgressStreamReader",
    "job_progress_sequence",
    "parse_progress_cursor",
]
