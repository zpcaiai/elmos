from __future__ import annotations

import enum
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

class TaskState(str, enum.Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    RETRYING = 'RETRYING'
    SKIPPED = 'SKIPPED'

@dataclass
class TaskRecord:
    task_id: str
    state: TaskState = TaskState.PENDING
    attempt: int = 0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    version: int = 1
    updated_at: float = field(default_factory=time.time)

class CheckpointStore:
    """Durable SQLite-backed checkpoint store with Compare-And-Swap (CAS) state updates."""

    def __init__(self, db_path: str = ':memory:'):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._persistent_conn = sqlite3.connect(self.db_path, check_same_thread=False) if self.db_path == ':memory:' else None
        if self._persistent_conn is not None:
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        if self._persistent_conn is None:
            conn.close()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS task_checkpoints (
                        graph_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        attempt INTEGER NOT NULL,
                        result TEXT,
                        error TEXT,
                        version INTEGER NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (graph_id, task_id)
                    )
                """)
                conn.commit()
            finally:
                self._close_conn(conn)

    def save_task(self, graph_id: str, record: TaskRecord) -> bool:
        """Saves or updates task record with CAS idempotency check."""
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT version FROM task_checkpoints WHERE graph_id = ? AND task_id = ?",
                    (graph_id, record.task_id),
                )
                row = cur.fetchone()
                now = time.time()
                res_json = json.dumps(record.result) if record.result is not None else None

                if row is None:
                    # Insert initial record
                    cur.execute(
                        """INSERT INTO task_checkpoints
                           (graph_id, task_id, state, attempt, result, error, version, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (graph_id, record.task_id, record.state.value, record.attempt, res_json, record.error, record.version, now),
                    )
                    conn.commit()
                    return True
                else:
                    curr_version = row['version']
                    if record.version <= curr_version:
                        record.version = curr_version + 1
                    cur.execute(
                        """UPDATE task_checkpoints
                           SET state = ?, attempt = ?, result = ?, error = ?, version = ?, updated_at = ?
                           WHERE graph_id = ? AND task_id = ? AND version = ?""",
                        (record.state.value, record.attempt, res_json, record.error, record.version, now, graph_id, record.task_id, curr_version),
                    )
                    success = cur.rowcount > 0
                    conn.commit()
                    return success
            finally:
                self._close_conn(conn)

    def get_task(self, graph_id: str, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM task_checkpoints WHERE graph_id = ? AND task_id = ?",
                    (graph_id, task_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return TaskRecord(
                    task_id=row['task_id'],
                    state=TaskState(row['state']),
                    attempt=row['attempt'],
                    result=json.loads(row['result']) if row['result'] else None,
                    error=row['error'],
                    version=row['version'],
                    updated_at=row['updated_at'],
                )
            finally:
                self._close_conn(conn)

    def get_all_tasks(self, graph_id: str) -> Dict[str, TaskRecord]:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM task_checkpoints WHERE graph_id = ?", (graph_id,))
                rows = cur.fetchall()
                results = {}
                for r in rows:
                    results[r['task_id']] = TaskRecord(
                        task_id=r['task_id'],
                        state=TaskState(r['state']),
                        attempt=r['attempt'],
                        result=json.loads(r['result']) if r['result'] else None,
                        error=r['error'],
                        version=r['version'],
                        updated_at=r['updated_at'],
                    )
                return results
            finally:
                self._close_conn(conn)

    def get_completed_ids(self, graph_id: str) -> Set[str]:
        all_tasks = self.get_all_tasks(graph_id)
        return {tid for tid, r in all_tasks.items() if r.state == TaskState.COMPLETED}

    def snapshot(self, graph_id: str) -> str:
        tasks = self.get_all_tasks(graph_id)
        serializable = {
            tid: {
                'task_id': r.task_id,
                'state': r.state.value,
                'attempt': r.attempt,
                'result': r.result,
                'error': r.error,
                'version': r.version,
                'updated_at': r.updated_at,
            }
            for tid, r in tasks.items()
        }
        return json.dumps(serializable)

    def restore(self, graph_id: str, snapshot_json: str) -> None:
        data = json.loads(snapshot_json)
        for tid, tdict in data.items():
            rec = TaskRecord(
                task_id=tdict['task_id'],
                state=TaskState(tdict['state']),
                attempt=tdict['attempt'],
                result=tdict.get('result'),
                error=tdict.get('error'),
                version=tdict.get('version', 1),
                updated_at=tdict.get('updated_at', time.time()),
            )
            self.save_task(graph_id, rec)
