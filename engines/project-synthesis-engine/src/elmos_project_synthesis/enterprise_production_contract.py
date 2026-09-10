"""The Enterprise Production Contract for ELMOS Project Synthesis.

Extends the baseline starter contract with industrial-grade microservice specifications:
1. Transactional Outbox Pattern for reliable event publishing without dual-write inconsistency.
2. Distributed Cache-Aside pattern with TTL jitter and null-object anti-penetration caching.
3. Enterprise rich querying with dynamic pagination, multi-field sorting, and range/predicate filtering.
4. Entity governance with automatic audit columns (created_at, updated_at, created_by) and optimistic locking (version).
5. Comprehensive SRE observability with 3-tier health probes (/health/live, /health/ready, /metrics) and graceful shutdown.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from .models import EntitySpec, RelationSpec, SynthesisRequest

# SRE & Observability constants
HEALTH_LIVE_PATH = "/health/live"
HEALTH_READY_PATH = "/health/ready"
METRICS_PATH = "/metrics"
TRACE_HEADER = "X-Trace-Id"
CORRELATION_HEADER = "X-Correlation-Id"
TENANT_HEADER = "X-Tenant-Id"
NULL_SENTINEL = "__ELMOS_NULL_SENTINEL__"

# Outbox Status
OutboxStatus = Literal["PENDING", "IN_FLIGHT", "PUBLISHED", "FAILED", "DEAD_LETTER"]


@dataclass(frozen=True)
class EnterpriseMiddlewareConfig:
    """Production Redis and Kafka/RabbitMQ middleware configurations."""

    redis_url_env: str = "REDIS_URL"
    redis_default_host: str = "localhost"
    redis_default_port: int = 6379
    redis_pool_size: int = 50
    redis_socket_timeout_seconds: float = 2.0
    null_sentinel: str = NULL_SENTINEL

    broker_type: Literal["kafka", "rabbitmq"] = "kafka"
    kafka_brokers_env: str = "KAFKA_BROKERS"
    kafka_default_brokers: str = "localhost:9092"
    rabbitmq_url_env: str = "RABBITMQ_URL"
    rabbitmq_default_url: str = "amqp://guest:guest@localhost:5672/"

    enable_w3c_trace_context: bool = True
    outbox_poll_interval_ms: int = 1000
    outbox_batch_size: int = 50


@dataclass(frozen=True)
class SagaStep:
    """A discrete forward action paired with an idempotent compensation action."""

    step_id: str
    name: str
    action_endpoint: str
    compensation_endpoint: str
    timeout_seconds: int = 30


@dataclass(frozen=True)
class SagaDefinition:
    """Specification of a multi-microservice distributed Saga workflow."""

    saga_id: str
    name: str
    steps: tuple[SagaStep, ...]


@dataclass(frozen=True)
class SagaExecutionRecord:
    """State record of an executing Saga instance with compensations."""

    execution_id: str
    saga_id: str
    tenant_id: str
    current_step: int
    status: Literal["PENDING", "RUNNING", "COMPLETED", "COMPENSATING", "COMPENSATED", "FAILED"]
    payload: dict[str, Any]
    error: str | None = None
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())


@dataclass(frozen=True)
class OutboxEvent:
    """Canonical domain event record for the Transactional Outbox Pattern."""

    event_id: str
    tenant_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    status: OutboxStatus = "PENDING"
    retry_count: int = 0
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    published_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "status": self.status,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "published_at": self.published_at,
        }


@dataclass(frozen=True)
class CacheConfig:
    """Configuration for Distributed Cache-Aside layer."""

    default_ttl_seconds: int = 300
    jitter_seconds: int = 30
    null_object_ttl_seconds: int = 30  # Anti-penetration for missing keys
    key_prefix: str = "elmos:cache"

    def compute_key(self, tenant_id: str, entity_name: str, entity_id: str) -> str:
        return f"{self.key_prefix}:{tenant_id}:{entity_name}:{entity_id}"

    def compute_query_key(self, tenant_id: str, entity_name: str, query_params: dict[str, Any]) -> str:
        serialized = json.dumps(query_params, sort_keys=True)
        query_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        return f"{self.key_prefix}:{tenant_id}:{entity_name}:query:{query_hash}"


@dataclass(frozen=True)
class PaginationSpec:
    """Standard dynamic pagination parameter specification."""

    default_page: int = 1
    default_page_size: int = 20
    max_page_size: int = 100


@dataclass(frozen=True)
class EnterpriseEntitySql:
    """Generated enterprise SQL supporting outbox, audit columns, 1:N relations, and optimistic locking."""

    entity: str
    plural: str
    table_name: str
    outbox_table_name: str
    outbox_ddl: str
    insert_outbox_sql: str
    poll_outbox_sql: str
    mark_outbox_published_sql: str
    paginated_list_sql: str
    count_sql: str
    optimistic_update_sql: str
    foreign_key_ddls: tuple[str, ...] = ()
    foreign_key_indexes: tuple[str, ...] = ()
    cascade_delete_sqls: tuple[str, ...] = ()


def enterprise_entity_sql(
    entity: EntitySpec,
    *,
    placeholder: str = "%s",
    is_sqlite: bool = False,
    is_mysql: bool = False,
    relations: tuple[RelationSpec, ...] = (),
) -> EnterpriseEntitySql:
    """Generate SQL expressions for Outbox, Pagination, Optimistic Locking, and 1:N Relations."""
    if is_mysql:
        table_name = f"`{entity.plural}`"
        outbox_table = "`outbox_events`"
        quote = "`"
    elif is_sqlite:
        table_name = f'"{entity.plural}"'
        outbox_table = '"outbox_events"'
        quote = '"'
    else:
        table_name = f'"app"."{entity.plural}"'
        outbox_table = '"app"."outbox_events"'
        quote = '"'

    p = placeholder

    # Outbox table DDL
    if is_mysql:
        outbox_ddl = f"""
        CREATE TABLE IF NOT EXISTS {outbox_table} (
            `event_id` VARCHAR(64) PRIMARY KEY,
            `tenant_id` VARCHAR(64) NOT NULL,
            `aggregate_type` VARCHAR(64) NOT NULL,
            `aggregate_id` VARCHAR(64) NOT NULL,
            `event_type` VARCHAR(64) NOT NULL,
            `payload` JSON NOT NULL,
            `status` VARCHAR(32) NOT NULL DEFAULT 'PENDING',
            `retry_count` INT NOT NULL DEFAULT 0,
            `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `published_at` TIMESTAMP NULL,
            INDEX `idx_outbox_status` (`tenant_id`, `status`, `created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """.strip()
    elif is_sqlite:
        outbox_ddl = f"""
        CREATE TABLE IF NOT EXISTS {outbox_table} (
            "event_id" TEXT PRIMARY KEY,
            "tenant_id" TEXT NOT NULL,
            "aggregate_type" TEXT NOT NULL,
            "aggregate_id" TEXT NOT NULL,
            "event_type" TEXT NOT NULL,
            "payload" TEXT NOT NULL,
            "status" TEXT NOT NULL DEFAULT 'PENDING',
            "retry_count" INTEGER NOT NULL DEFAULT 0,
            "created_at" TEXT NOT NULL,
            "published_at" TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_outbox_status ON {outbox_table} ("tenant_id", "status", "created_at");
        """.strip()
    else:
        outbox_ddl = f"""
        CREATE TABLE IF NOT EXISTS {outbox_table} (
            "event_id" VARCHAR(64) PRIMARY KEY,
            "tenant_id" VARCHAR(64) NOT NULL,
            "aggregate_type" VARCHAR(64) NOT NULL,
            "aggregate_id" VARCHAR(64) NOT NULL,
            "event_type" VARCHAR(64) NOT NULL,
            "payload" JSONB NOT NULL,
            "status" VARCHAR(32) NOT NULL DEFAULT 'PENDING',
            "retry_count" INT NOT NULL DEFAULT 0,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            "published_at" TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_outbox_status ON {outbox_table} ("tenant_id", "status", "created_at");
        """.strip()

    insert_outbox_sql = (
        f"INSERT INTO {outbox_table} ({quote}event_id{quote}, {quote}tenant_id{quote}, "
        f"{quote}aggregate_type{quote}, {quote}aggregate_id{quote}, {quote}event_type{quote}, "
        f"{quote}payload{quote}, {quote}status{quote}, {quote}created_at{quote}) "
        f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 'PENDING', {p})"
    )

    poll_outbox_sql = (
        f"SELECT {quote}event_id{quote}, {quote}tenant_id{quote}, {quote}aggregate_type{quote}, "
        f"{quote}aggregate_id{quote}, {quote}event_type{quote}, {quote}payload{quote}, "
        f"{quote}status{quote}, {quote}retry_count{quote} "
        f"FROM {outbox_table} "
        f"WHERE {quote}status{quote} = 'PENDING' "
        f"ORDER BY {quote}created_at{quote} ASC "
        f"LIMIT 50"
    )

    mark_outbox_published_sql = (
        f"UPDATE {outbox_table} "
        f"SET {quote}status{quote} = 'PUBLISHED', {quote}published_at{quote} = {p} "
        f"WHERE {quote}event_id{quote} = {p}"
    )

    # Rich pagination SQL with LIMIT and OFFSET
    paginated_list_sql = (
        f"SELECT * FROM {table_name} "
        f"WHERE {quote}tenant_id{quote} = {p} AND {quote}is_deleted{quote} = FALSE "
        f"ORDER BY {quote}created_at{quote} DESC "
        f"LIMIT {p} OFFSET {p}"
    )

    count_sql = (
        f"SELECT COUNT(*) FROM {table_name} "
        f"WHERE {quote}tenant_id{quote} = {p} AND {quote}is_deleted{quote} = FALSE"
    )

    # Optimistic locking update (Compare-And-Swap on version)
    optimistic_update_sql = (
        f"UPDATE {table_name} "
        f"SET {quote}version{quote} = {quote}version{quote} + 1, {quote}updated_at{quote} = {p} "
        f"WHERE {quote}tenant_id{quote} = {p} AND {quote}id{quote} = {p} AND {quote}version{quote} = {p}"
    )

    # 1:N Foreign key DDLs and cascading statements
    fk_ddls: list[str] = []
    fk_indexes: list[str] = []
    cascade_deletes: list[str] = []

    for rel in relations:
        # If this entity is the child in many-to-one or one-to-many
        if rel.target == entity.singular and rel.kind == "one-to-many":
            fk_col = rel.target_field or f"{rel.source}_id"
            parent_table = f"`{rel.source}s`" if is_mysql else (f'"{rel.source}s"' if is_sqlite else f'"app"."{rel.source}s"')
            fk_ddl = (
                f"ALTER TABLE {table_name} ADD CONSTRAINT {quote}fk_{entity.singular}_{rel.source}{quote} "
                f"FOREIGN KEY ({quote}{fk_col}{quote}) REFERENCES {parent_table}({quote}id{quote}) ON DELETE CASCADE;"
            )
            fk_idx = f"CREATE INDEX IF NOT EXISTS {quote}idx_{entity.singular}_{fk_col}{quote} ON {table_name} ({quote}tenant_id{quote}, {quote}{fk_col}{quote});"
            fk_ddls.append(fk_ddl)
            fk_indexes.append(fk_idx)
        elif rel.source == entity.singular and rel.kind == "one-to-many":
            # This entity is the parent, cascade delete on children
            child_table = f"`{rel.target}s`" if is_mysql else (f'"{rel.target}s"' if is_sqlite else f'"app"."{rel.target}s"')
            fk_col = rel.target_field or f"{entity.singular}_id"
            cascade_sql = f"DELETE FROM {child_table} WHERE {quote}tenant_id{quote} = {p} AND {quote}{fk_col}{quote} = {p}"
            cascade_deletes.append(cascade_sql)

    return EnterpriseEntitySql(
        entity=entity.singular,
        plural=entity.plural,
        table_name=table_name,
        outbox_table_name=outbox_table,
        outbox_ddl=outbox_ddl,
        insert_outbox_sql=insert_outbox_sql,
        poll_outbox_sql=poll_outbox_sql,
        mark_outbox_published_sql=mark_outbox_published_sql,
        paginated_list_sql=paginated_list_sql,
        count_sql=count_sql,
        optimistic_update_sql=optimistic_update_sql,
        foreign_key_ddls=tuple(fk_ddls),
        foreign_key_indexes=tuple(fk_indexes),
        cascade_delete_sqls=tuple(cascade_deletes),
    )

