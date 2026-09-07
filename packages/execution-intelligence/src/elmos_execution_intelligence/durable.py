"""Skills 08-12 — durable orchestration, checkpoints, idempotency, event replay, recovery ETA.

This is a reference implementation on SQLite, not a production deployment. It
exists so the properties the contract claims can actually be asserted:

* killing a worker mid-task does not lose the run (08)
* restarting the orchestrator resumes from persisted state, not from zero (09)
* replaying a request returns the original response and performs no second
  side effect (10)
* a client reconnecting with a last-seen sequence is replayed exactly what it
  missed, with no gaps and no duplicates (11)
* the ETA is recomputed from executed telemetry and still excludes human waits (12)

``sql/001_execution_intelligence.sql`` is the production target and mirrors these
semantics. Swapping SQLite for PostgreSQL changes the storage, not the assertions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .io_utils import quantile

TERMINAL_RUN_STATES = frozenset({"succeeded", "failed", "cancelled"})
TERMINAL_TASK_STATES = frozenset({"succeeded", "failed", "skipped", "cancelled"})

#: How a failure class decides what happens next. Retry policy is chosen by
#: class, never by matching exception text -- text matching breaks silently the
#: day a dependency rewords its errors.
RETRY_POLICY = {
    "transient": {"retry": True, "max_attempts": 4, "backoff_base_seconds": 5, "backoff_factor": 3.0},
    "lost_worker": {"retry": True, "max_attempts": 3, "backoff_base_seconds": 2, "backoff_factor": 2.0},
    "permanent": {"retry": False, "max_attempts": 1, "backoff_base_seconds": 0, "backoff_factor": 1.0},
    "business_conflict": {"retry": False, "max_attempts": 1, "backoff_base_seconds": 0, "backoff_factor": 1.0},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    dag_id TEXT NOT NULL,
    state TEXT NOT NULL,
    definition_of_done TEXT NOT NULL,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    last_event_seq INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS task (
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    complexity TEXT,
    depends_on TEXT NOT NULL,
    worker_units REAL NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    estimate TEXT NOT NULL,
    last_failure_class TEXT,
    PRIMARY KEY (run_id, task_id)
);
CREATE TABLE IF NOT EXISTS task_attempt (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    outcome TEXT,
    failure_class TEXT,
    started_at REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    finished_at REAL,
    execution_ms INTEGER,
    recovery_ms INTEGER,
    UNIQUE (run_id, task_id, attempt_number)
);
CREATE TABLE IF NOT EXISTS checkpoint (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT,
    kind TEXT NOT NULL,
    git_commit TEXT,
    workspace_uri TEXT,
    workspace_digest TEXT,
    state_blob TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS run_event (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    task_id TEXT,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS idempotency_key (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    response TEXT,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    completed_at REAL,
    PRIMARY KEY (scope, key)
);
CREATE TABLE IF NOT EXISTS outbox (
    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    published_at REAL
);
CREATE TABLE IF NOT EXISTS artifact (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    logical_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    git_ref TEXT,
    created_at REAL NOT NULL,
    UNIQUE (run_id, logical_name, version),
    UNIQUE (run_id, logical_name, sha256)
);
CREATE TABLE IF NOT EXISTS model_usage (
    usage_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    execution_ms INTEGER,
    status TEXT NOT NULL,
    recorded_at REAL NOT NULL
);
"""


class StoreUnavailable(RuntimeError):
    """The durable store could not be opened -- almost always a filesystem that cannot lock."""


class Conflict(ValueError):
    """An idempotency key was reused with a different request body."""


