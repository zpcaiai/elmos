#!/usr/bin/env python3
"""Durable workflow runtime: leases, idempotent events, rollback.

Design points that the conformance suite exercises directly:

* **Idempotency** - an event carries an id; delivering it twice produces one
  effect and the second delivery is reported as a duplicate.
* **Leases** - a runner holds a time-bounded lease.  If the runner disconnects,
  the lease expires and the run moves to ``reconciling`` rather than being lost
  or double-executed.
* **Compensation** - every step may register an undo.  Failure runs the undos
  in reverse order, and a compensation that itself fails escalates instead of
  being swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable

from scripts.modernization_b01_44.canonical import digest, format_instant, parse_instant
from scripts.modernization_b01_44.errors import (
    LeaseExpired,
    TenantIsolationViolation,
    WorkflowError,
)

TERMINAL_STATES = frozenset({"completed", "failed", "cancelled", "compensated"})

#: Allowed transitions.  Anything else is refused, so an illegal state change
#: cannot be reached even by a buggy caller.
TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"running", "cancelled"}),
    "running": frozenset({"awaiting_approval", "completed", "failed", "reconciling", "cancelled"}),
    "awaiting_approval": frozenset({"running", "cancelled", "failed"}),
    "reconciling": frozenset({"running", "failed", "compensated", "cancelled"}),
    "failed": frozenset({"compensating"}),
    "compensating": frozenset({"compensated", "failed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "compensated": frozenset(),
}

DEFAULT_LEASE = timedelta(minutes=5)


@dataclass
class Checkpoint:
    step: str
    output_digest: str
    at: str

    def as_dict(self) -> dict[str, Any]:
        return {"step": self.step, "output_digest": self.output_digest, "at": self.at}


@dataclass
class Lease:
    runner_id: str
    expires_at: str

    def is_expired(self, now: datetime) -> bool:
        return parse_instant(self.expires_at, "expires_at") <= now


@dataclass
class WorkflowRun:
    workflow_id: str
    definition_version: str
    tenant_id: str
    project_id: str
    state: str
    idempotency_key: str
    checkpoints: list[Checkpoint] = field(default_factory=list)
    approvals: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    lease: Lease | None = None
    applied_events: set[str] = field(default_factory=set)
    compensations: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def as_record(self) -> dict[str, Any]:
        """The schema-visible projection (matches ``workflow-run.schema.json``)."""

        return {
            "workflow_id": self.workflow_id,
            "definition_version": self.definition_version,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "state": self.state,
            "idempotency_key": self.idempotency_key,
            "checkpoints": [c.as_dict() for c in self.checkpoints],
            "approvals": list(self.approvals),
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class WorkflowRuntime:
    """Durable-by-construction run store with explicit state transitions."""

    def __init__(self, *, lease_duration: timedelta = DEFAULT_LEASE) -> None:
        self.lease_duration = lease_duration
        self._runs: dict[str, WorkflowRun] = {}
        self._by_idempotency: dict[str, str] = {}

    # -- lifecycle --------------------------------------------------------

    def start(
        self,
        *,
        definition_version: str,
        tenant_id: str,
        project_id: str,
        request: Any,
        now: datetime,
    ) -> tuple[WorkflowRun, bool]:
        """Start a run.  Returns ``(run, created)``; a repeat start is a no-op."""

        key = digest(
            {
                "definition_version": definition_version,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "request": request,
            }
        )
        existing_id = self._by_idempotency.get(key)
        if existing_id is not None:
            return self._runs[existing_id], False
        workflow_id = "wf-" + digest({"key": key, "at": format_instant(now)})[:24]
        run = WorkflowRun(
            workflow_id=workflow_id,
            definition_version=definition_version,
            tenant_id=tenant_id,
            project_id=project_id,
            state="created",
            idempotency_key=key,
        )
        run.history.append({"at": format_instant(now), "event": "created"})
        self._runs[workflow_id] = run
        self._by_idempotency[key] = workflow_id
        return run, True

    def get(self, workflow_id: str, *, tenant_id: str | None = None) -> WorkflowRun:
        try:
            run = self._runs[workflow_id]
        except KeyError:
            raise WorkflowError("unknown workflow run", workflow_id=workflow_id) from None
        if tenant_id is not None and run.tenant_id != tenant_id:
            raise TenantIsolationViolation(
                "workflow run belongs to a different tenant", workflow_id=workflow_id
            )
        return run

    def transition(self, run: WorkflowRun, target: str, *, now: datetime, reason: str = "") -> WorkflowRun:
        allowed = TRANSITIONS.get(run.state)
        if allowed is None:
            raise WorkflowError("unknown workflow state", state=run.state)
        if target not in allowed:
            raise WorkflowError(
                "illegal workflow transition", **{"from": run.state, "to": target}
            )
        run.state = target
        run.history.append({"at": format_instant(now), "event": f"->{target}", "reason": reason})
        return run

    # -- leases -----------------------------------------------------------

    def acquire_lease(self, run: WorkflowRun, runner_id: str, now: datetime) -> Lease:
        if run.lease is not None and not run.lease.is_expired(now) and run.lease.runner_id != runner_id:
            raise WorkflowError(
                "run is leased by another runner",
                workflow_id=run.workflow_id,
                holder=run.lease.runner_id,
            )
        run.lease = Lease(runner_id=runner_id, expires_at=format_instant(now + self.lease_duration))
        run.history.append({"at": format_instant(now), "event": "lease-acquired", "runner": runner_id})
        return run.lease

    def heartbeat(self, run: WorkflowRun, runner_id: str, now: datetime) -> Lease:
        if run.lease is None or run.lease.runner_id != runner_id:
            raise LeaseExpired("runner does not hold the lease", workflow_id=run.workflow_id)
        if run.lease.is_expired(now):
            raise LeaseExpired("lease already expired", workflow_id=run.workflow_id)
        run.lease = Lease(runner_id=runner_id, expires_at=format_instant(now + self.lease_duration))
        return run.lease

    def reap_expired_leases(self, now: datetime) -> list[str]:
        """Move runs whose runner vanished into ``reconciling``."""

        reaped: list[str] = []
        for workflow_id in sorted(self._runs):
            run = self._runs[workflow_id]
            if run.terminal or run.lease is None:
                continue
            if run.lease.is_expired(now) and run.state in ("running", "created"):
                if run.state == "created":
                    self.transition(run, "running", now=now, reason="lease-reap")
                self.transition(run, "reconciling", now=now, reason="lease-expired")
                run.lease = None
                reaped.append(workflow_id)
        return reaped

    # -- events -----------------------------------------------------------

    def apply_event(
        self,
        run: WorkflowRun,
        *,
        event_id: str,
        handler: Callable[[WorkflowRun], Any],
        now: datetime,
    ) -> tuple[Any, bool]:
        """Apply an event exactly once.  Returns ``(result, applied)``."""

        if event_id in run.applied_events:
            run.history.append({"at": format_instant(now), "event": "duplicate", "event_id": event_id})
            return None, False
        result = handler(run)
        run.applied_events.add(event_id)
        run.history.append({"at": format_instant(now), "event": "applied", "event_id": event_id})
        return result, True

    # -- steps and compensation -------------------------------------------

    def record_step(
        self,
        run: WorkflowRun,
        *,
        step: str,
        output: Any,
        now: datetime,
        undo: Callable[[], None] | None = None,
    ) -> Checkpoint:
        checkpoint = Checkpoint(step=step, output_digest=digest(output), at=format_instant(now))
        run.checkpoints.append(checkpoint)
        if undo is not None:
            run.compensations.append((step, undo))
        return checkpoint

    def compensate(self, run: WorkflowRun, now: datetime) -> list[str]:
        """Run undos newest-first.  A failing undo escalates, it is not hidden."""

        if run.state != "failed":
            self.transition(run, "failed", now=now, reason="compensation-requested")
        self.transition(run, "compensating", now=now)
        undone: list[str] = []
        failures: list[dict[str, str]] = []
        for step, undo in reversed(run.compensations):
            try:
                undo()
                undone.append(step)
            except Exception as exc:  # noqa: BLE001 - escalated below
                failures.append({"step": step, "error": str(exc)})
        run.compensations.clear()
        if failures:
            self.transition(run, "failed", now=now, reason="compensation-failed")
            raise WorkflowError(
                "compensation failed and requires manual recovery",
                workflow_id=run.workflow_id,
                failures=failures,
                undone=undone,
            )
        self.transition(run, "compensated", now=now)
        return undone

    # -- introspection ----------------------------------------------------

    def runs_for_tenant(self, tenant_id: str) -> list[WorkflowRun]:
        return [run for _, run in sorted(self._runs.items()) if run.tenant_id == tenant_id]

    def __len__(self) -> int:
        return len(self._runs)
