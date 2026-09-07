"""Run journal, finite-state machine and worker leases.

The journal is the recoverable truth. Materialised rows in SQLite/PostgreSQL
are a cache of it: :meth:`RunJournal.reconcile` rebuilds and cross-checks them
after a crash, detecting both sequence gaps and duplicate delivery.

Ownership is ``lease_id`` plus a monotonic ``lease_epoch``. Recovery bumps the
epoch when it claims a node, which is what makes a stale worker's later commit
impossible rather than merely unlikely.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .atomic import atomic_write_bytes
from .canonical import canonical_json_bytes, digest_of, fsync_directory
from .clock import SYSTEM_CLOCK, Clock, iso
from .db import MetadataStore
from .db.records import NodeRecord
from .db.store import new_id
from .enums import NODE_TRANSITIONS, NodeStatus, RunStatus
from .errors import ConflictError, InvalidTransition, NotFound, StaleLease

SCHEMA_VERSION = "1.0.0"
DEFAULT_LEASE_SECONDS = 60.0
DEFAULT_HEARTBEAT_SECONDS = 15.0


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    event_type: str
    actor: str
    run_id: str
    node_id: str | None = None
    attempt: int | None = None
    lease_epoch: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    recorded_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "actor": self.actor,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "attempt": self.attempt,
            "lease_epoch": self.lease_epoch,
            "payload": self.payload,
            "payload_digest": digest_of(self.payload),
            "correlation_id": self.correlation_id,
            "recorded_at": iso(self.recorded_at),
        }


class RunJournal:
    """Append-only NDJSON, fsynced per record, with strict sequence checking."""

    def __init__(self, path: Path, run_id: str, clock: Clock = SYSTEM_CLOCK) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._sequence = self._last_sequence()

    def _last_sequence(self) -> int:
        events = self.read_all()
        return events[-1].sequence if events else 0

    @property
    def sequence(self) -> int:
        return self._sequence

    def append(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        node_id: str | None = None,
        attempt: int | None = None,
        lease_epoch: int | None = None,
        correlation_id: str | None = None,
    ) -> JournalEvent:
        with self._lock:
            event = JournalEvent(
                sequence=self._sequence + 1,
                event_type=event_type,
                actor=actor,
                run_id=self.run_id,
                node_id=node_id,
                attempt=attempt,
                lease_epoch=lease_epoch,
                payload=payload or {},
                correlation_id=correlation_id,
                recorded_at=self.clock.now(),
            )
            line = canonical_json_bytes(event.to_dict()) + b"\n"
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            handle = os.open(self.path, flags, 0o600)
            try:
                os.write(handle, line)
                os.fsync(handle)
            finally:
                os.close(handle)
            fsync_directory(self.path.parent)
            self._sequence = event.sequence
            return event

    def read_all(self) -> list[JournalEvent]:
        """Read and validate. A gap means the journal cannot be trusted."""
        import json

        if not self.path.exists():
            return []
        events: list[JournalEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    # A torn final record from a kill mid-append: everything
                    # before it is still valid, so stop rather than fail.
                    if line_number == _count_lines(self.path):
                        break
                    raise ConflictError(
                        "journal contains an unreadable record", line=line_number, run_id=self.run_id
                    ) from None
                expected = len(events) + 1
                if data.get("sequence") != expected:
                    raise ConflictError(
                        "journal sequence gap",
                        line=line_number,
                        expected=expected,
                        found=data.get("sequence"),
                    )
                if digest_of(data.get("payload", {})) != data.get("payload_digest"):
                    raise ConflictError("journal payload digest mismatch", sequence=expected)
                events.append(
                    JournalEvent(
                        sequence=int(data["sequence"]),
                        event_type=data["event_type"],
                        actor=data["actor"],
                        run_id=data["run_id"],
                        node_id=data.get("node_id"),
                        attempt=data.get("attempt"),
                        lease_epoch=data.get("lease_epoch"),
                        payload=data.get("payload", {}),
                        correlation_id=data.get("correlation_id"),
                    )
                )
        return events

    def since(self, sequence: int) -> list[JournalEvent]:
        return [event for event in self.read_all() if event.sequence > sequence]


def _count_lines(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


@dataclass(frozen=True)
class Lease:
    lease_id: str
    run_id: str
    node_id: str
    attempt: int
    epoch: int
    expires_at: float

    def valid_at(self, now: float) -> bool:
        return now < self.expires_at


class LeaseManager:
    """Claim, heartbeat, expire, and reclaim node ownership."""

    def __init__(
        self,
        store: MetadataStore,
        clock: Clock = SYSTEM_CLOCK,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self.store = store
        self.clock = clock
        self.lease_seconds = lease_seconds

    def claim(self, run_id: str, node_id: str, attempt: int, worker: str) -> Lease:
        node = self.store.get_node(run_id, node_id, attempt)
        lease_id = f"lease-{worker}-{new_id('l')[2:10]}"
        claimed = self.store.claim_node(
            run_id, node_id, attempt, lease_id, self.lease_seconds, node.version, bump_epoch=True
        )
        return Lease(
            lease_id=lease_id,
            run_id=run_id,
            node_id=node_id,
            attempt=attempt,
            epoch=claimed.lease_epoch,
            expires_at=claimed.lease_expires_at or (self.clock.now() + self.lease_seconds),
        )

    def heartbeat(self, lease: Lease) -> Lease:
        node = self.store.heartbeat_node(
            lease.run_id, lease.node_id, lease.attempt, lease.lease_id, lease.epoch, self.lease_seconds
        )
        return Lease(
            lease_id=lease.lease_id,
            run_id=lease.run_id,
            node_id=lease.node_id,
            attempt=lease.attempt,
            epoch=node.lease_epoch,
            expires_at=node.lease_expires_at or (self.clock.now() + self.lease_seconds),
        )

    def assert_current(self, lease: Lease) -> NodeRecord:
        node = self.store.assert_lease(lease.run_id, lease.node_id, lease.attempt, lease.epoch)
        if node.lease_id != lease.lease_id:
            raise StaleLease(
                "another worker holds this node", node_id=lease.node_id, holder=node.lease_id
            )
        return node

    def expired(self) -> list[NodeRecord]:
        return self.store.expired_nodes(self.clock.now())

    def reclaim(self, node: NodeRecord, worker: str = "recovery") -> Lease:
        """Recovery claim. The epoch bump is what fences the previous owner."""
        return self.claim(node.run_id, node.node_id, node.attempt, worker)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    multiplier: float = 2.0

    def delay_for(self, attempt: int) -> float:
        delay = self.base_delay_seconds * (self.multiplier ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)

    def exhausted(self, retries: int) -> bool:
        return retries >= self.max_attempts


class RunCoordinator:
    """Drives run/node state, keeping the journal and the database in step.

    Every externally visible transition appends a journal record in the same
    logical step as the row update, so a crash can leave at most one of them
    un-applied -- and :meth:`reconcile` can tell which.
    """

    def __init__(
        self,
        store: MetadataStore,
        journal: RunJournal,
        leases: LeaseManager,
        actor: str = "coordinator",
        retry_policy: RetryPolicy | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self.store = store
        self.journal = journal
        self.leases = leases
        self.actor = actor
        self.retry_policy = retry_policy or RetryPolicy()
        self.clock = clock

    # -- run --------------------------------------------------------------
    def start_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        self.store.transition_run(run_id, RunStatus.RUNNING, run.version)
        self._emit("RUN_STARTED", {"run_id": run_id})

    def pause_run(self, run_id: str) -> None:
        """Safe at stage, side-effect and staged-file boundaries only."""
        run = self.store.get_run(run_id)
        self.store.transition_run(run_id, RunStatus.PAUSED, run.version)
        for node in self.store.list_nodes(run_id):
            if node.status in (NodeStatus.PENDING, NodeStatus.READY):
                self.store.transition_node(
                    run_id, node.node_id, node.attempt, NodeStatus.PAUSED, node.version
                )
        self._emit("RUN_PAUSED", {"run_id": run_id})

    def resume_run(self, run_id: str) -> None:
        run = self.store.get_run(run_id)
        self.store.transition_run(run_id, RunStatus.RUNNING, run.version)
        for node in self.store.list_nodes(run_id):
            if node.status is NodeStatus.PAUSED:
                self.store.transition_node(
                    run_id, node.node_id, node.attempt, NodeStatus.READY, node.version
                )
        self._emit("RUN_RESUMED", {"run_id": run_id})

    def cancel_run(self, run_id: str, reason: str) -> None:
        """Cancellation preserves evidence: nothing is deleted, only stopped."""
        run = self.store.get_run(run_id)
        self.store.transition_run(run_id, RunStatus.CANCELED, run.version)
        for node in self.store.list_nodes(run_id):
            if node.status not in (
                NodeStatus.SUCCEEDED,
                NodeStatus.FAILED_FINAL,
                NodeStatus.CANCELED,
            ):
                self.store.transition_node(
                    run_id,
                    node.node_id,
                    node.attempt,
                    NodeStatus.CANCELED,
                    node.version,
                    error_code="CANCELED",
                    error_details={"reason": reason},
                )
        self._emit("RUN_CANCELED", {"run_id": run_id, "reason": reason})

    def finish_run(self, run_id: str, succeeded: bool) -> None:
        run = self.store.get_run(run_id)
        target = RunStatus.SUCCEEDED if succeeded else RunStatus.FAILED
        self.store.transition_run(run_id, target, run.version)
        self._emit("RUN_FINISHED", {"run_id": run_id, "status": str(target)})

    # -- nodes ------------------------------------------------------------
    def mark_ready(self, run_id: str, node_id: str, attempt: int = 1) -> NodeRecord:
        node = self.store.get_node(run_id, node_id, attempt)
        updated = self.store.transition_node(run_id, node_id, attempt, NodeStatus.READY, node.version)
        self._emit("NODE_READY", {}, node_id, attempt)
        return updated

    def begin(self, run_id: str, node_id: str, attempt: int, worker: str) -> tuple[NodeRecord, Lease]:
        lease = self.leases.claim(run_id, node_id, attempt, worker)
        node = self.store.get_node(run_id, node_id, attempt)
        updated = self.store.transition_node(
            run_id, node_id, attempt, NodeStatus.RUNNING, node.version, lease_epoch=lease.epoch
        )
        self._emit("NODE_STARTED", {"worker": worker}, node_id, attempt, lease.epoch)
        return updated, lease

    def checkpointed(self, lease: Lease, checkpoint_id: str) -> NodeRecord:
        self.leases.assert_current(lease)
        node = self.store.get_node(lease.run_id, lease.node_id, lease.attempt)
        updated = self.store.transition_node(
            lease.run_id,
            lease.node_id,
            lease.attempt,
            NodeStatus.CHECKPOINTED,
            node.version,
            lease_epoch=lease.epoch,
        )
        self._emit(
            "NODE_CHECKPOINTED",
            {"checkpoint_id": checkpoint_id},
            lease.node_id,
            lease.attempt,
            lease.epoch,
        )
        return updated

    def succeed(self, lease: Lease, outcome: str = "OK", action_key: str | None = None) -> NodeRecord:
        self.leases.assert_current(lease)
        node = self.store.get_node(lease.run_id, lease.node_id, lease.attempt)
        updated = self.store.transition_node(
            lease.run_id,
            lease.node_id,
            lease.attempt,
            NodeStatus.SUCCEEDED,
            node.version,
            lease_epoch=lease.epoch,
            outcome=outcome,
        )
        self._emit(
            "NODE_SUCCEEDED",
            {"outcome": outcome, "action_key": action_key},
            lease.node_id,
            lease.attempt,
            lease.epoch,
        )
        return updated

    def fail(
        self, lease: Lease, error_code: str, retryable: bool, details: dict[str, Any] | None = None
    ) -> NodeRecord:
        self.leases.assert_current(lease)
        node = self.store.get_node(lease.run_id, lease.node_id, lease.attempt)
        exhausted = self.retry_policy.exhausted(node.retries + 1)
        target = NodeStatus.FAILED_RETRYABLE if retryable and not exhausted else NodeStatus.FAILED_FINAL
        updated = self.store.transition_node(
            lease.run_id,
            lease.node_id,
            lease.attempt,
            target,
            node.version,
            lease_epoch=lease.epoch,
            error_code=error_code,
            error_details=details,
        )
        self._emit(
            "NODE_FAILED",
            {
                "error_code": error_code,
                "retryable": retryable,
                "poison": target is NodeStatus.FAILED_FINAL and retryable,
                "retries": node.retries,
            },
            lease.node_id,
            lease.attempt,
            lease.epoch,
        )
        return updated

    def retry(self, run_id: str, node_id: str, attempt: int) -> NodeRecord:
        """Open a fresh attempt; the previous attempt's record is retained."""
        node = self.store.get_node(run_id, node_id, attempt)
        if node.status is not NodeStatus.FAILED_RETRYABLE:
            raise InvalidTransition(
                "only retryable failures may be retried", node_id=node_id, status=str(node.status)
            )
        if self.retry_policy.exhausted(node.retries + 1):
            self.store.transition_node(
                run_id, node_id, attempt, NodeStatus.FAILED_FINAL, node.version, error_code="RETRY_BUDGET"
            )
            self._emit("NODE_POISONED", {"retries": node.retries}, node_id, attempt)
            raise ConflictError("retry budget exhausted", node_id=node_id, retries=node.retries)
        next_attempt = self.store.latest_attempt(run_id, node_id) + 1
        created = self.store.upsert_node(
            run_id,
            node_id,
            node.stage_id,
            node.stage_version,
            attempt=next_attempt,
            status=NodeStatus.READY,
            action_key=node.action_key,
            retry_budget=node.retry_budget,
        )
        self.store.execute(
            "UPDATE run_nodes SET retries=? WHERE run_id=? AND node_id=? AND attempt=?",
            (node.retries + 1, run_id, node_id, next_attempt),
        )
        self._emit(
            "NODE_RETRY_SCHEDULED",
            {
                "previous_attempt": attempt,
                "attempt": next_attempt,
                "delay_seconds": self.retry_policy.delay_for(node.retries + 1),
            },
            node_id,
            next_attempt,
        )
        return created

    def recover_expired(self) -> list[dict[str, Any]]:
        """Fence expired workers and put their nodes back in play."""
        recovered: list[dict[str, Any]] = []
        for node in self.leases.expired():
            previous_epoch = node.lease_epoch
            self.store.transition_node(
                node.run_id, node.node_id, node.attempt, NodeStatus.STALE, node.version
            )
            stale = self.store.get_node(node.run_id, node.node_id, node.attempt)
            self.store.transition_node(
                node.run_id, node.node_id, node.attempt, NodeStatus.RECOVERING, stale.version
            )
            lease = self.leases.reclaim(self.store.get_node(node.run_id, node.node_id, node.attempt))
            self._emit(
                "NODE_RECOVERED",
                {"previous_lease_epoch": previous_epoch, "lease_epoch": lease.epoch},
                node.node_id,
                node.attempt,
                lease.epoch,
            )
            recovered.append(
                {
                    "node_id": node.node_id,
                    "attempt": node.attempt,
                    "previous_lease_epoch": previous_epoch,
                    "lease_epoch": lease.epoch,
                }
            )
        return recovered

    # -- journal ----------------------------------------------------------
    def _emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        node_id: str | None = None,
        attempt: int | None = None,
        lease_epoch: int | None = None,
    ) -> JournalEvent:
        event = self.journal.append(
            event_type, self.actor, payload, node_id=node_id, attempt=attempt, lease_epoch=lease_epoch
        )
        run = self.store.get_run(self.journal.run_id)
        self.store.append_event(
            tenant_id=run.tenant_id,
            run_id=run.run_id,
            node_id=node_id,
            sequence=event.sequence,
            event_type=event_type,
            actor=self.actor,
            payload=event.payload,
            lease_epoch=lease_epoch,
            project_id=run.project_id,
        )
        return event

    def deliver(self, event: JournalEvent) -> bool:
        """Idempotent event ingestion. Duplicate delivery changes nothing."""
        run = self.store.get_run(self.journal.run_id)
        return self.store.append_event(
            tenant_id=run.tenant_id,
            run_id=run.run_id,
            node_id=event.node_id,
            sequence=event.sequence,
            event_type=event.event_type,
            actor=event.actor,
            payload=event.payload,
            lease_epoch=event.lease_epoch,
            project_id=run.project_id,
        )

    def reconcile(self) -> dict[str, Any]:
        """Cross-check the journal against materialised rows after a crash."""
        events = self.journal.read_all()
        materialised = {row["sequence"]: row for row in self.store.list_events(self.journal.run_id)}
        missing = [event.sequence for event in events if event.sequence not in materialised]
        extra = sorted(set(materialised) - {event.sequence for event in events})
        mismatched = [
            event.sequence
            for event in events
            if event.sequence in materialised
            and materialised[event.sequence]["payload_digest"] != digest_of(event.payload)
        ]

        run = self.store.get_run(self.journal.run_id)
        for sequence in missing:
            event = events[sequence - 1]
            self.store.append_event(
                tenant_id=run.tenant_id,
                run_id=run.run_id,
                node_id=event.node_id,
                sequence=event.sequence,
                event_type=event.event_type,
                actor=event.actor,
                payload=event.payload,
                lease_epoch=event.lease_epoch,
                project_id=run.project_id,
            )

        node_states = {
            f"{node.node_id}#{node.attempt}": str(node.status) for node in self.store.list_nodes(run.run_id)
        }
        return {
            "journal_events": len(events),
            "replayed": missing,
            "materialised_only": extra,
            "payload_mismatches": mismatched,
            "node_states": node_states,
            "journal_sequence": events[-1].sequence if events else 0,
        }

    def rebuild_state(self) -> dict[str, str]:
        """Derive node states from the journal alone, for cross-checking rows."""
        derived: dict[str, str] = {}
        transitions = {
            "NODE_READY": NodeStatus.READY,
            "NODE_STARTED": NodeStatus.RUNNING,
            "NODE_CHECKPOINTED": NodeStatus.CHECKPOINTED,
            "NODE_SUCCEEDED": NodeStatus.SUCCEEDED,
            "NODE_RECOVERED": NodeStatus.RECOVERING,
            "NODE_POISONED": NodeStatus.FAILED_FINAL,
        }
        for event in self.journal.read_all():
            if event.node_id is None:
                continue
            key = f"{event.node_id}#{event.attempt}"
            if event.event_type in transitions:
                derived[key] = str(transitions[event.event_type])
            elif event.event_type == "NODE_FAILED":
                derived[key] = str(
                    NodeStatus.FAILED_FINAL
                    if event.payload.get("poison") or not event.payload.get("retryable")
                    else NodeStatus.FAILED_RETRYABLE
                )
            elif event.event_type == "RUN_CANCELED":
                for existing in list(derived):
                    if derived[existing] not in (str(NodeStatus.SUCCEEDED), str(NodeStatus.FAILED_FINAL)):
                        derived[existing] = str(NodeStatus.CANCELED)
        return dict(sorted(derived.items()))


def legal_transitions(status: NodeStatus) -> tuple[NodeStatus, ...]:
    return tuple(sorted(NODE_TRANSITIONS[status], key=str))


def write_run_control(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_bytes(path, canonical_json_bytes(payload) + b"\n")


def replay(events: Sequence[JournalEvent], handlers: Iterable[Any]) -> int:
    applied = 0
    for event in events:
        for handler in handlers:
            if handler(event):
                applied += 1
    return applied


__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_LEASE_SECONDS",
    "JournalEvent",
    "Lease",
    "LeaseManager",
    "NotFound",
    "RetryPolicy",
    "RunCoordinator",
    "RunJournal",
    "legal_transitions",
    "replay",
    "write_run_control",
]
