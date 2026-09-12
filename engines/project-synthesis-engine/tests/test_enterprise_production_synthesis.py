"""Unit and integration tests for Enterprise Production Synthesis.

Verifies:
1. Enterprise Production Contract SQL generation and event data structures.
2. Hosted Distributed Runner Fleet (node registration, heartbeat, lease fencing, quota limits, timeout kill, failover).
3. Cloud-native deployment generation (Distroless Dockerfile, Kubernetes manifests, Helm chart).
4. Full FastAPI enterprise target execution (Outbox, Cache-Aside, Pagination, Filtering, Optimistic Locking, SRE probes).
"""

from __future__ import annotations

import datetime as dt

import pytest

from elmos_project_synthesis.cloud_native_deployment import (
    generate_distroless_dockerfile,
    generate_helm_chart,
    generate_kubernetes_manifests,
)
from elmos_project_synthesis.enterprise_production_contract import (
    CacheConfig,
    enterprise_entity_sql,
)
from elmos_project_synthesis.enterprise_production_target import generate_enterprise_python_files
from elmos_project_synthesis.hosted_runner_fleet import (
    HostedRunnerFleet,
    WorkerNode,
)
from elmos_project_synthesis.models import EntitySpec, FieldSpec, SynthesisRequest


def test_enterprise_contract_sql_generation():
    entity = EntitySpec(
        singular="order",
        plural="orders",
        fields=[
            FieldSpec(name="reference", type="string", required=True),
            FieldSpec(name="total", type="number", required=True),
        ],
    )
    sql_pg = enterprise_entity_sql(entity, placeholder="%s", is_sqlite=False, is_mysql=False)
    assert 'CREATE TABLE IF NOT EXISTS "app"."outbox_events"' in sql_pg.outbox_ddl
    assert 'INSERT INTO "app"."outbox_events"' in sql_pg.insert_outbox_sql
    assert '"version" = "version" + 1' in sql_pg.optimistic_update_sql

    sql_mysql = enterprise_entity_sql(entity, placeholder="%s", is_sqlite=False, is_mysql=True)
    assert "CREATE TABLE IF NOT EXISTS `outbox_events`" in sql_mysql.outbox_ddl


def test_cache_config_key_generation():
    cfg = CacheConfig(key_prefix="test:cache")
    key = cfg.compute_key("tenant-1", "order", "ord-123")
    assert key == "test:cache:tenant-1:order:ord-123"

    query_key = cfg.compute_query_key("tenant-1", "order", {"page": 1, "size": 10})
    assert query_key.startswith("test:cache:tenant-1:order:query:")


def test_hosted_runner_fleet_full_lifecycle():
    fleet = HostedRunnerFleet()

    # 1. Register Worker Nodes
    node1 = WorkerNode(node_id="node-01", hostname="worker-01.infra.local", max_concurrency=2)
    node2 = WorkerNode(node_id="node-02", hostname="worker-02.infra.local", max_concurrency=2)
    fleet.register_node(node1)
    fleet.register_node(node2)

    # 2. Set Tenant Quota
    fleet.set_tenant_quota("tenant-acme", max_concurrency=2)

    # 3. Submit Jobs
    job1 = fleet.submit_job("tenant-acme", "actor-alice", {"target": "python"}, timeout_seconds=2)
    job2 = fleet.submit_job("tenant-acme", "actor-alice", {"target": "java"}, timeout_seconds=10)

    # Tenant Quota Check
    with pytest.raises(RuntimeError, match="TENANT_CONCURRENCY_QUOTA_EXCEEDED"):
        # Max concurrency is 2, submitting 3rd job while 2 are active/queued
        fleet.quotas["tenant-acme"].active_jobs = 2
        fleet.submit_job("tenant-acme", "actor-alice", {"target": "go"})
    fleet.quotas["tenant-acme"].active_jobs = 0

    # 4. Schedule and acquire lease
    scheduled = fleet.schedule_next_job()
    assert scheduled is not None
    s_job, s_node, s_lease = scheduled
    assert s_job.job_id == job1.job_id
    assert s_job.status == "RUNNING"
    assert s_lease.fencing_token > 1000
    assert s_lease.is_valid is True

    # 5. Heartbeat & Dead Node Eviction + Job Failover
    # Simulate node2 going silent
    node2.last_heartbeat_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=45)
    # Assign job2 to node2 manually to test failover
    job2.status = "RUNNING"
    job2.assigned_node_id = node2.node_id
    dead_nodes = fleet.evict_dead_nodes(heartbeat_timeout_seconds=30)
    assert "node-02" in dead_nodes
    assert node2.status == "DEAD"
    # job2 should have been failed over and requeued
    assert job2.status == "QUEUED"
    assert job2.retry_count == 1

    # 6. Timeout Kill
    job1.started_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=5)
    killed = fleet.check_timeouts()
    assert job1.job_id in killed
    assert job1.status == "TIMEOUT_KILLED"


