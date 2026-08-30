"""Durable, tenant/project-scoped SQLite control-plane storage.

SQLite is the bounded local implementation.  It supplies strict tables,
``BEGIN IMMEDIATE`` writes, request-bound idempotency, optimistic transitions
and append-only hash-chained journals.  The final database inode is opened
with ``O_NOFOLLOW`` and compared again after SQLite connects.  SQLite still
receives a pathname rather than that descriptor, so this is a bounded local
boundary rather than a strong sandbox or a replacement for PostgreSQL RLS.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .canonical import canonical_json, digest_object, strict_json_loads, to_jsonable
from .contracts import CapabilityLease, HandlerResult, Invocation, Scope, utc_now
from .errors import (
    ContractError,
    IdempotencyConflict,
    IntegrityError,
    NotFoundError,
    StoreError,
    TransitionConflict,
)
from .trusted_paths import PathBoundaryError, open_owned_regular, verify_regular_identity

_JOURNAL_STREAMS = frozenset({"AUDIT", "EVIDENCE", "CHECKPOINT", "OUTBOX"})
_MAX_CHECKPOINT_CHAIN_ROWS = 10_000
_MAX_CHECKPOINT_CHAIN_PAYLOAD_BYTES = 16 * 1_048_576
_MAX_PERSISTED_DOCUMENT_BYTES = 1_048_576
_MAX_INTEGRITY_SCOPES = 1_024
_MAX_INTEGRITY_SCOPE_DISCOVERY_ROWS = 100_000
_MAX_INTEGRITY_INVOCATIONS = 10_000
_MAX_INTEGRITY_JOURNAL_ENTRIES = 50_000
_MAX_INTEGRITY_JSON_BYTES = 64 * 1_048_576
_MAX_SCOPE_IDENTIFIER_BYTES = 200
_MAX_SQLITE_VALUE_BYTES = 4 * 1_048_576
_SQLITE_PROGRESS_GRANULARITY = 1_000
_MAX_READ_VM_STEPS = 50_000_000
_INTEGRITY_SCAN_INDEXES: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "idx_invocations_integrity_scan": (
        "invocations",
        ("tenant_id", "project_id", "invocation_id"),
    ),
    "idx_journal_integrity_scan": (
        "journal_entries",
        ("tenant_id", "project_id", "stream", "sequence"),
    ),
}
_TRUSTED_TABLE_LAYOUTS: Mapping[str, tuple[tuple[str, str, int, int, int], ...]] = {
    "schema_migrations": (
        ("version", "INTEGER", 0, 1, 0),
        ("applied_at", "TEXT", 1, 0, 0),
    ),
    "invocations": (
        ("tenant_id", "TEXT", 1, 1, 0),
        ("project_id", "TEXT", 1, 2, 0),
        ("invocation_id", "TEXT", 1, 3, 0),
        ("actor_id", "TEXT", 1, 0, 0),
        ("revision", "TEXT", 1, 0, 0),
        ("environment_id", "TEXT", 1, 0, 0),
        ("skill_id", "TEXT", 1, 0, 0),
        ("action", "TEXT", 1, 0, 0),
        ("idempotency_key", "TEXT", 1, 0, 0),
        ("request_digest", "TEXT", 1, 0, 0),
        ("request_json", "TEXT", 1, 0, 0),
        ("lease_digest", "TEXT", 1, 0, 0),
        ("state", "TEXT", 1, 0, 0),
        ("sequence", "INTEGER", 1, 0, 0),
        ("result_digest", "TEXT", 0, 0, 0),
        ("result_json", "TEXT", 0, 0, 0),
        ("error_code", "TEXT", 0, 0, 0),
        ("created_at", "TEXT", 1, 0, 0),
        ("updated_at", "TEXT", 1, 0, 0),
    ),
    "journal_entries": (
        ("tenant_id", "TEXT", 1, 1, 0),
        ("project_id", "TEXT", 1, 2, 0),
        ("actor_id", "TEXT", 1, 0, 0),
        ("revision", "TEXT", 1, 0, 0),
        ("environment_id", "TEXT", 1, 0, 0),
        ("stream", "TEXT", 1, 3, 0),
        ("sequence", "INTEGER", 1, 4, 0),
        ("event_id", "TEXT", 1, 0, 0),
        ("kind", "TEXT", 1, 0, 0),
        ("subject_id", "TEXT", 1, 0, 0),
        ("payload_json", "TEXT", 1, 0, 0),
        ("payload_digest", "TEXT", 1, 0, 0),
        ("previous_digest", "TEXT", 0, 0, 0),
        ("entry_digest", "TEXT", 1, 0, 0),
        ("created_at", "TEXT", 1, 0, 0),
    ),
}
_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "PENDING": frozenset({"AUTHORIZED", "DENIED", "FAILED"}),
    "AUTHORIZED": frozenset({"EXECUTING", "DENIED", "FAILED"}),
    "EXECUTING": frozenset({"PERSISTING", "FAILED", "BLOCKED"}),
    "PERSISTING": frozenset({"COMPLETED", "FAILED", "BLOCKED"}),
    "COMPLETED": frozenset(),
    "DENIED": frozenset(),
    "FAILED": frozenset(),
    "BLOCKED": frozenset(),
}


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise StoreError("store timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True, slots=True)
class InvocationSnapshot:
    scope: Scope
    invocation_id: str
    skill_id: str
    action: str
    idempotency_key: str
    request_digest: str
    lease_digest: str
    state: str
    sequence: int
    result_digest: str | None
    result: Mapping[str, Any] | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def terminal(self) -> bool:
        return not _TRANSITIONS[self.state]


@dataclass(frozen=True, slots=True)
class JournalEntry:
    scope: Scope
    stream: str
    sequence: int
    event_id: str
    kind: str
    subject_id: str
    payload: Mapping[str, Any]
    payload_digest: str
    previous_digest: str | None
    entry_digest: str
    created_at: datetime


_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS invocations (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  invocation_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  revision TEXT NOT NULL CHECK (length(revision) = 71 AND substr(revision, 1, 7) = 'sha256:'),
  environment_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  action TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL CHECK (length(request_digest) = 71 AND substr(request_digest, 1, 7) = 'sha256:'),
  request_json TEXT NOT NULL,
  lease_digest TEXT NOT NULL CHECK (length(lease_digest) = 71 AND substr(lease_digest, 1, 7) = 'sha256:'),
  state TEXT NOT NULL CHECK (state IN ('PENDING','AUTHORIZED','EXECUTING','PERSISTING','COMPLETED','DENIED','FAILED','BLOCKED')),
  sequence INTEGER NOT NULL CHECK (sequence >= 0),
  result_digest TEXT CHECK (result_digest IS NULL OR (length(result_digest) = 71 AND substr(result_digest, 1, 7) = 'sha256:')),
  result_json TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, invocation_id),
  UNIQUE (tenant_id, project_id, actor_id, skill_id, action, idempotency_key),
  CHECK ((result_digest IS NULL) = (result_json IS NULL)),
  CHECK (state != 'COMPLETED' OR result_json IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS journal_entries (
  tenant_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  revision TEXT NOT NULL CHECK (length(revision) = 71 AND substr(revision, 1, 7) = 'sha256:'),
  environment_id TEXT NOT NULL,
  stream TEXT NOT NULL CHECK (stream IN ('AUDIT','EVIDENCE','CHECKPOINT','OUTBOX')),
  sequence INTEGER NOT NULL CHECK (sequence >= 1),
  event_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 71 AND substr(payload_digest, 1, 7) = 'sha256:'),
  previous_digest TEXT CHECK (previous_digest IS NULL OR (length(previous_digest) = 71 AND substr(previous_digest, 1, 7) = 'sha256:')),
  entry_digest TEXT NOT NULL CHECK (length(entry_digest) = 71 AND substr(entry_digest, 1, 7) = 'sha256:'),
  created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, project_id, stream, sequence),
  UNIQUE (tenant_id, project_id, event_id),
  UNIQUE (tenant_id, project_id, stream, entry_digest)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_invocations_idempotency
  ON invocations(tenant_id, project_id, actor_id, skill_id, action, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_journal_subject
  ON journal_entries(tenant_id, project_id, stream, subject_id, sequence);
CREATE INDEX IF NOT EXISTS idx_invocations_integrity_scan
  ON invocations(tenant_id, project_id, invocation_id);
CREATE INDEX IF NOT EXISTS idx_journal_integrity_scan
  ON journal_entries(tenant_id, project_id, stream, sequence);

CREATE TRIGGER IF NOT EXISTS journal_entries_immutable_update
BEFORE UPDATE ON journal_entries BEGIN
  SELECT RAISE(ABORT, 'append-only journal');
END;
CREATE TRIGGER IF NOT EXISTS journal_entries_immutable_delete
BEFORE DELETE ON journal_entries BEGIN
  SELECT RAISE(ABORT, 'append-only journal');
END;
"""


