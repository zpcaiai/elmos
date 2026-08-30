from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_json, digest_value, validate_digest, validate_identifier
from .contracts import (
    ProofResult,
    ProofRunState,
    Scope,
    TERMINAL_RUN_STATES,
    TrustedIdentity,
    utc_now,
)
from .gate import validate_result


class StoreError(RuntimeError):
    pass


_ALLOWED_TRANSITIONS = {
    ProofRunState.QUEUED: {ProofRunState.LEASED, ProofRunState.CANCELLED},
    ProofRunState.LEASED: {
        ProofRunState.RUNNING,
        ProofRunState.QUEUED,
        ProofRunState.CANCEL_REQUESTED,
    },
    ProofRunState.RUNNING: {
        ProofRunState.PAUSED,
        ProofRunState.CANCEL_REQUESTED,
        ProofRunState.SUCCEEDED,
        ProofRunState.FAILED,
        ProofRunState.TIMED_OUT,
    },
    ProofRunState.PAUSED: {ProofRunState.LEASED, ProofRunState.CANCELLED},
    ProofRunState.CANCEL_REQUESTED: {ProofRunState.CANCELLED, ProofRunState.FAILED},
    ProofRunState.SUCCEEDED: set(),
    ProofRunState.FAILED: set(),
    ProofRunState.CANCELLED: set(),
    ProofRunState.TIMED_OUT: set(),
}