class LogicalClock:
    """Deterministic clock. Tests must not depend on wall-clock timing."""

    def __init__(self, start: float = 0.0, step: float = 1.0) -> None:
        self.now = float(start)
        self.step = float(step)

    def __call__(self) -> float:
        self.now += self.step
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class DurableStore:
    """Persistence for runs, tasks, attempts, checkpoints, events and side-effect guards."""

    def __init__(self, path: str = ":memory:", clock: Callable[[], float] | None = None,
                 allow_cross_thread: bool = False) -> None:
        self.path = path
        # Typed as the concrete clock: chaos scenarios need `advance()`, and a
        # bare Callable would hide that from the type checker.
        self.clock: Any = clock or LogicalClock()
        # sqlite3 binds a connection to its creating thread. The reference HTTP
        # server serves requests from its own thread, so it needs this off -- and
        # it is off by default everywhere else, because the check catches real
        # concurrency bugs.
        self.allow_cross_thread = allow_cross_thread
        try:
            self.connection = sqlite3.connect(path, check_same_thread=not allow_cross_thread)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.executescript(SCHEMA)
            self.connection.commit()
        except sqlite3.OperationalError as exc:
            # SQLite needs POSIX byte-range locking. Network and FUSE mounts
            # (including the desktop-bridge mount elmos is often edited through)
            # do not provide it, and the failure surfaces as a bare
            # "disk I/O error" that says nothing about the cause.
            raise StoreUnavailable(
                f"cannot open the durable store at '{path}': {exc}. "
                "SQLite requires real file locking; put the store on local disk "
                "(for example /tmp/elmos-run.db) rather than on a network or FUSE mount, "
                "or use ':memory:' for a throwaway run."
            ) from exc

    def close(self) -> None:
        self.connection.close()

    # ------------------------------------------------------------------ runs --

    def create_run(self, project: dict[str, Any], task_document: dict[str, Any],
                   tenant_id: str = "default", run_id: str | None = None) -> str:
        run_id = run_id or str(uuid.uuid4())
        now = self.clock()
        with self.connection:
            self.connection.execute(
                "INSERT INTO run (run_id, tenant_id, project_id, dag_id, state, definition_of_done, created_at)"
                " VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (run_id, tenant_id, project["project_id"], task_document.get("dag_id", "dag"),
                 json.dumps(project["definition_of_done"], ensure_ascii=False), now),
            )
            for task in task_document["tasks"]:
                self.connection.execute(
                    "INSERT INTO task (run_id, task_id, name, category, complexity, depends_on,"
                    " worker_units, state, estimate) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (run_id, task["id"], task.get("name", task["id"]), task.get("category"),
                     task.get("complexity"), json.dumps(task.get("depends_on", [])),
                     float(task.get("system", {}).get("worker_units", 1.0)),
                     json.dumps(task.get("system", {}), ensure_ascii=False)),
                )
        self.append_event(run_id, "run.created", None, {"project_id": project["project_id"]})
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM run WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"unknown run {run_id}")
        return dict(row)

    def set_run_state(self, run_id: str, state: str) -> None:
        now = self.clock()
        with self.connection:
            if state == "running":
                self.connection.execute(
                    "UPDATE run SET state = ?, started_at = COALESCE(started_at, ?) WHERE run_id = ?",
                    (state, now, run_id))
            elif state in TERMINAL_RUN_STATES:
                self.connection.execute(
                    "UPDATE run SET state = ?, finished_at = ? WHERE run_id = ?", (state, now, run_id))
            else:
                self.connection.execute("UPDATE run SET state = ? WHERE run_id = ?", (state, run_id))
        self.append_event(run_id, "run.state_changed", None, {"state": state})

    # ----------------------------------------------------------------- tasks --

    def tasks(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM task WHERE run_id = ? ORDER BY task_id", (run_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["depends_on"] = json.loads(item["depends_on"])
            item["estimate"] = json.loads(item["estimate"])
            result.append(item)
        return result

    def set_task_state(self, run_id: str, task_id: str, state: str,
                       failure_class: str | None = None) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE task SET state = ?, last_failure_class = COALESCE(?, last_failure_class)"
                " WHERE run_id = ? AND task_id = ?",
                (state, failure_class, run_id, task_id))

    # -------------------------------------------------------------- attempts --

    def start_attempt(self, run_id: str, task_id: str, worker_id: str) -> dict[str, Any]:
        now = self.clock()
        with self.connection:
            row = self.connection.execute(
                "SELECT attempt_count FROM task WHERE run_id = ? AND task_id = ?",
                (run_id, task_id)).fetchone()
            if row is None:
                raise ValueError(f"unknown task {task_id} in run {run_id}")
            attempt_number = int(row["attempt_count"]) + 1
            attempt_id = str(uuid.uuid4())
            self.connection.execute(
                "INSERT INTO task_attempt (attempt_id, run_id, task_id, attempt_number, worker_id,"
                " started_at, heartbeat_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, run_id, task_id, attempt_number, worker_id, now, now))
            self.connection.execute(
                "UPDATE task SET attempt_count = ?, state = 'running' WHERE run_id = ? AND task_id = ?",
                (attempt_number, run_id, task_id))
        self.append_event(run_id, "task.started", task_id,
                          {"attempt": attempt_number, "worker_id": worker_id})
        return {"attempt_id": attempt_id, "attempt_number": attempt_number}

    def heartbeat(self, attempt_id: str) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE task_attempt SET heartbeat_at = ? WHERE attempt_id = ?",
                (self.clock(), attempt_id))

    def finish_attempt(self, attempt_id: str, outcome: str, failure_class: str | None = None,
                       execution_ms: int | None = None, recovery_ms: int | None = None) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE task_attempt SET outcome = ?, failure_class = ?, finished_at = ?,"
                " execution_ms = ?, recovery_ms = ? WHERE attempt_id = ?",
                (outcome, failure_class, self.clock(), execution_ms, recovery_ms, attempt_id))

    def open_attempts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM task_attempt WHERE run_id = ? AND finished_at IS NULL", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def sweep_lost_attempts(self, run_id: str, heartbeat_timeout_seconds: float) -> list[dict[str, Any]]:
        """Mark attempts whose worker stopped reporting as `lost`, not as failed.

        A silent worker has no verdict: it may have committed, published, or even
        finished without writing back. Recording it as `permanent` loses work;
        recording it as `transient` and retrying blindly duplicates side effects.
        `lost` sends it through the four-step reconciliation instead.
        """
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

    # ------------------------------------------------------------ checkpoints --

    def record_checkpoint(self, run_id: str, task_id: str | None, kind: str,
                          git_commit: str | None = None, workspace_uri: str | None = None,
                          workspace_digest: str | None = None,
                          state_blob: dict[str, Any] | None = None) -> str:
        checkpoint_id = str(uuid.uuid4())
        with self.connection:
            self.connection.execute(
                "INSERT INTO checkpoint (checkpoint_id, run_id, task_id, kind, git_commit,"
                " workspace_uri, workspace_digest, state_blob, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (checkpoint_id, run_id, task_id, kind, git_commit, workspace_uri, workspace_digest,
                 json.dumps(state_blob, ensure_ascii=False) if state_blob is not None else None,
                 self.clock()))
        self.append_event(run_id, "task.checkpointed", task_id,
                          {"checkpoint_id": checkpoint_id, "kind": kind, "git_commit": git_commit})
        return checkpoint_id

    def checkpoints(self, run_id: str, task_id: str | None = None) -> list[dict[str, Any]]:
        if task_id is None:
            rows = self.connection.execute(
                "SELECT * FROM checkpoint WHERE run_id = ? ORDER BY created_at DESC", (run_id,)).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM checkpoint WHERE run_id = ? AND task_id = ? ORDER BY created_at DESC",
                (run_id, task_id)).fetchall()
        return [dict(row) for row in rows]

    def has_commit(self, run_id: str, git_commit: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM checkpoint WHERE run_id = ? AND git_commit = ? LIMIT 1",
            (run_id, git_commit)).fetchone()
        return row is not None

    # ---------------------------------------------------------------- events --

    def append_event(self, run_id: str, event_type: str, task_id: str | None,
                     payload: dict[str, Any]) -> int:
        """Allocate the next sequence and write the event in one transaction.

        The UPDATE takes the run row's write lock, so two writers cannot mint the
        same seq and no hole can appear between allocation and insert.
        """
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE run SET last_event_seq = last_event_seq + 1 WHERE run_id = ?", (run_id,))
            if cursor.rowcount == 0:
                raise ValueError(f"unknown run {run_id}")
            seq = int(self.connection.execute(
                "SELECT last_event_seq FROM run WHERE run_id = ?", (run_id,)).fetchone()[0])
            self.connection.execute(
                "INSERT INTO run_event (run_id, seq, event_type, task_id, payload, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, seq, event_type, task_id, json.dumps(payload, ensure_ascii=False), self.clock()))
        return seq

    def events_since(self, run_id: str, after_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM run_event WHERE run_id = ? AND seq > ? ORDER BY seq LIMIT ?",
            (run_id, int(after_seq), int(limit))).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            events.append(item)
        return events

    def sse_frames(self, run_id: str, last_event_id: int = 0, limit: int = 500) -> str:
        """Render events as SSE frames whose `id:` is the run-scoped seq."""
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

    # ----------------------------------------------------------- idempotency --

    def begin_idempotent(self, scope: str, key: str, request: Any) -> tuple[str, Any]:
        """Claim an idempotency key.

        Returns ``("claimed", None)`` when the caller should perform the effect,
        ``("replayed", response)`` when the effect already completed, and
        ``("in_flight", None)`` when another caller holds the key. A key reused
        with a different request body raises Conflict -- serving the old response
        to a different request is worse than failing.
        """
        digest = _digest(request)
        row = self.connection.execute(
            "SELECT * FROM idempotency_key WHERE scope = ? AND key = ?", (scope, key)).fetchone()
        if row is not None:
            if row["request_digest"] != digest:
                raise Conflict(
                    f"idempotency key '{key}' in scope '{scope}' was reused with a different request body")
            if row["state"] == "completed":
                return "replayed", json.loads(row["response"]) if row["response"] else None
            return "in_flight", None
        with self.connection:
            self.connection.execute(
                "INSERT INTO idempotency_key (scope, key, request_digest, state, created_at)"
                " VALUES (?, ?, ?, 'in_flight', ?)",
                (scope, key, digest, self.clock()))
        return "claimed", None

    def complete_idempotent(self, scope: str, key: str, response: Any) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE idempotency_key SET state = 'completed', response = ?, completed_at = ?"
                " WHERE scope = ? AND key = ?",
                (json.dumps(response, ensure_ascii=False), self.clock(), scope, key))

    def fail_idempotent(self, scope: str, key: str) -> None:
        """Release a claimed key so a later attempt can retry the effect."""
        with self.connection:
            self.connection.execute(
                "DELETE FROM idempotency_key WHERE scope = ? AND key = ? AND state = 'in_flight'",
                (scope, key))

    # ---------------------------------------------------------------- outbox --

    def enqueue_outbox(self, run_id: str | None, topic: str, payload: dict[str, Any]) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO outbox (run_id, topic, payload, created_at) VALUES (?, ?, ?, ?)",
                (run_id, topic, json.dumps(payload, ensure_ascii=False), self.clock()))
        # sqlite3 types lastrowid as Optional; after a successful INSERT it is not.
        if cursor.lastrowid is None:  # pragma: no cover - sqlite always sets it here
            raise StoreUnavailable("outbox insert returned no row id")
        return int(cursor.lastrowid)

    def unpublished_outbox(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM outbox WHERE published_at IS NULL ORDER BY outbox_id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def mark_published(self, outbox_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE outbox SET published_at = ? WHERE outbox_id = ?", (self.clock(), outbox_id))

    # -------------------------------------------------------------- artifacts --

    def publish_artifact(self, run_id: str, logical_name: str, content: bytes,
                         media_type: str = "application/octet-stream",
                         storage_uri: str | None = None, git_ref: str | None = None) -> dict[str, Any]:
        """Content-addressed publication.

        Republishing identical bytes returns the existing row unchanged.
        Different bytes under the same logical name take the next version; they
        never overwrite what was published before.
        """
        sha256 = hashlib.sha256(content).hexdigest()
        existing = self.connection.execute(
            "SELECT * FROM artifact WHERE run_id = ? AND logical_name = ? AND sha256 = ?",
            (run_id, logical_name, sha256)).fetchone()
        if existing is not None:
            return {**dict(existing), "deduplicated": True}

        row = self.connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM artifact WHERE run_id = ? AND logical_name = ?",
            (run_id, logical_name)).fetchone()
        version = int(row["v"]) + 1
        artifact_id = str(uuid.uuid4())
        with self.connection:
            self.connection.execute(
                "INSERT INTO artifact (artifact_id, run_id, logical_name, version, media_type,"
                " size_bytes, sha256, storage_uri, git_ref, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (artifact_id, run_id, logical_name, version, media_type, len(content), sha256,
                 storage_uri or f"artifact://{run_id}/{logical_name}/{version}", git_ref, self.clock()))
        self.append_event(run_id, "artifact.published", None,
                          {"logical_name": logical_name, "version": version, "sha256": sha256})
        return {
            "artifact_id": artifact_id, "run_id": run_id, "logical_name": logical_name,
            "version": version, "media_type": media_type, "size_bytes": len(content),
            "sha256": sha256, "storage_uri": storage_uri or f"artifact://{run_id}/{logical_name}/{version}",
            "git_ref": git_ref, "deduplicated": False,
        }

    def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM artifact WHERE run_id = ? ORDER BY logical_name, version", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def has_artifact(self, run_id: str, logical_name: str, sha256: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM artifact WHERE run_id = ? AND logical_name = ? AND sha256 = ? LIMIT 1",
            (run_id, logical_name, sha256)).fetchone() is not None

    # -------------------------------------------------------------- telemetry --

    def record_usage(self, run_id: str, task_id: str, attempt: int, model: str,
                     tokens: dict[str, int], execution_ms: int | None, status: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO model_usage (usage_id, run_id, task_id, attempt, model, input_tokens,"
                " cached_input_tokens, cache_write_tokens, output_tokens, reasoning_tokens,"
                " execution_ms, status, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), run_id, task_id, attempt, model,
                 int(tokens.get("input", 0)), int(tokens.get("cached_input", 0)),
                 int(tokens.get("cache_write", 0)), int(tokens.get("output", 0)),
                 int(tokens.get("reasoning_output", 0)), execution_ms, status, self.clock()))
        self.append_event(run_id, "usage.recorded", task_id,
                          {"attempt": attempt, "model": model, "tokens": tokens})

    def calibration_rows(self, run_id: str) -> list[dict[str, Any]]:
        """Export executed telemetry in exactly the shape `calibrate` consumes."""
        rows = []
        for task in self.tasks(run_id):
            if task["state"] != "succeeded":
                continue
            usage = self.connection.execute(
                "SELECT SUM(input_tokens + cached_input_tokens + cache_write_tokens + output_tokens"
                " + reasoning_tokens) AS total, SUM(execution_ms) AS ms, MAX(model) AS model"
                " FROM model_usage WHERE run_id = ? AND task_id = ?", (run_id, task["task_id"])).fetchone()
            if usage is None or usage["total"] is None:
                continue
            estimate = task["estimate"]
            profile = estimate.get("token_profile", {})
            estimated_tokens = sum(
                float(profile.get(field, 0))
                for field in ("input", "cached_input", "cache_write", "output", "reasoning_output"))
            if estimated_tokens <= 0:
                continue
            rows.append({
                "task_id": task["task_id"],
                "task_type": task["category"] or "unknown",
                "complexity": task["complexity"] or "unknown",
                "model": usage["model"] or "unknown",
                "estimated_minutes": float(estimate.get("most_likely_minutes", 0)),
                "actual_minutes": round(float(usage["ms"] or 0) / 60000.0, 6),
                "estimated_total_tokens": estimated_tokens,
                "actual_total_tokens": float(usage["total"]),
            })
        return rows