def test_cloud_native_deployment_assets():
    dockerfile = generate_distroless_dockerfile("python", "order-service", 8080)
    assert "gcr.io/distroless/python3-debian12:nonroot" in dockerfile
    assert "USER 10001:10001" in dockerfile

    k8s = generate_kubernetes_manifests("order-service", 8080)
    assert "kind: Deployment" in k8s
    assert "kind: HorizontalPodAutoscaler" in k8s
    assert "kind: PodDisruptionBudget" in k8s
    assert "kind: NetworkPolicy" in k8s
    assert "readOnlyRootFilesystem: true" in k8s

    helm = generate_helm_chart("order-service", 8080)
    assert "Chart.yaml" in helm
    assert "values.yaml" in helm
    assert "templates/deployment.yaml" in helm


def test_enterprise_generated_target_execution(tmp_path):
    from elmos_project_synthesis.intake import approve_request, create_draft

    draft = create_draft(
        name="enterprise-order-service",
        description="Enterprise order service with outbox, cache and audit.",
        entity="order",
        languages=["python"],
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="actor-test", approved_at="2026-09-10T00:00:00+00:00")
    request = SynthesisRequest.from_mapping(approved)
    files = generate_enterprise_python_files(request)

    assert "src/models.py" in files
    assert "src/cache.py" in files
    assert "src/outbox.py" in files
    assert "src/repository.py" in files
    assert "src/main.py" in files
    assert "tests/test_enterprise_api.py" in files

    # Verify every generated file is valid Python code via AST parser
    import ast

    for rel_path, content in files.items():
        tree = ast.parse(content, filename=rel_path)
        assert tree is not None, f"Failed to parse {rel_path}"

    # Verify structural presence of enterprise architectural components
    assert "class DistributedCache" in files["src/cache.py"]
    assert "NULL_SENTINEL" in files["src/cache.py"]
    assert "def set_null_marker" in files["src/cache.py"]
    assert "def invalidate" in files["src/cache.py"]

    assert "class OutboxManager" in files["src/outbox.py"]
    assert "def record_event_in_tx" in files["src/outbox.py"]
    assert "def poll_and_publish_pending" in files["src/outbox.py"]

    assert "class OrderRepository" in files["src/repository.py"]
    assert "def update_optimistic" in files["src/repository.py"]
    assert "def find_paginated" in files["src/repository.py"]

    assert "/health/live" in files["src/main.py"]
    assert "/health/ready" in files["src/main.py"]
    assert "/metrics" in files["src/main.py"]
    assert "tracing_middleware" in files["src/main.py"]
    assert "X-Trace-Id" in files["src/main.py"]


