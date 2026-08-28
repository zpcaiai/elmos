"""Durable SQLite control-plane store.

The store is the authoritative local implementation shared by the harness and
semantic compiler.  Every query is tenant *and* project qualified.  Composite
foreign keys prevent cross-tenant references.  Evidence, audit, outbox,
checkpoint, proof-result and reconciliation journals are append-only through
database triggers.  Mutable aggregates use optimistic sequence checks; worker
commits additionally require an epoch, fencing generation and opaque lease.

SQLite is suitable for deterministic local operation and tests.  It does not
claim PostgreSQL/RLS production evidence.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, Mapping

from .canonical import canonical_json, digest_bytes, digest_object, verify_digest
from .contracts import (
    ArtifactRef,
    CheckpointRecord,
    EvidenceProducer,
    EvidenceRecord,
    LeaseGrant,
    MetricPoint,
    SecurityContext,
)
from .errors import AuthorizationError, ConflictError, IntegrityError, NotFoundError, StoreError, ValidationError
from .storage import (
    MAX_INLINE_CHECKPOINT_BYTES,
    MAX_INLINE_EVIDENCE_BYTES,
    ControlPlaneJobClaim,
    ControlPlaneReceipt,
    StorageReadiness,
    StorageStatus,
)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _aware(value: datetime, *, field: str = "now") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field} must be timezone-aware", code="INVALID_TIMESTAMP")
    return value


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    tenant_id: str
    project_id: str
    run_id: str
    actor_id: str
    revision_set_id: str
    state: str
    sequence: int
    execution_epoch: int
    fencing_generation: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    deadline_at: datetime | None
    last_checkpoint_id: str | None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationRecord:
    effect_id: str
    tenant_id: str
    project_id: str
    run_id: str
    provider: str
    operation: str
    idempotency_key: str
    request_sha256: str
    state: str
    external_reference: str | None
    version: int
    execution_epoch: int
    fencing_generation: int


_MIGRATION_1 = r"""
CREATE TABLE tenants (
  tenant_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
CREATE TABLE projects (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id),
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE RESTRICT
);
CREATE TABLE actors (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, actor_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE RESTRICT
);
CREATE TABLE runs (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  revision_set_id TEXT NOT NULL,
  state TEXT NOT NULL,
  sequence INTEGER NOT NULL DEFAULT 0 CHECK (sequence >= 0),
  execution_epoch INTEGER NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation INTEGER NOT NULL CHECK (fencing_generation >= 1),
  lease_owner TEXT,
  lease_token_sha256 TEXT,
  lease_expires_at TEXT,
  deadline_at TEXT,
  last_checkpoint_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, run_id),
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE idempotency_receipts (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE control_plane_receipts (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  run_id TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_json TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE evidence (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  subject_revision TEXT NOT NULL,
  evidence_class TEXT NOT NULL,
  scope TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  content_bytes BLOB NOT NULL,
  record_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  PRIMARY KEY (tenant_id, project_id, evidence_id),
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE evidence_revocations (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  revocation_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, revocation_id),
  UNIQUE (tenant_id, project_id, evidence_id),
  FOREIGN KEY (tenant_id, project_id, evidence_id) REFERENCES evidence(tenant_id, project_id, evidence_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE audit_events (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE outbox_events (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE RESTRICT
);
CREATE TABLE outbox_deliveries (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  delivery_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  destination TEXT NOT NULL,
  state TEXT NOT NULL,
  detail_sha256 TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, delivery_id),
  FOREIGN KEY (tenant_id, project_id, event_id) REFERENCES outbox_events(tenant_id, project_id, event_id) ON DELETE RESTRICT
);
CREATE TABLE run_checkpoints (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  checkpoint_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  execution_epoch INTEGER NOT NULL,
  fencing_generation INTEGER NOT NULL,
  sequence INTEGER NOT NULL,
  payload_sha256 TEXT NOT NULL,
  payload_bytes BLOB NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, checkpoint_id),
  UNIQUE (tenant_id, project_id, run_id, sequence),
  FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES runs(tenant_id, project_id, run_id) ON DELETE RESTRICT
);
CREATE TABLE external_effects (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  execution_epoch INTEGER NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation INTEGER NOT NULL CHECK (fencing_generation >= 1),
  provider TEXT NOT NULL,
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  state TEXT NOT NULL,
  external_reference TEXT,
  reconciliation_strategy TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, effect_id),
  UNIQUE (tenant_id, project_id, provider, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, run_id) REFERENCES runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, actor_id) REFERENCES actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT
);
CREATE TABLE effect_events (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  state TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, event_id),
  FOREIGN KEY (tenant_id, project_id, effect_id) REFERENCES external_effects(tenant_id, project_id, effect_id) ON DELETE RESTRICT
);
CREATE TABLE metric_points (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  metric_id TEXT NOT NULL,
  name TEXT NOT NULL,
  value REAL NOT NULL,
  labels_json TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, metric_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE RESTRICT
);
CREATE INDEX idx_evidence_subject ON evidence(tenant_id, project_id, subject_revision, created_at);
CREATE INDEX idx_outbox_topic ON outbox_events(tenant_id, project_id, topic, created_at);
CREATE INDEX idx_effect_state ON external_effects(tenant_id, project_id, state);
CREATE INDEX idx_metric_name ON metric_points(tenant_id, project_id, name, occurred_at);
"""


_MIGRATION_2 = r"""
CREATE TRIGGER immutable_evidence_update BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT, 'append-only evidence'); END;
CREATE TRIGGER immutable_evidence_delete BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT, 'append-only evidence'); END;
CREATE TRIGGER immutable_revocation_update BEFORE UPDATE ON evidence_revocations BEGIN SELECT RAISE(ABORT, 'append-only evidence revocation'); END;
CREATE TRIGGER immutable_revocation_delete BEFORE DELETE ON evidence_revocations BEGIN SELECT RAISE(ABORT, 'append-only evidence revocation'); END;
CREATE TRIGGER immutable_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER immutable_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'append-only audit'); END;
CREATE TRIGGER immutable_outbox_update BEFORE UPDATE ON outbox_events BEGIN SELECT RAISE(ABORT, 'append-only outbox'); END;
CREATE TRIGGER immutable_outbox_delete BEFORE DELETE ON outbox_events BEGIN SELECT RAISE(ABORT, 'append-only outbox'); END;
CREATE TRIGGER immutable_delivery_update BEFORE UPDATE ON outbox_deliveries BEGIN SELECT RAISE(ABORT, 'append-only delivery'); END;
CREATE TRIGGER immutable_delivery_delete BEFORE DELETE ON outbox_deliveries BEGIN SELECT RAISE(ABORT, 'append-only delivery'); END;
CREATE TRIGGER immutable_checkpoint_update BEFORE UPDATE ON run_checkpoints BEGIN SELECT RAISE(ABORT, 'append-only checkpoint'); END;
CREATE TRIGGER immutable_checkpoint_delete BEFORE DELETE ON run_checkpoints BEGIN SELECT RAISE(ABORT, 'append-only checkpoint'); END;
CREATE TRIGGER immutable_effect_event_update BEFORE UPDATE ON effect_events BEGIN SELECT RAISE(ABORT, 'append-only effect journal'); END;
CREATE TRIGGER immutable_effect_event_delete BEFORE DELETE ON effect_events BEGIN SELECT RAISE(ABORT, 'append-only effect journal'); END;
CREATE TRIGGER immutable_metric_update BEFORE UPDATE ON metric_points BEGIN SELECT RAISE(ABORT, 'append-only metric'); END;
CREATE TRIGGER immutable_metric_delete BEFORE DELETE ON metric_points BEGIN SELECT RAISE(ABORT, 'append-only metric'); END;
"""


_MIGRATION_3 = r"""
CREATE TABLE scheduler_jobs (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  run_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING','CLAIMED','COMPLETED')),
  scheduler_role TEXT,
  worker_instance_id TEXT,
  lease_token_sha256 TEXT,
  lease_generation INTEGER NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
  lease_expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, operation, idempotency_key),
  FOREIGN KEY (tenant_id, project_id, operation, idempotency_key)
    REFERENCES control_plane_receipts(tenant_id, project_id, operation, idempotency_key)
    ON DELETE RESTRICT
);
CREATE TABLE scheduler_claim_events (
  event_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  scheduler_role TEXT NOT NULL,
  worker_instance_id TEXT NOT NULL,
  lease_generation INTEGER NOT NULL,
  occurred_at TEXT NOT NULL
);
CREATE TRIGGER enqueue_control_plane_job AFTER INSERT ON control_plane_receipts
WHEN NEW.operation = 'invoke'
BEGIN
  INSERT INTO scheduler_jobs(
    tenant_id,project_id,actor_id,operation,idempotency_key,request_sha256,run_id,
    state,lease_generation,created_at,updated_at
  ) VALUES (
    NEW.tenant_id,NEW.project_id,NEW.actor_id,NEW.operation,NEW.idempotency_key,
    NEW.request_sha256,NEW.run_id,'PENDING',0,NEW.created_at,NEW.created_at
  );
