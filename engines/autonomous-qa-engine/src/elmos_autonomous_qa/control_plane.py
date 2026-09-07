"""Durable, tenant-scoped autonomous-QA run control plane."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .canonical import (
    canonical_digest,
    canonical_json_bytes,
    parse_json_strict,
    require_sha256,
)
from .contracts import ContractError, strict_json


class ControlPlaneError(RuntimeError):
    """Base class for control-plane failures."""


class RunNotFound(ControlPlaneError):
    pass


class RunAlreadyExists(ControlPlaneError):
    pass


class IllegalTransition(ControlPlaneError):
    pass


class IdempotencyConflict(ControlPlaneError):
    pass


class EvidenceReceiptNotFound(ControlPlaneError):
    pass


class EvidenceReceiptInvalid(ControlPlaneError):
    pass


class ResourceQuotaExceeded(ControlPlaneError):
    pass


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_APPROVAL = "waiting_approval"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()


ACTIVE_STATUSES = (
    RunStatus.CREATED,
    RunStatus.RUNNING,
    RunStatus.PAUSED,
    RunStatus.WAITING_APPROVAL,
)

# Local heads detect deletion/truncation relative to this database. They are not
# an external transparency log, signature, or independent anchor.
EXTERNAL_CHAIN_ANCHOR_STATE = "NOT_RUN"
CONTROL_PLANE_SCHEMA_VERSION = 1
MAX_EVENTS_PER_RUN = 10_000
MAX_AUDIT_RECORDS_PER_RUN = 20_000
MAX_IDEMPOTENCY_RECORDS_PER_RUN = 20_000
MAX_IDEMPOTENCY_RECORDS_PER_TENANT = 100_000
MAX_IDEMPOTENCY_RECORDS_TOTAL = 200_000
MAX_RUNS_PER_TENANT = 10_000
MAX_RUNS_TOTAL = 100_000
MAX_ACTIVE_RUNS_PER_TENANT = 500
MAX_EVIDENCE_RECEIPTS_PER_RUN = 1_000
MAX_EVIDENCE_RECEIPTS_PER_TENANT = 10_000
MAX_EVIDENCE_RECEIPTS_TOTAL = 100_000
DEFAULT_HISTORY_PAGE_SIZE = 100
MAX_HISTORY_PAGE_SIZE = 500
_CONTROL_PLANE_TABLES = (
    "qa_runs",
    "qa_events",
    "qa_audit",
    "qa_idempotency",
    "qa_verified_evidence",
    "qa_chain_heads",
)
RUN_MODES = frozenset(
    {"plan-only", "generate", "verify", "repair", "certify", "continuous"}
)

_TRANSITIONS: dict[str, dict[RunStatus, RunStatus]] = {
    "start": {RunStatus.CREATED: RunStatus.RUNNING},
    "begin_materialization": {RunStatus.RUNNING: RunStatus.RUNNING},
    "begin_publishing": {RunStatus.RUNNING: RunStatus.RUNNING},
    "pause": {RunStatus.RUNNING: RunStatus.PAUSED},
    "resume": {RunStatus.PAUSED: RunStatus.RUNNING},
    "cancel": {
        RunStatus.CREATED: RunStatus.CANCELLED,
        RunStatus.RUNNING: RunStatus.CANCELLED,
        RunStatus.PAUSED: RunStatus.CANCELLED,
        RunStatus.WAITING_APPROVAL: RunStatus.CANCELLED,
    },
    "request_approval": {RunStatus.RUNNING: RunStatus.WAITING_APPROVAL},
    "approve": {RunStatus.WAITING_APPROVAL: RunStatus.RUNNING},
    "fail": {
        RunStatus.CREATED: RunStatus.FAILED,
        RunStatus.RUNNING: RunStatus.FAILED,
        RunStatus.PAUSED: RunStatus.FAILED,
        RunStatus.WAITING_APPROVAL: RunStatus.FAILED,
    },
    "complete": {RunStatus.RUNNING: RunStatus.COMPLETED},
}

OBSERVATION_KINDS = frozenset(
    {
        "worker-heartbeat",
        "shard-result",
        "progress",
        "budget",
        "eta",
        "checkpoint",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _timestamp(value: str, field: str) -> str:
    value = _identifier(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware timestamp")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise ValueError(f"{field} must be a non-empty identifier of at most 256 bytes")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{field} contains a control character")
    return value


def _stored_json_bytes(value: Any, field: str) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise ControlPlaneError(f"{field} has an invalid storage type")


def _bounded_json_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a JSON object")
    try:
        normalized = strict_json(value, field)
    except (ContractError, RecursionError) as exc:
        raise ValueError(f"{field} is not bounded canonical JSON") from exc
    if not isinstance(normalized, dict):
        raise ValueError(f"{field} must be a JSON object")
    return normalized


@dataclass(frozen=True, slots=True)
class QaRun:
    tenant_id: str
    run_id: str
    project_id: str
    mode: str
    status: RunStatus
    input_digest: str
    payload: Mapping[str, Any]
    attempt: int
    retry_of: str | None
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class QaEvent:
    tenant_id: str
    run_id: str
    sequence: int
    kind: str
    payload: Mapping[str, Any]
    previous_digest: str | None
    event_digest: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class AuditRecord:
    audit_id: int
    tenant_id: str
    run_id: str
    actor: str
    action: str
    outcome: str
    details: Mapping[str, Any]
    previous_digest: str | None
    record_digest: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceReceipt:
    tenant_id: str
    receipt_id: str
    run_id: str
    scope: str
    subject_digest: str
    evidence_digest: str
    artifact_digest: str
    authorization_ref: str
    executor_id: str
    verifier_id: str
    valid_until: str
    approval_request_digest: str
    approval_run_version: int
    revoked: bool
    consumed_at: str | None
    consumed_by: str | None
    consumption_digest: str | None
    created_at: str


class QaControlPlane:
    """SQLite-backed run state, event, audit, and idempotency authority.

    Each public lookup requires ``tenant_id``. A retry creates a new run
    identity and links it to the terminal source run; it never rewinds history.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30, factory=_ClosingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _table_columns(
        connection: sqlite3.Connection, table: str
    ) -> dict[str, sqlite3.Row]:
        return {
            str(row["name"]): row
            for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        }

    @staticmethod
    def _idempotency_record_digest(
        *,
        tenant_id: str,
        idempotency_key: str,
        command: str,
        request_digest: str,
        response: Mapping[str, Any],
        created_at: str,
    ) -> str:
        return canonical_digest(
            {
                "tenant_id": tenant_id,
                "idempotency_key": idempotency_key,
                "command": command,
                "request_digest": request_digest,
                "response": dict(response),
                "created_at": created_at,
            }
        )

    @staticmethod
    def _create_run_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_runs (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                input_digest TEXT NOT NULL,
                payload_json BLOB NOT NULL,
                attempt INTEGER NOT NULL CHECK (attempt >= 1),
                retry_of TEXT,
                version INTEGER NOT NULL CHECK (version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id)
            )
            """
        )

    @staticmethod
    def _create_event_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS qa_events (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                kind TEXT NOT NULL,
                payload_json BLOB NOT NULL,
                previous_digest TEXT,
                event_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id, sequence),
                FOREIGN KEY (tenant_id, run_id)
                    REFERENCES qa_runs (tenant_id, run_id) ON DELETE RESTRICT
            )
            """
        )

    @staticmethod
    def _create_audit_table(
        connection: sqlite3.Connection, *, table: str = "qa_audit"
    ) -> None:
        if table not in {"qa_audit", "qa_audit_migrating"}:
            raise ControlPlaneError("invalid internal audit table name")
        connection.execute(
            f"""
            CREATE TABLE {table} (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                outcome TEXT NOT NULL,
                details_json BLOB NOT NULL,
                previous_digest TEXT,
                record_digest TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY (tenant_id, run_id)
                    REFERENCES qa_runs (tenant_id, run_id) ON DELETE RESTRICT
            )
            """
        )

    @staticmethod
    def _create_idempotency_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE qa_idempotency (
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                command TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                response_json BLOB NOT NULL,
                response_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, idempotency_key)
            )
            """
        )

    @staticmethod
    def _create_evidence_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE qa_verified_evidence (
                tenant_id TEXT NOT NULL,
                receipt_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                subject_digest TEXT NOT NULL,
                evidence_digest TEXT NOT NULL,
                artifact_digest TEXT NOT NULL,
                authorization_ref TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                verifier_id TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                approval_request_digest TEXT NOT NULL,
                approval_run_version INTEGER NOT NULL
                    CHECK (approval_run_version >= 1),
                revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)),
                consumed_at TEXT,
                consumed_by TEXT,
                consumption_digest TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, receipt_id),
                FOREIGN KEY (tenant_id, run_id)
                    REFERENCES qa_runs (tenant_id, run_id) ON DELETE RESTRICT,
                CHECK (
                    (consumed_at IS NULL AND consumed_by IS NULL
                        AND consumption_digest IS NULL)
                    OR
                    (consumed_at IS NOT NULL AND consumed_by IS NOT NULL
                        AND consumption_digest IS NOT NULL)
                )
            )
            """
        )

    @staticmethod
    def _create_chain_head_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE qa_chain_heads (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                event_sequence INTEGER NOT NULL CHECK (event_sequence >= 0),
                event_digest TEXT,
                audit_id INTEGER NOT NULL CHECK (audit_id >= 0),
                audit_digest TEXT,
                external_anchor_state TEXT NOT NULL
                    CHECK (external_anchor_state = 'NOT_RUN'),
                PRIMARY KEY (tenant_id, run_id),
                FOREIGN KEY (tenant_id, run_id)
                    REFERENCES qa_runs (tenant_id, run_id) ON DELETE RESTRICT
            )
            """
        )

    @staticmethod
    def _has_run_foreign_key(
        connection: sqlite3.Connection, table: str
    ) -> bool:
        if table not in {
            "qa_events",
            "qa_audit",
            "qa_verified_evidence",
            "qa_chain_heads",
        }:
            raise ControlPlaneError("invalid internal foreign-key table name")
        rows = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        groups: dict[int, set[tuple[str, str, str, str, str]]] = {}
        for row in rows:
            groups.setdefault(int(row["id"]), set()).add(
                (
                    str(row["table"]),
                    str(row["from"]),
                    str(row["to"]),
                    str(row["on_update"]),
                    str(row["on_delete"]),
                )
            )
        expected = {
            ("qa_runs", "tenant_id", "tenant_id", "NO ACTION", "RESTRICT"),
            ("qa_runs", "run_id", "run_id", "NO ACTION", "RESTRICT"),
        }
        return any(bindings == expected for bindings in groups.values())

    @staticmethod
    def _normalized_schema_sql(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlPlaneError("versioned control-plane table SQL is missing")
        normalized = " ".join(value.split()).rstrip(";")
        for table in _CONTROL_PLANE_TABLES:
            normalized = normalized.replace(f'"{table}"', table)
        return normalized

    @classmethod
    def _schema_sql_fingerprint(cls, connection: sqlite3.Connection) -> str:
        placeholders = ",".join("?" for _ in _CONTROL_PLANE_TABLES)
        rows = connection.execute(
            f"SELECT name, sql FROM sqlite_master WHERE type = 'table' "
            f"AND name IN ({placeholders}) ORDER BY name",
            _CONTROL_PLANE_TABLES,
        )
        definitions = {
            str(row["name"]): cls._normalized_schema_sql(row["sql"])
            for row in rows
        }
        if set(definitions) != set(_CONTROL_PLANE_TABLES):
            raise ControlPlaneError("versioned control-plane table set is incomplete")
        explicit_index = connection.execute(
            f"SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL "
            f"AND tbl_name IN ({placeholders}) LIMIT 1",
            _CONTROL_PLANE_TABLES,
        ).fetchone()
        if explicit_index is not None:
            raise ControlPlaneError(
                "versioned control-plane schema contains an untrusted index"
            )
        return canonical_digest(definitions)

    @classmethod
    def _expected_schema_sql_fingerprint(cls) -> str:
        reference = sqlite3.connect(":memory:")
        reference.row_factory = sqlite3.Row
        try:
            cls._create_run_table(reference)
            cls._create_event_table(reference)
            cls._create_audit_table(reference)
            cls._create_idempotency_table(reference)
            cls._create_evidence_table(reference)
            cls._create_chain_head_table(reference)
            return cls._schema_sql_fingerprint(reference)
        finally:
            reference.close()

    @classmethod
    def _assert_versioned_schema(cls, connection: sqlite3.Connection) -> None:
        columns_by_table = {
            "qa_runs": {
                "tenant_id", "run_id", "project_id", "mode", "status",
                "input_digest", "payload_json", "attempt", "retry_of",
                "version", "created_at", "updated_at",
            },
            "qa_events": {
                "tenant_id", "run_id", "sequence", "kind", "payload_json",
                "previous_digest", "event_digest", "occurred_at",
            },
            "qa_audit": {
                "audit_id", "tenant_id", "run_id", "actor", "action",
                "outcome", "details_json", "previous_digest",
                "record_digest", "occurred_at",
            },
            "qa_idempotency": {
                "tenant_id", "idempotency_key", "command", "request_digest",
                "response_json", "response_digest", "created_at",
            },
            "qa_verified_evidence": {
                "tenant_id", "receipt_id", "run_id", "scope",
                "subject_digest", "evidence_digest", "artifact_digest",
                "authorization_ref", "executor_id", "verifier_id",
                "valid_until", "approval_request_digest",
                "approval_run_version", "revoked", "consumed_at",
                "consumed_by", "consumption_digest", "created_at",
            },
            "qa_chain_heads": {
                "tenant_id", "run_id", "event_sequence", "event_digest",
                "audit_id", "audit_digest", "external_anchor_state",
            },
        }
        primary_keys = {
            "qa_runs": ("tenant_id", "run_id"),
            "qa_events": ("tenant_id", "run_id", "sequence"),
            "qa_audit": ("audit_id",),
            "qa_idempotency": ("tenant_id", "idempotency_key"),
            "qa_verified_evidence": ("tenant_id", "receipt_id"),
            "qa_chain_heads": ("tenant_id", "run_id"),
        }
        blob_columns = {
            "payload_json",
            "details_json",
            "response_json",
        }
        integer_columns = {
            "attempt",
            "version",
            "sequence",
            "audit_id",
            "approval_run_version",
            "revoked",
            "event_sequence",
        }
        nullable_columns = {
            "qa_runs": {"retry_of"},
            "qa_events": {"previous_digest"},
            "qa_audit": {"audit_id", "previous_digest"},
            "qa_idempotency": set(),
            "qa_verified_evidence": {
                "consumed_at",
                "consumed_by",
                "consumption_digest",
            },
            "qa_chain_heads": {"event_digest", "audit_digest"},
        }
        for table, expected_columns in columns_by_table.items():
            columns = cls._table_columns(connection, table)
            if set(columns) != expected_columns:
                raise ControlPlaneError(f"versioned {table} schema is not exact")
            observed_primary_key = tuple(
                name
                for name, row in sorted(
                    columns.items(), key=lambda item: int(item[1]["pk"] or 0)
                )
                if int(row["pk"] or 0) > 0
            )
            if observed_primary_key != primary_keys[table]:
                raise ControlPlaneError(
                    f"versioned {table} primary key is invalid"
                )
            for name, row in columns.items():
                expected_type = (
                    "BLOB"
                    if name in blob_columns
                    else "INTEGER"
                    if name in integer_columns
                    else "TEXT"
                )
                if str(row["type"]).upper() != expected_type:
                    raise ControlPlaneError(
                        f"versioned {table}.{name} storage type is invalid"
                    )
                expected_not_null = name not in nullable_columns[table]
                if bool(row["notnull"]) != expected_not_null:
                    raise ControlPlaneError(
                        f"versioned {table}.{name} nullability is invalid"
                    )
        for table in (
            "qa_events",
            "qa_audit",
            "qa_verified_evidence",
            "qa_chain_heads",
        ):
            if not cls._has_run_foreign_key(connection, table):
                raise ControlPlaneError(
                    f"versioned {table} run foreign key is invalid"
                )
        table_names = tuple(columns_by_table)
        placeholders = ",".join("?" for _ in table_names)
        unexpected_trigger = connection.execute(
            f"SELECT name FROM sqlite_master WHERE type = 'trigger' "
            f"AND tbl_name IN ({placeholders}) LIMIT 1",
            table_names,
        ).fetchone()
        if unexpected_trigger is not None:
            raise ControlPlaneError(
                "versioned control-plane schema contains an untrusted trigger"
            )
        if (
            cls._schema_sql_fingerprint(connection)
            != cls._expected_schema_sql_fingerprint()
        ):
            raise ControlPlaneError(
                "versioned control-plane SQL definitions are not exact"
            )

    @classmethod
    def _validated_idempotency_rows(
        cls,
        connection: sqlite3.Connection,
        *,
        allow_legacy_digest: bool,
    ) -> list[tuple[Any, ...]]:
        columns = cls._table_columns(connection, "qa_idempotency")
        required = {
            "tenant_id",
            "idempotency_key",
            "command",
            "request_digest",
            "response_json",
            "created_at",
        }
        if not required.issubset(columns):
            raise ControlPlaneError("legacy idempotency schema is incomplete")
        has_digest = "response_digest" in columns
        select = (
            "SELECT tenant_id, idempotency_key, command, request_digest, "
            "response_json, created_at"
            + (", response_digest" if has_digest else "")
            + " FROM qa_idempotency ORDER BY tenant_id, idempotency_key"
        )
        migrated: list[tuple[Any, ...]] = []
        tenant_counts: dict[str, int] = {}
        for row in connection.execute(select):
            if len(migrated) >= MAX_IDEMPOTENCY_RECORDS_TOTAL:
                raise ResourceQuotaExceeded(
                    "stored idempotency records exceed the database quota"
                )
            try:
                tenant_id = _identifier(row["tenant_id"], "stored idempotency tenant_id")
                idempotency_key = _identifier(
                    row["idempotency_key"], "stored idempotency key"
                )
                command = _identifier(row["command"], "stored idempotency command")
                request_digest = require_sha256(
                    row["request_digest"], field="stored idempotency request_digest"
                )
                raw_created_at = row["created_at"]
                created_at = _timestamp(raw_created_at, "stored idempotency created_at")
                if created_at != raw_created_at:
                    raise ValueError("stored idempotency timestamp is not canonical")
                raw = _stored_json_bytes(
                    row["response_json"], "stored idempotency response"
                )
                response = parse_json_strict(raw)
            except (TypeError, ValueError) as exc:
                raise ControlPlaneError("stored idempotency record is invalid") from exc
            if not isinstance(response, dict) or canonical_json_bytes(response) != raw:
                raise ControlPlaneError(
                    "stored idempotency response is not canonical JSON"
                )
            tenant_count = tenant_counts.get(tenant_id, 0)
            if tenant_count >= MAX_IDEMPOTENCY_RECORDS_PER_TENANT:
                raise ResourceQuotaExceeded(
                    "stored tenant idempotency records exceed their quota"
                )
            tenant_counts[tenant_id] = tenant_count + 1
            cls._validate_idempotency_response(
                response,
                expected_tenant_id=tenant_id,
                expected_command=command,
            )
            if has_digest and row["response_digest"] is not None:
                try:
                    observed = require_sha256(
                        row["response_digest"],
                        field="legacy idempotency response_digest",
                    )
                except (TypeError, ValueError) as exc:
                    raise ControlPlaneError(
                        "legacy idempotency response digest is invalid"
                    ) from exc
                legacy_digest = canonical_digest(response)
                envelope_digest = cls._idempotency_record_digest(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    command=command,
                    request_digest=request_digest,
                    response=response,
                    created_at=created_at,
                )
                allowed_digests = {envelope_digest}
                if allow_legacy_digest:
                    allowed_digests.add(legacy_digest)
                if observed not in allowed_digests:
                    raise ControlPlaneError(
                        "legacy idempotency response digest verification failed"
                    )
            response_digest = cls._idempotency_record_digest(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command=command,
                request_digest=request_digest,
                response=response,
                created_at=created_at,
            )
            migrated.append(
                (
                    tenant_id,
                    idempotency_key,
                    command,
                    request_digest,
                    raw,
                    response_digest,
                    created_at,
                )
            )
            if not allow_legacy_digest and (
                not has_digest or row["response_digest"] is None
            ):
                raise ControlPlaneError(
                    "versioned idempotency response digest is missing"
                )
        return migrated

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("BEGIN IMMEDIATE")
            try:
                schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if schema_version not in {0, CONTROL_PLANE_SCHEMA_VERSION}:
                    raise ControlPlaneError(
                        f"unsupported control-plane schema version: {schema_version}"
                    )
                tables = {
                    str(row["name"])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                required_tables = {
                    "qa_runs",
                    "qa_events",
                    "qa_audit",
                    "qa_idempotency",
                    "qa_verified_evidence",
                    "qa_chain_heads",
                }
                if (
                    schema_version == CONTROL_PLANE_SCHEMA_VERSION
                    and not required_tables.issubset(tables)
                ):
                    raise ControlPlaneError("versioned control-plane schema is incomplete")
                if schema_version == CONTROL_PLANE_SCHEMA_VERSION:
                    self._assert_versioned_schema(connection)
                if {"qa_audit_migrating"} & tables:
                    raise ControlPlaneError("incomplete audit migration table is present")

                chain_head_table_existed = "qa_chain_heads" in tables
                audit_table_existed = "qa_audit" in tables
                idempotency_table_existed = "qa_idempotency" in tables
                evidence_table_existed = "qa_verified_evidence" in tables

                if schema_version == 0:
                    legacy_required_columns = {
                        "qa_runs": {
                            "tenant_id", "run_id", "project_id", "mode", "status",
                            "input_digest", "payload_json", "attempt", "retry_of",
                            "version", "created_at", "updated_at",
                        },
                        "qa_events": {
                            "tenant_id", "run_id", "sequence", "kind", "payload_json",
                            "previous_digest", "event_digest", "occurred_at",
                        },
                        "qa_chain_heads": {
                            "tenant_id", "run_id", "event_sequence", "event_digest",
                            "audit_id", "audit_digest", "external_anchor_state",
                        },
                        "qa_verified_evidence": {
                            "tenant_id", "receipt_id", "run_id", "scope",
                            "subject_digest", "evidence_digest", "artifact_digest",
                            "authorization_ref", "executor_id", "verifier_id",
                            "valid_until", "revoked", "created_at",
                        },
                    }
                    for table, required_columns in legacy_required_columns.items():
                        if table in tables and not required_columns.issubset(
                            self._table_columns(connection, table)
                        ):
                            raise ControlPlaneError(
                                f"legacy {table} schema is incomplete"
                            )

                if (
                    schema_version == 0
                    and "qa_runs" in tables
                    and not audit_table_existed
                    and connection.execute("SELECT 1 FROM qa_runs LIMIT 1").fetchone()
                    is not None
                ):
                    raise ControlPlaneError(
                        "legacy runs without an audit table cannot be safely migrated"
                    )

                if schema_version == 0 and audit_table_existed:
                    audit_columns = self._table_columns(connection, "qa_audit")
                    audit_count = int(
                        connection.execute("SELECT COUNT(*) FROM qa_audit").fetchone()[0]
                    )
                    required_audit = {
                        "audit_id",
                        "tenant_id",
                        "run_id",
                        "actor",
                        "action",
                        "outcome",
                        "details_json",
                        "record_digest",
                        "occurred_at",
                    }
                    if not required_audit.issubset(audit_columns):
                        raise ControlPlaneError("legacy audit schema is incomplete")
                    if audit_count and "previous_digest" not in audit_columns:
                        raise ControlPlaneError(
                            "legacy audit records cannot be safely re-chained"
                        )

                evidence_columns: dict[str, sqlite3.Row] = {}
                if evidence_table_existed:
                    evidence_columns = self._table_columns(
                        connection, "qa_verified_evidence"
                    )
                    binding_columns = {
                        "approval_request_digest",
                        "approval_run_version",
                        "consumed_at",
                        "consumed_by",
                        "consumption_digest",
                    }
                    if not binding_columns.issubset(evidence_columns):
                        evidence_count = int(
                            connection.execute(
                                "SELECT COUNT(*) FROM qa_verified_evidence"
                            ).fetchone()[0]
                        )
                        if evidence_count:
                            raise ControlPlaneError(
                                "legacy evidence receipts lack exact approval binding"
                            )
                        if schema_version == CONTROL_PLANE_SCHEMA_VERSION:
                            raise ControlPlaneError(
                                "versioned evidence schema is incomplete"
                            )
                    if schema_version == CONTROL_PLANE_SCHEMA_VERSION and any(
                        int(evidence_columns[column]["notnull"]) != 1
                        for column in (
                            "approval_request_digest",
                            "approval_run_version",
                            "revoked",
                        )
                    ):
                        raise ControlPlaneError(
                            "versioned evidence binding columns are nullable"
                        )

                migrated_idempotency: list[tuple[Any, ...]] = []
                if schema_version == 0 and idempotency_table_existed:
                    migrated_idempotency = self._validated_idempotency_rows(
                        connection, allow_legacy_digest=True
                    )

                self._create_run_table(connection)
                self._create_event_table(connection)

                if not audit_table_existed:
                    self._create_audit_table(connection)
                elif schema_version == 0:
                    audit_columns = self._table_columns(connection, "qa_audit")
                    if "previous_digest" not in audit_columns:
                        connection.execute(
                            "ALTER TABLE qa_audit ADD COLUMN previous_digest TEXT"
                        )
                    if not self._has_run_foreign_key(connection, "qa_audit"):
                        orphan = connection.execute(
                            "SELECT 1 FROM qa_audit AS audit "
                            "LEFT JOIN qa_runs AS run ON run.tenant_id = audit.tenant_id "
                            "AND run.run_id = audit.run_id WHERE run.run_id IS NULL LIMIT 1"
                        ).fetchone()
                        if orphan is not None:
                            raise ControlPlaneError("legacy audit contains an orphan record")
                        self._create_audit_table(
                            connection, table="qa_audit_migrating"
                        )
                        connection.execute(
                            "INSERT INTO qa_audit_migrating "
                            "(audit_id, tenant_id, run_id, actor, action, outcome, "
                            "details_json, previous_digest, record_digest, occurred_at) "
                            "SELECT audit_id, tenant_id, run_id, actor, action, outcome, "
                            "details_json, previous_digest, record_digest, occurred_at "
                            "FROM qa_audit ORDER BY audit_id"
                        )
                        connection.execute("DROP TABLE qa_audit")
                        connection.execute(
                            "ALTER TABLE qa_audit_migrating RENAME TO qa_audit"
                        )
                elif not self._has_run_foreign_key(connection, "qa_audit"):
                    raise ControlPlaneError("versioned audit foreign key is missing")

                if idempotency_table_existed and schema_version == 0:
                    connection.execute("DROP TABLE qa_idempotency")
                    self._create_idempotency_table(connection)
                    connection.executemany(
                        "INSERT INTO qa_idempotency "
                        "(tenant_id, idempotency_key, command, request_digest, "
                        "response_json, response_digest, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        migrated_idempotency,
                    )
                elif not idempotency_table_existed:
                    self._create_idempotency_table(connection)
                else:
                    idempotency_columns = self._table_columns(
                        connection, "qa_idempotency"
                    )
                    if (
                        "response_digest" not in idempotency_columns
                        or int(idempotency_columns["response_digest"]["notnull"]) != 1
                    ):
                        raise ControlPlaneError(
                            "versioned idempotency schema is not strict"
                        )

                if evidence_table_existed and not {
                    "approval_request_digest",
                    "approval_run_version",
                    "consumed_at",
                    "consumed_by",
                    "consumption_digest",
                }.issubset(evidence_columns):
                    connection.execute("DROP TABLE qa_verified_evidence")
                    self._create_evidence_table(connection)
                elif not evidence_table_existed:
                    self._create_evidence_table(connection)

                if not chain_head_table_existed:
                    self._create_chain_head_table(connection)

                self._assert_versioned_schema(connection)
                runs = connection.execute(
                    "SELECT * FROM qa_runs ORDER BY tenant_id, run_id"
                )
                run_count = 0
                tenant_run_counts: dict[str, int] = {}
                tenant_active_run_counts: dict[str, int] = {}
                for run in runs:
                    if run_count >= MAX_RUNS_TOTAL:
                        raise ResourceQuotaExceeded(
                            "stored runs exceed the database quota"
                        )
                    validated_run = self._run_from_row(run)
                    tenant_id = validated_run.tenant_id
                    run_id = validated_run.run_id
                    tenant_run_count = tenant_run_counts.get(tenant_id, 0)
                    if tenant_run_count >= MAX_RUNS_PER_TENANT:
                        raise ResourceQuotaExceeded(
                            "stored tenant runs exceed their quota"
                        )
                    tenant_run_counts[tenant_id] = tenant_run_count + 1
                    if validated_run.status in ACTIVE_STATUSES:
                        active_count = tenant_active_run_counts.get(tenant_id, 0)
                        if active_count >= MAX_ACTIVE_RUNS_PER_TENANT:
                            raise ResourceQuotaExceeded(
                                "stored tenant active runs exceed their quota"
                            )
                        tenant_active_run_counts[tenant_id] = active_count + 1
                    run_count += 1
                    events = self._validated_event_chain(
                        connection,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        verify_head=False,
                    )
                    audit = self._validated_audit_chain(
                        connection,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        verify_head=False,
                    )
                    event_sequence = events[-1].sequence if events else 0
                    event_digest = events[-1].event_digest if events else None
                    audit_id = audit[-1].audit_id if audit else 0
                    audit_digest = audit[-1].record_digest if audit else None
                    head = connection.execute(
                        "SELECT * FROM qa_chain_heads "
                        "WHERE tenant_id = ? AND run_id = ?",
                        (tenant_id, run_id),
                    ).fetchone()
                    if head is None:
                        if chain_head_table_existed:
                            raise ControlPlaneError("stored run chain head is missing")
                        connection.execute(
                            "INSERT INTO qa_chain_heads "
                            "(tenant_id, run_id, event_sequence, event_digest, audit_id, "
                            "audit_digest, external_anchor_state) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                tenant_id,
                                run_id,
                                event_sequence,
                                event_digest,
                                audit_id,
                                audit_digest,
                                EXTERNAL_CHAIN_ANCHOR_STATE,
                            ),
                        )
                    else:
                        self._verify_chain_head_values(
                            head,
                            event_sequence=event_sequence,
                            event_digest=event_digest,
                            audit_id=audit_id,
                            audit_digest=audit_digest,
                        )
                evidence_count = 0
                tenant_evidence_counts: dict[str, int] = {}
                run_evidence_counts: dict[tuple[str, str], int] = {}
                for row in connection.execute(
                    "SELECT * FROM qa_verified_evidence "
                    "ORDER BY tenant_id, receipt_id"
                ):
                    if evidence_count >= MAX_EVIDENCE_RECEIPTS_TOTAL:
                        raise ResourceQuotaExceeded(
                            "stored evidence receipts exceed the database quota"
                        )
                    receipt = self._receipt_from_row(row)
                    tenant_evidence_count = tenant_evidence_counts.get(
                        receipt.tenant_id, 0
                    )
                    run_key = (receipt.tenant_id, receipt.run_id)
                    run_evidence_count = run_evidence_counts.get(run_key, 0)
                    if tenant_evidence_count >= MAX_EVIDENCE_RECEIPTS_PER_TENANT:
                        raise ResourceQuotaExceeded(
                            "stored tenant evidence receipts exceed their quota"
                        )
                    if run_evidence_count >= MAX_EVIDENCE_RECEIPTS_PER_RUN:
                        raise ResourceQuotaExceeded(
                            "stored run evidence receipts exceed their quota"
                        )
                    tenant_evidence_counts[receipt.tenant_id] = (
                        tenant_evidence_count + 1
                    )
                    run_evidence_counts[run_key] = run_evidence_count + 1
                    evidence_count += 1
                    receipt_audit = self._validated_audit_chain(
                        connection,
                        tenant_id=receipt.tenant_id,
                        run_id=receipt.run_id,
                    )
                    self._validate_receipt_audit_binding(receipt, receipt_audit)
                self._validated_idempotency_rows(
                    connection, allow_legacy_digest=False
                )
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ControlPlaneError(
                        "control-plane foreign-key integrity verification failed"
                    )
                connection.execute(
                    f"PRAGMA user_version = {CONTROL_PLANE_SCHEMA_VERSION}"
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _validated_run(
        *,
        tenant_id: Any,
        run_id: Any,
        project_id: Any,
        mode: Any,
        status: Any,
        input_digest: Any,
        payload: Any,
        attempt: Any,
        retry_of: Any,
        version: Any,
        created_at: Any,
        updated_at: Any,
    ) -> QaRun:
        try:
            tenant_id = _identifier(tenant_id, "stored run tenant_id")
            run_id = _identifier(run_id, "stored run run_id")
            project_id = _identifier(project_id, "stored run project_id")
            if not isinstance(mode, str) or mode not in RUN_MODES:
                raise ValueError("stored run mode is invalid")
            if not isinstance(status, str):
                raise ValueError("stored run status is invalid")
            run_status = RunStatus(status)
            input_digest = require_sha256(
                input_digest, field="stored run input_digest"
            )
            if not isinstance(payload, dict):
                raise ValueError("stored run payload is not an object")
            if canonical_digest(payload) != input_digest:
                raise ValueError("stored run input digest does not match its payload")
            if type(attempt) is not int or attempt < 1:
                raise ValueError("stored run attempt is invalid")
            if retry_of is not None:
                retry_of = _identifier(retry_of, "stored run retry_of")
            if (attempt == 1) != (retry_of is None):
                raise ValueError("stored run attempt and retry_of are inconsistent")
            if type(version) is not int or version < 1:
                raise ValueError("stored run version is invalid")
            raw_created_at = created_at
            raw_updated_at = updated_at
            created_at = _timestamp(created_at, "stored run created_at")
            updated_at = _timestamp(updated_at, "stored run updated_at")
            if created_at != raw_created_at or updated_at != raw_updated_at:
                raise ValueError("stored run timestamps are not canonical UTC timestamps")
            created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            updated_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if updated_time < created_time:
                raise ValueError("stored run timestamps are inconsistent")
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored run record is invalid") from exc
        return QaRun(
            tenant_id=tenant_id,
            run_id=run_id,
            project_id=project_id,
            mode=mode,
            status=run_status,
            input_digest=input_digest,
            payload=payload,
            attempt=attempt,
            retry_of=retry_of,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
        )

    @classmethod
    def _run_from_row(cls, row: sqlite3.Row) -> QaRun:
        raw = _stored_json_bytes(row["payload_json"], "stored run payload")
        try:
            payload = parse_json_strict(raw)
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored run payload is invalid") from exc
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
            raise ControlPlaneError("stored run payload is not canonical JSON")
        return cls._validated_run(
            tenant_id=row["tenant_id"],
            run_id=row["run_id"],
            project_id=row["project_id"],
            mode=row["mode"],
            status=row["status"],
            input_digest=row["input_digest"],
            payload=payload,
            attempt=row["attempt"],
            retry_of=row["retry_of"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _run_response(run: QaRun) -> dict[str, Any]:
        return {
            "tenant_id": run.tenant_id,
            "run_id": run.run_id,
            "project_id": run.project_id,
            "mode": run.mode,
            "status": run.status.value,
            "input_digest": run.input_digest,
            "payload": dict(run.payload),
            "attempt": run.attempt,
            "retry_of": run.retry_of,
            "version": run.version,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }

    @classmethod
    def _response_run(cls, response: Mapping[str, Any]) -> QaRun:
        required = {
            "tenant_id",
            "run_id",
            "project_id",
            "mode",
            "status",
            "input_digest",
            "payload",
            "attempt",
            "retry_of",
            "version",
            "created_at",
            "updated_at",
        }
        if set(response) != required:
            raise ControlPlaneError("stored idempotency run response is ambiguous")
        return cls._validated_run(
            tenant_id=response["tenant_id"],
            run_id=response["run_id"],
            project_id=response["project_id"],
            mode=response["mode"],
            status=response["status"],
            input_digest=response["input_digest"],
            payload=response["payload"],
            attempt=response["attempt"],
            retry_of=response["retry_of"],
            version=response["version"],
            created_at=response["created_at"],
            updated_at=response["updated_at"],
        )

    @classmethod
    def _validate_idempotency_response(
        cls,
        response: Mapping[str, Any],
        *,
        expected_tenant_id: str | None = None,
        expected_run_id: str | None = None,
        expected_command: str | None = None,
    ) -> None:
        transition_action: str | None = None
        observation_kind: str | None = None
        if expected_command is not None:
            if expected_command.startswith("transition:"):
                transition_action = expected_command.removeprefix("transition:")
                if transition_action not in _TRANSITIONS:
                    raise ControlPlaneError(
                        "stored idempotency transition command is invalid"
                    )
            elif expected_command.startswith("observation:"):
                observation_kind = expected_command.removeprefix("observation:")
                if observation_kind not in OBSERVATION_KINDS:
                    raise ControlPlaneError(
                        "stored idempotency observation command is invalid"
                    )
            elif expected_command not in {"create", "retry"}:
                raise ControlPlaneError("stored idempotency command is invalid")
        if "_error_type" not in response:
            run = cls._response_run(response)
            if expected_tenant_id is not None and run.tenant_id != expected_tenant_id:
                raise ControlPlaneError(
                    "stored idempotency response crosses the tenant boundary"
                )
            if expected_run_id is not None and run.run_id != expected_run_id:
                raise ControlPlaneError(
                    "stored idempotency response is bound to a different run"
                )
            if expected_command in {"create", "retry"} and run.status is not RunStatus.CREATED:
                raise ControlPlaneError(
                    "stored idempotency creation response has an invalid status"
                )
            if transition_action is not None:
                expected_statuses = set(_TRANSITIONS[transition_action].values())
                if run.status not in expected_statuses:
                    raise ControlPlaneError(
                        "stored idempotency transition response has an invalid status"
                    )
            if observation_kind is not None and run.status not in ACTIVE_STATUSES:
                raise ControlPlaneError(
                    "stored idempotency observation response has an invalid status"
                )
            return
        if set(response) != {"_error_type", "error_code"}:
            raise ControlPlaneError("stored idempotency error response is ambiguous")
        if response.get("_error_type") != "IllegalTransition":
            raise ControlPlaneError("stored idempotency error type is invalid")
        error_code = response.get("error_code")
        if not isinstance(error_code, str) or not error_code:
            raise ControlPlaneError("stored idempotency error code is invalid")
        if expected_command is not None and transition_action is None:
            raise ControlPlaneError(
                "stored idempotency error is not bound to a transition command"
            )

    def _existing_response(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        idempotency_key: str,
        command: str,
        request_digest: str,
        expected_run_id: str,
    ) -> QaRun | None:
        row = connection.execute(
            "SELECT tenant_id, idempotency_key, command, request_digest, "
            "response_json, response_digest, created_at "
            "FROM qa_idempotency "
            "WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        try:
            stored_tenant_id = _identifier(
                row["tenant_id"], "stored idempotency tenant_id"
            )
            stored_key = _identifier(
                row["idempotency_key"], "stored idempotency key"
            )
            stored_command = _identifier(
                row["command"], "stored idempotency command"
            )
            stored_request_digest = require_sha256(
                row["request_digest"], field="stored idempotency request_digest"
            )
            raw_created_at = row["created_at"]
            created_at = _timestamp(raw_created_at, "stored idempotency created_at")
            if created_at != raw_created_at:
                raise ValueError("stored idempotency timestamp is not canonical")
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored idempotency record is invalid") from exc
        raw = _stored_json_bytes(
            row["response_json"], "stored idempotency response"
        )
        try:
            response = parse_json_strict(raw)
            observed_digest = require_sha256(
                row["response_digest"],
                field="stored idempotency response_digest",
            )
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored idempotency response is invalid") from exc
        if not isinstance(response, dict):
            raise ControlPlaneError("stored idempotency response is invalid")
        if canonical_json_bytes(response) != raw:
            raise ControlPlaneError(
                "stored idempotency response is not canonical JSON"
            )
        expected_digest = self._idempotency_record_digest(
            tenant_id=stored_tenant_id,
            idempotency_key=stored_key,
            command=stored_command,
            request_digest=stored_request_digest,
            response=response,
            created_at=created_at,
        )
        if expected_digest != observed_digest:
            raise ControlPlaneError(
                "stored idempotency response digest verification failed"
            )
        if (stored_tenant_id, stored_key) != (tenant_id, idempotency_key):
            raise ControlPlaneError("stored idempotency key binding is invalid")
        if stored_command != command or stored_request_digest != request_digest:
            raise IdempotencyConflict(
                f"idempotency key {idempotency_key!r} was already used for different input"
            )
        self._validate_idempotency_response(
            response,
            expected_tenant_id=tenant_id,
            expected_run_id=expected_run_id,
            expected_command=command,
        )
        error_type = response.get("_error_type")
        if error_type == "IllegalTransition":
            raise IllegalTransition(str(response.get("error_code", "transition denied")))
        if error_type is not None:
            raise ControlPlaneError("stored idempotency error type is invalid")
        return self._response_run(response)

    @staticmethod
    def _store_response(
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        idempotency_key: str,
        command: str,
        request_digest: str,
        run: QaRun,
        quota_run_id: str,
    ) -> None:
        response = QaControlPlane._run_response(run)
        response_json = canonical_json_bytes(response)
        created_at = _utc_now()
        response_digest = QaControlPlane._idempotency_record_digest(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command=command,
            request_digest=request_digest,
            response=response,
            created_at=created_at,
        )
        QaControlPlane._assert_idempotency_capacity(
            connection, tenant_id=tenant_id, run_id=quota_run_id
        )
        connection.execute(
            "INSERT INTO qa_idempotency "
            "(tenant_id, idempotency_key, command, request_digest, response_json, "
            "response_digest, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                idempotency_key,
                command,
                request_digest,
                response_json,
                response_digest,
                created_at,
            ),
        )

    @staticmethod
    def _store_error_response(
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        idempotency_key: str,
        command: str,
        request_digest: str,
        error_code: str,
        run_id: str,
    ) -> None:
        response = {
            "_error_type": "IllegalTransition",
            "error_code": error_code,
        }
        response_json = canonical_json_bytes(response)
        created_at = _utc_now()
        response_digest = QaControlPlane._idempotency_record_digest(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            command=command,
            request_digest=request_digest,
            response=response,
            created_at=created_at,
        )
        QaControlPlane._assert_idempotency_capacity(
            connection, tenant_id=tenant_id, run_id=run_id
        )
        connection.execute(
            "INSERT INTO qa_idempotency "
            "(tenant_id, idempotency_key, command, request_digest, response_json, "
            "response_digest, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                idempotency_key,
                command,
                request_digest,
                response_json,
                response_digest,
                created_at,
            ),
        )

    @staticmethod
    def _assert_idempotency_capacity(
        connection: sqlite3.Connection, *, tenant_id: str, run_id: str
    ) -> None:
        # Every new create/transition/retry idempotency record is written only
        # after its same-transaction audit record.  The immutable audit count
        # is therefore a conservative (possibly higher) per-run upper bound.
        run_count = connection.execute(
            "SELECT COUNT(*) FROM qa_audit WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        ).fetchone()
        tenant_count = connection.execute(
            "SELECT COUNT(*) FROM qa_idempotency WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        total_count = connection.execute(
            "SELECT COUNT(*) FROM qa_idempotency"
        ).fetchone()
        if (
            tenant_count is None
            or total_count is None
            or run_count is None
            or type(tenant_count[0]) is not int
            or type(total_count[0]) is not int
            or type(run_count[0]) is not int
        ):
            raise ControlPlaneError("idempotency quota count is invalid")
        if int(run_count[0]) > MAX_IDEMPOTENCY_RECORDS_PER_RUN:
            raise ResourceQuotaExceeded(
                "run idempotency record quota has been reached"
            )
        if int(tenant_count[0]) >= MAX_IDEMPOTENCY_RECORDS_PER_TENANT:
            raise ResourceQuotaExceeded(
                "tenant idempotency record quota has been reached"
            )
        if int(total_count[0]) >= MAX_IDEMPOTENCY_RECORDS_TOTAL:
            raise ResourceQuotaExceeded(
                "database idempotency record quota has been reached"
            )

    @staticmethod
    def _assert_run_capacity(
        connection: sqlite3.Connection, *, tenant_id: str
    ) -> None:
        tenant_count = connection.execute(
            "SELECT COUNT(*) FROM qa_runs WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        total_count = connection.execute("SELECT COUNT(*) FROM qa_runs").fetchone()
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        active_count = connection.execute(
            f"SELECT COUNT(*) FROM qa_runs WHERE tenant_id = ? "
            f"AND status IN ({placeholders})",
            (tenant_id, *(status.value for status in ACTIVE_STATUSES)),
        ).fetchone()
        if (
            tenant_count is None
            or total_count is None
            or active_count is None
            or type(tenant_count[0]) is not int
            or type(total_count[0]) is not int
            or type(active_count[0]) is not int
        ):
            raise ControlPlaneError("run quota count is invalid")
        if int(tenant_count[0]) >= MAX_RUNS_PER_TENANT:
            raise ResourceQuotaExceeded("tenant run quota has been reached")
        if int(total_count[0]) >= MAX_RUNS_TOTAL:
            raise ResourceQuotaExceeded("database run quota has been reached")
        if int(active_count[0]) >= MAX_ACTIVE_RUNS_PER_TENANT:
            raise ResourceQuotaExceeded("tenant active-run quota has been reached")

    @staticmethod
    def _assert_evidence_capacity(
        connection: sqlite3.Connection, *, tenant_id: str, run_id: str
    ) -> None:
        run_count = connection.execute(
            "SELECT COUNT(*) FROM qa_verified_evidence "
            "WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        ).fetchone()
        tenant_count = connection.execute(
            "SELECT COUNT(*) FROM qa_verified_evidence WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        total_count = connection.execute(
            "SELECT COUNT(*) FROM qa_verified_evidence"
        ).fetchone()
        counts = (run_count, tenant_count, total_count)
        if any(
            count is None or type(count[0]) is not int for count in counts
        ):
            raise ControlPlaneError("evidence quota count is invalid")
        if run_count is None or tenant_count is None or total_count is None:
            raise ControlPlaneError("evidence quota count is invalid")
        if int(run_count[0]) >= MAX_EVIDENCE_RECEIPTS_PER_RUN:
            raise ResourceQuotaExceeded("run evidence receipt quota has been reached")
        if int(tenant_count[0]) >= MAX_EVIDENCE_RECEIPTS_PER_TENANT:
            raise ResourceQuotaExceeded("tenant evidence receipt quota has been reached")
        if int(total_count[0]) >= MAX_EVIDENCE_RECEIPTS_TOTAL:
            raise ResourceQuotaExceeded("database evidence receipt quota has been reached")

    @staticmethod
    def _create_chain_head(
        connection: sqlite3.Connection, *, tenant_id: str, run_id: str
    ) -> None:
        connection.execute(
            "INSERT INTO qa_chain_heads "
            "(tenant_id, run_id, event_sequence, event_digest, audit_id, audit_digest, "
            "external_anchor_state) VALUES (?, ?, 0, NULL, 0, NULL, ?)",
            (tenant_id, run_id, EXTERNAL_CHAIN_ANCHOR_STATE),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
    ) -> None:
        events = QaControlPlane._validated_event_chain(
            connection, tenant_id=tenant_id, run_id=run_id
        )
        QaControlPlane._validated_audit_chain(
            connection, tenant_id=tenant_id, run_id=run_id
        )
        if len(events) >= MAX_EVENTS_PER_RUN:
            raise ResourceQuotaExceeded("run event quota has been reached")
        head = connection.execute(
            "SELECT * FROM qa_chain_heads WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        ).fetchone()
        if head is None:
            raise ControlPlaneError("event chain head is missing")
        head_sequence, head_digest, _, _ = QaControlPlane._chain_head_values(head)
        previous_event = events[-1] if events else None
        previous_sequence = 0 if previous_event is None else previous_event.sequence
        previous_digest = (
            None if previous_event is None else previous_event.event_digest
        )
        if (head_sequence, head_digest) != (previous_sequence, previous_digest):
            raise ControlPlaneError("event chain head does not match the event tail")
        sequence = previous_sequence + 1
        occurred_at = _utc_now()
        document = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "sequence": sequence,
            "kind": kind,
            "payload": dict(payload),
            "previous_digest": previous_digest,
            "occurred_at": occurred_at,
        }
        event_digest = canonical_digest(document)
        connection.execute(
            "INSERT INTO qa_events "
            "(tenant_id, run_id, sequence, kind, payload_json, previous_digest, "
            "event_digest, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                run_id,
                sequence,
                kind,
                canonical_json_bytes(dict(payload)),
                previous_digest,
                event_digest,
                occurred_at,
            ),
        )
        updated = connection.execute(
            "UPDATE qa_chain_heads SET event_sequence = ?, event_digest = ? "
            "WHERE tenant_id = ? AND run_id = ? AND event_sequence = ?",
            (sequence, event_digest, tenant_id, run_id, head_sequence),
        )
        if updated.rowcount != 1:
            raise ControlPlaneError("event chain head update failed")

    @staticmethod
    def _append_audit(
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        actor: str,
        action: str,
        outcome: str,
        details: Mapping[str, Any],
    ) -> AuditRecord:
        QaControlPlane._validated_event_chain(
            connection, tenant_id=tenant_id, run_id=run_id
        )
        records = QaControlPlane._validated_audit_chain(
            connection, tenant_id=tenant_id, run_id=run_id
        )
        if len(records) >= MAX_AUDIT_RECORDS_PER_RUN:
            raise ResourceQuotaExceeded("run audit quota has been reached")
        occurred_at = _utc_now()
        head = connection.execute(
            "SELECT * FROM qa_chain_heads WHERE tenant_id = ? AND run_id = ?",
            (tenant_id, run_id),
        ).fetchone()
        if head is None:
            raise ControlPlaneError("audit chain head is missing")
        _, _, head_audit_id, head_digest = QaControlPlane._chain_head_values(head)
        previous_record = records[-1] if records else None
        previous_id = 0 if previous_record is None else previous_record.audit_id
        previous_digest = (
            None if previous_record is None else previous_record.record_digest
        )
        if (head_audit_id, head_digest) != (previous_id, previous_digest):
            raise ControlPlaneError("audit chain head does not match the audit tail")
        document = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "details": dict(details),
            "previous_digest": previous_digest,
            "occurred_at": occurred_at,
        }
        record_digest = canonical_digest(document)
        inserted = connection.execute(
            "INSERT INTO qa_audit "
            "(tenant_id, run_id, actor, action, outcome, details_json, previous_digest, "
            "record_digest, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                run_id,
                actor,
                action,
                outcome,
                canonical_json_bytes(dict(details)),
                previous_digest,
                record_digest,
                occurred_at,
            ),
        )
        audit_id = int(inserted.lastrowid)
        updated = connection.execute(
            "UPDATE qa_chain_heads SET audit_id = ?, audit_digest = ? "
            "WHERE tenant_id = ? AND run_id = ? AND audit_id = ?",
            (
                audit_id,
                record_digest,
                tenant_id,
                run_id,
                head_audit_id,
            ),
        )
        if updated.rowcount != 1:
            raise ControlPlaneError("audit chain head update failed")
        row = connection.execute(
            "SELECT * FROM qa_audit WHERE audit_id = ?",
            (audit_id,),
        ).fetchone()
        if row is None:
            raise ControlPlaneError("appended audit record is missing")
        return QaControlPlane._audit_from_row(row)

    @staticmethod
    def _receipt_from_row(row: sqlite3.Row) -> VerifiedEvidenceReceipt:
        try:
            revoked = row["revoked"]
            if type(revoked) is not int:
                raise ValueError("revoked must be an integer")
            if revoked not in {0, 1}:
                raise ValueError("revoked must be zero or one")
            approval_run_version = row["approval_run_version"]
            if type(approval_run_version) is not int or approval_run_version < 1:
                raise ValueError("approval run version is invalid")
            raw_valid_until = row["valid_until"]
            raw_created_at = row["created_at"]
            valid_until = _timestamp(raw_valid_until, "stored receipt valid_until")
            created_at = _timestamp(raw_created_at, "stored receipt created_at")
            if valid_until != raw_valid_until or created_at != raw_created_at:
                raise ValueError("receipt timestamps are not canonical UTC timestamps")
            created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            valid_time = datetime.fromisoformat(
                valid_until.replace("Z", "+00:00")
            )
            if valid_time <= created_time:
                raise ValueError("receipt expiry must be after creation")
            consumption_values = (
                row["consumed_at"],
                row["consumed_by"],
                row["consumption_digest"],
            )
            if any(value is None for value in consumption_values) and not all(
                value is None for value in consumption_values
            ):
                raise ValueError("receipt consumption fields are inconsistent")
            consumed_at: str | None = None
            consumed_by: str | None = None
            consumption_digest: str | None = None
            if consumption_values[0] is not None:
                raw_consumed_at = consumption_values[0]
                consumed_at = _timestamp(
                    raw_consumed_at, "stored receipt consumed_at"
                )
                if consumed_at != raw_consumed_at:
                    raise ValueError("receipt consumed_at is not canonical UTC")
                if datetime.fromisoformat(
                    consumed_at.replace("Z", "+00:00")
                ) < created_time:
                    raise ValueError("receipt consumption predates registration")
                if datetime.fromisoformat(
                    consumed_at.replace("Z", "+00:00")
                ) >= valid_time:
                    raise ValueError("receipt consumption is not before expiry")
                consumed_by = _identifier(
                    consumption_values[1], "stored receipt consumed_by"
                )
                consumption_digest = require_sha256(
                    consumption_values[2],
                    field="stored receipt consumption_digest",
                )
            tenant_id = _identifier(row["tenant_id"], "stored receipt tenant_id")
            receipt_id = _identifier(row["receipt_id"], "stored receipt receipt_id")
            run_id = _identifier(row["run_id"], "stored receipt run_id")
            scope = _identifier(row["scope"], "stored receipt scope")
            authorization_ref = _identifier(
                row["authorization_ref"], "stored receipt authorization_ref"
            )
            executor_id = _identifier(
                row["executor_id"], "stored receipt executor_id"
            )
            verifier_id = _identifier(
                row["verifier_id"], "stored receipt verifier_id"
            )
            if executor_id == verifier_id:
                raise ValueError("receipt executor and verifier are not independent")
            return VerifiedEvidenceReceipt(
                tenant_id=tenant_id,
                receipt_id=receipt_id,
                run_id=run_id,
                scope=scope,
                subject_digest=require_sha256(
                    row["subject_digest"], field="stored receipt subject_digest"
                ),
                evidence_digest=require_sha256(
                    row["evidence_digest"], field="stored receipt evidence_digest"
                ),
                artifact_digest=require_sha256(
                    row["artifact_digest"], field="stored receipt artifact_digest"
                ),
                authorization_ref=authorization_ref,
                executor_id=executor_id,
                verifier_id=verifier_id,
                valid_until=valid_until,
                approval_request_digest=require_sha256(
                    row["approval_request_digest"],
                    field="stored receipt approval_request_digest",
                ),
                approval_run_version=approval_run_version,
                revoked=bool(revoked),
                consumed_at=consumed_at,
                consumed_by=consumed_by,
                consumption_digest=consumption_digest,
                created_at=created_at,
            )
        except (IndexError, TypeError, ValueError) as exc:
            raise ControlPlaneError("stored evidence receipt is invalid") from exc

    @staticmethod
    def _audit_from_row(row: sqlite3.Row) -> AuditRecord:
        raw = _stored_json_bytes(row["details_json"], "stored audit details")
        try:
            details = parse_json_strict(raw)
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored audit details are invalid") from exc
        if not isinstance(details, dict) or canonical_json_bytes(details) != raw:
            raise ControlPlaneError("stored audit details are not canonical JSON")
        try:
            audit_id = row["audit_id"]
            if type(audit_id) is not int or audit_id < 1:
                raise ValueError("stored audit ID is invalid")
            tenant_id = _identifier(row["tenant_id"], "stored audit tenant_id")
            run_id = _identifier(row["run_id"], "stored audit run_id")
            actor = _identifier(row["actor"], "stored audit actor")
            action = _identifier(row["action"], "stored audit action")
            outcome = _identifier(row["outcome"], "stored audit outcome")
            if outcome not in {"accepted", "denied"}:
                raise ValueError("stored audit outcome is invalid")
            previous_digest = (
                None
                if row["previous_digest"] is None
                else require_sha256(
                    row["previous_digest"], field="stored audit previous_digest"
                )
            )
            observed = require_sha256(
                row["record_digest"], field="stored audit record_digest"
            )
            raw_occurred_at = row["occurred_at"]
            occurred_at = _timestamp(
                raw_occurred_at, "stored audit occurred_at"
            )
            if occurred_at != raw_occurred_at:
                raise ValueError("stored audit timestamp is not canonical UTC")
        except (IndexError, TypeError, ValueError) as exc:
            raise ControlPlaneError("stored audit record is invalid") from exc
        document = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "actor": actor,
            "action": action,
            "outcome": outcome,
            "details": details,
            "previous_digest": previous_digest,
            "occurred_at": occurred_at,
        }
        if canonical_digest(document) != observed:
            raise ControlPlaneError("stored audit digest verification failed")
        return AuditRecord(
            audit_id=audit_id,
            tenant_id=tenant_id,
            run_id=run_id,
            actor=actor,
            action=action,
            outcome=outcome,
            details=details,
            previous_digest=previous_digest,
            record_digest=observed,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> QaEvent:
        raw = _stored_json_bytes(row["payload_json"], "stored event payload")
        try:
            payload = parse_json_strict(raw)
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored event payload is invalid") from exc
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
            raise ControlPlaneError("stored event payload is not canonical JSON")
        try:
            sequence = row["sequence"]
            if type(sequence) is not int or sequence < 1:
                raise ValueError("event sequence must be positive")
            tenant_id = _identifier(row["tenant_id"], "stored event tenant_id")
            run_id = _identifier(row["run_id"], "stored event run_id")
            kind = _identifier(row["kind"], "stored event kind")
            previous_digest = (
                None
                if row["previous_digest"] is None
                else require_sha256(
                    row["previous_digest"], field="stored event previous_digest"
                )
            )
            observed = require_sha256(
                row["event_digest"], field="stored event event_digest"
            )
            raw_occurred_at = row["occurred_at"]
            occurred_at = _timestamp(
                raw_occurred_at, "stored event occurred_at"
            )
            if occurred_at != raw_occurred_at:
                raise ValueError("stored event timestamp is not canonical UTC")
        except (IndexError, TypeError, ValueError) as exc:
            raise ControlPlaneError("stored event record is invalid") from exc
        document = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "sequence": sequence,
            "kind": kind,
            "payload": payload,
            "previous_digest": previous_digest,
            "occurred_at": occurred_at,
        }
        if canonical_digest(document) != observed:
            raise ControlPlaneError("stored event digest verification failed")
        return QaEvent(
            tenant_id=tenant_id,
            run_id=run_id,
            sequence=sequence,
            kind=kind,
            payload=payload,
            previous_digest=previous_digest,
            event_digest=observed,
            occurred_at=occurred_at,
        )

    @staticmethod
    def _chain_head_values(
        row: sqlite3.Row,
    ) -> tuple[int, str | None, int, str | None]:
        try:
            event_sequence = row["event_sequence"]
            audit_id = row["audit_id"]
            if type(event_sequence) is not int or event_sequence < 0:
                raise ValueError("event head sequence is invalid")
            if type(audit_id) is not int or audit_id < 0:
                raise ValueError("audit head ID is invalid")
            event_digest = (
                None
                if row["event_digest"] is None
                else require_sha256(
                    row["event_digest"], field="stored event head digest"
                )
            )
            audit_digest = (
                None
                if row["audit_digest"] is None
                else require_sha256(
                    row["audit_digest"], field="stored audit head digest"
                )
            )
            if (event_sequence == 0) != (event_digest is None):
                raise ValueError("event head fields are inconsistent")
            if (audit_id == 0) != (audit_digest is None):
                raise ValueError("audit head fields are inconsistent")
            if row["external_anchor_state"] != EXTERNAL_CHAIN_ANCHOR_STATE:
                raise ValueError("external chain anchor state is unsupported")
        except (TypeError, ValueError) as exc:
            raise ControlPlaneError("stored chain head is invalid") from exc
        return event_sequence, event_digest, audit_id, audit_digest

    @classmethod
    def _verify_chain_head_values(
        cls,
        row: sqlite3.Row,
        *,
        event_sequence: int,
        event_digest: str | None,
        audit_id: int,
        audit_digest: str | None,
    ) -> None:
        observed = cls._chain_head_values(row)
        expected = (event_sequence, event_digest, audit_id, audit_digest)
        if observed != expected:
            raise ControlPlaneError(
                "stored chain head does not match the materialized chain tail"
            )

    @classmethod
    def _validated_audit_chain(
        cls,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        verify_head: bool = True,
    ) -> tuple[AuditRecord, ...]:
        rows = connection.execute(
            "SELECT * FROM qa_audit WHERE tenant_id = ? AND run_id = ? "
            "ORDER BY audit_id",
            (tenant_id, run_id),
        )
        records: list[AuditRecord] = []
        previous_digest: str | None = None
        previous_id = 0
        for row in rows:
            if len(records) >= MAX_AUDIT_RECORDS_PER_RUN:
                raise ResourceQuotaExceeded(
                    "stored run audit chain exceeds its quota"
                )
            record = cls._audit_from_row(row)
            if (record.tenant_id, record.run_id) != (tenant_id, run_id):
                raise ControlPlaneError("stored audit resource binding is invalid")
            if record.audit_id <= previous_id:
                raise ControlPlaneError("stored audit order is invalid")
            if record.previous_digest != previous_digest:
                raise ControlPlaneError("stored audit previous-digest chain is invalid")
            records.append(record)
            previous_id = record.audit_id
            previous_digest = record.record_digest
        if verify_head:
            head = connection.execute(
                "SELECT * FROM qa_chain_heads WHERE tenant_id = ? AND run_id = ?",
                (tenant_id, run_id),
            ).fetchone()
            if head is None:
                raise ControlPlaneError("stored audit chain head is missing")
            _, _, head_audit_id, head_audit_digest = cls._chain_head_values(head)
            audit_id = records[-1].audit_id if records else 0
            audit_digest = records[-1].record_digest if records else None
            if (head_audit_id, head_audit_digest) != (audit_id, audit_digest):
                raise ControlPlaneError(
                    "stored audit chain head does not match the audit tail"
                )
        return tuple(records)

    @classmethod
    def _validated_event_chain(
        cls,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        run_id: str,
        verify_head: bool = True,
    ) -> tuple[QaEvent, ...]:
        rows = connection.execute(
            "SELECT * FROM qa_events WHERE tenant_id = ? AND run_id = ? "
            "ORDER BY sequence",
            (tenant_id, run_id),
        )
        events: list[QaEvent] = []
        previous_digest: str | None = None
        expected_sequence = 1
        for row in rows:
            if len(events) >= MAX_EVENTS_PER_RUN:
                raise ResourceQuotaExceeded(
                    "stored run event chain exceeds its quota"
                )
            event = cls._event_from_row(row)
            if (event.tenant_id, event.run_id) != (tenant_id, run_id):
                raise ControlPlaneError("stored event resource binding is invalid")
            if event.sequence != expected_sequence:
                raise ControlPlaneError("stored event sequence chain is invalid")
            if event.previous_digest != previous_digest:
                raise ControlPlaneError("stored event previous-digest chain is invalid")
            events.append(event)
            previous_digest = event.event_digest
            expected_sequence += 1
        if verify_head:
            head = connection.execute(
                "SELECT * FROM qa_chain_heads WHERE tenant_id = ? AND run_id = ?",
                (tenant_id, run_id),
            ).fetchone()
            if head is None:
                raise ControlPlaneError("stored event chain head is missing")
            head_sequence, head_digest, _, _ = cls._chain_head_values(head)
            sequence = events[-1].sequence if events else 0
            digest = events[-1].event_digest if events else None
            if (head_sequence, head_digest) != (sequence, digest):
                raise ControlPlaneError(
                    "stored event chain head does not match the event tail"
                )
        return tuple(events)

    @staticmethod
    def _validate_receipt_audit_binding(
        receipt: VerifiedEvidenceReceipt,
        records: tuple[AuditRecord, ...],
    ) -> None:
        registrations = [
            record
            for record in records
            if record.action == "register_verified_evidence"
            and record.outcome == "accepted"
            and record.details.get("receipt_id") == receipt.receipt_id
        ]
        if len(registrations) != 1:
            raise ControlPlaneError("evidence receipt registration audit is invalid")
        registration = registrations[0]
        expected_registration = {
            "receipt_id": receipt.receipt_id,
            "scope": receipt.scope,
            "subject_digest": receipt.subject_digest,
            "evidence_digest": receipt.evidence_digest,
            "artifact_digest": receipt.artifact_digest,
            "authorization_ref": receipt.authorization_ref,
            "executor_id": receipt.executor_id,
            "valid_until": receipt.valid_until,
            "approval_request_digest": receipt.approval_request_digest,
            "approval_run_version": receipt.approval_run_version,
            "created_at": receipt.created_at,
        }
        if (
            registration.tenant_id != receipt.tenant_id
            or registration.run_id != receipt.run_id
            or registration.actor != receipt.verifier_id
            or dict(registration.details) != expected_registration
            or datetime.fromisoformat(
                registration.occurred_at.replace("Z", "+00:00")
            )
            < datetime.fromisoformat(receipt.created_at.replace("Z", "+00:00"))
        ):
            raise ControlPlaneError("evidence receipt does not match its registration audit")
        approval_requests = [
            record
            for record in records
            if record.record_digest == receipt.approval_request_digest
            and record.action == "request_approval"
            and record.outcome == "accepted"
        ]
        if len(approval_requests) != 1:
            raise ControlPlaneError(
                "evidence receipt approval-request binding is invalid"
            )
        approval_request = approval_requests[0]
        expected_request = {
            "from": RunStatus.RUNNING.value,
            "to": RunStatus.WAITING_APPROVAL.value,
            "scope": receipt.scope,
            "subject_digest": receipt.subject_digest,
            "authorization_ref": receipt.authorization_ref,
        }
        prior_requests = [
            record
            for record in records
            if record.audit_id < registration.audit_id
            and record.action == "request_approval"
            and record.outcome == "accepted"
        ]
        derived_run_version = 1 + sum(
            1
            for record in records
            if record.audit_id <= approval_request.audit_id
            and record.action in _TRANSITIONS
            and record.outcome == "accepted"
        )
        if (
            approval_request.audit_id >= registration.audit_id
            or not prior_requests
            or prior_requests[-1].audit_id != approval_request.audit_id
            or dict(approval_request.details) != expected_request
            or approval_request.actor == receipt.verifier_id
            or receipt.approval_run_version != derived_run_version
        ):
            raise ControlPlaneError(
                "evidence receipt approval-request binding is invalid"
            )
        revocations = [
            record
            for record in records
            if record.action == "revoke_verified_evidence"
            and record.outcome == "accepted"
            and record.details.get("receipt_id") == receipt.receipt_id
        ]
        if (
            len(revocations) > 1
            or receipt.revoked != bool(revocations)
            or any(
                record.audit_id <= registration.audit_id
                or dict(record.details) != {"receipt_id": receipt.receipt_id}
                for record in revocations
            )
        ):
            raise ControlPlaneError("evidence receipt revocation audit is invalid")
        approvals = [
            record
            for record in records
            if record.action == "approve"
            and record.outcome == "accepted"
            and record.details.get("evidence_receipt_id") == receipt.receipt_id
        ]
        if receipt.consumed_at is None:
            if approvals:
                raise ControlPlaneError(
                    "unconsumed evidence receipt has an accepted approval audit"
                )
            return
        expected_approval = {
            "from": RunStatus.WAITING_APPROVAL.value,
            "to": RunStatus.RUNNING.value,
            "decision": "approved",
            "approver_id": receipt.consumed_by,
            "scope": receipt.scope,
            "subject_digest": receipt.subject_digest,
            "authorization_ref": receipt.authorization_ref,
            "evidence_receipt_id": receipt.receipt_id,
            "executor_id": receipt.executor_id,
            "verifier_id": receipt.verifier_id,
        }
        if len(approvals) != 1:
            raise ControlPlaneError("evidence receipt consumption audit is invalid")
        approval = approvals[0]
        if (
            approval.audit_id <= registration.audit_id
            or approval.audit_id <= approval_request.audit_id
            or approval.record_digest != receipt.consumption_digest
            or approval.actor != receipt.consumed_by
            or approval.occurred_at != receipt.consumed_at
            or dict(approval.details) != expected_approval
            or approval.actor == approval_request.actor
            or approval.actor in {receipt.executor_id, receipt.verifier_id}
            or receipt.verifier_id == approval_request.actor
            or (revocations and revocations[0].audit_id <= approval.audit_id)
        ):
            raise ControlPlaneError("evidence receipt consumption audit is invalid")

    def register_verified_evidence(
        self,
        *,
        tenant_id: str,
        receipt_id: str,
        run_id: str,
        scope: str,
        subject_digest: str,
        evidence_digest: str,
        artifact_digest: str,
        authorization_ref: str,
        executor_id: str,
        verifier_id: str,
        valid_until: str,
        registered_by: str,
    ) -> VerifiedEvidenceReceipt:
        try:
            tenant_id = _identifier(tenant_id, "tenant_id")
            receipt_id = _identifier(receipt_id, "receipt_id")
            run_id = _identifier(run_id, "run_id")
            scope = _identifier(scope, "scope")
            authorization_ref = _identifier(authorization_ref, "authorization_ref")
            executor_id = _identifier(executor_id, "executor_id")
            verifier_id = _identifier(verifier_id, "verifier_id")
            registered_by = _identifier(registered_by, "registered_by")
            if registered_by != verifier_id:
                raise ValueError("verified evidence must be registered by its verifier")
            if executor_id == verifier_id:
                raise ValueError("evidence executor and verifier must be independent")
            subject_digest = require_sha256(subject_digest, field="subject_digest")
            evidence_digest = require_sha256(evidence_digest, field="evidence_digest")
            artifact_digest = require_sha256(artifact_digest, field="artifact_digest")
            valid_until = _timestamp(valid_until, "valid_until")
        except (TypeError, ValueError) as exc:
            raise EvidenceReceiptInvalid(str(exc)) from exc
        expected = {
            "tenant_id": tenant_id,
            "receipt_id": receipt_id,
            "run_id": run_id,
            "scope": scope,
            "subject_digest": subject_digest,
            "evidence_digest": evidence_digest,
            "artifact_digest": artifact_digest,
            "authorization_ref": authorization_ref,
            "executor_id": executor_id,
            "verifier_id": verifier_id,
            "valid_until": valid_until,
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = self.get_run(
                tenant_id=tenant_id, run_id=run_id, connection=connection
            )
            self._validated_event_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            audit = self._validated_audit_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            existing = connection.execute(
                "SELECT * FROM qa_verified_evidence WHERE tenant_id = ? AND receipt_id = ?",
                (tenant_id, receipt_id),
            ).fetchone()
            if existing is not None:
                receipt = self._receipt_from_row(existing)
                observed = {
                    key: getattr(receipt, key) for key in expected
                }
                if observed != expected:
                    raise IdempotencyConflict("evidence receipt ID is bound to different input")
                self._validate_receipt_audit_binding(receipt, audit)
                return receipt
            if datetime.fromisoformat(valid_until.replace("Z", "+00:00")) <= datetime.now(UTC):
                raise EvidenceReceiptInvalid("valid_until must be in the future")
            if run.status is not RunStatus.WAITING_APPROVAL:
                raise EvidenceReceiptInvalid(
                    "verified evidence requires a run waiting for exact approval"
                )
            approval_request = next(
                (
                    record
                    for record in reversed(audit)
                    if record.action == "request_approval"
                    and record.outcome == "accepted"
                ),
                None,
            )
            if approval_request is None:
                raise EvidenceReceiptInvalid(
                    "verified evidence requires an accepted approval request"
                )
            if approval_request.actor == verifier_id:
                raise EvidenceReceiptInvalid(
                    "approval requester and evidence verifier must be independent"
                )
            if (
                approval_request.details.get("scope") != scope
                or approval_request.details.get("subject_digest") != subject_digest
                or approval_request.details.get("authorization_ref")
                != authorization_ref
            ):
                raise EvidenceReceiptInvalid(
                    "verified evidence does not match the active approval request"
                )
            self._assert_evidence_capacity(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            approval_request_digest = approval_request.record_digest
            approval_run_version = run.version
            now = _utc_now()
            connection.execute(
                "INSERT INTO qa_verified_evidence "
                "(tenant_id, receipt_id, run_id, scope, subject_digest, evidence_digest, "
                "artifact_digest, authorization_ref, executor_id, verifier_id, valid_until, "
                "approval_request_digest, approval_run_version, revoked, consumed_at, "
                "consumed_by, consumption_digest, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, ?)",
                (
                    tenant_id,
                    receipt_id,
                    run_id,
                    scope,
                    subject_digest,
                    evidence_digest,
                    artifact_digest,
                    authorization_ref,
                    executor_id,
                    verifier_id,
                    valid_until,
                    approval_request_digest,
                    approval_run_version,
                    now,
                ),
            )
            self._append_audit(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                actor=registered_by,
                action="register_verified_evidence",
                outcome="accepted",
                details={
                    "receipt_id": receipt_id,
                    "scope": scope,
                    "subject_digest": subject_digest,
                    "evidence_digest": evidence_digest,
                    "artifact_digest": artifact_digest,
                    "authorization_ref": authorization_ref,
                    "executor_id": executor_id,
                    "valid_until": valid_until,
                    "approval_request_digest": approval_request_digest,
                    "approval_run_version": approval_run_version,
                    "created_at": now,
                },
            )
            row = connection.execute(
                "SELECT * FROM qa_verified_evidence WHERE tenant_id = ? AND receipt_id = ?",
                (tenant_id, receipt_id),
            ).fetchone()
            if row is None:
                raise ControlPlaneError("registered evidence receipt is missing")
            receipt = self._receipt_from_row(row)
            audit = self._validated_audit_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            self._validate_receipt_audit_binding(receipt, audit)
            return receipt

    def revoke_verified_evidence(
        self, *, tenant_id: str, receipt_id: str, actor: str
    ) -> VerifiedEvidenceReceipt:
        try:
            tenant_id = _identifier(tenant_id, "tenant_id")
            receipt_id = _identifier(receipt_id, "receipt_id")
            actor = _identifier(actor, "actor")
        except (TypeError, ValueError) as exc:
            raise EvidenceReceiptInvalid(str(exc)) from exc
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM qa_verified_evidence "
                "WHERE tenant_id = ? AND receipt_id = ?",
                (tenant_id, receipt_id),
            ).fetchone()
            if row is None:
                raise EvidenceReceiptNotFound(f"evidence receipt not found: {receipt_id}")
            receipt = self._receipt_from_row(row)
            self._validated_event_chain(
                connection, tenant_id=tenant_id, run_id=receipt.run_id
            )
            audit = self._validated_audit_chain(
                connection, tenant_id=tenant_id, run_id=receipt.run_id
            )
            self._validate_receipt_audit_binding(receipt, audit)
            if not receipt.revoked:
                revoked = connection.execute(
                    "UPDATE qa_verified_evidence SET revoked = 1 "
                    "WHERE tenant_id = ? AND receipt_id = ? AND revoked = 0",
                    (tenant_id, receipt_id),
                )
                if revoked.rowcount != 1:
                    raise ControlPlaneError(
                        "evidence receipt revocation compare-and-set failed"
                    )
                self._append_audit(
                    connection,
                    tenant_id=tenant_id,
                    run_id=receipt.run_id,
                    actor=actor,
                    action="revoke_verified_evidence",
                    outcome="accepted",
                    details={"receipt_id": receipt_id},
                )
                row = connection.execute(
                    "SELECT * FROM qa_verified_evidence WHERE tenant_id = ? AND receipt_id = ?",
                    (tenant_id, receipt_id),
                ).fetchone()
                if row is None:
                    raise ControlPlaneError("revoked evidence receipt is missing")
                receipt = self._receipt_from_row(row)
                audit = self._validated_audit_chain(
                    connection, tenant_id=tenant_id, run_id=receipt.run_id
                )
                self._validate_receipt_audit_binding(receipt, audit)
            return receipt

    def get_verified_evidence(
        self,
        *,
        tenant_id: str,
        receipt_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> VerifiedEvidenceReceipt:
        try:
            tenant_id = _identifier(tenant_id, "tenant_id")
            receipt_id = _identifier(receipt_id, "receipt_id")
        except (TypeError, ValueError) as exc:
            raise EvidenceReceiptInvalid(str(exc)) from exc
        owns_connection = connection is None
        active_connection = self._connect() if connection is None else connection
        try:
            row = active_connection.execute(
                "SELECT * FROM qa_verified_evidence WHERE tenant_id = ? AND receipt_id = ?",
                (tenant_id, receipt_id),
            ).fetchone()
            if row is None:
                raise EvidenceReceiptNotFound(
                    f"evidence receipt not found: {receipt_id}"
                )
            receipt = self._receipt_from_row(row)
            self._validated_event_chain(
                active_connection, tenant_id=tenant_id, run_id=receipt.run_id
            )
            audit = self._validated_audit_chain(
                active_connection, tenant_id=tenant_id, run_id=receipt.run_id
            )
            self._validate_receipt_audit_binding(receipt, audit)
            return receipt
        finally:
            if owns_connection:
                active_connection.close()

    def create_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        project_id: str,
        mode: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        actor: str,
    ) -> QaRun:
        tenant_id = _identifier(tenant_id, "tenant_id")
        run_id = _identifier(run_id, "run_id")
        project_id = _identifier(project_id, "project_id")
        idempotency_key = _identifier(idempotency_key, "idempotency_key")
        actor = _identifier(actor, "actor")
        if mode not in RUN_MODES:
            raise ValueError(f"unsupported run mode: {mode!r}")
        payload = _bounded_json_object(payload, "payload")
        request = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "project_id": project_id,
            "mode": mode,
            "payload": payload,
            "actor": actor,
        }
        request_digest = canonical_digest(request)
        input_digest = canonical_digest(payload)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._existing_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command="create",
                request_digest=request_digest,
                expected_run_id=run_id,
            )
            if existing is not None:
                return existing
            if connection.execute(
                "SELECT 1 FROM qa_runs WHERE tenant_id = ? AND run_id = ?",
                (tenant_id, run_id),
            ).fetchone():
                raise RunAlreadyExists(f"run already exists: {tenant_id}/{run_id}")
            self._assert_run_capacity(connection, tenant_id=tenant_id)
            now = _utc_now()
            connection.execute(
                "INSERT INTO qa_runs "
                "(tenant_id, run_id, project_id, mode, status, input_digest, payload_json, "
                "attempt, retry_of, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL, 1, ?, ?)",
                (
                    tenant_id,
                    run_id,
                    project_id,
                    mode,
                    RunStatus.CREATED.value,
                    input_digest,
                    canonical_json_bytes(payload),
                    now,
                    now,
                ),
            )
            self._create_chain_head(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            self._append_event(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                kind="run.created",
                payload={"status": RunStatus.CREATED.value, "input_digest": input_digest},
            )
            self._append_audit(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                actor=actor,
                action="create",
                outcome="accepted",
                details={"mode": mode, "input_digest": input_digest},
            )
            run = self.get_run(tenant_id=tenant_id, run_id=run_id, connection=connection)
            self._store_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command="create",
                request_digest=request_digest,
                run=run,
                quota_run_id=run_id,
            )
            return run

    def transition(
        self,
        *,
        tenant_id: str,
        run_id: str,
        action: str,
        idempotency_key: str,
        actor: str,
        details: Mapping[str, Any] | None = None,
    ) -> QaRun:
        tenant_id = _identifier(tenant_id, "tenant_id")
        run_id = _identifier(run_id, "run_id")
        idempotency_key = _identifier(idempotency_key, "idempotency_key")
        actor = _identifier(actor, "actor")
        details = _bounded_json_object(
            {} if details is None else details, "transition details"
        )
        if action not in _TRANSITIONS:
            raise IllegalTransition(f"unknown or unauthorized action: {action!r}")
        request_digest = canonical_digest(
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "action": action,
                "actor": actor,
                "details": details,
            }
        )
        command = f"transition:{action}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = self.get_run(
                tenant_id=tenant_id, run_id=run_id, connection=connection
            )
            approval_audit = self._validated_audit_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            self._validated_event_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            existing = self._existing_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command=command,
                request_digest=request_digest,
                expected_run_id=run_id,
            )
            if existing is not None:
                return existing

            def deny(error_code: str, audit_details: Mapping[str, Any]) -> None:
                self._append_audit(
                    connection,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    actor=actor,
                    action=action,
                    outcome="denied",
                    details={"error_code": error_code, **dict(audit_details)},
                )
                self._store_error_response(
                    connection,
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    command=command,
                    request_digest=request_digest,
                    error_code=error_code,
                    run_id=run_id,
                )
                connection.commit()
                raise IllegalTransition(error_code)

            try:
                if action == "request_approval":
                    self._validate_approval_request(details)
                elif action == "approve":
                    self._validate_approval(actor, details)
                elif action == "complete":
                    self._validate_completion(run, details)
            except (IllegalTransition, ValueError) as exc:
                deny("APPROVAL_CONTRACT_INVALID", {"reason_type": type(exc).__name__})
            evidence_to_consume: VerifiedEvidenceReceipt | None = None
            if action == "approve":
                request_record = next(
                    (
                        record
                        for record in reversed(approval_audit)
                        if record.action == "request_approval"
                        and record.outcome == "accepted"
                    ),
                    None,
                )
                if request_record is None or request_record.actor == actor:
                    deny("INDEPENDENT_APPROVER_REQUIRED", {})
                request_details = request_record.details
                if (
                    request_details.get("scope") != details.get("scope")
                    or request_details.get("subject_digest")
                    != details.get("subject_digest")
                    or request_details.get("authorization_ref")
                    != details.get("authorization_ref")
                ):
                    deny("APPROVAL_REQUEST_SCOPE_MISMATCH", {})
                receipt = connection.execute(
                    "SELECT * FROM qa_verified_evidence WHERE tenant_id = ? "
                    "AND receipt_id = ? AND run_id = ?",
                    (tenant_id, details["evidence_receipt_id"], run_id),
                ).fetchone()
                if receipt is None:
                    deny("VERIFIED_EVIDENCE_RECEIPT_MISSING", {})
                evidence = self._receipt_from_row(receipt)
                self._validate_receipt_audit_binding(evidence, approval_audit)
                if evidence.revoked:
                    deny("VERIFIED_EVIDENCE_RECEIPT_REVOKED", {})
                if evidence.consumed_at is not None:
                    deny("VERIFIED_EVIDENCE_RECEIPT_CONSUMED", {})
                if (
                    evidence.approval_request_digest != request_record.record_digest
                    or evidence.approval_run_version != run.version
                ):
                    deny("VERIFIED_EVIDENCE_REQUEST_BINDING_STALE", {})
                valid_until = datetime.fromisoformat(
                    evidence.valid_until.replace("Z", "+00:00")
                )
                if valid_until <= datetime.now(UTC):
                    deny("VERIFIED_EVIDENCE_RECEIPT_EXPIRED", {})
                if (
                    evidence.scope != details.get("scope")
                    or evidence.subject_digest != details.get("subject_digest")
                    or evidence.authorization_ref
                    != details.get("authorization_ref")
                    or evidence.executor_id != details.get("executor_id")
                    or evidence.verifier_id != details.get("verifier_id")
                ):
                    deny("VERIFIED_EVIDENCE_SCOPE_MISMATCH", {})
                if evidence.verifier_id in {actor, request_record.actor}:
                    deny("VERIFIER_ROLE_SEPARATION_REQUIRED", {})
                if evidence.executor_id == actor:
                    deny("EXECUTOR_APPROVER_SEPARATION_REQUIRED", {})
                evidence_to_consume = evidence
            target = _TRANSITIONS[action].get(run.status)
            if target is None:
                deny("ILLEGAL_RUN_STATE", {"status": run.status.value})
            now = _utc_now()
            updated = connection.execute(
                "UPDATE qa_runs SET status = ?, version = version + 1, updated_at = ? "
                "WHERE tenant_id = ? AND run_id = ? AND version = ?",
                (target.value, now, tenant_id, run_id, run.version),
            )
            if updated.rowcount != 1:
                raise ControlPlaneError("concurrent run update detected")
            self._append_event(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                kind=f"run.{action}",
                payload={"from": run.status.value, "to": target.value, "details": details},
            )
            accepted_audit = self._append_audit(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                actor=actor,
                action=action,
                outcome="accepted",
                details={"from": run.status.value, "to": target.value, **details},
            )
            if evidence_to_consume is not None:
                consumed = connection.execute(
                    "UPDATE qa_verified_evidence SET consumed_at = ?, consumed_by = ?, "
                    "consumption_digest = ? WHERE tenant_id = ? AND receipt_id = ? "
                    "AND run_id = ? AND revoked = 0 AND consumed_at IS NULL "
                    "AND approval_request_digest = ? AND approval_run_version = ?",
                    (
                        accepted_audit.occurred_at,
                        actor,
                        accepted_audit.record_digest,
                        tenant_id,
                        evidence_to_consume.receipt_id,
                        run_id,
                        evidence_to_consume.approval_request_digest,
                        evidence_to_consume.approval_run_version,
                    ),
                )
                if consumed.rowcount != 1:
                    raise ControlPlaneError(
                        "evidence receipt consumption compare-and-set failed"
                    )
                receipt_row = connection.execute(
                    "SELECT * FROM qa_verified_evidence "
                    "WHERE tenant_id = ? AND receipt_id = ?",
                    (tenant_id, evidence_to_consume.receipt_id),
                ).fetchone()
                if receipt_row is None:
                    raise ControlPlaneError("consumed evidence receipt is missing")
                consumed_receipt = self._receipt_from_row(receipt_row)
                approval_audit = self._validated_audit_chain(
                    connection, tenant_id=tenant_id, run_id=run_id
                )
                self._validate_receipt_audit_binding(
                    consumed_receipt, approval_audit
                )
            result = self.get_run(tenant_id=tenant_id, run_id=run_id, connection=connection)
            self._store_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command=command,
                request_digest=request_digest,
                run=result,
                quota_run_id=run_id,
            )
        return result

    def record_observation(
        self,
        *,
        tenant_id: str,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        actor: str,
    ) -> QaRun:
        """Append one bounded, idempotent worker/progress observation.

        This records facts supplied by an authenticated worker or operator; it
        does not promote those facts to independently verified evidence.
        """

        tenant_id = _identifier(tenant_id, "tenant_id")
        run_id = _identifier(run_id, "run_id")
        kind = _identifier(kind, "observation kind")
        if kind not in OBSERVATION_KINDS:
            raise ValueError(f"unsupported observation kind: {kind!r}")
        payload = _bounded_json_object(payload, "observation payload")
        idempotency_key = _identifier(idempotency_key, "idempotency_key")
        actor = _identifier(actor, "actor")
        command = f"observation:{kind}"
        request_digest = canonical_digest(
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "kind": kind,
                "payload": payload,
                "actor": actor,
            }
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = self.get_run(
                tenant_id=tenant_id,
                run_id=run_id,
                connection=connection,
            )
            self._validated_event_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            self._validated_audit_chain(
                connection, tenant_id=tenant_id, run_id=run_id
            )
            existing = self._existing_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command=command,
                request_digest=request_digest,
                expected_run_id=run_id,
            )
            if existing is not None:
                return existing
            if run.status not in ACTIVE_STATUSES:
                raise IllegalTransition(
                    "observations require an active run"
                )
            self._append_event(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                kind=f"run.observation.{kind}",
                payload={
                    "observation": payload,
                    "verification": "SELF_ATTESTED_NOT_INDEPENDENTLY_VERIFIED",
                },
            )
            self._append_audit(
                connection,
                tenant_id=tenant_id,
                run_id=run_id,
                actor=actor,
                action=f"observe-{kind}",
                outcome="accepted",
                details={
                    "observation_digest": canonical_digest(payload),
                    "independent_evidence": "NOT_RUN",
                },
            )
            result = self.get_run(
                tenant_id=tenant_id,
                run_id=run_id,
                connection=connection,
            )
            self._store_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command=command,
                request_digest=request_digest,
                run=result,
                quota_run_id=run_id,
            )
            return result

    @staticmethod
    def _validate_approval_request(details: Mapping[str, Any]) -> None:
        required = {"scope", "subject_digest", "authorization_ref"}
        if set(details) != required:
            raise IllegalTransition(
                "approval request requires exact scope, subject_digest, and authorization_ref fields"
            )
        _identifier(details.get("scope"), "approval scope")
        require_sha256(
            details.get("subject_digest"), field="approval subject_digest"
        )
        _identifier(
            details.get("authorization_ref"), "approval authorization_ref"
        )

    @staticmethod
    def _validate_completion(run: QaRun, details: Mapping[str, Any]) -> None:
        if run.mode == "plan-only":
            if details:
                raise IllegalTransition(
                    "plan-only completion details must be empty"
                )
            return
        required = {
            "output_ref",
            "output_manifest_digest",
            "publication_durability",
        }
        if set(details) != required:
            raise IllegalTransition(
                "non-plan completion requires exact output_ref, "
                "output_manifest_digest, and publication_durability"
            )
        _identifier(details.get("output_ref"), "completion output_ref")
        require_sha256(
            details.get("output_manifest_digest"),
            field="completion output_manifest_digest",
        )
        if details.get("publication_durability") != "DURABLE":
            raise IllegalTransition(
                "non-plan completion requires a durable published output"
            )

    @staticmethod
    def _validate_approval(actor: str, details: Mapping[str, Any]) -> None:
        required = {
            "decision",
            "approver_id",
            "scope",
            "subject_digest",
            "authorization_ref",
            "evidence_receipt_id",
            "executor_id",
            "verifier_id",
        }
        if set(details) != required:
            raise IllegalTransition("approval fields are incomplete or ambiguous")
        if details.get("decision") != "approved" or details.get("approver_id") != actor:
            raise IllegalTransition("approval requires the acting approver and decision=approved")
        _identifier(details.get("scope"), "approval scope")
        require_sha256(
            details.get("subject_digest"), field="approval subject_digest"
        )
        _identifier(
            details.get("authorization_ref"), "approval authorization_ref"
        )
        _identifier(details.get("evidence_receipt_id"), "evidence_receipt_id")
        executor_id = _identifier(details.get("executor_id"), "executor_id")
        verifier_id = _identifier(details.get("verifier_id"), "verifier_id")
        if executor_id == verifier_id:
            raise IllegalTransition("evidence executor and verifier must be independent")

    def retry_run(
        self,
        *,
        tenant_id: str,
        source_run_id: str,
        new_run_id: str,
        idempotency_key: str,
        actor: str,
    ) -> QaRun:
        tenant_id = _identifier(tenant_id, "tenant_id")
        source_run_id = _identifier(source_run_id, "source_run_id")
        new_run_id = _identifier(new_run_id, "new_run_id")
        idempotency_key = _identifier(idempotency_key, "idempotency_key")
        actor = _identifier(actor, "actor")
        request = {
            "tenant_id": tenant_id,
            "source_run_id": source_run_id,
            "new_run_id": new_run_id,
            "actor": actor,
        }
        request_digest = canonical_digest(request)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = self.get_run(
                tenant_id=tenant_id, run_id=source_run_id, connection=connection
            )
            self._validated_event_chain(
                connection, tenant_id=tenant_id, run_id=source_run_id
            )
            self._validated_audit_chain(
                connection, tenant_id=tenant_id, run_id=source_run_id
            )
            existing = self._existing_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command="retry",
                request_digest=request_digest,
                expected_run_id=new_run_id,
            )
            if existing is not None:
                return existing
            if source.status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
                raise IllegalTransition(
                    f"retry requires failed or cancelled source, got {source.status.value}"
                )
            if connection.execute(
                "SELECT 1 FROM qa_runs WHERE tenant_id = ? AND run_id = ?",
                (tenant_id, new_run_id),
            ).fetchone():
                raise RunAlreadyExists(f"run already exists: {tenant_id}/{new_run_id}")
            self._assert_run_capacity(connection, tenant_id=tenant_id)
            now = _utc_now()
            connection.execute(
                "INSERT INTO qa_runs "
                "(tenant_id, run_id, project_id, mode, status, input_digest, payload_json, "
                "attempt, retry_of, version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    tenant_id,
                    new_run_id,
                    source.project_id,
                    source.mode,
                    RunStatus.CREATED.value,
                    source.input_digest,
                    canonical_json_bytes(dict(source.payload)),
                    source.attempt + 1,
                    source.run_id,
                    now,
                    now,
                ),
            )
            self._create_chain_head(
                connection, tenant_id=tenant_id, run_id=new_run_id
            )
            self._append_event(
                connection,
                tenant_id=tenant_id,
                run_id=new_run_id,
                kind="run.retried",
                payload={"retry_of": source.run_id, "attempt": source.attempt + 1},
            )
            self._append_audit(
                connection,
                tenant_id=tenant_id,
                run_id=source.run_id,
                actor=actor,
                action="retry",
                outcome="accepted",
                details={"new_run_id": new_run_id},
            )
            result = self.get_run(
                tenant_id=tenant_id, run_id=new_run_id, connection=connection
            )
            self._store_response(
                connection,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command="retry",
                request_digest=request_digest,
                run=result,
                quota_run_id=source_run_id,
            )
            return result

    def get_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        connection: sqlite3.Connection | None = None,
    ) -> QaRun:
        tenant_id = _identifier(tenant_id, "tenant_id")
        run_id = _identifier(run_id, "run_id")
        owns_connection = connection is None
        active_connection = self._connect() if connection is None else connection
        try:
            row = active_connection.execute(
                "SELECT * FROM qa_runs WHERE tenant_id = ? AND run_id = ?",
                (tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise RunNotFound(f"run not found: {tenant_id}/{run_id}")
            run = self._run_from_row(row)
            if (run.tenant_id, run.run_id) != (tenant_id, run_id):
                raise ControlPlaneError(
                    "stored run lookup crossed the requested resource boundary"
                )
            return run
        finally:
            if owns_connection:
                active_connection.close()

    def recover_active_runs(
        self,
        *,
        tenant_id: str,
        limit: int = MAX_ACTIVE_RUNS_PER_TENANT,
    ) -> tuple[QaRun, ...]:
        tenant_id = _identifier(tenant_id, "tenant_id")
        if type(limit) is not int or not 1 <= limit <= MAX_HISTORY_PAGE_SIZE:
            raise ValueError(
                f"limit must be between 1 and {MAX_HISTORY_PAGE_SIZE}"
            )
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM qa_runs WHERE tenant_id = ? AND status IN ({placeholders}) "
                "ORDER BY created_at, run_id LIMIT ?",
                (
                    tenant_id,
                    *(status.value for status in ACTIVE_STATUSES),
                    limit + 1,
                ),
            ).fetchall()
        if len(rows) > limit:
            raise ResourceQuotaExceeded(
                "active run recovery exceeds its hard result bound"
            )
        runs = tuple(self._run_from_row(row) for row in rows)
        if any(run.tenant_id != tenant_id for run in runs):
            raise ControlPlaneError(
                "active run recovery crossed the requested tenant boundary"
            )
        return runs

    @staticmethod
    def _history_page_bounds(
        *, after: int, limit: int, cursor_field: str
    ) -> tuple[int, int]:
        if type(after) is not int or after < 0:
            raise ValueError(f"{cursor_field} must be a non-negative integer")
        if type(limit) is not int or not 1 <= limit <= MAX_HISTORY_PAGE_SIZE:
            raise ValueError(
                f"limit must be between 1 and {MAX_HISTORY_PAGE_SIZE}"
            )
        return after, limit

    def list_events(
        self,
        *,
        tenant_id: str,
        run_id: str,
        after_sequence: int = 0,
        limit: int = DEFAULT_HISTORY_PAGE_SIZE,
    ) -> tuple[QaEvent, ...]:
        after_sequence, limit = self._history_page_bounds(
            after=after_sequence, limit=limit, cursor_field="after_sequence"
        )
        with self._connect() as connection:
            run = self.get_run(
                tenant_id=tenant_id, run_id=run_id, connection=connection
            )
            events = self._validated_event_chain(
                connection, tenant_id=run.tenant_id, run_id=run.run_id
            )
            return tuple(
                event for event in events if event.sequence > after_sequence
            )[:limit]

    def list_audit(
        self,
        *,
        tenant_id: str,
        run_id: str,
        after_audit_id: int = 0,
        limit: int = DEFAULT_HISTORY_PAGE_SIZE,
    ) -> tuple[AuditRecord, ...]:
        after_audit_id, limit = self._history_page_bounds(
            after=after_audit_id, limit=limit, cursor_field="after_audit_id"
        )
        with self._connect() as connection:
            run = self.get_run(
                tenant_id=tenant_id, run_id=run_id, connection=connection
            )
            audit = self._validated_audit_chain(
                connection, tenant_id=run.tenant_id, run_id=run.run_id
            )
            return tuple(
                record for record in audit if record.audit_id > after_audit_id
            )[:limit]
