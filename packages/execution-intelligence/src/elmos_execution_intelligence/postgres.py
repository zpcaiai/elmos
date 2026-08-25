"""PostgreSQL-backed durable store, running against ``sql/001_execution_intelligence.sql``.

The SQLite store in :mod:`durable` is the portable reference. This one talks to
the production schema unchanged -- same enums, same ``append_run_event``
function, same content-addressed artifact constraints -- so the claim "the
contract is portable" is something a test can settle rather than something a
README asserts.

It takes a DB-API 2.0 connection factory rather than importing a driver, so the
package keeps its zero-dependency default. Install ``psycopg``, ``psycopg2`` or
``pg8000`` yourself and hand the connection in.

Timestamps: the schema stores ``TIMESTAMPTZ``; the store's logical clock is a
float. Conversion happens in SQL (``to_timestamp`` / ``EXTRACT(EPOCH ...)``)
rather than in Python, so the rows a human reads in psql are real timestamps and
the deterministic tests still work.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Any, Literal

from .durable import Conflict, LogicalClock, StoreUnavailable, _digest
from .io_utils import quantile

SEARCH_PATH = "SET search_path TO execution_intelligence, public"


class PostgresStore:
    """Same method contract as :class:`durable.DurableStore`, backed by PostgreSQL."""

    def __init__(self, connect: Callable[[], Any], clock: Callable[[], float] | None = None,
                 tenant_id: str = "default") -> None:
        self.clock = clock or LogicalClock()
        self.tenant_id = tenant_id
        try:
            self.connection = connect()
        except Exception as exc:  # pragma: no cover - driver-specific
            raise StoreUnavailable(f"cannot connect to PostgreSQL: {exc}") from exc
        self.connection.autocommit = False
        with self._cursor() as cursor:
            cursor.execute(SEARCH_PATH)
        self._ensure_tenant(tenant_id)

    # ------------------------------------------------------------------ plumbing --

    class _CursorContext:
        """Commit on clean exit, roll back on any exception. Never leaks a cursor."""

        def __init__(self, store: PostgresStore) -> None:
            self.store = store
            self.cursor: Any = None

        def __enter__(self) -> Any:
            self.cursor = self.store.connection.cursor()
            return self.cursor

        def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
            if exc_type is None:
                self.store.connection.commit()
            else:
                self.store.connection.rollback()
            if self.cursor is not None:
                self.cursor.close()
            return False

    def _cursor(self) -> PostgresStore._CursorContext:
        return PostgresStore._CursorContext(self)

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows: list[tuple[Any, ...]] = cursor.fetchall()
            return rows

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
        rows = self._fetchall(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        self.connection.close()

    def _ensure_tenant(self, tenant_id: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO tenant (tenant_id, display_name) VALUES (%s, %s)"
                " ON CONFLICT (tenant_id) DO NOTHING",
                (tenant_id, tenant_id))

    # ---------------------------------------------------------------------- runs --

    def create_run(self, project: dict[str, Any], task_document: dict[str, Any],
                   tenant_id: str | None = None, run_id: str | None = None) -> str:
        tenant_id = tenant_id or self.tenant_id
        self._ensure_tenant(tenant_id)
        run_id = run_id or str(uuid.uuid4())
        now = self.clock()
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO run (run_id, tenant_id, project_id, dag_id, state, definition_of_done,"
                " created_at) VALUES (%s::uuid, %s, %s, %s, 'pending', %s::jsonb, to_timestamp(%s))",
                (run_id, tenant_id, project["project_id"], task_document.get("dag_id", "dag"),
                 json.dumps(project["definition_of_done"], ensure_ascii=False), now))
            for task in task_document["tasks"]:
                cursor.execute(
                    "INSERT INTO task (run_id, task_id, tenant_id, name, category, complexity,"
                    " depends_on, worker_units, state, estimate, created_at, updated_at)"
                    " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, 'pending', %s::jsonb,"
                    " to_timestamp(%s), to_timestamp(%s))",
                    (run_id, task["id"], tenant_id, task.get("name", task["id"]),
                     task.get("category"), task.get("complexity"),
                     list(task.get("depends_on", [])),
                     float(task.get("system", {}).get("worker_units", 1.0)),
                     json.dumps(task.get("system", {}), ensure_ascii=False), now, now))
        self.append_event(run_id, "run.created", None, {"project_id": project["project_id"]})
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self._fetchone(
            "SELECT run_id::text, tenant_id, project_id, dag_id, state::text,"
            " EXTRACT(EPOCH FROM created_at)::float8, EXTRACT(EPOCH FROM started_at)::float8,"
            " EXTRACT(EPOCH FROM finished_at)::float8, last_event_seq"
            " FROM run WHERE run_id = %s::uuid", (run_id,))
        if row is None:
            raise ValueError(f"unknown run {run_id}")
        keys = ("run_id", "tenant_id", "project_id", "dag_id", "state",
                "created_at", "started_at", "finished_at", "last_event_seq")
        return dict(zip(keys, row, strict=True))

    def set_run_state(self, run_id: str, state: str) -> None:
        now = self.clock()
        with self._cursor() as cursor:
            if state == "running":
                cursor.execute(
                    "UPDATE run SET state = %s::run_state,"
                    " started_at = COALESCE(started_at, to_timestamp(%s)) WHERE run_id = %s::uuid",
                    (state, now, run_id))
            elif state in {"succeeded", "failed", "cancelled"}:
                cursor.execute(
                    "UPDATE run SET state = %s::run_state, finished_at = to_timestamp(%s)"
                    " WHERE run_id = %s::uuid", (state, now, run_id))
            else:
                cursor.execute("UPDATE run SET state = %s::run_state WHERE run_id = %s::uuid",
                               (state, run_id))
        self.append_event(run_id, "run.state_changed", None, {"state": state})

    # --------------------------------------------------------------------- tasks --

    def tasks(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT task_id, name, category, complexity, depends_on, worker_units, state::text,"
            " attempt_count, estimate::text, NULL::text FROM task WHERE run_id = %s::uuid"
            " ORDER BY task_id", (run_id,))
        result = []
        for row in rows:
            result.append({
                "run_id": run_id,
                "task_id": row[0], "name": row[1], "category": row[2], "complexity": row[3],
                "depends_on": list(row[4] or []), "worker_units": float(row[5]),
                "state": row[6], "attempt_count": int(row[7]),
                "estimate": json.loads(row[8]), "last_failure_class": row[9],
            })
        return result

    def set_task_state(self, run_id: str, task_id: str, state: str,
                       failure_class: str | None = None) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE task SET state = %s::task_state, updated_at = to_timestamp(%s)"
                " WHERE run_id = %s::uuid AND task_id = %s",
                (state, self.clock(), run_id, task_id))

    # ------------------------------------------------------------------ attempts --

    def start_attempt(self, run_id: str, task_id: str, worker_id: str) -> dict[str, Any]:
        now = self.clock()
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT attempt_count FROM task WHERE run_id = %s::uuid AND task_id = %s FOR UPDATE",
                (run_id, task_id))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"unknown task {task_id} in run {run_id}")
            attempt_number = int(row[0]) + 1
            attempt_id = str(uuid.uuid4())
            cursor.execute(
                "INSERT INTO task_attempt (attempt_id, run_id, task_id, tenant_id, attempt_number,"
                " worker_id, started_at, heartbeat_at)"
                " VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s))",
                (attempt_id, run_id, task_id, self.tenant_id, attempt_number, worker_id, now, now))
            cursor.execute(
                "UPDATE task SET attempt_count = %s, state = 'running' WHERE run_id = %s::uuid"
                " AND task_id = %s", (attempt_number, run_id, task_id))
        self.append_event(run_id, "task.started", task_id,
                          {"attempt": attempt_number, "worker_id": worker_id})
        return {"attempt_id": attempt_id, "attempt_number": attempt_number}

    def heartbeat(self, attempt_id: str) -> None:
        with self._cursor() as cursor:
            cursor.execute("UPDATE task_attempt SET heartbeat_at = to_timestamp(%s)"
                           " WHERE attempt_id = %s::uuid", (self.clock(), attempt_id))

    def finish_attempt(self, attempt_id: str, outcome: str, failure_class: str | None = None,
                       execution_ms: int | None = None, recovery_ms: int | None = None) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE task_attempt SET outcome = %s::attempt_outcome, failure_class = %s,"
                " finished_at = to_timestamp(%s), execution_ms = %s, recovery_ms = %s"
                " WHERE attempt_id = %s::uuid",
                (outcome, failure_class, self.clock(), execution_ms, recovery_ms, attempt_id))

    def open_attempts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT attempt_id::text, task_id, attempt_number,"
            " EXTRACT(EPOCH FROM heartbeat_at)::float8"
            " FROM task_attempt WHERE run_id = %s::uuid AND finished_at IS NULL", (run_id,))
        return [
            {"attempt_id": row[0], "task_id": row[1], "attempt_number": int(row[2]),
             "heartbeat_at": float(row[3])}
            for row in rows
        ]

    def sweep_lost_attempts(self, run_id: str, heartbeat_timeout_seconds: float) -> list[dict[str, Any]]:
        cutoff = self.clock() - float(heartbeat_timeout_seconds)
        lost = []
        for attempt in self.open_attempts(run_id):
            if attempt["heartbeat_at"] < cutoff:
                self.finish_attempt(attempt["attempt_id"], "lost", "lost_worker")
                self.set_task_state(run_id, attempt["task_id"], "ready", "lost_worker")
                self.append_event(run_id, "task.recovered", attempt["task_id"],
                                  {"reason": "heartbeat_timeout", "attempt": attempt["attempt_number"]})
                lost.append(attempt)
        return lost

    # --------------------------------------------------------------- checkpoints --

    def record_checkpoint(self, run_id: str, task_id: str | None, kind: str,
                          git_commit: str | None = None, workspace_uri: str | None = None,
                          workspace_digest: str | None = None,
                          state_blob: dict[str, Any] | None = None) -> str:
        checkpoint_id = str(uuid.uuid4())
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO checkpoint (checkpoint_id, run_id, task_id, tenant_id, kind, git_commit,"
                " workspace_uri, workspace_digest, state_blob, created_at)"
                " VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, to_timestamp(%s))",
                (checkpoint_id, run_id, task_id, self.tenant_id, kind, git_commit, workspace_uri,
                 workspace_digest,
                 json.dumps(state_blob, ensure_ascii=False) if state_blob is not None else None,
                 self.clock()))
        self.append_event(run_id, "task.checkpointed", task_id,
                          {"checkpoint_id": checkpoint_id, "kind": kind, "git_commit": git_commit})
        return checkpoint_id

    def checkpoints(self, run_id: str, task_id: str | None = None) -> list[dict[str, Any]]:
        if task_id is None:
            rows = self._fetchall(
                "SELECT checkpoint_id::text, task_id, kind, git_commit,"
                " EXTRACT(EPOCH FROM created_at)::float8 FROM checkpoint"
                " WHERE run_id = %s::uuid ORDER BY created_at DESC", (run_id,))
        else:
            rows = self._fetchall(
                "SELECT checkpoint_id::text, task_id, kind, git_commit,"
                " EXTRACT(EPOCH FROM created_at)::float8 FROM checkpoint"
                " WHERE run_id = %s::uuid AND task_id = %s ORDER BY created_at DESC",
                (run_id, task_id))
        return [
            {"checkpoint_id": row[0], "task_id": row[1], "kind": row[2], "git_commit": row[3],
             "created_at": float(row[4])}
            for row in rows
        ]

    def has_commit(self, run_id: str, git_commit: str) -> bool:
        return self._fetchone(
            "SELECT 1 FROM checkpoint WHERE run_id = %s::uuid AND git_commit = %s LIMIT 1",
            (run_id, git_commit)) is not None

    # -------------------------------------------------------------------- events --

    def append_event(self, run_id: str, event_type: str, task_id: str | None,
                     payload: dict[str, Any]) -> int:
        """Delegates to the production ``append_run_event`` function.

        Sequence allocation therefore happens exactly where the schema says it
        does -- under the run row lock -- rather than in a Python re-implementation
        that could drift from it.
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT append_run_event(%s::uuid, %s, %s, %s, %s::jsonb)",
                (run_id, self.tenant_id, event_type, task_id,
                 json.dumps(payload, ensure_ascii=False)))
            row = cursor.fetchone()
        return int(row[0])

    def events_since(self, run_id: str, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT seq, event_type, task_id, payload::text,"
            " EXTRACT(EPOCH FROM created_at)::float8 FROM run_event"
            " WHERE run_id = %s::uuid AND seq > %s ORDER BY seq LIMIT %s",
            (run_id, int(after_seq), int(limit)))
        return [
            {"run_id": run_id, "seq": int(row[0]), "event_type": row[1], "task_id": row[2],
             "payload": json.loads(row[3]), "created_at": float(row[4])}
            for row in rows
        ]

    def sse_frames(self, run_id: str, last_event_id: int = 0, limit: int = 500) -> str:
        frames = []
        for event in self.events_since(run_id, last_event_id, limit):
            frames.append(
                "id: {seq}\nevent: {type}\ndata: {data}\n".format(
                    seq=event["seq"], type=event["event_type"],
                    data=json.dumps({
                        "seq": event["seq"], "runId": event["run_id"], "taskId": event["task_id"],
                        "eventType": event["event_type"], "payload": event["payload"],
                    }, ensure_ascii=False)))
        return "\n".join(frames)

    # --------------------------------------------------------------- idempotency --

    def begin_idempotent(self, scope: str, key: str, request: Any) -> tuple[str, Any]:
        digest = _digest(request)
        row = self._fetchone(
            "SELECT request_digest, state, response::text FROM idempotency_key"
            " WHERE tenant_id = %s AND scope = %s AND key = %s", (self.tenant_id, scope, key))
        if row is not None:
            if row[0] != digest:
                raise Conflict(
                    f"idempotency key '{key}' in scope '{scope}' was reused with a different request body")
            if row[1] == "completed":
                return "replayed", json.loads(row[2]) if row[2] else None
            return "in_flight", None
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO idempotency_key (tenant_id, scope, key, request_digest, state, created_at)"
                " VALUES (%s, %s, %s, %s, 'in_flight', to_timestamp(%s))",
                (self.tenant_id, scope, key, digest, self.clock()))
        return "claimed", None

    def complete_idempotent(self, scope: str, key: str, response: Any) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "UPDATE idempotency_key SET state = 'completed', response = %s::jsonb,"
                " completed_at = to_timestamp(%s) WHERE tenant_id = %s AND scope = %s AND key = %s",
                (json.dumps(response, ensure_ascii=False), self.clock(), self.tenant_id, scope, key))

    def fail_idempotent(self, scope: str, key: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM idempotency_key WHERE tenant_id = %s AND scope = %s AND key = %s"
                " AND state = 'in_flight'", (self.tenant_id, scope, key))

    # -------------------------------------------------------------------- outbox --

    def enqueue_outbox(self, run_id: str | None, topic: str, payload: dict[str, Any]) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO outbox (tenant_id, run_id, topic, payload, created_at)"
                " VALUES (%s, %s::uuid, %s, %s::jsonb, to_timestamp(%s)) RETURNING outbox_id",
                (self.tenant_id, run_id, topic, json.dumps(payload, ensure_ascii=False), self.clock()))
            row = cursor.fetchone()
        if row is None:  # pragma: no cover - RETURNING always yields a row
            raise StoreUnavailable("outbox insert returned no row id")
        return int(row[0])

    def unpublished_outbox(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT outbox_id, run_id::text, topic, payload::text FROM outbox"
            " WHERE published_at IS NULL AND tenant_id = %s ORDER BY outbox_id", (self.tenant_id,))
        return [
            {"outbox_id": int(row[0]), "run_id": row[1], "topic": row[2], "payload": json.loads(row[3])}
            for row in rows
        ]

    def mark_published(self, outbox_id: int) -> None:
        with self._cursor() as cursor:
            cursor.execute("UPDATE outbox SET published_at = to_timestamp(%s) WHERE outbox_id = %s",
                           (self.clock(), outbox_id))

    # ----------------------------------------------------------------- artifacts --

    def publish_artifact(self, run_id: str, logical_name: str, content: bytes,
                         media_type: str = "application/octet-stream",
                         storage_uri: str | None = None, git_ref: str | None = None) -> dict[str, Any]:
        sha256 = hashlib.sha256(content).hexdigest()
        existing = self._fetchone(
            "SELECT artifact_id::text, version, media_type, size_bytes, storage_uri, git_ref"
            " FROM artifact WHERE run_id = %s::uuid AND logical_name = %s AND sha256 = %s",
            (run_id, logical_name, sha256))
        if existing is not None:
            return {
                "artifact_id": existing[0], "run_id": run_id, "logical_name": logical_name,
                "version": int(existing[1]), "media_type": existing[2],
                "size_bytes": int(existing[3]), "sha256": sha256,
                "storage_uri": existing[4], "git_ref": existing[5], "deduplicated": True,
            }
        row = self._fetchone(
            "SELECT COALESCE(MAX(version), 0) FROM artifact WHERE run_id = %s::uuid AND logical_name = %s",
            (run_id, logical_name))
        version = (int(row[0]) if row else 0) + 1
        artifact_id = str(uuid.uuid4())
        uri = storage_uri or f"artifact://{run_id}/{logical_name}/{version}"
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO artifact (artifact_id, tenant_id, run_id, logical_name, version,"
                " media_type, size_bytes, sha256, storage_uri, git_ref, created_at)"
                " VALUES (%s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s))",
                (artifact_id, self.tenant_id, run_id, logical_name, version, media_type,
                 len(content), sha256, uri, git_ref, self.clock()))
        self.append_event(run_id, "artifact.published", None,
                          {"logical_name": logical_name, "version": version, "sha256": sha256})
        return {
            "artifact_id": artifact_id, "run_id": run_id, "logical_name": logical_name,
            "version": version, "media_type": media_type, "size_bytes": len(content),
            "sha256": sha256, "storage_uri": uri, "git_ref": git_ref, "deduplicated": False,
        }

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT artifact_id::text, logical_name, version, media_type, size_bytes, sha256,"
            " storage_uri, git_ref FROM artifact WHERE run_id = %s::uuid"
            " ORDER BY logical_name, version", (run_id,))
        return [
            {"artifact_id": row[0], "run_id": run_id, "logical_name": row[1], "version": int(row[2]),
             "media_type": row[3], "size_bytes": int(row[4]), "sha256": row[5],
             "storage_uri": row[6], "git_ref": row[7]}
            for row in rows
        ]

    def has_artifact(self, run_id: str, logical_name: str, sha256: str) -> bool:
        return self._fetchone(
            "SELECT 1 FROM artifact WHERE run_id = %s::uuid AND logical_name = %s AND sha256 = %s"
            " LIMIT 1", (run_id, logical_name, sha256)) is not None

    # ----------------------------------------------------------------- telemetry --

    def record_usage(self, run_id: str, task_id: str, attempt: int, model: str,
                     tokens: dict[str, int], execution_ms: int | None, status: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT INTO model_usage (usage_id, tenant_id, run_id, task_id, attempt, model,"
                " input_tokens, cached_input_tokens, cache_write_tokens, output_tokens,"
                " reasoning_tokens, execution_ms, status, recorded_at)"
                " VALUES (%s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                " to_timestamp(%s))",
                (str(uuid.uuid4()), self.tenant_id, run_id, task_id, attempt, model,
                 int(tokens.get("input", 0)), int(tokens.get("cached_input", 0)),
                 int(tokens.get("cache_write", 0)), int(tokens.get("output", 0)),
                 int(tokens.get("reasoning_output", 0)), execution_ms, status, self.clock()))
        self.append_event(run_id, "usage.recorded", task_id,
                          {"attempt": attempt, "model": model, "tokens": tokens})

    def calibration_rows(self, run_id: str) -> list[dict[str, Any]]:
        rows = []
        for task in self.tasks(run_id):
            if task["state"] != "succeeded":
                continue
            usage = self._fetchone(
                "SELECT SUM(input_tokens + cached_input_tokens + cache_write_tokens + output_tokens"
                " + reasoning_tokens), SUM(execution_ms), MAX(model) FROM model_usage"
                " WHERE run_id = %s::uuid AND task_id = %s", (run_id, task["task_id"]))
            if usage is None or usage[0] is None:
                continue
            profile = task["estimate"].get("token_profile", {})
            estimated_tokens = sum(
                float(profile.get(field, 0))
                for field in ("input", "cached_input", "cache_write", "output", "reasoning_output"))
            if estimated_tokens <= 0:
                continue
            rows.append({
                "task_id": task["task_id"],
                "task_type": task["category"] or "unknown",
                "complexity": task["complexity"] or "unknown",
                "model": usage[2] or "unknown",
                "estimated_minutes": float(task["estimate"].get("most_likely_minutes", 0)),
                "actual_minutes": round(float(usage[1] or 0) / 60000.0, 6),
                "estimated_total_tokens": estimated_tokens,
                "actual_total_tokens": float(usage[0]),
            })
        return rows


