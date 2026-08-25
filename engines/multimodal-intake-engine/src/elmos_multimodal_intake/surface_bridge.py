"""Executable local surfaces for multimodal intake Skills 25 and 26.

The module contains no network client.  Progress webhook delivery is durable,
but an injected transport and an unforgeable worker capability are required
before any external side effect can occur.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import stat
import threading
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .canonical import (
    MAX_SAFE_JSON_INTEGER,
    canonical_digest,
    canonical_json,
    require_actor_id,
    require_idempotency_key,
    require_resource_id,
    utc_now,
)
from .errors import IntegrityError, ValidationError
from .projects import ProjectContractError, normalize_relative_path
from .skill_runtime import RuntimeContext, SKILL_REGISTRY
from .webhooks import WebhookSigner


UI_SKILL = "elmos-multimodal-input-workbench-ui"
API_SKILL = "elmos-ingestion-api-and-sdk"
_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_DELIVERY_STATES = frozenset(
    {"PENDING", "CLAIMED", "DELIVERED", "RETRYABLE", "FAILED", "UNKNOWN"}
)
_MAX_PROGRESS_DELIVERY_ATTEMPTS = 10
_TRANSPORT_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "delivery_id",
        "body_digest",
        "delivery_state",
        "provider_message_id",
        "failure_code",
        "retryable",
    }
)
_PROGRESS_DELIVERY_COLUMNS = frozenset(
    {
        "tenant_id", "project_id", "actor_id", "delivery_id", "idempotency_key",
        "request_digest", "endpoint_ref", "event_type", "body_json", "body_digest",
        "state", "attempt", "claim_token_digest", "failure_code", "next_attempt_at",
        "transport_receipt_json", "transport_receipt_digest", "delivered_at",
        "created_at", "updated_at",
    }
)


class ProgressWebhookTransport(Protocol):
    def deliver(self, *, endpoint_ref: str, headers: Mapping[str, str], body: bytes) -> Mapping[str, Any]: ...


class ProgressDeliveryStore:
    """SQLite-backed claim/retry queue; endpoints are opaque trusted references."""

    def __init__(
        self,
        database: str | Path,
        *,
        worker_capability: object,
        producer_capability: object,
        transport: ProgressWebhookTransport | None = None,
        signer: WebhookSigner | None = None,
    ) -> None:
        path = Path(database).expanduser()
        if (
            not path.is_absolute()
            or path == Path(path.anchor)
            or worker_capability is None
            or producer_capability is None
            or producer_capability is worker_capability
        ):
            raise ValidationError("PROGRESS_DELIVERY_CONFIGURATION_INVALID")
        if transport is not None and not callable(getattr(transport, "deliver", None)):
            raise ValidationError("PROGRESS_WEBHOOK_TRANSPORT_INVALID")
        if signer is not None and not isinstance(signer, WebhookSigner):
            raise ValidationError("PROGRESS_WEBHOOK_SIGNER_INVALID")
        parent = path.parent
        existed = parent.exists() or parent.is_symlink()
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not existed:
            parent.chmod(0o700)
        parent_metadata = parent.stat()
        wrong_parent_owner = (
            hasattr(os, "geteuid") and parent_metadata.st_uid != os.geteuid()
        )
        if (
            parent.is_symlink()
            or not parent.is_dir()
            or wrong_parent_owner
            or parent_metadata.st_mode & 0o077
        ):
            raise ValidationError("PROGRESS_DELIVERY_DATABASE_PERMISSIONS_INVALID")
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValidationError("PROGRESS_DELIVERY_DATABASE_INVALID")
        if path.exists():
            metadata = path.stat()
            wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
            if wrong_owner or metadata.st_mode & 0o077:
                raise ValidationError("PROGRESS_DELIVERY_DATABASE_PERMISSIONS_INVALID")
        else:
            flags = (
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            try:
                descriptor = os.open(path, flags, 0o600)
            except OSError as error:
                raise ValidationError("PROGRESS_DELIVERY_DATABASE_INVALID") from error
            else:
                os.close(descriptor)
        self._connection = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._closed = False
        self._lock = threading.RLock()
        self._worker_capability = worker_capability
        self._producer_capability = producer_capability
        self._transport = transport
        self._signer = signer
        try:
            self._connection.executescript(
                """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS multimodal_progress_deliveries (
              tenant_id TEXT NOT NULL,
              project_id TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              delivery_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              endpoint_ref TEXT NOT NULL,
              event_type TEXT NOT NULL,
              body_json TEXT NOT NULL,
              body_digest TEXT NOT NULL,
              state TEXT NOT NULL,
              attempt INTEGER NOT NULL DEFAULT 0,
              claim_token_digest TEXT,
              failure_code TEXT,
              next_attempt_at TEXT,
              transport_receipt_json TEXT,
              transport_receipt_digest TEXT,
              delivered_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id,project_id,actor_id,delivery_id),
              UNIQUE (tenant_id,project_id,actor_id,idempotency_key)
            ) WITHOUT ROWID;
                """
            )
            self._migrate_legacy_schema()
        except Exception:
            self._connection.close()
            raise

    def _migrate_legacy_schema(self) -> None:
        """Upgrade the initial local-only queue without inventing delivery success."""

        columns = {
            str(row[1])
            for row in self._connection.execute(
                "PRAGMA table_info(multimodal_progress_deliveries)"
            ).fetchall()
        }
        additions = {
            "idempotency_key": "TEXT",
            "request_digest": "TEXT",
            "transport_receipt_json": "TEXT",
            "transport_receipt_digest": "TEXT",
            "delivered_at": "TEXT",
        }
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for name, declaration in additions.items():
                    if name not in columns:
                        self._connection.execute(
                            f"ALTER TABLE multimodal_progress_deliveries ADD COLUMN {name} {declaration}"
                        )
                self._connection.execute(
                    """UPDATE multimodal_progress_deliveries
                    SET idempotency_key=COALESCE(idempotency_key,'legacy-' || delivery_id)
                    WHERE idempotency_key IS NULL"""
                )
                legacy_rows = self._connection.execute(
                    """SELECT * FROM multimodal_progress_deliveries
                    WHERE request_digest IS NULL OR idempotency_key LIKE 'legacy-%'"""
                ).fetchall()
                for row in legacy_rows:
                    request_digest = canonical_digest(
                        {
                            "schema_version": "1.0.0",
                            "tenant_id": row["tenant_id"],
                            "project_id": row["project_id"],
                            "actor_id": row["actor_id"],
                            "idempotency_key": row["idempotency_key"],
                            "endpoint_ref": row["endpoint_ref"],
                            "event_type": row["event_type"],
                            "body_digest": row["body_digest"],
                        }
                    )
                    self._connection.execute(
                        """UPDATE multimodal_progress_deliveries
                        SET request_digest=?,state='UNKNOWN',
                            failure_code='PROGRESS_LEGACY_RECONCILIATION_REQUIRED',
                            claim_token_digest=NULL,next_attempt_at=NULL,updated_at=?
                        WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                        (
                            request_digest, utc_now(), row["tenant_id"],
                            row["project_id"], row["actor_id"], row["delivery_id"],
                        ),
                    )
                self._connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS multimodal_progress_idempotency_idx
                    ON multimodal_progress_deliveries
                    (tenant_id,project_id,actor_id,idempotency_key)"""
                )
                actual_columns = {
                    str(row[1])
                    for row in self._connection.execute(
                        "PRAGMA table_info(multimodal_progress_deliveries)"
                    ).fetchall()
                }
                if actual_columns != _PROGRESS_DELIVERY_COLUMNS:
                    raise IntegrityError("PROGRESS_DELIVERY_SCHEMA_INVALID")
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._connection.close()

    @staticmethod
    def _scope(ctx: RuntimeContext) -> tuple[str, str, str]:
        return (
            require_resource_id(ctx.tenant_id, "tenant_id"),
            require_resource_id(ctx.project_id, "project_id"),
            require_actor_id(ctx.actor_id),
        )

    @staticmethod
    def _attempt(row: sqlite3.Row) -> int:
        value = row["attempt"]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _MAX_PROGRESS_DELIVERY_ATTEMPTS:
            raise IntegrityError("PROGRESS_DELIVERY_ATTEMPT_CORRUPT")
        return value

    def prepare(
        self,
        ctx: RuntimeContext,
        *,
        endpoint_ref: str,
        event_type: str,
        event: Mapping[str, Any],
        idempotency_key: str,
        capability: object,
    ) -> dict[str, Any]:
        if capability is not self._producer_capability:
            raise ValidationError("PROGRESS_DELIVERY_PRODUCER_UNAUTHORIZED")
        tenant_id, project_id, actor_id = self._scope(ctx)
        if not isinstance(endpoint_ref, str) or not re.fullmatch(r"endpoint-ref:[A-Za-z0-9][A-Za-z0-9._:-]{0,242}", endpoint_ref):
            raise ValidationError("WEBHOOK_ENDPOINT_REFERENCE_INVALID")
        if not isinstance(event_type, str) or not re.fullmatch(r"intake\.[a-z0-9][a-z0-9_.-]{0,120}", event_type):
            raise ValidationError("PROGRESS_EVENT_TYPE_INVALID")
        body = self._progress_envelope(
            tenant_id=tenant_id,
            project_id=project_id,
            event_type=event_type,
            event=event,
        )
        idempotency_key = require_idempotency_key(idempotency_key)
        if len(idempotency_key.encode("utf-8")) < 8:
            raise ValidationError("PROGRESS_DELIVERY_IDEMPOTENCY_KEY_REQUIRED")
        delivery_id = "delivery-" + canonical_digest(
            [tenant_id, project_id, actor_id, idempotency_key]
        )[:40]
        body_json = canonical_json(body)
        if len(body_json.encode("utf-8")) > 1024 * 1024:
            raise ValidationError("PROGRESS_EVENT_TOO_LARGE")
        body_digest = canonical_digest(body)
        request_digest = canonical_digest(
            {
                "schema_version": "1.0.0",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "endpoint_ref": endpoint_ref,
                "event_type": event_type,
                "body_digest": body_digest,
            }
        )
        now = utc_now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """INSERT OR IGNORE INTO multimodal_progress_deliveries (
                        tenant_id,project_id,actor_id,delivery_id,idempotency_key,
                        request_digest,endpoint_ref,event_type,body_json,body_digest,
                        state,attempt,claim_token_digest,failure_code,next_attempt_at,
                        transport_receipt_json,transport_receipt_digest,delivered_at,
                        created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',0,NULL,NULL,NULL,NULL,NULL,NULL,?,?)""",
                    (
                        tenant_id, project_id, actor_id, delivery_id,
                        idempotency_key, request_digest, endpoint_ref,
                        event_type, body_json, body_digest, now, now,
                    ),
                )
                row = self._connection.execute(
                    """SELECT * FROM multimodal_progress_deliveries
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND idempotency_key=?""",
                    (tenant_id, project_id, actor_id, idempotency_key),
                ).fetchone()
                if (
                    row is None
                    or not hmac.compare_digest(str(row["request_digest"]), request_digest)
                    or row["delivery_id"] != delivery_id
                ):
                    raise ValidationError("PROGRESS_DELIVERY_IDEMPOTENCY_CONFLICT")
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self._public(row)

    @staticmethod
    def _progress_envelope(
        *,
        tenant_id: str,
        project_id: str,
        event_type: str,
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected = {
            "job_id", "sequence", "occurred_at", "trace_id", "state", "progress", "payload"
        }
        if not isinstance(event, Mapping) or set(event) != expected:
            raise ValidationError("PROGRESS_EVENT_INVALID")
        raw_job_id = event.get("job_id")
        if not isinstance(raw_job_id, str):
            raise ValidationError("PROGRESS_EVENT_INVALID")
        job_id = require_resource_id(raw_job_id, "job_id")
        sequence = event.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or not 0 <= sequence <= MAX_SAFE_JSON_INTEGER
        ):
            raise ValidationError("PROGRESS_EVENT_SEQUENCE_INVALID")
        occurred_at = event.get("occurred_at")
        if not isinstance(occurred_at, str):
            raise ValidationError("PROGRESS_EVENT_TIME_INVALID")
        try:
            parsed_time = datetime.fromisoformat(
                occurred_at[:-1] + "+00:00"
                if occurred_at.endswith("Z")
                else occurred_at
            )
        except (TypeError, ValueError):
            raise ValidationError("PROGRESS_EVENT_TIME_INVALID") from None
        if (
            not 1 <= len(occurred_at.encode("utf-8")) <= 64
            or parsed_time.tzinfo is None
        ):
            raise ValidationError("PROGRESS_EVENT_TIME_INVALID")
        trace_id = event.get("trace_id")
        if (
            not isinstance(trace_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", trace_id)
        ):
            raise ValidationError("PROGRESS_EVENT_TRACE_INVALID")
        state = event.get("state")
        if state not in {
            "PENDING", "RUNNING", "PARTIAL", "SUCCEEDED", "BLOCKED", "FAILED", "CANCELLED"
        }:
            raise ValidationError("PROGRESS_EVENT_STATE_INVALID")
        progress = event.get("progress")
        if not isinstance(progress, Mapping) or set(progress) != {
            "completed_units", "total_units", "percent"
        }:
            raise ValidationError("PROGRESS_EVENT_PROGRESS_INVALID")
        completed = progress.get("completed_units")
        total = progress.get("total_units")
        percent = progress.get("percent")
        if (
            not isinstance(completed, int)
            or isinstance(completed, bool)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or not 0 <= completed <= MAX_SAFE_JSON_INTEGER
            or not 1 <= total <= MAX_SAFE_JSON_INTEGER
            or completed > total
            or not isinstance(percent, (int, float))
            or isinstance(percent, bool)
            or not math.isfinite(float(percent))
            or not 0 <= float(percent) <= 100
            or abs(float(percent) - completed * 100.0 / total) > 0.01
        ):
            raise ValidationError("PROGRESS_EVENT_PROGRESS_INVALID")
        payload = event.get("payload")
        allowed_payload = {
            "asset_id", "asset_version", "checkpoint_id", "code", "message",
            "result_digest", "retryable",
        }
        if not isinstance(payload, Mapping) or set(payload) - allowed_payload:
            raise ValidationError("PROGRESS_EVENT_PAYLOAD_INVALID")
        normalized_payload = dict(payload)
        for field in ("asset_id", "checkpoint_id"):
            if field in normalized_payload:
                normalized_payload[field] = require_resource_id(normalized_payload[field], field)
        asset_version = normalized_payload.get("asset_version")
        if asset_version is not None and (
            not isinstance(asset_version, int)
            or isinstance(asset_version, bool)
            or not 1 <= asset_version <= MAX_SAFE_JSON_INTEGER
        ):
            raise ValidationError("PROGRESS_EVENT_PAYLOAD_INVALID")
        code = normalized_payload.get("code")
        if code is not None and (
            not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_:-]{0,127}", code)
        ):
            raise ValidationError("PROGRESS_EVENT_PAYLOAD_INVALID")
        message = normalized_payload.get("message")
        if message is not None and (
            not isinstance(message, str)
            or len(message) > 2048
            or any(ord(character) < 32 and character not in "\t\n\r" for character in message)
        ):
            raise ValidationError("PROGRESS_EVENT_PAYLOAD_INVALID")
        result_digest = normalized_payload.get("result_digest")
        if result_digest is not None and (
            not isinstance(result_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", result_digest)
        ):
            raise ValidationError("PROGRESS_EVENT_PAYLOAD_INVALID")
        if "retryable" in normalized_payload and not isinstance(normalized_payload["retryable"], bool):
            raise ValidationError("PROGRESS_EVENT_PAYLOAD_INVALID")
        payload_digest = canonical_digest(normalized_payload)
        event_id = "event-" + canonical_digest(
            [tenant_id, project_id, job_id, sequence, event_type, payload_digest]
        )[:40]
        unsigned = {
            "schema_version": "1.0.0",
            "event_id": event_id,
            "event_type": event_type,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "job_id": job_id,
            "sequence": sequence,
            "occurred_at": occurred_at,
            "trace_id": trace_id,
            "state": state,
            "progress": {
                "completed_units": completed,
                "total_units": total,
                "percent": float(percent),
            },
            "payload_digest": payload_digest,
            "payload": normalized_payload,
        }
        return {**unsigned, "event_digest": canonical_digest(unsigned)}

    def claim(self, ctx: RuntimeContext, *, delivery_id: str, claim_token: str, capability: object) -> dict[str, Any]:
        if capability is not self._worker_capability:
            raise ValidationError("PROGRESS_DELIVERY_WORKER_UNAUTHORIZED")
        if not isinstance(delivery_id, str) or not re.fullmatch(r"delivery-[0-9a-f]{40}", delivery_id):
            raise ValidationError("PROGRESS_DELIVERY_ID_INVALID")
        if not isinstance(claim_token, str) or not re.fullmatch(r"[\x21-\x7e]{16,256}", claim_token):
            raise ValidationError("PROGRESS_DELIVERY_CLAIM_TOKEN_INVALID")
        tenant_id, project_id, actor_id = self._scope(ctx)
        token_digest = canonical_digest(claim_token)
        now = utc_now()
        lease_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=60)
        ).isoformat()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """SELECT * FROM multimodal_progress_deliveries
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                    (tenant_id, project_id, actor_id, delivery_id),
                ).fetchone()
                if (
                    row is not None
                    and row["state"] == "CLAIMED"
                    and row["next_attempt_at"] is not None
                    and row["next_attempt_at"] <= now
                ):
                    raise ValidationError("PROGRESS_DELIVERY_OUTCOME_UNKNOWN")
                if (
                    row is not None
                    and row["state"] in {"PENDING", "RETRYABLE"}
                    and self._attempt(row) >= _MAX_PROGRESS_DELIVERY_ATTEMPTS
                ):
                    raise ValidationError("PROGRESS_DELIVERY_ATTEMPT_LIMIT")
                if (
                    row is None
                    or not (
                        row["state"] == "PENDING"
                        or row["state"] == "RETRYABLE"
                        and row["next_attempt_at"] is not None
                        and row["next_attempt_at"] <= now
                    )
                ):
                    raise ValidationError("PROGRESS_DELIVERY_NOT_CLAIMABLE")
                self._connection.execute(
                    """UPDATE multimodal_progress_deliveries
                    SET state='CLAIMED',attempt=attempt+1,claim_token_digest=?,next_attempt_at=?,updated_at=?
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                    (token_digest, lease_expires_at, now, tenant_id, project_id, actor_id, delivery_id),
                )
                claimed = self._connection.execute(
                    """SELECT * FROM multimodal_progress_deliveries
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                    (tenant_id, project_id, actor_id, delivery_id),
                ).fetchone()
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        result = self._public(claimed)
        result["body_json"] = claimed["body_json"]
        return result

    def complete(
        self,
        ctx: RuntimeContext,
        *,
        delivery_id: str,
        claim_token: str,
        capability: object,
        transport_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        if capability is not self._worker_capability:
            raise ValidationError("PROGRESS_DELIVERY_WORKER_UNAUTHORIZED")
        if not isinstance(delivery_id, str) or not re.fullmatch(r"delivery-[0-9a-f]{40}", delivery_id):
            raise ValidationError("PROGRESS_DELIVERY_ID_INVALID")
        if not isinstance(claim_token, str) or not re.fullmatch(r"[\x21-\x7e]{16,256}", claim_token):
            raise ValidationError("PROGRESS_DELIVERY_CLAIM_TOKEN_INVALID")
        tenant_id, project_id, actor_id = self._scope(ctx)
        token_digest = canonical_digest(claim_token)
        now = utc_now()
        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM multimodal_progress_deliveries
                WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                (tenant_id, project_id, actor_id, delivery_id),
            ).fetchone()
            if (
                row is None
                or row["state"] != "CLAIMED"
                or not isinstance(row["claim_token_digest"], str)
                or not hmac.compare_digest(row["claim_token_digest"], token_digest)
            ):
                raise ValidationError("PROGRESS_DELIVERY_CLAIM_LOST")
            normalized = self._validated_transport_receipt(
                transport_receipt,
                delivery_id=delivery_id,
                body_digest=str(row["body_digest"]),
                allow_unknown=True,
            )
            state = str(normalized["delivery_state"])
            if state == "RETRYABLE" and self._attempt(row) >= _MAX_PROGRESS_DELIVERY_ATTEMPTS:
                normalized = self._local_transport_receipt(
                    delivery_id=delivery_id,
                    body_digest=str(row["body_digest"]),
                    state="FAILED",
                    failure_code="PROGRESS_DELIVERY_ATTEMPT_LIMIT",
                )
                state = "FAILED"
            failure_code = normalized["failure_code"]
            receipt_json = canonical_json(normalized)
            receipt_digest = canonical_digest(normalized)
            next_attempt_at = (
                (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
                if state == "RETRYABLE"
                else None
            )
            delivered_at = now if state == "DELIVERED" else None
            cursor = self._connection.execute(
                """UPDATE multimodal_progress_deliveries
                SET state=?,failure_code=?,next_attempt_at=?,claim_token_digest=NULL,
                    transport_receipt_json=?,transport_receipt_digest=?,delivered_at=?,updated_at=?
                WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?
                  AND state='CLAIMED' AND claim_token_digest=?""",
                (
                    state, failure_code, next_attempt_at, receipt_json, receipt_digest,
                    delivered_at, now, tenant_id, project_id, actor_id, delivery_id,
                    token_digest,
                ),
            )
            if cursor.rowcount != 1:
                raise ValidationError("PROGRESS_DELIVERY_CLAIM_LOST")
            row = self._connection.execute(
                """SELECT * FROM multimodal_progress_deliveries
                WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                (tenant_id, project_id, actor_id, delivery_id),
            ).fetchone()
        return self._public(row)

    @staticmethod
    def _validated_transport_receipt(
        receipt: Mapping[str, Any],
        *,
        delivery_id: str,
        body_digest: str,
        allow_unknown: bool,
    ) -> dict[str, Any]:
        if not isinstance(receipt, Mapping) or set(receipt) != _TRANSPORT_RECEIPT_FIELDS:
            raise ValidationError("PROGRESS_TRANSPORT_RECEIPT_INVALID")
        state = receipt.get("delivery_state")
        allowed_states = {"DELIVERED", "RETRYABLE", "FAILED"}
        if allow_unknown:
            allowed_states.add("UNKNOWN")
        provider_message_id = receipt.get("provider_message_id")
        failure_code = receipt.get("failure_code")
        retryable = receipt.get("retryable")
        if (
            receipt.get("schema_version") != "1.0.0"
            or receipt.get("delivery_id") != delivery_id
            or receipt.get("body_digest") != body_digest
            or state not in allowed_states
            or not isinstance(retryable, bool)
            or provider_message_id is not None
            and (
                not isinstance(provider_message_id, str)
                or not 1 <= len(provider_message_id.encode("utf-8")) <= 256
                or any(ord(character) < 32 or ord(character) == 127 for character in provider_message_id)
            )
            or failure_code is not None
            and (
                not isinstance(failure_code, str)
                or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", failure_code)
            )
        ):
            raise ValidationError("PROGRESS_TRANSPORT_RECEIPT_INVALID")
        if state == "DELIVERED":
            valid_outcome = provider_message_id is not None and failure_code is None and not retryable
        elif state == "RETRYABLE":
            valid_outcome = failure_code is not None and provider_message_id is None and retryable
        else:
            valid_outcome = failure_code is not None and provider_message_id is None and not retryable
        if not valid_outcome:
            raise ValidationError("PROGRESS_TRANSPORT_RECEIPT_INVALID")
        return dict(receipt)

    @staticmethod
    def _local_transport_receipt(
        *,
        delivery_id: str,
        body_digest: str,
        state: str,
        failure_code: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "delivery_id": delivery_id,
            "body_digest": body_digest,
            "delivery_state": state,
            "provider_message_id": None,
            "failure_code": failure_code,
            "retryable": state == "RETRYABLE",
        }

    def reconcile(
        self,
        ctx: RuntimeContext,
        *,
        delivery_id: str,
        capability: object,
        transport_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply an exact provider query result to UNKNOWN or expired work."""

        if capability is not self._worker_capability:
            raise ValidationError("PROGRESS_DELIVERY_WORKER_UNAUTHORIZED")
        if not isinstance(delivery_id, str) or not re.fullmatch(r"delivery-[0-9a-f]{40}", delivery_id):
            raise ValidationError("PROGRESS_DELIVERY_ID_INVALID")
        tenant_id, project_id, actor_id = self._scope(ctx)
        now = utc_now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """SELECT * FROM multimodal_progress_deliveries
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                    (tenant_id, project_id, actor_id, delivery_id),
                ).fetchone()
                expired_claim = (
                    row is not None
                    and row["state"] == "CLAIMED"
                    and row["next_attempt_at"] is not None
                    and row["next_attempt_at"] <= now
                )
                if row is None or row["state"] != "UNKNOWN" and not expired_claim:
                    raise ValidationError("PROGRESS_DELIVERY_NOT_RECONCILABLE")
                normalized = self._validated_transport_receipt(
                    transport_receipt,
                    delivery_id=delivery_id,
                    body_digest=str(row["body_digest"]),
                    allow_unknown=False,
                )
                state = str(normalized["delivery_state"])
                if state == "RETRYABLE" and self._attempt(row) >= _MAX_PROGRESS_DELIVERY_ATTEMPTS:
                    normalized = self._local_transport_receipt(
                        delivery_id=delivery_id,
                        body_digest=str(row["body_digest"]),
                        state="FAILED",
                        failure_code="PROGRESS_DELIVERY_ATTEMPT_LIMIT",
                    )
                    state = "FAILED"
                failure_code = normalized["failure_code"]
                receipt_json = canonical_json(normalized)
                receipt_digest = canonical_digest(normalized)
                next_attempt_at = (
                    (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
                    if state == "RETRYABLE"
                    else None
                )
                delivered_at = now if state == "DELIVERED" else None
                self._connection.execute(
                    """UPDATE multimodal_progress_deliveries
                    SET state=?,failure_code=?,next_attempt_at=?,claim_token_digest=NULL,
                        transport_receipt_json=?,transport_receipt_digest=?,delivered_at=?,updated_at=?
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                    (
                        state, failure_code, next_attempt_at, receipt_json,
                        receipt_digest, delivered_at, now, tenant_id, project_id,
                        actor_id, delivery_id,
                    ),
                )
                reconciled = self._connection.execute(
                    """SELECT * FROM multimodal_progress_deliveries
                    WHERE tenant_id=? AND project_id=? AND actor_id=? AND delivery_id=?""",
                    (tenant_id, project_id, actor_id, delivery_id),
                ).fetchone()
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self._public(reconciled)

    def claim_and_deliver(
        self,
        ctx: RuntimeContext,
        *,
        delivery_id: str,
        claim_token: str,
        capability: object,
    ) -> dict[str, Any]:
        """Claim, invoke only a host-injected transport, then reconcile the claim."""

        if self._transport is None:
            raise ValidationError("PROGRESS_WEBHOOK_TRANSPORT_NOT_CONFIGURED")
        if self._signer is None:
            raise ValidationError("PROGRESS_WEBHOOK_SIGNER_NOT_CONFIGURED")
        claimed = self.claim(
            ctx,
            delivery_id=delivery_id,
            claim_token=claim_token,
            capability=capability,
        )
        body = str(claimed["body_json"]).encode("utf-8")
        try:
            signed_headers = {
                key.lower(): value
                for key, value in self._signer.sign(delivery_id, body).items()
            }
        except Exception:
            return self.complete(
                ctx,
                delivery_id=delivery_id,
                claim_token=claim_token,
                capability=capability,
                transport_receipt=self._local_transport_receipt(
                    delivery_id=delivery_id,
                    body_digest=str(claimed["body_digest"]),
                    state="RETRYABLE",
                    failure_code="PROGRESS_WEBHOOK_SIGNING_FAILED",
                ),
            )
        if (
            set(signed_headers)
            != {
                "x-elmos-delivery-id",
                "x-elmos-key-id",
                "x-elmos-timestamp",
                "x-elmos-signature",
            }
            or signed_headers["x-elmos-delivery-id"] != delivery_id
        ):
            return self.complete(
                ctx,
                delivery_id=delivery_id,
                claim_token=claim_token,
                capability=capability,
                transport_receipt=self._local_transport_receipt(
                    delivery_id=delivery_id,
                    body_digest=str(claimed["body_digest"]),
                    state="FAILED",
                    failure_code="PROGRESS_WEBHOOK_SIGNATURE_HEADERS_INVALID",
                ),
            )
        delivery_headers = {
            "content-type": "application/json",
            "x-elmos-body-sha256": claimed["body_digest"],
            "x-elmos-delivery-id": claimed["delivery_id"],
            "x-elmos-delivery-attempt": str(claimed["attempt"]),
            "x-elmos-key-id": signed_headers["x-elmos-key-id"],
            "x-elmos-timestamp": signed_headers["x-elmos-timestamp"],
            "x-elmos-signature": signed_headers["x-elmos-signature"],
        }
        outcome_unknown = False
        try:
            receipt = self._transport.deliver(
                endpoint_ref=claimed["endpoint_ref"],
                headers=delivery_headers,
                body=body,
            )
        except Exception:
            # The remote endpoint may have accepted the request before the
            # local exception.  Blind retry could duplicate a webhook, so the
            # only safe automatic state is UNKNOWN pending provider-side
            # reconciliation with the delivery ID.
            receipt = self._local_transport_receipt(
                delivery_id=delivery_id,
                body_digest=str(claimed["body_digest"]),
                state="UNKNOWN",
                failure_code="PROGRESS_TRANSPORT_OUTCOME_UNKNOWN",
            )
            outcome_unknown = True
        try:
            normalized_receipt = self._validated_transport_receipt(
                receipt,
                delivery_id=delivery_id,
                body_digest=str(claimed["body_digest"]),
                allow_unknown=outcome_unknown,
            )
        except ValidationError:
            normalized_receipt = self._local_transport_receipt(
                delivery_id=delivery_id,
                body_digest=str(claimed["body_digest"]),
                # The transport call returned, but an invalid receipt cannot
                # prove whether the remote endpoint accepted the body.  Keep
                # the outcome reconcilable and never infer non-delivery.
                state="UNKNOWN",
                failure_code="PROGRESS_TRANSPORT_RECEIPT_INVALID",
            )
        result = self.complete(
            ctx,
            delivery_id=delivery_id,
            claim_token=claim_token,
            capability=capability,
            transport_receipt=normalized_receipt,
        )
        return result

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        if row is None or row["state"] not in _DELIVERY_STATES:
            raise IntegrityError("PROGRESS_DELIVERY_RECORD_CORRUPT")
        ProgressDeliveryStore._attempt(row)
        body_json = row["body_json"]
        try:
            body = json.loads(body_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise IntegrityError("PROGRESS_DELIVERY_BODY_CORRUPT") from error
        if (
            not isinstance(body_json, str)
            or not isinstance(body, dict)
            or canonical_json(body) != body_json
            or not isinstance(row["body_digest"], str)
            or not hmac.compare_digest(canonical_digest(body), row["body_digest"])
            or body.get("tenant_id") != row["tenant_id"]
            or body.get("project_id") != row["project_id"]
            or body.get("event_type") != row["event_type"]
        ):
            raise IntegrityError("PROGRESS_DELIVERY_BODY_CORRUPT")
        expected_delivery_id = "delivery-" + canonical_digest(
            [row["tenant_id"], row["project_id"], row["actor_id"], row["idempotency_key"]]
        )[:40]
        expected_request_digest = canonical_digest(
            {
                "schema_version": "1.0.0",
                "tenant_id": row["tenant_id"],
                "project_id": row["project_id"],
                "actor_id": row["actor_id"],
                "idempotency_key": row["idempotency_key"],
                "endpoint_ref": row["endpoint_ref"],
                "event_type": row["event_type"],
                "body_digest": row["body_digest"],
            }
        )
        if (
            not str(row["idempotency_key"]).startswith("legacy-")
            and row["delivery_id"] != expected_delivery_id
            or not isinstance(row["request_digest"], str)
            or not hmac.compare_digest(row["request_digest"], expected_request_digest)
        ):
            raise IntegrityError("PROGRESS_DELIVERY_IDENTITY_CORRUPT")
        unsigned_event = dict(body)
        event_digest = unsigned_event.pop("event_digest", None)
        payload = body.get("payload")
        if (
            not isinstance(event_digest, str)
            or not hmac.compare_digest(canonical_digest(unsigned_event), event_digest)
            or not isinstance(payload, dict)
            or not isinstance(body.get("payload_digest"), str)
            or not hmac.compare_digest(
                canonical_digest(payload), str(body["payload_digest"])
            )
        ):
            raise IntegrityError("PROGRESS_DELIVERY_BODY_CORRUPT")
        receipt_json = row["transport_receipt_json"]
        receipt_digest = row["transport_receipt_digest"]
        receipt: dict[str, Any] | None = None
        if receipt_json is not None or receipt_digest is not None:
            if not isinstance(receipt_json, str) or not isinstance(receipt_digest, str):
                raise IntegrityError("PROGRESS_DELIVERY_RECEIPT_CORRUPT")
            try:
                decoded = json.loads(receipt_json)
            except (TypeError, json.JSONDecodeError) as error:
                raise IntegrityError("PROGRESS_DELIVERY_RECEIPT_CORRUPT") from error
            if (
                not isinstance(decoded, dict)
                or not hmac.compare_digest(canonical_digest(decoded), receipt_digest)
            ):
                raise IntegrityError("PROGRESS_DELIVERY_RECEIPT_CORRUPT")
            try:
                ProgressDeliveryStore._validated_transport_receipt(
                    decoded,
                    delivery_id=str(row["delivery_id"]),
                    body_digest=str(row["body_digest"]),
                    allow_unknown=True,
                )
            except ValidationError as error:
                raise IntegrityError("PROGRESS_DELIVERY_RECEIPT_CORRUPT") from error
            receipt = decoded
        legacy = str(row["idempotency_key"]).startswith("legacy-")
        if (
            receipt is None
            and row["state"] in {"DELIVERED", "RETRYABLE", "FAILED", "UNKNOWN"}
            and not legacy
            or receipt is not None
            and (
                receipt.get("delivery_state") != row["state"]
                or receipt.get("failure_code") != row["failure_code"]
            )
        ):
            raise IntegrityError("PROGRESS_DELIVERY_RECEIPT_STATE_MISMATCH")
        result = {
            key: row[key]
            for key in (
                "delivery_id", "endpoint_ref", "event_type", "body_digest", "state",
                "attempt", "failure_code", "next_attempt_at", "delivered_at",
                "created_at", "updated_at",
            )
        }
        result["transport_receipt"] = receipt
        result["transport_receipt_digest"] = receipt_digest
        return result


class SurfaceSkillBridge:
    """Content-addressed Skill 25/26 implementation and deterministic previewer."""

    _UI_OPERATIONS = ("describe", "capabilities", "health", "build_preview")
    _API_OPERATIONS = (
        "describe", "capabilities", "health", "build_contract",
    )
    _UI_FILES = {
        "apps/web-console/app/intake/page.tsx": (b"MultimodalIntakeWorkbench",),
        "apps/web-console/app/intake/MultimodalIntakeWorkbench.tsx": (b"useMicrophoneRecorder", b"get_session"),
        "apps/web-console/app/intake/MultimodalIntakeWorkbench.module.css": (b"inlineControl",),
        "apps/web-console/app/intake/useMicrophoneRecorder.ts": (b"getUserMedia", b"encodeWaveFile"),
        "apps/web-console/app/api/multimodal-intake/v1/execute/route.ts": (b"executeMultimodalSkill",),
        "apps/web-console/app/api/multimodal-intake/v1/progress/jobs/[jobId]/route.ts": (
            b"readMultimodalProgressBatch", b"Last-Event-ID",
        ),
        "apps/web-console/app/lib/server/multimodalIntakeRunner.ts": (
            b"validateEngineEnvelope", b"readMultimodalProgressBatch",
        ),
        "apps/web-console/lib/multimodal-intake/strictJson.ts": (b"parseStrictJson", b"canonicalStrictJson"),
    }
    _API_FILES = {
        "engines/multimodal-intake-engine/openapi/multimodal-intake-v1.openapi.yaml": (b"openapi: 3.1.0",),
        "contracts/multimodal-intake/asyncapi-v1.yaml": (b"asyncapi: 3.0.0",),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/api.py": (b"MultimodalIntakeApi",),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/contracts.py": (b"EXECUTION_CONTRACT_VERSION",),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/operation_registry.py": (
            b"OPERATION_REGISTRY_SCHEMA_VERSION", b"REQUIRES_ADAPTER",
        ),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/http_server.py": (
            b"EXECUTE_PATH", b"PROGRESS_TASK_EVENTS_PREFIX", b"PROGRESS_TASK_WEBSOCKET_PREFIX",
        ),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/progress_stream.py": (
            b"ProgressStreamReader", b"parse_progress_cursor",
        ),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/sdk.py": (b"MultimodalIntakeClient",),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/surface_bridge.py": (b"ProgressDeliveryStore",),
        "sdk/multimodal-intake/typescript/client.ts": (b"MultimodalIntakeClient",),
        "sdk/multimodal-intake/java/src/main/java/dev/elmos/intake/MultimodalIntakeClient.java": (b"class MultimodalIntakeClient",),
        "engines/multimodal-intake-engine/src/elmos_multimodal_intake/webhooks.py": (b"WebhookSigner", b"WebhookVerifier"),
    }

    def __init__(
        self,
        repository_root: str | Path | None = None,
    ) -> None:
        self._repository_root = Path(repository_root) if repository_root else Path(__file__).resolve().parents[4]

    @staticmethod
    def _envelope(state: str, code: str, outputs: Mapping[str, Any], metrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {"state": state, "code": code, "outputs": dict(outputs), "metrics": dict(metrics or {}), "retryable": False}

    def _read(self, relative: str) -> bytes:
        path = self._repository_root / relative
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= 4 * 1024 * 1024:
                raise ValueError("surface artifact is not a bounded regular file")
            chunks: list[bytes] = []
            observed = 0
            while observed < metadata.st_size:
                chunk = os.read(descriptor, min(64 * 1024, metadata.st_size - observed))
                if not chunk:
                    break
                chunks.append(chunk)
                observed += len(chunk)
            if observed != metadata.st_size:
                raise ValueError("surface artifact changed during read")
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    def _bundle(self, files: Mapping[str, tuple[bytes, ...]]) -> dict[str, Any]:
        records = []
        for relative, markers in sorted(files.items()):
            data = self._read(relative)
            if any(marker not in data for marker in markers):
                raise ValueError("surface marker missing")
            records.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        unsigned = {"schema_version": "1.0.0", "files": records}
        return {**unsigned, "bundle_digest": canonical_digest(unsigned)}

    @staticmethod
    def _catalog() -> dict[str, Any]:
        catalog = [
            {
                "ordinal": binding.ordinal, "skill": binding.skill,
                "handler_id": binding.handler_id, "phase": binding.phase,
            }
            for binding in sorted(SKILL_REGISTRY.values(), key=lambda item: item.ordinal)
        ]
        if (
            len(catalog) != 50
            or [item["ordinal"] for item in catalog] != list(range(1, 51))
            or catalog[24]["skill"] != UI_SKILL
            or catalog[25]["skill"] != API_SKILL
        ):
            raise ValueError("multimodal skill catalog integrity failed")
        unsigned = {"skill_count": len(catalog), "skills": catalog}
        return {**unsigned, "catalog_digest": canonical_digest(unsigned)}

    @staticmethod
    def _preview(payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_entries = payload.get("entries")
        if (
            not isinstance(raw_entries, Sequence)
            or isinstance(raw_entries, (str, bytes))
            or not 1 <= len(raw_entries) <= 10_000
        ):
            raise ValidationError("PREVIEW_ENTRIES_INVALID")
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        portable_seen: set[str] = set()
        for index, raw in enumerate(raw_entries):
            if not isinstance(raw, Mapping):
                raise ValidationError("PREVIEW_ENTRY_INVALID", details={"index": index})
            if set(raw) - {"path", "byte_count", "content_digest", "asset_id", "state", "role", "model_read_allowed"}:
                raise ValidationError("PREVIEW_ENTRY_FIELDS_INVALID", details={"index": index})
            try:
                path = normalize_relative_path(raw.get("path"))
            except (ProjectContractError, TypeError, UnicodeError):
                raise ValidationError("PREVIEW_ENTRY_PATH_INVALID", details={"index": index}) from None
            portable_path = "/".join(
                unicodedata.normalize("NFKC", part).casefold()
                for part in PurePosixPath(path).parts
            )
            if path in seen or portable_path in portable_seen:
                raise ValidationError("PREVIEW_ENTRY_PATH_COLLISION", details={"index": index})
            size = raw.get("byte_count")
            if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= 4 * 1024 * 1024 * 1024:
                raise ValidationError("PREVIEW_ENTRY_SIZE_INVALID", details={"index": index})
            digest = raw.get("content_digest")
            if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
                raise ValidationError("PREVIEW_ENTRY_DIGEST_REQUIRED", details={"index": index})
            role = raw.get("role")
            allowed = raw.get("model_read_allowed")
            if role not in {"PRIMARY", "REFERENCE", "IGNORE"} or not isinstance(allowed, bool) or role == "IGNORE" and allowed:
                raise ValidationError("PREVIEW_ENTRY_ACCESS_INVALID", details={"index": index})
            asset_id = raw.get("asset_id")
            if asset_id is not None and (
                not isinstance(asset_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", asset_id)
            ):
                raise ValidationError("PREVIEW_ENTRY_ASSET_ID_INVALID", details={"index": index})
            state = raw.get("state", "SELECTED")
            if not isinstance(state, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", state):
                raise ValidationError("PREVIEW_ENTRY_STATE_INVALID", details={"index": index})
            seen.add(path)
            portable_seen.add(portable_path)
            entries.append({
                "path": path, "byte_count": size,
                "content_digest": "sha256:" + digest.removeprefix("sha256:"),
                "asset_id": asset_id, "state": state,
                "role": role, "model_read_allowed": allowed,
            })
        entries.sort(key=lambda item: item["path"].encode("utf-8"))
        unsigned = {
            "schema_version": "1.0.0", "entry_count": len(entries),
            "total_bytes": sum(item["byte_count"] for item in entries), "entries": entries,
            "external_evidence": "NOT_RUN", "certification": "NOT_CERTIFIED",
        }
        return {**unsigned, "preview_digest": canonical_digest(unsigned)}

    def handle(self, skill_name: str, ctx: RuntimeContext, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if skill_name not in {UI_SKILL, API_SKILL}:
            return self._envelope("BLOCKED", "SURFACE_SKILL_UNKNOWN", {})
        raw_operation = payload.get("operation", "describe")
        operation = raw_operation if isinstance(raw_operation, str) else "INVALID"
        allowed = self._UI_OPERATIONS if skill_name == UI_SKILL else self._API_OPERATIONS
        if operation not in allowed:
            return self._envelope("BLOCKED", "SURFACE_OPERATION_UNSUPPORTED", {"operation": operation, "allowed_operations": list(allowed)})
        base_fields = {"operation", "idempotency_key", "trace_id"}
        expected_fields = base_fields | {"entries"} if operation == "build_preview" else base_fields
        unexpected = sorted(set(payload) - expected_fields)
        if unexpected:
            raise ValidationError("SURFACE_INPUT_FIELDS_INVALID", details={"unexpected": unexpected})
        try:
            if skill_name == UI_SKILL:
                bundle = self._bundle(self._UI_FILES)
                if operation == "build_preview":
                    preview = self._preview(payload)
                    return self._envelope("SUCCEEDED", "DETERMINISTIC_PACKAGE_PREVIEW_BUILT", {"preview": preview})
                capabilities = {
                    "drag_drop_files": True, "directory_selection": True, "microphone_recording": True,
                    "explicit_asset_role_and_model_read_permission": True, "recoverable_upload_metadata": True,
                    "safe_progress_polling": True, "sse_or_websocket_sync": True,
                }
                outputs = {
                    "surface_kind": "CHECKED_IN_NEXTJS_WORKBENCH", "page_route": "/intake",
                    "capabilities": capabilities, "file_bundle": bundle, "skill_catalog": self._catalog(),
                    "external_evidence": "NOT_RUN", "certification": "NOT_CERTIFIED",
                }
                return self._envelope("SUCCEEDED", f"LOCAL_UI_SURFACE_{operation.upper()}", outputs)
            bundle = self._bundle(self._API_FILES)
            contract = {
                "schema_version": "1.0.0", "contract_kind": "CONTENT_ADDRESSED_HTTP_ASYNCAPI_AND_SDK_BUNDLE",
                "sdk_languages": ["java", "python", "typescript"],
                "progress_transports": [
                    "safe-polling", "authenticated-sse",
                    "authenticated-read-only-websocket", "signed-webhook",
                ],
                "external_delivery_default": "DISABLED", "file_bundle": bundle, "skill_catalog": self._catalog(),
                "external_evidence": "NOT_RUN", "certification": "NOT_CERTIFIED",
            }
            contract["contract_digest"] = canonical_digest(contract)
            return self._envelope("SUCCEEDED", f"LOCAL_API_SDK_SURFACE_{operation.upper()}", {"contract_bundle": contract})
        except (OSError, ValueError):
            return self._envelope("FAILED", "LOCAL_SURFACE_INTEGRITY_FAILED", {"skill": skill_name})


__all__ = ["ProgressDeliveryStore", "ProgressWebhookTransport", "SurfaceSkillBridge"]
