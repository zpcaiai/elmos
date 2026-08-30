"""Durable turn supervision, deadline enforcement and run reconciliation."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .errors import ContractViolation, TenantIsolationError
from .models import Identity, digest_of

TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})


class RuntimeLedger(Protocol):
    def append(self, identity: Identity, event_type: str, payload: dict[str, Any], **kwargs: Any) -> Any: ...
    def events(self, tenant_id: str, run_id: str, *, after_seq: int = -1, limit: int = 1000) -> list[Any]: ...
    def run(self, tenant_id: str, run_id: str, node_id: str = "root") -> Any: ...
    def rebuild_projection(self, tenant_id: str, run_id: str) -> dict[str, Any]: ...
    def verify_chain(self, tenant_id: str, run_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class SupervisionRecord:
    identity: Identity
    state: str
    stage: str
    heartbeat_epoch: float
    deadline_epoch: float
    cancel_requested: bool
    cancel_reason: str | None
    cancel_actor: str | None
    version: int


@dataclass(frozen=True, slots=True)
class SupervisorDecision:
    identity: Identity
    decision: str
    reason: str
    version: int


class SupervisorStore:
    """SQLite reference store; production uses the same columns in PostgreSQL."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS runtime_supervision(
               tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,
               run_id TEXT NOT NULL,node_id TEXT NOT NULL,agent_id TEXT,state TEXT NOT NULL,
               stage TEXT NOT NULL,heartbeat_epoch REAL NOT NULL,deadline_epoch REAL NOT NULL,
               cancel_requested INTEGER NOT NULL DEFAULT 0,cancel_reason TEXT,cancel_actor TEXT,
               version INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY(tenant_id,run_id,node_id))"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def register(self, identity: Identity, *, deadline_epoch: float, now: float | None = None) -> SupervisionRecord:
        now = time.time() if now is None else now
        if deadline_epoch <= now:
            raise ContractViolation("run deadline must be in the future")
        with self._lock:
            self._connection.execute(
                """INSERT INTO runtime_supervision
                   (tenant_id,project_id,task_id,run_id,node_id,agent_id,state,stage,
                    heartbeat_epoch,deadline_epoch,cancel_requested,version)
                   VALUES(?,?,?,?,?,?, 'ready','registered',?,?,0,0)
                   ON CONFLICT(tenant_id,run_id,node_id) DO NOTHING""",
                (*identity.scope(), identity.agent_id, now, deadline_epoch),
            )
        record = self.get(identity)
        if record.deadline_epoch != deadline_epoch:
            raise ContractViolation("supervisor registration cannot mutate the original deadline")
        return record

    def heartbeat(self, identity: Identity, stage: str, *, state: str = "running", now: float | None = None) -> SupervisionRecord:
        now = time.time() if now is None else now
        if not stage or state in TERMINAL_STATES:
            raise ContractViolation("heartbeat requires a non-terminal stage")
        self.get(identity)
        with self._lock:
            updated = self._connection.execute(
                """UPDATE runtime_supervision SET heartbeat_epoch=?,stage=?,state=?,version=version+1
                   WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=?
                   AND state NOT IN ('succeeded','failed','cancelled')""",
                (now, stage[:128], state, *identity.scope()),
            ).rowcount
        if updated != 1:
            raise ContractViolation("run is absent or terminal in supervisor")
        return self.get(identity)

    def request_cancel(self, identity: Identity, actor: str, reason: str) -> SupervisionRecord:
        if not actor.strip() or not reason.strip():
            raise ContractViolation("cancellation requires actor and reason")
        self.get(identity)
        with self._lock:
            updated = self._connection.execute(
                """UPDATE runtime_supervision SET cancel_requested=1,cancel_actor=?,cancel_reason=?,
                   version=version+1 WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=?
                   AND state NOT IN ('succeeded','failed','cancelled')""",
                (actor[:128], reason[:1000], *identity.scope()),
            ).rowcount
        if updated != 1:
            raise ContractViolation("only a live supervised run can be cancelled")
        return self.get(identity)

    def mark(self, identity: Identity, state: str, stage: str, *, now: float | None = None) -> SupervisionRecord:
        if state not in {"ready", "running", "waiting", "blocked", *TERMINAL_STATES}:
            raise ContractViolation("invalid supervisor state")
        now = time.time() if now is None else now
        self.get(identity)
        with self._lock:
            updated = self._connection.execute(
                """UPDATE runtime_supervision SET state=?,stage=?,heartbeat_epoch=?,version=version+1
                   WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=?""",
                (state, stage[:128], now, *identity.scope()),
            ).rowcount
        if updated != 1:
            raise KeyError(identity.run_id)
        return self.get(identity)

    def get(self, identity: Identity) -> SupervisionRecord:
        row = self._connection.execute(
            "SELECT * FROM runtime_supervision WHERE tenant_id=? AND run_id=? AND node_id=?",
            (identity.tenant_id, identity.run_id, identity.node_id),
        ).fetchone()
        if row is None:
            raise KeyError(identity.run_id)
        record = self._record(row)
        if record.identity.scope() != identity.scope():
            raise TenantIsolationError("supervised run does not belong to the requested project/task")
        return record

    def live(self) -> tuple[SupervisionRecord, ...]:
        rows = self._connection.execute(
            "SELECT * FROM runtime_supervision WHERE state NOT IN ('succeeded','failed','cancelled') ORDER BY tenant_id,run_id,node_id"
        ).fetchall()
        return tuple(self._record(row) for row in rows)

    @staticmethod
    def _record(row: sqlite3.Row) -> SupervisionRecord:
        identity = Identity(row["tenant_id"], row["project_id"], row["task_id"], row["run_id"], row["node_id"], row["agent_id"])
        return SupervisionRecord(
            identity,
            row["state"],
            row["stage"],
            float(row["heartbeat_epoch"]),
            float(row["deadline_epoch"]),
            bool(row["cancel_requested"]),
            row["cancel_reason"],
            row["cancel_actor"],
            int(row["version"]),
        )


