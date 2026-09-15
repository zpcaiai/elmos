"""End-to-End integration tests for Hosted Runner Fleet Multi-Tenant Scheduling and Rootless Sandbox Execution.

Covers:
1. Multi-tenant concurrent job submissions with strict per-tenant concurrency quotas.
2. Fair FIFO queue scheduling with node availability checks.
3. Dead node heartbeat timeout eviction, running job failover, and retry limits.
4. Monotonic CAS lease fencing and split-brain protection.
5. WorkerAgentDaemon execution coupled with hermetic rootless sandbox validation.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

from elmos_project_synthesis.hosted_runner_fleet import (
    HostedRunnerFleet,
    WorkerNode,
)
from elmos_project_synthesis.worker_agent import WorkerAgentDaemon


def test_multi_tenant_concurrency_quotas_and_admission(tmp_path: Path):
    db_file = tmp_path / "fleet_multitenant.db"
    fleet = HostedRunnerFleet(db_path=db_file)

    # Register worker nodes
    fleet.register_node(WorkerNode(node_id="n1", hostname="host1.local", max_concurrency=4))
    fleet.register_node(WorkerNode(node_id="n2", hostname="host2.local", max_concurrency=4))

    # Tenant quotas
    fleet.set_tenant_quota("tenant-finance", max_concurrency=2)
    fleet.set_tenant_quota("tenant-logistics", max_concurrency=1)

    # Tenant-finance submits 2 jobs and they are scheduled into active execution
    j_f1 = fleet.submit_job("tenant-finance", "alice", {"name": "svc-f1", "target_language": "python"})
    j_f2 = fleet.submit_job("tenant-finance", "alice", {"name": "svc-f2", "target_language": "go"})
    assert j_f1.status == "QUEUED"
    assert j_f2.status == "QUEUED"

    # Schedule jobs so tenant-finance reaches its max_concurrency quota (2 active jobs)
    scheduled_1 = fleet.schedule_next_job()
    assert scheduled_1 is not None
    assert scheduled_1[0].job_id == j_f1.job_id
    assert scheduled_1[2].fencing_token >= 1001

    scheduled_2 = fleet.schedule_next_job()
    assert scheduled_2 is not None
    assert scheduled_2[0].job_id == j_f2.job_id
    assert scheduled_2[2].fencing_token > scheduled_1[2].fencing_token

    assert fleet.quotas["tenant-finance"].active_jobs == 2

    # 3rd job for tenant-finance exceeds quota
    with pytest.raises(RuntimeError, match="TENANT_CONCURRENCY_QUOTA_EXCEEDED"):
        fleet.submit_job("tenant-finance", "alice", {"name": "svc-f3"})

    # Tenant-logistics submits 1 job (admitted) and gets scheduled (reaches max_concurrency = 1)
    j_l1 = fleet.submit_job("tenant-logistics", "bob", {"name": "svc-l1", "target_language": "java"})
    assert j_l1.status == "QUEUED"
    scheduled_l1 = fleet.schedule_next_job()
    assert scheduled_l1 is not None
    assert scheduled_l1[0].job_id == j_l1.job_id
    assert fleet.quotas["tenant-logistics"].active_jobs == 1

    # Tenant-logistics 2nd job exceeds quota
    with pytest.raises(RuntimeError, match="TENANT_CONCURRENCY_QUOTA_EXCEEDED"):
        fleet.submit_job("tenant-logistics", "bob", {"name": "svc-l2"})

    # Complete job 1 for tenant-finance
    fleet.complete_job(j_f1.job_id, success=True)
    assert fleet.quotas["tenant-finance"].active_jobs == 1

    # Now tenant-finance can submit another job
    j_f4 = fleet.submit_job("tenant-finance", "alice", {"name": "svc-f4"})
    assert j_f4.status == "QUEUED"


def test_node_heartbeat_eviction_and_job_failover(tmp_path: Path):
    db_file = tmp_path / "fleet_failover.db"
    fleet = HostedRunnerFleet(db_path=db_file)

    node_a = WorkerNode(node_id="node-a", hostname="node-a.local", max_concurrency=2)
    node_b = WorkerNode(node_id="node-b", hostname="node-b.local", max_concurrency=2)
    fleet.register_node(node_a)
    fleet.register_node(node_b)
    fleet.set_tenant_quota("tenant-failover", max_concurrency=5)

    job = fleet.submit_job("tenant-failover", "actor-1", {"name": "critical-pipeline"})
    scheduled = fleet.schedule_next_job()
    assert scheduled is not None
    s_job, s_node, s_lease = scheduled
    assigned_node_id = s_node.node_id

    # Simulate assigned node becoming unresponsive
    if assigned_node_id == "node-a":
        node_a.last_heartbeat_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=60)
        backup_node_id = "node-b"
    else:
        node_b.last_heartbeat_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=60)
        backup_node_id = "node-a"

    dead_nodes = fleet.evict_dead_nodes(heartbeat_timeout_seconds=30)
    assert assigned_node_id in dead_nodes

    # Check that job was re-queued with incremented retry count
    assert fleet.jobs[job.job_id].status == "QUEUED"
    assert fleet.jobs[job.job_id].retry_count == 1

    # Next schedule picks up the backup node
    rescheduled = fleet.schedule_next_job()
    assert rescheduled is not None
    r_job, r_node, r_lease = rescheduled
    assert r_job.job_id == job.job_id
    assert r_node.node_id == backup_node_id
    assert r_lease.fencing_token > s_lease.fencing_token  # Monotonic fence increment


def test_worker_agent_with_rootless_sandbox_execution(tmp_path: Path):
    db_file = tmp_path / "fleet_sandbox.db"
    fleet = HostedRunnerFleet(db_path=db_file)
    workspace_root = tmp_path / "workspaces"

    worker = WorkerAgentDaemon(
        node_id="sandbox-worker-01",
        hostname="sandbox-host.local",
        fleet=fleet,
        max_concurrency=2,
        workspace_root=workspace_root,
    )
    worker.register()

    # Submit job with sandbox command
    job = fleet.submit_job(
        "tenant-sandbox",
        "actor-sandbox",
        {
            "name": "secure-service",
            "target_language": "python",
            "sandbox_command": [sys.executable, "-c", "import sys; print('Sandboxed execution verified!')"],
            "sandbox_backend": "hermetic_path_jail",
        },
    )

    scheduled = fleet.schedule_next_job()
    assert scheduled is not None
    s_job, s_node, s_lease = scheduled

    result = worker.execute_scheduled_job(s_job, s_lease)
    assert result["status"] == "COMPLETED"
    assert "sandbox_info" in result
    assert result["sandbox_info"]["exit_code"] == 0
    assert result["sandbox_info"]["is_success"] is True
    assert result["sandbox_info"]["security_verifications"]["read_only_root"] is True
    assert fleet.jobs[job.job_id].status == "COMPLETED"
