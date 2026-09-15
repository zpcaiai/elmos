"""Tests for PostgresConnectionPool and OutboxDispatcher."""

from __future__ import annotations

import json
import sqlite3
import time
from unittest.mock import MagicMock

import pytest

from elmos_proof_harness.connection_pool import (
    PoolError,
    PoolExhaustedError,
    PostgresConnectionPool,
)
from elmos_proof_harness.outbox import OutboxDispatcher, OutboxMessage
from elmos_proof_harness.contracts import SecurityContext
from elmos_proof_harness.store import SQLiteStore


# ---- Connection Pool Tests ----


class FakeRawConnection:
    def __init__(self, should_fail_ping: bool = False) -> None:
        self.should_fail_ping = should_fail_ping
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.should_fail_ping)

    def close(self) -> None:
        self.closed = True


class FakeCursor:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    def execute(self, query: str) -> None:
        if self.fail:
            raise RuntimeError("Connection broken")

    def fetchone(self) -> tuple[int]:
        return (1,)

    def close(self) -> None:
        pass


def test_pool_warmup_and_acquire() -> None:
    created = 0

    def connect() -> FakeRawConnection:
        nonlocal created
        created += 1
        return FakeRawConnection()

    pool = PostgresConnectionPool(connect, min_size=2, max_size=4)
    assert created == 2
    metrics = pool.metrics()
    assert metrics.total_connections == 2
    assert metrics.available_connections == 2

    # Borrow connection
    with pool.acquire() as conn:
        assert isinstance(conn, FakeRawConnection)
        m = pool.metrics()
        assert m.active_connections == 1
        assert m.available_connections == 1

    # Returned to pool
    m2 = pool.metrics()
    assert m2.active_connections == 0
    assert m2.available_connections == 2
    pool.close()


def test_pool_exhaustion_timeout() -> None:
    def connect() -> FakeRawConnection:
        return FakeRawConnection()

    pool = PostgresConnectionPool(connect, min_size=1, max_size=1, timeout_seconds=0.1)
    with pool.acquire():
        with pytest.raises(PoolExhaustedError):
            with pool.acquire(timeout=0.05):
                pass
    pool.close()


def test_pool_unhealthy_reconnect() -> None:
    attempts = 0

    def connect() -> FakeRawConnection:
        nonlocal attempts
        attempts += 1
        # First one fails ping, second succeeds
        return FakeRawConnection(should_fail_ping=(attempts == 1))

    pool = PostgresConnectionPool(connect, min_size=1, max_size=2, ping_on_borrow=True)
    with pool.acquire() as conn:
        assert isinstance(conn, FakeRawConnection)
        assert conn.should_fail_ping is False

    metrics = pool.metrics()
    assert metrics.failed_health_checks >= 1
    pool.close()


# ---- Outbox Dispatcher Tests ----


def test_outbox_dispatch_lifecycle(tmp_path: pytest.TempPathFactory) -> None:
    db_file = str(tmp_path) + "/outbox_test.db"
    store = SQLiteStore(db_file)

    ctx = SecurityContext(
        tenant_id="tenant-acme",
        project_id="proj-commerce",
        actor_id="actor-system",
        run_id="run-outbox-01",
        execution_epoch=1,
        fencing_generation=1,
    )

    # Initialize scope in store
    store.register_scope(ctx)

    # Directly insert an outbox event
    payload = {"order_id": "ord-12345", "amount": 99.9}
    payload_str = json.dumps(payload)
    with store.transaction(ctx) as cursor:
        cursor.execute(
            "INSERT INTO outbox_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.tenant_id,
                ctx.project_id,
                "evt-outbox-001",
                "order.created",
                "ord-12345",
                payload_str,
                "sha256-mock",
                "2026-09-15T12:00:00Z",
            ),
        )

    dispatcher = OutboxDispatcher(store, ctx)

    # Check pending
    pending = dispatcher.fetch_pending()
    assert len(pending) == 1
    assert pending[0].event_id == "evt-outbox-001"
    assert pending[0].payload["order_id"] == "ord-12345"

    received: list[OutboxMessage] = []

    def order_handler(msg: OutboxMessage) -> tuple[bool, str | None]:
        received.append(msg)
        return True, "delivered successfully"

    dispatcher.register_handler("order.created", order_handler)

    # Dispatch batch
    dispatched = dispatcher.dispatch_batch()
    assert dispatched == 1
    assert len(received) == 1
    assert received[0].event_id == "evt-outbox-001"

    # Pending should now be 0
    pending_after = dispatcher.fetch_pending()
    assert len(pending_after) == 0


def test_outbox_dispatch_dead_letter(tmp_path: pytest.TempPathFactory) -> None:
    db_file = str(tmp_path) + "/outbox_dlq.db"
    store = SQLiteStore(db_file)

    ctx = SecurityContext(
        tenant_id="tenant-acme",
        project_id="proj-dlq",
        actor_id="actor-system",
        run_id="run-outbox-dlq",
        execution_epoch=1,
        fencing_generation=1,
    )
    store.register_scope(ctx)

    with store.transaction(ctx) as cursor:
        cursor.execute(
            "INSERT INTO outbox_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.tenant_id,
                ctx.project_id,
                "evt-failing-001",
                "payment.failed",
                "pay-001",
                "{}",
                "sha-failing",
                "2026-09-15T12:05:00Z",
            ),
        )

    dispatcher = OutboxDispatcher(store, ctx)

    def failing_handler(msg: OutboxMessage) -> tuple[bool, str | None]:
        return False, "Downstream service unavailable"

    dispatcher.register_handler("payment.failed", failing_handler)

    dispatched = dispatcher.dispatch_batch(max_attempts=2)
    assert dispatched == 1

    # Should no longer be pending because state is DEAD_LETTER
    assert len(dispatcher.fetch_pending()) == 0

    # Verify outbox_deliveries has DEAD_LETTER
    with store.transaction(ctx) as cur:
        cur.execute(
            "SELECT state FROM outbox_deliveries WHERE tenant_id=? AND project_id=? AND event_id=?",
            (ctx.tenant_id, ctx.project_id, "evt-failing-001"),
        )
        row = cur.fetchone()
        assert row is not None
        assert row["state"] == "DEAD_LETTER"


def test_outbox_worker_daemon(tmp_path: pytest.TempPathFactory) -> None:
    db_file = str(tmp_path) + "/outbox_worker.db"
    store = SQLiteStore(db_file)
    ctx = SecurityContext("tenant-acme", "proj-worker", "actor-system")
    store.register_scope(ctx)

    dispatcher = OutboxDispatcher(store, ctx)
    dispatched_events: list[str] = []

    def handler(msg: OutboxMessage) -> tuple[bool, str | None]:
        dispatched_events.append(msg.event_id)
        return True, "ok"

    dispatcher.register_handler("worker.test", handler)
    dispatcher.start_worker(poll_interval_seconds=0.05, batch_size=10)

    # Insert event while worker is running
    with store.transaction(ctx) as cursor:
        cursor.execute(
            "INSERT INTO outbox_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ctx.tenant_id,
                ctx.project_id,
                "evt-async-001",
                "worker.test",
                "agg-1",
                "{\"status\": \"queued\"}",
                "sha-async",
                "2026-09-15T12:10:00Z",
            ),
        )

    # Wait up to 1 second for worker to process
    start_time = time.monotonic()
    while time.monotonic() - start_time < 1.0:
        if "evt-async-001" in dispatched_events:
            break
        time.sleep(0.05)

    dispatcher.stop_worker(timeout=2.0)
    assert "evt-async-001" in dispatched_events

