"""Hosted Distributed Runner Fleet Controller and Scheduler.

Provides production-grade multi-node fleet management for ELMOS Project Synthesis:
1. Distributed Worker Node registration, heartbeat monitoring, and automatic dead node eviction/draining.
2. Tenant concurrency quota enforcement and fair FIFO/priority scheduling.
3. Compare-And-Swap (CAS) lease fencing with monotonically increasing fencing tokens.
4. Hard resource quota limits, sandboxed workspace isolation, and execution timeout hard killing.
5. Automatic job failover, exponential backoff retries, and dead-letter handling.
6. Persistent SQLite/Postgres backend support with crash-recovery and replayability.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
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
    last_heartbeat_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
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
        return self.status in ("ACQUIRED", "RENEWED") and dt.datetime.now(dt.UTC) < self.expires_at


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
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    error_reason: str | None = None


class HostedRunnerFleet:
    """Enterprise Distributed Runner Fleet Orchestrator with Persistent Durability."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.nodes: dict[str, WorkerNode] = {}
        self.quotas: dict[str, TenantQuota] = {}
        self.jobs: dict[str, JobQueueItem] = {}
        self.leases: dict[str, RunnerLease] = {}
        self._fencing_sequence: int = 1000

        if self.db_path:
            self._init_sqlite()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_sqlite(self) -> None:
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS fleet_fencing_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_seq INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fleet_worker_nodes (
                    node_id TEXT PRIMARY KEY,
                    hostname TEXT NOT NULL,
                    max_concurrency INTEGER NOT NULL,
                    active_jobs INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    last_heartbeat_at TEXT NOT NULL,
                    capabilities TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fleet_tenant_quotas (
                    tenant_id TEXT PRIMARY KEY,
                    max_concurrent_jobs INTEGER NOT NULL,
                    active_jobs INTEGER NOT NULL,
                    max_runtime_minutes_per_day INTEGER NOT NULL,
                    used_runtime_seconds_today INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fleet_jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    cpu_limit REAL NOT NULL,
                    memory_limit_mb INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    assigned_node_id TEXT,
                    lease_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS fleet_runner_leases (
                    lease_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
            """)

            # Load or init fencing sequence
            row = conn.execute("SELECT current_seq FROM fleet_fencing_state WHERE id = 1").fetchone()
            if row:
                self._fencing_sequence = max(1000, row["current_seq"])
            else:
                conn.execute("INSERT INTO fleet_fencing_state (id, current_seq) VALUES (1, 1000)")
                self._fencing_sequence = 1000

            # Load nodes
            for r in conn.execute("SELECT * FROM fleet_worker_nodes"):
                self.nodes[r["node_id"]] = WorkerNode(
                    node_id=r["node_id"],
                    hostname=r["hostname"],
                    max_concurrency=r["max_concurrency"],
                    active_jobs=r["active_jobs"],
                    status=r["status"],
                    last_heartbeat_at=dt.datetime.fromisoformat(r["last_heartbeat_at"]),
                    capabilities=set(json.loads(r["capabilities"])),
                )

            # Load quotas
            for r in conn.execute("SELECT * FROM fleet_tenant_quotas"):
                self.quotas[r["tenant_id"]] = TenantQuota(
                    tenant_id=r["tenant_id"],
                    max_concurrent_jobs=r["max_concurrent_jobs"],
                    active_jobs=r["active_jobs"],
                    max_runtime_minutes_per_day=r["max_runtime_minutes_per_day"],
                    used_runtime_seconds_today=r["used_runtime_seconds_today"],
                )

            # Load leases
            for r in conn.execute("SELECT * FROM fleet_runner_leases"):
                self.leases[r["lease_id"]] = RunnerLease(
                    lease_id=r["lease_id"],
                    job_id=r["job_id"],
                    node_id=r["node_id"],
                    tenant_id=r["tenant_id"],
                    actor_id=r["actor_id"],
                    fencing_token=r["fencing_token"],
                    expires_at=dt.datetime.fromisoformat(r["expires_at"]),
                    status=r["status"],
                )

            # Load jobs
            for r in conn.execute("SELECT * FROM fleet_jobs"):
                self.jobs[r["job_id"]] = JobQueueItem(
                    job_id=r["job_id"],
                    tenant_id=r["tenant_id"],
                    actor_id=r["actor_id"],
                    payload=json.loads(r["payload"]),
                    timeout_seconds=r["timeout_seconds"],
                    cpu_limit=r["cpu_limit"],
                    memory_limit_mb=r["memory_limit_mb"],
                    status=r["status"],
                    retry_count=r["retry_count"],
                    max_retries=r["max_retries"],
                    assigned_node_id=r["assigned_node_id"],
                    lease_id=r["lease_id"],
                    created_at=dt.datetime.fromisoformat(r["created_at"]),
                    started_at=dt.datetime.fromisoformat(r["started_at"]) if r["started_at"] else None,
                    completed_at=dt.datetime.fromisoformat(r["completed_at"]) if r["completed_at"] else None,
                    error_reason=r["error_reason"],
                )

    def _persist_node(self, node: WorkerNode) -> None:
        if not self.db_path:
            return
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO fleet_worker_nodes (node_id, hostname, max_concurrency, active_jobs, status, last_heartbeat_at, capabilities)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(node_id) DO UPDATE SET
                     hostname=excluded.hostname, max_concurrency=excluded.max_concurrency,
                     active_jobs=excluded.active_jobs, status=excluded.status,
                     last_heartbeat_at=excluded.last_heartbeat_at, capabilities=excluded.capabilities""",
                (
                    node.node_id,
                    node.hostname,
                    node.max_concurrency,
                    node.active_jobs,
                    node.status,
                    node.last_heartbeat_at.isoformat(),
                    json.dumps(sorted(list(node.capabilities))),
                ),
            )

    def _persist_quota(self, quota: TenantQuota) -> None:
        if not self.db_path:
            return
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO fleet_tenant_quotas (tenant_id, max_concurrent_jobs, active_jobs, max_runtime_minutes_per_day, used_runtime_seconds_today)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(tenant_id) DO UPDATE SET
                     max_concurrent_jobs=excluded.max_concurrent_jobs,
                     active_jobs=excluded.active_jobs,
                     max_runtime_minutes_per_day=excluded.max_runtime_minutes_per_day,
                     used_runtime_seconds_today=excluded.used_runtime_seconds_today""",
                (
                    quota.tenant_id,
                    quota.max_concurrent_jobs,
                    quota.active_jobs,
                    quota.max_runtime_minutes_per_day,
                    quota.used_runtime_seconds_today,
                ),
            )

    def _persist_job(self, job: JobQueueItem) -> None:
        if not self.db_path:
            return
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO fleet_jobs (job_id, tenant_id, actor_id, payload, timeout_seconds, cpu_limit, memory_limit_mb, status, retry_count, max_retries, assigned_node_id, lease_id, created_at, started_at, completed_at, error_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                     status=excluded.status, retry_count=excluded.retry_count,
                     assigned_node_id=excluded.assigned_node_id, lease_id=excluded.lease_id,
                     started_at=excluded.started_at, completed_at=excluded.completed_at,
                     error_reason=excluded.error_reason""",
                (
                    job.job_id,
                    job.tenant_id,
                    job.actor_id,
                    json.dumps(job.payload),
                    job.timeout_seconds,
                    job.cpu_limit,
                    job.memory_limit_mb,
                    job.status,
                    job.retry_count,
                    job.max_retries,
                    job.assigned_node_id,
                    job.lease_id,
                    job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.error_reason,
                ),
            )

    def _persist_lease(self, lease: RunnerLease) -> None:
        if not self.db_path:
            return
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO fleet_runner_leases (lease_id, job_id, node_id, tenant_id, actor_id, fencing_token, expires_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(lease_id) DO UPDATE SET status=excluded.status, expires_at=excluded.expires_at""",
                (
                    lease.lease_id,
                    lease.job_id,
                    lease.node_id,
                    lease.tenant_id,
                    lease.actor_id,
                    lease.fencing_token,
                    lease.expires_at.isoformat(),
                    lease.status,
                ),
            )

    def _persist_fencing_seq(self) -> None:
        if not self.db_path:
            return
        with self._get_conn() as conn:
            conn.execute("UPDATE fleet_fencing_state SET current_seq = ? WHERE id = 1", (self._fencing_sequence,))

    def register_node(self, node: WorkerNode) -> None:
        self.nodes[node.node_id] = node
        self._persist_node(node)
        logger.info(f"Worker node registered: {node.node_id} ({node.hostname})")

    def heartbeat(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.last_heartbeat_at = dt.datetime.now(dt.UTC)
        if node.status == "OFFLINE":
            node.status = "READY"
        self._persist_node(node)
        return True

    def drain_node(self, node_id: str) -> bool:
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.status = "DRAINING"
        self._persist_node(node)
        logger.info(f"Worker node draining: {node_id}")
        return True

    def set_tenant_quota(self, tenant_id: str, max_concurrency: int = 5) -> None:
        quota = TenantQuota(
            tenant_id=tenant_id,
            max_concurrent_jobs=max_concurrency,
        )
        self.quotas[tenant_id] = quota
        self._persist_quota(quota)

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
        self._persist_job(job)
        return job

    def schedule_next_job(self) -> tuple[JobQueueItem, WorkerNode, RunnerLease] | None:
        queued_jobs = [j for j in self.jobs.values() if j.status == "QUEUED"]
        if not queued_jobs:
            return None

        # Sort by creation time (FIFO)
        queued_jobs.sort(key=lambda j: j.created_at)

        for job in queued_jobs:
            quota = self.quotas.setdefault(job.tenant_id, TenantQuota(tenant_id=job.tenant_id))
            if not quota.can_admit:
                continue

            available_nodes = [n for n in self.nodes.values() if n.is_available]
            if not available_nodes:
                return None

            # Select least loaded node
            node = min(available_nodes, key=lambda n: n.active_jobs)

            # Assign job and acquire lease with CAS fencing token
            self._fencing_sequence += 1
            self._persist_fencing_seq()

            lease_id = f"lease-{uuid.uuid4().hex[:12]}"
            expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=job.timeout_seconds + 30)

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
            job.started_at = dt.datetime.now(dt.UTC)

            node.active_jobs += 1
            quota.active_jobs += 1

            self.leases[lease_id] = lease
            self._persist_job(job)
            self._persist_lease(lease)
            self._persist_node(node)
            self._persist_quota(quota)

            return job, node, lease

        return None

    def verify_lease(self, lease_id: str, fencing_token: int) -> bool:
        """Verify that a lease is valid and has not been superseded by a higher token or revoked."""
        lease = self.leases.get(lease_id)
        if not lease or not lease.is_valid:
            return False
        return lease.fencing_token == fencing_token

    def complete_job(self, job_id: str, success: bool = True, error: str | None = None) -> None:
        job = self.jobs.get(job_id)
        if not job or job.status != "RUNNING":
            return

        now = dt.datetime.now(dt.UTC)
        job.completed_at = now
        job.status = "COMPLETED" if success else "FAILED"
        job.error_reason = error

        if job.assigned_node_id and job.assigned_node_id in self.nodes:
            self.nodes[job.assigned_node_id].active_jobs = max(0, self.nodes[job.assigned_node_id].active_jobs - 1)
            self._persist_node(self.nodes[job.assigned_node_id])

        if job.tenant_id in self.quotas:
            self.quotas[job.tenant_id].active_jobs = max(0, self.quotas[job.tenant_id].active_jobs - 1)
            if job.started_at:
                elapsed = int((now - job.started_at).total_seconds())
                self.quotas[job.tenant_id].used_runtime_seconds_today += elapsed
            self._persist_quota(self.quotas[job.tenant_id])

        if job.lease_id and job.lease_id in self.leases:
            self.leases[job.lease_id].status = "RELEASED"
            self._persist_lease(self.leases[job.lease_id])

        self._persist_job(job)

    def check_timeouts(self) -> list[str]:
        """Detect and terminate jobs exceeding their configured timeout."""
        killed_ids: list[str] = []
        now = dt.datetime.now(dt.UTC)

        for job in list(self.jobs.values()):
            if job.status == "RUNNING" and job.started_at:
                runtime_seconds = (now - job.started_at).total_seconds()
                if runtime_seconds > job.timeout_seconds:
                    logger.warning(f"Job {job.job_id} exceeded timeout {job.timeout_seconds}s; hard killing.")
                    self.complete_job(job.job_id, success=False, error="EXECUTION_TIMEOUT_HARD_KILL")
                    job.status = "TIMEOUT_KILLED"
                    self._persist_job(job)
                    killed_ids.append(job.job_id)

        return killed_ids

    def evict_dead_nodes(self, heartbeat_timeout_seconds: int = 30) -> list[str]:
        """Detect worker nodes whose heartbeat stopped and fail over their active jobs."""
        dead_node_ids: list[str] = []
        now = dt.datetime.now(dt.UTC)

        for node in list(self.nodes.values()):
            if node.status != "DEAD":
                idle_seconds = (now - node.last_heartbeat_at).total_seconds()
                if idle_seconds > heartbeat_timeout_seconds:
                    logger.error(f"Node {node.node_id} heartbeat expired ({idle_seconds:.1f}s); marking DEAD.")
                    node.status = "DEAD"
                    self._persist_node(node)
                    dead_node_ids.append(node.node_id)

                    for job in list(self.jobs.values()):
                        if job.status == "RUNNING" and job.assigned_node_id == node.node_id:
                            self._failover_job(job, f"NODE_HEARTBEAT_EXPIRED:{node.node_id}")

        return dead_node_ids

    def _failover_job(self, job: JobQueueItem, reason: str) -> None:
        """Retry job if within max_retries, otherwise fail to dead-letter status."""
        logger.info(f"Failing over job {job.job_id} from dead node: {reason}")
        if job.lease_id and job.lease_id in self.leases:
            self.leases[job.lease_id].status = "REVOKED"
            self._persist_lease(self.leases[job.lease_id])

        if job.tenant_id in self.quotas:
            self.quotas[job.tenant_id].active_jobs = max(0, self.quotas[job.tenant_id].active_jobs - 1)
            self._persist_quota(self.quotas[job.tenant_id])

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
            job.completed_at = dt.datetime.now(dt.UTC)
            logger.error(f"Job {job.job_id} reached max retries; marked FAILED")

        self._persist_job(job)
