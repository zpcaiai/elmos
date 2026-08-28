"""Runtime-plane worker registry, admission control and cursor streams."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from .errors import BudgetExceeded, ContractViolation, LeaseLost, TenantIsolationError
from .ledger import EventLedger
from .models import Event, Identity, new_id


@dataclass(frozen=True, slots=True)
class WorkerLease:
    worker_id: str
    region: str
    capabilities: frozenset[str]
    fencing_token: str
    expires_at: float
    draining: bool = False


class WorkerRegistry:
    def __init__(self, *, lease_seconds: float = 30.0) -> None:
        self.lease_seconds = lease_seconds
        self._workers: dict[str, WorkerLease] = {}
        self._lock = threading.RLock()

    def register(
        self, worker_id: str, region: str, capabilities: Iterable[str], *, now: float | None = None
    ) -> WorkerLease:
        if not worker_id or not region:
            raise ContractViolation("worker identity and region are required")
        now = time.time() if now is None else now
        lease = WorkerLease(worker_id, region, frozenset(capabilities), new_id(), now + self.lease_seconds)
        with self._lock:
            self._workers[worker_id] = lease
        return lease

    def heartbeat(self, lease: WorkerLease, *, now: float | None = None) -> WorkerLease:
        now = time.time() if now is None else now
        with self._lock:
            current = self._workers.get(lease.worker_id)
            if current is None or current.fencing_token != lease.fencing_token or current.expires_at <= now:
                raise LeaseLost("worker lease is stale")
            updated = WorkerLease(
                lease.worker_id,
                lease.region,
                lease.capabilities,
                lease.fencing_token,
                now + self.lease_seconds,
                lease.draining,
            )
            self._workers[lease.worker_id] = updated
            return updated

    def drain(self, lease: WorkerLease) -> WorkerLease:
        with self._lock:
            current = self._workers.get(lease.worker_id)
            if current is None or current.fencing_token != lease.fencing_token:
                raise LeaseLost("worker lease is stale")
            updated = WorkerLease(
                current.worker_id,
                current.region,
                current.capabilities,
                current.fencing_token,
                current.expires_at,
                True,
            )
            self._workers[lease.worker_id] = updated
            return updated

    def choose(
        self, *, region: str, required_capabilities: Iterable[str], now: float | None = None
    ) -> WorkerLease:
        now = time.time() if now is None else now
        required = set(required_capabilities)
        with self._lock:
            candidates = [
                worker
                for worker in self._workers.values()
                if not worker.draining
                and worker.region == region
                and worker.expires_at > now
                and required.issubset(worker.capabilities)
            ]
        if not candidates:
            raise LeaseLost("no healthy worker satisfies placement constraints")
        return min(candidates, key=lambda worker: worker.worker_id)


class AdmissionController:
    def __init__(self, quotas: dict[str, int] | None = None) -> None:
        self.quotas = quotas or {}
        self._active: dict[str, int] = {}
        self._lock = threading.RLock()

    def admit(self, tenant_id: str) -> None:
        with self._lock:
            limit = self.quotas.get(tenant_id, 1)
            active = self._active.get(tenant_id, 0)
            if active >= limit:
                raise ContractViolation("tenant concurrency quota exceeded")
            self._active[tenant_id] = active + 1

    def release(self, tenant_id: str) -> None:
        with self._lock:
            self._active[tenant_id] = max(0, self._active.get(tenant_id, 0) - 1)

    def active(self, tenant_id: str) -> int:
        return self._active.get(tenant_id, 0)


class EventStream:
    def __init__(self, ledger: EventLedger) -> None:
        self.ledger = ledger

    def read(self, identity: Identity, *, after_seq: int = -1, limit: int = 100) -> tuple[Event, ...]:
        self.ledger.assert_identity(identity)
        return tuple(
            self.ledger.events(identity.tenant_id, identity.run_id, after_seq=after_seq, limit=limit)
        )


@dataclass(frozen=True, slots=True)
class WorkerCapacity:
    slots: int
    cpu_cores: float
    memory_mb: int

    def __post_init__(self) -> None:
        if self.slots < 1 or self.cpu_cores <= 0 or self.memory_mb < 1:
            raise ContractViolation("worker capacity must be positive")


@dataclass(frozen=True, slots=True)
class DurableWorkerLease:
    worker_id: str
    region: str
    residency: frozenset[str]
    capabilities: frozenset[str]
    capacity: WorkerCapacity
    used_slots: int
    fencing_token: str
    epoch: int
    expires_at: float
    draining: bool
    deployment_version: str


class DurableWorkerRegistry:
    """Persistent worker membership, placement, reservation and fencing."""

    def __init__(self, database: str | Path = ":memory:", *, lease_seconds: float = 30.0) -> None:
        if lease_seconds <= 0:
            raise ContractViolation("worker lease TTL must be positive")
        self.lease_seconds = lease_seconds
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS runtime_workers(worker_id TEXT PRIMARY KEY,region TEXT NOT NULL,residency_json TEXT NOT NULL,capabilities_json TEXT NOT NULL,capacity_json TEXT NOT NULL,used_slots INTEGER NOT NULL DEFAULT 0,fencing_token TEXT NOT NULL,epoch INTEGER NOT NULL,expires_at REAL NOT NULL,draining INTEGER NOT NULL DEFAULT 0,deployment_version TEXT NOT NULL);
               CREATE TABLE IF NOT EXISTS worker_assignments(assignment_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,worker_id TEXT NOT NULL,worker_token TEXT NOT NULL,state TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(tenant_id,run_id,node_id));"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def register(
        self,
        worker_id: str,
        *,
        region: str,
        residency: Iterable[str],
        capabilities: Iterable[str],
        capacity: WorkerCapacity,
        deployment_version: str,
        now: float | None = None,
    ) -> DurableWorkerLease:
        if not worker_id or not region or not deployment_version:
            raise ContractViolation("worker registration identity is incomplete")
        now = time.time() if now is None else now
        with self._lock:
            row = self._connection.execute(
                "SELECT epoch FROM runtime_workers WHERE worker_id=?", (worker_id,)
            ).fetchone()
            epoch = 1 if row is None else int(row["epoch"]) + 1
            token = new_id()
            self._connection.execute(
                """INSERT INTO runtime_workers VALUES(?,?,?,?,?,0,?,?,?,0,?)
                   ON CONFLICT(worker_id) DO UPDATE SET region=excluded.region,residency_json=excluded.residency_json,
                   capabilities_json=excluded.capabilities_json,capacity_json=excluded.capacity_json,used_slots=0,
                   fencing_token=excluded.fencing_token,epoch=excluded.epoch,expires_at=excluded.expires_at,
                   draining=0,deployment_version=excluded.deployment_version""",
                (
                    worker_id,
                    region,
                    json.dumps(sorted(set(residency))),
                    json.dumps(sorted(set(capabilities))),
                    json.dumps(asdict(capacity), sort_keys=True),
                    token,
                    epoch,
                    now + self.lease_seconds,
                    deployment_version,
                ),
            )
        return self.get(worker_id)

    def heartbeat(self, lease: DurableWorkerLease, *, now: float | None = None) -> DurableWorkerLease:
        now = time.time() if now is None else now
        with self._lock:
            updated = self._connection.execute(
                "UPDATE runtime_workers SET expires_at=? WHERE worker_id=? AND fencing_token=? AND epoch=? AND expires_at>?",
                (now + self.lease_seconds, lease.worker_id, lease.fencing_token, lease.epoch, now),
            ).rowcount
        if updated != 1:
            raise LeaseLost("durable worker heartbeat lost fencing ownership")
        return self.get(lease.worker_id)

    def drain(self, lease: DurableWorkerLease) -> DurableWorkerLease:
        updated = self._connection.execute(
            "UPDATE runtime_workers SET draining=1 WHERE worker_id=? AND fencing_token=? AND epoch=?",
            (lease.worker_id, lease.fencing_token, lease.epoch),
        ).rowcount
        if updated != 1:
            raise LeaseLost("durable worker drain lost fencing ownership")
        return self.get(lease.worker_id)

    def place(
        self,
        identity: Identity,
        *,
        region: str,
        residency: str,
        required_capabilities: Iterable[str],
        now: float | None = None,
    ) -> tuple[str, DurableWorkerLease]:
        now = time.time() if now is None else now
        required = set(required_capabilities)
        with self._lock:
            self.recover_stale(now=now)
            rows = self._connection.execute(
                "SELECT * FROM runtime_workers WHERE region=? AND draining=0 AND expires_at>? ORDER BY used_slots ASC,worker_id ASC",
                (region, now),
            ).fetchall()
            candidates = [self._lease(row) for row in rows]
            candidates = [
                worker
                for worker in candidates
                if residency in worker.residency
                and required.issubset(worker.capabilities)
                and worker.used_slots < worker.capacity.slots
            ]
            if not candidates:
                raise LeaseLost("no durable worker satisfies capacity/residency constraints")
            worker = candidates[0]
            assignment_id = new_id()
            self._connection.execute(
                "UPDATE runtime_workers SET used_slots=used_slots+1 WHERE worker_id=? AND fencing_token=? AND used_slots<?",
                (worker.worker_id, worker.fencing_token, worker.capacity.slots),
            )
            try:
                self._connection.execute(
                    "INSERT INTO worker_assignments VALUES(?,?,?,?,?,?,?,?, 'active',?)",
                    (assignment_id, *identity.scope(), worker.worker_id, worker.fencing_token, now),
                )
            except sqlite3.IntegrityError:
                self._connection.execute(
                    "UPDATE runtime_workers SET used_slots=MAX(0,used_slots-1) WHERE worker_id=?",
                    (worker.worker_id,),
                )
                row = self._connection.execute(
                    "SELECT assignment_id,worker_id,project_id,task_id FROM worker_assignments WHERE tenant_id=? AND run_id=? AND node_id=? AND state='active'",
                    (identity.tenant_id, identity.run_id, identity.node_id),
                ).fetchone()
                if row is None:
                    raise
                if (row["project_id"], row["task_id"]) != (identity.project_id, identity.task_id):
                    raise TenantIsolationError("worker assignment run is bound to another project/task")
                return row["assignment_id"], self.get(row["worker_id"])
        return assignment_id, self.get(worker.worker_id)

    def release(self, identity: Identity, assignment_id: str) -> None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM worker_assignments WHERE assignment_id=? AND tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=? AND state='active'",
                (assignment_id, *identity.scope()),
            ).fetchone()
            if row is None:
                return
            self._connection.execute(
                "UPDATE worker_assignments SET state='released' WHERE assignment_id=?", (assignment_id,)
            )
            self._connection.execute(
                "UPDATE runtime_workers SET used_slots=MAX(0,used_slots-1) WHERE worker_id=?",
                (row["worker_id"],),
            )

    def recover_stale(self, *, now: float | None = None) -> tuple[str, ...]:
        now = time.time() if now is None else now
        rows = self._connection.execute(
            "SELECT worker_id FROM runtime_workers WHERE expires_at<=?", (now,)
        ).fetchall()
        stale = tuple(row["worker_id"] for row in rows)
        for worker_id in stale:
            self._connection.execute(
                "UPDATE worker_assignments SET state='stale' WHERE worker_id=? AND state='active'",
                (worker_id,),
            )
            self._connection.execute(
                "UPDATE runtime_workers SET used_slots=0,draining=1 WHERE worker_id=?", (worker_id,)
            )
        return stale

    def assignments(self, worker_id: str, *, active_only: bool = True) -> int:
        if active_only:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM worker_assignments WHERE worker_id=? AND state='active'",
                (worker_id,),
            ).fetchone()
        else:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM worker_assignments WHERE worker_id=?",
                (worker_id,),
            ).fetchone()
        return int(row[0])

    def get(self, worker_id: str) -> DurableWorkerLease:
        row = self._connection.execute(
            "SELECT * FROM runtime_workers WHERE worker_id=?", (worker_id,)
        ).fetchone()
        if row is None:
            raise KeyError(worker_id)
        return self._lease(row)

    @staticmethod
    def _lease(row: sqlite3.Row) -> DurableWorkerLease:
        return DurableWorkerLease(
            row["worker_id"],
            row["region"],
            frozenset(json.loads(row["residency_json"])),
            frozenset(json.loads(row["capabilities_json"])),
            WorkerCapacity(**json.loads(row["capacity_json"])),
            int(row["used_slots"]),
            row["fencing_token"],
            int(row["epoch"]),
            float(row["expires_at"]),
            bool(row["draining"]),
            row["deployment_version"],
        )


@dataclass(frozen=True, slots=True)
class TenantQuota:
    concurrency: int
    tokens: int
    cpu_minutes: float
    storage_bytes: int
    cost_micros: int
    queue_depth: int = 100

    def __post_init__(self) -> None:
        if (
            min(
                self.concurrency,
                self.tokens,
                self.cpu_minutes,
                self.storage_bytes,
                self.cost_micros,
                self.queue_depth,
            )
            < 0
        ):
            raise ContractViolation("tenant quota values cannot be negative")


@dataclass(frozen=True, slots=True)
class AdmissionLease:
    admission_id: str
    identity: Identity
    window: str
    state: str


class DurableAdmissionController:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS tenant_quotas(tenant_id TEXT PRIMARY KEY,quota_json TEXT NOT NULL);
               CREATE TABLE IF NOT EXISTS tenant_usage(tenant_id TEXT NOT NULL,window TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0,queued INTEGER NOT NULL DEFAULT 0,tokens INTEGER NOT NULL DEFAULT 0,cpu_minutes REAL NOT NULL DEFAULT 0,storage_bytes INTEGER NOT NULL DEFAULT 0,cost_micros INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,window));
               CREATE TABLE IF NOT EXISTS admissions(admission_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,agent_id TEXT,window TEXT NOT NULL,state TEXT NOT NULL);"""
        )
        self._lock = threading.RLock()
        self._backpressure = {"database": False, "event_bus": False, "workspace": False}

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    def set_quota(self, tenant_id: str, quota: TenantQuota) -> None:
        with self._transaction():
            self._connection.execute(
                "INSERT INTO tenant_quotas VALUES(?,?) ON CONFLICT(tenant_id) DO UPDATE SET quota_json=excluded.quota_json",
                (tenant_id, json.dumps(asdict(quota), sort_keys=True)),
            )

    def set_backpressure(self, component: str, active: bool) -> None:
        if component not in self._backpressure:
            raise ContractViolation("unknown backpressure component")
        with self._lock:
            self._backpressure[component] = active

    def admit(self, identity: Identity, *, window: str) -> AdmissionLease:
        if not window:
            raise ContractViolation("admission window is required")
        with self._transaction():
            if any(self._backpressure.values()):
                raise ContractViolation("runtime plane is applying backpressure")
            quota = self._quota(identity.tenant_id)
            self._connection.execute(
                "INSERT OR IGNORE INTO tenant_usage(tenant_id,window) VALUES(?,?)",
                (identity.tenant_id, window),
            )
            usage = self._connection.execute(
                "SELECT * FROM tenant_usage WHERE tenant_id=? AND window=?", (identity.tenant_id, window)
            ).fetchone()
            if int(usage["active"]) >= quota.concurrency:
                if int(usage["queued"]) >= quota.queue_depth:
                    raise BudgetExceeded("tenant admission queue is full")
                self._connection.execute(
                    "UPDATE tenant_usage SET queued=queued+1 WHERE tenant_id=? AND window=?",
                    (identity.tenant_id, window),
                )
                state = "queued"
            else:
                self._connection.execute(
                    "UPDATE tenant_usage SET active=active+1 WHERE tenant_id=? AND window=?",
                    (identity.tenant_id, window),
                )
                state = "active"
            lease = AdmissionLease(new_id(), identity, window, state)
            self._connection.execute(
                "INSERT INTO admissions VALUES(?,?,?,?,?,?,?,?,?)",
                (lease.admission_id, *identity.scope(), identity.agent_id, window, state),
            )
            return lease

    def promote(self, lease: AdmissionLease) -> AdmissionLease:
        with self._transaction():
            row = self._admission(lease)
            quota = self._quota(lease.identity.tenant_id)
            usage = self._connection.execute(
                "SELECT * FROM tenant_usage WHERE tenant_id=? AND window=?",
                (lease.identity.tenant_id, lease.window),
            ).fetchone()
            if (
                lease.state != "queued"
                or row["state"] != "queued"
                or usage is None
                or int(usage["active"]) >= quota.concurrency
            ):
                raise LeaseLost("queued admission cannot be promoted")
            self._connection.execute(
                "UPDATE tenant_usage SET queued=MAX(0,queued-1),active=active+1 WHERE tenant_id=? AND window=?",
                (lease.identity.tenant_id, lease.window),
            )
            updated = self._connection.execute(
                "UPDATE admissions SET state='active' WHERE admission_id=? AND state='queued'",
                (lease.admission_id,),
            ).rowcount
            if updated != 1:
                raise LeaseLost("queued admission was concurrently changed")
        return AdmissionLease(lease.admission_id, lease.identity, lease.window, "active")

    def consume(
        self,
        lease: AdmissionLease,
        *,
        tokens: int = 0,
        cpu_minutes: float = 0,
        storage_bytes: int = 0,
        cost_micros: int = 0,
    ) -> None:
        if lease.state != "active" or min(tokens, cpu_minutes, storage_bytes, cost_micros) < 0:
            raise ContractViolation("usage consumption requires an active admission and non-negative values")
        with self._transaction():
            quota = self._quota(lease.identity.tenant_id)
            if self._admission(lease)["state"] != "active":
                raise LeaseLost("admission is no longer active")
            usage = self._connection.execute(
                "SELECT * FROM tenant_usage WHERE tenant_id=? AND window=?",
                (lease.identity.tenant_id, lease.window),
            ).fetchone()
            requested = {
                "tokens": int(usage["tokens"]) + tokens,
                "cpu_minutes": float(usage["cpu_minutes"]) + cpu_minutes,
                "storage_bytes": int(usage["storage_bytes"]) + storage_bytes,
                "cost_micros": int(usage["cost_micros"]) + cost_micros,
            }
            if (
                requested["tokens"] > quota.tokens
                or requested["cpu_minutes"] > quota.cpu_minutes
                or requested["storage_bytes"] > quota.storage_bytes
                or requested["cost_micros"] > quota.cost_micros
            ):
                raise BudgetExceeded("tenant multidimensional quota exceeded")
            self._connection.execute(
                "UPDATE tenant_usage SET tokens=?,cpu_minutes=?,storage_bytes=?,cost_micros=? WHERE tenant_id=? AND window=?",
                (*requested.values(), lease.identity.tenant_id, lease.window),
            )

    def release(self, lease: AdmissionLease) -> None:
        with self._transaction():
            row = self._admission(lease)
            if row["state"] == "released":
                return
            if row["state"] == "active":
                self._connection.execute(
                    "UPDATE tenant_usage SET active=MAX(0,active-1) WHERE tenant_id=? AND window=?",
                    (lease.identity.tenant_id, lease.window),
                )
            else:
                self._connection.execute(
                    "UPDATE tenant_usage SET queued=MAX(0,queued-1) WHERE tenant_id=? AND window=?",
                    (lease.identity.tenant_id, lease.window),
                )
            self._connection.execute(
                "UPDATE admissions SET state='released' WHERE admission_id=?", (lease.admission_id,)
            )

    def _admission(self, lease: AdmissionLease) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM admissions WHERE admission_id=?", (lease.admission_id,)
        ).fetchone()
        if row is None:
            raise LeaseLost("admission is unavailable")
        stored_scope = (row["tenant_id"], row["project_id"], row["task_id"], row["run_id"], row["node_id"])
        if stored_scope != lease.identity.scope() or row["window"] != lease.window:
            raise TenantIsolationError("admission lease scope mismatch")
        return cast(sqlite3.Row, row)

    def _quota(self, tenant_id: str) -> TenantQuota:
        row = self._connection.execute(
            "SELECT quota_json FROM tenant_quotas WHERE tenant_id=?", (tenant_id,)
        ).fetchone()
        if row is None:
            raise BudgetExceeded("tenant quota is not configured")
        return TenantQuota(**json.loads(row["quota_json"]))


