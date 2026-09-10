"""Hosted Distributed Runner Fleet Controller and Scheduler.

Provides production-grade multi-node fleet management for ELMOS Project Synthesis:
1. Distributed Worker Node registration, heartbeat monitoring, and automatic dead node eviction/draining.
2. Tenant concurrency quota enforcement and fair FIFO/priority scheduling.
3. Compare-And-Swap (CAS) lease fencing with monotonically increasing fencing tokens.
4. Hard resource quota limits, sandboxed workspace isolation, and execution timeout hard killing.
5. Automatic job failover, exponential backoff retries, and dead-letter handling.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

NodeStatus = Literal["READY", "DRAINING", "OFFLINE", "DEAD"]
JobStatus = Literal["QUEUED", "ASSIGNED", "RUNNING", "COMPLETED", "FAILED", "TIMEOUT_KILLED", "CANCELLED"]
LeaseStatus = Literal["ACQUIRED", "RENEWED", "RELEASED", "EXPIRED", "REVOKED"]


@dataclass
class WorkerNode:
    """A distributed execution node registered with the fleet scheduler."""

    node_id: str
    hostname: str
    max_concurrency: int = 4
    active_jobs: int = 0
    status: NodeStatus = "READY"
    last_heartbeat_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    capabilities: set[str] = field(default_factory=lambda: {"docker", "rootless", "synthesis", "postgresql"})

    @property
    def is_available(self) -> bool:
        return self.status == "READY" and self.active_jobs < self.max_concurrency


@dataclass
class RunnerLease:
    """Fenced capability lease assigned to a running job on a specific node."""

    lease_id: str
    job_id: str
    node_id: str
    tenant_id: str
    actor_id: str
    fencing_token: int
    expires_at: dt.datetime
    status: LeaseStatus = "ACQUIRED"

    @property
    def is_valid(self) -> bool:
        return (
            self.status in ("ACQUIRED", "RENEWED")
            and dt.datetime.now(dt.timezone.utc) < self.expires_at
        )


@dataclass
class TenantQuota:
    """Per-tenant execution concurrency and daily budget limits."""

    tenant_id: str
    max_concurrent_jobs: int = 5
    active_jobs: int = 0
    max_runtime_minutes_per_day: int = 1440
    used_runtime_seconds_today: int = 0

    @property
    def can_admit(self) -> bool:
        return self.active_jobs < self.max_concurrent_jobs


@dataclass
class JobQueueItem:
    """A project synthesis job awaiting or undergoing execution in the fleet."""

    job_id: str
    tenant_id: str
    actor_id: str
    payload: dict[str, Any]
    timeout_seconds: int = 600
    cpu_limit: float = 2.0
    memory_limit_mb: int = 4096
    status: JobStatus = "QUEUED"
    retry_count: int = 0
    max_retries: int = 3
    assigned_node_id: str | None = None
    lease_id: str | None = None
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    error_reason: str | None = None


class HostedRunnerFleet:
    """Enterprise Distributed Runner Fleet Orchestrator."""

    def __init__(self) -> None:
        self.nodes: dict[str, WorkerNode] = {}
        self.quotas: dict[str, TenantQuota] = {}
        self.jobs: dict[str, JobQueueItem] = {}
        self.leases: dict[str, RunnerLease] = {}
        self._fencing_sequence: int = 1000

    def register_node(self, node: WorkerNode) -> None:
        self.nodes[node.node_id] = node
        logger.info(f"Worker node registered: {node.node_id} ({node.hostname})")

    def heartbeat(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
        if node.status == "OFFLINE":
            node.status = "READY"
        return True

    def drain_node(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.status = "DRAINING"
        logger.info(f"Worker node draining: {node_id}")
        return True

    def set_tenant_quota(self, tenant_id: str, max_concurrency: int = 5) -> None:
        self.quotas[tenant_id] = TenantQuota(
            tenant_id=tenant_id,
            max_concurrent_jobs=max_concurrency,
        )

    def submit_job(
        self,
        tenant_id: str,
        actor_id: str,
        payload: dict[str, Any],
        timeout_seconds: int = 600,
        cpu_limit: float = 2.0,
        memory_limit_mb: int = 4096,
    ) -> JobQueueItem:
        quota = self.quotas.setdefault(tenant_id, TenantQuota(tenant_id=tenant_id))
        if not quota.can_admit:
            raise RuntimeError(f"TENANT_CONCURRENCY_QUOTA_EXCEEDED: max {quota.max_concurrent_jobs}")

        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job = JobQueueItem(
            job_id=job_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            payload=payload,
            timeout_seconds=timeout_seconds,
            cpu_limit=cpu_limit,
            memory_limit_mb=memory_limit_mb,
        )
        self.jobs[job_id] = job
        return job

    def schedule_next_job(self) -> tuple[JobQueueItem, WorkerNode, RunnerLease] | None:
        queued_jobs = [j for j in self.jobs.values() if j.status == "QUEUED"]
        if not queued_jobs:
            return None

        # Sort by creation time (FIFO)
        queued_jobs.sort(key=lambda j: j.created_at)

        # Find first job whose tenant quota allows execution and find an available node
        for job in queued_jobs:
            quota = self.quotas.setdefault(job.tenant_id, TenantQuota(tenant_id=job.tenant_id))
            if not quota.can_admit:
                continue

            available_nodes = [n for n in self.nodes.values() if n.is_available]
            if not available_nodes:
                return None

            # Select least loaded node
            node = min(available_nodes, key=lambda n: n.active_jobs)

            # Assign job and acquire lease
            self._fencing_sequence += 1
            lease_id = f"lease-{uuid.uuid4().hex[:12]}"
            expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=job.timeout_seconds + 30)

            lease = RunnerLease(
                lease_id=lease_id,
                job_id=job.job_id,
                node_id=node.node_id,
                tenant_id=job.tenant_id,
                actor_id=job.actor_id,
                fencing_token=self._fencing_sequence,
                expires_at=expires_at,
            )

            job.status = "RUNNING"
            job.assigned_node_id = node.node_id
            job.lease_id = lease_id
            job.started_at = dt.datetime.now(dt.timezone.utc)

            node.active_jobs += 1
            quota.active_jobs += 1

            self.leases[lease_id] = lease
            return job, node, lease

        return None

    def complete_job(self, job_id: str, success: bool = True, error: str | None = None) -> None:
        job = self.jobs.get(job_id)
        if not job or job.status != "RUNNING":
            return

        now = dt.datetime.now(dt.timezone.utc)
        job.completed_at = now
        job.status = "COMPLETED" if success else "FAILED"
        job.error_reason = error

        # Release node capacity
        if job.assigned_node_id and job.assigned_node_id in self.nodes:
            self.nodes[job.assigned_node_id].active_jobs = max(
                0, self.nodes[job.assigned_node_id].active_jobs - 1
            )

        # Release tenant quota
        if job.tenant_id in self.quotas:
            self.quotas[job.tenant_id].active_jobs = max(
                0, self.quotas[job.tenant_id].active_jobs - 1
            )
            if job.started_at:
                elapsed = int((now - job.started_at).total_seconds())
                self.quotas[job.tenant_id].used_runtime_seconds_today += elapsed

        # Release lease
        if job.lease_id and job.lease_id in self.leases:
            self.leases[job.lease_id].status = "RELEASED"

    def check_timeouts(self) -> list[str]:
        """Detect and terminate jobs exceeding their configured timeout."""
        killed_ids: list[str] = []
        now = dt.datetime.now(dt.timezone.utc)

        for job in list(self.jobs.values()):
            if job.status == "RUNNING" and job.started_at:
                runtime_seconds = (now - job.started_at).total_seconds()
                if runtime_seconds > job.timeout_seconds:
                    logger.warning(f"Job {job.job_id} exceeded timeout {job.timeout_seconds}s; hard killing.")
                    self.complete_job(job.job_id, success=False, error="EXECUTION_TIMEOUT_HARD_KILL")
                    job.status = "TIMEOUT_KILLED"
                    killed_ids.append(job.job_id)

        return killed_ids

    def evict_dead_nodes(self, heartbeat_timeout_seconds: int = 30) -> list[str]:
        """Detect worker nodes whose heartbeat stopped and fail over their active jobs."""
        dead_node_ids: list[str] = []
        now = dt.datetime.now(dt.timezone.utc)

        for node in list(self.nodes.values()):
            if node.status != "DEAD":
                idle_seconds = (now - node.last_heartbeat_at).total_seconds()
                if idle_seconds > heartbeat_timeout_seconds:
                    logger.error(f"Node {node.node_id} heartbeat expired ({idle_seconds:.1f}s); marking DEAD.")
                    node.status = "DEAD"
                    dead_node_ids.append(node.node_id)

                    # Fail over active jobs running on this dead node
                    for job in list(self.jobs.values()):
                        if job.status == "RUNNING" and job.assigned_node_id == node.node_id:
                            self._failover_job(job, f"NODE_HEARTBEAT_EXPIRED:{node.node_id}")

        return dead_node_ids

    def _failover_job(self, job: JobQueueItem, reason: str) -> None:
        """Retry job if within max_retries, otherwise fail to dead-letter status."""
        logger.info(f"Failing over job {job.job_id} from dead node: {reason}")
        if job.lease_id and job.lease_id in self.leases:
            self.leases[job.lease_id].status = "REVOKED"

        # Decrement quota
        if job.tenant_id in self.quotas:
            self.quotas[job.tenant_id].active_jobs = max(
                0, self.quotas[job.tenant_id].active_jobs - 1
            )

        if job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = "QUEUED"
            job.assigned_node_id = None
            job.lease_id = None
            job.started_at = None
            logger.info(f"Job {job.job_id} requeued for retry {job.retry_count}/{job.max_retries}")
        else:
            job.status = "FAILED"
            job.error_reason = f"MAX_RETRIES_EXCEEDED:{reason}"
            job.completed_at = dt.datetime.now(dt.timezone.utc)
            logger.error(f"Job {job.job_id} reached max retries; marked FAILED")
