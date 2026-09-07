"""Durable, resource-scoped persistence for the PDHI local runtime.

SQLite is intentionally a local engineering backend.  It provides real crash
recovery, fencing, idempotency, audit and outbox semantics without pretending
to be a multi-replica production database.  Production deployments use the
same public contract through a PostgreSQL adapter with forced RLS.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import secrets
import sqlite3
import threading
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence
import unicodedata


SCHEMA_VERSION = 2
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_TEXT_LENGTH = 1024


class StoreError(RuntimeError):
    """Base class for durable-store failures."""


class ScopeViolation(StoreError):
    """The authenticated tenant/project scope is unknown or mismatched."""


class IdempotencyConflict(StoreError):
    """An idempotency key was reused for different canonical input."""


class OptimisticConflict(StoreError):
    """The caller used a stale aggregate version."""


class InvalidTransition(StoreError):
    """A requested lifecycle transition is not permitted."""


class LeaseConflict(StoreError):
    """A live lease is owned by another worker or has a stale fence."""


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StoreError(f"{field} is required")
    if value != value.strip() or unicodedata.normalize("NFC", value) != value:
        raise StoreError(f"{field} must use canonical text")
    if len(value) > MAX_TEXT_LENGTH:
        raise StoreError(f"{field} is too long")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise StoreError(f"{field} contains control characters")
    return value


def _utc(value: datetime | None = None) -> datetime:
    current = datetime.now(UTC) if value is None else value
    if current.tzinfo is None or current.utcoffset() is None:
        raise StoreError("timestamp must be timezone-aware")
    return current.astimezone(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value).astimezone(UTC)


def _json_shape(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StoreError("non-finite JSON number")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise StoreError("non-finite decimal")
        return format(value, "f")
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise StoreError("JSON objects require string keys")
        return {key: _json_shape(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_json_shape(item) for item in value]
    raise StoreError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    encoded = json.dumps(
        _json_shape(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise StoreError("JSON payload exceeds local durable-store limit")
    return encoded


def digest(value: Any, *, domain: str) -> str:
    body = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(domain.encode("utf-8") + b"\x00" + body).hexdigest()


def _sha256(value: str | None, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    checked = _text(value, field)
    raw = checked.removeprefix("sha256:")
    if len(raw) != 64 or raw.lower() != raw:
        raise StoreError(f"{field} must be a canonical SHA-256 digest")
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise StoreError(f"{field} must be a canonical SHA-256 digest") from exc
    return "sha256:" + raw


@dataclass(frozen=True, slots=True)
class ScopeBinding:
    tenant_id: str
    project_id: str
    actor_id: str
    authority_revision: str
    environment_revision: str

    def __post_init__(self) -> None:
        for field in ("tenant_id", "project_id", "actor_id", "authority_revision", "environment_revision"):
            _text(getattr(self, field), field)
        for field in ("authority_revision", "environment_revision"):
            value = getattr(self, field)
            raw = value.removeprefix("sha256:")
            if len(raw) != 64 or raw.lower() != raw:
                raise StoreError(f"{field} must be a canonical SHA-256 digest")
            try:
                bytes.fromhex(raw)
            except ValueError as exc:
                raise StoreError(f"{field} must be a canonical SHA-256 digest") from exc


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    created: bool
    in_progress: bool
    response: Mapping[str, Any] | None
    request_digest: str


@dataclass(frozen=True, slots=True)
class LeaseGrant:
    resource_id: str
    owner_id: str
    generation: int
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class EffectRecord:
    effect_id: str
    job_id: str
    operation: str
    state: str
    request_digest: str
    response: Mapping[str, Any] | None
    lease_resource: str
    lease_generation: int
    version: int


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    event_id: int
    topic: str
    aggregate_id: str
    payload: Mapping[str, Any]
    delivery_token: str
    attempts: int


JOB_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "QUEUED": frozenset({"PREFLIGHT", "PAUSED", "CANCELLED", "FAILED"}),
    "PREFLIGHT": frozenset({"PLANNING", "BLOCKED", "PAUSED", "CANCELLED", "FAILED"}),
    "PLANNING": frozenset({"EXECUTING", "BLOCKED", "PAUSED", "CANCELLED", "FAILED"}),
    "EXECUTING": frozenset({"VERIFYING", "BLOCKED", "PAUSED", "RETRYING", "ROLLING_BACK", "CANCELLED", "FAILED"}),
    "VERIFYING": frozenset({"CERTIFYING", "EXECUTING", "BLOCKED", "PAUSED", "ROLLING_BACK", "FAILED"}),
    "CERTIFYING": frozenset({"READY_TO_RELEASE", "BLOCKED", "FAILED"}),
    "READY_TO_RELEASE": frozenset({"RELEASED", "BLOCKED", "CANCELLED"}),
    "PAUSED": frozenset({"PREFLIGHT", "PLANNING", "EXECUTING", "VERIFYING", "CANCELLED"}),
    "BLOCKED": frozenset({"PREFLIGHT", "PLANNING", "EXECUTING", "VERIFYING", "CANCELLED", "FAILED"}),
    "RETRYING": frozenset({"EXECUTING", "VERIFYING", "BLOCKED", "FAILED"}),
    "ROLLING_BACK": frozenset({"FAILED", "CANCELLED", "QUARANTINED"}),
    "FAILED": frozenset({"RETRYING", "ROLLING_BACK", "QUARANTINED"}),
    "RELEASED": frozenset(),
    "CANCELLED": frozenset(),
    "QUARANTINED": frozenset(),
}

EFFECT_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "PREPARED": frozenset({"STARTED", "CANCELLED"}),
    "STARTED": frozenset({"SUCCEEDED", "FAILED", "UNKNOWN"}),
    "UNKNOWN": frozenset({"SUCCEEDED", "FAILED", "COMPENSATED"}),
    "SUCCEEDED": frozenset({"COMPENSATING"}),
    "COMPENSATING": frozenset({"COMPENSATED", "UNKNOWN", "FAILED"}),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
    "COMPENSATED": frozenset(),
}

AGENT_COMMAND_STATES: Mapping[str, Mapping[str, str]] = {
    "REGISTER": MappingProxyType({"ABSENT": "RUNNING"}),
    "STEER": MappingProxyType({"RUNNING": "RUNNING", "PAUSED": "PAUSED"}),
    "PAUSE": MappingProxyType({"RUNNING": "PAUSED"}),
    "RESUME": MappingProxyType({"PAUSED": "RUNNING"}),
    "KILL": MappingProxyType({"RUNNING": "KILLED", "PAUSED": "KILLED"}),
    "REVIVE": MappingProxyType({"KILLED": "RUNNING", "FAILED": "RUNNING"}),
    "FAIL": MappingProxyType({"RUNNING": "FAILED", "PAUSED": "FAILED"}),
    "COMPLETE": MappingProxyType({"RUNNING": "SUCCEEDED"}),
}

SESSION_COMMAND_STATES: Mapping[str, Mapping[str, str]] = {
    "REGISTER": MappingProxyType({"ABSENT": "ACTIVE"}),
    "CHECKPOINT": MappingProxyType({"ACTIVE": "ACTIVE"}),
    "ROTATE": MappingProxyType({"ACTIVE": "ROTATED", "STALE": "ROTATED"}),
    "RESET": MappingProxyType({"ACTIVE": "RESET_REQUIRED", "STALE": "RESET_REQUIRED"}),
    "MARK_STALE": MappingProxyType({"ACTIVE": "STALE"}),
    "CLOSE": MappingProxyType({"ACTIVE": "CLOSED", "STALE": "CLOSED", "RESET_REQUIRED": "CLOSED"}),
}


class SqlitePdhiStore:
    """Crash-durable single-node implementation with exact scope checks."""

    def __init__(self, database: str | Path) -> None:
        raw = str(database)
        if not raw:
            raise StoreError("database path is required")
        self._database = raw
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(raw, isolation_level=None, check_same_thread=False, timeout=30)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._connection.execute("PRAGMA synchronous = FULL")
        if raw != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    def _migrate(self) -> None:
        statements = (
            "CREATE TABLE IF NOT EXISTS pdhi_schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
            """CREATE TABLE IF NOT EXISTS pdhi_scopes(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, project_id))""",
            """CREATE TABLE IF NOT EXISTS pdhi_jobs(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
                actor_id TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL,
                input_revision TEXT NOT NULL, authority_revision TEXT NOT NULL,
                environment_revision TEXT NOT NULL, payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, project_id, job_id),
                FOREIGN KEY(tenant_id, project_id) REFERENCES pdhi_scopes(tenant_id, project_id))""",
            """CREATE TABLE IF NOT EXISTS pdhi_idempotency(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL,
                status TEXT NOT NULL, response_json TEXT, created_at TEXT NOT NULL, completed_at TEXT,
                PRIMARY KEY(tenant_id, project_id, operation, idempotency_key))""",
            """CREATE TABLE IF NOT EXISTS pdhi_leases(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, resource_id TEXT NOT NULL,
                owner_id TEXT NOT NULL, token_digest TEXT NOT NULL, generation INTEGER NOT NULL,
                state TEXT NOT NULL, expires_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, project_id, resource_id))""",
            """CREATE TABLE IF NOT EXISTS pdhi_effects(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, effect_id TEXT NOT NULL,
                job_id TEXT NOT NULL, operation TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL, request_json TEXT NOT NULL, state TEXT NOT NULL,
                response_json TEXT, lease_resource TEXT NOT NULL, lease_generation INTEGER NOT NULL,
                version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, project_id, effect_id),
                UNIQUE(tenant_id, project_id, operation, idempotency_key))""",
            """CREATE TABLE IF NOT EXISTS pdhi_outbox(
                event_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
                topic TEXT NOT NULL, aggregate_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, available_at TEXT NOT NULL,
                claimed_by TEXT, claimed_until TEXT, delivery_token_digest TEXT,
                created_at TEXT NOT NULL, delivered_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS pdhi_audit(
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
                actor_id TEXT NOT NULL, operation TEXT NOT NULL, aggregate_id TEXT NOT NULL,
                decision TEXT NOT NULL, detail_json TEXT NOT NULL, occurred_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS pdhi_metrics(
                metric_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
                job_id TEXT NOT NULL, metric_name TEXT NOT NULL, value_decimal TEXT NOT NULL,
                unit TEXT NOT NULL, currency TEXT, grain TEXT NOT NULL, definition_version TEXT NOT NULL,
                observed_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS pdhi_agent_controls(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
                agent_id TEXT NOT NULL, state TEXT NOT NULL, generation INTEGER NOT NULL,
                command_json TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, project_id, job_id, agent_id))""",
            """CREATE TABLE IF NOT EXISTS pdhi_provider_sessions(
                tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
                session_id TEXT NOT NULL, provider_id TEXT NOT NULL, state TEXT NOT NULL,
                generation INTEGER NOT NULL, external_ref_digest TEXT,
                checkpoint_digest TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY(tenant_id, project_id, job_id, session_id))""",
            "CREATE INDEX IF NOT EXISTS pdhi_jobs_state_idx ON pdhi_jobs(state, updated_at)",
            "CREATE INDEX IF NOT EXISTS pdhi_outbox_ready_idx ON pdhi_outbox(state, available_at, event_id)",
            "CREATE INDEX IF NOT EXISTS pdhi_audit_scope_idx ON pdhi_audit(tenant_id, project_id, audit_id)",
            "CREATE INDEX IF NOT EXISTS pdhi_metrics_rollup_idx ON pdhi_metrics(tenant_id, project_id, job_id, metric_name)",
        )
        with self._transaction() as connection:
            for statement in statements:
                connection.execute(statement)
            row = connection.execute("SELECT MAX(version) AS version FROM pdhi_schema_version").fetchone()
            version = None if row is None else row["version"]
            if version is None:
                connection.execute(
                    "INSERT INTO pdhi_schema_version(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _timestamp()),
                )
            elif int(version) == 1 and SCHEMA_VERSION == 2:
                connection.execute(
                    "INSERT INTO pdhi_schema_version(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, _timestamp()),
                )
            elif int(version) != SCHEMA_VERSION:
                raise StoreError(f"unsupported PDHI schema version: {version}")

    def _assert_scope(self, connection: sqlite3.Connection, scope: ScopeBinding) -> None:
        row = connection.execute(
            "SELECT 1 FROM pdhi_scopes WHERE tenant_id = ? AND project_id = ?",
            (scope.tenant_id, scope.project_id),
        ).fetchone()
        if row is None:
            raise ScopeViolation("tenant/project scope is not registered")

    def register_scope(self, scope: ScopeBinding, *, now: datetime | None = None) -> None:
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO pdhi_scopes(tenant_id, project_id, created_at) VALUES (?, ?, ?)",
                (scope.tenant_id, scope.project_id, _timestamp(now)),
            )
            self._audit(connection, scope, "scope.register", scope.project_id, "ALLOW", {})

    def _audit(
        self,
        connection: sqlite3.Connection,
        scope: ScopeBinding,
        operation: str,
        aggregate_id: str,
        decision: str,
        detail: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO pdhi_audit(
                tenant_id, project_id, actor_id, operation, aggregate_id, decision, detail_json, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scope.tenant_id,
                scope.project_id,
                scope.actor_id,
                _text(operation, "operation"),
                _text(aggregate_id, "aggregate_id"),
                _text(decision, "decision"),
                canonical_json(detail),
                _timestamp(now),
            ),
        )

    def _outbox(
        self,
        connection: sqlite3.Connection,
        scope: ScopeBinding,
        topic: str,
        aggregate_id: str,
        payload: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> None:
        timestamp = _timestamp(now)
        connection.execute(
            """INSERT INTO pdhi_outbox(
                tenant_id, project_id, topic, aggregate_id, payload_json, state, available_at, created_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
            (
                scope.tenant_id,
                scope.project_id,
                _text(topic, "topic"),
                _text(aggregate_id, "aggregate_id"),
                canonical_json(payload),
                timestamp,
                timestamp,
            ),
        )

    def reserve_idempotency(
        self,
        scope: ScopeBinding,
        *,
        operation: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        now: datetime | None = None,
    ) -> IdempotencyReservation:
        operation = _text(operation, "operation")
        idempotency_key = _text(idempotency_key, "idempotency_key")
        request_digest = digest(request, domain=f"pdhi-idempotency:{operation}")
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            row = connection.execute(
                """SELECT request_digest, status, response_json FROM pdhi_idempotency
                   WHERE tenant_id = ? AND project_id = ? AND operation = ? AND idempotency_key = ?""",
                (scope.tenant_id, scope.project_id, operation, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict("idempotency key request digest mismatch")
                response = None if row["response_json"] is None else json.loads(row["response_json"])
                return IdempotencyReservation(False, row["status"] == "PENDING", response, request_digest)
            connection.execute(
                """INSERT INTO pdhi_idempotency(
                    tenant_id, project_id, operation, idempotency_key, request_digest, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'PENDING', ?)""",
                (scope.tenant_id, scope.project_id, operation, idempotency_key, request_digest, _timestamp(now)),
            )
            self._audit(connection, scope, operation, idempotency_key, "RESERVED", {"request_digest": request_digest})
            return IdempotencyReservation(True, False, None, request_digest)

    def complete_idempotency(
        self,
        scope: ScopeBinding,
        *,
        operation: str,
        idempotency_key: str,
        request_digest: str,
        response: Mapping[str, Any],
        now: datetime | None = None,
    ) -> None:
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            cursor = connection.execute(
                """UPDATE pdhi_idempotency SET status = 'COMPLETED', response_json = ?, completed_at = ?
                   WHERE tenant_id = ? AND project_id = ? AND operation = ? AND idempotency_key = ?
                     AND request_digest = ? AND status = 'PENDING'""",
                (
                    canonical_json(response),
                    _timestamp(now),
                    scope.tenant_id,
                    scope.project_id,
                    _text(operation, "operation"),
                    _text(idempotency_key, "idempotency_key"),
                    _text(request_digest, "request_digest"),
                ),
            )
            if cursor.rowcount != 1:
                raise IdempotencyConflict("idempotency reservation is missing, stale, or already completed")
            self._audit(connection, scope, operation, idempotency_key, "COMPLETED", {"request_digest": request_digest})

    def create_job(
        self,
        scope: ScopeBinding,
        *,
        job_id: str,
        input_revision: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        job_id = _text(job_id, "job_id")
        input_revision = _text(input_revision, "input_revision")
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            try:
                connection.execute(
                    """INSERT INTO pdhi_jobs(
                        tenant_id, project_id, job_id, actor_id, state, version, input_revision,
                        authority_revision, environment_revision, payload_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'QUEUED', 1, ?, ?, ?, ?, ?, ?)""",
                    (
                        scope.tenant_id,
                        scope.project_id,
                        job_id,
                        scope.actor_id,
                        input_revision,
                        scope.authority_revision,
                        scope.environment_revision,
                        canonical_json(payload),
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise OptimisticConflict("job already exists in this tenant/project") from exc
            self._audit(connection, scope, "job.create", job_id, "ALLOW", {"state": "QUEUED", "version": 1})
            self._outbox(
                connection,
                scope,
                "pdhi.job.created",
                job_id,
                {"job_id": job_id, "state": "QUEUED", "version": 1},
                now=now,
            )
        return self.get_job(scope, job_id)

    def get_job(self, scope: ScopeBinding, job_id: str) -> Mapping[str, Any]:
        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM pdhi_jobs WHERE tenant_id = ? AND project_id = ? AND job_id = ?""",
                (scope.tenant_id, scope.project_id, _text(job_id, "job_id")),
            ).fetchone()
        if row is None:
            raise ScopeViolation("job is unavailable in authenticated scope")
        return {
            "tenant_id": row["tenant_id"],
            "project_id": row["project_id"],
            "job_id": row["job_id"],
            "actor_id": row["actor_id"],
            "state": row["state"],
            "version": int(row["version"]),
            "input_revision": row["input_revision"],
            "authority_revision": row["authority_revision"],
            "environment_revision": row["environment_revision"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def transition_job(
        self,
        scope: ScopeBinding,
        *,
        job_id: str,
        expected_version: int,
        target_state: str,
        reason: str,
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        job_id = _text(job_id, "job_id")
        target_state = _text(target_state, "target_state")
        reason = _text(reason, "reason")
        if expected_version < 1:
            raise OptimisticConflict("expected_version must be positive")
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            row = connection.execute(
                "SELECT state, version FROM pdhi_jobs WHERE tenant_id = ? AND project_id = ? AND job_id = ?",
                (scope.tenant_id, scope.project_id, job_id),
            ).fetchone()
            if row is None:
                raise ScopeViolation("job is unavailable in authenticated scope")
            current = row["state"]
            version = int(row["version"])
            if version != expected_version:
                raise OptimisticConflict("job version is stale")
            if target_state not in JOB_TRANSITIONS.get(current, frozenset()):
                raise InvalidTransition(f"job cannot transition from {current} to {target_state}")
            cursor = connection.execute(
                """UPDATE pdhi_jobs SET state = ?, version = version + 1, updated_at = ?
                   WHERE tenant_id = ? AND project_id = ? AND job_id = ? AND version = ?""",
                (target_state, _timestamp(now), scope.tenant_id, scope.project_id, job_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise OptimisticConflict("job version changed during transition")
            next_version = expected_version + 1
            detail = {"from": current, "to": target_state, "version": next_version, "reason": reason}
            self._audit(connection, scope, "job.transition", job_id, "ALLOW", detail)
            self._outbox(connection, scope, "pdhi.job.transitioned", job_id, {"job_id": job_id, **detail}, now=now)
        return self.get_job(scope, job_id)

    def acquire_lease(
        self,
        scope: ScopeBinding,
        *,
        resource_id: str,
        owner_id: str,
        ttl: timedelta,
        now: datetime | None = None,
    ) -> LeaseGrant:
        resource_id = _text(resource_id, "resource_id")
        owner_id = _text(owner_id, "owner_id")
        if ttl <= timedelta(0) or ttl > timedelta(minutes=15):
            raise LeaseConflict("lease ttl must be in (0, 15 minutes]")
        current = _utc(now)
        expires = current + ttl
        token = secrets.token_urlsafe(32)
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            row = connection.execute(
                "SELECT owner_id, generation, state, expires_at FROM pdhi_leases WHERE tenant_id = ? AND project_id = ? AND resource_id = ?",
                (scope.tenant_id, scope.project_id, resource_id),
            ).fetchone()
            generation = 1
            if row is not None:
                live = row["state"] == "ACTIVE" and _parse_timestamp(row["expires_at"]) > current
                if live and row["owner_id"] != owner_id:
                    raise LeaseConflict("resource is leased by another owner")
                generation = int(row["generation"]) + 1
            token_digest = digest(
                {"resource_id": resource_id, "owner_id": owner_id, "generation": generation, "token": token},
                domain="pdhi-lease-token",
            )
            connection.execute(
                """INSERT INTO pdhi_leases(
                    tenant_id, project_id, resource_id, owner_id, token_digest, generation, state, expires_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)
                    ON CONFLICT(tenant_id, project_id, resource_id) DO UPDATE SET
                    owner_id=excluded.owner_id, token_digest=excluded.token_digest,
                    generation=excluded.generation, state='ACTIVE', expires_at=excluded.expires_at,
                    updated_at=excluded.updated_at""",
                (
                    scope.tenant_id,
                    scope.project_id,
                    resource_id,
                    owner_id,
                    token_digest,
                    generation,
                    _timestamp(expires),
                    _timestamp(current),
                ),
            )
            self._audit(connection, scope, "lease.acquire", resource_id, "ALLOW", {"owner_id": owner_id, "generation": generation, "expires_at": _timestamp(expires)})
        return LeaseGrant(resource_id, owner_id, generation, token, expires)

    def verify_lease(
        self,
        scope: ScopeBinding,
        grant: LeaseGrant,
        *,
        now: datetime | None = None,
    ) -> None:
        current = _utc(now)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM pdhi_leases WHERE tenant_id = ? AND project_id = ? AND resource_id = ?",
                (scope.tenant_id, scope.project_id, grant.resource_id),
            ).fetchone()
        expected = digest(
            {"resource_id": grant.resource_id, "owner_id": grant.owner_id, "generation": grant.generation, "token": grant.token},
            domain="pdhi-lease-token",
        )
        if (
            row is None
            or row["state"] != "ACTIVE"
            or row["owner_id"] != grant.owner_id
            or int(row["generation"]) != grant.generation
            or not secrets.compare_digest(row["token_digest"], expected)
            or _parse_timestamp(row["expires_at"]) <= current
        ):
            raise LeaseConflict("lease is missing, expired, revoked, or stale")

    def revoke_lease(self, scope: ScopeBinding, grant: LeaseGrant, *, now: datetime | None = None) -> None:
        self.verify_lease(scope, grant, now=now)
        with self._transaction() as connection:
            cursor = connection.execute(
                """UPDATE pdhi_leases SET state = 'REVOKED', updated_at = ?
                   WHERE tenant_id = ? AND project_id = ? AND resource_id = ? AND generation = ?""",
                (_timestamp(now), scope.tenant_id, scope.project_id, grant.resource_id, grant.generation),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("lease changed while revoking")
            self._audit(connection, scope, "lease.revoke", grant.resource_id, "ALLOW", {"generation": grant.generation})

    def prepare_effect(
        self,
        scope: ScopeBinding,
        *,
        effect_id: str,
        job_id: str,
        operation: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        lease: LeaseGrant,
        now: datetime | None = None,
    ) -> EffectRecord:
        self.verify_lease(scope, lease, now=now)
        effect_id = _text(effect_id, "effect_id")
        job_id = _text(job_id, "job_id")
        operation = _text(operation, "operation")
        idempotency_key = _text(idempotency_key, "idempotency_key")
        request_digest = digest(request, domain=f"pdhi-effect:{operation}")
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            row = connection.execute(
                """SELECT * FROM pdhi_effects WHERE tenant_id = ? AND project_id = ?
                   AND operation = ? AND idempotency_key = ?""",
                (scope.tenant_id, scope.project_id, operation, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest or row["effect_id"] != effect_id:
                    raise IdempotencyConflict("effect idempotency key was reused for another request")
                return self._effect(row)
            connection.execute(
                """INSERT INTO pdhi_effects(
                    tenant_id, project_id, effect_id, job_id, operation, idempotency_key,
                    request_digest, request_json, state, response_json, lease_resource,
                    lease_generation, version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PREPARED', NULL, ?, ?, 1, ?, ?)""",
                (
                    scope.tenant_id,
                    scope.project_id,
                    effect_id,
                    job_id,
                    operation,
                    idempotency_key,
                    request_digest,
                    canonical_json(request),
                    lease.resource_id,
                    lease.generation,
                    timestamp,
                    timestamp,
                ),
            )
            detail = {"operation": operation, "request_digest": request_digest, "lease_generation": lease.generation}
            self._audit(connection, scope, "effect.prepare", effect_id, "ALLOW", detail)
            self._outbox(connection, scope, "pdhi.effect.prepared", effect_id, {"effect_id": effect_id, **detail}, now=now)
        return self.get_effect(scope, effect_id)

    @staticmethod
    def _effect(row: sqlite3.Row) -> EffectRecord:
        return EffectRecord(
            effect_id=row["effect_id"],
            job_id=row["job_id"],
            operation=row["operation"],
            state=row["state"],
            request_digest=row["request_digest"],
            response=None if row["response_json"] is None else json.loads(row["response_json"]),
            lease_resource=row["lease_resource"],
            lease_generation=int(row["lease_generation"]),
            version=int(row["version"]),
        )

    def get_effect(self, scope: ScopeBinding, effect_id: str) -> EffectRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM pdhi_effects WHERE tenant_id = ? AND project_id = ? AND effect_id = ?",
                (scope.tenant_id, scope.project_id, _text(effect_id, "effect_id")),
            ).fetchone()
        if row is None:
            raise ScopeViolation("effect is unavailable in authenticated scope")
        return self._effect(row)

    def transition_effect(
        self,
        scope: ScopeBinding,
        *,
        effect_id: str,
        expected_version: int,
        target_state: str,
        response: Mapping[str, Any] | None = None,
        lease: LeaseGrant | None = None,
        completion_receipt_digest: str | None = None,
        now: datetime | None = None,
    ) -> EffectRecord:
        effect_id = _text(effect_id, "effect_id")
        target_state = _text(target_state, "target_state")
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            row = connection.execute(
                "SELECT state, version FROM pdhi_effects WHERE tenant_id = ? AND project_id = ? AND effect_id = ?",
                (scope.tenant_id, scope.project_id, effect_id),
            ).fetchone()
            if row is None:
                raise ScopeViolation("effect is unavailable in authenticated scope")
            state = row["state"]
            version = int(row["version"])
            if version != expected_version:
                raise OptimisticConflict("effect version is stale")
            if target_state not in EFFECT_TRANSITIONS.get(state, frozenset()):
                raise InvalidTransition(f"effect cannot transition from {state} to {target_state}")
            if state == "UNKNOWN":
                if lease is None:
                    raise LeaseConflict("reconciling an UNKNOWN effect requires its current lease")
                self.verify_lease(scope, lease, now=now)
                if completion_receipt_digest is None:
                    raise InvalidTransition("UNKNOWN effect requires a trusted completion receipt")
                _sha256(completion_receipt_digest, "completion_receipt_digest")
                if lease.resource_id != row["lease_resource"] or lease.generation != int(row["lease_generation"]):
                    raise LeaseConflict("completion lease does not match the prepared effect")
                if response is None or response.get("receipt_digest") != completion_receipt_digest:
                    raise InvalidTransition("completion receipt is not bound to the effect response")
            cursor = connection.execute(
                """UPDATE pdhi_effects SET state = ?, response_json = ?, version = version + 1, updated_at = ?
                   WHERE tenant_id = ? AND project_id = ? AND effect_id = ? AND version = ?""",
                (
                    target_state,
                    None if response is None else canonical_json(response),
                    _timestamp(now),
                    scope.tenant_id,
                    scope.project_id,
                    effect_id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise OptimisticConflict("effect changed during transition")
            detail = {"from": state, "to": target_state, "version": expected_version + 1}
            self._audit(connection, scope, "effect.transition", effect_id, "ALLOW", detail)
            self._outbox(connection, scope, "pdhi.effect.transitioned", effect_id, {"effect_id": effect_id, **detail}, now=now)
        return self.get_effect(scope, effect_id)

    def append_metric(
        self,
        scope: ScopeBinding,
        *,
        job_id: str,
        metric_name: str,
        value: Decimal | int | str,
        unit: str,
        grain: str,
        definition_version: str,
        currency: str | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        if isinstance(value, bool) or isinstance(value, float):
            raise StoreError("metric values must use exact decimal input")
        try:
            decimal_value = Decimal(value)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise StoreError("invalid metric decimal") from exc
        if not decimal_value.is_finite():
            raise StoreError("metric decimal must be finite")
        currency_value = None if currency is None else _text(currency, "currency").upper()
        if currency_value is not None and (len(currency_value) != 3 or not currency_value.isalpha()):
            raise StoreError("currency must be an ISO-like three-letter code")
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            connection.execute(
                """INSERT INTO pdhi_metrics(
                    tenant_id, project_id, job_id, metric_name, value_decimal, unit, currency,
                    grain, definition_version, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope.tenant_id,
                    scope.project_id,
                    _text(job_id, "job_id"),
                    _text(metric_name, "metric_name"),
                    format(decimal_value, "f"),
                    _text(unit, "unit"),
                    currency_value,
                    _text(grain, "grain"),
                    _text(definition_version, "definition_version"),
                    _timestamp(observed_at),
                ),
            )

    def metric_rollup(
        self,
        scope: ScopeBinding,
        *,
        job_id: str | None = None,
        metric_names: Sequence[str] = (),
    ) -> tuple[Mapping[str, Any], ...]:
        """Aggregate exact metric values without mixing units or currencies."""

        if job_id is not None:
            job_id = _text(job_id, "job_id")
        names = tuple(_text(item, "metric_name") for item in metric_names)
        if len(set(names)) != len(names):
            raise StoreError("metric_names contains duplicates")
        clauses = ["tenant_id = ?", "project_id = ?"]
        values: list[Any] = [scope.tenant_id, scope.project_id]
        if job_id is not None:
            clauses.append("job_id = ?")
            values.append(job_id)
        if names:
            clauses.append("metric_name IN (" + ",".join("?" for _ in names) + ")")
            values.extend(names)
        query = (
            "SELECT metric_name, unit, currency, grain, definition_version, value_decimal "
            "FROM pdhi_metrics WHERE " + " AND ".join(clauses)
        )
        with self._lock:
            self._assert_scope(self._connection, scope)
            rows = self._connection.execute(query, tuple(values)).fetchall()
        groups: dict[tuple[str, str, str | None, str, str], Decimal] = {}
        for row in rows:
            key = (
                row["metric_name"],
                row["unit"],
                row["currency"],
                row["grain"],
                row["definition_version"],
            )
            groups[key] = groups.get(key, Decimal("0")) + Decimal(row["value_decimal"])
        return tuple(
            {
                "metric_name": key[0],
                "unit": key[1],
                "currency": key[2],
                "grain": key[3],
                "definition_version": key[4],
                "value": format(total, "f"),
            }
            for key, total in sorted(groups.items(), key=lambda item: tuple("" if value is None else value for value in item[0]))
        )

    def control_agent(
        self,
        scope: ScopeBinding,
        *,
        job_id: str,
        agent_id: str,
        command: str,
        expected_generation: int,
        detail: Mapping[str, Any],
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        """Apply a fenced, durable operator command to one scoped agent."""

        job_id = _text(job_id, "job_id")
        agent_id = _text(agent_id, "agent_id")
        command = _text(command, "command").upper()
        if command not in AGENT_COMMAND_STATES:
            raise InvalidTransition(f"unknown agent command: {command}")
        if isinstance(expected_generation, bool) or expected_generation < 0:
            raise OptimisticConflict("expected_generation must be non-negative")
        command_json = canonical_json(detail)
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            job = connection.execute(
                "SELECT 1 FROM pdhi_jobs WHERE tenant_id = ? AND project_id = ? AND job_id = ?",
                (scope.tenant_id, scope.project_id, job_id),
            ).fetchone()
            if job is None:
                raise ScopeViolation("job is unavailable in authenticated scope")
            row = connection.execute(
                """SELECT state, generation FROM pdhi_agent_controls
                   WHERE tenant_id = ? AND project_id = ? AND job_id = ? AND agent_id = ?""",
                (scope.tenant_id, scope.project_id, job_id, agent_id),
            ).fetchone()
            state = "ABSENT" if row is None else row["state"]
            generation = 0 if row is None else int(row["generation"])
            if generation != expected_generation:
                raise OptimisticConflict("agent generation is stale")
            target = AGENT_COMMAND_STATES[command].get(state)
            if target is None:
                raise InvalidTransition(f"agent command {command} is invalid from {state}")
            next_generation = generation + 1
            connection.execute(
                """INSERT INTO pdhi_agent_controls(
                    tenant_id, project_id, job_id, agent_id, state, generation, command_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, project_id, job_id, agent_id) DO UPDATE SET
                    state=excluded.state, generation=excluded.generation,
                    command_json=excluded.command_json, updated_at=excluded.updated_at""",
                (
                    scope.tenant_id,
                    scope.project_id,
                    job_id,
                    agent_id,
                    target,
                    next_generation,
                    command_json,
                    timestamp,
                ),
            )
            event = {
                "job_id": job_id,
                "agent_id": agent_id,
                "command": command,
                "from": state,
                "to": target,
                "generation": next_generation,
                "detail_digest": digest(detail, domain="pdhi-agent-command"),
            }
            self._audit(connection, scope, "agent.control", agent_id, "ALLOW", event, now=now)
            self._outbox(connection, scope, "pdhi.agent.controlled", agent_id, event, now=now)
        return MappingProxyType({**event, "updated_at": timestamp})

    def mutate_provider_session(
        self,
        scope: ScopeBinding,
        *,
        job_id: str,
        session_id: str,
        provider_id: str,
        command: str,
        expected_generation: int,
        external_ref_digest: str | None = None,
        checkpoint_digest: str | None = None,
        now: datetime | None = None,
    ) -> Mapping[str, Any]:
        """Record provider-session lifecycle only; it performs no provider call."""

        job_id = _text(job_id, "job_id")
        session_id = _text(session_id, "session_id")
        provider_id = _text(provider_id, "provider_id")
        command = _text(command, "command").upper()
        if command not in SESSION_COMMAND_STATES:
            raise InvalidTransition(f"unknown session command: {command}")
        if isinstance(expected_generation, bool) or expected_generation < 0:
            raise OptimisticConflict("expected_generation must be non-negative")
        external_ref = _sha256(external_ref_digest, "external_ref_digest", optional=True)
        checkpoint = _sha256(checkpoint_digest, "checkpoint_digest", optional=True)
        timestamp = _timestamp(now)
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            job = connection.execute(
                "SELECT 1 FROM pdhi_jobs WHERE tenant_id = ? AND project_id = ? AND job_id = ?",
                (scope.tenant_id, scope.project_id, job_id),
            ).fetchone()
            if job is None:
                raise ScopeViolation("job is unavailable in authenticated scope")
            row = connection.execute(
                """SELECT * FROM pdhi_provider_sessions
                   WHERE tenant_id = ? AND project_id = ? AND job_id = ? AND session_id = ?""",
                (scope.tenant_id, scope.project_id, job_id, session_id),
            ).fetchone()
            state = "ABSENT" if row is None else row["state"]
            generation = 0 if row is None else int(row["generation"])
            if generation != expected_generation:
                raise OptimisticConflict("provider session generation is stale")
            if row is not None and row["provider_id"] != provider_id:
                raise ScopeViolation("provider session identity mismatch")
            target = SESSION_COMMAND_STATES[command].get(state)
            if target is None:
                raise InvalidTransition(f"session command {command} is invalid from {state}")
            next_generation = generation + 1
            inherited_ref = external_ref if external_ref is not None else (None if row is None else row["external_ref_digest"])
            inherited_checkpoint = checkpoint if checkpoint is not None else (None if row is None else row["checkpoint_digest"])
            connection.execute(
                """INSERT INTO pdhi_provider_sessions(
                    tenant_id, project_id, job_id, session_id, provider_id, state, generation,
                    external_ref_digest, checkpoint_digest, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, project_id, job_id, session_id) DO UPDATE SET
                    state=excluded.state, generation=excluded.generation,
                    external_ref_digest=excluded.external_ref_digest,
                    checkpoint_digest=excluded.checkpoint_digest, updated_at=excluded.updated_at""",
                (
                    scope.tenant_id,
                    scope.project_id,
                    job_id,
                    session_id,
                    provider_id,
                    target,
                    next_generation,
                    inherited_ref,
                    inherited_checkpoint,
                    timestamp,
                ),
            )
            event = {
                "job_id": job_id,
                "session_id": session_id,
                "provider_id": provider_id,
                "command": command,
                "from": state,
                "to": target,
                "generation": next_generation,
                "external_effect_status": "NOT_RUN",
            }
            self._audit(connection, scope, "provider-session.control", session_id, "ALLOW", event, now=now)
            self._outbox(connection, scope, "pdhi.provider-session.controlled", session_id, event, now=now)
        return MappingProxyType({
            **event,
            "external_ref_digest": inherited_ref,
            "checkpoint_digest": inherited_checkpoint,
            "updated_at": timestamp,
        })

    def record_control_event(
        self,
        scope: ScopeBinding,
        *,
        operation: str,
        aggregate_id: str,
        decision: str,
        detail: Mapping[str, Any],
        topic: str | None = None,
        now: datetime | None = None,
    ) -> str:
        """Append an auditable, optionally outboxed control-plane observation."""

        event_digest = digest(
            {
                "operation": operation,
                "aggregate_id": aggregate_id,
                "decision": decision,
                "detail": detail,
            },
            domain="pdhi-control-event",
        )
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            self._audit(connection, scope, operation, aggregate_id, decision, {**detail, "event_digest": event_digest}, now=now)
            if topic is not None:
                self._outbox(connection, scope, topic, aggregate_id, {**detail, "event_digest": event_digest}, now=now)
        return event_digest

    def claim_outbox(
        self,
        scope: ScopeBinding,
        *,
        worker_id: str,
        limit: int = 32,
        lease: timedelta = timedelta(seconds=30),
        now: datetime | None = None,
    ) -> tuple[OutboxClaim, ...]:
        worker_id = _text(worker_id, "worker_id")
        if limit < 1 or limit > 256:
            raise StoreError("outbox limit must be in [1, 256]")
        if lease <= timedelta(0) or lease > timedelta(minutes=5):
            raise StoreError("outbox claim ttl must be in (0, 5 minutes]")
        current = _utc(now)
        claims: list[OutboxClaim] = []
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            rows = connection.execute(
                """SELECT * FROM pdhi_outbox
                   WHERE tenant_id = ? AND project_id = ?
                     AND (state = 'PENDING' OR (state = 'CLAIMED' AND claimed_until <= ?))
                     AND available_at <= ? ORDER BY event_id LIMIT ?""",
                (
                    scope.tenant_id,
                    scope.project_id,
                    _timestamp(current),
                    _timestamp(current),
                    limit,
                ),
            ).fetchall()
            for row in rows:
                token = secrets.token_urlsafe(24)
                token_digest = digest({"event_id": row["event_id"], "worker_id": worker_id, "token": token}, domain="pdhi-outbox-token")
                connection.execute(
                    """UPDATE pdhi_outbox SET state = 'CLAIMED', attempts = attempts + 1,
                       claimed_by = ?, claimed_until = ?, delivery_token_digest = ?
                       WHERE event_id = ? AND tenant_id = ? AND project_id = ?""",
                    (
                        worker_id,
                        _timestamp(current + lease),
                        token_digest,
                        row["event_id"],
                        scope.tenant_id,
                        scope.project_id,
                    ),
                )
                claims.append(
                    OutboxClaim(
                        event_id=int(row["event_id"]),
                        topic=row["topic"],
                        aggregate_id=row["aggregate_id"],
                        payload=json.loads(row["payload_json"]),
                        delivery_token=token,
                        attempts=int(row["attempts"]) + 1,
                    )
                )
        return tuple(claims)

    def acknowledge_outbox(
        self,
        scope: ScopeBinding,
        claim: OutboxClaim,
        *,
        worker_id: str,
        delivered_at: datetime | None = None,
    ) -> None:
        expected = digest({"event_id": claim.event_id, "worker_id": worker_id, "token": claim.delivery_token}, domain="pdhi-outbox-token")
        with self._transaction() as connection:
            self._assert_scope(connection, scope)
            cursor = connection.execute(
                """UPDATE pdhi_outbox SET state = 'DELIVERED', delivered_at = ?, claimed_until = NULL
                   WHERE event_id = ? AND tenant_id = ? AND project_id = ?
                     AND state = 'CLAIMED' AND claimed_by = ? AND delivery_token_digest = ?""",
                (
                    _timestamp(delivered_at),
                    claim.event_id,
                    scope.tenant_id,
                    scope.project_id,
                    _text(worker_id, "worker_id"),
                    expected,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseConflict("outbox delivery claim is stale or invalid")

    def audit_records(self, scope: ScopeBinding, *, after_id: int = 0, limit: int = 100) -> tuple[Mapping[str, Any], ...]:
        if after_id < 0 or limit < 1 or limit > 1000:
            raise StoreError("invalid audit page")
        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM pdhi_audit WHERE tenant_id = ? AND project_id = ? AND audit_id > ?
                   ORDER BY audit_id LIMIT ?""",
                (scope.tenant_id, scope.project_id, after_id, limit),
            ).fetchall()
        return tuple(
            {
                "audit_id": int(row["audit_id"]),
                "actor_id": row["actor_id"],
                "operation": row["operation"],
                "aggregate_id": row["aggregate_id"],
                "decision": row["decision"],
                "detail": json.loads(row["detail_json"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        )

    def readiness(self) -> Mapping[str, Any]:
        try:
            row = self._connection.execute("PRAGMA integrity_check").fetchone()
            integrity = None if row is None else row[0]
            version = self._connection.execute("SELECT MAX(version) FROM pdhi_schema_version").fetchone()[0]
        except sqlite3.Error as exc:
            return {"status": "NOT_READY", "backend": "sqlite-local", "reason": str(exc), "schema_version": None}
        return {
            "status": "READY" if integrity == "ok" and int(version) == SCHEMA_VERSION else "NOT_READY",
            "backend": "sqlite-local",
            "reason": "local engineering backend only" if integrity == "ok" else str(integrity),
            "schema_version": int(version),
            "production_multi_replica": False,
        }


__all__ = [
    "EFFECT_TRANSITIONS",
    "JOB_TRANSITIONS",
    "EffectRecord",
    "IdempotencyConflict",
    "IdempotencyReservation",
    "InvalidTransition",
    "LeaseConflict",
    "LeaseGrant",
    "OptimisticConflict",
    "OutboxClaim",
    "SCHEMA_VERSION",
    "ScopeBinding",
    "ScopeViolation",
    "SqlitePdhiStore",
    "StoreError",
    "canonical_json",
    "digest",
]
