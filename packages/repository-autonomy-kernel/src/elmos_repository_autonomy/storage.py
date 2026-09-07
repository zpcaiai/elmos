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
CREATE TABLE IF NOT EXISTS external_operations (
  operation_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL,
  run_id TEXT, capability TEXT NOT NULL, adapter_id TEXT NOT NULL, adapter_version TEXT NOT NULL,
  provider_instance TEXT NOT NULL, region TEXT NOT NULL, native_resource_id TEXT NOT NULL,
  action TEXT NOT NULL, state TEXT NOT NULL, side_effects INTEGER NOT NULL,
  idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, request_metadata TEXT NOT NULL,
  authority_hash TEXT, result TEXT, error TEXT, unknown_outcome INTEGER NOT NULL DEFAULT 0,
  compensation_token TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, capability, adapter_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS external_receipts (
  receipt_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
  operation_id TEXT NOT NULL REFERENCES external_operations(operation_id) ON DELETE CASCADE,
  receipt_type TEXT NOT NULL, status TEXT NOT NULL, producer_id TEXT NOT NULL,
  verifier_id TEXT, evidence_class TEXT NOT NULL, raw_evidence TEXT NOT NULL,
  content_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox_events (
  event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, operation_id TEXT,
  topic TEXT NOT NULL, ordering_key TEXT NOT NULL, event_type TEXT NOT NULL,
  payload TEXT NOT NULL, payload_hash TEXT NOT NULL, state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0, idempotency_key TEXT NOT NULL,
  available_at TEXT NOT NULL, created_at TEXT NOT NULL, published_at TEXT,
  UNIQUE(tenant_id, topic, idempotency_key)
);
CREATE TABLE IF NOT EXISTS outbox_receipts (
  receipt_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
  event_id TEXT NOT NULL REFERENCES outbox_events(event_id) ON DELETE CASCADE,
  status TEXT NOT NULL, producer_id TEXT NOT NULL, verifier_id TEXT,
  evidence_class TEXT NOT NULL, raw_evidence TEXT NOT NULL,
  content_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox_events (
  tenant_id TEXT NOT NULL, consumer_id TEXT NOT NULL, event_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, ordering_key TEXT NOT NULL, state TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0, side_effects INTEGER NOT NULL,
  result TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, consumer_id, event_id)
);
CREATE TABLE IF NOT EXISTS secret_leases (
  lease_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, broker_id TEXT NOT NULL,
  secret_ref TEXT NOT NULL, scope_hash TEXT NOT NULL, state TEXT NOT NULL,
  native_lease_id TEXT, evidence_class TEXT NOT NULL, expires_at TEXT NOT NULL,
  receipt_hash TEXT NOT NULL, revoke_receipt_hash TEXT, created_at TEXT NOT NULL, revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS certification_evidence (
  evidence_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, case_id TEXT NOT NULL,
  capability TEXT NOT NULL, level TEXT NOT NULL, status TEXT NOT NULL,
  evidence_class TEXT NOT NULL, source_kind TEXT NOT NULL, producer_id TEXT NOT NULL,
  verifier_id TEXT, independent INTEGER NOT NULL, payload TEXT NOT NULL,
  signed_document TEXT NOT NULL, signature TEXT, key_id TEXT,
  content_hash TEXT NOT NULL, signature_verified INTEGER NOT NULL,
  captured_at TEXT NOT NULL, expires_at TEXT
);
CREATE TABLE IF NOT EXISTS certification_runs (
  certification_run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
  candidate_digest TEXT NOT NULL, state TEXT NOT NULL, level_results TEXT NOT NULL,
  matrix_result TEXT NOT NULL, p05_issued INTEGER NOT NULL DEFAULT 0,
  decision_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_acceptance (
  acceptance_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, repository_binding_hash TEXT NOT NULL,
  route_id TEXT NOT NULL, candidate_digest TEXT NOT NULL, customer_actor_id TEXT NOT NULL,
  executor_id TEXT NOT NULL, decision TEXT NOT NULL, evidence_ids TEXT NOT NULL,
  signature_verified INTEGER NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, repository_binding_hash, route_id, candidate_digest)
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
        for key in (
            "payload", "state_snapshot", "metadata", "source", "result", "error", "provenance",
            "request_metadata", "raw_evidence", "level_results", "matrix_result", "evidence_ids",
            "signed_document",
        ):
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

    def create_external_operation(
        self, *, tenant_id: str, account_id: str, capability: str, adapter_id: str,
        adapter_version: str, provider_instance: str, region: str, native_resource_id: str,
        action: str, side_effects: bool, idempotency_key: str, request_hash: str,
        request_metadata: Mapping[str, Any], run_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.transaction() as db:
            existing = db.execute(
                "SELECT * FROM external_operations WHERE tenant_id=? AND capability=? AND adapter_id=? AND idempotency_key=?",
                (tenant_id, capability, adapter_id, idempotency_key),
            ).fetchone()
            if existing:
                decoded = self._decode(existing) or {}
                if decoded.get("request_hash") != request_hash:
                    raise ContractError("IDEMPOTENCY_CONFLICT", "idempotency key was reused with a different request")
                return decoded
            operation_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO external_operations(operation_id,tenant_id,account_id,run_id,capability,adapter_id,adapter_version,provider_instance,region,native_resource_id,action,state,side_effects,idempotency_key,request_hash,request_metadata,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    operation_id, tenant_id, account_id, run_id, capability, adapter_id, adapter_version,
                    provider_instance, region, native_resource_id, action, "DRY_RUN", int(side_effects),
                    idempotency_key, request_hash, self._json(request_metadata), now, now,
                ),
            )
            self._inc_metric_locked(db, "external_operations_created")
            row = db.execute("SELECT * FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone()
        return self._decode(row) or {}

    def get_external_operation(self, operation_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM external_operations WHERE operation_id=? AND tenant_id=?", (operation_id, tenant_id)
            ).fetchone()
        return self._decode(row)

    def transition_external_operation(
        self, operation_id: str, *, tenant_id: str, expected_states: set[str], target: str,
        authority_hash: str | None = None, result: Any = None, error: Any = None,
        unknown_outcome: bool | None = None, compensation_token: str | None = None,
    ) -> dict[str, Any]:
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM external_operations WHERE operation_id=? AND tenant_id=?", (operation_id, tenant_id)
            ).fetchone()
            if row is None:
                raise ContractError("EXTERNAL_OPERATION_NOT_FOUND", "operation is not visible in the requested tenant")
            if row["state"] not in expected_states:
                raise StaleStateError(
                    "EXTERNAL_OPERATION_STATE_CONFLICT",
                    f"cannot transition external operation from {row['state']} to {target}",
                )
            values = {
                "state": target,
                "authority_hash": authority_hash if authority_hash is not None else row["authority_hash"],
                "result": self._json(result) if result is not None else row["result"],
                "error": self._json(error) if error is not None else row["error"],
                "unknown_outcome": int(unknown_outcome) if unknown_outcome is not None else row["unknown_outcome"],
                "compensation_token": compensation_token if compensation_token is not None else row["compensation_token"],
                "updated_at": utc_now(),
            }
            db.execute(
                "UPDATE external_operations SET state=?,authority_hash=?,result=?,error=?,unknown_outcome=?,compensation_token=?,updated_at=? WHERE operation_id=? AND tenant_id=?",
                (*values.values(), operation_id, tenant_id),
            )
            self._inc_metric_locked(db, f"external_state_{target.lower()}")
            updated = db.execute("SELECT * FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone()
        return self._decode(updated) or {}

    def record_external_receipt(
        self, *, tenant_id: str, operation_id: str, receipt_type: str, status: str,
        producer_id: str, verifier_id: str | None, evidence_class: str,
        raw_evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.get_external_operation(operation_id, tenant_id=tenant_id) is None:
            raise ContractError("EXTERNAL_OPERATION_NOT_FOUND", "operation is not visible in the requested tenant")
        created_at = utc_now()
        body = {
            "operation_id": operation_id, "receipt_type": receipt_type, "status": status,
            "producer_id": producer_id, "verifier_id": verifier_id,
            "evidence_class": evidence_class, "raw_evidence": dict(raw_evidence), "created_at": created_at,
        }
        row = {"receipt_id": str(uuid.uuid4()), "tenant_id": tenant_id, **body, "content_hash": digest(body)}
        with self.transaction() as db:
            db.execute(
                "INSERT INTO external_receipts(receipt_id,tenant_id,operation_id,receipt_type,status,producer_id,verifier_id,evidence_class,raw_evidence,content_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["receipt_id"], tenant_id, operation_id, receipt_type, status, producer_id, verifier_id,
                    evidence_class, self._json(raw_evidence), row["content_hash"], created_at,
                ),
            )
        return row

    def list_external_receipts(self, operation_id: str, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM external_receipts WHERE operation_id=? AND tenant_id=? ORDER BY created_at,receipt_id",
                (operation_id, tenant_id),
            ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def enqueue_outbox(
        self, *, tenant_id: str, topic: str, ordering_key: str, event_type: str,
        payload: Mapping[str, Any], idempotency_key: str, operation_id: str | None = None,
        available_at: str | None = None,
    ) -> dict[str, Any]:
        created_at = utc_now()
        payload_hash = digest(payload)
        with self.transaction() as db:
            existing = db.execute(
                "SELECT * FROM outbox_events WHERE tenant_id=? AND topic=? AND idempotency_key=?",
                (tenant_id, topic, idempotency_key),
            ).fetchone()
            if existing:
                decoded = self._decode(existing) or {}
                if decoded.get("payload_hash") != payload_hash:
                    raise ContractError("IDEMPOTENCY_CONFLICT", "outbox idempotency key was reused")
                return decoded
            row = {
                "event_id": str(uuid.uuid4()), "tenant_id": tenant_id, "operation_id": operation_id,
                "topic": topic, "ordering_key": ordering_key, "event_type": event_type,
                "payload": dict(payload), "payload_hash": payload_hash, "state": "PENDING", "attempts": 0,
                "idempotency_key": idempotency_key, "available_at": available_at or created_at,
                "created_at": created_at, "published_at": None,
            }
            db.execute(
                "INSERT INTO outbox_events(event_id,tenant_id,operation_id,topic,ordering_key,event_type,payload,payload_hash,state,attempts,idempotency_key,available_at,created_at,published_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["event_id"], tenant_id, operation_id, topic, ordering_key, event_type,
                    self._json(payload), payload_hash, "PENDING", 0, idempotency_key,
                    row["available_at"], created_at, None,
                ),
            )
        return row

    def claim_outbox(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ContractError("INVALID_INPUT", "outbox claim limit must be between 1 and 1000")
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM outbox_events WHERE tenant_id=? AND state IN ('PENDING','RETRY') AND available_at<=? ORDER BY ordering_key,created_at,event_id LIMIT ?",
                (tenant_id, utc_now(), limit),
            ).fetchall()
            ids = [row["event_id"] for row in rows]
            for event_id in ids:
                db.execute("UPDATE outbox_events SET state='PUBLISHING',attempts=attempts+1 WHERE event_id=?", (event_id,))
            claimed = [db.execute("SELECT * FROM outbox_events WHERE event_id=?", (event_id,)).fetchone() for event_id in ids]
        return [self._decode(row) or {} for row in claimed if row is not None]

    def complete_outbox(self, event_id: str, *, tenant_id: str, outcome: str) -> dict[str, Any]:
        if outcome not in {"PUBLISHED", "RETRY", "UNKNOWN", "DEAD_LETTER"}:
            raise ContractError("INVALID_INPUT", "unsupported outbox outcome")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM outbox_events WHERE event_id=? AND tenant_id=?", (event_id, tenant_id)).fetchone()
            if row is None:
                raise ContractError("EVENT_NOT_FOUND", "outbox event is not visible in the requested tenant")
            if row["state"] != "PUBLISHING":
                raise StaleStateError("EVENT_STATE_CONFLICT", "outbox event is not currently claimed")
            published_at = utc_now() if outcome == "PUBLISHED" else None
            db.execute(
                "UPDATE outbox_events SET state=?,published_at=? WHERE event_id=? AND tenant_id=?",
                (outcome, published_at, event_id, tenant_id),
            )
            updated = db.execute("SELECT * FROM outbox_events WHERE event_id=?", (event_id,)).fetchone()
        return self._decode(updated) or {}

    def get_outbox_event(self, event_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM outbox_events WHERE event_id=? AND tenant_id=?", (event_id, tenant_id)
            ).fetchone()
        return self._decode(row)

    def reconcile_outbox(self, event_id: str, *, tenant_id: str, published: bool | None) -> dict[str, Any]:
        """Resolve an unknown publish without treating uncertainty as success."""

        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM outbox_events WHERE event_id=? AND tenant_id=?", (event_id, tenant_id)
            ).fetchone()
            if row is None:
                raise ContractError("EVENT_NOT_FOUND", "outbox event is not visible in the requested tenant")
            if row["state"] != "UNKNOWN":
                raise StaleStateError("EVENT_STATE_CONFLICT", "only unknown events can be reconciled")
            if published is True:
                state, published_at = "PUBLISHED", utc_now()
            elif published is False:
                state, published_at = "RETRY", None
            else:
                state, published_at = "UNKNOWN", None
            db.execute(
                "UPDATE outbox_events SET state=?,published_at=? WHERE event_id=? AND tenant_id=?",
                (state, published_at, event_id, tenant_id),
            )
            updated = db.execute("SELECT * FROM outbox_events WHERE event_id=?", (event_id,)).fetchone()
        return self._decode(updated) or {}

    def record_outbox_receipt(
        self, *, event_id: str, tenant_id: str, status: str, producer_id: str,
        verifier_id: str | None, evidence_class: str, raw_evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.get_outbox_event(event_id, tenant_id=tenant_id) is None:
            raise ContractError("EVENT_NOT_FOUND", "outbox event is not visible in the requested tenant")
        created_at = utc_now()
        body = {
            "event_id": event_id,
            "status": status,
            "producer_id": producer_id,
            "verifier_id": verifier_id,
            "evidence_class": evidence_class,
            "raw_evidence": dict(raw_evidence),
            "created_at": created_at,
        }
        row = {
            "receipt_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **body,
            "content_hash": digest(body),
        }
        with self.transaction() as db:
            db.execute(
                "INSERT INTO outbox_receipts(receipt_id,tenant_id,event_id,status,producer_id,verifier_id,evidence_class,raw_evidence,content_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    row["receipt_id"], tenant_id, event_id, status, producer_id, verifier_id,
                    evidence_class, self._json(raw_evidence), row["content_hash"], created_at,
                ),
            )
        return row

    def list_outbox_receipts(self, event_id: str, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM outbox_receipts WHERE event_id=? AND tenant_id=? ORDER BY created_at,receipt_id",
                (event_id, tenant_id),
            ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def begin_inbox_event(
        self, *, tenant_id: str, consumer_id: str, event_id: str, payload: Mapping[str, Any],
        ordering_key: str, side_effects: bool,
    ) -> dict[str, Any]:
        payload_hash = digest(payload)
        now = utc_now()
        with self.transaction() as db:
            existing = db.execute(
                "SELECT * FROM inbox_events WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (tenant_id, consumer_id, event_id),
            ).fetchone()
            if existing is not None:
                decoded = self._decode(existing) or {}
                if decoded.get("payload_hash") != payload_hash:
                    raise ContractError("EVENT_ID_CONFLICT", "event ID was reused with a different payload")
                if decoded.get("state") in {"PROCESSING", "UNKNOWN"}:
                    raise StaleStateError(
                        "EVENT_RECONCILIATION_REQUIRED",
                        "event is already processing or has an unknown side-effect outcome",
                    )
                if decoded.get("state") == "PROCESSED":
                    return {**decoded, "replayed": True}
                db.execute(
                    "UPDATE inbox_events SET state='PROCESSING',attempts=attempts+1,updated_at=? WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                    (now, tenant_id, consumer_id, event_id),
                )
            else:
                db.execute(
                    "INSERT INTO inbox_events(tenant_id,consumer_id,event_id,payload_hash,ordering_key,state,attempts,side_effects,created_at,updated_at) VALUES(?,?,?,?,?,'PROCESSING',1,?,?,?)",
                    (tenant_id, consumer_id, event_id, payload_hash, ordering_key, int(side_effects), now, now),
                )
            row = db.execute(
                "SELECT * FROM inbox_events WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (tenant_id, consumer_id, event_id),
            ).fetchone()
        return {**(self._decode(row) or {}), "replayed": False}

    def complete_inbox_event(
        self, *, tenant_id: str, consumer_id: str, event_id: str, state: str,
        result: Mapping[str, Any] | None = None, error: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if state not in {"PROCESSED", "RETRY", "UNKNOWN", "DEAD_LETTER"}:
            raise ContractError("INVALID_INPUT", "unsupported inbox outcome")
        with self.transaction() as db:
            current = db.execute(
                "SELECT * FROM inbox_events WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (tenant_id, consumer_id, event_id),
            ).fetchone()
            if current is None:
                raise ContractError("EVENT_NOT_FOUND", "inbox event is not visible in the requested tenant")
            if current["state"] != "PROCESSING":
                raise StaleStateError("EVENT_STATE_CONFLICT", "inbox event is not being processed")
            db.execute(
                "UPDATE inbox_events SET state=?,result=?,error=?,updated_at=? WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (
                    state,
                    self._json(result) if result is not None else None,
                    self._json(error) if error is not None else None,
                    utc_now(),
                    tenant_id,
                    consumer_id,
                    event_id,
                ),
            )
            updated = db.execute(
                "SELECT * FROM inbox_events WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (tenant_id, consumer_id, event_id),
            ).fetchone()
        return self._decode(updated) or {}

    def reconcile_inbox_event(
        self, *, tenant_id: str, consumer_id: str, event_id: str, processed: bool | None,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self.transaction() as db:
            current = db.execute(
                "SELECT * FROM inbox_events WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (tenant_id, consumer_id, event_id),
            ).fetchone()
            if current is None:
                raise ContractError("EVENT_NOT_FOUND", "inbox event is not visible in the requested tenant")
            if current["state"] not in {"UNKNOWN", "PROCESSING"}:
                raise StaleStateError("EVENT_STATE_CONFLICT", "inbox event is not reconcilable")
            state = "PROCESSED" if processed is True else "RETRY" if processed is False else "UNKNOWN"
            db.execute(
                "UPDATE inbox_events SET state=?,result=?,updated_at=? WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (state, self._json({"reconciliation_evidence": dict(evidence)}), utc_now(), tenant_id, consumer_id, event_id),
            )
            updated = db.execute(
                "SELECT * FROM inbox_events WHERE tenant_id=? AND consumer_id=? AND event_id=?",
                (tenant_id, consumer_id, event_id),
            ).fetchone()
        return self._decode(updated) or {}

    def record_secret_lease(
        self, *, tenant_id: str, broker_id: str, secret_ref: str, scope: Mapping[str, Any],
        expires_at: str, receipt_hash: str, native_lease_id: str | None = None,
        evidence_class: str = "LOCAL_ENGINEERING_VALIDATED",
    ) -> dict[str, Any]:
        if any(key.casefold() in {"value", "secret", "token", "password"} for key in scope):
            raise ContractError("SECRET_EXPOSURE", "secret lease scope must contain references, not secret values")
        row = {
            "lease_id": str(uuid.uuid4()), "tenant_id": tenant_id, "broker_id": broker_id,
            "secret_ref": secret_ref, "scope_hash": digest(scope), "state": "ACTIVE",
            "native_lease_id": native_lease_id, "evidence_class": evidence_class,
            "expires_at": expires_at, "receipt_hash": receipt_hash, "revoke_receipt_hash": None,
            "created_at": utc_now(), "revoked_at": None,
        }
        with self.transaction() as db:
            db.execute(
                "INSERT INTO secret_leases(lease_id,tenant_id,broker_id,secret_ref,scope_hash,state,native_lease_id,evidence_class,expires_at,receipt_hash,revoke_receipt_hash,created_at,revoked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(row.values()),
            )
        return row

    def revoke_secret_lease(
        self, lease_id: str, *, tenant_id: str, state: str = "REVOKED",
        revoke_receipt_hash: str | None = None,
    ) -> dict[str, Any]:
        if state not in {"REVOKED", "REVOKE_UNKNOWN"}:
            raise ContractError("INVALID_INPUT", "unsupported secret revoke state")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM secret_leases WHERE lease_id=? AND tenant_id=?", (lease_id, tenant_id)).fetchone()
            if row is None:
                raise ContractError("SECRET_LEASE_NOT_FOUND", "secret lease is not visible in the requested tenant")
            if row["state"] == "REVOKED":
                return self._decode(row) or {}
            revoked_at = row["revoked_at"] or utc_now()
            db.execute(
                "UPDATE secret_leases SET state=?,revoke_receipt_hash=?,revoked_at=? WHERE lease_id=?",
                (state, revoke_receipt_hash or row["revoke_receipt_hash"], revoked_at, lease_id),
            )
            updated = db.execute("SELECT * FROM secret_leases WHERE lease_id=?", (lease_id,)).fetchone()
        return self._decode(updated) or {}

    def record_certification_evidence(self, *, tenant_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        required = (
            "evidence_id", "case_id", "capability", "level", "status", "evidence_class", "source_kind",
            "producer_id", "independent", "content_hash", "signature_verified", "captured_at",
        )
        missing = [key for key in required if key not in record]
        if missing:
            raise ContractError("EVIDENCE_INVALID", f"certification evidence is missing fields: {missing}")
        with self.transaction() as db:
            existing = db.execute(
                "SELECT * FROM certification_evidence WHERE evidence_id=?", (record["evidence_id"],)
            ).fetchone()
            if existing is not None:
                decoded = self._decode(existing) or {}
                if decoded.get("tenant_id") != tenant_id or decoded.get("content_hash") != record["content_hash"]:
                    raise ContractError("EVIDENCE_ID_CONFLICT", "evidence ID was reused with different bytes or tenant")
                return decoded
            db.execute(
                "INSERT INTO certification_evidence(evidence_id,tenant_id,case_id,capability,level,status,evidence_class,source_kind,producer_id,verifier_id,independent,payload,signed_document,signature,key_id,content_hash,signature_verified,captured_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record["evidence_id"], tenant_id, record["case_id"], record["capability"], record["level"],
                    record["status"], record["evidence_class"], record["source_kind"], record["producer_id"],
                    record.get("verifier_id"), int(bool(record["independent"])), self._json(record.get("payload", {})),
                    self._json(record.get("signed_document", {})), record.get("signature"), record.get("key_id"),
                    record["content_hash"], int(bool(record["signature_verified"])), record["captured_at"],
                    record.get("expires_at"),
                ),
            )
        return dict(record)

    def list_certification_evidence(self, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM certification_evidence WHERE tenant_id=? ORDER BY case_id,captured_at,evidence_id", (tenant_id,)
            ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def record_certification_run(
        self, *, tenant_id: str, candidate_digest: str, state: str,
        level_results: Mapping[str, Any], matrix_result: Mapping[str, Any], p05_issued: bool,
    ) -> dict[str, Any]:
        created_at = utc_now()
        body = {
            "candidate_digest": candidate_digest, "state": state, "level_results": dict(level_results),
            "matrix_result": dict(matrix_result), "p05_issued": bool(p05_issued), "created_at": created_at,
        }
        row = {"certification_run_id": str(uuid.uuid4()), "tenant_id": tenant_id, **body, "decision_hash": digest(body)}
        with self.transaction() as db:
            db.execute(
                "INSERT INTO certification_runs(certification_run_id,tenant_id,candidate_digest,state,level_results,matrix_result,p05_issued,decision_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    row["certification_run_id"], tenant_id, candidate_digest, state,
                    self._json(level_results), self._json(matrix_result), int(p05_issued), row["decision_hash"], created_at,
                ),
            )
        return row

    def record_customer_acceptance(
        self, *, tenant_id: str, repository_binding_hash: str, route_id: str, candidate_digest: str,
        customer_actor_id: str, executor_id: str, decision: str, evidence_ids: list[str],
        signature_verified: bool,
    ) -> dict[str, Any]:
        if customer_actor_id == executor_id:
            raise ContractError("SELF_APPROVAL_DENIED", "customer acceptance must be independent from the executor")
        if decision == "ACCEPTED" and (not signature_verified or not evidence_ids):
            raise ContractError("ACCEPTANCE_EVIDENCE_MISSING", "accepted decisions require verified evidence")
        body = {
            "tenant_id": tenant_id,
            "repository_binding_hash": repository_binding_hash, "route_id": route_id,
            "candidate_digest": candidate_digest, "customer_actor_id": customer_actor_id,
            "executor_id": executor_id, "decision": decision, "evidence_ids": list(evidence_ids),
            "signature_verified": bool(signature_verified), "created_at": utc_now(),
        }
        row = {"acceptance_id": str(uuid.uuid4()), **body, "content_hash": digest(body)}
        with self.transaction() as db:
            existing = db.execute(
                "SELECT * FROM customer_acceptance WHERE tenant_id=? AND repository_binding_hash=? AND route_id=? AND candidate_digest=?",
                (tenant_id, repository_binding_hash, route_id, candidate_digest),
            ).fetchone()
            if existing is not None:
                decoded = self._decode(existing) or {}
                same = (
                    decoded.get("customer_actor_id") == customer_actor_id
                    and decoded.get("executor_id") == executor_id
                    and decoded.get("decision") == decision
                    and decoded.get("evidence_ids") == evidence_ids
                    and bool(decoded.get("signature_verified")) == bool(signature_verified)
                )
                if not same:
                    raise ContractError("ACCEPTANCE_CONFLICT", "acceptance key was reused with a different decision")
                return decoded
            db.execute(
                "INSERT INTO customer_acceptance(acceptance_id,tenant_id,repository_binding_hash,route_id,candidate_digest,customer_actor_id,executor_id,decision,evidence_ids,signature_verified,content_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["acceptance_id"], tenant_id, repository_binding_hash, route_id, candidate_digest,
                    customer_actor_id, executor_id, decision, self._json(evidence_ids), int(signature_verified),
                    row["content_hash"], row["created_at"],
                ),
            )
        return row

    def list_customer_acceptances(
        self, *, tenant_id: str, candidate_digest: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM customer_acceptance WHERE tenant_id=?"
        parameters: tuple[Any, ...] = (tenant_id,)
        if candidate_digest is not None:
            query += " AND candidate_digest=?"
            parameters += (candidate_digest,)
        query += " ORDER BY created_at,acceptance_id"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._decode(row) or {} for row in rows]

    def _inc_metric_locked(self, db: sqlite3.Connection, name: str, amount: float = 1) -> None:
        db.execute("INSERT INTO metrics(metric,value) VALUES(?,?) ON CONFLICT(metric) DO UPDATE SET value=value+excluded.value", (name, amount))

    def metrics(self) -> dict[str, float]:
        with self._lock:
            rows = self._connection.execute("SELECT metric,value FROM metrics ORDER BY metric").fetchall()
            return {row["metric"]: float(row["value"]) for row in rows}
