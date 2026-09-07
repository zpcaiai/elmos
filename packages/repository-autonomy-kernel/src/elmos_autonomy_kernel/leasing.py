"""Workspace Lease Fencing.

This module exists because of one specific, well-documented distributed-systems failure: a worker
acquires a lease, stops (GC pause, host freeze, network partition, a debugger), the lease expires,
a second worker takes over, and then the *first* worker wakes up and writes.  It has no idea
anything happened.  Nothing about its local state is wrong from its own point of view.  Only a
monotonically increasing token, checked by the thing being written to, can reject it.

So the discipline here is deliberately paranoid:

*The token is re-checked immediately before every write, not once at the start of the step.*
:meth:`LeaseManager.guard` and :class:`FencedWriter` both re-validate against the store at the
last possible moment.  A validity check performed a hundred milliseconds earlier proves nothing.

*A lease lost mid-write is INTERRUPTED, not FAILED.*  If the token was current before the write
and stale after it, the side effect may have landed and may not have.  Reporting that as a plain
failure invites a blind retry, which is exactly how a duplicate side effect is created.  The
error carries ``interrupted=True`` and points at reconciliation.

*A token is meaningless without its resource.*  Tokens are monotonic *per resource*, so resource
X and resource Y both start at 1.  Every validation is ``(resource_id, owner_id, token)``; a bare
integer is never accepted as proof of anything.

*Takeover requires a reason and leaves a record.*  An unexplained takeover is indistinguishable
from a split brain after the fact.

Deviation from the design direction, with reason: ``guard`` is a real context manager rather than
a bare pre-write check, and it re-validates on *exit* as well as entry.  The entry check alone
cannot see a lease that expired during a slow write, which is the case that produces a torn
workspace.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from .contracts import (
    digest,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
)
from .errors import Category, KernelError, register_codes
from .ports import Clock, EventStore, LeaseStore
from .registry import register

__all__ = [
    "FencedWriter",
    "Lease",
    "LeaseManager",
    "RecoveryPlan",
    "SideEffectStatus",
    "TakeoverRecord",
    "handle",
]

register_codes(Category.CONCURRENCY, "SIDE_EFFECT_AMBIGUOUS", "TAKEOVER_DENIED")
register_codes(Category.INTEGRITY, "CHECKPOINT_CORRUPT")

T = TypeVar("T")

#: A side effect is either known to have landed, known not to have landed, or unknown.  The third
#: state is not a bug in the ledger, it is the honest answer after a crash between the effect and
#: its confirmation — and it must never be collapsed into either of the other two.
SideEffectStatus = ("applied", "not-applied", "unknown")


@dataclass(frozen=True, slots=True)
class Lease:
    """Proof of exclusive ownership of one resource for one bounded window.

    The lease is a value, not a handle: holding it proves nothing on its own.  It is only
    meaningful when re-validated against the store, which is why every write path in this module
    takes the store as well as the lease.
    """

    resource_id: str
    owner_id: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime
    ttl_seconds: int

    def __post_init__(self) -> None:
        require_identifier(self.resource_id, "resource_id")
        require_identifier(self.owner_id, "owner_id")
        require_int(self.fencing_token, "fencing_token", minimum=1)
        require_int(self.ttl_seconds, "ttl_seconds", minimum=1)
        if self.expires_at <= self.acquired_at:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="lease expires_at must be strictly after acquired_at",
                recommended_action="acquire with a positive ttl",
            )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def to_payload(self) -> dict[str, Any]:
        core = {
            "resourceId": self.resource_id,
            "ownerId": self.owner_id,
            "fencingToken": self.fencing_token,
            "acquiredAt": format_timestamp(self.acquired_at),
            "expiresAt": format_timestamp(self.expires_at),
            "ttlSeconds": self.ttl_seconds,
        }
        return {**core, "digest": digest(core)}


@dataclass(frozen=True, slots=True)
class TakeoverRecord:
    """The audit trail of one ownership transfer.

    ``reason`` is mandatory.  Six months later, a takeover with no stated reason and a takeover
    caused by a split brain look identical, and only one of them is safe.
    """

    resource_id: str
    previous_owner: str
    previous_token: int
    new_owner: str
    new_token: int
    reason: str
    recorded_at: datetime
    event_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        core = {
            "type": "lease.takeover",
            "resourceId": self.resource_id,
            "previousOwner": self.previous_owner,
            "previousToken": self.previous_token,
            "newOwner": self.new_owner,
            "newToken": self.new_token,
            "reason": self.reason,
            "recordedAt": format_timestamp(self.recorded_at),
            "eventId": self.event_id,
        }
        return {**core, "digest": digest(core)}


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """What a new owner may do about side effects the previous owner started.

    The three buckets are kept apart on purpose.  ``reconcile`` is the dangerous one: those
    effects have unknown status, and replaying them blindly is how one refund becomes two.
    """

    resource_id: str
    checkpoint_id: str
    checkpoint_digest: str
    replay: tuple[str, ...]
    skip: tuple[str, ...]
    reconcile: tuple[str, ...]

    def assert_replayable(self) -> None:
        """Raise unless every effect has a known status.

        Callers that intend to replay call this first.  It is the guard on invariant I4: an
        unknown side effect is never blindly replayed.
        """

        if self.reconcile:
            raise KernelError(
                code="SIDE_EFFECT_AMBIGUOUS",
                message=(
                    f"{len(self.reconcile)} side effect(s) on {self.resource_id!r} have unknown "
                    f"status: {list(self.reconcile)}"
                ),
                retryable=False,
                recommended_action=(
                    "reconcile each effect against the external system before replaying anything"
                ),
                details={"reconcile": list(self.reconcile)},
            )

    def to_payload(self) -> dict[str, Any]:
        core = {
            "resourceId": self.resource_id,
            "checkpointId": self.checkpoint_id,
            "checkpointDigest": self.checkpoint_digest,
            "replay": list(self.replay),
            "skip": list(self.skip),
            "reconcile": list(self.reconcile),
            "blindReplayAllowed": not self.reconcile,
        }
        return {**core, "digest": digest(core)}


class LeaseManager:
    """Fencing discipline on top of a :class:`~.ports.LeaseStore`.

    The store issues monotonic tokens; this class adds the things that make those tokens actually
    protect a workspace — last-moment revalidation, explained takeover, an idempotent side-effect
    ledger, and recovery planning that refuses to guess.
    """

    __slots__ = ("_store", "_clock", "_events", "_takeovers")

    def __init__(self, store: LeaseStore, clock: Clock, *,
                 events: EventStore | None = None) -> None:
        self._store = store
        self._clock = clock
        self._events = events
        self._takeovers: list[TakeoverRecord] = []

    @property
    def takeovers(self) -> tuple[TakeoverRecord, ...]:
        return tuple(self._takeovers)

    # --- lifecycle -----------------------------------------------------------

    def acquire(self, resource_id: str, owner_id: str, *, ttl_seconds: int) -> Lease:
        """Acquire the lease, obtaining a token strictly greater than every prior token."""

        require_identifier(resource_id, "resource_id")
        require_identifier(owner_id, "owner_id")
        require_int(ttl_seconds, "ttl_seconds", minimum=1)
        granted = self._store.acquire(resource_id, owner_id, ttl_seconds=ttl_seconds)
        return self._lease_from(granted, ttl_seconds)

    def renew(self, lease: Lease, *, ttl_seconds: int) -> Lease:
        """Heartbeat.  Keeps the same token; a renewal never issues a new one."""

        return self.renew_token(lease.resource_id, lease.owner_id, lease.fencing_token,
                                ttl_seconds=ttl_seconds)

    def renew_token(self, resource_id: str, owner_id: str, fencing_token: int, *,
                    ttl_seconds: int) -> Lease:
        """Heartbeat from an identity triple, for a worker resuming without a Lease object."""

        require_identifier(resource_id, "resource_id")
        require_identifier(owner_id, "owner_id")
        require_int(fencing_token, "fencing_token", minimum=1)
        require_int(ttl_seconds, "ttl_seconds", minimum=1)
        granted = self._store.renew(resource_id, owner_id, fencing_token,
                                    ttl_seconds=ttl_seconds)
        return self._lease_from(granted, ttl_seconds)

    def release(self, lease: Lease) -> None:
        self._store.release(lease.resource_id, lease.owner_id, lease.fencing_token)

    def current_token(self, resource_id: str) -> int:
        """Current token for ``resource_id``; ``0`` means no lease was ever issued for it."""

        return self._store.current_token(resource_id)

    def takeover(self, resource_id: str, *, new_owner: str, reason: str, ttl_seconds: int,
                 previous_owner: str | None = None) -> tuple[Lease, TakeoverRecord]:
        """Transfer ownership, issuing a strictly greater token and recording why.

        A takeover of a *live* lease requires naming the previous owner: forcing an owner out
        without knowing who they were is not a takeover, it is a race.  A takeover of an expired
        lease needs no such argument, because the store will simply issue the next token.
        """

        require_identifier(resource_id, "resource_id")
        require_identifier(new_owner, "new_owner")
        require_int(ttl_seconds, "ttl_seconds", minimum=1)
        if not require_str(reason, "reason", max_length=512).strip():
            raise KernelError(
                code="MALFORMED_INPUT",
                message="takeover reason must be a non-empty explanation",
                recommended_action="state why ownership is being moved",
            )
        previous_token = self._store.current_token(resource_id)
        try:
            granted = self._store.acquire(resource_id, new_owner, ttl_seconds=ttl_seconds)
        except KernelError as exc:
            if exc.code != "LEASE_HELD_BY_OTHER":
                raise
            if previous_owner is None:
                raise KernelError(
                    code="TAKEOVER_DENIED",
                    message=(
                        f"{resource_id!r} is held by a live lease; name the previous owner to "
                        "take it over explicitly"
                    ),
                    retryable=False,
                    recommended_action="pass previous_owner, or wait for the lease to expire",
                ) from exc
            self._store.release(resource_id, previous_owner, previous_token)
            granted = self._store.acquire(resource_id, new_owner, ttl_seconds=ttl_seconds)

        lease = self._lease_from(granted, ttl_seconds)
        record = TakeoverRecord(
            resource_id=resource_id,
            previous_owner=previous_owner or "",
            previous_token=previous_token,
            new_owner=new_owner,
            new_token=lease.fencing_token,
            reason=reason,
            recorded_at=self._clock.now(),
        )
        if self._events is not None:
            stored = self._events.append(resource_id, record.to_payload(),
                                         fencing_token=lease.fencing_token)
            record = TakeoverRecord(
                resource_id=record.resource_id,
                previous_owner=record.previous_owner,
                previous_token=record.previous_token,
                new_owner=record.new_owner,
                new_token=record.new_token,
                reason=record.reason,
                recorded_at=record.recorded_at,
                event_id=stored.event_id,
            )
        self._takeovers.append(record)
        return lease, record

    # --- validation ----------------------------------------------------------

    def assert_current(self, resource_id: str, fencing_token: int) -> None:
        """Raise ``LEASE_LOST`` unless ``(resource, token)`` is the live lease.

        The resource is part of the identity on purpose: tokens are monotonic *per resource*, so
        token 3 on workspace A says nothing at all about workspace B.

        Ownership is not re-checked against the store here, and that is not an oversight: the
        port exposes no way to read the holder without ``renew``, and renewing during a *check*
        would silently extend the very lease being validated.  The store issues each token to
        exactly one owner, so a current token is already proof of who holds it.
        """

        current = self._store.current_token(resource_id)
        if current == 0:
            raise KernelError(
                code="LEASE_LOST",
                message=f"no lease has ever been issued for {resource_id!r}",
                retryable=False,
                recommended_action="acquire the lease before writing",
                details={"resourceId": resource_id, "presentedToken": fencing_token},
            )
        if fencing_token != current:
            raise KernelError(
                code="LEASE_LOST",
                message=(
                    f"fencing token {fencing_token} is not current for {resource_id!r}; "
                    f"the resource is at {current}"
                ),
                retryable=False,
                recommended_action="stop writing, re-acquire the lease and rebuild local state",
                details={"resourceId": resource_id, "presentedToken": fencing_token,
                         "currentToken": current},
            )

    def validate(self, lease: Lease) -> None:
        """Raise ``LEASE_LOST`` unless ``lease`` is still the live lease for its resource."""

        now = self._clock.now()
        if lease.is_expired(now):
            raise KernelError(
                code="LEASE_LOST",
                message=(
                    f"lease on {lease.resource_id!r} expired at "
                    f"{format_timestamp(lease.expires_at)}; now is {format_timestamp(now)}"
                ),
                retryable=False,
                recommended_action="re-acquire the lease and rebuild local state",
                details={"resourceId": lease.resource_id,
                         "presentedToken": lease.fencing_token},
            )
        self.assert_current(lease.resource_id, lease.fencing_token)

    @contextmanager
    def guard(self, lease: Lease) -> Iterator[Lease]:
        """Re-validate immediately before *and* after the guarded write.

        The entry check is the classic fencing check.  The exit check catches the case the entry
        check cannot see: a lease that lapsed *during* a slow write.  If that happens the side
        effect may or may not have landed, so the error is ``interrupted`` — a blind retry here
        is how one write becomes two.
        """

        self.validate(lease)
        yield lease
        try:
            self.validate(lease)
        except KernelError as exc:
            raise KernelError(
                code="LEASE_LOST",
                message=(
                    f"lease on {lease.resource_id!r} was lost while the guarded write ran: "
                    f"{exc.message}"
                ),
                retryable=False,
                interrupted=True,
                recommended_action=(
                    "reconcile the workspace against the side-effect ledger before retrying"
                ),
                details={"resourceId": lease.resource_id,
                         "presentedToken": lease.fencing_token},
            ) from exc

    def fenced_writer(self, lease: Lease) -> FencedWriter:
        return FencedWriter(self, lease)

    # --- side-effect ledger --------------------------------------------------

    def record_side_effect(self, lease: Lease, *, effect_id: str, idempotency_key: str,
                           payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Append one side effect to the ledger, idempotently and under the fencing token.

        A duplicate delivery returns the *original* record rather than appending a second one, and
        an append carrying a superseded token is rejected by the store.  Both are required for
        ``duplicate-delivery-safe``.
        """

        if self._events is None:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="a side-effect ledger requires an event store",
                recommended_action="construct the LeaseManager with an EventStore",
            )
        require_identifier(effect_id, "effect_id")
        require_identifier(idempotency_key, "idempotency_key")
        self.validate(lease)
        record = {
            "type": "lease.side-effect",
            "resourceId": lease.resource_id,
            "ownerId": lease.owner_id,
            "fencingToken": lease.fencing_token,
            "effectId": effect_id,
            "payload": dict(require_mapping(payload, "payload")),
        }
        stored = self._events.append(lease.resource_id, record,
                                     idempotency_key=idempotency_key,
                                     fencing_token=lease.fencing_token)
        return {
            "eventId": stored.event_id,
            "sequence": stored.sequence,
            "hashChain": stored.hash_chain,
            "record": record,
        }

    # --- recovery ------------------------------------------------------------

    def plan_recovery(self, checkpoint: Mapping[str, Any],
                      ledger: Sequence[Mapping[str, Any]]) -> RecoveryPlan:
        """Classify every ledger entry as replayable, already-done, or ambiguous.

        The checkpoint's declared digest is verified against its content first: a plan built on a
        corrupt checkpoint is worse than no plan, because it looks authoritative.
        """

        body = require_mapping(checkpoint, "checkpoint")
        reject_unknown_fields(body, ("checkpointId", "resourceId", "state", "digest"),
                              field_name="checkpoint")
        checkpoint_id = require_identifier(body.get("checkpointId"), "checkpoint.checkpointId")
        resource_id = require_identifier(body.get("resourceId"), "checkpoint.resourceId")
        declared = require_str(body.get("digest"), "checkpoint.digest")
        state = require_mapping(body.get("state", {}), "checkpoint.state")
        computed = digest({"checkpointId": checkpoint_id, "resourceId": resource_id,
                           "state": dict(state)})
        if computed != declared:
            raise KernelError(
                code="CHECKPOINT_CORRUPT",
                message=(
                    f"checkpoint {checkpoint_id!r} declares {declared} but its content hashes "
                    f"to {computed}"
                ),
                retryable=False,
                recommended_action="discard the checkpoint and recover from the event log",
                details={"checkpointId": checkpoint_id},
            )

        replay: list[str] = []
        skip: list[str] = []
        reconcile: list[str] = []
        for index, raw in enumerate(ledger):
            entry = require_mapping(raw, f"side_effect_ledger[{index}]")
            reject_unknown_fields(entry, ("effectId", "status", "idempotencyKey", "fencingToken"),
                                  field_name=f"side_effect_ledger[{index}]")
            effect_id = require_identifier(entry.get("effectId"),
                                           f"side_effect_ledger[{index}].effectId")
            status = require_str(entry.get("status"), f"side_effect_ledger[{index}].status",
                                 max_length=32)
            if status not in SideEffectStatus:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=(
                        f"side_effect_ledger[{index}].status={status!r} is not one of "
                        f"{list(SideEffectStatus)}"
                    ),
                    recommended_action="record every side effect with a known status vocabulary",
                )
            if status == "applied":
                skip.append(effect_id)
            elif status == "not-applied":
                replay.append(effect_id)
            else:
                reconcile.append(effect_id)

        return RecoveryPlan(
            resource_id=resource_id,
            checkpoint_id=checkpoint_id,
            checkpoint_digest=computed,
            replay=tuple(replay),
            skip=tuple(skip),
            reconcile=tuple(reconcile),
        )

    # --- internals -----------------------------------------------------------

    def _lease_from(self, granted: Mapping[str, Any], ttl_seconds: int) -> Lease:
        expires_at = granted["expiresAt"]
        if isinstance(expires_at, str):
            expires_at = parse_timestamp(expires_at, "expiresAt")
        acquired_at = self._clock.now()
        return Lease(
            resource_id=require_identifier(granted["resourceId"], "resourceId"),
            owner_id=require_identifier(granted["ownerId"], "ownerId"),
            fencing_token=require_int(granted["fencingToken"], "fencingToken", minimum=1),
            acquired_at=acquired_at,
            expires_at=expires_at,
            ttl_seconds=ttl_seconds,
        )

