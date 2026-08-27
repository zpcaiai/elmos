"""Transactional local durable store.

The API mirrors the PostgreSQL migration and intentionally keeps event history
append-only. SQLite is used only as a dependency-free local backend; the same
invariants are expressed in ``sql/001_autonomy_kernel.sql`` for PostgreSQL.
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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .errors import ContractError, StaleStateError
from .models import bytes_digest, canonical_json, digest, utc_now

RUN_STATES = {
    "CREATED", "DISCOVERING", "SPECIFYING", "PLANNING", "AWAITING_APPROVAL", "EXECUTING",
    "VERIFYING", "REPAIRING", "RELEASING", "PAUSED", "BLOCKED", "CANCEL_REQUESTED",
    "CANCELLED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "PARTIALLY_COMPLETED", "ROLLING_BACK",
    "ROLLED_BACK", "SUCCEEDED",
}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"DISCOVERING", "SPECIFYING", "CANCEL_REQUESTED"},
    "DISCOVERING": {"SPECIFYING", "PLANNING", "PAUSED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "CANCEL_REQUESTED"},
    "SPECIFYING": {"PLANNING", "BLOCKED", "PAUSED", "FAILED_TERMINAL", "CANCEL_REQUESTED"},
    "PLANNING": {"AWAITING_APPROVAL", "EXECUTING", "BLOCKED", "PAUSED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "CANCEL_REQUESTED"},
    "AWAITING_APPROVAL": {"EXECUTING", "BLOCKED", "CANCEL_REQUESTED", "FAILED_TERMINAL"},
    "EXECUTING": {"VERIFYING", "PAUSED", "FAILED_RETRYABLE", "FAILED_TERMINAL", "CANCEL_REQUESTED"},
    "VERIFYING": {"REPAIRING", "RELEASING", "PARTIALLY_COMPLETED", "FAILED_TERMINAL", "PAUSED", "CANCEL_REQUESTED"},
    "REPAIRING": {"EXECUTING", "VERIFYING", "PARTIALLY_COMPLETED", "FAILED_TERMINAL", "PAUSED", "CANCEL_REQUESTED"},
    "RELEASING": {"SUCCEEDED", "ROLLING_BACK", "FAILED_TERMINAL"},
    "CANCEL_REQUESTED": {"CANCELLED", "ROLLING_BACK"},
    "ROLLING_BACK": {"ROLLED_BACK", "FAILED_TERMINAL"},
    "PAUSED": {"DISCOVERING", "SPECIFYING", "PLANNING", "EXECUTING", "VERIFYING", "REPAIRING", "CANCEL_REQUESTED"},
    "FAILED_RETRYABLE": {"DISCOVERING", "SPECIFYING", "PLANNING", "EXECUTING", "VERIFYING", "REPAIRING", "FAILED_TERMINAL", "CANCEL_REQUESTED"},
}


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL,
  task_spec_hash TEXT NOT NULL, workflow_version TEXT NOT NULL,
  repo_snapshot_sha TEXT, state TEXT NOT NULL, payload TEXT NOT NULL,
  idempotency_key TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS steps (
  run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  step_id TEXT NOT NULL, step_type TEXT NOT NULL, step_version TEXT NOT NULL,
  state TEXT NOT NULL, attempt_no INTEGER NOT NULL DEFAULT 0,
  input_artifact_hashes TEXT NOT NULL DEFAULT '[]', output_artifact_hashes TEXT NOT NULL DEFAULT '[]',
  error TEXT, started_at TEXT, finished_at TEXT, wall_clock_ms INTEGER,
  PRIMARY KEY(run_id, step_id)
);
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  sequence_no INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL,
  payload TEXT NOT NULL, occurred_at TEXT NOT NULL, PRIMARY KEY(run_id, sequence_no)
);
CREATE TABLE IF NOT EXISTS checkpoints (
  checkpoint_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  step_id TEXT, state_snapshot TEXT NOT NULL, side_effect_cursor INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
  lease_id TEXT PRIMARY KEY, resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,
  owner_id TEXT NOT NULL, fencing_token INTEGER NOT NULL, state TEXT NOT NULL,
  acquired_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  released_at TEXT, UNIQUE(resource_type, resource_id, fencing_token)
);
CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT, kind TEXT NOT NULL,
  content_hash TEXT NOT NULL, media_type TEXT NOT NULL, content BLOB NOT NULL,
  metadata TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, kind, content_hash)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT, claim TEXT NOT NULL,
  evidence_type TEXT NOT NULL, source TEXT NOT NULL, confidence REAL, snapshot_sha TEXT,
  captured_at TEXT NOT NULL, expires_at TEXT
);
CREATE TABLE IF NOT EXISTS policy_decisions (
  decision_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT, event_type TEXT NOT NULL,
  decision TEXT NOT NULL, reason TEXT NOT NULL, policy_hash TEXT NOT NULL, payload TEXT NOT NULL,
  decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_calls (
  tool_call_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT, step_id TEXT NOT NULL,
  tool_id TEXT NOT NULL, tool_version TEXT NOT NULL, state TEXT NOT NULL, input_hash TEXT NOT NULL,
  idempotency_key TEXT, result TEXT, error TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, tool_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT,
  scope TEXT NOT NULL, risk_level TEXT NOT NULL, state TEXT NOT NULL,
  decision_by TEXT, decision_reason TEXT, expires_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validations (
  validation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT,
  validator_id TEXT NOT NULL, validator_version TEXT NOT NULL, status TEXT NOT NULL,
  metrics TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS findings (
  finding_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT,
  category TEXT NOT NULL, severity TEXT NOT NULL, confidence REAL NOT NULL,
  description TEXT NOT NULL, location TEXT, evidence_ids TEXT NOT NULL,
  reproducer TEXT, status TEXT NOT NULL, validated_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acceptance_decisions (
  acceptance_decision_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT,
  decision TEXT NOT NULL, gate_results TEXT NOT NULL, release_artifact_ids TEXT NOT NULL,
  rollback_artifact_ids TEXT NOT NULL, deployment_complete INTEGER NOT NULL DEFAULT 0,
  decided_by TEXT NOT NULL, decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS capability_packages (
  package_id TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
  content_hash TEXT NOT NULL, manifest TEXT NOT NULL, signature TEXT, state TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(name, version)
);
CREATE TABLE IF NOT EXISTS eval_runs (
  eval_run_id TEXT PRIMARY KEY, suite_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
  task_segment TEXT NOT NULL, result TEXT NOT NULL, cost REAL, wall_clock_ms INTEGER, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS elo_ratings (
  candidate_id TEXT NOT NULL, task_segment TEXT NOT NULL, rating REAL NOT NULL,
  uncertainty REAL NOT NULL, sample_count INTEGER NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(candidate_id, task_segment)
);
CREATE TABLE IF NOT EXISTS cache_entries (
  tenant_id TEXT NOT NULL, cache_layer TEXT NOT NULL, key_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL, value TEXT NOT NULL, provenance TEXT NOT NULL,
  expires_at TEXT, created_at TEXT NOT NULL, PRIMARY KEY(tenant_id, cache_layer, key_hash)
);
CREATE TABLE IF NOT EXISTS metrics (
  metric TEXT PRIMARY KEY, value REAL NOT NULL
);
"""


