"""Tenant-sharded job dispatcher for hosted generation.

Queueing never rejects a job just because a tenant is at its concurrent cap:
the extra work waits, and one tenant cannot starve another. Tokens are minted
only when a slot is actually granted.
"""
from __future__ import annotations

import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .hosted_job_token import (
    MAX_LIFETIME_SECONDS,
    JobTokenClaims,
    JobTokenError,
    issue_job_token,
)

PLAN_LIMITS: dict[str, dict[str, int]] = {
    "trial": {"concurrent_jobs": 1, "active_projects": 1, "retention_days": 7},
    "professional-monthly": {"concurrent_jobs": 3, "active_projects": 10, "retention_days": 30},
    "professional-annual": {"concurrent_jobs": 5, "active_projects": 25, "retention_days": 90},
}

HARD_CPU_MILLIS = 2000
HARD_MEMORY_MIB = 2048
HARD_PIDS = 256
HARD_WALLCLOCK = 900


class DispatcherError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class QueuedJob:
    job_id: str
    tenant: str
    actor: str
    plan: str
    scope: tuple[str, ...]
    image: str
    submitted_at: int
    status: str = "QUEUED"
    token: str | None = None


@dataclass
class TenantQueue:
    waiting: deque[QueuedJob] = field(default_factory=deque)
    running: dict[str, QueuedJob] = field(default_factory=dict)


class JobDispatcher:
    def __init__(self, *, private_key: Path, key_id: str) -> None:
        self.private_key = private_key
        self.key_id = key_id
        self.tenants: dict[str, TenantQueue] = {}

    def enqueue(
        self,
        *,
        tenant: str,
        actor: str,
        plan: str,
        scope: tuple[str, ...],
        image: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        if plan not in PLAN_LIMITS:
            raise DispatcherError("DISPATCHER_PLAN_UNKNOWN")
        observed = int(now if now is not None else time.time())
        job = QueuedJob(
            job_id=f"job-{uuid.uuid4()}",
            tenant=tenant,
            actor=actor,
            plan=plan,
            scope=scope,
            image=image,
            submitted_at=observed,
        )
        shard = self.tenants.setdefault(tenant, TenantQueue())
        shard.waiting.append(job)
        granted = self._grant(tenant, observed)
        position = self._position(tenant, job.job_id)
        return {
            "job_id": job.job_id,
            "tenant": tenant,
            "status": granted.status if granted and granted.job_id == job.job_id else "QUEUED",
            "queue_position": position,
            "token": granted.token if granted and granted.job_id == job.job_id else None,
        }

    def complete(self, tenant: str, job_id: str, *, now: int | None = None) -> QueuedJob | None:
        shard = self.tenants.get(tenant)
        if shard is None or job_id not in shard.running:
            raise DispatcherError("DISPATCHER_JOB_NOT_RUNNING")
        finished = shard.running.pop(job_id)
        finished.status = "COMPLETED"
        return self._grant(tenant, int(now if now is not None else time.time()))

    def snapshot(self) -> dict[str, Any]:
        return {
            tenant: {
                "running": sorted(shard.running),
                "queued": [job.job_id for job in shard.waiting],
            }
            for tenant, shard in self.tenants.items()
        }

    def _position(self, tenant: str, job_id: str) -> int:
        shard = self.tenants[tenant]
        if job_id in shard.running:
            return 0
        for index, job in enumerate(shard.waiting, start=1):
            if job.job_id == job_id:
                return index
        return -1

    def _grant(self, tenant: str, now: int) -> QueuedJob | None:
        shard = self.tenants[tenant]
        if shard.waiting:
            cap = PLAN_LIMITS[shard.waiting[0].plan]["concurrent_jobs"]
        elif shard.running:
            cap = PLAN_LIMITS[next(iter(shard.running.values())).plan]["concurrent_jobs"]
        else:
            return None
        granted: QueuedJob | None = None
        while shard.waiting and len(shard.running) < cap:
            job = shard.waiting.popleft()
            job.status = "GRANTED"
            job.token = issue_job_token(
                JobTokenClaims(
                    jti=f"jti-{uuid.uuid4()}",
                    tenant=job.tenant,
                    actor=job.actor,
                    job=job.job_id,
                    scope=job.scope,
                    image=job.image,
                    cpu_millis=HARD_CPU_MILLIS,
                    memory_mib=HARD_MEMORY_MIB,
                    pids=HARD_PIDS,
                    wallclock_seconds=HARD_WALLCLOCK,
                    issued_at=now,
                    expires_at=now + MAX_LIFETIME_SECONDS,
                ),
                private_key=self.private_key,
                key_id=self.key_id,
                now=now,
            )
            shard.running[job.job_id] = job
            granted = job
        return granted


def clamp_limits(requested: dict[str, int]) -> dict[str, int]:
    return {
        "cpu_millis": min(int(requested.get("cpu_millis", HARD_CPU_MILLIS)), HARD_CPU_MILLIS),
        "memory_mib": min(int(requested.get("memory_mib", HARD_MEMORY_MIB)), HARD_MEMORY_MIB),
        "pids": min(int(requested.get("pids", HARD_PIDS)), HARD_PIDS),
        "wallclock_seconds": min(int(requested.get("wallclock_seconds", HARD_WALLCLOCK)), HARD_WALLCLOCK),
    }


def reject_local_token_in_production(environment: dict[str, str]) -> None:
    if environment.get("ELMOS_ENVIRONMENT") != "production":
        return
    if environment.get("ELMOS_LOCAL_RUNNER_AUTH_TOKEN") or environment.get(
        "ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE"
    ):
        raise JobTokenError("LOCAL_RUNNER_TOKEN_FORBIDDEN_IN_PRODUCTION")
    if environment.get("ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID"):
        raise JobTokenError("TRUSTED_SINGLE_TENANT_FORBIDDEN_IN_PRODUCTION")
    if environment.get("ELMOS_HOSTED_RUNNER_ENABLED") != "true":
        raise JobTokenError("HOSTED_RUNNER_REQUIRED_IN_PRODUCTION")


def write_isolation_assertion(path: Path, record: dict[str, Any]) -> None:
    required = (
        "job_id",
        "image",
        "network",
        "read_only_root",
        "cap_drop",
        "no_new_privileges",
        "user",
        "pids_limit",
        "memory",
        "cpus",
        "exit_code",
    )
    missing = [key for key in required if key not in record]
    if missing:
        raise DispatcherError("ISOLATION_ASSERTION_INCOMPLETE:" + ",".join(missing))
    if record.get("network") != "none" or record.get("read_only_root") is not True:
        raise DispatcherError("ISOLATION_ASSERTION_FAILED")
    if record.get("cap_drop") != "ALL" or record.get("no_new_privileges") is not True:
        raise DispatcherError("ISOLATION_ASSERTION_FAILED")
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