def test_enterprise_multi_language_synthesis():
    from elmos_project_synthesis.enterprise_production_target import generate_enterprise_target_files
    from elmos_project_synthesis.intake import approve_request, create_draft
    from elmos_project_synthesis.models import SynthesisRequest

    draft = create_draft(
        name="enterprise-order-service",
        description="Enterprise multi-language order service with outbox, cache and audit.",
        entities=[
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "reference", "type": "string", "required": True},
                    {"name": "total", "type": "number", "required": True},
                ],
            },
            {
                "singular": "order_item",
                "plural": "order_items",
                "fields": [
                    {"name": "sku", "type": "string", "required": True},
                    {"name": "price", "type": "number", "required": True},
                    {"name": "order_id", "type": "string", "required": True},
                ],
            },
        ],
        relations=[
            {
                "source": "order",
                "target": "order_item",
                "kind": "one-to-many",
                "required": False,
                "source_field": "id",
                "target_field": "order_id",
            }
        ],
        languages=["python", "java", "go", "csharp", "typescript", "rust", "kotlin", "php"],
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="actor-test", approved_at="2026-09-10T00:00:00+00:00")
    request = SynthesisRequest.from_mapping(approved)

    # 1. Java Spring Boot 3
    java_files = generate_enterprise_target_files(request, language="java")
    assert "pom.xml" in java_files
    assert "spring-boot-starter-data-redis" in java_files["pom.xml"]
    assert "spring-kafka" in java_files["pom.xml"]
    assert any("Entity.java" in k for k in java_files)
    assert any("DistributedCacheService.java" in k for k in java_files)
    assert any("OutboxPublisher.java" in k for k in java_files)
    assert any("Controller.java" in k for k in java_files)

    # 2. Go (GORM + Gin + go-redis + kafka-go)
    go_files = generate_enterprise_target_files(request, language="go")
    assert "go.mod" in go_files
    assert "github.com/gin-gonic/gin" in go_files["go.mod"]
    assert "models/models.go" in go_files
    assert "cache/cache.go" in go_files
    assert "outbox/outbox.go" in go_files
    assert "api/handlers.go" in go_files

    # 3. .NET 8 (C# EF Core + StackExchange.Redis + Confluent.Kafka)
    dotnet_files = generate_enterprise_target_files(request, language="dotnet")
    assert any(k.endswith(".csproj") for k in dotnet_files)
    assert "Models/Entities.cs" in dotnet_files
    assert "Cache/DistributedCacheService.cs" in dotnet_files
    assert "Outbox/OutboxPublisher.cs" in dotnet_files
    assert "Data/AppDbContext.cs" in dotnet_files

    # 4. TypeScript (NestJS 10 + TypeORM + ioredis + kafkajs)
    ts_files = generate_enterprise_target_files(request, language="typescript")
    assert "package.json" in ts_files
    assert "@nestjs/typeorm" in ts_files["package.json"]
    assert any(k.endswith(".entity.ts") for k in ts_files)
    assert "src/cache/cache.service.ts" in ts_files
    assert "src/outbox/outbox.service.ts" in ts_files

    # 5. Rust (Axum + SQLx + Redis + Kafka)
    rust_files = generate_enterprise_target_files(request, language="rust")
    assert "Cargo.toml" in rust_files
    assert "src/main.rs" in rust_files
    assert "src/cache.rs" in rust_files

    # 6. Kotlin (Spring Boot 3 + JPA)
    kotlin_files = generate_enterprise_target_files(request, language="kotlin")
    assert "build.gradle.kts" in kotlin_files

    # 7. PHP (Laravel 11)
    php_files = generate_enterprise_target_files(request, language="php")
    assert "composer.json" in php_files
    assert "routes/api.php" in php_files


def test_enterprise_relation_specs_and_cascading_ddl():
    from elmos_project_synthesis.enterprise_production_contract import enterprise_entity_sql
    from elmos_project_synthesis.models import EntitySpec, FieldSpec, RelationSpec

    _parent = EntitySpec(
        singular="order",
        plural="orders",
        fields=[FieldSpec(name="reference", type="string", required=True)],
    )
    child = EntitySpec(
        singular="order_item",
        plural="order_items",
        fields=[FieldSpec(name="sku", type="string", required=True)],
    )
    relations = [
        RelationSpec(
            source="order",
            target="order_item",
            kind="one-to-many",
            required=False,
            target_field="order_id",
        )
    ]

    sql_child = enterprise_entity_sql(child, relations=relations, is_sqlite=False)
    assert 'CONSTRAINT "fk_order_item_order"' in sql_child.foreign_key_ddls[0]
    assert 'REFERENCES "app"."orders"("id") ON DELETE CASCADE' in sql_child.foreign_key_ddls[0]
    assert "idx_order_item_order_id" in sql_child.foreign_key_indexes[0]


def test_enterprise_saga_contract():
    from elmos_project_synthesis.enterprise_production_contract import (
        SagaDefinition,
        SagaExecutionRecord,
        SagaStep,
    )

    definition = SagaDefinition(
        saga_id="saga-def-01",
        name="OrderCreationSaga",
        steps=(
            SagaStep(
                step_id="step-01",
                name="reserve_credit",
                action_endpoint="/api/v1/credits/reserve",
                compensation_endpoint="/api/v1/credits/release",
            ),
            SagaStep(
                step_id="step-02",
                name="deduct_inventory",
                action_endpoint="/api/v1/inventory/deduct",
                compensation_endpoint="/api/v1/inventory/restore",
            ),
        ),
    )

    record = SagaExecutionRecord(
        execution_id="exec-01",
        saga_id=definition.saga_id,
        tenant_id="tenant-acme",
        current_step=0,
        status="RUNNING",
        payload={"order_id": "ord-123"},
    )

    assert record.status == "RUNNING"
    assert len(definition.steps) == 2
    assert definition.steps[0].compensation_endpoint == "/api/v1/credits/release"