class DurableStore:
    """Thread-safe transactional store with tenant-scoped content and leases."""

    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:":
            parent = Path(path).expanduser().resolve().parent
            if not parent.exists() or not parent.is_dir():
                raise ContractError("STORE_UNAVAILABLE", f"store parent does not exist: {parent}")
        self.path = path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=10)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=10000")
        self._connection.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except Exception:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_json(value).decode("utf-8")

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        for key in ("payload", "state_snapshot", "metadata", "source", "result", "error", "provenance"):
            if key in value and isinstance(value[key], str):
                try:
                    value[key] = json.loads(value[key])
                except json.JSONDecodeError:
                    pass
        return value

    def create_run(
        self, *, tenant_id: str, account_id: str, task_spec_hash: str, workflow_version: str,
        repo_snapshot_sha: str | None, payload: Mapping[str, Any], idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        run_id = str(uuid.uuid4())
        with self.transaction() as db:
            if idempotency_key:
                old = db.execute(
                    "SELECT * FROM runs WHERE tenant_id=? AND idempotency_key=?", (tenant_id, idempotency_key)
                ).fetchone()
                if old:
                    return self._decode(old) or {}
            db.execute(
                "INSERT INTO runs(run_id,tenant_id,account_id,task_spec_hash,workflow_version,repo_snapshot_sha,state,payload,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, tenant_id, account_id, task_spec_hash, workflow_version, repo_snapshot_sha, "CREATED", self._json(payload), idempotency_key, now, now),
            )
            self._append_event_locked(db, run_id, "RUN_CREATED", {"state": "CREATED"}, event_id=None)
            self._inc_metric_locked(db, "runs_created")
            return self._decode(db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()) or {}

    def get_run(self, run_id: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            query = "SELECT * FROM runs WHERE run_id=?"
            args: list[Any] = [run_id]
            if tenant_id is not None:
                query += " AND tenant_id=?"
                args.append(tenant_id)
            return self._decode(self._connection.execute(query, args).fetchone())

    def upsert_step(self, *, run_id: str, step_id: str, step_type: str, step_version: str = "2.0.0", state: str = "PENDING", attempt_no: int = 0, tenant_id: str | None = None) -> dict[str, Any]:
        run = self.get_run(run_id, tenant_id=tenant_id)
        if run is None:
            raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
        with self.transaction() as db:
            db.execute("INSERT INTO steps(run_id,step_id,step_type,step_version,state,attempt_no) VALUES(?,?,?,?,?,?) ON CONFLICT(run_id,step_id) DO UPDATE SET state=excluded.state,attempt_no=excluded.attempt_no", (run_id, step_id, step_type, step_version, state, attempt_no))
            row = db.execute("SELECT * FROM steps WHERE run_id=? AND step_id=?", (run_id, step_id)).fetchone()
        return self._decode(row) or {}

    def record_policy_decision(self, *, tenant_id: str, run_id: str | None, event_type: str, decision: str, reason: str, policy_hash: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        row = {"decision_id": str(uuid.uuid4()), "tenant_id": tenant_id, "run_id": run_id, "event_type": event_type, "decision": decision, "reason": reason, "policy_hash": policy_hash, "payload": dict(payload), "decided_at": utc_now()}
        with self.transaction() as db:
            db.execute("INSERT INTO policy_decisions(decision_id,tenant_id,run_id,event_type,decision,reason,policy_hash,payload,decided_at) VALUES(?,?,?,?,?,?,?,?,?)", (row["decision_id"], tenant_id, run_id, event_type, decision, reason, policy_hash, self._json(payload), row["decided_at"]))
        return row

    def get_tool_call(self, *, tenant_id: str, tool_id: str, idempotency_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM tool_calls WHERE tenant_id=? AND tool_id=? AND idempotency_key=?", (tenant_id, tool_id, idempotency_key)).fetchone()
        return self._decode(row)

    def record_tool_call(self, *, tenant_id: str, run_id: str | None, step_id: str, tool_id: str, tool_version: str, state: str, input_hash: str, idempotency_key: str | None, result: Any = None, error: Any = None) -> dict[str, Any]:
        call_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.transaction() as db:
            if idempotency_key:
                existing = db.execute("SELECT * FROM tool_calls WHERE tenant_id=? AND tool_id=? AND idempotency_key=?", (tenant_id, tool_id, idempotency_key)).fetchone()
                if existing:
                    return self._decode(existing) or {}
            db.execute("INSERT INTO tool_calls(tool_call_id,tenant_id,run_id,step_id,tool_id,tool_version,state,input_hash,idempotency_key,result,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (call_id, tenant_id, run_id, step_id, tool_id, tool_version, state, input_hash, idempotency_key, self._json(result) if result is not None else None, self._json(error) if error is not None else None, created_at))
        return {"tool_call_id": call_id, "tenant_id": tenant_id, "run_id": run_id, "step_id": step_id, "tool_id": tool_id, "tool_version": tool_version, "state": state, "input_hash": input_hash, "idempotency_key": idempotency_key, "result": result, "error": error, "created_at": created_at}

    def transition_run(self, run_id: str, target: str, *, event_type: str = "STATE_CHANGED", payload: Mapping[str, Any] | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        if target not in RUN_STATES:
            raise ContractError("ORCHESTRATOR_INCONSISTENT", f"unknown run state: {target}")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or (tenant_id is not None and row["tenant_id"] != tenant_id):
                raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
            current = row["state"]
            if target not in ALLOWED_TRANSITIONS.get(current, set()):
                raise ContractError("ORCHESTRATOR_INCONSISTENT", f"illegal transition {current}->{target}")
            now = utc_now()
            db.execute("UPDATE runs SET state=?,updated_at=? WHERE run_id=?", (target, now, run_id))
            event_payload = {"from": current, "to": target, **(dict(payload or {}))}
            self._append_event_locked(db, run_id, event_type, event_payload, event_id=None)
            return self._decode(db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()) or {}

    def _append_event_locked(self, db: sqlite3.Connection, run_id: str, event_type: str, payload: Mapping[str, Any], event_id: str | None) -> dict[str, Any]:
        event_id = event_id or str(uuid.uuid4())
        existing = db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if existing:
            return dict(existing)
        row = db.execute("SELECT COALESCE(MAX(sequence_no),0)+1 AS next FROM events WHERE run_id=?", (run_id,)).fetchone()
        sequence = int(row["next"])
        occurred = utc_now()
        db.execute(
            "INSERT INTO events(run_id,sequence_no,event_id,event_type,payload,occurred_at) VALUES(?,?,?,?,?,?)",
            (run_id, sequence, event_id, event_type, self._json(payload), occurred),
        )
        self._inc_metric_locked(db, "events_appended")
        return {"run_id": run_id, "sequence_no": sequence, "event_id": event_id, "event_type": event_type, "payload": dict(payload), "occurred_at": occurred}

    def append_event(self, run_id: str, event_type: str, payload: Mapping[str, Any], *, event_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        with self.transaction() as db:
            run = db.execute("SELECT tenant_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or (tenant_id is not None and run["tenant_id"] != tenant_id):
                raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
            return self._append_event_locked(db, run_id, event_type, payload, event_id)

    def events_since(self, run_id: str, sequence_no: int = 0, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            run = self._connection.execute("SELECT tenant_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or (tenant_id is not None and run["tenant_id"] != tenant_id):
                raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
            rows = self._connection.execute("SELECT * FROM events WHERE run_id=? AND sequence_no>? ORDER BY sequence_no", (run_id, sequence_no)).fetchall()
            return [self._decode(row) or {} for row in rows]

    def replay_state(self, run_id: str, *, tenant_id: str | None = None) -> str:
        events = self.events_since(run_id, 0, tenant_id=tenant_id)
        state: str | None = None
        for event in events:
            payload = event.get("payload") or {}
            if event["event_type"] == "RUN_CREATED":
                state = "CREATED"
            elif event["event_type"] == "STATE_CHANGED":
                state = payload.get("to")
        if not state:
            raise StaleStateError("ORCHESTRATOR_INCONSISTENT", "run has no reconstructable state")
        current = self.get_run(run_id, tenant_id=tenant_id)
        if not current or current["state"] != state:
            raise StaleStateError("ORCHESTRATOR_INCONSISTENT", "materialized state differs from event replay")
        return state

    def export_run(self, run_id: str, *, tenant_id: str | None = None) -> dict[str, Any]:
        run = self.get_run(run_id, tenant_id=tenant_id)
        if run is None:
            raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
        with self._lock:
            steps = self._connection.execute("SELECT * FROM steps WHERE run_id=? ORDER BY step_id", (run_id,)).fetchall()
            checkpoints = self._connection.execute("SELECT * FROM checkpoints WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
        return {"run": run, "steps": [self._decode(row) or {} for row in steps], "events": self.events_since(run_id, tenant_id=tenant_id), "checkpoints": [self._decode(row) or {} for row in checkpoints], "exported_at": utc_now(), "export_hash": digest({"run": run, "steps": [dict(row) for row in steps], "events": self.events_since(run_id, tenant_id=tenant_id)})}

    def backup_to(self, destination: str) -> dict[str, Any]:
        """Create an atomic, integrity-checked SQLite backup."""
        target = Path(destination).expanduser().resolve()
        if target.name in {"", "."}:
            raise ContractError("BACKUP_INVALID", "backup destination must be a file")
        if self.path != ":memory:" and target == Path(self.path).expanduser().resolve():
            raise ContractError("BACKUP_INVALID", "backup destination must differ from the active store")
        if not target.parent.exists() or not target.parent.is_dir():
            raise ContractError("BACKUP_INVALID", f"backup parent does not exist: {target.parent}")
        fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with self._lock:
                replica = sqlite3.connect(str(temporary))
                try:
                    self._connection.backup(replica)
                    replica.execute("PRAGMA wal_checkpoint(FULL)")
                    check = replica.execute("PRAGMA integrity_check").fetchone()
                    if not check or check[0] != "ok":
                        raise ContractError("BACKUP_INVALID", "SQLite integrity check failed")
                finally:
                    replica.close()
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        raw = target.read_bytes()
        return {"path": str(target), "content_hash": bytes_digest(raw), "size_bytes": len(raw), "created_at": utc_now()}

    @classmethod
    def restore_from(cls, source: str, destination: str) -> dict[str, Any]:
        """Validate a backup and atomically install it as a new local store."""
        source_path = Path(source).expanduser().resolve()
        target = Path(destination).expanduser().resolve()
        if source_path == target:
            raise ContractError("RESTORE_INVALID", "restore source and destination must differ")
        if not source_path.is_file():
            raise ContractError("RESTORE_INVALID", f"restore source does not exist: {source_path}")
        if not target.parent.exists() or not target.parent.is_dir():
            raise ContractError("RESTORE_INVALID", f"restore parent does not exist: {target.parent}")
        check_connection = sqlite3.connect(str(source_path))
        try:
            integrity = check_connection.execute("PRAGMA integrity_check").fetchone()
            tables = {row[0] for row in check_connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            check_connection.close()
        required = {"runs", "events", "leases", "artifacts"}
        if not integrity or integrity[0] != "ok" or not required.issubset(tables):
            raise ContractError("RESTORE_INVALID", "source is not a Repository Autonomy Kernel store")
        fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            source_connection = sqlite3.connect(str(source_path))
            replica = sqlite3.connect(str(temporary))
            try:
                source_connection.backup(replica)
                check = replica.execute("PRAGMA integrity_check").fetchone()
                if not check or check[0] != "ok":
                    raise ContractError("RESTORE_INVALID", "restored SQLite integrity check failed")
            finally:
                replica.close()
                source_connection.close()
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        raw = target.read_bytes()
        return {"path": str(target), "content_hash": bytes_digest(raw), "size_bytes": len(raw), "restored_at": utc_now()}

    def create_checkpoint(self, run_id: str, state_snapshot: Mapping[str, Any], *, step_id: str | None = None, side_effect_cursor: int = 0, tenant_id: str | None = None) -> dict[str, Any]:
        if self.get_run(run_id, tenant_id=tenant_id) is None:
            raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
        checkpoint_id = str(uuid.uuid4())
        content_hash = digest(state_snapshot)
        row = {"checkpoint_id": checkpoint_id, "run_id": run_id, "step_id": step_id, "state_snapshot": dict(state_snapshot), "side_effect_cursor": side_effect_cursor, "content_hash": content_hash, "created_at": utc_now()}
        with self.transaction() as db:
            db.execute("INSERT INTO checkpoints(checkpoint_id,run_id,step_id,state_snapshot,side_effect_cursor,content_hash,created_at) VALUES(?,?,?,?,?,?,?)", (checkpoint_id, run_id, step_id, self._json(state_snapshot), side_effect_cursor, content_hash, row["created_at"]))
            self._append_event_locked(db, run_id, "CHECKPOINT_CREATED", {"checkpoint_id": checkpoint_id, "content_hash": content_hash}, event_id=None)
        return row

    def latest_checkpoint(self, run_id: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
        if self.get_run(run_id, tenant_id=tenant_id) is None:
            raise ContractError("RUN_NOT_FOUND", "run is not visible in the requested tenant")
        with self._lock:
            return self._decode(self._connection.execute("SELECT * FROM checkpoints WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone())

    def acquire_lease(self, resource_type: str, resource_id: str, owner_id: str, *, ttl_seconds: int = 60) -> dict[str, Any]:
        if ttl_seconds < 1 or ttl_seconds > 86400:
            raise ContractError("INVALID_INPUT", "lease ttl must be between 1 and 86400 seconds")
        with self.transaction() as db:
            latest = db.execute("SELECT COALESCE(MAX(fencing_token),0) AS token FROM leases WHERE resource_type=? AND resource_id=?", (resource_type, resource_id)).fetchone()
            token = int(latest["token"]) + 1
            now = datetime.now(UTC)
            row = {"lease_id": str(uuid.uuid4()), "resource_type": resource_type, "resource_id": resource_id, "owner_id": owner_id, "fencing_token": token, "state": "ACTIVE", "acquired_at": now.isoformat().replace("+00:00", "Z"), "heartbeat_at": now.isoformat().replace("+00:00", "Z"), "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z"), "released_at": None}
            db.execute("INSERT INTO leases(lease_id,resource_type,resource_id,owner_id,fencing_token,state,acquired_at,heartbeat_at,expires_at,released_at) VALUES(?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))
            self._inc_metric_locked(db, "leases_acquired")
            return row

    def assert_lease(self, lease: Mapping[str, Any]) -> None:
        resource_type = str(lease.get("resource_type", ""))
        resource_id = str(lease.get("resource_id", ""))
        token = lease.get("fencing_token")
        owner_id = str(lease.get("owner_id", ""))
        with self._lock:
            row = self._connection.execute("SELECT * FROM leases WHERE resource_type=? AND resource_id=? AND fencing_token=?", (resource_type, resource_id, token)).fetchone()
        if row is None or row["owner_id"] != owner_id or row["state"] != "ACTIVE" or row["expires_at"] <= utc_now():
            raise StaleStateError("FENCING_REJECTED", "lease is not current or has expired")
        with self._lock:
            newest = self._connection.execute("SELECT MAX(fencing_token) AS token FROM leases WHERE resource_type=? AND resource_id=?", (resource_type, resource_id)).fetchone()["token"]
        if int(newest) != int(token):
            raise StaleStateError("FENCING_REJECTED", "a newer fencing token owns the resource")

    def heartbeat_lease(self, lease: Mapping[str, Any], *, ttl_seconds: int = 60) -> dict[str, Any]:
        self.assert_lease(lease)
        now = datetime.now(UTC)
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
        with self.transaction() as db:
            db.execute("UPDATE leases SET heartbeat_at=?,expires_at=? WHERE lease_id=? AND fencing_token=?", (now.isoformat().replace("+00:00", "Z"), expires, lease["lease_id"], lease["fencing_token"]))
        return {**dict(lease), "heartbeat_at": now.isoformat().replace("+00:00", "Z"), "expires_at": expires}

    def release_lease(self, lease: Mapping[str, Any]) -> None:
        self.assert_lease(lease)
        with self.transaction() as db:
            db.execute("UPDATE leases SET state='RELEASED',released_at=? WHERE lease_id=? AND fencing_token=?", (utc_now(), lease["lease_id"], lease["fencing_token"]))

    def put_artifact(self, *, tenant_id: str, content: bytes, kind: str, media_type: str = "application/octet-stream", run_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        content_hash = bytes_digest(content)
        artifact_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM artifacts WHERE tenant_id=? AND kind=? AND content_hash=?", (tenant_id, kind, content_hash)).fetchone()
            if existing:
                value = self._decode(existing) or {}
                value.pop("content", None)
                return value
            db.execute("INSERT INTO artifacts(artifact_id,tenant_id,run_id,kind,content_hash,media_type,content,metadata,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (artifact_id, tenant_id, run_id, kind, content_hash, media_type, content, self._json(metadata or {}), created_at))
        return {"artifact_id": artifact_id, "tenant_id": tenant_id, "run_id": run_id, "kind": kind, "content_hash": content_hash, "media_type": media_type, "size_bytes": len(content), "metadata": dict(metadata or {}), "created_at": created_at}

    def read_artifact(self, artifact_id: str, *, tenant_id: str) -> bytes:
        with self._lock:
            row = self._connection.execute("SELECT content,content_hash FROM artifacts WHERE artifact_id=? AND tenant_id=?", (artifact_id, tenant_id)).fetchone()
        if row is None or bytes_digest(row["content"]) != row["content_hash"]:
            raise StaleStateError("ARTIFACT_CORRUPT", "artifact is missing or its content hash changed")
        return bytes(row["content"])

    def put_evidence(self, *, tenant_id: str, claim: str, evidence_type: str, source: Mapping[str, Any], run_id: str | None = None, confidence: float | None = None, snapshot_sha: str | None = None, expires_at: str | None = None) -> dict[str, Any]:
        evidence_id = str(uuid.uuid4())
        row = {"evidence_id": evidence_id, "tenant_id": tenant_id, "run_id": run_id, "claim": claim, "evidence_type": evidence_type, "source": dict(source), "confidence": confidence, "snapshot_sha": snapshot_sha, "captured_at": utc_now(), "expires_at": expires_at}
        with self.transaction() as db:
            db.execute("INSERT INTO evidence(evidence_id,tenant_id,run_id,claim,evidence_type,source,confidence,snapshot_sha,captured_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (evidence_id, tenant_id, run_id, claim, evidence_type, self._json(source), confidence, snapshot_sha, row["captured_at"], expires_at))
        return row

    def cache_get(self, *, tenant_id: str, layer: str, key_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM cache_entries WHERE tenant_id=? AND cache_layer=? AND key_hash=?", (tenant_id, layer, key_hash)).fetchone()
        if row is None:
            return None
        if row["expires_at"] and row["expires_at"] <= utc_now():
            return None
        return self._decode(row)

    def cache_put(self, *, tenant_id: str, layer: str, key_hash: str, value: Any, provenance: Mapping[str, Any], expires_at: str | None = None) -> dict[str, Any]:
        content_hash = digest(value)
        created_at = utc_now()
        with self.transaction() as db:
            db.execute("INSERT INTO cache_entries(tenant_id,cache_layer,key_hash,content_hash,value,provenance,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,cache_layer,key_hash) DO UPDATE SET content_hash=excluded.content_hash,value=excluded.value,provenance=excluded.provenance,expires_at=excluded.expires_at,created_at=excluded.created_at", (tenant_id, layer, key_hash, content_hash, self._json(value), self._json(provenance), expires_at, created_at))
        return {"tenant_id": tenant_id, "cache_layer": layer, "key_hash": key_hash, "content_hash": content_hash, "provenance": dict(provenance), "expires_at": expires_at, "created_at": created_at}

    def _inc_metric_locked(self, db: sqlite3.Connection, name: str, amount: float = 1) -> None:
        db.execute("INSERT INTO metrics(metric,value) VALUES(?,?) ON CONFLICT(metric) DO UPDATE SET value=value+excluded.value", (name, amount))

    def metrics(self) -> dict[str, float]:
        with self._lock:
            rows = self._connection.execute("SELECT metric,value FROM metrics ORDER BY metric").fetchall()
            return {row["metric"]: float(row["value"]) for row in rows}
