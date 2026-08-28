"""Durable state and append-only history for the PI Harness.

SQLite is supported for a single-node deployment and local development.  The
schema and transaction boundaries are deliberately explicit so a PostgreSQL
adapter can preserve the same invariants; this module never treats process
memory as authoritative.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self

from .canonical import (
    canonical_bytes,
    digest,
    require_nonempty,
    require_uuid,
    utc_after,
    utc_now,
)
from .lifecycle import assert_transition
from .models import (
    AuthoritySnapshot,
    ConflictError,
    ExecutorIdentity,
    HarnessError,
    LeaseConflictError,
    NotFoundError,
    QuotaExceededError,
    StaleGenerationError,
    TaskState,
    ToolInvocation,
    ToolResult,
    WorkspaceLease,
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenant (
    tenant_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project (
    project_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    name TEXT NOT NULL,
    repository_uri TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    project_id TEXT NOT NULL REFERENCES project(project_id),
    objective TEXT NOT NULL,
    parent_task_id TEXT,
    state TEXT NOT NULL,
    request_json TEXT NOT NULL,
    required_verifications INTEGER NOT NULL DEFAULT 0,
    passed_verifications INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_tenant_state ON task(tenant_id, state);

CREATE TABLE IF NOT EXISTS task_event (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task(task_id),
    task_sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    correlation_id TEXT,
    causation_id TEXT,
    payload_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, task_sequence)
);
CREATE INDEX IF NOT EXISTS idx_task_event_tenant_task_seq
    ON task_event(tenant_id, task_id, task_sequence);

CREATE TABLE IF NOT EXISTS idempotency_key (
    tenant_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    response_json TEXT,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY(tenant_id, scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS execution_environment (
    environment_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    execution_id TEXT NOT NULL,
    owner_execution_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0,
    environment_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    sandbox_overrides_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_environment_tenant_execution
    ON execution_environment(tenant_id, execution_id);

CREATE TABLE IF NOT EXISTS authority_snapshot (
    authority_snapshot_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    authority_owner_id TEXT NOT NULL,
    environment_id TEXT NOT NULL REFERENCES execution_environment(environment_id),
    permission_profile_version TEXT NOT NULL,
    allowed_capabilities_json TEXT NOT NULL,
    denied_capabilities_json TEXT NOT NULL,
    sandbox_overrides_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executor_connection (
    environment_id TEXT NOT NULL REFERENCES execution_environment(environment_id),
    executor_id TEXT NOT NULL,
    executor_generation INTEGER NOT NULL,
    connection_epoch INTEGER NOT NULL,
    state TEXT NOT NULL,
    retired INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(environment_id, executor_id, executor_generation)
);
CREATE INDEX IF NOT EXISTS idx_executor_active
    ON executor_connection(environment_id, retired, executor_generation);

CREATE TABLE IF NOT EXISTS workspace_lease (
    workspace_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    owner_execution_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    repository_id TEXT NOT NULL,
    base_revision TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task(task_id),
    workspace_id TEXT,
    owner_execution_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    workspace_digest TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_call (
    call_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task(task_id),
    environment_id TEXT NOT NULL REFERENCES execution_environment(environment_id),
    authority_snapshot_id TEXT NOT NULL REFERENCES authority_snapshot(authority_snapshot_id),
    capability TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    executor_generation INTEGER NOT NULL,
    state TEXT NOT NULL,
    result_json TEXT,
    error_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(tenant_id, task_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS effect_journal (
    effect_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task(task_id),
    action_kind TEXT NOT NULL,
    parent_call_id TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    resolver_id TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, task_id, action_kind, effect_id)
);

CREATE TABLE IF NOT EXISTS artifact (
    artifact_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES task(task_id),
    logical_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(tenant_id, task_id, sha256)
);

CREATE TABLE IF NOT EXISTS campaign (
    campaign_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    name TEXT NOT NULL,
    mode TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS benchmark_run (
    run_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaign(campaign_id),
    tenant_id TEXT NOT NULL,
    system TEXT NOT NULL,
    system_version TEXT,
    repo_revision TEXT NOT NULL,
    task_case TEXT NOT NULL,
    repetition INTEGER NOT NULL,
    validated_success INTEGER,
    evidence_level TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(campaign_id, system, task_case, repetition)
);
"""