@dataclass(frozen=True, slots=True)
class SignedEventCursor:
    tenant_id: str
    project_id: str
    task_id: str
    run_id: str
    node_id: str
    after_seq: int
    head_digest: str
    signature: str


class ResumableEventStream(EventStream):
    def __init__(self, ledger: EventLedger, signing_key: bytes) -> None:
        super().__init__(ledger)
        if len(signing_key) < 32:
            raise ContractViolation("event cursor signing key must be at least 256 bits")
        self.signing_key = signing_key

    def cursor(self, identity: Identity, *, after_seq: int) -> SignedEventCursor:
        self.ledger.assert_identity(identity)
        events = self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000)
        if after_seq < -1 or after_seq >= len(events):
            raise ContractViolation("event cursor sequence is outside the durable stream")
        head = "genesis" if after_seq == -1 else str(events[after_seq].digest)
        body = f"{identity.tenant_id}\n{identity.project_id}\n{identity.task_id}\n{identity.run_id}\n{identity.node_id}\n{after_seq}\n{head}".encode()
        signature = hmac.new(self.signing_key, body, hashlib.sha256).hexdigest()
        return SignedEventCursor(
            identity.tenant_id,
            identity.project_id,
            identity.task_id,
            identity.run_id,
            identity.node_id,
            after_seq,
            head,
            signature,
        )

    def resume(self, identity: Identity, cursor: SignedEventCursor, *, limit: int = 100) -> tuple[Event, ...]:
        if (
            cursor.tenant_id,
            cursor.project_id,
            cursor.task_id,
            cursor.run_id,
            cursor.node_id,
        ) != identity.scope():
            raise TenantIsolationError("event cursor scope mismatch")
        self.ledger.assert_identity(identity)
        body = f"{cursor.tenant_id}\n{cursor.project_id}\n{cursor.task_id}\n{cursor.run_id}\n{cursor.node_id}\n{cursor.after_seq}\n{cursor.head_digest}".encode()
        signature = hmac.new(self.signing_key, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, cursor.signature):
            raise ContractViolation("event cursor is stale or tampered")
        events = self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000)
        actual = (
            "genesis"
            if cursor.after_seq == -1
            else (str(events[cursor.after_seq].digest) if cursor.after_seq < len(events) else "missing")
        )
        if actual != cursor.head_digest:
            raise ContractViolation("event cursor no longer binds the durable stream")
        return self.read(identity, after_seq=cursor.after_seq, limit=limit)


class RollingDeploymentController:
    def __init__(self, registry: DurableWorkerRegistry) -> None:
        self.registry = registry

    def begin(self, workers: Iterable[DurableWorkerLease], *, target_version: str) -> tuple[str, ...]:
        draining: list[str] = []
        for worker in workers:
            if worker.deployment_version != target_version:
                self.registry.drain(worker)
                draining.append(worker.worker_id)
        return tuple(draining)

    def safe_to_remove(self, worker_id: str) -> bool:
        worker = self.registry.get(worker_id)
        return worker.draining and self.registry.assignments(worker_id) == 0