def recovery_aware_eta(store: Any, run_id: str, capacity: float = 4.0) -> dict[str, Any]:
    """ETA over a PostgresStore. Mirrors :func:`durable.recovery_aware_eta`."""
    tasks = store.tasks(run_id)
    completed = [task for task in tasks if task["state"] == "succeeded"]
    remaining = [task for task in tasks
                 if task["state"] not in {"succeeded", "failed", "skipped", "cancelled"}]

    observed_ratios: list[float] = []
    recovery_ms_total = 0
    for task in completed:
        row = store._fetchone(
            "SELECT SUM(execution_ms), SUM(COALESCE(recovery_ms, 0)) FROM task_attempt"
            " WHERE run_id = %s::uuid AND task_id = %s", (run_id, task["task_id"]))
        if not row or row[0] is None:
            continue
        recovery_ms_total += int(row[1] or 0)
        estimated = float(task["estimate"].get("most_likely_minutes", 0))
        actual = float(row[0]) / 60000.0
        if estimated > 0 and actual > 0:
            observed_ratios.append(actual / estimated)

    multiplier = quantile(observed_ratios, 0.5) if observed_ratios else 1.0
    basis = "forecast_only"
    if len(observed_ratios) >= 5:
        basis = "telemetry_dominant"
    elif observed_ratios:
        basis = "forecast_plus_telemetry"

    remaining_worker_minutes = sum(
        float(task["estimate"].get("most_likely_minutes", 0)) * float(task["worker_units"])
        for task in remaining)
    parallel_minutes = remaining_worker_minutes * multiplier / max(capacity, 1e-9)
    total = len(tasks)
    return {
        "schema_version": "1.0.0",
        "artifact": "recovery-eta-update",
        "run_id": run_id,
        "completed_fraction": round(len(completed) / total, 4) if total else 0.0,
        "observed_runtime_multiplier": round(multiplier, 4),
        "observed_samples": len(observed_ratios),
        "basis": basis,
        "remaining_tasks": len(remaining),
        "remaining_serial_minutes": round(
            sum(float(t["estimate"].get("most_likely_minutes", 0)) for t in remaining), 2),
        "wall_clock_hours": {
            "p50": round(parallel_minutes / 60.0, 3),
            "p80": round(parallel_minutes * 1.25 / 60.0, 3),
            "p90": round(parallel_minutes * 1.45 / 60.0, 3),
            "worst_case": round(parallel_minutes * 2.0 / 60.0, 3),
        },
        "recovery_hours_included": round(recovery_ms_total / 3_600_000.0, 4),
        "excludes": [
            "human approvals",
            "human acceptance and review effort",
            "credential and access provisioning waits",
            "external business or vendor decisions",
        ],
        "note": "Same definition as the SQLite reference implementation.",
    }