class DurableStore:
    """Thread-safe transactional store with tenant-scoped reads and writes."""

    def __init__(self, path: str = ":memory:", artifact_root: str | Path | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        if path != ":memory:":
            db_path = Path(path)
            if db_path.exists() and db_path.is_symlink():
                raise HarnessError("database path must not be a symlink")
            db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA busy_timeout=30000")
            if path != ":memory:":
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.executescript(SCHEMA)
            # Keep file-backed installations forward compatible with the first
            # development schema, which did not have parent_task_id.
            task_columns = {row[1] for row in self._connection.execute("PRAGMA table_info(task)").fetchall()}
            if "parent_task_id" not in task_columns:
                self._connection.execute("ALTER TABLE task ADD COLUMN parent_task_id TEXT")
            self._connection.commit()
        except sqlite3.Error as exc:
            raise HarnessError(f"unable to open durable store: {exc}") from exc
        root = Path(artifact_root) if artifact_root is not None else Path(tempfile.gettempdir()) / "elmos-pi-harness-artifacts"
        if not root.is_absolute():
            raise ValueError("artifact_root must be absolute")
        root.mkdir(parents=True, exist_ok=True)
        self._artifact_root = root.resolve()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                yield self._connection
            except Exception:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            yield self._connection

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_bytes(value).decode("utf-8")

    @staticmethod
    def _decode(value: str | None) -> Any:
        return json.loads(value) if value is not None else None

    def _ensure_tenant_locked(self, tenant_id: str, display_name: str | None = None) -> None:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        self._connection.execute(
            "INSERT INTO tenant(tenant_id, display_name, created_at) VALUES(?,?,?) ON CONFLICT(tenant_id) DO NOTHING",
            (tenant_id, display_name or tenant_id, utc_now()),
        )

    def _ensure_project_locked(self, tenant_id: str, project_id: str, name: str | None = None) -> None:
        project_id = require_uuid(project_id, "project_id")
        row = self._connection.execute(
            "SELECT tenant_id FROM project WHERE project_id=?", (project_id,)
        ).fetchone()
        if row and row["tenant_id"] != tenant_id:
            raise NotFoundError("project not found")
        self._connection.execute(
            "INSERT INTO project(project_id,tenant_id,name,created_at) VALUES(?,?,?,?) ON CONFLICT(project_id) DO NOTHING",
            (project_id, tenant_id, name or project_id, utc_now()),
        )

    def _idempotency_locked(self, tenant_id: str, scope: str, key: str, request_digest: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT request_digest,response_json,state FROM idempotency_key WHERE tenant_id=? AND scope=? AND idempotency_key=?",
            (tenant_id, scope, key),
        ).fetchone()
        if row is None:
            self._connection.execute(
                "INSERT INTO idempotency_key(tenant_id,scope,idempotency_key,request_digest,state,created_at) VALUES(?,?,?,?,?,?)",
                (tenant_id, scope, key, request_digest, "in_flight", utc_now()),
            )
            return None
        if row["request_digest"] != request_digest:
            raise ConflictError("idempotency key was reused with a different request")
        if row["response_json"] is None:
            raise ConflictError("an equivalent request is already in progress")
        return {"response": self._decode(row["response_json"]), "replayed": True}

    def _finish_idempotency_locked(self, tenant_id: str, scope: str, key: str, response: Mapping[str, Any]) -> None:
        self._connection.execute(
            "UPDATE idempotency_key SET response_json=?,state='completed',completed_at=? WHERE tenant_id=? AND scope=? AND idempotency_key=?",
            (self._json(dict(response)), utc_now(), tenant_id, scope, key),
        )

    def _append_event_locked(
        self,
        tenant_id: str,
        task_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        actor_id: str,
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> dict[str, Any]:
        task = self._connection.execute(
            "SELECT project_id FROM task WHERE task_id=? AND tenant_id=?", (task_id, tenant_id)
        ).fetchone()
        if task is None:
            raise NotFoundError("task not found")
        last = self._connection.execute(
            "SELECT COALESCE(MAX(task_sequence),0) AS n FROM task_event WHERE task_id=?", (task_id,)
        ).fetchone()["n"]
        event = {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "project_id": task["project_id"],
            "task_id": task_id,
            "task_sequence": int(last) + 1,
            "event_type": require_nonempty(event_type, "event_type", 128),
            "actor_id": require_nonempty(actor_id, "actor_id", 256),
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "payload_version": 1,
            "payload": dict(payload),
            "created_at": utc_now(),
        }
        self._connection.execute(
            "INSERT INTO task_event(event_id,tenant_id,project_id,task_id,task_sequence,event_type,actor_id,correlation_id,causation_id,payload_version,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event["event_id"], event["tenant_id"], event["project_id"], event["task_id"], event["task_sequence"],
                event["event_type"], event["actor_id"], event["correlation_id"], event["causation_id"],
                event["payload_version"], self._json(event["payload"]), event["created_at"],
            ),
        )
        return event

    def create_task(
        self,
        tenant_id: str,
        project_id: str,
        objective: str,
        *,
        idempotency_key: str,
        request_payload: Mapping[str, Any] | None = None,
        actor_id: str = "system",
        task_id: str | None = None,
        project_name: str | None = None,
        parent_task_id: str | None = None,
    ) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        project_id = require_uuid(project_id, "project_id")
        objective = require_nonempty(objective, "objective", 1_000_000)
        idempotency_key = require_nonempty(idempotency_key, "idempotency_key", 256)
        request = dict(request_payload or {"project_id": project_id, "objective": objective})
        request_digest = digest(request)
        scope = "task:create"
        with self._write():
            self._ensure_tenant_locked(tenant_id)
            self._ensure_project_locked(tenant_id, project_id, project_name)
            replay = self._idempotency_locked(tenant_id, scope, idempotency_key, request_digest)
            if replay:
                return replay["response"] | {"replayed": True}
            task_id = require_uuid(task_id or str(uuid.uuid4()), "task_id")
            if parent_task_id is not None:
                parent_task_id = require_uuid(parent_task_id, "parent_task_id")
                self._task_locked(tenant_id, parent_task_id)
            now = utc_now()
            self._connection.execute(
                "INSERT INTO task(task_id,tenant_id,project_id,objective,parent_task_id,state,request_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (task_id, tenant_id, project_id, objective, parent_task_id, TaskState.CREATED.value, self._json(request), now, now),
            )
            event = self._append_event_locked(tenant_id, task_id, "task.created", {"objective": objective}, actor_id)
            response = {
                "task_id": task_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "status": TaskState.CREATED.value,
                "event_sequence": event["task_sequence"],
                "replayed": False,
            }
            self._finish_idempotency_locked(tenant_id, scope, idempotency_key, response)
            return response

    def _task_locked(self, tenant_id: str, task_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM task WHERE task_id=? AND tenant_id=?", (task_id, tenant_id)
        ).fetchone()
        if row is None:
            raise NotFoundError("task not found")
        return row

    def get_task(self, tenant_id: str, task_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        with self._read():
            row = self._task_locked(tenant_id, task_id)
            return {
                "task_id": row["task_id"], "tenant_id": row["tenant_id"], "project_id": row["project_id"],
                "objective": row["objective"], "status": row["state"], "request": self._decode(row["request_json"]),
                "parent_task_id": row["parent_task_id"],
                "required_verifications": row["required_verifications"], "passed_verifications": row["passed_verifications"],
                "created_at": row["created_at"], "updated_at": row["updated_at"],
            }

    def transition_task(
        self,
        tenant_id: str,
        task_id: str,
        target: str | TaskState,
        *,
        idempotency_key: str,
        actor_id: str,
        payload: Mapping[str, Any] | None = None,
        max_running_tasks: int = 3,
    ) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        target_state = TaskState(target)
        if max_running_tasks < 1:
            raise ValueError("max_running_tasks must be positive")
        body = {"task_id": task_id, "target": target_state.value, "payload": dict(payload or {})}
        scope = f"task:{task_id}:transition"
        key = require_nonempty(idempotency_key, "idempotency_key", 256)
        with self._write():
            replay = self._idempotency_locked(tenant_id, scope, key, digest(body))
            if replay:
                return replay["response"] | {"replayed": True}
            row = self._task_locked(tenant_id, task_id)
            current = TaskState(row["state"])
            assert_transition(current, target_state)
            if target_state is TaskState.SUCCEEDED:
                if body["payload"].get("verification_passed") is not True:
                    raise ConflictError("successful task requires an explicit passing verification result")
                if row["passed_verifications"] < row["required_verifications"]:
                    raise ConflictError("successful task is missing required verification gates")
            if target_state is TaskState.RUNNING and current is not TaskState.RUNNING:
                active = self._connection.execute(
                    "SELECT COUNT(*) AS n FROM task WHERE tenant_id=? AND state=?", (tenant_id, TaskState.RUNNING.value)
                ).fetchone()["n"]
                if int(active) >= max_running_tasks:
                    raise QuotaExceededError("tenant running-task quota exceeded")
            now = utc_now()
            self._connection.execute("UPDATE task SET state=?,updated_at=? WHERE task_id=? AND tenant_id=?", (target_state.value, now, task_id, tenant_id))
            event = self._append_event_locked(tenant_id, task_id, f"task.{target_state.value.lower()}", body["payload"], actor_id)
            response = {"task_id": task_id, "status": target_state.value, "event_sequence": event["task_sequence"], "replayed": False}
            self._finish_idempotency_locked(tenant_id, scope, key, response)
            return response

    def set_required_verifications(self, tenant_id: str, task_id: str, required: int) -> None:
        if required < 0:
            raise ValueError("required verification count cannot be negative")
        with self._write():
            self._task_locked(require_uuid(tenant_id, "tenant_id"), require_uuid(task_id, "task_id"))
            self._connection.execute("UPDATE task SET required_verifications=?,updated_at=? WHERE task_id=?", (required, utc_now(), task_id))

    def record_verification(self, tenant_id: str, task_id: str, passed: bool, *, actor_id: str, verification_type: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        verification_type = require_nonempty(verification_type, "verification_type", 128)
        with self._write():
            row = self._task_locked(tenant_id, task_id)
            if passed:
                self._connection.execute("UPDATE task SET passed_verifications=passed_verifications+1,updated_at=? WHERE task_id=?", (utc_now(), task_id))
            event = self._append_event_locked(tenant_id, task_id, "verification.completed", {"type": verification_type, "passed": passed}, actor_id)
            return {"task_id": task_id, "passed": passed, "event_sequence": event["task_sequence"], "passed_verifications": row["passed_verifications"] + int(passed)}

    def events(self, tenant_id: str, task_id: str, *, after_sequence: int = 0, limit: int = 100) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        if after_sequence < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid event pagination")
        with self._read():
            self._task_locked(tenant_id, task_id)
            rows = self._connection.execute(
                "SELECT * FROM task_event WHERE tenant_id=? AND task_id=? AND task_sequence>? ORDER BY task_sequence LIMIT ?",
                (tenant_id, task_id, after_sequence, limit),
            ).fetchall()
            items = [
                {
                    "event_id": row["event_id"], "sequence": row["task_sequence"], "global_sequence": row["sequence"],
                    "tenant_id": row["tenant_id"], "project_id": row["project_id"], "task_id": row["task_id"],
                    "event_type": row["event_type"], "actor_id": row["actor_id"], "correlation_id": row["correlation_id"],
                    "causation_id": row["causation_id"], "payload_version": row["payload_version"],
                    "payload": self._decode(row["payload_json"]), "created_at": row["created_at"],
                }
                for row in rows
            ]
            return {"items": items, "next_sequence": items[-1]["sequence"] if len(items) == limit else None}

    def branch_task(self, tenant_id: str, source_task_id: str, objective: str, *, idempotency_key: str, actor_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        source_task_id = require_uuid(source_task_id, "source_task_id")
        objective = require_nonempty(objective, "objective", 1_000_000)
        key = require_nonempty(idempotency_key, "idempotency_key", 256)
        body = {"source_task_id": source_task_id, "objective": objective}
        scope = f"task:{source_task_id}:branch"
        with self._write():
            source = self._task_locked(tenant_id, source_task_id)
            replay = self._idempotency_locked(tenant_id, scope, key, digest(body))
            if replay:
                return replay["response"] | {"replayed": True}
            task_id = str(uuid.uuid4())
            now = utc_now()
            self._connection.execute(
                "INSERT INTO task(task_id,tenant_id,project_id,objective,parent_task_id,state,request_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (task_id, tenant_id, source["project_id"], objective, source_task_id, TaskState.CREATED.value, self._json(body), now, now),
            )
            event = self._append_event_locked(tenant_id, task_id, "task.created", {"objective": objective, "parent_task_id": source_task_id}, actor_id)
            self._append_event_locked(tenant_id, source_task_id, "task.branched", {"child_task_id": task_id}, actor_id)
            response = {"task_id": task_id, "parent_task_id": source_task_id, "status": TaskState.CREATED.value, "event_sequence": event["task_sequence"], "replayed": False}
            self._finish_idempotency_locked(tenant_id, scope, key, response)
            return response

    def create_environment(
        self,
        tenant_id: str,
        execution_id: str,
        environment_type: str,
        *,
        config: Mapping[str, Any] | None = None,
        sandbox_overrides: Mapping[str, Any] | None = None,
        environment_id: str | None = None,
    ) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        execution_id = require_uuid(execution_id, "execution_id")
        environment_id = require_uuid(environment_id or str(uuid.uuid4()), "environment_id")
        environment_type = require_nonempty(environment_type, "environment_type", 64)
        with self._write():
            self._ensure_tenant_locked(tenant_id)
            now = utc_now()
            self._connection.execute(
                "INSERT INTO execution_environment(environment_id,tenant_id,execution_id,owner_execution_id,generation,environment_type,config_json,sandbox_overrides_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (environment_id, tenant_id, execution_id, execution_id, 0, environment_type, self._json(dict(config or {})), self._json(dict(sandbox_overrides or {})), now, now),
            )
            return self.get_environment(tenant_id, environment_id)

    def get_environment(self, tenant_id: str, environment_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        environment_id = require_uuid(environment_id, "environment_id")
        with self._read():
            row = self._connection.execute("SELECT * FROM execution_environment WHERE tenant_id=? AND environment_id=?", (tenant_id, environment_id)).fetchone()
            if row is None:
                raise NotFoundError("environment not found")
            return {
                "environment_id": row["environment_id"], "tenant_id": row["tenant_id"], "execution_id": row["execution_id"],
                "owner_execution_id": row["owner_execution_id"], "generation": row["generation"],
                "environment_type": row["environment_type"], "config": self._decode(row["config_json"]),
                "sandbox_overrides": self._decode(row["sandbox_overrides_json"]), "updated_at": row["updated_at"],
            }

    def create_authority_snapshot(self, tenant_id: str, snapshot_id: str, snapshot: AuthoritySnapshot) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        snapshot_id = require_uuid(snapshot_id, "authority_snapshot_id")
        with self._write():
            env = self._connection.execute(
                "SELECT 1 FROM execution_environment WHERE tenant_id=? AND environment_id=?", (tenant_id, snapshot.environment_id)
            ).fetchone()
            if env is None:
                raise NotFoundError("environment not found")
            self._connection.execute(
                "INSERT INTO authority_snapshot(authority_snapshot_id,tenant_id,authority_owner_id,environment_id,permission_profile_version,allowed_capabilities_json,denied_capabilities_json,sandbox_overrides_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (snapshot_id, tenant_id, snapshot.authority_owner_id, snapshot.environment_id, snapshot.permission_profile_version, self._json(sorted(snapshot.allowed_capabilities)), self._json(sorted(snapshot.denied_capabilities)), self._json(dict(snapshot.sandbox_overrides)), utc_now()),
            )
            return {"authority_snapshot_id": snapshot_id, "tenant_id": tenant_id, **snapshot.to_dict(), "snapshot_digest": snapshot.snapshot_digest}

    def get_authority_snapshot(self, tenant_id: str, snapshot_id: str) -> AuthoritySnapshot:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        snapshot_id = require_uuid(snapshot_id, "authority_snapshot_id")
        with self._read():
            row = self._connection.execute("SELECT * FROM authority_snapshot WHERE tenant_id=? AND authority_snapshot_id=?", (tenant_id, snapshot_id)).fetchone()
            if row is None:
                raise NotFoundError("authority snapshot not found")
            return AuthoritySnapshot(
                authority_owner_id=row["authority_owner_id"], environment_id=row["environment_id"],
                permission_profile_version=row["permission_profile_version"],
                allowed_capabilities=frozenset(self._decode(row["allowed_capabilities_json"])),
                denied_capabilities=frozenset(self._decode(row["denied_capabilities_json"])),
                sandbox_overrides=self._decode(row["sandbox_overrides_json"]),
            )

    def register_executor(self, tenant_id: str, environment_id: str, identity: ExecutorIdentity) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        environment_id = require_uuid(environment_id, "environment_id")
        with self._write():
            env = self._connection.execute("SELECT generation FROM execution_environment WHERE tenant_id=? AND environment_id=?", (tenant_id, environment_id)).fetchone()
            if env is None:
                raise NotFoundError("environment not found")
            active = self._connection.execute("SELECT * FROM executor_connection WHERE environment_id=? AND retired=0 ORDER BY executor_generation DESC LIMIT 1", (environment_id,)).fetchone()
            if active and identity.generation < int(active["executor_generation"]):
                raise StaleGenerationError("executor generation is older than the active generation")
            if active and identity.generation == int(active["executor_generation"]) and identity.executor_id != active["executor_id"]:
                raise ConflictError("executor generation already belongs to another executor")
            self._connection.execute("UPDATE executor_connection SET retired=1,state='RETIRED',updated_at=? WHERE environment_id=? AND retired=0", (utc_now(), environment_id))
            self._connection.execute(
                "INSERT INTO executor_connection(environment_id,executor_id,executor_generation,connection_epoch,state,retired,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(environment_id,executor_id,executor_generation) DO UPDATE SET state='CONNECTED',retired=0,updated_at=excluded.updated_at",
                (environment_id, identity.executor_id, identity.generation, identity.generation, "CONNECTED", 0, utc_now()),
            )
            self._connection.execute("UPDATE execution_environment SET generation=?,updated_at=? WHERE tenant_id=? AND environment_id=?", (identity.generation, utc_now(), tenant_id, environment_id))
            return {"environment_id": environment_id, **identity.to_dict(), "state": "CONNECTED"}

    def assert_active_executor(self, tenant_id: str, environment_id: str, identity: ExecutorIdentity) -> None:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        environment_id = require_uuid(environment_id, "environment_id")
        with self._read():
            row = self._connection.execute(
                "SELECT ec.executor_id,ec.executor_generation FROM executor_connection ec JOIN execution_environment ee ON ee.environment_id=ec.environment_id WHERE ee.tenant_id=? AND ec.environment_id=? AND ec.retired=0 ORDER BY ec.executor_generation DESC LIMIT 1",
                (tenant_id, environment_id),
            ).fetchone()
            if row is None or row["executor_id"] != identity.executor_id or int(row["executor_generation"]) != identity.generation:
                raise StaleGenerationError("stale_executor_generation")

    def acquire_workspace(
        self,
        tenant_id: str,
        lease: WorkspaceLease,
        *,
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        if lease_seconds < 1 or lease_seconds > 86_400:
            raise ValueError("lease_seconds out of range")
        with self._write():
            existing = self._connection.execute("SELECT * FROM workspace_lease WHERE workspace_id=?", (lease.workspace_id,)).fetchone()
            now = utc_now()
            if existing:
                if existing["tenant_id"] != tenant_id:
                    raise LeaseConflictError("workspace is not available")
                if (existing["owner_execution_id"] == lease.owner_execution_id and existing["repository_id"] == lease.repository_id and existing["base_revision"] == lease.base_revision):
                    return {"bound": True, "idempotent": True, "lease": self._lease_dict(existing)}
                raise LeaseConflictError("workspace_owned_by_other_execution")
            self._ensure_tenant_locked(tenant_id)
            expires = utc_after(lease_seconds)
            self._connection.execute(
                "INSERT INTO workspace_lease(workspace_id,tenant_id,owner_execution_id,generation,repository_id,base_revision,lifecycle_state,metadata_json,heartbeat_at,lease_expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (lease.workspace_id, tenant_id, lease.owner_execution_id, lease.generation, lease.repository_id, lease.base_revision, lease.lifecycle_state, self._json(dict(lease.metadata)), now, expires, now),
            )
            return {"bound": True, "idempotent": False, "lease": lease.to_dict() | {"tenant_id": tenant_id, "heartbeat_at": now, "lease_expires_at": expires}}

    def _lease_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "workspace_id": row["workspace_id"], "tenant_id": row["tenant_id"], "owner_execution_id": row["owner_execution_id"],
            "generation": row["generation"], "repository_id": row["repository_id"], "base_revision": row["base_revision"],
            "lifecycle_state": row["lifecycle_state"], "metadata": self._decode(row["metadata_json"]),
            "heartbeat_at": row["heartbeat_at"], "lease_expires_at": row["lease_expires_at"],
        }

    def heartbeat_workspace(self, tenant_id: str, workspace_id: str, owner_execution_id: str, generation: int, *, lease_seconds: int = 300) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        owner_execution_id = require_uuid(owner_execution_id, "owner_execution_id")
        if lease_seconds < 1 or lease_seconds > 86_400:
            raise ValueError("lease_seconds out of range")
        with self._write():
            row = self._connection.execute("SELECT * FROM workspace_lease WHERE tenant_id=? AND workspace_id=?", (tenant_id, workspace_id)).fetchone()
            if row is None:
                raise NotFoundError("workspace lease not found")
            if row["owner_execution_id"] != owner_execution_id or int(row["generation"]) != generation:
                raise StaleGenerationError("workspace lease generation is stale")
            now = utc_now()
            self._connection.execute("UPDATE workspace_lease SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE workspace_id=?", (now, utc_after(lease_seconds), now, workspace_id))
            return self._lease_dict(self._connection.execute("SELECT * FROM workspace_lease WHERE workspace_id=?", (workspace_id,)).fetchone())

    def takeover_workspace(self, tenant_id: str, workspace_id: str, requester_execution_id: str, checkpoint_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        requester_execution_id = require_uuid(requester_execution_id, "requester_execution_id")
        checkpoint_id = require_uuid(checkpoint_id, "checkpoint_id")
        with self._write():
            row = self._connection.execute("SELECT * FROM workspace_lease WHERE tenant_id=? AND workspace_id=?", (tenant_id, workspace_id)).fetchone()
            if row is None:
                raise NotFoundError("workspace lease not found")
            checkpoint = self._connection.execute("SELECT 1 FROM checkpoint WHERE tenant_id=? AND checkpoint_id=? AND workspace_id=? AND owner_execution_id=?", (tenant_id, checkpoint_id, workspace_id, row["owner_execution_id"])).fetchone()
            if checkpoint is None:
                raise ConflictError("checkpoint_not_ready")
            if row["owner_execution_id"] == requester_execution_id:
                raise ConflictError("same_owner_should_resume_not_takeover")
            if row["lease_expires_at"] > utc_now():
                raise LeaseConflictError("owner_not_stale")
            generation = int(row["generation"]) + 1
            now = utc_now()
            self._connection.execute("UPDATE workspace_lease SET owner_execution_id=?,generation=?,lifecycle_state='TAKEN_OVER',heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE tenant_id=? AND workspace_id=?", (requester_execution_id, generation, now, utc_after(300), now, tenant_id, workspace_id))
            updated = self._connection.execute("SELECT * FROM workspace_lease WHERE workspace_id=?", (workspace_id,)).fetchone()
            return {"bound": True, "taken_over": True, "lease": self._lease_dict(updated)}

    def record_checkpoint(self, tenant_id: str, task_id: str, owner_execution_id: str, state: Mapping[str, Any], *, workspace_id: str | None = None, workspace_digest: str | None = None, checkpoint_id: str | None = None) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        owner_execution_id = require_uuid(owner_execution_id, "owner_execution_id")
        checkpoint_id = require_uuid(checkpoint_id or str(uuid.uuid4()), "checkpoint_id")
        with self._write():
            self._task_locked(tenant_id, task_id)
            now = utc_now()
            self._connection.execute("INSERT INTO checkpoint(checkpoint_id,tenant_id,task_id,workspace_id,owner_execution_id,state_json,workspace_digest,created_at) VALUES(?,?,?,?,?,?,?,?)", (checkpoint_id, tenant_id, task_id, workspace_id, owner_execution_id, self._json(dict(state)), workspace_digest, now))
            return {"checkpoint_id": checkpoint_id, "tenant_id": tenant_id, "task_id": task_id, "workspace_id": workspace_id, "owner_execution_id": owner_execution_id, "created_at": now}

    def begin_tool_call(self, tenant_id: str, invocation: ToolInvocation, identity: ExecutorIdentity) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        self.assert_active_executor(tenant_id, invocation.environment_id, identity)
        with self._write():
            self._task_locked(tenant_id, invocation.task_id)
            existing = self._connection.execute("SELECT * FROM tool_call WHERE tenant_id=? AND task_id=? AND idempotency_key=?", (tenant_id, invocation.task_id, invocation.idempotency_key)).fetchone()
            if existing:
                if existing["request_digest"] != invocation.request_digest:
                    raise ConflictError("tool idempotency key was reused with a different request")
                if existing["result_json"] is not None:
                    return {"replayed": True, "result": ToolResult.from_dict(self._decode(existing["result_json"]))}
                raise ConflictError("tool call is already in progress")
            now = utc_now()
            self._connection.execute("INSERT INTO tool_call(call_id,tenant_id,task_id,environment_id,authority_snapshot_id,capability,request_digest,idempotency_key,executor_id,executor_generation,state,started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (invocation.call_id, tenant_id, invocation.task_id, invocation.environment_id, invocation.authority_snapshot_id, invocation.capability, invocation.request_digest, invocation.idempotency_key, identity.executor_id, identity.generation, "REQUESTED", now))
            self._append_event_locked(tenant_id, invocation.task_id, "tool.requested", {"call_id": invocation.call_id, "capability": invocation.capability, "executor_generation": identity.generation}, "runtime")
            return {"replayed": False, "call_id": invocation.call_id, "state": "REQUESTED"}

    def mark_tool_executing(self, tenant_id: str, call_id: str, identity: ExecutorIdentity) -> None:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        call_id = require_uuid(call_id, "call_id")
        with self._write():
            row = self._connection.execute("SELECT * FROM tool_call WHERE tenant_id=? AND call_id=?", (tenant_id, call_id)).fetchone()
            if row is None:
                raise NotFoundError("tool call not found")
            self.assert_active_executor(tenant_id, row["environment_id"], identity)
            if row["state"] != "REQUESTED":
                raise ConflictError("tool call is not requestable")
            self._connection.execute("UPDATE tool_call SET state='EXECUTING' WHERE tenant_id=? AND call_id=?", (tenant_id, call_id))

    def complete_tool_call(self, tenant_id: str, call_id: str, identity: ExecutorIdentity, result: ToolResult) -> ToolResult:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        call_id = require_uuid(call_id, "call_id")
        if result.call_id != call_id:
            raise ConflictError("tool result call_id does not match request")
        with self._write():
            row = self._connection.execute("SELECT * FROM tool_call WHERE tenant_id=? AND call_id=?", (tenant_id, call_id)).fetchone()
            if row is None:
                raise NotFoundError("tool call not found")
            self.assert_active_executor(tenant_id, row["environment_id"], identity)
            if row["result_json"] is not None:
                return ToolResult.from_dict(self._decode(row["result_json"]))
            now = utc_now()
            self._connection.execute("UPDATE tool_call SET state=?,result_json=?,finished_at=? WHERE tenant_id=? AND call_id=?", (result.status.upper(), self._json(result.to_dict()), now, tenant_id, call_id))
            self._append_event_locked(tenant_id, row["task_id"], "tool.completed" if result.status == "completed" else "tool.failed", {"call_id": call_id, "status": result.status, "executor_generation": identity.generation}, "runtime")
            return result

    def begin_effect(self, tenant_id: str, task_id: str, effect_id: str, action_kind: str, *, parent_call_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        effect_id = require_uuid(effect_id, "effect_id")
        action_kind = require_nonempty(action_kind, "action_kind", 128)
        with self._write():
            self._task_locked(tenant_id, task_id)
            existing = self._connection.execute("SELECT * FROM effect_journal WHERE tenant_id=? AND effect_id=?", (tenant_id, effect_id)).fetchone()
            if existing:
                return self._effect_dict(existing) | {"replayed": True}
            now = utc_now()
            self._connection.execute("INSERT INTO effect_journal(effect_id,tenant_id,task_id,action_kind,parent_call_id,status,metadata_json,updated_at) VALUES(?,?,?,?,?,?,?,?)", (effect_id, tenant_id, task_id, action_kind, parent_call_id, "PENDING", self._json(dict(metadata or {})), now))
            self._append_event_locked(tenant_id, task_id, "effect.approval_requested", {"effect_id": effect_id, "action_kind": action_kind}, "runtime")
            row = self._connection.execute("SELECT * FROM effect_journal WHERE effect_id=?", (effect_id,)).fetchone()
            return self._effect_dict(row) | {"replayed": False}

    def resolve_effect(self, tenant_id: str, effect_id: str, *, approved: bool, resolver_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        resolver_id = require_nonempty(resolver_id, "resolver_id", 256)
        with self._write():
            row = self._connection.execute("SELECT * FROM effect_journal WHERE tenant_id=? AND effect_id=?", (tenant_id, effect_id)).fetchone()
            if row is None:
                raise NotFoundError("effect not found")
            if row["status"] != "PENDING":
                return self._effect_dict(row)
            status = "APPROVED" if approved else "DENIED"
            now = utc_now()
            self._connection.execute("UPDATE effect_journal SET status=?,resolver_id=?,updated_at=? WHERE tenant_id=? AND effect_id=?", (status, resolver_id, now, tenant_id, effect_id))
            self._append_event_locked(tenant_id, row["task_id"], "effect.approval_resolved", {"effect_id": effect_id, "status": status}, resolver_id)
            return self._effect_dict(self._connection.execute("SELECT * FROM effect_journal WHERE effect_id=?", (effect_id,)).fetchone())

    def _effect_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"effect_id": row["effect_id"], "tenant_id": row["tenant_id"], "task_id": row["task_id"], "action_kind": row["action_kind"], "parent_call_id": row["parent_call_id"], "status": row["status"], "metadata": self._decode(row["metadata_json"]), "resolver_id": row["resolver_id"], "updated_at": row["updated_at"]}

    def put_artifact(self, tenant_id: str, task_id: str, logical_name: str, content: bytes, *, media_type: str = "application/octet-stream", metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        logical_name = require_nonempty(logical_name, "logical_name", 512)
        if len(content) > 256 * 1024 * 1024:
            raise ValueError("artifact exceeds 256 MiB")
        sha = digest_bytes(content)
        with self._write():
            self._task_locked(tenant_id, task_id)
            existing = self._connection.execute("SELECT * FROM artifact WHERE tenant_id=? AND task_id=? AND sha256=?", (tenant_id, task_id, sha)).fetchone()
            if existing:
                return self._artifact_dict(existing) | {"replayed": True}
            relative = Path(tenant_id) / sha[7:9] / sha[7:]
            target = self._artifact_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.is_symlink() or target.stat().st_size != len(content):
                    raise HarnessError("artifact content-addressed path is unsafe")
            else:
                fd, temp_name = tempfile.mkstemp(prefix=".artifact-", dir=str(target.parent))
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(content)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temp_name, target)
                finally:
                    if os.path.exists(temp_name):
                        os.unlink(temp_name)
            now = utc_now()
            artifact_id = str(uuid.uuid4())
            self._connection.execute("INSERT INTO artifact(artifact_id,tenant_id,task_id,logical_name,media_type,size_bytes,sha256,storage_uri,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (artifact_id, tenant_id, task_id, logical_name, media_type, len(content), sha, str(target), self._json(dict(metadata or {})), now))
            self._append_event_locked(tenant_id, task_id, "artifact.created", {"artifact_id": artifact_id, "sha256": sha, "size_bytes": len(content)}, "runtime")
            row = self._connection.execute("SELECT * FROM artifact WHERE artifact_id=?", (artifact_id,)).fetchone()
            return self._artifact_dict(row) | {"replayed": False}

    def _artifact_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {"artifact_id": row["artifact_id"], "tenant_id": row["tenant_id"], "task_id": row["task_id"], "logical_name": row["logical_name"], "media_type": row["media_type"], "size_bytes": row["size_bytes"], "sha256": row["sha256"], "storage_uri": row["storage_uri"], "metadata": self._decode(row["metadata_json"]), "created_at": row["created_at"]}

    def artifacts(self, tenant_id: str, task_id: str) -> list[dict[str, Any]]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        task_id = require_uuid(task_id, "task_id")
        with self._read():
            self._task_locked(tenant_id, task_id)
            return [self._artifact_dict(row) for row in self._connection.execute("SELECT * FROM artifact WHERE tenant_id=? AND task_id=? ORDER BY created_at", (tenant_id, task_id)).fetchall()]

    def create_campaign(self, tenant_id: str, campaign_id: str, name: str, mode: str, definition: Mapping[str, Any]) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        campaign_id = require_uuid(campaign_id, "campaign_id")
        name = require_nonempty(name, "name", 256)
        mode = require_nonempty(mode, "mode", 64)
        with self._write():
            self._ensure_tenant_locked(tenant_id)
            now = utc_now()
            self._connection.execute("INSERT INTO campaign(campaign_id,tenant_id,name,mode,definition_json,created_at) VALUES(?,?,?,?,?,?)", (campaign_id, tenant_id, name, mode, self._json(dict(definition)), now))
            return {"campaign_id": campaign_id, "tenant_id": tenant_id, "name": name, "mode": mode, "created_at": now}

    def record_benchmark_run(self, tenant_id: str, campaign_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        campaign_id = require_uuid(campaign_id, "campaign_id")
        required = ("run_id", "system", "repo_revision", "task_case", "repetition", "evidence_level")
        missing = [key for key in required if key not in result]
        if missing:
            raise ValueError("benchmark result missing: " + ",".join(missing))
        with self._write():
            campaign = self._connection.execute("SELECT 1 FROM campaign WHERE tenant_id=? AND campaign_id=?", (tenant_id, campaign_id)).fetchone()
            if campaign is None:
                raise NotFoundError("campaign not found")
            self._connection.execute("INSERT INTO benchmark_run(run_id,campaign_id,tenant_id,system,system_version,repo_revision,task_case,repetition,validated_success,evidence_level,result_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (require_uuid(result["run_id"], "run_id"), campaign_id, tenant_id, require_nonempty(result["system"], "system", 256), result.get("system_version"), require_nonempty(result["repo_revision"], "repo_revision", 256), require_nonempty(result["task_case"], "task_case", 512), int(result["repetition"]), None if result.get("validated_success") is None else int(bool(result["validated_success"])), require_nonempty(result["evidence_level"], "evidence_level", 32), self._json(dict(result)), utc_now()))
            return dict(result)


def digest_bytes(content: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(content).hexdigest()