class FencedWriter:
    """Runs a callable only while its lease is provably current.

    The callable is opaque on purpose: this class does not know whether it writes a file, a row
    or an S3 object, only that it must not run for a superseded owner.
    """

    __slots__ = ("_manager", "_lease")

    def __init__(self, manager: LeaseManager, lease: Lease) -> None:
        self._manager = manager
        self._lease = lease

    @property
    def lease(self) -> Lease:
        return self._lease

    def write(self, operation: Callable[[], T], *, description: str = "write") -> T:
        """Validate, run, revalidate.

        A validation failure *before* the call means nothing happened: terminal, safe to route
        elsewhere.  A validation failure *after* the call means the effect may have landed under a
        revoked lease: interrupted, and the caller must reconcile rather than retry.
        """

        require_str(description, "description", max_length=256)
        with self._manager.guard(self._lease):
            return operation()

    __call__ = write


class _FrozenClock:
    """A clock pinned to one instant so ``handle`` never reads wall time."""

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return 0


@register("workspace-lease-fencing")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    ``ports`` is required and carries live :class:`~.ports.LeaseStore` / ``EventStore`` /
    ``Clock`` objects.  This is a deliberate deviation from the JSON-only shape of the other
    handlers: a lease kernel with no durable store cannot answer the only question it exists to
    answer ("is this token still current?"), and inventing a fresh in-memory store per call would
    produce a confident answer that is always wrong.  Absent ports is ``MISSING_REQUIRED_INPUT``,
    never a silent local default.
    """

    body = require_mapping(request, "request")
    reject_unknown_fields(
        body,
        ("workspace", "worker_identity", "lease_policy", "checkpoint", "side_effect_ledger",
         "ports"),
        field_name="request",
    )
    for required in ("workspace", "worker_identity", "lease_policy", "ports"):
        if required not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{required} is required",
                recommended_action=f"supply {required}",
            )

    ports = require_mapping(body["ports"], "ports")
    reject_unknown_fields(ports, ("lease_store", "event_store", "clock"), field_name="ports")
    store = ports.get("lease_store")
    if store is None:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="ports.lease_store is required; fencing without a store is not fencing",
            recommended_action="inject a LeaseStore adapter",
        )

    workspace = require_mapping(body["workspace"], "workspace")
    reject_unknown_fields(workspace, ("workspaceId",), field_name="workspace")
    resource_id = require_identifier(workspace.get("workspaceId"), "workspace.workspaceId")

    worker = require_mapping(body["worker_identity"], "worker_identity")
    reject_unknown_fields(worker, ("ownerId",), field_name="worker_identity")
    owner_id = require_identifier(worker.get("ownerId"), "worker_identity.ownerId")

    policy = require_mapping(body["lease_policy"], "lease_policy")
    reject_unknown_fields(
        policy, ("ttlSeconds", "issuedAt", "action", "reason", "previousOwner", "fencingToken"),
        field_name="lease_policy",
    )
    ttl_seconds = require_int(policy.get("ttlSeconds"), "lease_policy.ttlSeconds", minimum=1,
                              maximum=86_400)
    now = parse_timestamp(policy.get("issuedAt"), "lease_policy.issuedAt")
    action = require_str(policy.get("action", "acquire"), "lease_policy.action", max_length=32)
    if action not in ("acquire", "renew", "takeover"):
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"lease_policy.action={action!r} is not acquire|renew|takeover",
            recommended_action="use a known lease action; unknown actions are refused",
        )

    clock = ports.get("clock") or _FrozenClock(now)
    manager = LeaseManager(store, clock, events=ports.get("event_store"))

    takeover_payload: Mapping[str, Any] | None = None
    if action == "acquire":
        lease = manager.acquire(resource_id, owner_id, ttl_seconds=ttl_seconds)
    elif action == "renew":
        held = require_int(policy.get("fencingToken"), "lease_policy.fencingToken", minimum=1)
        lease = manager.renew_token(resource_id, owner_id, held, ttl_seconds=ttl_seconds)
    else:
        lease, record = manager.takeover(
            resource_id, new_owner=owner_id,
            reason=require_str(policy.get("reason", ""), "lease_policy.reason", max_length=512),
            ttl_seconds=ttl_seconds,
            previous_owner=(
                require_identifier(policy["previousOwner"], "lease_policy.previousOwner")
                if policy.get("previousOwner") is not None else None
            ),
        )
        takeover_payload = record.to_payload()

    recovery: Mapping[str, Any] | None = None
    if body.get("checkpoint") is not None:
        plan = manager.plan_recovery(body["checkpoint"], body.get("side_effect_ledger") or ())
        recovery = plan.to_payload()

    heartbeat = {
        "resourceId": lease.resource_id,
        "ownerId": lease.owner_id,
        "fencingToken": lease.fencing_token,
        "observedAt": format_timestamp(clock.now()),
        "expiresAt": format_timestamp(lease.expires_at),
        "ttlSeconds": lease.ttl_seconds,
    }
    return {
        "lease": lease.to_payload(),
        "fencing_token": lease.fencing_token,
        "heartbeat": {**heartbeat, "digest": digest(heartbeat)},
        "takeover_event": takeover_payload,
        "recovery_plan": recovery,
    }