def _normalize_schema_sql(document: str) -> str:
    return " ".join(document.strip().removesuffix(";").split())


def _trusted_schema_statement(marker: str, *, trigger: bool = False) -> str:
    start = _SCHEMA.index(marker)
    terminator = "END;" if trigger else ";"
    end = _SCHEMA.index(terminator, start) + len(terminator)
    statement = _SCHEMA[start:end].replace(" IF NOT EXISTS", "", 1)
    return _normalize_schema_sql(statement)


_TRUSTED_SCHEMA_OBJECTS: Mapping[str, tuple[str, str, str]] = {
    "schema_migrations": (
        "table",
        "schema_migrations",
        _trusted_schema_statement("CREATE TABLE IF NOT EXISTS schema_migrations"),
    ),
    "invocations": (
        "table",
        "invocations",
        _trusted_schema_statement("CREATE TABLE IF NOT EXISTS invocations"),
    ),
    "journal_entries": (
        "table",
        "journal_entries",
        _trusted_schema_statement("CREATE TABLE IF NOT EXISTS journal_entries"),
    ),
    "idx_invocations_integrity_scan": (
        "index",
        "invocations",
        _trusted_schema_statement("CREATE INDEX IF NOT EXISTS idx_invocations_integrity_scan"),
    ),
    "idx_journal_integrity_scan": (
        "index",
        "journal_entries",
        _trusted_schema_statement("CREATE INDEX IF NOT EXISTS idx_journal_integrity_scan"),
    ),
    "journal_entries_immutable_update": (
        "trigger",
        "journal_entries",
        _trusted_schema_statement("CREATE TRIGGER IF NOT EXISTS journal_entries_immutable_update", trigger=True),
    ),
    "journal_entries_immutable_delete": (
        "trigger",
        "journal_entries",
        _trusted_schema_statement("CREATE TRIGGER IF NOT EXISTS journal_entries_immutable_delete", trigger=True),
    ),
}


