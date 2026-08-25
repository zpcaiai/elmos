"""Durable isolated run state, append-only events, and local evidence receipts."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, canonical_json, parse_json_strict, sha256_digest
from .errors import (
    EvidenceValidationError,
    IdempotencyConflict,
    RunNotFound,
    StateConflict,
)
from .runtime import (
    DOMAIN_PHASES,
    LOCAL_EXECUTED_SELF_ATTESTED,
    NOT_CERTIFIED,
    NOT_RUN,
    SkillRegistry,
    ValidatedRequest,
    validate_request,
)

ACTIVE = "ACTIVE"
PAUSED = "PAUSED"
CANCELLED = "CANCELLED"
READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"
LOCAL_HANDOFF_PREPARED = "LOCAL_HANDOFF_PREPARED"
BLOCKED = "BLOCKED"
REQUIRED_LOCAL_EVIDENCE_ROLES = frozenset({"catalog", "request", "plan"})

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}\Z")
_ROLE_RE = re.compile(r"[a-z][a-z0-9._:-]{0,127}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


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
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, project_id, run_id),
                    UNIQUE (tenant_id, project_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS run_events (
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
                );

                CREATE TABLE IF NOT EXISTS evidence_records (
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
                );

                CREATE TRIGGER IF NOT EXISTS run_events_no_update
                BEFORE UPDATE ON run_events
                BEGIN
                    SELECT RAISE(ABORT, 'run_events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS run_events_no_delete
                BEFORE DELETE ON run_events
                BEGIN
                    SELECT RAISE(ABORT, 'run_events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_records_no_update
                BEFORE UPDATE ON evidence_records
                BEGIN
                    SELECT RAISE(ABORT, 'evidence_records are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_records_no_delete
                BEFORE DELETE ON evidence_records
                BEGIN
                    SELECT RAISE(ABORT, 'evidence_records are append-only');
                END;
                """
            )

    def _validate_existing_schema(self) -> None:
        required_tables = {"runs", "run_events", "evidence_records"}
        required_triggers = {
            "run_events_no_update",
            "run_events_no_delete",
            "evidence_records_no_update",
            "evidence_records_no_delete",
        }
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'trigger')"
            ).fetchall()
        actual_tables = {str(row[1]) for row in rows if row[0] == "table"}
        actual_triggers = {str(row[1]) for row in rows if row[0] == "trigger"}
        if not required_tables.issubset(actual_tables) or not required_triggers.issubset(actual_triggers):
            raise StateConflict(
                "state database schema is incomplete",
                details={
                    "missing_tables": sorted(required_tables - actual_tables),
                    "missing_triggers": sorted(required_triggers - actual_triggers),
                },
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

    @staticmethod
    def _row_to_run(row: sqlite3.Row, *, replayed: bool = False) -> RunRecord:
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
        with self._connect() as connection:
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
                return self._row_to_run(existing, replayed=True)
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
        return self._row_to_run(row)

    def get_run(self, tenant_id: str, project_id: str, run_id: str) -> RunRecord:
        scope = (
            _identifier(tenant_id, "tenant_id"),
            _identifier(project_id, "project_id"),
            _identifier(run_id, "run_id"),
        )
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM runs WHERE tenant_id = ? AND project_id = ? AND run_id = ?", scope
            ).fetchone()
            if row is None:
                connection.rollback()
                raise RunNotFound("run does not exist in the requested tenant/project scope")
            current_state = str(row["state"])
            current_version = int(row["version"])
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
            connection.commit()
        assert result is not None
        return self._row_to_run(result)

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
        self.get_run(tenant_id, project_id, run_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM run_events
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                ORDER BY sequence
                """,
                (tenant_id, project_id, run_id),
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
        if executor == verifier:
            raise EvidenceValidationError("evidence executor and verifier must be distinct")
        if not isinstance(role, str) or not _ROLE_RE.fullmatch(role):
            raise EvidenceValidationError("evidence role is invalid")
        if role not in REQUIRED_LOCAL_EVIDENCE_ROLES:
            raise EvidenceValidationError("evidence role is not part of the bounded local readiness contract")
        if not isinstance(payload, dict) or not payload:
            raise EvidenceValidationError("evidence payload must be a non-empty JSON object")
        catalog_binding = run.plan.get("catalog")
        if (
            not isinstance(catalog_binding, dict)
            or set(catalog_binding) != {"source_archive_sha256", "compiled_contracts_sha256", "skill_count"}
            or catalog_binding.get("source_archive_sha256")
            != "sha256:952dce43681a56dbd3323ef03b334b08d5be980000e9c7ee3f0ac3e3bcd42c4e"
            or not isinstance(catalog_binding.get("compiled_contracts_sha256"), str)
            or not _DIGEST_RE.fullmatch(str(catalog_binding.get("compiled_contracts_sha256")))
            or catalog_binding.get("skill_count") != 196
        ):
            raise EvidenceValidationError("run plan has no valid pinned catalog binding")
        expected_payloads: dict[str, dict[str, object]] = {
            "catalog": {
                "authorization_id": authorization,
                "source_archive_sha256": catalog_binding["source_archive_sha256"],
                "compiled_contracts_sha256": catalog_binding["compiled_contracts_sha256"],
                "skill_count": 196,
            },
            "request": {
                "authorization_id": authorization,
                "request_sha256": run.request_sha256,
                "schema_version": "elmos.spring-golden-route.request.v1",
            },
            "plan": {
                "authorization_id": authorization,
                "plan_sha256": run.plan_sha256,
                "decision": "DRAFT_ONLY",
            },
        }
        if role in REQUIRED_LOCAL_EVIDENCE_ROLES and payload != expected_payloads[role]:
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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
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

    def list_evidence(self, tenant_id: str, project_id: str, run_id: str) -> list[dict[str, object]]:
        self.get_run(tenant_id, project_id, run_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM evidence_records
                WHERE tenant_id = ? AND project_id = ? AND run_id = ?
                ORDER BY evidence_id
                """,
                (tenant_id, project_id, run_id),
            ).fetchall()
        records = [self._evidence_dict(row) for row in rows]
        for record in records:
            payload_bytes = canonical_bytes(record["payload"])
            if (
                record["payload_sha256"] != sha256_digest(payload_bytes)
                or record["byte_count"] != len(payload_bytes)
                or record["executor_id"] == record["verifier_id"]
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
        # The local store has no independent authorization trust store. Even a
        # structurally complete receipt set is therefore only a local handoff,
        # never an external-gate readiness decision.
        decision = LOCAL_HANDOFF_PREPARED if not reasons else BLOCKED
        return {
            "decision": decision,
            "reasons": reasons,
            "missing_evidence_roles": missing_roles,
            "event_count": len(events),
            "evidence_count": len(evidence),
            "local_evaluation_status": LOCAL_EXECUTED_SELF_ATTESTED,
            "runtime_evidence_status": NOT_RUN,
            "customer_evidence_status": NOT_RUN,
            "external_evidence_status": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "side_effects_authorized": False,
        }
