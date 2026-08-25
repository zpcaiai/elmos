"""Durable isolated run state, append-only events, and local evidence receipts."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, canonical_json, parse_json_strict, sha256_digest
from .catalog import (
    COMPILED_CONTRACTS_SHA256,
    EXPECTED_SKILL_COUNT,
    SOURCE_ARCHIVE_SHA256,
)
from .errors import (
    EvidenceValidationError,
    IdempotencyConflict,
    RequestValidationError,
    RunNotFound,
    SchemaMigrationRequired,
    StateConflict,
)
from .runtime import (
    DOMAIN_PHASES,
    LOCAL_EXECUTED_SELF_ATTESTED,
    NOT_CERTIFIED,
    NOT_RUN,
    RESPONSE_SCHEMA_VERSION,
    SkillRegistry,
    ValidatedRequest,
    validate_request,
)

ACTIVE = "ACTIVE"
PAUSED = "PAUSED"
CANCELLED = "CANCELLED"
LOCAL_HANDOFF_PREPARED = "LOCAL_HANDOFF_PREPARED"
BLOCKED = "BLOCKED"
REQUIRED_LOCAL_EVIDENCE_ROLES = frozenset({"catalog", "request", "plan"})
STATE_SCHEMA_ID = "elmos.spring-golden-route.run-store"
STATE_SCHEMA_VERSION = 1


def _normalize_schema_sql(sql: str) -> str:
    """Normalize formatting while retaining every schema token and literal."""

    return re.sub(r"\s+", " ", sql.strip().removesuffix(";")).strip()


_SCHEMA_TABLE_SQL = {
    "engine_schema": """
        CREATE TABLE engine_schema (
            schema_id TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            schema_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """.strip(),
    "runs": """
        CREATE TABLE runs (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            request_json TEXT NOT NULL,
            plan_sha256 TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'PAUSED', 'CANCELLED')),
            version INTEGER NOT NULL CHECK (version >= 1),
            evidence_authorization_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, run_id),
            UNIQUE (tenant_id, project_id, idempotency_key)
        )
    """.strip(),
    "run_events": """
        CREATE TABLE run_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT NOT NULL,
            run_version INTEGER NOT NULL,
            occurred_at TEXT NOT NULL,
            previous_sha256 TEXT,
            event_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (tenant_id, project_id, run_id)
                REFERENCES runs (tenant_id, project_id, run_id)
        )
    """.strip(),
    "evidence_records": """
        CREATE TABLE evidence_records (
            tenant_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            role TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            byte_count INTEGER NOT NULL CHECK (byte_count > 0),
            executor_id TEXT NOT NULL,
            verifier_id TEXT NOT NULL,
            authorization_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (tenant_id, project_id, run_id, evidence_id),
            FOREIGN KEY (tenant_id, project_id, run_id)
                REFERENCES runs (tenant_id, project_id, run_id)
        )
    """.strip(),
}
_SCHEMA_TRIGGER_SQL = {
    "run_events_no_update": """
        CREATE TRIGGER run_events_no_update
        BEFORE UPDATE ON run_events
        BEGIN
            SELECT RAISE(ABORT, 'run_events are append-only');
        END
    """.strip(),
    "run_events_no_delete": """
        CREATE TRIGGER run_events_no_delete
        BEFORE DELETE ON run_events
        BEGIN
            SELECT RAISE(ABORT, 'run_events are append-only');
        END
    """.strip(),
    "evidence_records_no_update": """
        CREATE TRIGGER evidence_records_no_update
        BEFORE UPDATE ON evidence_records
        BEGIN
            SELECT RAISE(ABORT, 'evidence_records are append-only');
        END
    """.strip(),
    "evidence_records_no_delete": """
        CREATE TRIGGER evidence_records_no_delete
        BEFORE DELETE ON evidence_records
        BEGIN
            SELECT RAISE(ABORT, 'evidence_records are append-only');
        END
    """.strip(),
}
_SCHEMA_TRIGGER_TARGETS = {
    "run_events_no_update": "run_events",
    "run_events_no_delete": "run_events",
    "evidence_records_no_update": "evidence_records",
    "evidence_records_no_delete": "evidence_records",
}
_SCHEMA_TABLE_INFO = {
    "engine_schema": (
        ("schema_id", "TEXT", 0, None, 1),
        ("version", "INTEGER", 1, None, 0),
        ("schema_sha256", "TEXT", 1, None, 0),
        ("created_at", "TEXT", 1, None, 0),
    ),
    "runs": (
        ("tenant_id", "TEXT", 1, None, 1),
        ("project_id", "TEXT", 1, None, 2),
        ("run_id", "TEXT", 1, None, 3),
        ("task_id", "TEXT", 1, None, 0),
        ("skill_name", "TEXT", 1, None, 0),
        ("idempotency_key", "TEXT", 1, None, 0),
        ("request_sha256", "TEXT", 1, None, 0),
        ("request_json", "TEXT", 1, None, 0),
        ("plan_sha256", "TEXT", 1, None, 0),
        ("plan_json", "TEXT", 1, None, 0),
        ("state", "TEXT", 1, None, 0),
        ("version", "INTEGER", 1, None, 0),
        ("evidence_authorization_id", "TEXT", 0, None, 0),
        ("created_at", "TEXT", 1, None, 0),
        ("updated_at", "TEXT", 1, None, 0),
    ),
    "run_events": (
        ("sequence", "INTEGER", 0, None, 1),
        ("tenant_id", "TEXT", 1, None, 0),
        ("project_id", "TEXT", 1, None, 0),
        ("run_id", "TEXT", 1, None, 0),
        ("event_type", "TEXT", 1, None, 0),
        ("actor_id", "TEXT", 1, None, 0),
        ("from_state", "TEXT", 0, None, 0),
        ("to_state", "TEXT", 1, None, 0),
        ("run_version", "INTEGER", 1, None, 0),
        ("occurred_at", "TEXT", 1, None, 0),
        ("previous_sha256", "TEXT", 0, None, 0),
        ("event_sha256", "TEXT", 1, None, 0),
        ("payload_json", "TEXT", 1, None, 0),
    ),
    "evidence_records": (
        ("tenant_id", "TEXT", 1, None, 1),
        ("project_id", "TEXT", 1, None, 2),
        ("run_id", "TEXT", 1, None, 3),
        ("evidence_id", "TEXT", 1, None, 4),
        ("role", "TEXT", 1, None, 0),
        ("payload_json", "TEXT", 1, None, 0),
        ("payload_sha256", "TEXT", 1, None, 0),
        ("byte_count", "INTEGER", 1, None, 0),
        ("executor_id", "TEXT", 1, None, 0),
        ("verifier_id", "TEXT", 1, None, 0),
        ("authorization_id", "TEXT", 1, None, 0),
        ("created_at", "TEXT", 1, None, 0),
    ),
}
_SCHEMA_FOREIGN_KEYS = {
    "engine_schema": (),
    "runs": (),
    "run_events": (
        (0, 0, "runs", "tenant_id", "tenant_id", "NO ACTION", "NO ACTION", "NONE"),
        (0, 1, "runs", "project_id", "project_id", "NO ACTION", "NO ACTION", "NONE"),
        (0, 2, "runs", "run_id", "run_id", "NO ACTION", "NO ACTION", "NONE"),
    ),
    "evidence_records": (
        (0, 0, "runs", "tenant_id", "tenant_id", "NO ACTION", "NO ACTION", "NONE"),
        (0, 1, "runs", "project_id", "project_id", "NO ACTION", "NO ACTION", "NONE"),
        (0, 2, "runs", "run_id", "run_id", "NO ACTION", "NO ACTION", "NONE"),
    ),
}
_SCHEMA_INDEXES = {
    "engine_schema": (
        {
            "name": "sqlite_autoindex_engine_schema_1",
            "unique": True,
            "origin": "pk",
            "partial": False,
            "terms": (("schema_id", False, "BINARY"),),
        },
    ),
    "runs": (
        {
            "name": "sqlite_autoindex_runs_1",
            "unique": True,
            "origin": "pk",
            "partial": False,
            "terms": (
                ("tenant_id", False, "BINARY"),
                ("project_id", False, "BINARY"),
                ("run_id", False, "BINARY"),
            ),
        },
        {
            "name": "sqlite_autoindex_runs_2",
            "unique": True,
            "origin": "u",
            "partial": False,
            "terms": (
                ("tenant_id", False, "BINARY"),
                ("project_id", False, "BINARY"),
                ("idempotency_key", False, "BINARY"),
            ),
        },
    ),
    "run_events": (),
    "evidence_records": (
        {
            "name": "sqlite_autoindex_evidence_records_1",
            "unique": True,
            "origin": "pk",
            "partial": False,
            "terms": (
                ("tenant_id", False, "BINARY"),
                ("project_id", False, "BINARY"),
                ("run_id", False, "BINARY"),
                ("evidence_id", False, "BINARY"),
            ),
        },
    ),
}
_SCHEMA_DDL = ";\n\n".join(
    (*_SCHEMA_TABLE_SQL.values(), *_SCHEMA_TRIGGER_SQL.values())
) + ";"
_SCHEMA_CONTRACT = {
    "schema_id": STATE_SCHEMA_ID,
    "version": STATE_SCHEMA_VERSION,
    "tables": {
        name: {
            "sql": _normalize_schema_sql(sql),
            "table_info": _SCHEMA_TABLE_INFO[name],
            "foreign_keys": _SCHEMA_FOREIGN_KEYS[name],
            "indexes": _SCHEMA_INDEXES[name],
        }
        for name, sql in _SCHEMA_TABLE_SQL.items()
    },
    "triggers": {
        name: {
            "table": _SCHEMA_TRIGGER_TARGETS[name],
            "sql": _normalize_schema_sql(sql),
        }
        for name, sql in _SCHEMA_TRIGGER_SQL.items()
    },
}
STATE_SCHEMA_SHA256 = sha256_digest(canonical_bytes(_SCHEMA_CONTRACT))

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")
_ROLE_RE = re.compile(r"[a-z][a-z0-9._:-]{0,127}\Z")
_PLAN_RESPONSE_KEYS = {
    "actor_id", "batch", "batch_dependencies", "catalog", "certification", "constraints",
    "control_plane_execution_status", "customer_evidence_status", "decision",
    "dependencies", "domain_phase_status", "external_adapter_required",
    "external_evidence_status", "limitations", "objective", "operation",
    "output_blueprints", "project_id", "request_sha256", "run_id",
    "runtime_evidence_status", "schema_version", "side_effects_performed",
    "skill_name", "source", "source_contract_sha256", "source_id", "target",
    "task_id", "tenant_id",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise StateConflict(f"{label} is not a valid bounded identifier")
    return value


def _json_object(raw: str) -> dict[str, object]:
    value = parse_json_strict(raw)
    if not isinstance(value, dict):
        raise StateConflict("stored canonical JSON is not an object")
    return value


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _read_index_contract(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[dict[str, object], ...]:
    indexes: list[dict[str, object]] = []
    table_identifier = _quoted_identifier(table)
    for row in connection.execute(f"PRAGMA index_list({table_identifier})").fetchall():
        index_name = str(row[1])
        index_identifier = _quoted_identifier(index_name)
        terms = tuple(
            (
                None if item[2] is None else str(item[2]),
                bool(item[3]),
                None if item[4] is None else str(item[4]),
            )
            for item in connection.execute(f"PRAGMA index_xinfo({index_identifier})").fetchall()
            if int(item[5]) == 1
        )
        indexes.append(
            {
                "name": index_name,
                "unique": bool(row[2]),
                "origin": str(row[3]),
                "partial": bool(row[4]),
                "terms": terms,
            }
        )
    return tuple(sorted(indexes, key=lambda value: str(value["name"])))


@dataclass(frozen=True, slots=True)
class RunRecord:
    tenant_id: str
    project_id: str
    run_id: str
    task_id: str
    skill_name: str
    idempotency_key: str
    request_sha256: str
    plan_sha256: str
    state: str
    version: int
    evidence_authorization_id: str | None
    created_at: str
    updated_at: str
    request: dict[str, object]
    plan: dict[str, object]
    replayed: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "skill_name": self.skill_name,
            "idempotency_key": self.idempotency_key,
            "request_sha256": self.request_sha256,
            "plan_sha256": self.plan_sha256,
            "state": self.state,
            "version": self.version,
            "evidence_authorization_id": self.evidence_authorization_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "request": self.request,
            "plan": self.plan,
            "replayed": self.replayed,
            "runtime_evidence_status": NOT_RUN,
            "customer_evidence_status": NOT_RUN,
            "external_evidence_status": NOT_RUN,
            "certification": NOT_CERTIFIED,
        }


class RunStore:
    """SQLite state store scoped by the exact tenant/project/run tuple."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        registry: SkillRegistry | None = None,
        create: bool = True,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.registry = registry
        if not self.database_path.parent.is_dir():
            raise StateConflict("database parent directory does not exist")
        if create:
            self._initialize()
        else:
            if not self.database_path.is_file():
                raise RunNotFound("state database does not exist")
            self._validate_existing_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
        except BaseException:
            connection.close()
            raise
        return connection

    def _initialize(self) -> None:
        if self.database_path.exists():
            self._validate_existing_schema()
            return
        with closing(self._connect()) as connection, connection:
            connection.executescript(_SCHEMA_DDL)
            connection.execute(
                "INSERT INTO engine_schema (schema_id, version, schema_sha256, created_at) VALUES (?, ?, ?, ?)",
                (STATE_SCHEMA_ID, STATE_SCHEMA_VERSION, STATE_SCHEMA_SHA256, _now()),
            )
            connection.execute(f"PRAGMA user_version = {STATE_SCHEMA_VERSION}")
        self._validate_existing_schema()

    def _validate_existing_schema(self) -> None:
        expected_objects = {
            *(('table', name) for name in _SCHEMA_TABLE_SQL),
            *(('trigger', name) for name in _SCHEMA_TRIGGER_SQL),
        }
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """
                    SELECT type, name, tbl_name, sql
                    FROM sqlite_master
                    WHERE type IN ('table', 'index', 'trigger', 'view')
                    ORDER BY type, name
                    """
                ).fetchall()
                user_rows = [row for row in rows if not str(row[1]).startswith("sqlite_")]
                actual_objects = {
                    (str(row[0]), str(row[1]))
                    for row in user_rows
                    if str(row[0]) != "index"
                }
                if actual_objects != expected_objects:
                    raise SchemaMigrationRequired(
                        "state database schema objects drifted; automatic migration is forbidden",
                        details={
                            "missing_objects": sorted(expected_objects - actual_objects),
                            "unexpected_objects": sorted(actual_objects - expected_objects),
                        },
                    )

                rows_by_object = {(str(row[0]), str(row[1])): row for row in user_rows}
                for table, expected_sql in _SCHEMA_TABLE_SQL.items():
                    row = rows_by_object[("table", table)]
                    actual_sql = "" if row[3] is None else _normalize_schema_sql(str(row[3]))
                    normalized_expected = _normalize_schema_sql(expected_sql)
                    if str(row[2]) != table or actual_sql != normalized_expected:
                        raise SchemaMigrationRequired(
                            "state database table definition drift requires an explicit reviewed migration",
                            details={
                                "table": table,
                                "expected_sql": normalized_expected,
                                "actual_sql": actual_sql,
                            },
                        )

                for trigger, expected_sql in _SCHEMA_TRIGGER_SQL.items():
                    row = rows_by_object[("trigger", trigger)]
                    actual_sql = "" if row[3] is None else _normalize_schema_sql(str(row[3]))
                    expected_target = _SCHEMA_TRIGGER_TARGETS[trigger]
                    normalized_expected = _normalize_schema_sql(expected_sql)
                    if str(row[2]) != expected_target or actual_sql != normalized_expected:
                        raise SchemaMigrationRequired(
                            "state database trigger definition drift requires an explicit reviewed migration",
                            details={
                                "trigger": trigger,
                                "expected_table": expected_target,
                                "actual_table": str(row[2]),
                                "expected_sql": normalized_expected,
                                "actual_sql": actual_sql,
                            },
                        )

                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if user_version != STATE_SCHEMA_VERSION:
                    raise SchemaMigrationRequired(
                        "state database user_version is unsupported; an explicit reviewed migration is required",
                        details={"expected": STATE_SCHEMA_VERSION, "actual": user_version},
                    )

                for table, expected_table_info in _SCHEMA_TABLE_INFO.items():
                    table_identifier = _quoted_identifier(table)
                    actual_table_info = tuple(
                        (
                            str(row[1]),
                            str(row[2]),
                            int(row[3]),
                            row[4],
                            int(row[5]),
                        )
                        for row in connection.execute(
                            f"PRAGMA table_info({table_identifier})"
                        ).fetchall()
                    )
                    if actual_table_info != expected_table_info:
                        raise SchemaMigrationRequired(
                            "state database column contract drift requires an explicit reviewed migration",
                            details={
                                "table": table,
                                "expected": expected_table_info,
                                "actual": actual_table_info,
                            },
                        )

                    actual_foreign_keys = tuple(
                        tuple(row)
                        for row in connection.execute(
                            f"PRAGMA foreign_key_list({table_identifier})"
                        ).fetchall()
                    )
                    if actual_foreign_keys != _SCHEMA_FOREIGN_KEYS[table]:
                        raise SchemaMigrationRequired(
                            "state database foreign-key contract drift requires an explicit reviewed migration",
                            details={
                                "table": table,
                                "expected": _SCHEMA_FOREIGN_KEYS[table],
                                "actual": actual_foreign_keys,
                            },
                        )

                    actual_indexes = _read_index_contract(connection, table)
                    if actual_indexes != _SCHEMA_INDEXES[table]:
                        raise SchemaMigrationRequired(
                            "state database index contract drift requires an explicit reviewed migration",
                            details={
                                "table": table,
                                "expected": _SCHEMA_INDEXES[table],
                                "actual": actual_indexes,
                            },
                        )

                metadata = connection.execute(
                    "SELECT schema_id, version, schema_sha256 FROM engine_schema"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise SchemaMigrationRequired(
                "state database schema could not be validated; an explicit reviewed migration is required",
                details={"sqlite_error": type(exc).__name__},
            ) from exc

        if len(metadata) != 1 or tuple(metadata[0]) != (
            STATE_SCHEMA_ID,
            STATE_SCHEMA_VERSION,
            STATE_SCHEMA_SHA256,
        ):
            raise SchemaMigrationRequired(
                "state database schema metadata is missing or incompatible; automatic migration is forbidden"
            )

    @staticmethod
    def _event_body(
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_type: str,
        actor_id: str,
        from_state: str | None,
        to_state: str,
        run_version: int,
        occurred_at: str,
        previous_sha256: str | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "event_type": event_type,
            "actor_id": actor_id,
            "from_state": from_state,
            "to_state": to_state,
            "run_version": run_version,
            "occurred_at": occurred_at,
            "previous_sha256": previous_sha256,
            "payload": payload,
        }

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_type: str,
        actor_id: str,
        from_state: str | None,
        to_state: str,
        run_version: int,
        payload: dict[str, object],
    ) -> str:
        previous_row = connection.execute(
            """
            SELECT event_sha256 FROM run_events
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
            ORDER BY sequence DESC LIMIT 1
            """,
            (tenant_id, project_id, run_id),
        ).fetchone()
        previous_sha256 = str(previous_row[0]) if previous_row else None
        occurred_at = _now()
        body = self._event_body(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            event_type=event_type,
            actor_id=actor_id,
            from_state=from_state,
            to_state=to_state,
            run_version=run_version,
            occurred_at=occurred_at,
            previous_sha256=previous_sha256,
            payload=payload,
        )
        event_sha256 = sha256_digest(canonical_bytes(body))
        connection.execute(
            """
            INSERT INTO run_events (
                tenant_id, project_id, run_id, event_type, actor_id,
                from_state, to_state, run_version, occurred_at,
                previous_sha256, event_sha256, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                project_id,
                run_id,
                event_type,
                actor_id,
                from_state,
                to_state,
                run_version,
                occurred_at,
                previous_sha256,
                event_sha256,
                canonical_json(payload),
            ),
        )
        return event_sha256

    def _row_to_run(self, row: sqlite3.Row, *, replayed: bool = False) -> RunRecord:
        if self.registry is None:
            raise StateConflict("run access requires the exact validated Skill registry")
        request_raw = str(row["request_json"])
        plan_raw = str(row["plan_json"])
        request = _json_object(request_raw)
        plan = _json_object(plan_raw)
        request_canonical = canonical_json(request)
        plan_canonical = canonical_json(plan)
        if request_raw != request_canonical or sha256_digest(request_canonical.encode("utf-8")) != row["request_sha256"]:
            raise StateConflict("stored request content/digest integrity check failed")
        if plan_raw != plan_canonical or sha256_digest(plan_canonical.encode("utf-8")) != row["plan_sha256"]:
            raise StateConflict("stored plan content/digest integrity check failed")
        try:
            validated_request = validate_request(request)
        except RequestValidationError as exc:
            raise StateConflict("stored request no longer satisfies the exact request contract") from exc
        column_bindings = {
            "tenant_id": validated_request.tenant_id,
            "project_id": validated_request.project_id,
            "run_id": validated_request.run_id,
            "task_id": validated_request.task_id,
            "skill_name": validated_request.skill_name,
            "idempotency_key": validated_request.idempotency_key,
            "request_sha256": validated_request.digest,
        }
        for column, expected in column_bindings.items():
            if row[column] != expected:
                raise StateConflict(
                    "run row is not bound to its canonical request",
                    details={"column": column},
                )
        if set(plan) != _PLAN_RESPONSE_KEYS:
            raise StateConflict("stored plan response field set is invalid")
        plan_bindings = {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "decision": "DRAFT_ONLY",
            "operation": "plan",
            "skill_name": validated_request.skill_name,
            "request_sha256": validated_request.digest,
            "tenant_id": validated_request.tenant_id,
            "project_id": validated_request.project_id,
            "run_id": validated_request.run_id,
            "task_id": validated_request.task_id,
            "actor_id": validated_request.actor_id,
            "control_plane_execution_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "runtime_evidence_status": NOT_RUN,
            "customer_evidence_status": NOT_RUN,
            "external_evidence_status": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "side_effects_performed": False,
            "external_adapter_required": True,
        }
        for field, expected in plan_bindings.items():
            if plan.get(field) != expected:
                raise StateConflict(
                    "stored plan is not bound to its canonical request/run",
                    details={"field": field},
                )
        catalog = plan.get("catalog")
        if (
            not isinstance(catalog, dict)
            or set(catalog) != {"source_archive_sha256", "compiled_contracts_sha256", "skill_count"}
            or catalog.get("source_archive_sha256") != SOURCE_ARCHIVE_SHA256
            or catalog.get("compiled_contracts_sha256") != COMPILED_CONTRACTS_SHA256
            or catalog.get("skill_count") != EXPECTED_SKILL_COUNT
        ):
            raise StateConflict("stored plan catalog binding is invalid")
        phases = plan.get("domain_phase_status")
        if not isinstance(phases, dict) or set(phases) != set(DOMAIN_PHASES) or any(
            status != NOT_RUN for status in phases.values()
        ):
            raise StateConflict("stored plan contains unsupported execution evidence")
        expected_plan = self.registry.dispatch(validated_request)
        if canonical_json(expected_plan) != plan_canonical:
            raise StateConflict("stored plan differs from the exact validated registry response")
        return RunRecord(
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["run_id"]),
            task_id=str(row["task_id"]),
            skill_name=str(row["skill_name"]),
            idempotency_key=str(row["idempotency_key"]),
            request_sha256=str(row["request_sha256"]),
            plan_sha256=str(row["plan_sha256"]),
            state=str(row["state"]),
            version=int(row["version"]),
            evidence_authorization_id=(
                str(row["evidence_authorization_id"])
                if row["evidence_authorization_id"] is not None
                else None
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            request=request,
            plan=plan,
            replayed=replayed,
        )

    def create_run(self, request: ValidatedRequest, plan: dict[str, object]) -> RunRecord:
        validated_request = validate_request(request.as_dict())
        if validated_request.digest != request.digest:
            raise StateConflict("validated request content diverges from its digest")
        request = validated_request
        if request.operation != "plan":
            raise StateConflict("only a validated plan request can create a run")
        if self.registry is None:
            raise StateConflict("create_run requires the exact validated Skill registry")
        expected_plan = self.registry.dispatch(request)
        if canonical_json(plan) != canonical_json(expected_plan):
            raise StateConflict("run plan is not the exact response from the validated Skill registry")
        if (
            plan.get("decision") != "DRAFT_ONLY"
            or plan.get("skill_name") != request.skill_name
            or plan.get("request_sha256") != request.digest
            or plan.get("side_effects_performed") is not False
        ):
            raise StateConflict("run plan is not bound to the validated request")
        phases = plan.get("domain_phase_status")
        if not isinstance(phases, dict) or set(phases) != set(DOMAIN_PHASES) or any(
            status != NOT_RUN for status in phases.values()
        ):
            raise StateConflict("run plan contains unsupported domain execution evidence")
        request_json = request.canonical.decode("utf-8")
        plan_json = canonical_json(plan)
        plan_sha256 = sha256_digest(plan_json.encode("utf-8"))
        now = _now()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM runs
                WHERE tenant_id = ? AND project_id = ? AND idempotency_key = ?
                """,
                (request.tenant_id, request.project_id, request.idempotency_key),
            ).fetchone()
            if existing is not None:
                if (
                    existing["request_sha256"] != request.digest
                    or existing["plan_sha256"] != plan_sha256
                    or existing["run_id"] != request.run_id
                ):
                    connection.rollback()
                    raise IdempotencyConflict(
                        "idempotency key is already bound to different content",
                        details={"idempotency_key": request.idempotency_key},
                    )
                connection.commit()
                replay = self._row_to_run(existing, replayed=True)
                self._verified_events(replay)
                return replay
            same_run = connection.execute(
                "SELECT 1 FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (request.tenant_id, request.project_id, request.run_id),
            ).fetchone()
            if same_run is not None:
                connection.rollback()
                raise StateConflict("run_id already exists in this tenant/project scope")
            connection.execute(
                """
                INSERT INTO runs (
                    tenant_id, project_id, run_id, task_id, skill_name,
                    idempotency_key, request_sha256, request_json,
                    plan_sha256, plan_json, state, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 1, ?, ?)
                """,
                (
                    request.tenant_id,
                    request.project_id,
                    request.run_id,
                    request.task_id,
                    request.skill_name,
                    request.idempotency_key,
                    request.digest,
                    request_json,
                    plan_sha256,
                    plan_json,
                    now,
                    now,
                ),
            )
            self._append_event(
                connection,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                run_id=request.run_id,
                event_type="RUN_CREATED",
                actor_id=request.actor_id,
                from_state=None,
                to_state=ACTIVE,
                run_version=1,
                payload={
                    "idempotency_key": request.idempotency_key,
                    "request_sha256": request.digest,
                    "plan_sha256": plan_sha256,
                },
            )
            row = connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?",
                (request.tenant_id, request.project_id, request.run_id),
            ).fetchone()
            connection.commit()
        assert row is not None
        created = self._row_to_run(row)
        self._verified_events(created)
        return created

    def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord:
        run = self._get_run_without_event_validation(tenant_id, project_id, run_id)
        self._verified_events(run)
        return run

    def _get_run_without_event_validation(
        self, tenant_id: str, project_id: str, run_id: str
    ) -> RunRecord:
        scope = (
            _identifier(tenant_id, "tenant_id"),
            _identifier(project_id, "project_id"),
            _identifier(run_id, "run_id"),
        )
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?", scope
            ).fetchone()
        if row is None:
            raise RunNotFound("run does not exist in the requested tenant/project scope")
        return self._row_to_run(row)

    def _transition(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        actor_id: str,
        expected_version: int,
        event_type: str,
        allowed_states: frozenset[str],
        target_state: str,
    ) -> RunRecord:
        scope = (
            _identifier(tenant_id, "tenant_id"),
            _identifier(project_id, "project_id"),
            _identifier(run_id, "run_id"),
        )
        actor = _identifier(actor_id, "actor_id")
        if type(expected_version) is not int or expected_version < 1:
            raise StateConflict("expected_version must be a positive integer")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?", scope
            ).fetchone()
            if row is None:
                connection.rollback()
                raise RunNotFound("run does not exist in the requested tenant/project scope")
            current_run = self._row_to_run(row)
            self._verified_events(current_run, connection=connection)
            current_state = current_run.state
            current_version = current_run.version
            if current_version != expected_version:
                connection.rollback()
                raise StateConflict(
                    "optimistic version conflict",
                    details={"expected_version": expected_version, "actual_version": current_version},
                )
            if current_state not in allowed_states:
                connection.rollback()
                raise StateConflict(
                    "invalid state transition",
                    details={"state": current_state, "event_type": event_type},
                )
            new_version = current_version + 1
            now = _now()
            updated = connection.execute(
                """
                UPDATE runs SET state = ?, version = ?, updated_at = ?
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                  AND state = ? AND version = ?
                """,
                (target_state, new_version, now, *scope, current_state, current_version),
            )
            if updated.rowcount != 1:
                connection.rollback()
                raise StateConflict("concurrent run update detected")
            self._append_event(
                connection,
                tenant_id=scope[0],
                project_id=scope[1],
                run_id=scope[2],
                event_type=event_type,
                actor_id=actor,
                from_state=current_state,
                to_state=target_state,
                run_version=new_version,
                payload={"expected_version": expected_version},
            )
            result = connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?", scope
            ).fetchone()
            assert result is not None
            terminal_run = self._row_to_run(result)
            self._verified_events(terminal_run, connection=connection)
            connection.commit()
        return self.get_run(scope[0], scope[1], scope[2])

    def pause(
        self, tenant_id: str, project_id: str, run_id: str, *, actor_id: str, expected_version: int
    ) -> RunRecord:
        return self._transition(
            tenant_id,
            project_id,
            run_id,
            actor_id=actor_id,
            expected_version=expected_version,
            event_type="RUN_PAUSED",
            allowed_states=frozenset({ACTIVE}),
            target_state=PAUSED,
        )

    def resume(
        self, tenant_id: str, project_id: str, run_id: str, *, actor_id: str, expected_version: int
    ) -> RunRecord:
        return self._transition(
            tenant_id,
            project_id,
            run_id,
            actor_id=actor_id,
            expected_version=expected_version,
            event_type="RUN_RESUMED",
            allowed_states=frozenset({PAUSED}),
            target_state=ACTIVE,
        )

    def cancel(
        self, tenant_id: str, project_id: str, run_id: str, *, actor_id: str, expected_version: int
    ) -> RunRecord:
        return self._transition(
            tenant_id,
            project_id,
            run_id,
            actor_id=actor_id,
            expected_version=expected_version,
            event_type="RUN_CANCELLED",
            allowed_states=frozenset({ACTIVE, PAUSED}),
            target_state=CANCELLED,
        )

    def list_events(self, tenant_id: str, project_id: str, run_id: str) -> list[dict[str, object]]:
        run = self._get_run_without_event_validation(tenant_id, project_id, run_id)
        return self._verified_events(run)

    def _verified_events(
        self,
        run: RunRecord,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with closing(self._connect()) as owned_connection:
                return self._verified_events(run, connection=owned_connection)
        rows = connection.execute(
            """
            SELECT * FROM run_events
            WHERE tenant_id = ? AND project_id = ? AND run_id = ?
            ORDER BY sequence
            """,
            (run.tenant_id, run.project_id, run.run_id),
        ).fetchall()
        events: list[dict[str, object]] = []
        expected_previous: str | None = None
        for row in rows:
            payload = _json_object(str(row["payload_json"]))
            body = self._event_body(
                tenant_id=str(row["tenant_id"]),
                project_id=str(row["project_id"]),
                run_id=str(row["run_id"]),
                event_type=str(row["event_type"]),
                actor_id=str(row["actor_id"]),
                from_state=str(row["from_state"]) if row["from_state"] is not None else None,
                to_state=str(row["to_state"]),
                run_version=int(row["run_version"]),
                occurred_at=str(row["occurred_at"]),
                previous_sha256=str(row["previous_sha256"]) if row["previous_sha256"] is not None else None,
                payload=payload,
            )
            actual_digest = sha256_digest(canonical_bytes(body))
            if row["previous_sha256"] != expected_previous or row["event_sha256"] != actual_digest:
                raise StateConflict("append-only event hash chain verification failed")
            expected_previous = actual_digest
            events.append({"sequence": int(row["sequence"]), **body, "event_sha256": actual_digest})
        if not events:
            raise StateConflict("run has no creation event")
        creation = events[0]
        expected_creation_payload = {
            "idempotency_key": run.idempotency_key,
            "request_sha256": run.request_sha256,
            "plan_sha256": run.plan_sha256,
        }
        if (
            creation["event_type"] != "RUN_CREATED"
            or creation["actor_id"] != run.request["actor_id"]
            or creation["from_state"] is not None
            or creation["to_state"] != ACTIVE
            or creation["run_version"] != 1
            or creation["payload"] != expected_creation_payload
        ):
            raise StateConflict("RUN_CREATED event is not bound to the current run row")
        previous_state = ACTIVE
        expected_transitions = {
            "RUN_PAUSED": ({ACTIVE}, PAUSED),
            "RUN_RESUMED": ({PAUSED}, ACTIVE),
            "RUN_CANCELLED": ({ACTIVE, PAUSED}, CANCELLED),
        }
        for expected_version, event in enumerate(events[1:], start=2):
            transition = expected_transitions.get(str(event["event_type"]))
            if transition is None:
                raise StateConflict("event chain contains an unsupported transition")
            allowed_from, target = transition
            if (
                previous_state not in allowed_from
                or event["from_state"] != previous_state
                or event["to_state"] != target
                or event["run_version"] != expected_version
                or event["payload"] != {"expected_version": expected_version - 1}
            ):
                raise StateConflict("event transition is inconsistent with the run state machine")
            previous_state = target
        if run.version != len(events) or run.state != previous_state:
            raise StateConflict("current run state/version is not the terminal event-chain state")
        return events

    def record_evidence(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        evidence_id: str,
        role: str,
        payload: dict[str, object],
        executor_id: str,
        verifier_id: str,
        authorization_id: str,
    ) -> dict[str, object]:
        run = self.get_run(tenant_id, project_id, run_id)
        evidence = _identifier(evidence_id, "evidence_id")
        executor = _identifier(executor_id, "executor_id")
        verifier = _identifier(verifier_id, "verifier_id")
        authorization = _identifier(authorization_id, "authorization_id")
        if run.evidence_authorization_id is not None and run.evidence_authorization_id != authorization:
            raise EvidenceValidationError("evidence authorization differs from the run authorization binding")
        if executor == verifier:
            raise EvidenceValidationError("evidence executor and verifier must be distinct")
        if not isinstance(role, str) or not _ROLE_RE.fullmatch(role):
            raise EvidenceValidationError("evidence role is invalid")
        if role not in REQUIRED_LOCAL_EVIDENCE_ROLES:
            raise EvidenceValidationError("evidence role is not part of the bounded local readiness contract")
        if evidence != f"evidence-{role}":
            raise EvidenceValidationError("evidence_id must be deterministically bound to its required role")
        if not isinstance(payload, dict) or not payload:
            raise EvidenceValidationError("evidence payload must be a non-empty JSON object")
        catalog_binding = run.plan.get("catalog")
        if (
            not isinstance(catalog_binding, dict)
            or set(catalog_binding) != {"source_archive_sha256", "compiled_contracts_sha256", "skill_count"}
            or catalog_binding.get("source_archive_sha256") != SOURCE_ARCHIVE_SHA256
            or catalog_binding.get("compiled_contracts_sha256") != COMPILED_CONTRACTS_SHA256
            or catalog_binding.get("skill_count") != EXPECTED_SKILL_COUNT
        ):
            raise EvidenceValidationError("run plan has no valid pinned catalog binding")
        expected_payload = self._expected_evidence_payload(
            run, role, authorization, executor, verifier
        )
        if payload != expected_payload:
            raise EvidenceValidationError(
                "required evidence role payload is not exactly bound to this run, authorization, and pinned catalog"
            )
        try:
            payload_bytes = canonical_bytes(payload)
        except Exception as exc:
            raise EvidenceValidationError("evidence payload is not bounded canonical JSON") from exc
        if len(payload_bytes) > 65_536:
            raise EvidenceValidationError("evidence payload exceeds 65536 bytes")
        payload_sha256 = sha256_digest(payload_bytes)
        created_at = _now()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE runs SET evidence_authorization_id = ?
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                  AND evidence_authorization_id IS NULL
                """,
                (authorization, tenant_id, project_id, run_id),
            )
            bound_authorization = connection.execute(
                """
                SELECT evidence_authorization_id FROM runs
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                """,
                (tenant_id, project_id, run_id),
            ).fetchone()
            if bound_authorization is None or bound_authorization[0] != authorization:
                connection.rollback()
                raise EvidenceValidationError("run evidence authorization binding conflict")
            existing = connection.execute(
                """
                SELECT * FROM evidence_records
                WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND evidence_id = ?
                """,
                (tenant_id, project_id, run_id, evidence),
            ).fetchone()
            if existing is not None:
                matches = (
                    existing["role"] == role
                    and existing["payload_sha256"] == payload_sha256
                    and existing["executor_id"] == executor
                    and existing["verifier_id"] == verifier
                    and existing["authorization_id"] == authorization
                )
                connection.commit()
                if not matches:
                    raise EvidenceValidationError("evidence_id is already bound to different content")
                return self._evidence_dict(existing, replayed=True)
            connection.execute(
                """
                INSERT INTO evidence_records (
                    tenant_id, project_id, run_id, evidence_id, role,
                    payload_json, payload_sha256, byte_count,
                    executor_id, verifier_id, authorization_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.tenant_id,
                    run.project_id,
                    run.run_id,
                    evidence,
                    role,
                    payload_bytes.decode("utf-8"),
                    payload_sha256,
                    len(payload_bytes),
                    executor,
                    verifier,
                    authorization,
                    created_at,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM evidence_records
                WHERE tenant_id = ? AND project_id = ? AND run_id = ? AND evidence_id = ?
                """,
                (tenant_id, project_id, run_id, evidence),
            ).fetchone()
            connection.commit()
        assert row is not None
        return self._evidence_dict(row)

    @staticmethod
    def _evidence_dict(row: sqlite3.Row, *, replayed: bool = False) -> dict[str, object]:
        return {
            "tenant_id": str(row["tenant_id"]),
            "project_id": str(row["project_id"]),
            "run_id": str(row["run_id"]),
            "evidence_id": str(row["evidence_id"]),
            "role": str(row["role"]),
            "payload": _json_object(str(row["payload_json"])),
            "payload_sha256": str(row["payload_sha256"]),
            "byte_count": int(row["byte_count"]),
            "executor_id": str(row["executor_id"]),
            "verifier_id": str(row["verifier_id"]),
            "authorization_id": str(row["authorization_id"]),
            "created_at": str(row["created_at"]),
            "replayed": replayed,
        }

    @staticmethod
    def _expected_evidence_payload(
        run: RunRecord,
        role: str,
        authorization_id: str,
        executor_id: str,
        verifier_id: str,
    ) -> dict[str, object]:
        catalog = run.plan["catalog"]
        payloads: dict[str, dict[str, object]] = {
            "catalog": {
                "authorization_id": authorization_id,
                "executor_id": executor_id,
                "verifier_id": verifier_id,
                "source_archive_sha256": catalog["source_archive_sha256"],
                "compiled_contracts_sha256": catalog["compiled_contracts_sha256"],
                "skill_count": EXPECTED_SKILL_COUNT,
            },
            "request": {
                "authorization_id": authorization_id,
                "executor_id": executor_id,
                "verifier_id": verifier_id,
                "request_sha256": run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            "plan": {
                "authorization_id": authorization_id,
                "executor_id": executor_id,
                "verifier_id": verifier_id,
                "plan_sha256": run.plan_sha256,
                "decision": "DRAFT_ONLY",
            },
        }
        try:
            return payloads[role]
        except KeyError as exc:
            raise EvidenceValidationError("stored evidence role is outside the exact local contract") from exc

    def list_evidence(self, tenant_id: str, project_id: str, run_id: str) -> list[dict[str, object]]:
        run = self.get_run(tenant_id, project_id, run_id)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_records
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                ORDER BY evidence_id
                """,
                (tenant_id, project_id, run_id),
            ).fetchall()
        records = [self._evidence_dict(row) for row in rows]
        if run.evidence_authorization_id is not None and not records:
            raise EvidenceValidationError("run authorization binding exists but its evidence rows are missing")
        for record in records:
            payload_bytes = canonical_bytes(record["payload"])
            if (
                record["tenant_id"] != run.tenant_id
                or record["project_id"] != run.project_id
                or record["run_id"] != run.run_id
                or record["role"] not in REQUIRED_LOCAL_EVIDENCE_ROLES
                or record["evidence_id"] != f"evidence-{record['role']}"
                or record["authorization_id"] != run.evidence_authorization_id
            ):
                raise EvidenceValidationError("stored evidence scope or role is not bound to the current run")
            try:
                _identifier(str(record["evidence_id"]), "evidence_id")
                _identifier(str(record["executor_id"]), "executor_id")
                _identifier(str(record["verifier_id"]), "verifier_id")
                authorization = _identifier(str(record["authorization_id"]), "authorization_id")
            except StateConflict as exc:
                raise EvidenceValidationError("stored evidence identity is invalid") from exc
            expected_payload = self._expected_evidence_payload(
                run,
                str(record["role"]),
                authorization,
                str(record["executor_id"]),
                str(record["verifier_id"]),
            )
            if (
                record["payload_sha256"] != sha256_digest(payload_bytes)
                or record["byte_count"] != len(payload_bytes)
                or record["executor_id"] == record["verifier_id"]
                or record["payload"] != expected_payload
            ):
                raise EvidenceValidationError("stored evidence integrity check failed")
        return records

    def evaluate_readiness(self, tenant_id: str, project_id: str, run_id: str) -> dict[str, object]:
        run = self.get_run(tenant_id, project_id, run_id)
        events = self.list_events(tenant_id, project_id, run_id)
        evidence = self.list_evidence(tenant_id, project_id, run_id)
        roles = {str(record["role"]) for record in evidence}
        missing_roles = sorted(REQUIRED_LOCAL_EVIDENCE_ROLES - roles)
        reasons: list[str] = []
        if run.state != PAUSED:
            reasons.append("run must be PAUSED for an external gate handoff")
        if missing_roles:
            reasons.append("missing digest-bound local evidence roles")
        required_records = [record for record in evidence if record["role"] in REQUIRED_LOCAL_EVIDENCE_ROLES]
        role_counts = {
            role: sum(1 for record in required_records if record["role"] == role)
            for role in REQUIRED_LOCAL_EVIDENCE_ROLES
        }
        if any(count != 1 for count in role_counts.values()):
            reasons.append("each required evidence role must have exactly one immutable record")
        authorizations = {record["authorization_id"] for record in required_records}
        if len(authorizations) != 1:
            reasons.append("required evidence must share one exact authorization binding")
        phases = run.plan.get("domain_phase_status")
        if not isinstance(phases, dict) or set(phases) != set(DOMAIN_PHASES) or any(
            value != NOT_RUN for value in phases.values()
        ):
            reasons.append("plan evidence boundary is invalid")
        structurally_complete = not reasons
        # A caller-provided authorization identifier is not an independently
        # verified authorization. The generic local store has no trust store,
        # so its decision remains BLOCKED even when the handoff structure is
        # locally complete.
        reasons.append("independent authorization and verifier trust were NOT_RUN")
        return {
            "decision": BLOCKED,
            "local_handoff_status": LOCAL_HANDOFF_PREPARED if structurally_complete else BLOCKED,
            "reasons": reasons,
            "missing_evidence_roles": missing_roles,
            "event_count": len(events),
            "evidence_count": len(evidence),
            "local_evaluation_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "authorization_verification_status": NOT_RUN,
            "independent_verifier_status": NOT_RUN,
            "runtime_evidence_status": NOT_RUN,
            "customer_evidence_status": NOT_RUN,
            "external_evidence_status": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "side_effects_authorized": False,
        }
