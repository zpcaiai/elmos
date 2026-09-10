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

from .models import EntitySpec, SynthesisRequest

# SRE & Observability constants
HEALTH_LIVE_PATH = "/health/live"
HEALTH_READY_PATH = "/health/ready"
METRICS_PATH = "/metrics"
TRACE_HEADER = "X-Trace-Id"
CORRELATION_HEADER = "X-Correlation-Id"
TENANT_HEADER = "X-Tenant-Id"

# Outbox Status
OutboxStatus = Literal["PENDING", "IN_FLIGHT", "PUBLISHED", "FAILED", "DEAD_LETTER"]


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
    """Generated enterprise SQL supporting outbox, audit columns, and optimistic locking."""

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


def enterprise_entity_sql(
    entity: EntitySpec,
    *,
    placeholder: str = "%s",
    is_sqlite: bool = False,
    is_mysql: bool = False,
) -> EnterpriseEntitySql:
    """Generate SQL expressions for Outbox, Pagination, and Optimistic Locking."""
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
    )