class SQLiteControlPlaneStore:
    def __init__(self, path: str | Path = ":memory:", *, _read_only: bool = False) -> None:
        if isinstance(path, Path):
            path_value = str(path)
        elif isinstance(path, str):
            path_value = path
        else:
            raise StoreError("SQLite path must be text or Path")
        if _read_only and path_value == ":memory:":
            raise StoreError("read-only verification requires an existing durable database")
        self.path = path_value
        self._read_only = _read_only
        self._lock = threading.RLock()
        self.__mutation_capability = object()
        secured_path: Path | None = None
        descriptor: int | None = None
        identity = None
        if path_value != ":memory:":
            try:
                secured_path, descriptor, identity, _ = open_owned_regular(
                    path,
                    label="SQLite database",
                    create=not _read_only,
                    read_only=_read_only,
                )
            except PathBoundaryError as exc:
                raise StoreError(str(exc), code="SQLITE_PATH_UNSAFE") from exc
            path_value = str(secured_path)
            self.path = path_value
        connection: sqlite3.Connection | None = None
        try:
            if _read_only:
                uri = f"file:{quote(path_value, safe='/')}?mode=ro"
                connection = sqlite3.connect(
                    uri,
                    isolation_level=None,
                    check_same_thread=False,
                    uri=True,
                )
            else:
                connection = sqlite3.connect(path_value, isolation_level=None, check_same_thread=False)
            if secured_path is not None and descriptor is not None and identity is not None:
                verify_regular_identity(
                    secured_path,
                    descriptor,
                    identity,
                    label="SQLite database",
                )
        except (sqlite3.Error, PathBoundaryError) as exc:
            if connection is not None:
                connection.close()
            raise StoreError("failed to securely open SQLite database", code="SQLITE_OPEN_UNSAFE") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if connection is None:
            raise StoreError("SQLite connection was not established")
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        try:
            set_limit = getattr(self._connection, "setlimit", None)
            length_category = getattr(sqlite3, "SQLITE_LIMIT_LENGTH", None)
            if not callable(set_limit) or not isinstance(length_category, int):
                self._connection.close()
                raise StoreError("SQLite runtime does not expose bounded value limits")
            set_limit(length_category, _MAX_SQLITE_VALUE_BYTES)
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
        except sqlite3.Error as exc:
            self._connection.close()
            raise StoreError("failed to configure bounded SQLite limits", code="SQLITE_LIMIT_CONFIGURATION_FAILED") from exc
        try:
            if _read_only:
                self._connection.execute("PRAGMA query_only = ON")
                self._validate_existing_schema()
            else:
                self._connection.execute("PRAGMA secure_delete = ON")
                if path_value != ":memory:":
                    self._connection.execute("PRAGMA journal_mode = WAL")
                    self._connection.execute("PRAGMA synchronous = FULL")
                self._migrate()
        except Exception:
            self._connection.close()
            raise

    @classmethod
    def open_readonly(cls, path: str | Path) -> SQLiteControlPlaneStore:
        """Open an existing control-plane database without migrations or write PRAGMAs."""

        return cls(path, _read_only=True)

    def _validate_existing_schema(self) -> None:
        self._assert_exact_schema_locked(self._connection, require_version=True)

    def _migrate(self) -> None:
        with self._lock:
            try:
                self._connection.executescript(_SCHEMA)
                self._assert_exact_schema_locked(self._connection, require_version=False)
                self._connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (1, _iso(utc_now())),
                )
                self._assert_exact_schema_locked(self._connection, require_version=True)
            except sqlite3.Error as exc:
                raise StoreError("failed to initialize control-plane schema") from exc

    @staticmethod
    def _assert_exact_schema_locked(connection: sqlite3.Connection, *, require_version: bool) -> None:
        try:
            for object_name, (expected_type, expected_table, expected_sql) in _TRUSTED_SCHEMA_OBJECTS.items():
                rows = connection.execute(
                    "SELECT type, tbl_name, sql FROM sqlite_schema WHERE name=? LIMIT 2",
                    (object_name,),
                ).fetchmany(2)
                if len(rows) != 1:
                    raise StoreError("control-plane schema object is missing", code="STORE_SCHEMA_INVALID")
                row = rows[0]
                sql = row["sql"]
                if (
                    row["type"] != expected_type
                    or row["tbl_name"] != expected_table
                    or not isinstance(sql, str)
                    or _normalize_schema_sql(sql) != expected_sql
                ):
                    raise StoreError("control-plane schema object is invalid", code="STORE_SCHEMA_INVALID")

            for table_name, expected_layout in _TRUSTED_TABLE_LAYOUTS.items():
                layout_rows = connection.execute(f"PRAGMA table_xinfo('{table_name}')").fetchmany(
                    len(expected_layout) + 1
                )
                actual_layout = tuple(
                    (
                        row["name"],
                        row["type"],
                        int(row["notnull"]),
                        int(row["pk"]),
                        int(row["hidden"]),
                    )
                    for row in layout_rows
                )
                if actual_layout != expected_layout:
                    raise StoreError("control-plane table layout is invalid", code="STORE_SCHEMA_INVALID")
                table_rows = connection.execute(
                    """
                    SELECT type, ncol, wr, strict FROM pragma_table_list
                    WHERE schema='main' AND name=? LIMIT 2
                    """,
                    (table_name,),
                ).fetchmany(2)
                if (
                    len(table_rows) != 1
                    or table_rows[0]["type"] != "table"
                    or int(table_rows[0]["ncol"]) != len(expected_layout)
                    or int(table_rows[0]["wr"]) != 0
                    or int(table_rows[0]["strict"]) != 1
                ):
                    raise StoreError("control-plane table mode is invalid", code="STORE_SCHEMA_INVALID")

            trigger_rows = connection.execute(
                """
                SELECT name FROM sqlite_schema
                WHERE type='trigger' AND tbl_name IN ('invocations','journal_entries')
                LIMIT 4
                """
            ).fetchmany(4)
            trigger_names = {row["name"] for row in trigger_rows}
            expected_triggers = {
                "journal_entries_immutable_update",
                "journal_entries_immutable_delete",
            }
            if trigger_names != expected_triggers:
                raise StoreError("control-plane trigger set is invalid", code="STORE_SCHEMA_INVALID")
            SQLiteControlPlaneStore._assert_integrity_indexes_locked(connection)

            if require_version:
                version_rows = connection.execute(
                    "SELECT version, applied_at FROM schema_migrations ORDER BY version LIMIT 2"
                ).fetchmany(2)
                if len(version_rows) != 1 or version_rows[0]["version"] != 1:
                    raise StoreError("control-plane schema version is invalid", code="STORE_SCHEMA_INVALID")
                applied_at = version_rows[0]["applied_at"]
                if not isinstance(applied_at, str):
                    raise StoreError("control-plane migration timestamp is invalid", code="STORE_SCHEMA_INVALID")
                parsed = _dt(applied_at)
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise StoreError("control-plane migration timestamp is invalid", code="STORE_SCHEMA_INVALID")
        except StoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise StoreError("cannot validate control-plane schema", code="STORE_SCHEMA_INVALID") from exc

    @staticmethod
    def _assert_integrity_indexes_locked(connection: sqlite3.Connection) -> None:
        for index_name, (expected_table, expected_columns) in _INTEGRITY_SCAN_INDEXES.items():
            rows = connection.execute(f"PRAGMA index_info('{index_name}')").fetchmany(len(expected_columns) + 1)
            actual_columns = tuple(row["name"] for row in rows)
            if actual_columns != expected_columns:
                raise StoreError("control-plane integrity index is invalid", code="STORE_SCHEMA_INVALID")
            index_rows = connection.execute(f"PRAGMA index_list('{expected_table}')").fetchmany(16)
            matches = [row for row in index_rows if row["name"] == index_name]
            if (
                len(matches) != 1
                or matches[0]["origin"] != "c"
                or int(matches[0]["partial"]) != 0
            ):
                raise StoreError("control-plane integrity index ownership is invalid", code="STORE_SCHEMA_INVALID")

    @property
    def schema_version(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
        return int(row["version"])

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        if self._read_only:
            raise StoreError("read-only control-plane stores cannot be mutated", code="STORE_READ_ONLY")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield self._connection
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        """Hold one bounded, repeatable SQLite read snapshot."""

        with self._lock:
            if self._connection.in_transaction:
                raise StoreError("cannot start a nested store read transaction")
            started = False
            consumed_steps = 0

            def progress() -> int:
                nonlocal consumed_steps
                consumed_steps += _SQLITE_PROGRESS_GRANULARITY
                return int(consumed_steps > _MAX_READ_VM_STEPS)

            def rollback_if_needed() -> None:
                if not started or not bool(getattr(self._connection, "in_transaction", False)):
                    return
                try:
                    self._connection.execute("ROLLBACK")
                except sqlite3.Error:
                    return

            self._connection.set_progress_handler(progress, _SQLITE_PROGRESS_GRANULARITY)
            try:
                self._connection.execute("BEGIN")
                started = True
                yield self._connection
                self._connection.execute("COMMIT")
                started = False
            except sqlite3.Error as exc:
                self._connection.set_progress_handler(None, 0)
                rollback_if_needed()
                if isinstance(exc, sqlite3.OperationalError) and "interrupted" in str(exc).lower():
                    raise IntegrityError("store read instruction limit exceeded", code="STORE_INTEGRITY_LIMIT") from exc
                raise StoreError("bounded store read failed", code="STORE_READ_FAILED") from exc
            except Exception:
                self._connection.set_progress_handler(None, 0)
                rollback_if_needed()
                raise
            finally:
                self._connection.set_progress_handler(None, 0)

    def _assert_mutation_capability(self, candidate: object) -> None:
        if candidate is not self.__mutation_capability:
            raise StoreError(
                "control-plane mutation requires the runtime-owned writer capability",
                code="STORE_MUTATION_CAPABILITY_REQUIRED",
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> SQLiteControlPlaneStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _request_document(invocation: Invocation, inputs: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "action": invocation.action,
            "input_digest": digest_object(inputs, domain="invocation-inputs"),
            "scope_digest": invocation.scope.digest,
            "skill_id": invocation.skill_id,
        }

    @staticmethod
    def request_digest(invocation: Invocation, inputs: Mapping[str, Any]) -> str:
        return digest_object(
            SQLiteControlPlaneStore._request_document(invocation, inputs),
            domain="invocation-request",
        )

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> InvocationSnapshot:
        try:
            scope = Scope(
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                actor_id=row["actor_id"],
                revision=row["revision"],
                environment_id=row["environment_id"],
            )
            created_at = _dt(row["created_at"])
            updated_at = _dt(row["updated_at"])
        except (ContractError, TypeError, ValueError) as exc:
            raise IntegrityError("stored invocation envelope is invalid", code="INVOCATION_TAMPERED") from exc
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise IntegrityError("stored invocation timestamp is naive", code="INVOCATION_TAMPERED")
        if updated_at.tzinfo is None or updated_at.utcoffset() is None or updated_at < created_at:
            raise IntegrityError("stored invocation timestamps are inconsistent", code="INVOCATION_TAMPERED")

        request = SQLiteControlPlaneStore._canonical_mapping(
            row["request_json"],
            label="request",
            code="REQUEST_TAMPERED",
        )
        if digest_object(request, domain="invocation-request") != row["request_digest"]:
            raise IntegrityError("stored request digest mismatch", code="REQUEST_TAMPERED")
        expected_request_binding = {
            "action": row["action"],
            "scope_digest": scope.digest,
            "skill_id": row["skill_id"],
        }
        if set(request) != {"action", "input_digest", "scope_digest", "skill_id"} or any(
            request.get(field) != value for field, value in expected_request_binding.items()
        ):
            raise IntegrityError("stored request binding mismatch", code="REQUEST_TAMPERED")
        input_digest = request.get("input_digest")
        if not isinstance(input_digest, str) or not input_digest.startswith("sha256:") or len(input_digest) != 71:
            raise IntegrityError("stored input digest is invalid", code="REQUEST_TAMPERED")

        state = row["state"]
        if state not in _TRANSITIONS:
            raise IntegrityError("stored invocation state is invalid", code="INVOCATION_STATE_TAMPERED")
        result_json = row["result_json"]
        result_digest = row["result_digest"]
        if (result_json is None) != (result_digest is None):
            raise IntegrityError("stored result fields are inconsistent", code="RESULT_TAMPERED")
        result: Mapping[str, Any] | None = None
        if result_json is not None:
            result = SQLiteControlPlaneStore._canonical_mapping(
                result_json,
                label="result",
                code="RESULT_TAMPERED",
            )
            if digest_object(result, domain="handler-result") != result_digest:
                raise IntegrityError("stored result digest mismatch", code="RESULT_TAMPERED")
            if result.get("skill_id") != row["skill_id"]:
                raise IntegrityError("stored result Skill binding mismatch", code="RESULT_TAMPERED")
            output = result.get("output")
            if not isinstance(output, Mapping):
                raise IntegrityError("stored result output is invalid", code="RESULT_TAMPERED")
            if "scope_digest" in output and output["scope_digest"] != scope.digest:
                raise IntegrityError("stored result scope binding mismatch", code="RESULT_TAMPERED")
        if (state == "COMPLETED") != (result is not None):
            raise IntegrityError("stored result does not match invocation state", code="RESULT_TAMPERED")
        if state == "COMPLETED" and row["error_code"] is not None:
            raise IntegrityError("completed invocation retains an error", code="INVOCATION_STATE_TAMPERED")
        return InvocationSnapshot(
            scope=scope,
            invocation_id=row["invocation_id"],
            skill_id=row["skill_id"],
            action=row["action"],
            idempotency_key=row["idempotency_key"],
            request_digest=row["request_digest"],
            lease_digest=row["lease_digest"],
            state=state,
            sequence=int(row["sequence"]),
            result_digest=result_digest,
            result=result,
            error_code=row["error_code"],
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _canonical_mapping(document: object, *, label: str, code: str) -> Mapping[str, Any]:
        if not isinstance(document, str):
            raise IntegrityError(f"stored {label} is not text", code=code)
        try:
            value = strict_json_loads(document)
            if not isinstance(value, Mapping):
                raise ContractError(f"stored {label} must be a JSON object")
            if canonical_json(value) != document:
                raise ContractError(f"stored {label} is not canonical JSON")
        except ContractError as exc:
            raise IntegrityError(f"stored {label} is invalid", code=code) from exc
        return value

    def _begin_invocation(
        self,
        invocation: Invocation,
        lease: CapabilityLease,
        inputs: Mapping[str, Any],
        *,
        _runtime_capability: object,
    ) -> InvocationSnapshot:
        self._assert_mutation_capability(_runtime_capability)
        request_document = self._request_document(invocation, inputs)
        request_digest = digest_object(request_document, domain="invocation-request")
        if request_digest != invocation.request_digest:
            raise IntegrityError(
                "invocation request digest mismatch",
                code="REQUEST_DIGEST_MISMATCH",
                details={"expected": invocation.request_digest, "actual": request_digest},
            )
        now = _iso(utc_now())
        scope = invocation.scope
        with self._write() as connection:
            existing = connection.execute(
                """
                SELECT * FROM invocations
                WHERE tenant_id=? AND project_id=? AND actor_id=? AND skill_id=? AND action=? AND idempotency_key=?
                """,
                (
                    scope.tenant_id,
                    scope.project_id,
                    scope.actor_id,
                    invocation.skill_id,
                    invocation.action,
                    invocation.idempotency_key,
                ),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest or existing["lease_digest"] != lease.digest:
                    raise IdempotencyConflict(
                        "idempotency key was reused with a different request or authority",
                        details={"idempotency_key": invocation.idempotency_key},
                    )
                return self._snapshot(existing)
            try:
                connection.execute(
                    """
                    INSERT INTO invocations(
                      tenant_id,project_id,invocation_id,actor_id,revision,environment_id,
                      skill_id,action,idempotency_key,request_digest,request_json,lease_digest,
                      state,sequence,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        scope.tenant_id,
                        scope.project_id,
                        invocation.invocation_id,
                        scope.actor_id,
                        scope.revision,
                        scope.environment_id,
                        invocation.skill_id,
                        invocation.action,
                        invocation.idempotency_key,
                        request_digest,
                        canonical_json(request_document),
                        lease.digest,
                        "PENDING",
                        0,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise IdempotencyConflict("invocation identity conflicts with an existing request") from exc
            self._append_journal_locked(
                connection,
                scope,
                "AUDIT",
                event_id=f"{invocation.invocation_id}:created",
                kind="INVOCATION_CREATED",
                subject_id=invocation.invocation_id,
                payload={"request_digest": request_digest, "skill_id": invocation.skill_id, "action": invocation.action},
                created_at=now,
            )
            row = connection.execute(
                "SELECT * FROM invocations WHERE tenant_id=? AND project_id=? AND invocation_id=?",
                (scope.tenant_id, scope.project_id, invocation.invocation_id),
            ).fetchone()
        if row is None:
            raise StoreError("invocation insert did not persist")
        return self._snapshot(row)

    def get_invocation(self, scope: Scope, invocation_id: str) -> InvocationSnapshot:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM invocations WHERE tenant_id=? AND project_id=? AND invocation_id=?",
                (scope.tenant_id, scope.project_id, invocation_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("invocation not found")
        snapshot = self._snapshot(row)
        if snapshot.scope != scope:
            raise NotFoundError("invocation not found")
        return snapshot

    def _transition_invocation(
        self,
        scope: Scope,
        invocation_id: str,
        *,
        expected_sequence: int,
        expected_state: str,
        new_state: str,
        error_code: str | None = None,
        _runtime_capability: object,
    ) -> InvocationSnapshot:
        self._assert_mutation_capability(_runtime_capability)
        if new_state not in _TRANSITIONS.get(expected_state, frozenset()):
            raise TransitionConflict(
                "invalid invocation state transition",
                details={"from": expected_state, "to": new_state},
            )
        now = _iso(utc_now())
        with self._write() as connection:
            cursor = connection.execute(
                """
                UPDATE invocations
                SET state=?, sequence=sequence+1, error_code=?, updated_at=?
                WHERE tenant_id=? AND project_id=? AND invocation_id=? AND actor_id=?
                  AND revision=? AND environment_id=? AND sequence=? AND state=?
                """,
                (
                    new_state,
                    error_code,
                    now,
                    scope.tenant_id,
                    scope.project_id,
                    invocation_id,
                    scope.actor_id,
                    scope.revision,
                    scope.environment_id,
                    expected_sequence,
                    expected_state,
                ),
            )
            if cursor.rowcount != 1:
                raise TransitionConflict("invocation CAS transition failed")
            self._append_journal_locked(
                connection,
                scope,
                "AUDIT",
                event_id=f"{invocation_id}:transition:{expected_sequence + 1}",
                kind="INVOCATION_TRANSITION",
                subject_id=invocation_id,
                payload={"from": expected_state, "to": new_state, "sequence": expected_sequence + 1, "error_code": error_code},
                created_at=now,
            )
            row = connection.execute(
                "SELECT * FROM invocations WHERE tenant_id=? AND project_id=? AND invocation_id=?",
                (scope.tenant_id, scope.project_id, invocation_id),
            ).fetchone()
        if row is None:
            raise StoreError("invocation transition disappeared")
        return self._snapshot(row)

    def _commit_result(
        self,
        scope: Scope,
        invocation_id: str,
        *,
        expected_sequence: int,
        result: HandlerResult,
        _runtime_capability: object,
    ) -> InvocationSnapshot:
        self._assert_mutation_capability(_runtime_capability)
        result_document = result.to_dict()
        result_json = canonical_json(result_document)
        result_digest = digest_object(result_document, domain="handler-result")
        now = _iso(utc_now())
        with self._write() as connection:
            current = connection.execute(
                "SELECT * FROM invocations WHERE tenant_id=? AND project_id=? AND invocation_id=?",
                (scope.tenant_id, scope.project_id, invocation_id),
            ).fetchone()
            if current is None or self._snapshot(current).scope != scope:
                raise NotFoundError("invocation not found")
            if current["skill_id"] != result.skill_id:
                raise IntegrityError("handler result skill binding mismatch", code="RESULT_SKILL_MISMATCH")
            cursor = connection.execute(
                """
                UPDATE invocations
                SET state='COMPLETED', sequence=sequence+1, result_digest=?, result_json=?, error_code=NULL, updated_at=?
                WHERE tenant_id=? AND project_id=? AND invocation_id=? AND actor_id=?
                  AND revision=? AND environment_id=? AND sequence=? AND state='PERSISTING'
                """,
                (
                    result_digest,
                    result_json,
                    now,
                    scope.tenant_id,
                    scope.project_id,
                    invocation_id,
                    scope.actor_id,
                    scope.revision,
                    scope.environment_id,
                    expected_sequence,
                ),
            )
            if cursor.rowcount != 1:
                raise TransitionConflict("result commit CAS failed")
            for evidence in result.evidence:
                self._append_journal_locked(
                    connection,
                    scope,
                    "EVIDENCE",
                    event_id=f"{invocation_id}:evidence:{evidence.evidence_id}",
                    kind="EVIDENCE_RECORDED",
                    subject_id=invocation_id,
                    payload=evidence.to_dict(),
                    created_at=now,
                )
            self._append_journal_locked(
                connection,
                scope,
                "AUDIT",
                event_id=f"{invocation_id}:completed:{expected_sequence + 1}",
                kind="INVOCATION_COMPLETED",
                subject_id=invocation_id,
                payload={"result_digest": result_digest, "status": result.status.value},
                created_at=now,
            )
            self._append_journal_locked(
                connection,
                scope,
                "OUTBOX",
                event_id=f"{invocation_id}:outbox:completed",
                kind="commercial.invocation.completed.v1",
                subject_id=invocation_id,
                payload={"invocation_id": invocation_id, "result_digest": result_digest, "status": result.status.value},
                created_at=now,
            )
            row = connection.execute(
                "SELECT * FROM invocations WHERE tenant_id=? AND project_id=? AND invocation_id=?",
                (scope.tenant_id, scope.project_id, invocation_id),
            ).fetchone()
        if row is None:
            raise StoreError("committed invocation disappeared")
        return self._snapshot(row)

    def _append_checkpoint(
        self,
        scope: Scope,
        invocation_id: str,
        payload: Mapping[str, Any],
        *,
        event_id: str,
        _runtime_capability: object,
    ) -> JournalEntry:
        self._assert_mutation_capability(_runtime_capability)
        now = _iso(utc_now())
        with self._write() as connection:
            row = connection.execute(
                "SELECT actor_id, revision, environment_id FROM invocations WHERE tenant_id=? AND project_id=? AND invocation_id=?",
                (scope.tenant_id, scope.project_id, invocation_id),
            ).fetchone()
            if row is None or (row["actor_id"], row["revision"], row["environment_id"]) != (
                scope.actor_id,
                scope.revision,
                scope.environment_id,
            ):
                raise NotFoundError("invocation not found")
            return self._append_journal_locked(
                connection,
                scope,
                "CHECKPOINT",
                event_id=event_id,
                kind="INVOCATION_CHECKPOINT",
                subject_id=invocation_id,
                payload=payload,
                created_at=now,
            )

    def latest_checkpoint(self, scope: Scope, invocation_id: str) -> JournalEntry | None:
        """Return the latest checkpoint after a bounded chain replay from local genesis.

        The securely opened SQLite database is the local trust boundary.  This
        detects partial corruption but is not an independently authenticated,
        out-of-database journal anchor.
        """

        with self._read() as connection:
            self._assert_exact_schema_locked(connection, require_version=True)
            target = connection.execute(
                """
                SELECT * FROM journal_entries
                WHERE tenant_id=? AND project_id=? AND stream='CHECKPOINT' AND subject_id=?
                ORDER BY sequence DESC LIMIT 1
                """,
                (scope.tenant_id, scope.project_id, invocation_id),
            ).fetchone()
            if target is None:
                return None
            target_sequence = int(target["sequence"])
            if target_sequence > _MAX_CHECKPOINT_CHAIN_ROWS:
                raise IntegrityError("checkpoint chain exceeds the verification limit", code="JOURNAL_CHAIN_LIMIT")
            cursor = connection.execute(
                """
                SELECT * FROM journal_entries
                WHERE tenant_id=? AND project_id=? AND stream='CHECKPOINT' AND sequence<=?
                ORDER BY sequence
                LIMIT ?
                """,
                (
                    scope.tenant_id,
                    scope.project_id,
                    target_sequence,
                    _MAX_CHECKPOINT_CHAIN_ROWS + 1,
                ),
            )
            expected_sequence = 1
            previous_digest: str | None = None
            payload_bytes = 0
            entry: JournalEntry | None = None
            for row in cursor:
                expected_sequence_before = expected_sequence
                expected_sequence += 1
                if expected_sequence_before > _MAX_CHECKPOINT_CHAIN_ROWS:
                    raise IntegrityError("checkpoint chain exceeds the verification limit", code="JOURNAL_CHAIN_LIMIT")
                current = self._journal_snapshot(row)
                payload_json = row["payload_json"]
                if not isinstance(payload_json, str):
                    raise IntegrityError("checkpoint payload storage is invalid", code="JOURNAL_PAYLOAD_TAMPERED")
                payload_bytes += len(payload_json.encode("utf-8"))
                if payload_bytes > _MAX_CHECKPOINT_CHAIN_PAYLOAD_BYTES:
                    raise IntegrityError(
                        "checkpoint chain payload exceeds the verification limit",
                        code="JOURNAL_CHAIN_LIMIT",
                    )
                if current.sequence != expected_sequence_before:
                    raise IntegrityError("checkpoint sequence gap", code="JOURNAL_SEQUENCE_INVALID")
                if current.previous_digest != previous_digest:
                    raise IntegrityError("checkpoint predecessor mismatch", code="JOURNAL_CHAIN_INVALID")
                previous_digest = current.entry_digest
                entry = current

        if entry is None or entry.sequence != target_sequence or entry.entry_digest != target["entry_digest"]:
            raise IntegrityError("checkpoint chain does not reach the selected entry", code="JOURNAL_CHAIN_INVALID")
        if entry.subject_id != invocation_id or entry.scope != scope:
            raise NotFoundError("checkpoint not found")
        return entry

    @staticmethod
    def _journal_snapshot(row: sqlite3.Row) -> JournalEntry:
        stream = row["stream"]
        if stream not in _JOURNAL_STREAMS:
            raise IntegrityError("stored journal stream is invalid", code="JOURNAL_ENTRY_TAMPERED")
        try:
            sequence = int(row["sequence"])
        except (TypeError, ValueError) as exc:
            raise IntegrityError("stored journal sequence is invalid", code="JOURNAL_SEQUENCE_INVALID") from exc
        previous_digest = row["previous_digest"]
        if sequence < 1 or (sequence == 1) != (previous_digest is None):
            raise IntegrityError("stored journal predecessor is invalid", code="JOURNAL_CHAIN_INVALID")
        payload = SQLiteControlPlaneStore._canonical_mapping(
            row["payload_json"],
            label="journal payload",
            code="JOURNAL_PAYLOAD_TAMPERED",
        )
        payload_digest = digest_object(payload, domain=f"journal-payload:{stream}")
        if payload_digest != row["payload_digest"]:
            raise IntegrityError("stored journal payload digest mismatch", code="JOURNAL_PAYLOAD_TAMPERED")
        envelope = {
            "actor_id": row["actor_id"],
            "created_at": row["created_at"],
            "environment_id": row["environment_id"],
            "event_id": row["event_id"],
            "kind": row["kind"],
            "payload_digest": payload_digest,
            "previous_digest": previous_digest,
            "project_id": row["project_id"],
            "revision": row["revision"],
            "sequence": sequence,
            "stream": stream,
            "subject_id": row["subject_id"],
            "tenant_id": row["tenant_id"],
        }
        if digest_object(envelope, domain=f"journal-entry:{stream}") != row["entry_digest"]:
            raise IntegrityError("stored journal entry digest mismatch", code="JOURNAL_ENTRY_TAMPERED")
        try:
            scope = Scope(
                tenant_id=row["tenant_id"],
                project_id=row["project_id"],
                actor_id=row["actor_id"],
                revision=row["revision"],
                environment_id=row["environment_id"],
            )
            created_at = _dt(row["created_at"])
        except (ContractError, TypeError, ValueError) as exc:
            raise IntegrityError("stored journal envelope is invalid", code="JOURNAL_ENTRY_TAMPERED") from exc
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise IntegrityError("stored journal timestamp is naive", code="JOURNAL_ENTRY_TAMPERED")
        return JournalEntry(
            scope=scope,
            stream=stream,
            sequence=sequence,
            event_id=row["event_id"],
            kind=row["kind"],
            subject_id=row["subject_id"],
            payload=payload,
            payload_digest=payload_digest,
            previous_digest=previous_digest,
            entry_digest=row["entry_digest"],
            created_at=created_at,
        )

    def _append_journal_locked(
        self,
        connection: sqlite3.Connection,
        scope: Scope,
        stream: str,
        *,
        event_id: str,
        kind: str,
        subject_id: str,
        payload: Mapping[str, Any],
        created_at: str,
    ) -> JournalEntry:
        if stream not in _JOURNAL_STREAMS:
            raise StoreError("unknown journal stream")
        previous = connection.execute(
            """
            SELECT sequence, entry_digest FROM journal_entries
            WHERE tenant_id=? AND project_id=? AND stream=?
            ORDER BY sequence DESC LIMIT 1
            """,
            (scope.tenant_id, scope.project_id, stream),
        ).fetchone()
        sequence = 1 if previous is None else int(previous["sequence"]) + 1
        previous_digest = None if previous is None else previous["entry_digest"]
        payload_document = to_jsonable(payload)
        payload_digest = digest_object(payload_document, domain=f"journal-payload:{stream}")
        envelope = {
            "actor_id": scope.actor_id,
            "created_at": created_at,
            "environment_id": scope.environment_id,
            "event_id": event_id,
            "kind": kind,
            "payload_digest": payload_digest,
            "previous_digest": previous_digest,
            "project_id": scope.project_id,
            "revision": scope.revision,
            "sequence": sequence,
            "stream": stream,
            "subject_id": subject_id,
            "tenant_id": scope.tenant_id,
        }
        entry_digest = digest_object(envelope, domain=f"journal-entry:{stream}")
        try:
            connection.execute(
                """
                INSERT INTO journal_entries(
                  tenant_id,project_id,actor_id,revision,environment_id,stream,sequence,
                  event_id,kind,subject_id,payload_json,payload_digest,previous_digest,entry_digest,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    scope.tenant_id,
                    scope.project_id,
                    scope.actor_id,
                    scope.revision,
                    scope.environment_id,
                    stream,
                    sequence,
                    event_id,
                    kind,
                    subject_id,
                    canonical_json(payload_document),
                    payload_digest,
                    previous_digest,
                    entry_digest,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise StoreError("journal append conflict") from exc
        row = connection.execute(
            "SELECT * FROM journal_entries WHERE tenant_id=? AND project_id=? AND stream=? AND sequence=?",
            (scope.tenant_id, scope.project_id, stream, sequence),
        ).fetchone()
        if row is None:
            raise StoreError("journal append did not persist")
        return self._journal_snapshot(row)

    @staticmethod
    def _bounded_stored_size(value: object, *, label: str, code: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise IntegrityError(f"stored {label} length is invalid", code=code)
        if value > _MAX_PERSISTED_DOCUMENT_BYTES:
            raise IntegrityError(f"stored {label} exceeds the document limit", code=code)
        return value

    @staticmethod
    def _schema_version_locked(connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
        if row is None:
            raise StoreError("control-plane schema version is unavailable")
        return int(row["version"])

    def _verify_scope_integrity_locked(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        project_id: str,
        *,
        max_json_bytes: int | None = None,
    ) -> tuple[dict[str, Any], int]:
        if max_json_bytes is None:
            max_json_bytes = _MAX_INTEGRITY_JSON_BYTES
        invocation_count = 0
        journal_count = 0
        total_json_bytes = 0
        invocation_metadata = connection.execute(
            """
            SELECT CASE WHEN length(CAST(invocation_id AS BLOB)) <= ? THEN invocation_id END AS invocation_id,
                   length(CAST(request_json AS BLOB)) AS request_bytes,
                   CASE WHEN result_json IS NULL THEN 0
                        ELSE length(CAST(result_json AS BLOB)) END AS result_bytes
            FROM invocations INDEXED BY idx_invocations_integrity_scan
            WHERE tenant_id=? AND project_id=?
            ORDER BY invocation_id
            LIMIT ?
            """,
            (
                _MAX_SCOPE_IDENTIFIER_BYTES,
                tenant_id,
                project_id,
                _MAX_INTEGRITY_INVOCATIONS + 1,
            ),
        )
        invocation_rows = connection.cursor()
        for metadata in invocation_metadata:
            invocation_count += 1
            if invocation_count > _MAX_INTEGRITY_INVOCATIONS:
                raise IntegrityError("invocation integrity row limit exceeded", code="STORE_INTEGRITY_LIMIT")
            request_bytes = self._bounded_stored_size(
                metadata["request_bytes"],
                label="request JSON",
                code="REQUEST_TAMPERED",
            )
            result_bytes = self._bounded_stored_size(
                metadata["result_bytes"],
                label="result JSON",
                code="RESULT_TAMPERED",
            )
            total_json_bytes += request_bytes + result_bytes
            if total_json_bytes > max_json_bytes:
                raise IntegrityError("store integrity byte limit exceeded", code="STORE_INTEGRITY_LIMIT")
            invocation_id = metadata["invocation_id"]
            if not isinstance(invocation_id, str):
                raise IntegrityError("stored invocation identifier exceeds its limit", code="INVOCATION_TAMPERED")
            row = invocation_rows.execute(
                """
                SELECT * FROM invocations INDEXED BY idx_invocations_integrity_scan
                WHERE tenant_id=? AND project_id=? AND invocation_id=?
                """,
                (tenant_id, project_id, invocation_id),
            ).fetchone()
            if row is None:
                raise IntegrityError("invocation disappeared during integrity verification", code="INVOCATION_TAMPERED")
            self._snapshot(row)

        previous_by_stream: dict[str, str | None] = {stream: None for stream in _JOURNAL_STREAMS}
        expected_sequence: dict[str, int] = {stream: 1 for stream in _JOURNAL_STREAMS}
        journal_metadata = connection.execute(
            """
            SELECT stream, sequence, length(CAST(payload_json AS BLOB)) AS payload_bytes
            FROM journal_entries INDEXED BY idx_journal_integrity_scan
            WHERE tenant_id=? AND project_id=?
            ORDER BY stream, sequence
            LIMIT ?
            """,
            (tenant_id, project_id, _MAX_INTEGRITY_JOURNAL_ENTRIES + 1),
        )
        journal_rows = connection.cursor()
        for metadata in journal_metadata:
            journal_count += 1
            if journal_count > _MAX_INTEGRITY_JOURNAL_ENTRIES:
                raise IntegrityError("journal integrity row limit exceeded", code="STORE_INTEGRITY_LIMIT")
            payload_bytes = self._bounded_stored_size(
                metadata["payload_bytes"],
                label="journal payload",
                code="JOURNAL_PAYLOAD_TAMPERED",
            )
            total_json_bytes += payload_bytes
            if total_json_bytes > max_json_bytes:
                raise IntegrityError("store integrity byte limit exceeded", code="STORE_INTEGRITY_LIMIT")
            row = journal_rows.execute(
                """
                SELECT * FROM journal_entries INDEXED BY idx_journal_integrity_scan
                WHERE tenant_id=? AND project_id=? AND stream=? AND sequence=?
                """,
                (tenant_id, project_id, metadata["stream"], metadata["sequence"]),
            ).fetchone()
            if row is None:
                raise IntegrityError("journal entry disappeared during integrity verification", code="JOURNAL_ENTRY_TAMPERED")
            entry = self._journal_snapshot(row)
            stream = entry.stream
            if entry.sequence != expected_sequence[stream]:
                raise IntegrityError("journal sequence gap", code="JOURNAL_SEQUENCE_INVALID")
            if entry.previous_digest != previous_by_stream[stream]:
                raise IntegrityError("journal chain predecessor mismatch", code="JOURNAL_CHAIN_INVALID")
            previous_by_stream[stream] = entry.entry_digest
            expected_sequence[stream] += 1

        return (
            {
                "status": "OK",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "invocations": invocation_count,
                "journal_entries": journal_count,
                "schema_version": self._schema_version_locked(connection),
            },
            total_json_bytes,
        )

    def verify_scope_integrity(self, tenant_id: str, project_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or len(tenant_id.encode("utf-8")) > _MAX_SCOPE_IDENTIFIER_BYTES:
            raise StoreError("tenant identifier is invalid", code="STORE_SCOPE_INVALID")
        if not isinstance(project_id, str) or len(project_id.encode("utf-8")) > _MAX_SCOPE_IDENTIFIER_BYTES:
            raise StoreError("project identifier is invalid", code="STORE_SCOPE_INVALID")
        with self._read() as connection:
            self._assert_exact_schema_locked(connection, require_version=True)
            report, _ = self._verify_scope_integrity_locked(connection, tenant_id, project_id)
            return report

    def verify_all_integrity(self) -> dict[str, Any]:
        with self._read() as connection:
            self._assert_exact_schema_locked(connection, require_version=True)
            discovery = connection.execute(
                """
                SELECT CASE WHEN length(CAST(tenant_id AS BLOB)) <= ? THEN tenant_id END AS tenant_id,
                       CASE WHEN length(CAST(project_id AS BLOB)) <= ? THEN project_id END AS project_id
                FROM invocations
                UNION ALL
                SELECT CASE WHEN length(CAST(tenant_id AS BLOB)) <= ? THEN tenant_id END AS tenant_id,
                       CASE WHEN length(CAST(project_id AS BLOB)) <= ? THEN project_id END AS project_id
                FROM journal_entries
                LIMIT ?
                """,
                (
                    _MAX_SCOPE_IDENTIFIER_BYTES,
                    _MAX_SCOPE_IDENTIFIER_BYTES,
                    _MAX_SCOPE_IDENTIFIER_BYTES,
                    _MAX_SCOPE_IDENTIFIER_BYTES,
                    _MAX_INTEGRITY_SCOPE_DISCOVERY_ROWS + 1,
                ),
            )
            scopes: set[tuple[str, str]] = set()
            discovery_rows = 0
            for row in discovery:
                discovery_rows += 1
                if discovery_rows > _MAX_INTEGRITY_SCOPE_DISCOVERY_ROWS:
                    raise IntegrityError("store scope discovery row limit exceeded", code="STORE_INTEGRITY_LIMIT")
                tenant_id = row["tenant_id"]
                project_id = row["project_id"]
                if not isinstance(tenant_id, str) or not isinstance(project_id, str):
                    raise IntegrityError("stored scope identifier exceeds its limit", code="STORE_SCOPE_TAMPERED")
                scopes.add((tenant_id, project_id))
                if len(scopes) > _MAX_INTEGRITY_SCOPES:
                    raise IntegrityError("store scope count limit exceeded", code="STORE_INTEGRITY_LIMIT")
            reports: list[dict[str, Any]] = []
            remaining_json_bytes = _MAX_INTEGRITY_JSON_BYTES
            for tenant_id, project_id in sorted(scopes):
                report, consumed_json_bytes = self._verify_scope_integrity_locked(
                    connection,
                    tenant_id,
                    project_id,
                    max_json_bytes=remaining_json_bytes,
                )
                reports.append(report)
                remaining_json_bytes -= consumed_json_bytes
            verified_rows = sum(
                int(report["invocations"]) + int(report["journal_entries"])
                for report in reports
            )
            if verified_rows != discovery_rows:
                raise IntegrityError("store scope discovery did not cover every row", code="STORE_INTEGRITY_COVERAGE_INVALID")
            schema_version = self._schema_version_locked(connection)
        return {
            "status": "OK",
            "schema_version": schema_version,
            "scope_count": len(reports),
            "scopes": reports,
        }


class _RuntimeStoreWriter:
    """Capability-bearing writer handed only to the authenticated runtime."""

    __slots__ = ("__capability", "__store")

    def __init__(self, store: SQLiteControlPlaneStore, capability: object) -> None:
        store._assert_mutation_capability(capability)
        self.__store = store
        self.__capability = capability

    def begin_invocation(
        self,
        invocation: Invocation,
        lease: CapabilityLease,
        inputs: Mapping[str, Any],
    ) -> InvocationSnapshot:
        return self.__store._begin_invocation(
            invocation,
            lease,
            inputs,
            _runtime_capability=self.__capability,
        )

    def transition_invocation(
        self,
        scope: Scope,
        invocation_id: str,
        *,
        expected_sequence: int,
        expected_state: str,
        new_state: str,
        error_code: str | None = None,
    ) -> InvocationSnapshot:
        return self.__store._transition_invocation(
            scope,
            invocation_id,
            expected_sequence=expected_sequence,
            expected_state=expected_state,
            new_state=new_state,
            error_code=error_code,
            _runtime_capability=self.__capability,
        )

    def commit_result(
        self,
        scope: Scope,
        invocation_id: str,
        *,
        expected_sequence: int,
        result: HandlerResult,
    ) -> InvocationSnapshot:
        return self.__store._commit_result(
            scope,
            invocation_id,
            expected_sequence=expected_sequence,
            result=result,
            _runtime_capability=self.__capability,
        )

    def append_checkpoint(
        self,
        scope: Scope,
        invocation_id: str,
        payload: Mapping[str, Any],
        *,
        event_id: str,
    ) -> JournalEntry:
        return self.__store._append_checkpoint(
            scope,
            invocation_id,
            payload,
            event_id=event_id,
            _runtime_capability=self.__capability,
        )


def _bind_runtime_writer(store: SQLiteControlPlaneStore) -> _RuntimeStoreWriter:
    """Internal bootstrap seam; supported callers never receive this writer."""

    capability = object.__getattribute__(store, "_SQLiteControlPlaneStore__mutation_capability")
    return _RuntimeStoreWriter(store, capability)


class ReadonlyControlPlaneStore:
    """Public inspection facade with no migration or mutation operations."""

    __slots__ = ("__store",)

    def __init__(self, path: str | Path) -> None:
        self.__store = SQLiteControlPlaneStore.open_readonly(path)

    @property
    def schema_version(self) -> int:
        return self.__store.schema_version

    @staticmethod
    def _redact_report(report: Mapping[str, Any]) -> dict[str, Any]:
        tenant_id = report.get("tenant_id")
        project_id = report.get("project_id")
        if not isinstance(tenant_id, str) or not isinstance(project_id, str):
            raise IntegrityError("control-plane scope report is malformed")
        return {
            "status": report.get("status"),
            "scope_digest": digest_object(
                {"project_id": project_id, "tenant_id": tenant_id},
                domain="control-plane-scope",
            ),
            "invocations": report.get("invocations"),
            "journal_entries": report.get("journal_entries"),
            "schema_version": report.get("schema_version"),
        }

    def verify_scope_integrity(self, tenant_id: str, project_id: str) -> dict[str, Any]:
        return self._redact_report(self.__store.verify_scope_integrity(tenant_id, project_id))

    def verify_all_integrity(self) -> dict[str, Any]:
        report = self.__store.verify_all_integrity()
        scopes = report.get("scopes", ())
        if not isinstance(scopes, (tuple, list)):
            raise IntegrityError("control-plane integrity report is malformed")
        return {
            "status": report.get("status"),
            "schema_version": report.get("schema_version"),
            "scope_count": report.get("scope_count"),
            "scopes": [self._redact_report(item) for item in scopes if isinstance(item, Mapping)],
        }

    def close(self) -> None:
        self.__store.close()

    def __enter__(self) -> ReadonlyControlPlaneStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