END;
CREATE TRIGGER complete_control_plane_job AFTER UPDATE OF response_json ON control_plane_receipts
WHEN OLD.response_json IS NULL AND NEW.response_json IS NOT NULL
BEGIN
  UPDATE scheduler_jobs SET state='COMPLETED',lease_token_sha256=NULL,
    lease_expires_at=NULL,updated_at=NEW.completed_at
  WHERE tenant_id=NEW.tenant_id AND project_id=NEW.project_id
    AND operation=NEW.operation AND idempotency_key=NEW.idempotency_key;
END;
CREATE TRIGGER immutable_scheduler_claim_event_update BEFORE UPDATE ON scheduler_claim_events
BEGIN SELECT RAISE(ABORT, 'append-only scheduler claim event'); END;
CREATE TRIGGER immutable_scheduler_claim_event_delete BEFORE DELETE ON scheduler_claim_events
BEGIN SELECT RAISE(ABORT, 'append-only scheduler claim event'); END;
CREATE INDEX idx_scheduler_jobs_claim
  ON scheduler_jobs(state, lease_expires_at, created_at);
"""


_MIGRATIONS = ((1, _MIGRATION_1), (2, _MIGRATION_2), (3, _MIGRATION_3))

_TERMINAL_RUN_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "PARTIAL"})
_SIDE_EFFECT_START_STATES = frozenset({"EXECUTING", "VERIFYING", "CERTIFYING", "RESUMING"})
_EFFECT_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "STARTED": frozenset({"SUCCEEDED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "UNKNOWN_RESULT"}),
    "FAILED_RETRYABLE": frozenset({"SUCCEEDED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "UNKNOWN_RESULT"}),
    "UNKNOWN_RESULT": frozenset({"SUCCEEDED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "UNKNOWN_RESULT"}),
    "SUCCEEDED": frozenset({"RECONCILED"}),
    "FAILED_TERMINAL": frozenset({"RECONCILED"}),
    "RECONCILED": frozenset(),
}


class SQLiteStore:
    """Thread-safe SQLite repository with explicit resource-scoped methods."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
        self._migrate()

    @property
    def schema_version(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
        return int(row["version"])

    def readiness(self) -> StorageReadiness:
        """Return an explicit local-engineering health result.

        This result never represents a production-ready shared store.  Service
        startup must reject ``SQLiteStore`` when runtime mode is production.
        """

        try:
            version = self.schema_version
        except Exception:
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="SQLite schema probe failed",
                backend="sqlite-local-engineering",
            )
        if version != len(_MIGRATIONS):
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason="SQLite schema is incomplete",
                backend="sqlite-local-engineering",
                schema_version=version,
            )
        return StorageReadiness(
            status=StorageStatus.READY,
            reason="local-engineering SQLite store is ready",
            backend="sqlite-local-engineering",
            schema_version=version,
            server_version=sqlite3.sqlite_version,
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _migrate(self) -> None:
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            existing = {
                int(row["version"]): str(row["checksum"])
                for row in self._connection.execute("SELECT version, checksum FROM schema_migrations")
            }
            for version, sql in _MIGRATIONS:
                checksum = digest_bytes(sql.encode("utf-8"), domain="sqlite-migration")
                if version in existing:
                    if existing[version] != checksum:
                        raise StoreError("migration checksum mismatch", code="MIGRATION_DRIFT", details={"version": version})
                    continue
                applied_at = _iso(datetime.now(UTC))
                escaped_checksum = checksum.replace("'", "''")
                escaped_time = applied_at.replace("'", "''")
                try:
                    self._connection.executescript(
                        f"BEGIN IMMEDIATE;\n{sql}\nINSERT INTO schema_migrations(version, checksum, applied_at) VALUES ({version}, '{escaped_checksum}', '{escaped_time}');\nCOMMIT;"
                    )
                except sqlite3.Error as exc:
                    try:
                        self._connection.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                    raise StoreError("database migration failed", code="MIGRATION_FAILED", details={"version": version}) from exc

    @contextmanager
    def transaction(self, context: SecurityContext | None = None) -> Iterator[sqlite3.Cursor]:
        # ``context`` is accepted to match the production protocol. SQLite has
        # no trusted session variables, so every statement remains explicitly
        # tenant/project qualified and composite-FK constrained.
        del context
        with self._lock:
            cursor = self._connection.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
                yield cursor
                cursor.execute("COMMIT")
            except Exception:
                try:
                    cursor.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            finally:
                cursor.close()

    def register_scope(self, context: SecurityContext, *, now: datetime | None = None) -> None:
        """Bootstrap an already-authenticated tenant/project/actor binding."""

        timestamp = _iso(now or datetime.now(UTC))
        with self.transaction(context) as cursor:
            cursor.execute("INSERT OR IGNORE INTO tenants(tenant_id, created_at) VALUES (?, ?)", (context.tenant_id, timestamp))
            cursor.execute(
                "INSERT OR IGNORE INTO projects(tenant_id, project_id, created_at) VALUES (?, ?, ?)",
                (context.tenant_id, context.project_id, timestamp),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO actors(tenant_id, project_id, actor_id, created_at) VALUES (?, ?, ?, ?)",
                (context.tenant_id, context.project_id, context.actor_id, timestamp),
            )

    def assert_scope(self, context: SecurityContext) -> None:
        with self.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT 1 FROM actors WHERE tenant_id=? AND project_id=? AND actor_id=?",
                (context.tenant_id, context.project_id, context.actor_id),
            ).fetchone()
        if row is None:
            raise AuthorizationError("authenticated scope is not registered", code="SCOPE_NOT_REGISTERED")

    def _append_audit_outbox(
        self,
        cursor: sqlite3.Cursor,
        context: SecurityContext,
        *,
        event_type: str,
        subject_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        event_id = f"evt-{uuid.uuid4()}"
        payload_json = canonical_json(payload)
        payload_sha256 = digest_bytes(payload_json.encode("utf-8"), domain="event-payload")
        created_at = _iso(datetime.now(UTC))
        cursor.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                context.tenant_id,
                context.project_id,
                event_id,
                context.actor_id,
                event_type,
                subject_id,
                payload_json,
                payload_sha256,
                created_at,
            ),
        )
        cursor.execute(
            "INSERT INTO outbox_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                context.tenant_id,
                context.project_id,
                event_id,
                f"proof-harness.{event_type.lower()}",
                subject_id,
                payload_json,
                payload_sha256,
                created_at,
            ),
        )
        return event_id

    def _idempotent_response(
        self,
        cursor: sqlite3.Cursor,
        context: SecurityContext,
        operation: str,
        key: str | None,
        request_sha256: str,
    ) -> Mapping[str, Any] | None:
        if key is None:
            return None
        if not key.strip():
            raise ValidationError("idempotency key cannot be empty")
        row = cursor.execute(
            "SELECT actor_id, request_sha256, response_json FROM idempotency_receipts WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=?",
            (context.tenant_id, context.project_id, operation, key),
        ).fetchone()
        if row is None:
            return None
        if row["actor_id"] != context.actor_id:
            raise AuthorizationError("idempotency receipt belongs to another actor", code="IDEMPOTENCY_SCOPE_MISMATCH")
        if row["request_sha256"] != request_sha256:
            raise ConflictError("idempotency key was reused with a different request", code="IDEMPOTENCY_CONFLICT")
        return json.loads(row["response_json"])

    def _store_idempotency(
        self,
        cursor: sqlite3.Cursor,
        context: SecurityContext,
        operation: str,
        key: str | None,
        request_sha256: str,
        response: Mapping[str, Any],
    ) -> None:
        if key is None:
            return
        cursor.execute(
            "INSERT INTO idempotency_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                operation,
                key,
                request_sha256,
                canonical_json(response),
                _iso(datetime.now(UTC)),
            ),
        )

    # ---- Evidence -----------------------------------------------------

    def append_evidence(
        self,
        context: SecurityContext,
        record: EvidenceRecord,
        content: bytes,
        *,
        idempotency_key: str | None = None,
    ) -> EvidenceRecord:
        self.assert_scope(context)
        if (record.tenant_id, record.project_id, record.actor_id) != (
            context.tenant_id,
            context.project_id,
            context.actor_id,
        ):
            raise AuthorizationError("evidence scope does not match authenticated context", code="EVIDENCE_SCOPE_MISMATCH")
        if not isinstance(content, bytes):
            raise ValidationError("evidence content must be bytes")
        if len(content) > MAX_INLINE_EVIDENCE_BYTES:
            raise ValidationError(
                "evidence exceeds the inline storage limit",
                code="EVIDENCE_TOO_LARGE",
                details={"maximum_bytes": MAX_INLINE_EVIDENCE_BYTES},
            )
        if len(content) != record.content.byte_length:
            raise IntegrityError("evidence byte length mismatch", code="EVIDENCE_LENGTH_MISMATCH")
        verify_digest(content, record.content.sha256, domain=record.content.domain)
        request_sha256 = digest_object(
            {"record": record, "content_sha256": record.content.sha256},
            domain="append-evidence-request",
        )
        with self.transaction(context) as cursor:
            receipt = self._idempotent_response(cursor, context, "append_evidence", idempotency_key, request_sha256)
            if receipt is not None:
                existing, existing_bytes = self._get_evidence_cursor(cursor, context, str(receipt["evidence_id"]))
                verify_digest(existing_bytes, existing.content.sha256, domain=existing.content.domain)
                return existing
            for parent_id in record.lineage:
                parent = cursor.execute(
                    "SELECT 1 FROM evidence WHERE tenant_id=? AND project_id=? AND evidence_id=?",
                    (context.tenant_id, context.project_id, parent_id),
                ).fetchone()
                if parent is None:
                    raise IntegrityError("evidence lineage is unresolved", code="LINEAGE_NOT_FOUND", details={"evidence_id": parent_id})
            try:
                cursor.execute(
                    "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        record.evidence_id,
                        context.actor_id,
                        record.subject_revision,
                        record.evidence_class,
                        record.scope,
                        record.content.sha256,
                        sqlite3.Binary(content),
                        canonical_json(record),
                        _iso(record.created_at),
                        _iso(record.expires_at) if record.expires_at else None,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise IntegrityError("evidence id already exists", code="EVIDENCE_ALREADY_EXISTS") from exc
            self._append_audit_outbox(
                cursor,
                context,
                event_type="EVIDENCE_APPENDED",
                subject_id=record.evidence_id,
                payload={"evidence_id": record.evidence_id, "sha256": record.content.sha256},
            )
            self._store_idempotency(
                cursor,
                context,
                "append_evidence",
                idempotency_key,
                request_sha256,
                {"evidence_id": record.evidence_id},
            )
        return record

    def _get_evidence_cursor(
        self, cursor: sqlite3.Cursor, context: SecurityContext, evidence_id: str
    ) -> tuple[EvidenceRecord, bytes]:
        row = cursor.execute(
            "SELECT record_json, content_bytes FROM evidence WHERE tenant_id=? AND project_id=? AND evidence_id=?",
            (context.tenant_id, context.project_id, evidence_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("evidence was not found", details={"evidence_id": evidence_id})
        return self._decode_evidence(str(row["record_json"])), bytes(row["content_bytes"])

    def get_evidence(self, context: SecurityContext, evidence_id: str) -> tuple[EvidenceRecord, bytes]:
        self.assert_scope(context)
        with self.transaction(context) as cursor:
            return self._get_evidence_cursor(cursor, context, evidence_id)

    @staticmethod
    def _decode_evidence(payload: str) -> EvidenceRecord:
        data = json.loads(payload)
        content = ArtifactRef(**data.pop("content"))
        producer = EvidenceProducer(**data.pop("producer"))
        data["created_at"] = _dt(data["created_at"])
        if data.get("expires_at") is not None:
            data["expires_at"] = _dt(data["expires_at"])
        data["lineage"] = tuple(data.get("lineage", ()))
        data["assumptions"] = tuple(data.get("assumptions", ()))
        return EvidenceRecord(content=content, producer=producer, **data)

    def revoke_evidence(
        self,
        context: SecurityContext,
        evidence_id: str,
        *,
        reason: str,
        revocation_id: str | None = None,
        now: datetime | None = None,
    ) -> str:
        self.assert_scope(context)
        if not reason.strip():
            raise ValidationError("revocation reason is required")
        revocation_id = revocation_id or f"revoke-{uuid.uuid4()}"
        timestamp = _iso(now or datetime.now(UTC))
        with self.transaction(context) as cursor:
            self._get_evidence_cursor(cursor, context, evidence_id)
            try:
                cursor.execute(
                    "INSERT INTO evidence_revocations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (context.tenant_id, context.project_id, revocation_id, evidence_id, context.actor_id, reason, timestamp),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("evidence is already revoked", code="EVIDENCE_ALREADY_REVOKED") from exc
            self._append_audit_outbox(
                cursor,
                context,
                event_type="EVIDENCE_REVOKED",
                subject_id=evidence_id,
                payload={"evidence_id": evidence_id, "revocation_id": revocation_id, "reason": reason},
            )
        return revocation_id

    def evidence_revoked(self, context: SecurityContext, evidence_id: str) -> bool:
        self.assert_scope(context)
        with self.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT 1 FROM evidence_revocations WHERE tenant_id=? AND project_id=? AND evidence_id=?",
                (context.tenant_id, context.project_id, evidence_id),
            ).fetchone()
        return row is not None

    # ---- Runs, optimistic state and fencing ---------------------------

    def create_run(
        self,
        context: SecurityContext,
        *,
        run_id: str,
        revision_set_id: str,
        initial_state: str = "CREATED",
        deadline_at: datetime | None = None,
        idempotency_key: str | None = None,
        now: datetime | None = None,
    ) -> RunSnapshot:
        self.assert_scope(context)
        if not run_id or not revision_set_id:
            raise ValidationError("run_id and revision_set_id are required")
        timestamp = _aware(now or datetime.now(UTC))
        request = {
            "run_id": run_id,
            "revision_set_id": revision_set_id,
            "state": initial_state,
            "deadline_at": deadline_at,
            "execution_epoch": context.execution_epoch,
            "fencing_generation": context.fencing_generation,
        }
        request_sha256 = digest_object(request, domain="create-run-request")
        with self.transaction(context) as cursor:
            receipt = self._idempotent_response(cursor, context, "create_run", idempotency_key, request_sha256)
            if receipt is not None:
                return self._get_run_cursor(cursor, context, str(receipt["run_id"]))
            try:
                cursor.execute(
                    "INSERT INTO runs(tenant_id,project_id,run_id,actor_id,revision_set_id,state,sequence,execution_epoch,fencing_generation,deadline_at,created_at,updated_at) VALUES (?,?,?,?,?,?,0,?,?,?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        run_id,
                        context.actor_id,
                        revision_set_id,
                        initial_state,
                        context.execution_epoch,
                        context.fencing_generation,
                        _iso(deadline_at) if deadline_at else None,
                        _iso(timestamp),
                        _iso(timestamp),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("run id already exists", code="RUN_ALREADY_EXISTS") from exc
            self._append_audit_outbox(
                cursor,
                context,
                event_type="RUN_CREATED",
                subject_id=run_id,
                payload=request,
            )
            self._store_idempotency(
                cursor,
                context,
                "create_run",
                idempotency_key,
                request_sha256,
                {"run_id": run_id},
            )
            return self._get_run_cursor(cursor, context, run_id)

    def _get_run_cursor(self, cursor: sqlite3.Cursor, context: SecurityContext, run_id: str) -> RunSnapshot:
        row = cursor.execute(
            "SELECT * FROM runs WHERE tenant_id=? AND project_id=? AND run_id=?",
            (context.tenant_id, context.project_id, run_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("run was not found", details={"run_id": run_id})
        if row["actor_id"] != context.actor_id:
            raise AuthorizationError("run belongs to another actor", code="RUN_ACTOR_MISMATCH")
        return self._run_snapshot(row)

    @staticmethod
    def _run_snapshot(row: sqlite3.Row) -> RunSnapshot:
        return RunSnapshot(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["run_id"]),
            actor_id=str(row["actor_id"]),
            revision_set_id=str(row["revision_set_id"]),
            state=str(row["state"]),
            sequence=int(row["sequence"]),
            execution_epoch=int(row["execution_epoch"]),
            fencing_generation=int(row["fencing_generation"]),
            lease_owner=str(row["lease_owner"]) if row["lease_owner"] is not None else None,
            lease_expires_at=_dt(str(row["lease_expires_at"])) if row["lease_expires_at"] else None,
            deadline_at=_dt(str(row["deadline_at"])) if row["deadline_at"] else None,
            last_checkpoint_id=str(row["last_checkpoint_id"]) if row["last_checkpoint_id"] is not None else None,
            updated_at=_dt(str(row["updated_at"])),
        )

    def get_run(self, context: SecurityContext, run_id: str | None = None) -> RunSnapshot:
        self.assert_scope(context)
        selected = run_id or context.run_id
        if selected is None:
            raise ValidationError("run_id is required")
        with self.transaction(context) as cursor:
            return self._get_run_cursor(cursor, context, selected)

    def acquire_lease(
        self,
        context: SecurityContext,
        *,
        owner_id: str,
        ttl_seconds: int,
        expected_sequence: int,
        now: datetime | None = None,
    ) -> LeaseGrant:
        self.assert_scope(context)
        if context.run_id is None or not owner_id:
            raise ValidationError("run-bound context and owner_id are required")
        if ttl_seconds < 1 or ttl_seconds > 86_400:
            raise ValidationError("lease ttl is outside the safe range")
        current_time = _aware(now or datetime.now(UTC))
        expires_at = current_time + timedelta(seconds=ttl_seconds)
        token = secrets.token_urlsafe(32)
        token_sha256 = digest_bytes(token.encode("utf-8"), domain="lease-token")
        with self.transaction(context) as cursor:
            run = self._get_run_cursor(cursor, context, context.run_id)
            if run.sequence != expected_sequence:
                raise ConflictError("optimistic sequence conflict", details={"expected": expected_sequence, "actual": run.sequence})
            if run.execution_epoch != context.execution_epoch:
                raise ConflictError("execution epoch is stale", code="STALE_EPOCH")
            if run.fencing_generation != context.fencing_generation:
                raise ConflictError("fencing generation is stale", code="STALE_FENCE")
            if run.state in _TERMINAL_RUN_STATES:
                raise ConflictError("terminal run cannot acquire a lease", code="RUN_TERMINAL")
            if run.lease_expires_at is not None and current_time < run.lease_expires_at and run.lease_owner != owner_id:
                raise ConflictError("run already has an active lease", code="LEASE_HELD")
            generation = run.fencing_generation + 1
            sequence = run.sequence + 1
            cursor.execute(
                "UPDATE runs SET lease_owner=?,lease_token_sha256=?,lease_expires_at=?,fencing_generation=?,sequence=?,updated_at=? WHERE tenant_id=? AND project_id=? AND run_id=? AND sequence=? AND execution_epoch=? AND fencing_generation=?",
                (
                    owner_id,
                    token_sha256,
                    _iso(expires_at),
                    generation,
                    sequence,
                    _iso(current_time),
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    expected_sequence,
                    context.execution_epoch,
                    run.fencing_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("lease compare-and-swap failed", code="LEASE_CONFLICT")
            self._append_audit_outbox(
                cursor,
                context,
                event_type="LEASE_ACQUIRED",
                subject_id=context.run_id,
                payload={"owner_id": owner_id, "fencing_generation": generation, "expires_at": expires_at},
            )
        return LeaseGrant(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id,
            owner_id=owner_id,
            execution_epoch=context.execution_epoch,
            fencing_generation=generation,
            token=token,
            expires_at=expires_at,
            sequence=sequence,
        )

    def _assert_lease_cursor(
        self,
        cursor: sqlite3.Cursor,
        context: SecurityContext,
        lease_token: str,
        *,
        now: datetime,
    ) -> RunSnapshot:
        if context.run_id is None:
            raise ValidationError("run-bound context is required")
        run = self._get_run_cursor(cursor, context, context.run_id)
        if run.execution_epoch != context.execution_epoch:
            raise ConflictError("execution epoch is stale", code="STALE_EPOCH")
        if run.fencing_generation != context.fencing_generation:
            raise ConflictError("fencing generation is stale", code="STALE_FENCE")
        row = cursor.execute(
            "SELECT lease_token_sha256 FROM runs WHERE tenant_id=? AND project_id=? AND run_id=?",
            (context.tenant_id, context.project_id, context.run_id),
        ).fetchone()
        supplied = digest_bytes(lease_token.encode("utf-8"), domain="lease-token")
        stored = str(row["lease_token_sha256"]) if row is not None else ""
        if row is None or not hmac.compare_digest(stored, supplied):
            raise AuthorizationError("lease token is invalid", code="LEASE_TOKEN_INVALID")
        if run.lease_expires_at is None or now >= run.lease_expires_at:
            raise ConflictError("lease is expired", code="LEASE_EXPIRED")
        return run

    def transition_run(
        self,
        context: SecurityContext,
        *,
        target_state: str,
        expected_sequence: int,
        lease_token: str,
        now: datetime | None = None,
    ) -> RunSnapshot:
        current_time = _aware(now or datetime.now(UTC))
        with self.transaction(context) as cursor:
            run = self._assert_lease_cursor(cursor, context, lease_token, now=current_time)
            if run.sequence != expected_sequence:
                raise ConflictError("optimistic sequence conflict", details={"expected": expected_sequence, "actual": run.sequence})
            sequence = run.sequence + 1
            cursor.execute(
                "UPDATE runs SET state=?,sequence=?,updated_at=? WHERE tenant_id=? AND project_id=? AND run_id=? AND sequence=? AND execution_epoch=? AND fencing_generation=?",
                (
                    target_state,
                    sequence,
                    _iso(current_time),
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    expected_sequence,
                    context.execution_epoch,
                    context.fencing_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("run transition compare-and-swap failed")
            self._append_audit_outbox(
                cursor,
                context,
                event_type="RUN_TRANSITIONED",
                subject_id=context.run_id or "",
                payload={"from": run.state, "to": target_state, "sequence": sequence},
            )
            return self._get_run_cursor(cursor, context, context.run_id or "")

    def append_checkpoint(
        self,
        context: SecurityContext,
        payload: bytes,
        *,
        expected_sequence: int,
        lease_token: str,
        checkpoint_id: str | None = None,
        now: datetime | None = None,
    ) -> CheckpointRecord:
        if not isinstance(payload, bytes) or not payload:
            raise ValidationError("checkpoint payload must be non-empty bytes")
        if len(payload) > MAX_INLINE_CHECKPOINT_BYTES:
            raise ValidationError(
                "checkpoint exceeds the inline storage limit",
                code="CHECKPOINT_TOO_LARGE",
                details={"maximum_bytes": MAX_INLINE_CHECKPOINT_BYTES},
            )
        checkpoint_id = checkpoint_id or f"checkpoint-{uuid.uuid4()}"
        current_time = _aware(now or datetime.now(UTC))
        payload_sha256 = digest_bytes(payload, domain="checkpoint")
        with self.transaction(context) as cursor:
            run = self._assert_lease_cursor(cursor, context, lease_token, now=current_time)
            if run.sequence != expected_sequence:
                raise ConflictError("optimistic sequence conflict", details={"expected": expected_sequence, "actual": run.sequence})
            sequence = run.sequence + 1
            cursor.execute(
                "INSERT INTO run_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    context.tenant_id,
                    context.project_id,
                    checkpoint_id,
                    context.run_id,
                    context.execution_epoch,
                    context.fencing_generation,
                    sequence,
                    payload_sha256,
                    sqlite3.Binary(payload),
                    _iso(current_time),
                ),
            )
            cursor.execute(
                "UPDATE runs SET state='CHECKPOINTED',sequence=?,last_checkpoint_id=?,updated_at=? WHERE tenant_id=? AND project_id=? AND run_id=? AND sequence=? AND execution_epoch=? AND fencing_generation=?",
                (
                    sequence,
                    checkpoint_id,
                    _iso(current_time),
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    expected_sequence,
                    context.execution_epoch,
                    context.fencing_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("checkpoint compare-and-swap failed")
            self._append_audit_outbox(
                cursor,
                context,
                event_type="RUN_CHECKPOINTED",
                subject_id=context.run_id or "",
                payload={"checkpoint_id": checkpoint_id, "sha256": payload_sha256, "sequence": sequence},
            )
        return CheckpointRecord(
            checkpoint_id=checkpoint_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id or "",
            execution_epoch=context.execution_epoch,
            fencing_generation=context.fencing_generation,
            sequence=sequence,
            payload_sha256=payload_sha256,
            created_at=current_time,
        )

    def get_checkpoint(self, context: SecurityContext, checkpoint_id: str) -> tuple[CheckpointRecord, bytes]:
        self.assert_scope(context)
        with self.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT * FROM run_checkpoints WHERE tenant_id=? AND project_id=? AND checkpoint_id=?",
                (context.tenant_id, context.project_id, checkpoint_id),
            ).fetchone()
            if row is not None:
                checkpoint_run_id = str(row["run_id"])
                if context.run_id is not None and context.run_id != checkpoint_run_id:
                    raise AuthorizationError("checkpoint belongs to another run", code="CHECKPOINT_SCOPE_MISMATCH")
                self._get_run_cursor(cursor, context, checkpoint_run_id)
        if row is None:
            raise NotFoundError("checkpoint was not found", details={"checkpoint_id": checkpoint_id})
        payload = bytes(row["payload_bytes"])
        verify_digest(payload, str(row["payload_sha256"]), domain="checkpoint")
        return (
            CheckpointRecord(
                checkpoint_id=str(row["checkpoint_id"]),
                tenant_id=str(row["tenant_id"]),
                project_id=str(row["project_id"]),
                run_id=str(row["run_id"]),
                execution_epoch=int(row["execution_epoch"]),
                fencing_generation=int(row["fencing_generation"]),
                sequence=int(row["sequence"]),
                payload_sha256=str(row["payload_sha256"]),
                created_at=_dt(str(row["created_at"])),
            ),
            payload,
        )

    def recover_run(
        self,
        context: SecurityContext,
        *,
        owner_id: str,
        expected_sequence: int,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> tuple[RunSnapshot, LeaseGrant, CheckpointRecord, bytes]:
        """Fence an expired worker and resume from byte-verified checkpoint.

        ``RESUMING`` and ``EXECUTING`` are recoverable only because the method
        already requires both a durable last checkpoint and an expired lease.
        This closes the crash windows immediately after reclaim and around the
        worker's checkpoint transitions without allowing takeover of live work.
        """

        if context.run_id is None:
            raise ValidationError("run-bound context is required")
        if ttl_seconds < 1 or ttl_seconds > 86_400:
            raise ValidationError("lease ttl is outside the safe range")
        current_time = _aware(now or datetime.now(UTC))
        token = secrets.token_urlsafe(32)
        expires_at = current_time + timedelta(seconds=ttl_seconds)
        with self.transaction(context) as cursor:
            run = self._get_run_cursor(cursor, context, context.run_id)
            if run.sequence != expected_sequence:
                raise ConflictError("optimistic sequence conflict", details={"expected": expected_sequence, "actual": run.sequence})
            if run.execution_epoch != context.execution_epoch:
                raise ConflictError("execution epoch is stale", code="STALE_EPOCH")
            if run.fencing_generation != context.fencing_generation:
                raise ConflictError("fencing generation is stale", code="STALE_FENCE")
            if run.state not in {"PAUSED", "CHECKPOINTED", "BLOCKED", "RESUMING", "EXECUTING"}:
                raise ConflictError("run state is not recoverable", code="RUN_NOT_RECOVERABLE", details={"state": run.state})
            if run.last_checkpoint_id is None:
                raise ConflictError("run has no checkpoint", code="CHECKPOINT_REQUIRED")
            if run.lease_expires_at is not None and current_time < run.lease_expires_at:
                raise ConflictError("active worker must be cancelled or expire before recovery", code="LEASE_HELD")
            checkpoint_row = cursor.execute(
                "SELECT * FROM run_checkpoints WHERE tenant_id=? AND project_id=? AND checkpoint_id=?",
                (context.tenant_id, context.project_id, run.last_checkpoint_id),
            ).fetchone()
            if checkpoint_row is None:
                raise IntegrityError("last checkpoint reference is broken", code="CHECKPOINT_MISSING")
            payload = bytes(checkpoint_row["payload_bytes"])
            verify_digest(payload, str(checkpoint_row["payload_sha256"]), domain="checkpoint")
            epoch = run.execution_epoch + 1
            fence = run.fencing_generation + 1
            sequence = run.sequence + 1
            token_sha256 = digest_bytes(token.encode("utf-8"), domain="lease-token")
            cursor.execute(
                "UPDATE runs SET state='RESUMING',sequence=?,execution_epoch=?,fencing_generation=?,lease_owner=?,lease_token_sha256=?,lease_expires_at=?,updated_at=? WHERE tenant_id=? AND project_id=? AND run_id=? AND sequence=? AND execution_epoch=? AND fencing_generation=?",
                (
                    sequence,
                    epoch,
                    fence,
                    owner_id,
                    token_sha256,
                    _iso(expires_at),
                    _iso(current_time),
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    expected_sequence,
                    run.execution_epoch,
                    run.fencing_generation,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("recovery compare-and-swap failed")
            recovery_context = context.for_run(context.run_id, execution_epoch=epoch, fencing_generation=fence)
            self._append_audit_outbox(
                cursor,
                recovery_context,
                event_type="RUN_RECOVERING",
                subject_id=context.run_id,
                payload={"checkpoint_id": run.last_checkpoint_id, "execution_epoch": epoch, "fencing_generation": fence},
            )
            snapshot = self._get_run_cursor(cursor, recovery_context, context.run_id)
        checkpoint = CheckpointRecord(
            checkpoint_id=str(checkpoint_row["checkpoint_id"]),
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id,
            execution_epoch=int(checkpoint_row["execution_epoch"]),
            fencing_generation=int(checkpoint_row["fencing_generation"]),
            sequence=int(checkpoint_row["sequence"]),
            payload_sha256=str(checkpoint_row["payload_sha256"]),
            created_at=_dt(str(checkpoint_row["created_at"])),
        )
        grant = LeaseGrant(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id,
            owner_id=owner_id,
            execution_epoch=epoch,
            fencing_generation=fence,
            token=token,
            expires_at=expires_at,
            sequence=sequence,
        )
        return snapshot, grant, checkpoint, payload

    # ---- Side effects and reconciliation ------------------------------

    def start_external_effect(
        self,
        context: SecurityContext,
        *,
        effect_id: str,
        provider: str,
        operation: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        reconciliation_strategy: str,
        lease_token: str,
        now: datetime | None = None,
    ) -> ReconciliationRecord:
        self.assert_scope(context)
        if context.run_id is None or not all((effect_id, provider, operation, idempotency_key, reconciliation_strategy)):
            raise ValidationError("external effect bindings are incomplete")
        request_sha256 = digest_object(request, domain="external-effect-request")
        current_time = _aware(now or datetime.now(UTC))
        timestamp = _iso(current_time)
        with self.transaction(context) as cursor:
            run = self._assert_lease_cursor(cursor, context, lease_token, now=current_time)
            if run.state not in _SIDE_EFFECT_START_STATES:
                raise ConflictError(
                    "run state does not permit a new external effect",
                    code="RUN_STATE_FORBIDS_SIDE_EFFECT",
                    details={"state": run.state},
                )
            existing = cursor.execute(
                "SELECT * FROM external_effects WHERE tenant_id=? AND project_id=? AND provider=? AND operation=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, provider, operation, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["run_id"] != context.run_id or existing["actor_id"] != context.actor_id:
                    raise AuthorizationError("external idempotency receipt belongs to another run or actor")
                if existing["request_sha256"] != request_sha256:
                    raise ConflictError("external idempotency key was reused", code="IDEMPOTENCY_CONFLICT")
                return self._effect_record(existing)
            cursor.execute(
                "INSERT INTO external_effects VALUES (?,?,?,?,?,?,?,?,?,?,?,'STARTED',NULL,?,0,?,?)",
                (
                    context.tenant_id,
                    context.project_id,
                    effect_id,
                    context.run_id,
                    context.actor_id,
                    run.execution_epoch,
                    run.fencing_generation,
                    provider,
                    operation,
                    idempotency_key,
                    request_sha256,
                    reconciliation_strategy,
                    timestamp,
                    timestamp,
                ),
            )
            self._append_effect_event(cursor, context, effect_id, "STARTED", {"request_sha256": request_sha256}, timestamp)
            self._append_audit_outbox(
                cursor,
                context,
                event_type="EXTERNAL_EFFECT_STARTED",
                subject_id=effect_id,
                payload={"provider": provider, "operation": operation, "request_sha256": request_sha256},
            )
            row = cursor.execute(
                "SELECT * FROM external_effects WHERE tenant_id=? AND project_id=? AND effect_id=?",
                (context.tenant_id, context.project_id, effect_id),
            ).fetchone()
            assert row is not None
            return self._effect_record(row)

    def reconcile_external_effect(
        self,
        context: SecurityContext,
        *,
        effect_id: str,
        target_state: str,
        expected_version: int,
        detail: Mapping[str, Any],
        lease_token: str,
        external_reference: str | None = None,
        now: datetime | None = None,
    ) -> ReconciliationRecord:
        allowed = {"SUCCEEDED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "UNKNOWN_RESULT", "RECONCILED"}
        if target_state not in allowed:
            raise ValidationError("invalid reconciliation state")
        current_time = _aware(now or datetime.now(UTC))
        timestamp = _iso(current_time)
        with self.transaction(context) as cursor:
            run = self._assert_lease_cursor(cursor, context, lease_token, now=current_time)
            row = cursor.execute(
                "SELECT * FROM external_effects WHERE tenant_id=? AND project_id=? AND effect_id=?",
                (context.tenant_id, context.project_id, effect_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("external effect was not found")
            if row["run_id"] != run.run_id or row["actor_id"] != context.actor_id:
                raise AuthorizationError("external effect belongs to another run or actor")
            if int(row["version"]) != expected_version:
                raise ConflictError("reconciliation version conflict")
            current_state = str(row["state"])
            if target_state not in _EFFECT_TRANSITIONS.get(current_state, frozenset()):
                raise ConflictError(
                    "invalid external effect state transition",
                    code="RECONCILIATION_TRANSITION_INVALID",
                    details={"source": current_state, "target": target_state},
                )
            version = expected_version + 1
            cursor.execute(
                "UPDATE external_effects SET state=?,external_reference=?,version=?,updated_at=? WHERE tenant_id=? AND project_id=? AND effect_id=? AND version=?",
                (
                    target_state,
                    external_reference,
                    version,
                    timestamp,
                    context.tenant_id,
                    context.project_id,
                    effect_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("reconciliation compare-and-swap failed")
            self._append_effect_event(cursor, context, effect_id, target_state, detail, timestamp)
            self._append_audit_outbox(
                cursor,
                context,
                event_type="EXTERNAL_EFFECT_RECONCILED",
                subject_id=effect_id,
                payload={"state": target_state, "version": version, "external_reference": external_reference},
            )
            updated = cursor.execute(
                "SELECT * FROM external_effects WHERE tenant_id=? AND project_id=? AND effect_id=?",
                (context.tenant_id, context.project_id, effect_id),
            ).fetchone()
            assert updated is not None
            return self._effect_record(updated)

    def _append_effect_event(
        self,
        cursor: sqlite3.Cursor,
        context: SecurityContext,
        effect_id: str,
        state: str,
        detail: Mapping[str, Any],
        timestamp: str,
    ) -> None:
        cursor.execute(
            "INSERT INTO effect_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                context.tenant_id,
                context.project_id,
                f"effect-event-{uuid.uuid4()}",
                effect_id,
                state,
                canonical_json(detail),
                timestamp,
            ),
        )

    @staticmethod
    def _effect_record(row: sqlite3.Row) -> ReconciliationRecord:
        return ReconciliationRecord(
            effect_id=str(row["effect_id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["run_id"]),
            provider=str(row["provider"]),
            operation=str(row["operation"]),
            idempotency_key=str(row["idempotency_key"]),
            request_sha256=str(row["request_sha256"]),
            state=str(row["state"]),
            external_reference=str(row["external_reference"]) if row["external_reference"] is not None else None,
            version=int(row["version"]),
            execution_epoch=int(row["execution_epoch"]),
            fencing_generation=int(row["fencing_generation"]),
        )

    def unsettled_side_effect_count(self, context: SecurityContext, *, run_id: str | None = None) -> int:
        self.assert_scope(context)
        query = "SELECT COUNT(*) AS count FROM external_effects WHERE tenant_id=? AND project_id=? AND state NOT IN ('RECONCILED','FAILED_TERMINAL')"
        params: list[Any] = [context.tenant_id, context.project_id]
        selected = run_id or context.run_id
        if selected is not None:
            query += " AND run_id=?"
            params.append(selected)
        with self.transaction(context) as cursor:
            if selected is not None:
                self._get_run_cursor(cursor, context, selected)
            row = cursor.execute(query, params).fetchone()
        return int(row["count"])

    # ---- Append-only outbox delivery and metrics ----------------------

    def record_outbox_delivery(
        self,
        context: SecurityContext,
        *,
        event_id: str,
        destination: str,
        state: str,
        detail: bytes | None = None,
    ) -> str:
        self.assert_scope(context)
        delivery_id = f"delivery-{uuid.uuid4()}"
        detail_sha256 = digest_bytes(detail, domain="outbox-delivery") if detail is not None else None
        with self.transaction(context) as cursor:
            try:
                cursor.execute(
                    "INSERT INTO outbox_deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        delivery_id,
                        event_id,
                        destination,
                        state,
                        detail_sha256,
                        _iso(datetime.now(UTC)),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise NotFoundError("outbox event was not found") from exc
        return delivery_id

    def record_metric(self, context: SecurityContext, point: MetricPoint) -> str:
        self.assert_scope(context)
        metric_id = f"metric-{uuid.uuid4()}"
        with self.transaction(context) as cursor:
            cursor.execute(
                "INSERT INTO metric_points VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    context.tenant_id,
                    context.project_id,
                    metric_id,
                    point.name,
                    point.value,
                    canonical_json(point.labels),
                    _iso(point.occurred_at),
                ),
            )
        return metric_id

    def metric_totals(self, context: SecurityContext) -> dict[str, float]:
        self.assert_scope(context)
        with self.transaction(context) as cursor:
            rows = cursor.execute(
                "SELECT name, SUM(value) AS total FROM metric_points WHERE tenant_id=? AND project_id=? GROUP BY name ORDER BY name",
                (context.tenant_id, context.project_id),
            ).fetchall()
        return {str(row["name"]): float(row["total"]) for row in rows}

    # ---- Durable HTTP/control-plane idempotency ----------------------

    @staticmethod
    def _control_plane_receipt(row: Mapping[str, Any]) -> ControlPlaneReceipt:
        request = json.loads(str(row["request_json"]))
        response = json.loads(str(row["response_json"])) if row["response_json"] is not None else None
        if not isinstance(request, dict) or (response is not None and not isinstance(response, dict)):
            raise IntegrityError("control-plane receipt payload is invalid", code="RECEIPT_INVALID")
        return ControlPlaneReceipt(
            actor_id=str(row["actor_id"]),
            operation=str(row["operation"]),
            idempotency_key=str(row["idempotency_key"]),
            request_sha256=str(row["request_sha256"]),
            run_id=str(row["run_id"]),
            request=request,
            response=response,
            created_at=_dt(str(row["created_at"])),
            completed_at=_dt(str(row["completed_at"])) if row["completed_at"] is not None else None,
        )

    def claim_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
        run_id: str,
        request: Mapping[str, Any],
        now: datetime | None = None,
    ) -> tuple[bool, ControlPlaneReceipt]:
        self.assert_scope(context)
        if not all((operation.strip(), idempotency_key.strip(), request_sha256, run_id.strip())):
            raise ValidationError("control-plane receipt binding is incomplete")
        timestamp = _iso(_aware(now or datetime.now(UTC)))
        with self.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT * FROM control_plane_receipts WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, operation, idempotency_key),
            ).fetchone()
            if row is not None:
                receipt = self._control_plane_receipt(row)
                if receipt.actor_id != context.actor_id:
                    raise AuthorizationError(
                        "idempotency receipt belongs to another actor",
                        code="IDEMPOTENCY_SCOPE_MISMATCH",
                    )
                if receipt.request_sha256 != request_sha256:
                    raise ConflictError(
                        "idempotency key was reused with a different request",
                        code="IDEMPOTENCY_CONFLICT",
                    )
                return False, receipt
            cursor.execute(
                "INSERT INTO control_plane_receipts VALUES (?,?,?,?,?,?,?,?,NULL,?,NULL)",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    operation,
                    idempotency_key,
                    request_sha256,
                    run_id,
                    canonical_json(request),
                    timestamp,
                ),
            )
            created = cursor.execute(
                "SELECT * FROM control_plane_receipts WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, operation, idempotency_key),
            ).fetchone()
            assert created is not None
            return True, self._control_plane_receipt(created)

    def complete_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
        response: Mapping[str, Any],
        now: datetime | None = None,
    ) -> ControlPlaneReceipt:
        self.assert_scope(context)
        timestamp = _iso(_aware(now or datetime.now(UTC)))
        with self.transaction(context) as cursor:
            cursor.execute(
                "UPDATE control_plane_receipts SET response_json=?,completed_at=? WHERE tenant_id=? AND project_id=? AND actor_id=? AND operation=? AND idempotency_key=? AND request_sha256=? AND response_json IS NULL",
                (
                    canonical_json(response),
                    timestamp,
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    operation,
                    idempotency_key,
                    request_sha256,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("control-plane receipt completion conflict", code="RECEIPT_COMPLETION_CONFLICT")
            row = cursor.execute(
                "SELECT * FROM control_plane_receipts WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, operation, idempotency_key),
            ).fetchone()
            assert row is not None
            return self._control_plane_receipt(row)

    def get_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
    ) -> ControlPlaneReceipt | None:
        self.assert_scope(context)
        with self.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT * FROM control_plane_receipts WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=?",
                (context.tenant_id, context.project_id, operation, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        receipt = self._control_plane_receipt(row)
        if receipt.actor_id != context.actor_id:
            raise AuthorizationError("idempotency receipt belongs to another actor", code="IDEMPOTENCY_SCOPE_MISMATCH")
        if receipt.request_sha256 != request_sha256:
            raise ConflictError("idempotency key was reused with a different request", code="IDEMPOTENCY_CONFLICT")
        return receipt

    def abandon_control_plane_receipt(
        self,
        context: SecurityContext,
        *,
        operation: str,
        idempotency_key: str,
        request_sha256: str,
    ) -> bool:
        """Remove only an incomplete claim so a failed pre-run request can retry."""

        self.assert_scope(context)
        with self.transaction(context) as cursor:
            cursor.execute(
                "DELETE FROM control_plane_receipts WHERE tenant_id=? AND project_id=? AND actor_id=? AND operation=? AND idempotency_key=? AND request_sha256=? AND response_json IS NULL",
                (
                    context.tenant_id,
                    context.project_id,
                    context.actor_id,
                    operation,
                    idempotency_key,
                    request_sha256,
                ),
            )
            return cursor.rowcount == 1

    def list_pending_control_plane_receipts(
        self,
        context: SecurityContext,
        *,
        limit: int = 100,
    ) -> tuple[ControlPlaneReceipt, ...]:
        """List restart-reconcilable claims only inside one trusted scope.

        This is intentionally not a global queue scan.  A scheduler supplies
        an authenticated tenant/project/actor scope, then competes for the
        run's recovery lease; epoch/fence CAS decides the sole winner.
        """

        self.assert_scope(context)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValidationError("pending receipt limit is outside the safe range")
        with self.transaction(context) as cursor:
            rows = cursor.execute(
                "SELECT * FROM control_plane_receipts WHERE tenant_id=? AND project_id=? AND actor_id=? AND response_json IS NULL ORDER BY created_at,operation,idempotency_key LIMIT ?",
                (context.tenant_id, context.project_id, context.actor_id, limit),
            ).fetchall()
        return tuple(self._control_plane_receipt(row) for row in rows)

    def claim_next_control_plane_job(
        self,
        *,
        worker_instance_id: str,
        ttl_seconds: int = 60,
        now: datetime | None = None,
    ) -> ControlPlaneJobClaim | None:
        """Claim one global job in the single-process local SQLite backend.

        This method is intentionally local-engineering only.  Production uses
        :class:`PostgresScheduler`, whose SECURITY DEFINER function and
        independent DSN avoid granting the HTTP role any global table access.
        """

        if not isinstance(worker_instance_id, str) or not worker_instance_id.strip():
            raise ValidationError("worker_instance_id is required")
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValidationError("scheduler lease ttl is outside the safe range")
        current = _aware(now or datetime.now(UTC))
        expires = current + timedelta(seconds=ttl_seconds)
        timestamp = _iso(current)
        token = secrets.token_urlsafe(32)
        token_digest = digest_bytes(token.encode("utf-8"), domain="scheduler-lease-token")
        with self.transaction() as cursor:
            row = cursor.execute(
                "SELECT job.*,receipt.request_json FROM scheduler_jobs job "
                "JOIN control_plane_receipts receipt USING(tenant_id,project_id,operation,idempotency_key) "
                "WHERE receipt.response_json IS NULL AND (job.state='PENDING' OR "
                "(job.state='CLAIMED' AND job.lease_expires_at<=?)) "
                "ORDER BY job.created_at,job.tenant_id,job.project_id,job.operation,job.idempotency_key LIMIT 1",
                (timestamp,),
            ).fetchone()
            if row is None:
                return None
            generation = int(row["lease_generation"]) + 1
            cursor.execute(
                "UPDATE scheduler_jobs SET state='CLAIMED',scheduler_role='sqlite-local-scheduler',"
                "worker_instance_id=?,lease_token_sha256=?,lease_generation=?,lease_expires_at=?,updated_at=? "
                "WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=? "
                "AND lease_generation=? AND (state='PENDING' OR (state='CLAIMED' AND lease_expires_at<=?))",
                (
                    worker_instance_id,
                    token_digest,
                    generation,
                    _iso(expires),
                    timestamp,
                    str(row["tenant_id"]),
                    str(row["project_id"]),
                    str(row["operation"]),
                    str(row["idempotency_key"]),
                    int(row["lease_generation"]),
                    timestamp,
                ),
            )
            if cursor.rowcount != 1:
                raise ConflictError("scheduler job claim compare-and-swap failed")
            cursor.execute(
                "INSERT INTO scheduler_claim_events VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    f"scheduler-event-{uuid.uuid4()}",
                    str(row["tenant_id"]),
                    str(row["project_id"]),
                    str(row["operation"]),
                    str(row["idempotency_key"]),
                    "sqlite-local-scheduler",
                    worker_instance_id,
                    generation,
                    timestamp,
                ),
            )
        request = json.loads(str(row["request_json"]))
        if not isinstance(request, dict):
            raise IntegrityError("scheduled control-plane request is invalid")
        return ControlPlaneJobClaim(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            actor_id=str(row["actor_id"]),
            operation=str(row["operation"]),
            idempotency_key=str(row["idempotency_key"]),
            request_sha256=str(row["request_sha256"]),
            run_id=str(row["run_id"]),
            request=request,
            scheduler_role="sqlite-local-scheduler",
            worker_instance_id=worker_instance_id,
            lease_token=token,
            lease_generation=generation,
            lease_expires_at=expires,
        )

    def count_rows(self, context: SecurityContext, table: str) -> int:
        """Test/diagnostic count over an allowlisted tenant-qualified table."""

        allowed = {
            "evidence",
            "evidence_revocations",
            "audit_events",
            "outbox_events",
            "outbox_deliveries",
            "run_checkpoints",
            "external_effects",
            "effect_events",
            "metric_points",
            "idempotency_receipts",
            "control_plane_receipts",
        }
        if table not in allowed:
            raise ValidationError("table is not available for diagnostics")
        self.assert_scope(context)
        with self.transaction(context) as cursor:
            row = cursor.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE tenant_id=? AND project_id=?",
                (context.tenant_id, context.project_id),
            ).fetchone()
        return int(row["count"])
