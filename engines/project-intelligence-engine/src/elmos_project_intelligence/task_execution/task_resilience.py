"""Durable, tenant-scoped idempotency and recovery for campaign tasks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
import sqlite3
import stat
import threading
from typing import Any

from ..canonical import canonical_digest, canonical_json, canonical_value
from ..contracts import require_identifier


class DurableTaskError(RuntimeError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_attempts (
 tenant_id TEXT NOT NULL,
 project_id TEXT NOT NULL,
 campaign_id TEXT NOT NULL,
 task_id TEXT NOT NULL,
 input_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RUNNING','SUCCEEDED','FAILED','UNKNOWN')),
 result_json TEXT,
 result_digest TEXT,
 checkpoint_json TEXT NOT NULL,
 checkpoint_digest TEXT NOT NULL,
 measured_wall_ms INTEGER NOT NULL CHECK(measured_wall_ms >= 0),
 reported_cost_json TEXT NOT NULL,
 reported_cost_digest TEXT NOT NULL,
 PRIMARY KEY(tenant_id,project_id,campaign_id,task_id),
 CHECK((result_json IS NULL) = (result_digest IS NULL))
) WITHOUT ROWID, STRICT;
CREATE TRIGGER IF NOT EXISTS task_attempts_no_delete BEFORE DELETE ON task_attempts
BEGIN SELECT RAISE(ABORT, 'task attempts are retained'); END;
"""


