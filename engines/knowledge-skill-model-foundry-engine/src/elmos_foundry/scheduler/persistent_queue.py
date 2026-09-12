from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class QueueMessage:
    msg_id: str
    tenant_id: str
    task_id: str
    payload: Dict[str, Any]
    priority: int = 5  # Higher is higher priority
    attempt: int = 0
    max_retries: int = 3
    lease_owner: Optional[str] = None
    lease_expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)


class PersistentTaskQueue:
    """Industrial durable SQLite/WAL-backed priority task queue with visibility timeouts."""

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
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS persistent_queue (
                        msg_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        priority INTEGER NOT NULL,
                        attempt INTEGER NOT NULL DEFAULT 0,
                        max_retries INTEGER NOT NULL DEFAULT 3,
                        lease_owner TEXT,
                        lease_expires_at REAL NOT NULL DEFAULT 0.0,
                        state TEXT NOT NULL DEFAULT 'READY',
                        created_at REAL NOT NULL
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_poll ON persistent_queue (state, priority DESC, created_at ASC);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_lease ON persistent_queue (lease_expires_at);")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS dead_letter_queue (
                        msg_id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        failed_at REAL NOT NULL
                    );
                """)
                conn.commit()
            finally:
                self._close_conn(conn)

    def enqueue(self, msg_id: str, tenant_id: str, task_id: str, payload: Dict[str, Any], priority: int = 5, max_retries: int = 3) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO persistent_queue (
                        msg_id, tenant_id, task_id, payload_json, priority, max_retries, state, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'READY', ?)
                """, (msg_id, tenant_id, task_id, json.dumps(payload), priority, max_retries, time.time()))
                conn.commit()
                return True
            finally:
                self._close_conn(conn)

    def poll(self, worker_id: str, lease_duration: float = 30.0, limit: int = 1) -> List[QueueMessage]:
        now = time.time()
        results: List[QueueMessage] = []
        with self._lock:
            conn = self._get_conn()
            try:
                # 1. Reclaim expired leases
                conn.execute("""
                    UPDATE persistent_queue
                    SET state = 'READY', lease_owner = NULL, lease_expires_at = 0.0
                    WHERE state = 'LEASED' AND lease_expires_at <= ?
                """, (now,))

                # 2. Acquire available ready tasks
                cursor = conn.execute("""
                    SELECT msg_id, tenant_id, task_id, payload_json, priority, attempt, max_retries, created_at
                    FROM persistent_queue
                    WHERE state = 'READY'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                if not rows:
                    conn.commit()
                    return []

                new_expires = now + lease_duration
                for r in rows:
                    m_id = r["msg_id"]
                    new_attempt = r["attempt"] + 1
                    conn.execute("""
                        UPDATE persistent_queue
                        SET state = 'LEASED', lease_owner = ?, lease_expires_at = ?, attempt = ?
                        WHERE msg_id = ?
                    """, (worker_id, new_expires, new_attempt, m_id))

                    msg = QueueMessage(
                        msg_id=m_id,
                        tenant_id=r["tenant_id"],
                        task_id=r["task_id"],
                        payload=json.loads(r["payload_json"]),
                        priority=r["priority"],
                        attempt=new_attempt,
                        max_retries=r["max_retries"],
                        lease_owner=worker_id,
                        lease_expires_at=new_expires,
                        created_at=r["created_at"],
                    )
                    results.append(msg)

                conn.commit()
                return results
            finally:
                self._close_conn(conn)

    def ack(self, msg_id: str, worker_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("DELETE FROM persistent_queue WHERE msg_id = ? AND lease_owner = ?", (msg_id, worker_id))
                conn.commit()
                return cur.rowcount > 0
            finally:
                self._close_conn(conn)

    def nack(self, msg_id: str, worker_id: str, reason: str = "") -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("""
                    SELECT msg_id, tenant_id, task_id, payload_json, attempt, max_retries
                    FROM persistent_queue
                    WHERE msg_id = ? AND lease_owner = ?
                """, (msg_id, worker_id))
                row = cur.fetchone()
                if not row:
                    return False

                if row["attempt"] >= row["max_retries"]:
                    # Move to Dead Letter Queue
                    conn.execute("""
                        INSERT OR REPLACE INTO dead_letter_queue (
                            msg_id, tenant_id, task_id, payload_json, reason, failed_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (row["msg_id"], row["tenant_id"], row["task_id"], row["payload_json"], reason, time.time()))
                    conn.execute("DELETE FROM persistent_queue WHERE msg_id = ?", (msg_id,))
                else:
                    # Release back to READY
                    conn.execute("""
                        UPDATE persistent_queue
                        SET state = 'READY', lease_owner = NULL, lease_expires_at = 0.0
                        WHERE msg_id = ?
                    """, (msg_id,))

                conn.commit()
                return True
            finally:
                self._close_conn(conn)

    def size(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("SELECT COUNT(*) AS c FROM persistent_queue WHERE state = 'READY'")
                row = cur.fetchone()
                return int(row["c"]) if row else 0
            finally:
                self._close_conn(conn)

    def dlq_size(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute("SELECT COUNT(*) AS c FROM dead_letter_queue")
                row = cur.fetchone()
                return int(row["c"]) if row else 0
            finally:
                self._close_conn(conn)
