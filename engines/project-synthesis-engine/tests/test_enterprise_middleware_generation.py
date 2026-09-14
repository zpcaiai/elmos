"""Unit and integration tests for Enterprise Middleware Generation & Contracts.

Covers:
1. Idempotent Consumer DDL & atomic insertion across PostgreSQL, MySQL, and SQLite.
2. Real SQLite execution of idempotent consumer schema and deduplication persistence.
3. Resilient consumer pipeline integration with real SQLite deduplication.
4. Polyglot enterprise targets generation (Java, Go, TypeScript, C#, Rust) verifying
   outbox tables, cache-aside, and message broker integration.
5. Distributed lock with CAS fencing token sequence and heartbeat daemon.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from elmos_project_synthesis.enterprise_production_target import generate_enterprise_target_files
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.messaging_infrastructure import (
    ConsumedMessage,
    DeadLetterQueueManager,
    DistributedLockHandle,
    ExponentialBackoffWithJitter,
    IdempotentDeduplicationStore,
    LockHeartbeatDaemon,
    MessageDeliveryStatus,
    MockRedisState,
    RedisClusterLockManager,
    ResilientMessageConsumerPipeline,
    idempotent_consumer_ddl,
    idempotent_consumer_insert_sql,
)
from elmos_project_synthesis.models import SynthesisRequest


def test_idempotent_consumer_ddl_dialects():
    pg_ddl = idempotent_consumer_ddl("postgres")
    assert "TIMESTAMPTZ" in pg_ddl
    assert "PRIMARY KEY" in pg_ddl
    assert "idempotent_consumer_log" in pg_ddl

    mysql_ddl = idempotent_consumer_ddl("mysql")
    assert "`idempotent_consumer_log`" in mysql_ddl
    assert "ENGINE=InnoDB" in mysql_ddl

    sqlite_ddl = idempotent_consumer_ddl("sqlite")
    assert '"idempotent_consumer_log"' in sqlite_ddl
    assert "datetime('now')" in sqlite_ddl


def test_idempotent_consumer_insert_sql_dialects():
    pg_sql = idempotent_consumer_insert_sql("postgres", placeholder="%s")
    assert "ON CONFLICT" in pg_sql
    assert "DO NOTHING" in pg_sql

    mysql_sql = idempotent_consumer_insert_sql("mysql", placeholder="%s")
    assert "INSERT IGNORE INTO" in mysql_sql

    sqlite_sql = idempotent_consumer_insert_sql("sqlite", placeholder="?")
    assert "INSERT OR IGNORE INTO" in sqlite_sql


def test_real_sqlite_idempotent_deduplication_store():
    conn = sqlite3.connect(":memory:")
    ddl = idempotent_consumer_ddl("sqlite")
    conn.executescript(ddl)

    store = IdempotentDeduplicationStore(db_connection=conn, dialect="sqlite")

    # Initially not processed
    assert not store.is_processed("orders-group", "msg-001")

    # Mark processed with payload hash
    store.mark_processed("orders-group", "msg-001", payload_sha256="abc123hash")
    assert store.is_processed("orders-group", "msg-001")
    assert not store.is_processed("payments-group", "msg-001")  # Different group

    # Second mark processed does not fail (idempotent ignore)
    store.mark_processed("orders-group", "msg-001", payload_sha256="abc123hash")
    assert store.is_processed("orders-group", "msg-001")

    # Verify rows in database
    cursor = conn.cursor()
    cursor.execute('SELECT "consumer_group", "message_id", "payload_sha256" FROM "idempotent_consumer_log"')
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0] == ("orders-group", "msg-001", "abc123hash")

    conn.close()


def test_resilient_pipeline_with_sqlite_persistent_dedup():
    conn = sqlite3.connect(":memory:")
    conn.executescript(idempotent_consumer_ddl("sqlite"))

    store = IdempotentDeduplicationStore(db_connection=conn, dialect="sqlite")
    dlq = DeadLetterQueueManager()
    retry_policy = ExponentialBackoffWithJitter(base_delay_ms=1.0, max_delay_ms=10.0, max_attempts=3)

    processed_orders = []

    def handler(msg: ConsumedMessage):
        processed_orders.append(msg.payload["order_id"])

    pipeline = ResilientMessageConsumerPipeline("order-worker", handler, store, retry_policy, dlq)

    msg = ConsumedMessage("msg-99", "orders", 0, 10, "ord-key", {"order_id": "ord-777"})

    # First delivery
    status1 = pipeline.process_message(msg)
    assert status1 == MessageDeliveryStatus.ACKNOWLEDGED
    assert processed_orders == ["ord-777"]

    # Duplicate replay -> skipped via SQLite store
    status2 = pipeline.process_message(msg)
    assert status2 == MessageDeliveryStatus.ACKNOWLEDGED
    assert processed_orders == ["ord-777"]  # Still 1 call

    conn.close()


def test_redis_cluster_lock_heartbeat_and_cas_fencing():
    redis = MockRedisState()
    mgr = RedisClusterLockManager(redis)

    handle = mgr.acquire_lock("resource:invoice:888", "worker-node-1", ttl_seconds=2.0)
    assert handle is not None
    assert handle.is_active is True
    assert handle.fencing_token >= 1001

    daemon = LockHeartbeatDaemon(mgr, handle, heartbeat_interval_seconds=0.1)
    daemon.start()

    time.sleep(0.35)
    # Handle should remain active due to heartbeat renewals
    assert handle.is_active is True
    assert not handle.is_expired

    daemon.stop()
    released = mgr.release_lock(handle)
    assert released is True
    assert handle.is_active is False

    # Second acquire should receive strictly higher monotonic fencing token
    handle2 = mgr.acquire_lock("resource:invoice:888", "worker-node-2", ttl_seconds=2.0)
    assert handle2 is not None
    assert handle2.fencing_token > handle.fencing_token
    mgr.release_lock(handle2)


def test_polyglot_enterprise_targets_include_middleware_components():
    draft = create_draft(
        name="enterprise-inventory",
        description="Multi-language inventory service with Kafka and Redis",
        entities=[
            {
                "singular": "inventory",
                "plural": "inventories",
                "fields": [
                    {"name": "sku", "type": "string", "required": True},
                    {"name": "stock", "type": "integer", "required": True},
                ],
            }
        ],
        languages=["python", "java", "go", "typescript", "csharp", "rust"],
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="actor-tester", approved_at="2026-09-12T00:00:00+00:00")
    request = SynthesisRequest.from_mapping(approved)

    # 1. Java: Spring Boot + Kafka + Redis
    java_files = generate_enterprise_target_files(request, language="java")
    assert any("DistributedCacheService.java" in f for f in java_files)
    assert any("OutboxPublisher.java" in f for f in java_files)

    # 2. Go: Gin + go-redis + kafka-go
    go_files = generate_enterprise_target_files(request, language="go")
    assert "cache/cache.go" in go_files
    assert "outbox/outbox.go" in go_files

    # 3. TypeScript: NestJS + ioredis + kafkajs
    ts_files = generate_enterprise_target_files(request, language="typescript")
    assert "src/cache/cache.service.ts" in ts_files
    assert "src/outbox/outbox.service.ts" in ts_files

    # 4. .NET: C# EF Core + StackExchange.Redis + Confluent.Kafka
    dotnet_files = generate_enterprise_target_files(request, language="dotnet")
    assert "Cache/DistributedCacheService.cs" in dotnet_files
    assert "Outbox/OutboxPublisher.cs" in dotnet_files

    # 5. Rust: Axum + deadpool-redis + rdkafka
    rust_files = generate_enterprise_target_files(request, language="rust")
    assert "src/cache.rs" in rust_files
    assert "Cargo.toml" in rust_files