@dataclass
class TaskOutcome:
    """What an executor returns for one attempt."""

    status: str  # "succeeded" | "failed"
    failure_class: str | None = None
    tokens: dict[str, int] = field(default_factory=dict)
    execution_ms: int = 0
    git_commit: str | None = None
    artifacts: list[tuple[str, bytes]] = field(default_factory=list)
    model: str = "unspecified"


Executor = Callable[[dict[str, Any], int], TaskOutcome]


class Orchestrator:
    """Durable, resumable DAG execution.

    The orchestrator holds no state of its own between steps: everything it needs
    is re-derivable from the store. That is what makes `resume()` on a fresh
    process equivalent to never having crashed.
    """

    def __init__(self, store: DurableStore, run_id: str, capacity: float = 4.0,
                 heartbeat_timeout_seconds: float = 60.0, worker_id: str = "worker-1") -> None:
        self.store = store
        self.run_id = run_id
        self.capacity = float(capacity)
        self.heartbeat_timeout_seconds = float(heartbeat_timeout_seconds)
        self.worker_id = worker_id

    # -------------------------------------------------------------- scheduling --

    def ready_tasks(self) -> list[dict[str, Any]]:
        tasks = {task["task_id"]: task for task in self.store.tasks(self.run_id)}
        ready = []
        for task in tasks.values():
            if task["state"] not in {"pending", "ready", "blocked"}:
                continue
            dependencies = task["depends_on"]
            if any(tasks[dep]["state"] != "succeeded" for dep in dependencies if dep in tasks):
                continue
            if task["worker_units"] > self.capacity:
                continue
            ready.append(task)
        ready.sort(key=lambda task: task["task_id"])
        return ready

    # ------------------------------------------------------------- reconciling --

    def reconcile_before_retry(self, task_id: str, expected_commit: str | None = None,
                               expected_artifact: tuple[str, str] | None = None) -> dict[str, Any]:
        """The four-step check that must precede any retry after a lost attempt.

        Skipping it is the standard cause of duplicated side effects: the work may
        already be committed, published, or recorded under an idempotency key.
        """
        idempotency = self.store.connection.execute(
            "SELECT state FROM idempotency_key WHERE scope = ? AND key = ?",
            (f"task:{self.run_id}", task_id)).fetchone()
        checks = {
            "original_request": "completed" if idempotency and idempotency["state"] == "completed" else "absent",
            "original_commit": (
                "present" if expected_commit and self.store.has_commit(self.run_id, expected_commit)
                else "absent"
            ),
            "original_artifact": (
                "present" if expected_artifact and self.store.has_artifact(
                    self.run_id, expected_artifact[0], expected_artifact[1]) else "absent"
            ),
        }
        already_done = any(value in {"completed", "present"} for value in checks.values())
        checks["decision"] = "adopt_existing_result" if already_done else "retry"
        self.store.append_event(self.run_id, "task.retry_scheduled", task_id, checks)
        return checks

    def _retry_decision(self, task: dict[str, Any], failure_class: str) -> tuple[bool, float]:
        policy = RETRY_POLICY.get(failure_class, RETRY_POLICY["permanent"])
        attempts = int(task["attempt_count"])
        if not policy["retry"] or attempts >= int(policy["max_attempts"]):
            return False, 0.0
        backoff = float(policy["backoff_base_seconds"]) * (float(policy["backoff_factor"]) ** (attempts - 1))
        return True, backoff

    # ---------------------------------------------------------------- stepping --

    def step(self, executor: Executor) -> dict[str, Any] | None:
        """Run one ready task to a verdict. Returns None when nothing is runnable."""
        run = self.store.get_run(self.run_id)
        if run["state"] in TERMINAL_RUN_STATES:
            return None
        if run["state"] == "pending":
            self.store.set_run_state(self.run_id, "running")

        self.store.sweep_lost_attempts(self.run_id, self.heartbeat_timeout_seconds)
        ready = self.ready_tasks()
        if not ready:
            return None

        task = ready[0]
        task_id = task["task_id"]
        attempt = self.store.start_attempt(self.run_id, task_id, self.worker_id)
        scope = f"task:{self.run_id}"

        if int(task["attempt_count"]) > 0:
            self.reconcile_before_retry(task_id)

        status, replayed = self.store.begin_idempotent(scope, task_id, {"task_id": task_id})
        if status == "replayed":
            self.store.finish_attempt(attempt["attempt_id"], "succeeded")
            self.store.set_task_state(self.run_id, task_id, "succeeded")
            self.store.append_event(self.run_id, "task.succeeded", task_id,
                                    {"replayed": True, "attempt": attempt["attempt_number"]})
            return {"task_id": task_id, "status": "succeeded", "replayed": True}

        try:
            outcome = executor(task, attempt["attempt_number"])
        except BaseException:
            # The worker vanished mid-attempt. Leave the attempt open so the
            # heartbeat sweeper classifies it as lost_worker rather than guessing.
            self.store.fail_idempotent(scope, task_id)
            raise

        self.store.heartbeat(attempt["attempt_id"])
        if outcome.tokens:
            self.store.record_usage(self.run_id, task_id, attempt["attempt_number"],
                                    outcome.model, outcome.tokens, outcome.execution_ms,
                                    outcome.status)

        if outcome.status == "succeeded":
            for logical_name, content in outcome.artifacts:
                self.store.publish_artifact(self.run_id, logical_name, content)
            self.store.record_checkpoint(
                self.run_id, task_id, "git" if outcome.git_commit else "state",
                git_commit=outcome.git_commit,
                state_blob={"task_id": task_id, "attempt": attempt["attempt_number"]})
            self.store.finish_attempt(attempt["attempt_id"], "succeeded",
                                      execution_ms=outcome.execution_ms)
            self.store.set_task_state(self.run_id, task_id, "succeeded")
            self.store.complete_idempotent(scope, task_id,
                                           {"task_id": task_id, "status": "succeeded"})
            self.store.enqueue_outbox(self.run_id, "task.succeeded", {"task_id": task_id})
            self.store.append_event(self.run_id, "task.succeeded", task_id,
                                    {"attempt": attempt["attempt_number"]})
            return {"task_id": task_id, "status": "succeeded", "replayed": False}

        failure_class = outcome.failure_class or "permanent"
        self.store.fail_idempotent(scope, task_id)
        self.store.finish_attempt(attempt["attempt_id"], _outcome_for(failure_class), failure_class,
                                  execution_ms=outcome.execution_ms)
        current = next(t for t in self.store.tasks(self.run_id) if t["task_id"] == task_id)
        should_retry, backoff = self._retry_decision(current, failure_class)
        if should_retry:
            self.store.set_task_state(self.run_id, task_id, "ready", failure_class)
            self.store.append_event(self.run_id, "task.retry_scheduled", task_id,
                                    {"failure_class": failure_class, "backoff_seconds": backoff,
                                     "attempt": attempt["attempt_number"]})
            return {"task_id": task_id, "status": "retry_scheduled",
                    "failure_class": failure_class, "backoff_seconds": backoff}

        self.store.set_task_state(self.run_id, task_id, "failed", failure_class)
        self.store.append_event(self.run_id, "task.failed", task_id,
                                {"failure_class": failure_class, "attempt": attempt["attempt_number"]})
        return {"task_id": task_id, "status": "failed", "failure_class": failure_class}

    def run_to_completion(self, executor: Executor, max_steps: int = 10_000) -> dict[str, Any]:
        steps = 0
        while steps < max_steps:
            result = self.step(executor)
            if result is None:
                break
            steps += 1
        return self.finalize()

    def finalize(self) -> dict[str, Any]:
        tasks = self.store.tasks(self.run_id)
        run = self.store.get_run(self.run_id)
        if run["state"] in TERMINAL_RUN_STATES:
            return {"run_id": self.run_id, "state": run["state"], "tasks": tasks}
        if all(task["state"] == "succeeded" for task in tasks):
            state = "succeeded"
        elif any(task["state"] == "failed" for task in tasks):
            state = "failed"
        else:
            return {"run_id": self.run_id, "state": run["state"], "tasks": tasks}
        self.store.set_run_state(self.run_id, state)
        self.store.append_event(self.run_id, "run.finished", None, {"state": state})
        return {"run_id": self.run_id, "state": state, "tasks": tasks}

    def resume(self) -> dict[str, Any]:
        """Recover after a crash: reclassify silent attempts, then report what is left."""
        lost = self.store.sweep_lost_attempts(self.run_id, self.heartbeat_timeout_seconds)
        tasks = self.store.tasks(self.run_id)
        remaining = [task for task in tasks if task["state"] not in TERMINAL_TASK_STATES]
        self.store.append_event(self.run_id, "run.state_changed", None,
                                {"state": "recovering", "lost_attempts": len(lost),
                                 "remaining_tasks": len(remaining)})
        return {
            "run_id": self.run_id,
            "lost_attempts": [attempt["task_id"] for attempt in lost],
            "completed_tasks": [t["task_id"] for t in tasks if t["state"] == "succeeded"],
            "remaining_tasks": [t["task_id"] for t in remaining],
        }