class StateStore:
    """Tenant-scoped durable local state used by the trusted service boundary.

    PostgreSQL 17 migrations in the imported package are the production
    persistence contract. SQLite is deliberately limited to local execution,
    tests and offline replay; it preserves the same fail-closed invariants.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            state_path = Path(path).expanduser()
            if state_path.is_symlink():
                raise StoreError("state database path must not be a symlink")
            state_path.parent.mkdir(parents=True, exist_ok=True)
            path = state_path
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
              tenant_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              response_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS events (
              tenant_id TEXT NOT NULL,
              aggregate_type TEXT NOT NULL,
              aggregate_id TEXT NOT NULL,
              sequence INTEGER NOT NULL,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              previous_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, aggregate_type, aggregate_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS proof_runs (
              tenant_id TEXT NOT NULL,
              run_id TEXT NOT NULL,
              account_id TEXT NOT NULL,
              project_id TEXT,
              source_artifact_digest TEXT,
              target_artifact_digest TEXT,
              environment_digest TEXT,
              workload_key TEXT,
              data_classification TEXT,
              obligation_id TEXT NOT NULL,
              engine TEXT NOT NULL DEFAULT 'local',
              engine_version TEXT NOT NULL DEFAULT '1.0.0',
              formula_hash TEXT,
              mode TEXT NOT NULL DEFAULT 'BOUNDED',
              bound_json TEXT,
              options_json TEXT NOT NULL DEFAULT '{}',
              state TEXT NOT NULL,
              owner_id TEXT,
              fencing_token INTEGER NOT NULL,
              lease_expires_at TEXT,
              trace_id TEXT,
              checkpoint_json TEXT,
              retry_parent_run_id TEXT,
              retry_root_run_id TEXT,
              retry_attempt INTEGER NOT NULL DEFAULT 0,
              retry_maximum_attempts INTEGER,
              started_at TEXT,
              completed_at TEXT,
              wall_clock_ms INTEGER,
              result_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, run_id)
            );
            CREATE TABLE IF NOT EXISTS run_operation_idempotency (
              tenant_id TEXT NOT NULL,
              operation_key TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              operation_type TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              aggregate_run_id TEXT NOT NULL,
              response_digest TEXT NOT NULL,
              response_row_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, operation_key)
            );
            CREATE TABLE IF NOT EXISTS cache_entries (
              tenant_id TEXT NOT NULL,
              cache_key TEXT NOT NULL,
              result_json TEXT NOT NULL,
              stale INTEGER NOT NULL DEFAULT 0,
              expires_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, cache_key)
            );
            CREATE TABLE IF NOT EXISTS invocations (
              tenant_id TEXT NOT NULL,
              invocation_id TEXT NOT NULL,
              skill_id TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              outcome_digest TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, invocation_id)
            );
            CREATE TABLE IF NOT EXISTS assurance_documents (
              tenant_id TEXT NOT NULL,
              document_type TEXT NOT NULL,
              document_id TEXT NOT NULL,
              document_version TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              content_digest TEXT NOT NULL,
              content_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, document_type, document_id, document_version)
            );
            CREATE TABLE IF NOT EXISTS execution_permits (
              tenant_id TEXT NOT NULL,
              permit_id TEXT NOT NULL,
              nonce TEXT NOT NULL,
              execution_digest TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              expires_at_epoch INTEGER NOT NULL,
              consumed_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, permit_id),
              UNIQUE (tenant_id, nonce)
            );
            CREATE TABLE IF NOT EXISTS execution_receipts (
              tenant_id TEXT NOT NULL,
              execution_id TEXT NOT NULL,
              execution_digest TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              receipt_digest TEXT NOT NULL,
              receipt_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, execution_id)
            );
            CREATE TABLE IF NOT EXISTS telemetry_events (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              tenant_id TEXT NOT NULL,
              account_id TEXT NOT NULL,
              project_id TEXT,
              scope_digest TEXT NOT NULL,
              metric_name TEXT NOT NULL,
              metric_value_micros INTEGER NOT NULL,
              labels_json TEXT NOT NULL,
              trace_id TEXT NOT NULL,
              observed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS telemetry_scope_time
              ON telemetry_events(tenant_id, scope_digest, observed_at);
            CREATE TABLE IF NOT EXISTS proof_dependencies (
              tenant_id TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              subject_type TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              dependency_kind TEXT NOT NULL,
              dependency_id TEXT NOT NULL,
              dependency_hash TEXT NOT NULL,
              stale INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              PRIMARY KEY (
                tenant_id,
                scope_digest,
                subject_type,
                subject_id,
                dependency_kind,
                dependency_id,
                dependency_hash
              )
            );
            CREATE INDEX IF NOT EXISTS proof_dependencies_lookup
              ON proof_dependencies(
                tenant_id, scope_digest, dependency_kind, dependency_id, stale
              );
            CREATE TABLE IF NOT EXISTS reproof_queue (
              tenant_id TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              subject_type TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              dependency_kind TEXT NOT NULL,
              dependency_id TEXT NOT NULL,
              old_hash TEXT NOT NULL,
              new_hash TEXT NOT NULL,
              state TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (
                tenant_id,
                scope_digest,
                subject_type,
                subject_id,
                dependency_kind,
                dependency_id,
                new_hash
              )
            );
            CREATE TABLE IF NOT EXISTS security_audit_events (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              tenant_id TEXT NOT NULL,
              actor_id TEXT NOT NULL,
              project_id TEXT,
              action TEXT NOT NULL,
              decision TEXT NOT NULL,
              reason TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS security_audit_tenant_time
              ON security_audit_events(tenant_id, created_at);
            CREATE TABLE IF NOT EXISTS event_outbox (
              event_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              scope_digest TEXT NOT NULL,
              topic TEXT NOT NULL,
              aggregate_type TEXT NOT NULL,
              aggregate_id TEXT NOT NULL,
              sequence INTEGER NOT NULL,
              event_json TEXT NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              available_at TEXT NOT NULL,
              published_at TEXT,
              delivery_receipt TEXT,
              last_error TEXT,
              created_at TEXT NOT NULL,
              UNIQUE (tenant_id, aggregate_type, aggregate_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS event_outbox_pending
              ON event_outbox(tenant_id, scope_digest, state, available_at, created_at);
            """
        )
        self._ensure_legacy_columns()
        self._ensure_support_columns()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _ensure_legacy_columns(self) -> None:
        """Upgrade a database created by the initial local engine safely."""
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(proof_runs)")
        }
        additions = {
            "project_id": "TEXT",
            "source_artifact_digest": "TEXT",
            "target_artifact_digest": "TEXT",
            "environment_digest": "TEXT",
            "workload_key": "TEXT",
            "data_classification": "TEXT",
            "engine": "TEXT NOT NULL DEFAULT 'local'",
            "engine_version": "TEXT NOT NULL DEFAULT '1.0.0'",
            "formula_hash": "TEXT",
            "mode": "TEXT NOT NULL DEFAULT 'BOUNDED'",
            "bound_json": "TEXT",
            "options_json": "TEXT NOT NULL DEFAULT '{}'",
            "trace_id": "TEXT",
            "checkpoint_json": "TEXT",
            "retry_parent_run_id": "TEXT",
            "retry_root_run_id": "TEXT",
            "retry_attempt": "INTEGER NOT NULL DEFAULT 0",
            "retry_maximum_attempts": "INTEGER",
            "started_at": "TEXT",
            "completed_at": "TEXT",
            "wall_clock_ms": "INTEGER",
        }
        with self._lock, self._connection:
            for name, definition in additions.items():
                if name not in columns:
                    self._connection.execute(
                        f"ALTER TABLE proof_runs ADD COLUMN {name} {definition}"
                    )
            self._connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS proof_runs_one_child_per_parent "
                "ON proof_runs(tenant_id, retry_parent_run_id) "
                "WHERE retry_parent_run_id IS NOT NULL"
            )
            self._connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS proof_runs_one_attempt_per_root "
                "ON proof_runs(tenant_id, retry_root_run_id, retry_attempt) "
                "WHERE retry_root_run_id IS NOT NULL"
            )

    def _ensure_support_columns(self) -> None:
        """Upgrade repository-owned support tables without touching source SQL."""
        outbox_columns = {
            row[1]
            for row in self._connection.execute("PRAGMA table_info(event_outbox)")
        }
        with self._lock, self._connection:
            if "delivery_receipt" not in outbox_columns:
                self._connection.execute(
                    "ALTER TABLE event_outbox ADD COLUMN delivery_receipt TEXT"
                )

    def consume_execution_permit(
        self,
        scope: Scope,
        permit_id: str,
        nonce: str,
        execution_digest: str,
        expires_at_epoch: int,
    ) -> None:
        """Atomically consume a one-use native execution authorization."""
        validate_identifier(permit_id, "permitId")
        validate_identifier(nonce, "permitNonce")
        if not isinstance(execution_digest, str) or not execution_digest.startswith(
            "sha256:"
        ):
            raise StoreError("execution digest is invalid")
        if not isinstance(expires_at_epoch, int) or isinstance(expires_at_epoch, bool):
            raise StoreError("execution permit expiry must be an integer")
        if expires_at_epoch < int(time.time()):
            raise StoreError("execution permit expired before it could be consumed")
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    "INSERT INTO execution_permits VALUES(?,?,?,?,?,?,?)",
                    (
                        scope.tenant_id,
                        permit_id,
                        nonce,
                        execution_digest,
                        digest_value(scope.to_dict()),
                        expires_at_epoch,
                        utc_now(),
                    ),
                )
                self._append_event_locked(
                    scope,
                    "execution_permit",
                    permit_id,
                    "consumed",
                    {
                        "nonceDigest": digest_value(nonce),
                        "executionDigest": execution_digest,
                        "expiresAtEpoch": expires_at_epoch,
                    },
                )
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                "execution permit or nonce has already been consumed"
            ) from exc

    def put_execution_receipt(
        self,
        scope: Scope,
        execution_id: str,
        execution_digest: str,
        receipt: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist an immutable digest-bound native execution receipt."""
        validate_identifier(execution_id, "executionId")
        if not isinstance(receipt, dict):
            raise StoreError("execution receipt must be an object")
        scope_digest = digest_value(scope.to_dict())
        receipt_digest = digest_value(receipt)
        receipt_json = canonical_json(receipt).decode("utf-8")
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT execution_digest,scope_digest,receipt_digest,receipt_json,created_at FROM execution_receipts WHERE tenant_id=? AND execution_id=?",
                (scope.tenant_id, execution_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["execution_digest"] != execution_digest
                    or existing["scope_digest"] != scope_digest
                    or existing["receipt_digest"] != receipt_digest
                    or existing["receipt_json"] != receipt_json
                ):
                    raise StoreError("immutable execution receipt conflict")
                created_at = existing["created_at"]
            else:
                created_at = utc_now()
                self._connection.execute(
                    "INSERT INTO execution_receipts VALUES(?,?,?,?,?,?,?)",
                    (
                        scope.tenant_id,
                        execution_id,
                        execution_digest,
                        scope_digest,
                        receipt_digest,
                        receipt_json,
                        created_at,
                    ),
                )
                self._append_event_locked(
                    scope,
                    "native_execution",
                    execution_id,
                    "receipt_committed",
                    {
                        "executionDigest": execution_digest,
                        "receiptDigest": receipt_digest,
                    },
                )
        return {
            "executionId": execution_id,
            "executionDigest": execution_digest,
            "receiptDigest": receipt_digest,
            "createdAt": created_at,
            "immutable": True,
        }

    def get_execution_receipt(self, scope: Scope, execution_id: str) -> dict[str, Any]:
        validate_identifier(execution_id, "executionId")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM execution_receipts WHERE tenant_id=? AND execution_id=?",
                (scope.tenant_id, execution_id),
            ).fetchone()
        if row is None:
            raise StoreError("unknown execution receipt")
        if row["scope_digest"] != digest_value(scope.to_dict()):
            raise StoreError("execution receipt scope does not match trusted request")
        receipt = json.loads(row["receipt_json"])
        if digest_value(receipt) != row["receipt_digest"]:
            raise StoreError("execution receipt integrity check failed")
        return receipt

    def record_telemetry(
        self,
        scope: Scope,
        metric_name: str,
        metric_value_micros: int,
        labels: dict[str, str],
        trace_id: str,
    ) -> int:
        validate_identifier(metric_name, "metricName")
        validate_identifier(trace_id, "traceId")
        if not isinstance(metric_value_micros, int) or isinstance(
            metric_value_micros, bool
        ):
            raise StoreError("metricValueMicros must be an integer")
        if not isinstance(labels, dict) or len(labels) > 16:
            raise StoreError("telemetry labels must be a bounded object")
        safe_labels: dict[str, str] = {}
        for key, value in labels.items():
            validate_identifier(key, "telemetryLabel")
            if not isinstance(value, str) or len(value) > 128:
                raise StoreError("telemetry label values must be bounded strings")
            if any(
                token in key.lower()
                for token in ("formula", "source", "target", "secret", "token")
            ):
                raise StoreError("sensitive telemetry label is forbidden")
            safe_labels[key] = value
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO telemetry_events(tenant_id,account_id,project_id,scope_digest,metric_name,metric_value_micros,labels_json,trace_id,observed_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    scope.account_id,
                    scope.project_id,
                    digest_value(scope.to_dict()),
                    metric_name,
                    metric_value_micros,
                    canonical_json(safe_labels).decode("utf-8"),
                    trace_id,
                    utc_now(),
                ),
            )
            if cursor.lastrowid is None:
                raise StoreError("telemetry event insert did not return a sequence")
            return cursor.lastrowid

    def telemetry(self, scope: Scope, *, limit: int = 1000) -> list[dict[str, Any]]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 10_000
        ):
            raise StoreError("telemetry limit is outside policy")
        with self._lock:
            rows = self._connection.execute(
                "SELECT metric_name,metric_value_micros,labels_json,trace_id,observed_at FROM telemetry_events WHERE tenant_id=? AND scope_digest=? ORDER BY sequence DESC LIMIT ?",
                (scope.tenant_id, digest_value(scope.to_dict()), limit),
            ).fetchall()
        return [
            {
                "metricName": row["metric_name"],
                "metricValueMicros": row["metric_value_micros"],
                "labels": json.loads(row["labels_json"]),
                "traceId": row["trace_id"],
                "observedAt": row["observed_at"],
            }
            for row in rows
        ]

    def record_security_audit(
        self,
        identity: TrustedIdentity,
        *,
        action: str,
        decision: str,
        reason: str,
        request_metadata: dict[str, Any] | None = None,
    ) -> int:
        """Append a tenant-local authorization audit without target payload data."""
        action = validate_identifier(action, "audit.action")
        if decision not in {"ALLOW", "DENY"}:
            raise StoreError("security audit decision must be ALLOW or DENY")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise StoreError("security audit reason is invalid")
        metadata = request_metadata or {}
        if not isinstance(metadata, dict):
            raise StoreError("security audit request metadata must be an object")
        request_digest = digest_value(metadata)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO security_audit_events(tenant_id,actor_id,project_id,action,decision,reason,request_digest,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    identity.tenant_id,
                    identity.actor_id,
                    identity.project_id,
                    action,
                    decision,
                    " ".join(reason.split()),
                    request_digest,
                    utc_now(),
                ),
            )
            if cursor.lastrowid is None:
                raise StoreError("security audit insert did not return a sequence")
            return int(cursor.lastrowid)

    def security_audit(
        self, identity: TrustedIdentity, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 10_000
        ):
            raise StoreError("security audit limit is outside policy")
        with self._lock:
            rows = self._connection.execute(
                "SELECT sequence,actor_id,project_id,action,decision,reason,request_digest,created_at "
                "FROM security_audit_events WHERE tenant_id=? ORDER BY sequence DESC LIMIT ?",
                (identity.tenant_id, limit),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "tenantId": identity.tenant_id,
                "actorId": row["actor_id"],
                "projectId": row["project_id"],
                "action": row["action"],
                "decision": row["decision"],
                "reason": row["reason"],
                "requestDigest": row["request_digest"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_idempotent(
        self, tenant_id: str, key: str, request_digest: str
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT request_digest, response_json FROM idempotency WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise StoreError("idempotency key was reused with a different request")
        return json.loads(row["response_json"])

    def put_idempotent(
        self, tenant_id: str, key: str, request_digest: str, response: dict[str, Any]
    ) -> None:
        payload = canonical_json(response).decode("utf-8")
        with self._lock, self._connection:
            try:
                self._connection.execute(
                    "INSERT INTO idempotency VALUES (?, ?, ?, ?, ?)",
                    (tenant_id, key, request_digest, payload, utc_now()),
                )
            except sqlite3.IntegrityError:
                existing = self.get_idempotent(tenant_id, key, request_digest)
                if existing != response:
                    raise StoreError("idempotency record conflict")

    def _run_operation_replay_locked(
        self,
        scope: Scope,
        operation_key: str,
        request_digest: str,
        operation_type: str,
        aggregate_run_id: str,
    ) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT request_digest,operation_type,scope_digest,aggregate_run_id,"
            "response_digest,response_row_json FROM run_operation_idempotency "
            "WHERE tenant_id=? AND operation_key=?",
            (scope.tenant_id, operation_key),
        ).fetchone()
        if row is None:
            return None
        if (
            row["request_digest"] != request_digest
            or row["operation_type"] != operation_type
            or row["scope_digest"] != digest_value(scope.to_dict())
            or row["aggregate_run_id"] != aggregate_run_id
        ):
            raise StoreError("run operation idempotency key was reused")
        try:
            response = json.loads(row["response_row_json"])
        except json.JSONDecodeError as exc:
            raise StoreError("run operation idempotency record is corrupt") from exc
        if not isinstance(response, dict) or digest_value(response) != row["response_digest"]:
            raise StoreError("run operation idempotency integrity check failed")
        return response

    def _put_run_operation_locked(
        self,
        scope: Scope,
        operation_key: str,
        request_digest: str,
        operation_type: str,
        aggregate_run_id: str,
        response: dict[str, Any],
    ) -> None:
        response_json = canonical_json(response).decode("utf-8")
        try:
            self._connection.execute(
                "INSERT INTO run_operation_idempotency(tenant_id,operation_key,"
                "request_digest,operation_type,scope_digest,aggregate_run_id,"
                "response_digest,response_row_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    operation_key,
                    request_digest,
                    operation_type,
                    digest_value(scope.to_dict()),
                    aggregate_run_id,
                    digest_value(response),
                    response_json,
                    utc_now(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            replay = self._run_operation_replay_locked(
                scope,
                operation_key,
                request_digest,
                operation_type,
                aggregate_run_id,
            )
            if replay != response:
                raise StoreError("run operation idempotency conflict") from exc

    @staticmethod
    def _validate_run_operation_binding(
        operation_key: str | None, request_digest: str | None
    ) -> bool:
        if (operation_key is None) != (request_digest is None):
            raise StoreError(
                "operation key and request digest must be supplied together"
            )
        if operation_key is None:
            return False
        assert request_digest is not None
        validate_digest(operation_key, "operationKey")
        validate_digest(request_digest, "requestDigest")
        return True

    def record_invocation(
        self,
        scope: Scope,
        invocation_id: str,
        skill_id: str,
        subject_id: str,
        request_digest: str,
        outcome: dict[str, Any],
    ) -> None:
        validate_identifier(invocation_id, "invocationId")
        with self._lock, self._connection:
            try:
                self._connection.execute(
                    "INSERT INTO invocations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        scope.tenant_id,
                        invocation_id,
                        skill_id,
                        subject_id,
                        request_digest,
                        digest_value(outcome),
                        utc_now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise StoreError("invocation records are append-only") from exc

    def put_document(
        self,
        scope: Scope,
        document_type: str,
        document_id: str,
        document: dict[str, Any],
        *,
        version: str = "1",
    ) -> dict[str, Any]:
        """Persist a typed assurance aggregate as immutable canonical JSON."""
        validate_identifier(document_type, "documentType")
        validate_identifier(document_id, "documentId")
        validate_identifier(version, "documentVersion")
        if not isinstance(document, dict):
            raise StoreError("assurance document must be an object")
        scope_digest = digest_value(scope.to_dict())
        content_digest = digest_value(document)
        content_json = canonical_json(document).decode("utf-8")
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT scope_digest,content_digest,content_json,created_at FROM assurance_documents WHERE tenant_id=? AND document_type=? AND document_id=? AND document_version=?",
                (scope.tenant_id, document_type, document_id, version),
            ).fetchone()
            if existing is not None:
                if (
                    existing["scope_digest"] != scope_digest
                    or existing["content_digest"] != content_digest
                    or existing["content_json"] != content_json
                ):
                    raise StoreError("immutable assurance document conflict")
                created_at = existing["created_at"]
            else:
                created_at = utc_now()
                self._connection.execute(
                    "INSERT INTO assurance_documents VALUES(?,?,?,?,?,?,?,?)",
                    (
                        scope.tenant_id,
                        document_type,
                        document_id,
                        version,
                        scope_digest,
                        content_digest,
                        content_json,
                        created_at,
                    ),
                )
                event_payload: dict[str, Any] = {
                    "documentType": document_type,
                    "documentId": document_id,
                    "version": version,
                    "contentDigest": content_digest,
                    "scopeDigest": scope_digest,
                }
                if document_type == "gate_decision":
                    event_payload["gateDecision"] = document
                self._append_event_locked(
                    scope,
                    "assurance_document",
                    f"{document_type}:{document_id}:{version}",
                    "registered",
                    event_payload,
                )
        return {
            "documentType": document_type,
            "documentId": document_id,
            "version": version,
            "contentDigest": content_digest,
            "scopeDigest": scope_digest,
            "createdAt": created_at,
            "immutable": True,
        }

    def get_document(
        self,
        scope: Scope,
        document_type: str,
        document_id: str,
        *,
        version: str | None = None,
    ) -> dict[str, Any]:
        validate_identifier(document_type, "documentType")
        validate_identifier(document_id, "documentId")
        parameters: list[Any] = [scope.tenant_id, document_type, document_id]
        query = "SELECT * FROM assurance_documents WHERE tenant_id=? AND document_type=? AND document_id=?"
        if version is not None:
            validate_identifier(version, "documentVersion")
            query += " AND document_version=?"
            parameters.append(version)
        query += " ORDER BY created_at DESC, document_version DESC LIMIT 1"
        with self._lock:
            row = self._connection.execute(query, tuple(parameters)).fetchone()
        if row is None:
            raise StoreError("unknown assurance document")
        if row["scope_digest"] != digest_value(scope.to_dict()):
            raise StoreError("assurance document scope does not match trusted request")
        document = json.loads(row["content_json"])
        if digest_value(document) != row["content_digest"]:
            raise StoreError("assurance document integrity check failed")
        return {
            "documentType": row["document_type"],
            "documentId": row["document_id"],
            "version": row["document_version"],
            "contentDigest": row["content_digest"],
            "createdAt": row["created_at"],
            "document": document,
        }

    def list_documents(
        self,
        scope: Scope,
        *,
        subject_id: str | None = None,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        """Return integrity-checked documents for one exact trusted scope.

        ``subject_id`` matches the aggregate identifier or an explicit
        ``subjectId``, ``runId`` or ``obligationId`` field in the document.
        It is intentionally evaluated after the full-scope database filter so
        an identifier guess can never broaden a tenant/account/project read.
        """
        if subject_id is not None:
            validate_identifier(subject_id, "subjectId")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 10_000
        ):
            raise StoreError("document list limit is outside policy")
        scope_digest = digest_value(scope.to_dict())
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM assurance_documents WHERE tenant_id=? AND scope_digest=? "
                "ORDER BY created_at,document_type,document_id,document_version LIMIT ?",
                (scope.tenant_id, scope_digest, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            document = json.loads(row["content_json"])
            if digest_value(document) != row["content_digest"]:
                raise StoreError("assurance document integrity check failed")
            if subject_id is not None and not (
                row["document_id"] == subject_id
                or any(
                    document.get(field) == subject_id
                    for field in ("subjectId", "runId", "obligationId")
                )
            ):
                continue
            result.append(
                {
                    "documentType": row["document_type"],
                    "documentId": row["document_id"],
                    "version": row["document_version"],
                    "contentDigest": row["content_digest"],
                    "createdAt": row["created_at"],
                    "document": document,
                }
            )
        return result

    def register_dependency(
        self,
        scope: Scope,
        *,
        subject_type: str,
        subject_id: str,
        dependency_kind: str,
        dependency_id: str,
        dependency_hash: str,
    ) -> dict[str, Any]:
        """Bind proof/cache evidence to one immutable dependency revision."""
        for value, path in (
            (subject_type, "subjectType"),
            (subject_id, "subjectId"),
            (dependency_kind, "dependencyKind"),
            (dependency_id, "dependencyId"),
        ):
            validate_identifier(value, path)
        from .canonical import validate_digest

        dependency_hash = validate_digest(dependency_hash, "dependencyHash")
        scope_digest = digest_value(scope.to_dict())
        created_at = utc_now()
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO proof_dependencies(tenant_id,scope_digest,subject_type,subject_id,dependency_kind,dependency_id,dependency_hash,stale,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,scope_digest,subject_type,subject_id,dependency_kind,dependency_id,dependency_hash) DO NOTHING",
                (
                    scope.tenant_id,
                    scope_digest,
                    subject_type,
                    subject_id,
                    dependency_kind,
                    dependency_id,
                    dependency_hash,
                    0,
                    created_at,
                ),
            )
        return {
            "subjectType": subject_type,
            "subjectId": subject_id,
            "dependencyKind": dependency_kind,
            "dependencyId": dependency_id,
            "dependencyHash": dependency_hash,
            "scopeDigest": scope_digest,
        }

    def mark_dependency_drift(
        self,
        scope: Scope,
        *,
        dependency_kind: str,
        dependency_id: str,
        new_hash: str,
    ) -> dict[str, Any]:
        """Invalidate dependent evidence and enqueue the minimal replay set.

        This operation is transactional: dependency rows, persisted proof
        results, local caches, the replay queue and the drift event either all
        advance together or none do.
        """
        validate_identifier(dependency_kind, "dependencyKind")
        validate_identifier(dependency_id, "dependencyId")
        from .canonical import validate_digest

        new_hash = validate_digest(new_hash, "newHash")
        scope_digest = digest_value(scope.to_dict())
        affected_subjects: list[dict[str, str]] = []
        old_hashes: set[str] = set()
        cache_count = 0
        proof_run_count = 0
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT subject_type,subject_id,dependency_hash FROM proof_dependencies "
                "WHERE tenant_id=? AND scope_digest=? AND dependency_kind=? AND dependency_id=? AND dependency_hash<>? AND stale=0",
                (
                    scope.tenant_id,
                    scope_digest,
                    dependency_kind,
                    dependency_id,
                    new_hash,
                ),
            ).fetchall()
            for row in rows:
                subject_type = str(row["subject_type"])
                subject_id = str(row["subject_id"])
                old_hash = str(row["dependency_hash"])
                old_hashes.add(old_hash)
                self._connection.execute(
                    "UPDATE proof_dependencies SET stale=1 WHERE tenant_id=? AND scope_digest=? AND subject_type=? AND subject_id=? AND dependency_kind=? AND dependency_id=? AND dependency_hash=?",
                    (
                        scope.tenant_id,
                        scope_digest,
                        subject_type,
                        subject_id,
                        dependency_kind,
                        dependency_id,
                        old_hash,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO reproof_queue(tenant_id,scope_digest,subject_type,subject_id,dependency_kind,dependency_id,old_hash,new_hash,state,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,scope_digest,subject_type,subject_id,dependency_kind,dependency_id,new_hash) DO NOTHING",
                    (
                        scope.tenant_id,
                        scope_digest,
                        subject_type,
                        subject_id,
                        dependency_kind,
                        dependency_id,
                        old_hash,
                        new_hash,
                        "QUEUED",
                        utc_now(),
                    ),
                )
                affected_subjects.append(
                    {"subjectType": subject_type, "subjectId": subject_id}
                )
                if subject_type == "proof_run":
                    run = self._connection.execute(
                        "SELECT result_json FROM proof_runs WHERE tenant_id=? AND run_id=?",
                        (scope.tenant_id, subject_id),
                    ).fetchone()
                    if run is not None and run["result_json"]:
                        result = json.loads(run["result_json"])
                        if not result.get("stale", False):
                            result["stale"] = True
                            self._connection.execute(
                                "UPDATE proof_runs SET result_json=?,updated_at=? WHERE tenant_id=? AND run_id=?",
                                (
                                    canonical_json(result).decode("utf-8"),
                                    utc_now(),
                                    scope.tenant_id,
                                    subject_id,
                                ),
                            )
                            proof_run_count += 1

            cache_rows = self._connection.execute(
                "SELECT cache_key,result_json FROM cache_entries WHERE tenant_id=? AND stale=0",
                (scope.tenant_id,),
            ).fetchall()
            for row in cache_rows:
                stored = json.loads(row["result_json"])
                if (
                    not isinstance(stored, dict)
                    or stored.get("scopeDigest") != scope_digest
                    or not isinstance(stored.get("result"), dict)
                ):
                    continue
                result = stored["result"]
                bindings = result.get("dependencyBindings", {})
                identifiers = result.get("dependencies", [])
                bound_hash = (
                    bindings.get(dependency_id) if isinstance(bindings, dict) else None
                )
                if dependency_id in identifiers or (
                    bound_hash is not None and bound_hash != new_hash
                ):
                    self._connection.execute(
                        "UPDATE cache_entries SET stale=1 WHERE tenant_id=? AND cache_key=?",
                        (scope.tenant_id, row["cache_key"]),
                    )
                    cache_count += 1

            sorted_old_hashes = sorted(old_hashes)
            old_hash = (
                sorted_old_hashes[0]
                if len(sorted_old_hashes) == 1
                else digest_value({"oldHashes": sorted_old_hashes})
            )
            event = self._append_event_locked(
                scope,
                "proof_drift",
                dependency_id,
                "dependency_changed",
                {
                    "dependencyKind": dependency_kind,
                    "dependencyId": dependency_id,
                    "oldHash": old_hash,
                    "oldHashes": sorted_old_hashes,
                    "newHash": new_hash,
                    "affectedSubjects": affected_subjects,
                    "cacheEntriesInvalidated": cache_count,
                    "proofResultsMarkedStale": proof_run_count,
                },
            )
        return {
            "dependencyKind": dependency_kind,
            "dependencyId": dependency_id,
            "oldHash": old_hash,
            "oldHashes": sorted_old_hashes,
            "newHash": new_hash,
            "affectedSubjects": affected_subjects,
            "cacheEntriesInvalidated": cache_count,
            "proofResultsMarkedStale": proof_run_count,
            "reproofPlan": affected_subjects,
            "event": event,
        }

    def pending_reproofs(
        self, scope: Scope, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 10_000
        ):
            raise StoreError("reproof queue limit is outside policy")
        with self._lock:
            rows = self._connection.execute(
                "SELECT subject_type,subject_id,dependency_kind,dependency_id,old_hash,new_hash,state,created_at "
                "FROM reproof_queue WHERE tenant_id=? AND scope_digest=? ORDER BY created_at,subject_type,subject_id LIMIT ?",
                (scope.tenant_id, digest_value(scope.to_dict()), limit),
            ).fetchall()
        return [
            {
                "subjectType": row["subject_type"],
                "subjectId": row["subject_id"],
                "dependencyKind": row["dependency_kind"],
                "dependencyId": row["dependency_id"],
                "oldHash": row["old_hash"],
                "newHash": row["new_hash"],
                "state": row["state"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def complete_idempotent_invocation(
        self,
        scope: Scope,
        invocation_id: str,
        skill_id: str,
        subject_id: str,
        request_digest: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist idempotency, invocation and audit event in one transaction."""
        validate_identifier(invocation_id, "invocationId")
        response_json = canonical_json(response).decode("utf-8")
        outcome_digest = digest_value(response)
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT request_digest, response_json FROM idempotency WHERE tenant_id=? AND idempotency_key=?",
                (scope.tenant_id, invocation_id),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest:
                    raise StoreError(
                        "idempotency key was reused with a different request"
                    )
                return json.loads(existing["response_json"])
            self._connection.execute(
                "INSERT INTO idempotency VALUES (?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    invocation_id,
                    request_digest,
                    response_json,
                    utc_now(),
                ),
            )
            self._connection.execute(
                "INSERT INTO invocations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    invocation_id,
                    skill_id,
                    subject_id,
                    request_digest,
                    outcome_digest,
                    utc_now(),
                ),
            )
            self._append_event_locked(
                scope,
                "skill_invocation",
                invocation_id,
                "completed",
                {
                    "skillId": skill_id,
                    "outcomeDigest": outcome_digest,
                    "proofStatus": response["proofStatus"],
                },
            )
        return response

    def _append_event_locked(
        self,
        scope: Scope,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT sequence, event_hash FROM events WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=? ORDER BY sequence DESC LIMIT 1",
            (scope.tenant_id, aggregate_type, aggregate_id),
        ).fetchone()
        sequence = 1 if row is None else int(row["sequence"]) + 1
        previous_hash = "0" * 64 if row is None else row["event_hash"]
        unsigned = {
            "tenantId": scope.tenant_id,
            "aggregateType": aggregate_type,
            "aggregateId": aggregate_id,
            "sequence": sequence,
            "eventType": event_type,
            "payload": payload,
            "previousHash": previous_hash,
        }
        event_hash = digest_value(unsigned)
        event = {**unsigned, "eventHash": event_hash, "createdAt": utc_now()}
        self._connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scope.tenant_id,
                aggregate_type,
                aggregate_id,
                sequence,
                event_type,
                canonical_json(payload).decode("utf-8"),
                previous_hash,
                event_hash,
                event["createdAt"],
            ),
        )
        if aggregate_type == "proof_drift":
            topic = "driftEvents"
        elif aggregate_type == "gate_decision" or (
            aggregate_type == "assurance_document"
            and payload.get("documentType") == "gate_decision"
        ):
            topic = "gateEvents"
        else:
            topic = "proofEvents"
        event_id = digest_value(
            {
                "tenantId": scope.tenant_id,
                "aggregateType": aggregate_type,
                "aggregateId": aggregate_id,
                "sequence": sequence,
                "eventHash": event_hash,
            }
        )
        if topic == "driftEvents":
            message = {
                "dependencyKind": payload.get("dependencyKind"),
                "dependencyId": payload.get("dependencyId"),
                "oldHash": str(payload.get("oldHash", "")).removeprefix("sha256:"),
                "newHash": str(payload.get("newHash", "")).removeprefix("sha256:"),
            }
        elif topic == "gateEvents":
            gate_decision = payload.get("gateDecision")
            if not isinstance(gate_decision, dict):
                raise StoreError("gate event requires an exact gate decision payload")
            message = gate_decision
        else:
            message = {
                "eventId": event_id,
                "eventType": event_type,
                "tenantId": scope.tenant_id,
                "aggregateId": aggregate_id,
                "occurredAt": event["createdAt"],
                "payload": payload,
            }
        outbox_document = {
            "format": "elmos-formal-assurance-event/v1",
            "eventId": event_id,
            "topic": topic,
            "scopeDigest": digest_value(scope.to_dict()),
            "message": message,
            **event,
        }
        self._connection.execute(
            "INSERT INTO event_outbox(event_id,tenant_id,scope_digest,topic,aggregate_type,aggregate_id,sequence,event_json,state,attempts,available_at,published_at,delivery_receipt,last_error,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                scope.tenant_id,
                digest_value(scope.to_dict()),
                topic,
                aggregate_type,
                aggregate_id,
                sequence,
                canonical_json(outbox_document).decode("utf-8"),
                "PENDING",
                0,
                event["createdAt"],
                None,
                None,
                None,
                event["createdAt"],
            ),
        )
        return event

    def append_event(
        self,
        scope: Scope,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            return self._append_event_locked(
                scope, aggregate_type, aggregate_id, event_type, payload
            )

    def events(
        self, scope: Scope, aggregate_type: str, aggregate_id: str
    ) -> list[dict[str, Any]]:
        with self._lock:
            if aggregate_type == "proof_run":
                self._run_row(scope, aggregate_id)
            rows = self._connection.execute(
                "SELECT * FROM events WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=? ORDER BY sequence",
                (scope.tenant_id, aggregate_type, aggregate_id),
            ).fetchall()
        return [
            {
                "tenantId": row["tenant_id"],
                "aggregateType": row["aggregate_type"],
                "aggregateId": row["aggregate_id"],
                "sequence": row["sequence"],
                "eventType": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "previousHash": row["previous_hash"],
                "eventHash": row["event_hash"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def pending_outbox(self, scope: Scope, *, limit: int = 100) -> list[dict[str, Any]]:
        """Read a bounded scope-local batch for at-least-once delivery."""
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise StoreError("outbox batch limit is outside policy")
        with self._lock:
            rows = self._connection.execute(
                "SELECT event_id,topic,event_json,attempts,created_at FROM event_outbox "
                "WHERE tenant_id=? AND scope_digest=? AND state='PENDING' AND available_at<=? "
                "ORDER BY created_at,event_id LIMIT ?",
                (scope.tenant_id, digest_value(scope.to_dict()), utc_now(), limit),
            ).fetchall()
        return [
            {
                "eventId": row["event_id"],
                "topic": row["topic"],
                "event": json.loads(row["event_json"]),
                "attempts": row["attempts"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def mark_outbox_published(
        self, scope: Scope, event_id: str, *, delivery_receipt: str
    ) -> None:
        from .canonical import validate_digest

        validate_digest(event_id, "eventId")
        validate_digest(delivery_receipt, "deliveryReceipt")
        with self._lock, self._connection:
            updated = self._connection.execute(
                "UPDATE event_outbox SET state='PUBLISHED',published_at=?,delivery_receipt=?,last_error=NULL "
                "WHERE event_id=? AND tenant_id=? AND scope_digest=? AND state='PENDING'",
                (
                    utc_now(),
                    delivery_receipt,
                    event_id,
                    scope.tenant_id,
                    digest_value(scope.to_dict()),
                ),
            )
            if updated.rowcount != 1:
                row = self._connection.execute(
                    "SELECT state FROM event_outbox WHERE event_id=? AND tenant_id=? AND scope_digest=?",
                    (event_id, scope.tenant_id, digest_value(scope.to_dict())),
                ).fetchone()
                if row is None:
                    raise StoreError("unknown outbox event")
                if row["state"] != "PUBLISHED":
                    raise StoreError("outbox event is not publishable")

    def mark_outbox_failed(
        self,
        scope: Scope,
        event_id: str,
        *,
        error: str,
        max_attempts: int = 10,
    ) -> dict[str, Any]:
        from .canonical import validate_digest

        validate_digest(event_id, "eventId")
        if not isinstance(error, str) or not error.strip():
            raise StoreError("outbox failure reason is required")
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not 1 <= max_attempts <= 100
        ):
            raise StoreError("outbox max attempts is outside policy")
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT attempts,state FROM event_outbox WHERE event_id=? AND tenant_id=? AND scope_digest=?",
                (event_id, scope.tenant_id, digest_value(scope.to_dict())),
            ).fetchone()
            if row is None:
                raise StoreError("unknown outbox event")
            if row["state"] == "PUBLISHED":
                raise StoreError("published outbox event cannot fail")
            attempts = int(row["attempts"]) + 1
            state = "DEAD" if attempts >= max_attempts else "PENDING"
            self._connection.execute(
                "UPDATE event_outbox SET attempts=?,state=?,available_at=?,last_error=? WHERE event_id=? AND tenant_id=? AND scope_digest=?",
                (
                    attempts,
                    state,
                    utc_now(),
                    " ".join(error.split())[:1000],
                    event_id,
                    scope.tenant_id,
                    digest_value(scope.to_dict()),
                ),
            )
        return {"eventId": event_id, "attempts": attempts, "state": state}

    def submit_run(
        self,
        scope: Scope,
        run_id: str,
        obligation_id: str,
        account_concurrency: int = 3,
        *,
        engine: str = "local",
        engine_version: str = "1.0.0",
        mode: str = "BOUNDED",
        formula_hash: str | None = None,
        bound: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        validate_identifier(run_id, "runId")
        validate_identifier(obligation_id, "obligationId")
        if not isinstance(account_concurrency, int) or isinstance(
            account_concurrency, bool
        ):
            raise StoreError("account concurrency must be an integer")
        if account_concurrency < 1 or account_concurrency > 3:
            raise StoreError("top-level account concurrency must be between 1 and 3")
        if not isinstance(engine, str) or not engine.strip():
            raise StoreError("run engine is required")
        if not isinstance(engine_version, str) or not engine_version.strip():
            raise StoreError("run engine version is required")
        if mode not in {"CERTIFIED", "INDUCTIVE", "SMT", "BOUNDED", "RUNTIME"}:
            raise StoreError("run mode is invalid")
        if formula_hash is not None:
            formula_hash = validate_digest(formula_hash, "formulaHash")
        if bound is not None and not isinstance(bound, dict):
            raise StoreError("run bound must be an object")
        if options is not None and not isinstance(options, dict):
            raise StoreError("run options must be an object")
        reserved_retry_options = {
            "retryOf",
            "retryRoot",
            "retryAttempt",
            "retryMaximumAttempts",
            "priorResultDigest",
        }
        if options is not None and set(options) & reserved_retry_options:
            raise StoreError("run options contain reserved retry lineage fields")
        if bound is not None and len(canonical_json(bound)) > 512 * 1024:
            raise StoreError("run bound exceeds the local size limit")
        if options is not None and len(canonical_json(options)) > 512 * 1024:
            raise StoreError("run options exceed the local size limit")
        if trace_id is not None:
            validate_identifier(trace_id, "traceId")
        with self._lock, self._connection:
            return self._insert_run_locked(
                scope,
                run_id,
                obligation_id,
                account_concurrency,
                engine=engine,
                engine_version=engine_version,
                mode=mode,
                formula_hash=formula_hash,
                bound=bound,
                options=options or {},
                trace_id=trace_id,
            )

    def _insert_run_locked(
        self,
        scope: Scope,
        run_id: str,
        obligation_id: str,
        account_concurrency: int,
        *,
        engine: str,
        engine_version: str,
        mode: str,
        formula_hash: str | None,
        bound: dict[str, Any] | None,
        options: dict[str, Any],
        trace_id: str | None,
        retry_parent_run_id: str | None = None,
        retry_root_run_id: str | None = None,
        retry_attempt: int = 0,
        retry_maximum_attempts: int | None = None,
    ) -> dict[str, Any]:
        existing = self._connection.execute(
            "SELECT 1 FROM proof_runs WHERE tenant_id=? AND run_id=?",
            (scope.tenant_id, run_id),
        ).fetchone()
        if existing is not None:
            raise StoreError("duplicate proof run")
        active = self._connection.execute(
            "SELECT count(*) FROM proof_runs WHERE tenant_id=? AND account_id=? "
            "AND state NOT IN (?, ?, ?, ?)",
            (
                scope.tenant_id,
                scope.account_id,
                *(state.value for state in TERMINAL_RUN_STATES),
            ),
        ).fetchone()[0]
        if active >= account_concurrency:
            raise StoreError("top-level account concurrency limit exceeded")
        duplicate_obligation = self._connection.execute(
            "SELECT 1 FROM proof_runs WHERE tenant_id=? AND obligation_id=? "
            "AND state IN (?, ?) LIMIT 1",
            (
                scope.tenant_id,
                obligation_id,
                ProofRunState.LEASED.value,
                ProofRunState.RUNNING.value,
            ),
        ).fetchone()
        if duplicate_obligation is not None:
            raise StoreError("proof obligation already has an active owner")
        now = utc_now()
        try:
            self._connection.execute(
                "INSERT INTO proof_runs(tenant_id,run_id,account_id,project_id,"
                "source_artifact_digest,target_artifact_digest,environment_digest,"
                "workload_key,data_classification,obligation_id,engine,engine_version,"
                "formula_hash,mode,bound_json,options_json,state,owner_id,fencing_token,"
                "lease_expires_at,trace_id,checkpoint_json,retry_parent_run_id,"
                "retry_root_run_id,retry_attempt,retry_maximum_attempts,started_at,"
                "completed_at,wall_clock_ms,result_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    run_id,
                    scope.account_id,
                    scope.project_id,
                    scope.source_artifact_digest,
                    scope.target_artifact_digest,
                    scope.environment_digest,
                    scope.workload_key,
                    scope.data_classification,
                    obligation_id,
                    engine,
                    engine_version,
                    formula_hash,
                    mode,
                    canonical_json(bound).decode("utf-8")
                    if bound is not None
                    else None,
                    canonical_json(options).decode("utf-8"),
                    ProofRunState.QUEUED.value,
                    None,
                    1,
                    None,
                    trace_id,
                    None,
                    retry_parent_run_id,
                    retry_root_run_id,
                    retry_attempt,
                    retry_maximum_attempts,
                    None,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise StoreError("proof run or retry lineage conflicts with durable state") from exc
        event_payload: dict[str, Any] = {
            "fencingToken": 1,
            "obligationId": obligation_id,
        }
        if retry_parent_run_id is not None:
            event_payload.update(
                {
                    "retryOf": retry_parent_run_id,
                    "retryRoot": retry_root_run_id,
                    "retryAttempt": retry_attempt,
                    "retryMaximumAttempts": retry_maximum_attempts,
                }
            )
        self._append_event_locked(
            scope, "proof_run", run_id, "submitted", event_payload
        )
        return dict(self._run_row(scope, run_id))

    @staticmethod
    def _scope_matches(row: sqlite3.Row, scope: Scope) -> bool:
        expected = {
            "tenant_id": scope.tenant_id,
            "account_id": scope.account_id,
            "project_id": scope.project_id,
            "source_artifact_digest": scope.source_artifact_digest,
            "target_artifact_digest": scope.target_artifact_digest,
            "environment_digest": scope.environment_digest,
            "workload_key": scope.workload_key,
            "data_classification": scope.data_classification,
        }
        return all(row[key] == value for key, value in expected.items())

    def _run_row(self, scope: Scope, run_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM proof_runs WHERE tenant_id=? AND run_id=?",
            (scope.tenant_id, run_id),
        ).fetchone()
        if row is None:
            raise StoreError("unknown proof run")
        if not self._scope_matches(row, scope):
            raise StoreError("proof run scope does not match trusted request")
        return row

    def get_run(self, scope: Scope, run_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._run_row(scope, run_id))

    def lease_run(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        expected_token: int,
        lease_seconds: int = 900,
    ) -> dict[str, Any]:
        if lease_seconds < 1 or lease_seconds > 86_400:
            raise StoreError("lease duration is outside the allowed bound")
        now = datetime.now(timezone.utc)
        expiry = (
            (now + timedelta(seconds=lease_seconds))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        with self._lock, self._connection:
            row = self._run_row(scope, run_id)
            state = ProofRunState(row["state"])
            if state not in {
                ProofRunState.QUEUED,
                ProofRunState.PAUSED,
                ProofRunState.LEASED,
            }:
                raise StoreError("run is not leasable")
            if int(row["fencing_token"]) != expected_token:
                raise StoreError("fencing token mismatch")
            if (
                state == ProofRunState.LEASED
                and row["owner_id"] != worker_id
                and row["lease_expires_at"]
                and row["lease_expires_at"] > utc_now()
            ):
                raise StoreError("active lease belongs to another worker")
            new_token = expected_token + 1
            updated = self._connection.execute(
                "UPDATE proof_runs SET state=?, owner_id=?, fencing_token=?, lease_expires_at=?, updated_at=? WHERE tenant_id=? AND run_id=? AND fencing_token=?",
                (
                    ProofRunState.LEASED.value,
                    worker_id,
                    new_token,
                    expiry,
                    utc_now(),
                    scope.tenant_id,
                    run_id,
                    expected_token,
                ),
            )
            if updated.rowcount != 1:
                raise StoreError("lease was lost to another worker")
            self._append_event_locked(
                scope,
                "proof_run",
                run_id,
                "leased",
                {"ownerId": worker_id, "fencingToken": new_token},
            )
        return self.get_run(scope, run_id)

    def start_run(
        self, scope: Scope, run_id: str, worker_id: str, token: int
    ) -> dict[str, Any]:
        return self._authorized_transition(
            scope, run_id, worker_id, token, ProofRunState.RUNNING
        )

    def transition_run(
        self, scope: Scope, run_id: str, new_state: ProofRunState
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            row = self._run_row(scope, run_id)
            current = ProofRunState(row["state"])
            if new_state not in _ALLOWED_TRANSITIONS[current]:
                raise StoreError(
                    f"invalid transition {current.value}->{new_state.value}"
                )
            self._connection.execute(
                "UPDATE proof_runs SET state=?, updated_at=? WHERE tenant_id=? AND run_id=?",
                (new_state.value, utc_now(), scope.tenant_id, run_id),
            )
            self._append_event_locked(
                scope, "proof_run", run_id, "state_changed", {"state": new_state.value}
            )
        return self.get_run(scope, run_id)

    def control_run(self, scope: Scope, run_id: str, action: str) -> dict[str, Any]:
        """Apply an authenticated control-plane action without worker authority.

        This path never commits evidence.  Resuming an expired paused lease
        requeues the run with a higher fencing token so the old worker cannot
        regain write authority.
        """
        if action not in {"PAUSE", "RESUME", "CANCEL"}:
            raise StoreError("unknown proof run control action")
        with self._lock, self._connection:
            row = self._run_row(scope, run_id)
            current = ProofRunState(row["state"])
            if action == "CANCEL":
                if (
                    current in TERMINAL_RUN_STATES
                    or current == ProofRunState.CANCEL_REQUESTED
                ):
                    return dict(row)
                if current in {ProofRunState.QUEUED, ProofRunState.PAUSED}:
                    target = ProofRunState.CANCELLED
                elif current in {ProofRunState.LEASED, ProofRunState.RUNNING}:
                    target = ProofRunState.CANCEL_REQUESTED
                else:
                    raise StoreError(f"cannot cancel a run in state {current.value}")
                owner_id = row["owner_id"]
                lease_expires_at = row["lease_expires_at"]
                fencing_token = int(row["fencing_token"])
            elif action == "PAUSE":
                if current == ProofRunState.PAUSED:
                    return dict(row)
                if current not in {ProofRunState.LEASED, ProofRunState.RUNNING}:
                    raise StoreError(f"cannot pause a run in state {current.value}")
                target = ProofRunState.PAUSED
                owner_id = row["owner_id"]
                lease_expires_at = row["lease_expires_at"]
                fencing_token = int(row["fencing_token"])
            else:
                if current in {ProofRunState.RUNNING, ProofRunState.LEASED}:
                    return dict(row)
                if current != ProofRunState.PAUSED:
                    raise StoreError(f"cannot resume a run in state {current.value}")
                if (
                    row["owner_id"]
                    and row["lease_expires_at"]
                    and row["lease_expires_at"] > utc_now()
                ):
                    target = ProofRunState.RUNNING
                    owner_id = row["owner_id"]
                    lease_expires_at = row["lease_expires_at"]
                    fencing_token = int(row["fencing_token"])
                else:
                    target = ProofRunState.QUEUED
                    owner_id = None
                    lease_expires_at = None
                    fencing_token = int(row["fencing_token"]) + 1
            updated = self._connection.execute(
                "UPDATE proof_runs SET state=?,owner_id=?,lease_expires_at=?,fencing_token=?,completed_at=CASE WHEN ? IN (?,?) THEN ? ELSE completed_at END,updated_at=? WHERE tenant_id=? AND run_id=? AND state=? AND fencing_token=?",
                (
                    target.value,
                    owner_id,
                    lease_expires_at,
                    fencing_token,
                    target.value,
                    ProofRunState.CANCELLED.value,
                    ProofRunState.FAILED.value,
                    utc_now(),
                    utc_now(),
                    scope.tenant_id,
                    run_id,
                    current.value,
                    row["fencing_token"],
                ),
            )
            if updated.rowcount != 1:
                raise StoreError("control action lost its state or fencing race")
            self._append_event_locked(
                scope,
                "proof_run",
                run_id,
                "control_action",
                {
                    "action": action,
                    "previousState": current.value,
                    "state": target.value,
                    "fencingToken": fencing_token,
                },
            )
        return self.get_run(scope, run_id)

    def checkpoint_run(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        token: int,
        checkpoint: dict[str, Any],
        progress: dict[str, Any],
        *,
        operation_key: str | None = None,
        request_digest: str | None = None,
    ) -> dict[str, Any]:
        """Commit one owner/fence-bound checkpoint and wall-clock progress event."""
        validate_identifier(run_id, "runId")
        validate_identifier(worker_id, "workerId")
        if not isinstance(token, int) or isinstance(token, bool) or token < 1:
            raise StoreError("checkpoint fencing token must be a positive integer")
        if not isinstance(checkpoint, dict):
            raise StoreError("checkpoint must be an object")
        if not isinstance(progress, dict):
            raise StoreError("checkpoint progress must be an object")
        unknown_progress = set(progress) - {
            "completed",
            "total",
            "phase",
            "etaWallClockSeconds",
        }
        if unknown_progress:
            raise StoreError(
                "checkpoint progress contains unknown fields: "
                + ", ".join(sorted(unknown_progress))
            )
        completed = progress.get("completed")
        total = progress.get("total")
        if not isinstance(completed, int) or isinstance(completed, bool):
            raise StoreError("checkpoint progress completed and total must be integers")
        if not isinstance(total, int) or isinstance(total, bool):
            raise StoreError("checkpoint progress completed and total must be integers")
        if total < 1 or completed < 0 or completed > total:
            raise StoreError("checkpoint progress is outside the valid range")
        phase = progress.get("phase")
        if phase is not None:
            validate_identifier(phase, "checkpoint.progress.phase")
        eta = progress.get("etaWallClockSeconds")
        if eta is not None and (
            not isinstance(eta, (int, float))
            or isinstance(eta, bool)
            or eta < 0
            or eta > 31_536_000
        ):
            raise StoreError("checkpoint ETA must be bounded wall-clock seconds")
        if len(canonical_json(checkpoint)) > 512 * 1024:
            raise StoreError("checkpoint exceeds the local size bound")
        idempotent = self._validate_run_operation_binding(
            operation_key, request_digest
        )
        with self._lock, self._connection:
            if idempotent:
                assert operation_key is not None and request_digest is not None
                replay = self._run_operation_replay_locked(
                    scope,
                    operation_key,
                    request_digest,
                    "CHECKPOINT",
                    run_id,
                )
                if replay is not None:
                    return replay
            row = self._run_row(scope, run_id)
            if row["state"] != ProofRunState.RUNNING.value:
                raise StoreError("only a running owner may checkpoint")
            if row["owner_id"] != worker_id or int(row["fencing_token"]) != token:
                raise StoreError("stale or non-owner checkpoint writer")
            if row["lease_expires_at"] and row["lease_expires_at"] <= utc_now():
                raise StoreError("checkpoint writer lease has expired")
            prior_sequence = 0
            if row["checkpoint_json"]:
                try:
                    prior = json.loads(row["checkpoint_json"])
                    prior_sequence = int(prior["sequence"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise StoreError("stored checkpoint is corrupt") from exc
            checkpoint_document = {
                "format": "elmos-proof-run-checkpoint/v1",
                "runId": run_id,
                "workerId": worker_id,
                "fencingToken": token,
                "sequence": prior_sequence + 1,
                "state": checkpoint,
                "stateDigest": digest_value(checkpoint),
                "progress": {
                    "completed": completed,
                    "total": total,
                    "phase": phase,
                    "etaWallClockSeconds": eta,
                    "etaUnit": "wall-clock-seconds",
                },
                "createdAt": utc_now(),
            }
            updated = self._connection.execute(
                "UPDATE proof_runs SET checkpoint_json=?,updated_at=? WHERE tenant_id=? AND run_id=? AND owner_id=? AND fencing_token=? AND state=?",
                (
                    canonical_json(checkpoint_document).decode("utf-8"),
                    utc_now(),
                    scope.tenant_id,
                    run_id,
                    worker_id,
                    token,
                    ProofRunState.RUNNING.value,
                ),
            )
            if updated.rowcount != 1:
                raise StoreError("checkpoint commit lost its fencing race")
            self._append_event_locked(
                scope,
                "proof_run",
                run_id,
                "checkpoint_committed",
                {
                    "sequence": checkpoint_document["sequence"],
                    "stateDigest": checkpoint_document["stateDigest"],
                    "progress": checkpoint_document["progress"],
                    "fencingToken": token,
                },
            )
            response = dict(self._run_row(scope, run_id))
            if idempotent:
                assert operation_key is not None and request_digest is not None
                self._put_run_operation_locked(
                    scope,
                    operation_key,
                    request_digest,
                    "CHECKPOINT",
                    run_id,
                    response,
                )
            return response

    def retry_run(
        self,
        scope: Scope,
        run_id: str,
        retry_run_id: str,
        *,
        account_concurrency: int = 3,
        maximum_attempts: int | None = None,
        operation_key: str | None = None,
        request_digest: str | None = None,
    ) -> dict[str, Any]:
        """Schedule a new immutable attempt; terminal history is never reopened."""
        validate_identifier(run_id, "runId")
        validate_identifier(retry_run_id, "retryRunId")
        if retry_run_id == run_id:
            raise StoreError("retry run ID must differ from its parent run ID")
        if not isinstance(account_concurrency, int) or isinstance(
            account_concurrency, bool
        ):
            raise StoreError("account concurrency must be an integer")
        if not 1 <= account_concurrency <= 3:
            raise StoreError("top-level account concurrency must be between 1 and 3")
        if maximum_attempts is not None and (
            not isinstance(maximum_attempts, int)
            or isinstance(maximum_attempts, bool)
        ):
            raise StoreError("maximum attempts must be an integer")
        if maximum_attempts is not None and not 1 <= maximum_attempts <= 10:
            raise StoreError("maximum attempts must be between 1 and 10")
        idempotent = self._validate_run_operation_binding(
            operation_key, request_digest
        )
        try:
            with self._lock, self._connection:
                if idempotent:
                    assert operation_key is not None and request_digest is not None
                    replay = self._run_operation_replay_locked(
                        scope,
                        operation_key,
                        request_digest,
                        "RETRY",
                        run_id,
                    )
                    if replay is not None:
                        return replay
                row = self._run_row(scope, run_id)
                state = ProofRunState(row["state"])
                if state not in {ProofRunState.FAILED, ProofRunState.TIMED_OUT}:
                    raise StoreError("only FAILED or TIMED_OUT runs may be retried")
                existing_child = self._connection.execute(
                    "SELECT run_id FROM proof_runs WHERE tenant_id=? "
                    "AND retry_parent_run_id=?",
                    (scope.tenant_id, run_id),
                ).fetchone()
                if existing_child is not None:
                    raise StoreError(
                        "proof run already has an immutable retry child: "
                        + str(existing_child["run_id"])
                    )
                prior_attempt = int(row["retry_attempt"] or 0)
                stored_parent = row["retry_parent_run_id"]
                stored_root = row["retry_root_run_id"]
                stored_maximum = row["retry_maximum_attempts"]
                if stored_root is None:
                    if (
                        prior_attempt != 0
                        or stored_parent is not None
                        or stored_maximum is not None
                    ):
                        raise StoreError("root proof run retry lineage is corrupt")
                    retry_root = run_id
                    effective_maximum = (
                        3 if maximum_attempts is None else maximum_attempts
                    )
                else:
                    validate_identifier(stored_root, "retryRootRunId")
                    if stored_parent is None or prior_attempt < 1:
                        raise StoreError("retry parent or attempt binding is missing")
                    validate_identifier(stored_parent, "retryParentRunId")
                    if stored_maximum is None:
                        raise StoreError("retry maximum attempts binding is missing")
                    effective_maximum = int(stored_maximum)
                    if not 1 <= effective_maximum <= 10:
                        raise StoreError("stored retry maximum attempts is corrupt")
                    if (
                        maximum_attempts is not None
                        and maximum_attempts != effective_maximum
                    ):
                        raise StoreError(
                            "retry maximum attempts is immutable for the retry chain"
                        )
                    retry_root = str(stored_root)
                    root_row = self._run_row(scope, retry_root)
                    if (
                        root_row["retry_parent_run_id"] is not None
                        or root_row["retry_root_run_id"] is not None
                        or int(root_row["retry_attempt"] or 0) != 0
                        or root_row["retry_maximum_attempts"] is not None
                    ):
                        raise StoreError("retry root binding is corrupt")
                attempt = prior_attempt + 1
                if attempt > effective_maximum:
                    raise StoreError("proof run retry limit exceeded")
                try:
                    options = json.loads(row["options_json"] or "{}")
                    bound = (
                        json.loads(row["bound_json"])
                        if row["bound_json"]
                        else None
                    )
                except json.JSONDecodeError as exc:
                    raise StoreError("stored run retry inputs are corrupt") from exc
                if not isinstance(options, dict) or (
                    bound is not None and not isinstance(bound, dict)
                ):
                    raise StoreError("stored run retry inputs are corrupt")
                reserved_retry_options = {
                    "retryOf",
                    "retryRoot",
                    "retryAttempt",
                    "retryMaximumAttempts",
                    "priorResultDigest",
                }
                present_retry_options = set(options) & reserved_retry_options
                if stored_root is None and present_retry_options:
                    raise StoreError("root run contains forged retry lineage options")
                if stored_root is not None:
                    expected_lineage = {
                        "retryOf": stored_parent,
                        "retryRoot": retry_root,
                        "retryAttempt": prior_attempt,
                        "retryMaximumAttempts": effective_maximum,
                    }
                    if any(
                        options.get(key) != value
                        for key, value in expected_lineage.items()
                    ):
                        raise StoreError(
                            "retry columns and immutable options lineage disagree"
                        )
                    prior_result_digest = options.get("priorResultDigest")
                    if prior_result_digest is not None:
                        validate_digest(
                            prior_result_digest, "retryOptions.priorResultDigest"
                        )
                base_options = {
                    key: value
                    for key, value in options.items()
                    if key not in reserved_retry_options
                }
                result_digest = None
                if row["result_json"]:
                    try:
                        result_digest = digest_value(json.loads(row["result_json"]))
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise StoreError("stored run result is corrupt") from exc
                retry_options = {
                    **base_options,
                    "retryOf": run_id,
                    "retryRoot": retry_root,
                    "retryAttempt": attempt,
                    "retryMaximumAttempts": effective_maximum,
                    "priorResultDigest": result_digest,
                }
                retry = self._insert_run_locked(
                    scope,
                    retry_run_id,
                    row["obligation_id"],
                    account_concurrency,
                    engine=row["engine"],
                    engine_version=row["engine_version"],
                    mode=row["mode"],
                    formula_hash=row["formula_hash"],
                    bound=bound,
                    options=retry_options,
                    trace_id=row["trace_id"],
                    retry_parent_run_id=run_id,
                    retry_root_run_id=retry_root,
                    retry_attempt=attempt,
                    retry_maximum_attempts=effective_maximum,
                )
                self._append_event_locked(
                    scope,
                    "proof_run",
                    run_id,
                    "retry_scheduled",
                    {
                        "retryRunId": retry_run_id,
                        "retryRoot": retry_root,
                        "retryAttempt": attempt,
                        "retryMaximumAttempts": effective_maximum,
                    },
                )
                if idempotent:
                    assert operation_key is not None and request_digest is not None
                    self._put_run_operation_locked(
                        scope,
                        operation_key,
                        request_digest,
                        "RETRY",
                        run_id,
                        retry,
                    )
                return retry
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                raise StoreError(
                    "retry scheduling contention prevented a duplicate attempt"
                ) from exc
            raise

    def authorized_transition(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        token: int,
        new_state: ProofRunState,
    ) -> dict[str, Any]:
        return self._authorized_transition(scope, run_id, worker_id, token, new_state)

    def commit_run(
        self, scope: Scope, run_id: str, worker_id: str, token: int, result: ProofResult
    ) -> dict[str, Any]:
        if result.run_id != run_id:
            raise StoreError("result run mismatch")
        try:
            validate_result(result)
        except ValueError as exc:
            raise StoreError(f"invalid proof result: {exc}") from exc
        with self._lock, self._connection:
            run = self._run_row(scope, run_id)
            if result.obligation_id != run["obligation_id"]:
                raise StoreError("result obligation mismatch")
            if (
                run["formula_hash"] is not None
                and result.formula_hash != run["formula_hash"]
            ):
                raise StoreError("result formula does not match proof run")
            row = self._connection.execute(
                "SELECT state,owner_id,fencing_token,lease_expires_at FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise StoreError("unknown proof run")
            if row["state"] != ProofRunState.RUNNING.value:
                raise StoreError("only a running owner may commit")
            if row["owner_id"] != worker_id or int(row["fencing_token"]) != token:
                raise StoreError("stale or non-owner worker")
            if row["lease_expires_at"] and row["lease_expires_at"] <= utc_now():
                raise StoreError("worker lease has expired")
            completed_at = utc_now()
            wall_clock_ms = None
            if run["started_at"]:
                started = datetime.fromisoformat(
                    str(run["started_at"]).replace("Z", "+00:00")
                )
                completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                wall_clock_ms = max(
                    0, int((completed - started).total_seconds() * 1000)
                )
            updated = self._connection.execute(
                "UPDATE proof_runs SET state=?, result_json=?, completed_at=?, wall_clock_ms=?, lease_expires_at=NULL, updated_at=? WHERE tenant_id=? AND run_id=? AND owner_id=? AND fencing_token=? AND state=?",
                (
                    ProofRunState.SUCCEEDED.value,
                    canonical_json(result_to_dict(result)).decode("utf-8"),
                    completed_at,
                    wall_clock_ms,
                    completed_at,
                    scope.tenant_id,
                    run_id,
                    worker_id,
                    token,
                    ProofRunState.RUNNING.value,
                ),
            )
            if updated.rowcount != 1:
                raise StoreError("proof result commit lost its fencing race")
            self._append_event_locked(
                scope,
                "proof_run",
                run_id,
                "evidence_committed",
                {"fencingToken": token, "status": result.status.value},
            )
        return self.get_run(scope, run_id)

    def _authorized_transition(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        token: int,
        new_state: ProofRunState,
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            row = self._run_row(scope, run_id)
            if row["owner_id"] != worker_id or int(row["fencing_token"]) != token:
                raise StoreError("stale or non-owner worker")
            if row["lease_expires_at"] and row["lease_expires_at"] <= utc_now():
                raise StoreError("worker lease has expired")
            current = ProofRunState(row["state"])
            if new_state not in _ALLOWED_TRANSITIONS[current]:
                raise StoreError(
                    f"invalid transition {current.value}->{new_state.value}"
                )
            updated = self._connection.execute(
                "UPDATE proof_runs SET state=?, started_at=CASE WHEN ?=? AND started_at IS NULL THEN ? ELSE started_at END, updated_at=? WHERE tenant_id=? AND run_id=? AND owner_id=? AND fencing_token=? AND state=?",
                (
                    new_state.value,
                    new_state.value,
                    ProofRunState.RUNNING.value,
                    utc_now(),
                    utc_now(),
                    scope.tenant_id,
                    run_id,
                    worker_id,
                    token,
                    current.value,
                ),
            )
            if updated.rowcount != 1:
                raise StoreError("authorized transition lost its fencing race")
            self._append_event_locked(
                scope, "proof_run", run_id, "state_changed", {"state": new_state.value}
            )
        return self.get_run(scope, run_id)

    def put_cache(
        self,
        scope: Scope,
        cache_key: str,
        result: dict[str, Any],
        ttl_seconds: int = 86_400,
    ) -> None:
        if ttl_seconds < 1 or ttl_seconds > 31_536_000:
            raise StoreError("cache TTL is outside the allowed bound")
        expires = (
            (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        storage_key = digest_value(
            {"scope": scope.to_dict(), "callerCacheKey": cache_key}
        )
        stored_result = {
            "scopeDigest": digest_value(scope.to_dict()),
            "callerCacheKey": cache_key,
            "result": result,
        }
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO cache_entries VALUES (?, ?, ?, 0, ?) ON CONFLICT(tenant_id,cache_key) DO UPDATE SET result_json=excluded.result_json, stale=0, expires_at=excluded.expires_at",
                (
                    scope.tenant_id,
                    storage_key,
                    canonical_json(stored_result).decode("utf-8"),
                    expires,
                ),
            )

    def get_cache(self, scope: Scope, cache_key: str) -> dict[str, Any] | None:
        storage_key = digest_value(
            {"scope": scope.to_dict(), "callerCacheKey": cache_key}
        )
        with self._lock:
            row = self._connection.execute(
                "SELECT result_json, stale, expires_at FROM cache_entries WHERE tenant_id=? AND cache_key=?",
                (scope.tenant_id, storage_key),
            ).fetchone()
        if row is None or row["stale"] or row["expires_at"] <= utc_now():
            return None
        stored = json.loads(row["result_json"])
        if (
            not isinstance(stored, dict)
            or stored.get("scopeDigest") != digest_value(scope.to_dict())
            or stored.get("callerCacheKey") != cache_key
            or not isinstance(stored.get("result"), dict)
        ):
            return None
        return stored["result"]

    def invalidate_cache(self, scope: Scope, dependency_id: str) -> int:
        with self._lock, self._connection:
            # Cache records are keyed by a canonical dependency tuple.  The
            # dependency id is intentionally matched only in stored metadata.
            rows = self._connection.execute(
                "SELECT cache_key,result_json FROM cache_entries WHERE tenant_id=? AND stale=0",
                (scope.tenant_id,),
            ).fetchall()
            affected = 0
            for row in rows:
                stored = json.loads(row["result_json"])
                if (
                    not isinstance(stored, dict)
                    or stored.get("scopeDigest") != digest_value(scope.to_dict())
                    or not isinstance(stored.get("result"), dict)
                ):
                    continue
                if dependency_id in stored["result"].get("dependencies", []):
                    self._connection.execute(
                        "UPDATE cache_entries SET stale=1 WHERE tenant_id=? AND cache_key=?",
                        (scope.tenant_id, row["cache_key"]),
                    )
                    affected += 1
            return affected

    def verify_event_chain(
        self, scope: Scope, aggregate_type: str, aggregate_id: str
    ) -> list[str]:
        """Verify the append-only hash chain without trusting stored hashes."""
        errors: list[str] = []
        previous = "0" * 64
        for event in self.events(scope, aggregate_type, aggregate_id):
            if event["previousHash"] != previous:
                errors.append(f"sequence {event['sequence']}: previous hash mismatch")
            unsigned = {
                "tenantId": event["tenantId"],
                "aggregateType": event["aggregateType"],
                "aggregateId": event["aggregateId"],
                "sequence": event["sequence"],
                "eventType": event["eventType"],
                "payload": event["payload"],
                "previousHash": event["previousHash"],
            }
            expected = digest_value(unsigned)
            if event["eventHash"] != expected:
                errors.append(f"sequence {event['sequence']}: event hash mismatch")
            previous = event["eventHash"]
        return errors


def result_to_dict(result: ProofResult) -> dict[str, Any]:
    return {
        "runId": result.run_id,
        "obligationId": result.obligation_id,
        "status": result.status.value,
        "assuranceLevel": result.assurance_level.value,
        "engine": result.engine,
        "mode": result.mode,
        "assumptionHash": result.assumption_hash,
        "tcbHash": result.tcb_hash,
        "formulaHash": result.formula_hash,
        "bound": result.bound,
        "artifacts": list(result.artifact_refs),
        "counterexampleId": result.counterexample_id,
        "diagnostics": list(result.diagnostics),
        "createdAt": result.created_at,
        "stale": result.stale,
    }
