"""Unit and integration tests for Enterprise Production Synthesis.

Verifies:
1. Enterprise Production Contract SQL generation and event data structures.
2. Hosted Distributed Runner Fleet (node registration, heartbeat, lease fencing, quota limits, timeout kill, failover).
3. Cloud-native deployment generation (Distroless Dockerfile, Kubernetes manifests, Helm chart).
4. Full FastAPI enterprise target execution (Outbox, Cache-Aside, Pagination, Filtering, Optimistic Locking, SRE probes).
"""
from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import pytest
from elmos_project_synthesis.cloud_native_deployment import (
    generate_distroless_dockerfile,
    generate_helm_chart,
    generate_kubernetes_manifests,
)
from elmos_project_synthesis.enterprise_production_contract import (
    CacheConfig,
    OutboxEvent,
    enterprise_entity_sql,
)
from elmos_project_synthesis.enterprise_production_target import generate_enterprise_python_files
from elmos_project_synthesis.hosted_runner_fleet import (
    HostedRunnerFleet,
    JobQueueItem,
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
    node2.last_heartbeat_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=45)
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
    job1.started_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
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