def _outcome_for(failure_class: str) -> str:
    return {
        "transient": "transient_failure",
        "permanent": "permanent_failure",
        "business_conflict": "business_conflict",
        "lost_worker": "lost",
    }.get(failure_class, "permanent_failure")


def recovery_aware_eta(store: DurableStore, run_id: str, capacity: float = 4.0) -> dict[str, Any]:
    """Skill 12 — recompute the ETA from what has actually executed.

    Observed durations correct the remaining estimates. Recovery time already
    spent is reported separately and is *not* subtracted from the remaining work.
    Human approval and acceptance stay outside this number, as everywhere else.
    """
    tasks = store.tasks(run_id)
    completed = [task for task in tasks if task["state"] == "succeeded"]
    remaining = [task for task in tasks if task["state"] not in TERMINAL_TASK_STATES]

    observed_ratios: list[float] = []
    recovery_ms_total = 0
    for task in completed:
        row = store.connection.execute(
            "SELECT SUM(execution_ms) AS ms, SUM(COALESCE(recovery_ms, 0)) AS rms"
            " FROM task_attempt WHERE run_id = ? AND task_id = ?", (run_id, task["task_id"])).fetchone()
        if not row or row["ms"] is None:
            continue
        recovery_ms_total += int(row["rms"] or 0)
        estimated = float(task["estimate"].get("most_likely_minutes", 0))
        actual = float(row["ms"]) / 60000.0
        if estimated > 0 and actual > 0:
            observed_ratios.append(actual / estimated)

    multiplier = quantile(observed_ratios, 0.5) if observed_ratios else 1.0
    basis = "forecast_only"
    if len(observed_ratios) >= 5:
        basis = "telemetry_dominant"
    elif observed_ratios:
        basis = "forecast_plus_telemetry"

    remaining_minutes = sum(float(task["estimate"].get("most_likely_minutes", 0)) for task in remaining)
    remaining_worker_minutes = sum(
        float(task["estimate"].get("most_likely_minutes", 0)) * float(task["worker_units"])
        for task in remaining)
    corrected = remaining_worker_minutes * multiplier
    parallel_minutes = corrected / max(capacity, 1e-9)

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
        "remaining_serial_minutes": round(remaining_minutes, 2),
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
        "note": (
            "Quantile spread above P50 is a fixed uncertainty band, not a second Monte Carlo. "
            "For a full distribution re-run `forecast` with a calibrated DAG."
        ),
    }


def replay_is_gapless(events: Iterable[dict[str, Any]], after_seq: int = 0) -> bool:
    """A replay is correct only if the sequence is contiguous from after_seq + 1."""
    expected = int(after_seq) + 1
    for event in events:
        if int(event["seq"]) != expected:
            return False
        expected += 1
    return True
