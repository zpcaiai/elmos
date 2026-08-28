from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_json, digest_value, validate_identifier
from .contracts import ProofResult, ProofRunState, Scope, TERMINAL_RUN_STATES, utc_now
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
              started_at TEXT,
              completed_at TEXT,
              wall_clock_ms INTEGER,
              result_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, run_id)
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
            """
        )
        self._ensure_legacy_columns()

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
            raise StoreError("execution permit or nonce has already been consumed") from exc

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

    def get_execution_receipt(
        self, scope: Scope, execution_id: str
    ) -> dict[str, Any]:
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

    def telemetry(
        self, scope: Scope, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10_000:
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
                self._append_event_locked(
                    scope,
                    "assurance_document",
                    f"{document_type}:{document_id}:{version}",
                    "registered",
                    {
                        "documentType": document_type,
                        "documentId": document_id,
                        "version": version,
                        "contentDigest": content_digest,
                        "scopeDigest": scope_digest,
                    },
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
        query = (
            "SELECT * FROM assurance_documents WHERE tenant_id=? AND document_type=? AND document_id=?"
        )
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
        if not isinstance(account_concurrency, int) or isinstance(account_concurrency, bool):
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
            from .canonical import validate_digest

            formula_hash = validate_digest(formula_hash, "formulaHash")
        if bound is not None and not isinstance(bound, dict):
            raise StoreError("run bound must be an object")
        if options is not None and not isinstance(options, dict):
            raise StoreError("run options must be an object")
        if trace_id is not None:
            validate_identifier(trace_id, "traceId")
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
            if existing is not None:
                raise StoreError("duplicate proof run")
            active = self._connection.execute(
                "SELECT count(*) FROM proof_runs WHERE tenant_id=? AND account_id=? AND state NOT IN (?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    scope.account_id,
                    *(state.value for state in TERMINAL_RUN_STATES),
                ),
            ).fetchone()[0]
            if active >= account_concurrency:
                raise StoreError("top-level account concurrency limit exceeded")
            duplicate_obligation = self._connection.execute(
                "SELECT 1 FROM proof_runs WHERE tenant_id=? AND obligation_id=? AND state IN (?, ?) LIMIT 1",
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
            self._connection.execute(
                "INSERT INTO proof_runs(tenant_id,run_id,account_id,project_id,source_artifact_digest,target_artifact_digest,environment_digest,workload_key,data_classification,obligation_id,engine,engine_version,formula_hash,mode,bound_json,options_json,state,owner_id,fencing_token,lease_expires_at,trace_id,checkpoint_json,started_at,completed_at,wall_clock_ms,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    canonical_json(bound).decode("utf-8") if bound is not None else None,
                    canonical_json(options or {}).decode("utf-8"),
                    ProofRunState.QUEUED.value,
                    None,
                    1,
                    None,
                    trace_id,
                    None,
                    None,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
            self._append_event_locked(
                scope,
                "proof_run",
                run_id,
                "submitted",
                {"fencingToken": 1, "obligationId": obligation_id},
            )
        return self.get_run(scope, run_id)

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

    def control_run(
        self, scope: Scope, run_id: str, action: str
    ) -> dict[str, Any]:
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
                if current in TERMINAL_RUN_STATES or current == ProofRunState.CANCEL_REQUESTED:
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
            if run["formula_hash"] is not None and result.formula_hash != run["formula_hash"]:
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
                wall_clock_ms = max(0, int((completed - started).total_seconds() * 1000))
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
                raise StoreError(f"invalid transition {current.value}->{new_state.value}")
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