class RuntimeSupervisor:
    def __init__(self, store: SupervisorStore, ledger: RuntimeLedger, *, stuck_after_seconds: float = 120.0) -> None:
        if stuck_after_seconds <= 0:
            raise ContractViolation("stuck timeout must be positive")
        self.store = store
        self.ledger = ledger
        self.stuck_after_seconds = stuck_after_seconds

    def register(self, identity: Identity, *, deadline_epoch: float, now: float | None = None) -> SupervisionRecord:
        record = self.store.register(identity, deadline_epoch=deadline_epoch, now=now)
        self.ledger.append(
            identity,
            "supervisor.registered",
            {"deadline_epoch": deadline_epoch, "stuck_after_seconds": self.stuck_after_seconds},
            idempotency_key=f"supervisor-register:{identity.node_id}",
        )
        return record

    def before_turn(self, identity: Identity, *, now: float | None = None) -> None:
        now = time.time() if now is None else now
        record = self.store.get(identity)
        if record.cancel_requested:
            raise ContractViolation("run cancellation is pending", code="CANCEL_REQUESTED")
        if record.deadline_epoch <= now:
            raise ContractViolation("run deadline exceeded", code="DEADLINE_EXCEEDED")
        self.store.heartbeat(identity, "turn-start", now=now)

    def heartbeat(self, identity: Identity, stage: str, *, now: float | None = None) -> SupervisionRecord:
        record = self.store.heartbeat(identity, stage, now=now)
        self.ledger.append(
            identity,
            "supervisor.heartbeat",
            {"stage": stage, "version": record.version},
            idempotency_key=f"supervisor-heartbeat:{identity.node_id}:{record.version}",
        )
        return record

    def complete_turn(self, identity: Identity, state: str, *, now: float | None = None) -> None:
        self.store.mark(identity, state, "turn-complete", now=now)

    def request_cancel(self, identity: Identity, actor: str, reason: str) -> SupervisionRecord:
        record = self.store.request_cancel(identity, actor, reason)
        self.ledger.append(
            identity,
            "run.cancel.requested",
            {"actor": actor, "reason": reason, "version": record.version},
            idempotency_key=f"cancel-request:{identity.node_id}:{record.version}",
        )
        return record

    def sweep(self, *, now: float | None = None) -> tuple[SupervisorDecision, ...]:
        now = time.time() if now is None else now
        decisions: list[SupervisorDecision] = []
        for record in self.store.live():
            decision: str | None = None
            reason = ""
            terminal = ""
            if record.cancel_requested:
                decision, reason, terminal = "cancel", record.cancel_reason or "cancel requested", "cancelled"
            elif record.deadline_epoch <= now:
                decision, reason, terminal = "deadline", "run deadline exceeded", "cancelled"
            elif record.state == "running" and record.heartbeat_epoch + self.stuck_after_seconds <= now:
                decision, reason, terminal = "stuck", "turn heartbeat expired", "blocked"
            if decision is None:
                continue
            current = self.store.mark(record.identity, terminal, decision, now=now)
            payload = {"decision": decision, "reason": reason, "supervisor_version": current.version}
            self.ledger.append(
                record.identity,
                "supervisor.decision",
                payload,
                idempotency_key=f"supervisor-decision:{record.identity.node_id}:{current.version}",
            )
            self.ledger.append(
                record.identity,
                "run.status",
                {"status": terminal, "reason": decision},
                idempotency_key=f"supervisor-status:{record.identity.node_id}:{current.version}",
            )
            decisions.append(SupervisorDecision(record.identity, decision, reason, current.version))
        return tuple(decisions)


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    identity: Identity
    chain_valid: bool
    run_status: str
    projected_status: str
    unfinished_actions: tuple[str, ...]
    projection_digest: str
    repaired: bool


class RunStateReconciler:
    """Rebuilds authoritative state and reports unfinished side effects."""

    def __init__(self, ledger: RuntimeLedger) -> None:
        self.ledger = ledger

    def reconcile(self, identity: Identity, *, repair_status: bool = True) -> ReconciliationReport:
        chain_valid = self.ledger.verify_chain(identity.tenant_id, identity.run_id)
        projection = self.ledger.rebuild_projection(identity.tenant_id, identity.run_id)
        run = self.ledger.run(identity.tenant_id, identity.run_id, identity.node_id)
        proposed: dict[str, str] = {}
        observed: set[str] = set()
        for event in self.ledger.events(identity.tenant_id, identity.run_id, limit=100_000):
            if event.event_type == "action.proposed":
                proposed[str(event.payload.get("action_id", ""))] = str(event.idempotency_key or "")
            elif event.event_type == "tool.observed":
                observed.add(str(event.payload.get("action_id", "")))
        unfinished = tuple(sorted(action_id for action_id in proposed if action_id and action_id not in observed))
        projected_status = str(projection.get("status", run.status))
        repaired = False
        if repair_status and run.status != projected_status:
            body = {"status": projected_status, "reason": "projection_reconciliation"}
            self.ledger.append(
                identity,
                "run.status",
                body,
                idempotency_key="reconciled-status:" + digest_of({"run": identity.run_id, **body}),
            )
            repaired = True
        return ReconciliationReport(
            identity,
            chain_valid,
            run.status,
            projected_status,
            unfinished,
            digest_of(projection),
            repaired,
        )
