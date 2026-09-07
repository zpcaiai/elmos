"""Durable ETGB lifecycle state with CAS, leases, checkpoints and idempotency."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

from .canonical import canonical_json, digest_json
from .state_v11 import ALLOWED_TRANSITIONS, JsonRunStateStore, RunState, StateConflict, TERMINAL_STATES


class StateStore:
    """SQLite-backed state store suitable for one ETGB control-plane shard.

    SQLite is intentionally scoped to local control-plane state; it is not
    advertised as a distributed coordinator.  Production deployments should
    provide a transactional database adapter with the same methods.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=30000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except Exception:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def _migrate(self) -> None:
        with self._transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    suite_id TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    fencing_token TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS case_runs (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    result_digest TEXT,
                    owner TEXT NOT NULL,
                    fencing_token TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, case_id, seed)
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    cursor_json TEXT NOT NULL,
                    artifact_digest TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, case_id)
                );
                CREATE TABLE IF NOT EXISTS leases (
                    resource TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    fencing_token TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def now() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat()

    def create_run(self, *, run_id: str, idempotency_key: str, suite_id: str, profile: str, owner: str, plan_digest: str, candidate: dict[str, Any], budget: dict[str, Any]) -> dict[str, Any]:
        now = self.now()
        token = secrets.token_hex(16)
        with self._transaction() as connection:
            existing = connection.execute("SELECT * FROM runs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                return dict(existing)
            connection.execute(
                "INSERT INTO runs(run_id,idempotency_key,suite_id,profile,status,owner,fencing_token,plan_digest,candidate_json,budget_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, idempotency_key, suite_id, profile, "PLANNED", owner, token, plan_digest, canonical_json(candidate).decode(), canonical_json(budget).decode(), now, now),
            )
            self._audit(connection, run_id, "run.created", {"profile": profile, "owner": owner})
            return dict(connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())

    def claim_run(self, run_id: str, *, owner: str, lease_seconds: int = 900) -> str:
        if lease_seconds < 1 or lease_seconds > 86400:
            raise StateConflict("invalid lease duration")
        now = dt.datetime.now(dt.timezone.utc)
        expires = now + dt.timedelta(seconds=lease_seconds)
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                raise StateConflict("run does not exist")
            if row["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                raise StateConflict(f"cannot claim terminal run {run_id}")
            lease = connection.execute("SELECT * FROM leases WHERE resource=?", (f"run:{run_id}",)).fetchone()
            if row["owner"] != owner and lease and dt.datetime.fromisoformat(lease["expires_at"]) > now:
                raise StateConflict("run is owned by another live worker")
            token = secrets.token_hex(16)
            connection.execute("UPDATE runs SET owner=?,fencing_token=?,updated_at=?,version=version+1 WHERE run_id=?", (owner, token, now.isoformat(), run_id))
            connection.execute("INSERT INTO leases(resource,owner,fencing_token,expires_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(resource) DO UPDATE SET owner=excluded.owner,fencing_token=excluded.fencing_token,expires_at=excluded.expires_at,updated_at=excluded.updated_at", (f"run:{run_id}", owner, token, expires.isoformat(), now.isoformat()))
            self._audit(connection, run_id, "run.claimed", {"owner": owner})
            return token

    def transition(self, run_id: str, *, owner: str, fencing_token: str, expected: str, new_status: str) -> dict[str, Any]:
        now = self.now()
        with self._transaction() as connection:
            self._assert_owner(connection, run_id, owner, fencing_token)
            cursor = connection.execute("UPDATE runs SET status=?,updated_at=?,version=version+1 WHERE run_id=? AND owner=? AND fencing_token=? AND status=?", (new_status, now, run_id, owner, fencing_token, expected))
            if cursor.rowcount != 1:
                raise StateConflict(f"transition rejected: {expected} -> {new_status}")
            self._audit(connection, run_id, "run.transition", {"from": expected, "to": new_status})
            return dict(connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())

    def save_checkpoint(self, run_id: str, case_id: str, *, owner: str, fencing_token: str, phase: str, cursor: dict[str, Any], artifact_digest: str | None = None) -> None:
        now = self.now()
        with self._transaction() as connection:
            self._assert_owner(connection, run_id, owner, fencing_token)
            connection.execute("INSERT INTO checkpoints(run_id,case_id,phase,cursor_json,artifact_digest,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(run_id,case_id) DO UPDATE SET phase=excluded.phase,cursor_json=excluded.cursor_json,artifact_digest=excluded.artifact_digest,updated_at=excluded.updated_at", (run_id, case_id, phase, canonical_json(cursor).decode(), artifact_digest, now))
            self._audit(connection, run_id, "case.checkpoint", {"case_id": case_id, "phase": phase})

    def save_case_result(self, run_id: str, case_id: str, seed: int, *, owner: str, fencing_token: str, result: dict[str, Any], attempt: int = 1) -> dict[str, Any]:
        now = self.now()
        result_json = canonical_json(result).decode()
        result_digest = digest_json(result)
        with self._transaction() as connection:
            self._assert_owner(connection, run_id, owner, fencing_token)
            existing = connection.execute("SELECT * FROM case_runs WHERE run_id=? AND case_id=? AND seed=?", (run_id, case_id, seed)).fetchone()
            if existing and existing["result_digest"]:
                if existing["result_digest"] != result_digest:
                    raise StateConflict("idempotency conflict: case result differs")
                return dict(existing)
            connection.execute("INSERT INTO case_runs(run_id,case_id,seed,attempt,status,result_json,result_digest,owner,fencing_token,started_at,finished_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(run_id,case_id,seed) DO UPDATE SET attempt=excluded.attempt,status=excluded.status,result_json=excluded.result_json,result_digest=excluded.result_digest,owner=excluded.owner,fencing_token=excluded.fencing_token,finished_at=excluded.finished_at,updated_at=excluded.updated_at", (run_id, case_id, seed, attempt, result.get("status", "error"), result_json, result_digest, owner, fencing_token, result.get("started_at"), result.get("finished_at"), now))
            self._audit(connection, run_id, "case.result", {"case_id": case_id, "seed": seed, "status": result.get("status")})
            return dict(connection.execute("SELECT * FROM case_runs WHERE run_id=? AND case_id=? AND seed=?", (run_id, case_id, seed)).fetchone())

    def get_case_results(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM case_runs WHERE run_id=? ORDER BY case_id,seed", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def _assert_owner(self, connection: sqlite3.Connection, run_id: str, owner: str, fencing_token: str) -> None:
        row = connection.execute("SELECT owner,fencing_token,status FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row or row["owner"] != owner or row["fencing_token"] != fencing_token or row["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            raise StateConflict("worker ownership or fencing token is stale")
        lease = connection.execute("SELECT owner,fencing_token,expires_at FROM leases WHERE resource=?", (f"run:{run_id}",)).fetchone()
        if not lease or lease["owner"] != owner or lease["fencing_token"] != fencing_token or dt.datetime.fromisoformat(lease["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
            raise StateConflict("worker lease is missing or expired")

    @staticmethod
    def _audit(connection: sqlite3.Connection, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        connection.execute("INSERT INTO audit_events(run_id,event_type,payload_json,created_at) VALUES(?,?,?,?)", (run_id, event_type, canonical_json(payload).decode(), StateStore.now()))