class ResilientTaskExecutor:
    """Persist task attempts; uncertain work requires explicit reconciliation."""

    def __init__(
        self,
        database_path: Path | str,
        *,
        tenant_id: str,
        project_id: str,
        campaign_id: str,
    ) -> None:
        self.path = Path(database_path)
        if self.path.is_symlink():
            raise DurableTaskError("task database may not be a symlink")
        require_identifier(tenant_id, field_name="tenant_id")
        require_identifier(project_id, field_name="project_id")
        require_identifier(campaign_id, field_name="campaign_id")
        self.scope = (tenant_id, project_id, campaign_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        self._connection = sqlite3.connect(self.path)
        if not existed:
            os.chmod(self.path, 0o600)
        metadata = self.path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1:
            self._connection.close()
            raise DurableTaskError("task database must be a private single-link regular file")
        self._connection.executescript(_SCHEMA)
        self._lock = threading.RLock()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ResilientTaskExecutor":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _document(value: Mapping[str, Any], label: str) -> tuple[str, str]:
        if not isinstance(value, Mapping):
            raise TypeError(f"{label} must be an object")
        normalized = canonical_value(dict(value))
        return canonical_json(normalized), canonical_digest(normalized)

    def _row(self, task_id: str) -> sqlite3.Row | None:
        self._connection.row_factory = sqlite3.Row
        return self._connection.execute(
            "SELECT * FROM task_attempts WHERE tenant_id=? AND project_id=? AND campaign_id=? AND task_id=?",
            (*self.scope, task_id),
        ).fetchone()

    def begin_attempt(self, task_id: str, input_document: Mapping[str, Any]) -> str:
        require_identifier(task_id, field_name="task_id")
        _input_json, input_digest = self._document(input_document, "input_document")
        empty_json, empty_digest = self._document({}, "checkpoint")
        cost_json, cost_digest = self._document(
            {"state": "NOT_RUN", "currency": None, "amount": None}, "cost"
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._row(task_id)
                if row is not None:
                    if row["input_digest"] != input_digest:
                        raise DurableTaskError("task idempotency input digest conflict")
                    self._connection.commit()
                    return str(row["state"])
                self._connection.execute(
                    "INSERT INTO task_attempts VALUES(?,?,?,?,?,'RUNNING',NULL,NULL,?,?,0,?,?)",
                    (*self.scope, task_id, input_digest, empty_json, empty_digest, cost_json, cost_digest),
                )
                self._connection.commit()
                return "CREATED"
            except BaseException:
                self._connection.rollback()
                raise

    def execute_idempotent(
        self,
        task_id: str,
        input_document: Mapping[str, Any],
        operation: Callable[[], Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        existing = self.begin_attempt(task_id, input_document)
        row = self._row(task_id)
        assert row is not None
        if existing == "SUCCEEDED":
            return {
                "task_id": task_id,
                "status": "REPLAYED_FROM_DURABLE_STORE",
                "result": json.loads(row["result_json"]),
                "side_effects_repeated": False,
                "cost_evidence": json.loads(row["reported_cost_json"]),
            }
        if existing == "FAILED":
            return {
                "task_id": task_id,
                "status": "REPLAYED_TERMINAL_FAILURE",
                "result": json.loads(row["result_json"]),
                "side_effects_repeated": False,
                "cost_evidence": json.loads(row["reported_cost_json"]),
            }
        if existing in {"RUNNING", "UNKNOWN"} and row["result_json"] is None:
            return {"task_id": task_id, "status": "RECOVERY_REQUIRED", "side_effects_repeated": False}
        try:
            result = operation()
            result_json, result_digest = self._document(result, "operation result")
        except BaseException:
            with self._connection:
                self._connection.execute(
                    "UPDATE task_attempts SET state='UNKNOWN' WHERE tenant_id=? AND project_id=? AND campaign_id=? AND task_id=?",
                    (*self.scope, task_id),
                )
            raise
        cost_json, cost_digest = self._document(
            {"state": "CALLER_REPORTED_UNVERIFIED", "currency": None, "amount": None}, "cost"
        )
        with self._connection:
            self._connection.execute(
                "UPDATE task_attempts SET state='SUCCEEDED',result_json=?,result_digest=?,reported_cost_json=?,reported_cost_digest=? WHERE tenant_id=? AND project_id=? AND campaign_id=? AND task_id=? AND state='RUNNING'",
                (result_json, result_digest, cost_json, cost_digest, *self.scope, task_id),
            )
        return {
            "task_id": task_id,
            "status": "EXECUTED_FRESH",
            "result": canonical_value(dict(result)),
            "side_effects_repeated": False,
            "cost_evidence": json.loads(cost_json),
        }

    def checkpoint(self, task_id: str, state: Mapping[str, Any]) -> str:
        state_json, state_digest = self._document(state, "checkpoint")
        with self._connection:
            changed = self._connection.execute(
                "UPDATE task_attempts SET checkpoint_json=?,checkpoint_digest=? WHERE tenant_id=? AND project_id=? AND campaign_id=? AND task_id=? AND state IN ('RUNNING','UNKNOWN')",
                (state_json, state_digest, *self.scope, task_id),
            ).rowcount
        if changed != 1:
            raise DurableTaskError("checkpoint requires an active or unknown attempt")
        return state_digest

    def reconcile(
        self,
        task_id: str,
        input_document: Mapping[str, Any],
        *,
        decision: str,
        result: Mapping[str, Any],
        reconciliation_receipt_digest: str,
    ) -> Mapping[str, Any]:
        if decision not in {"SUCCEEDED", "FAILED"}:
            raise ValueError("reconciliation decision is unsupported")
        from ..canonical import validate_digest

        validate_digest(reconciliation_receipt_digest)
        _input_json, input_digest = self._document(input_document, "input_document")
        result_json, result_digest = self._document(result, "reconciled result")
        with self._connection:
            changed = self._connection.execute(
                "UPDATE task_attempts SET state=?,result_json=?,result_digest=? WHERE tenant_id=? AND project_id=? AND campaign_id=? AND task_id=? AND input_digest=? AND state IN ('RUNNING','UNKNOWN')",
                (decision, result_json, result_digest, *self.scope, task_id, input_digest),
            ).rowcount
        if changed != 1:
            raise DurableTaskError("reconciliation target is absent, terminal, or drifted")
        return {
            "task_id": task_id,
            "status": f"RECONCILED_{decision}",
            "result_digest": result_digest,
            "reconciliation_receipt_digest": reconciliation_receipt_digest,
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
