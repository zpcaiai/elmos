"""Tests for Persistent HostedRunnerFleet & WorkerAgentDaemon with CAS Fencing."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from elmos_project_synthesis.hosted_runner_fleet import HostedRunnerFleet, WorkerNode
from elmos_project_synthesis.worker_agent import WorkerAgentDaemon


def test_persistent_fleet_lifecycle_and_crash_recovery(tmp_path: Path):
    db_file = tmp_path / "fleet_state.db"

    # 1. First Fleet instance: submit and schedule job
    fleet1 = HostedRunnerFleet(db_path=db_file)
    node1 = WorkerNode(node_id="node-p1", hostname="worker-p1.local", max_concurrency=3)
    fleet1.register_node(node1)
    fleet1.set_tenant_quota("tenant-persistent", max_concurrency=3)

    job1 = fleet1.submit_job("tenant-persistent", "actor-bob", {"sample": "data1"})
    scheduled1 = fleet1.schedule_next_job()
    assert scheduled1 is not None
    s_job1, s_node1, s_lease1 = scheduled1
    token1 = s_lease1.fencing_token
    assert token1 >= 1001

    # Simulate coordinator restart / crash recovery
    del fleet1

    # 2. Second Fleet instance: recovers state from DB
    fleet2 = HostedRunnerFleet(db_path=db_file)
    assert "node-p1" in fleet2.nodes
    assert fleet2.nodes["node-p1"].status == "READY"
    assert "tenant-persistent" in fleet2.quotas
    assert s_job1.job_id in fleet2.jobs
    assert fleet2.jobs[s_job1.job_id].status == "RUNNING"
    assert s_lease1.lease_id in fleet2.leases
    assert fleet2.leases[s_lease1.lease_id].fencing_token == token1

    # Monotonic fencing sequence after crash: next token must be strictly greater
    job2 = fleet2.submit_job("tenant-persistent", "actor-bob", {"sample": "data2"})
    scheduled2 = fleet2.schedule_next_job()
    assert scheduled2 is not None
    s_job2, s_node2, s_lease2 = scheduled2
    token2 = s_lease2.fencing_token
    assert token2 > token1, f"Fencing token must be monotonically strictly greater: {token2} > {token1}"


def test_worker_agent_execution_and_brain_split_protection(tmp_path: Path):
    db_file = tmp_path / "fleet_worker_test.db"
    fleet = HostedRunnerFleet(db_path=db_file)
    workspace_dir = tmp_path / "workspaces"

    worker = WorkerAgentDaemon(
        node_id="worker-node-alpha",
        hostname="alpha.worker.corp",
        fleet=fleet,
        max_concurrency=2,
        workspace_root=workspace_dir,
    )
    worker.register()

    assert worker.heartbeat() is True
    assert "worker-node-alpha" in fleet.nodes

    # Submit job for Go enterprise microservice
    job = fleet.submit_job(
        "tenant-corp",
        "actor-worker-test",
        {
            "name": "enterprise-inventory",
            "target_language": "go",
        },
    )

    scheduled = fleet.schedule_next_job()
    assert scheduled is not None
    s_job, s_node, s_lease = scheduled

    # 1. Normal execution
    res = worker.execute_scheduled_job(s_job, s_lease)
    assert res["status"] == "COMPLETED"
    assert res["files_count"] > 0
    assert res["target_language"] == "go"
    assert res["evidence_sha256"].startswith("sha256:")
    assert fleet.jobs[job.job_id].status == "COMPLETED"

    # 2. Brain-split protection: simulate revoked/expired lease
    job_split = fleet.submit_job("tenant-corp", "actor-test", {"name": "split-job"})
    s_split = fleet.schedule_next_job()
    assert s_split is not None
    j_split, n_split, l_split = s_split

    # Revoke lease (simulating lease eviction / reassignment to another node)
    fleet.leases[l_split.lease_id].status = "REVOKED"

    # Worker attempts to execute with revoked lease
    abort_res = worker.execute_scheduled_job(j_split, l_split)
    assert abort_res["status"] == "ABORTED"
    assert "LEASE_FENCING_INVALID" in abort_res["reason"]
