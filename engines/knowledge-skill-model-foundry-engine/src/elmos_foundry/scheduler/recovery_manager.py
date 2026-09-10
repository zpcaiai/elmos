from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class JournalEntry:
    entry_id: int
    graph_id: str
    task_id: str
    event_type: str
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class RecoveryJournalManager:
    """Manages write-ahead journal entries and crash-recovery state reconstruction."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._persistent_conn = sqlite3.connect(self.db_path, check_same_thread=False) if self.db_path == ":memory:" else None
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
                    CREATE TABLE IF NOT EXISTS scheduler_journal (
                        entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        graph_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_graph ON scheduler_journal (graph_id, timestamp ASC);")
                conn.commit()
            finally:
                self._close_conn(conn)

    def append_event(self, graph_id: str, task_id: str, event_type: str, payload: Dict[str, Any]) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("""
                    INSERT INTO scheduler_journal (graph_id, task_id, event_type, payload_json, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (graph_id, task_id, event_type, json.dumps(payload), time.time()))
                conn.commit()
                return cur.lastrowid or 0
            finally:
                self._close_conn(conn)

    def reconstruct_state(self, graph_id: str, target_time: Optional[float] = None) -> Dict[str, Dict[str, Any]]:
        """Replay journal events to reconstruct task graph state up to target_time."""
        with self._lock:
            conn = self._get_conn()
            try:
                if target_time is not None:
                    cur = conn.execute("""
                        SELECT task_id, event_type, payload_json, timestamp
                        FROM scheduler_journal
                        WHERE graph_id = ? AND timestamp <= ?
                        ORDER BY entry_id ASC
                    """, (graph_id, target_time))
                else:
                    cur = conn.execute("""
                        SELECT task_id, event_type, payload_json, timestamp
                        FROM scheduler_journal
                        WHERE graph_id = ?
                        ORDER BY entry_id ASC
                    """, (graph_id,))

                tasks: Dict[str, Dict[str, Any]] = {}
                for row in cur.fetchall():
                    tid = row["task_id"]
                    etype = row["event_type"]
                    data = json.loads(row["payload_json"])

                    if tid not in tasks:
                        tasks[tid] = {
                            "task_id": tid,
                            "state": "PENDING",
                            "history": [],
                        }

                    tasks[tid]["history"].append({"event": etype, "timestamp": row["timestamp"]})

                    if etype == "TASK_SCHEDULED":
                        tasks[tid]["state"] = "SCHEDULED"
                    elif etype == "TASK_RUNNING":
                        tasks[tid]["state"] = "RUNNING"
                        tasks[tid]["worker_id"] = data.get("worker_id")
                    elif etype == "TASK_COMPLETED":
                        tasks[tid]["state"] = "COMPLETED"
                        tasks[tid]["result"] = data.get("result")
                    elif etype == "TASK_FAILED":
                        tasks[tid]["state"] = "FAILED"
                        tasks[tid]["error"] = data.get("error")
                    elif etype == "TASK_COMPENSATED":
                        tasks[tid]["state"] = "COMPENSATED"

                return tasks
            finally:
                self._close_conn(conn)

    def prune_journal(self, before_time: float) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("DELETE FROM scheduler_journal WHERE timestamp < ?", (before_time,))
                conn.commit()
                return cur.rowcount
            finally:
                self._close_conn(conn)
