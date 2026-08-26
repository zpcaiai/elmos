"""Durable event journal, checkpoints, leases and the side-effect ledger.

The orchestrator is an event-sourced state machine.  Everything that makes a
long refactor survivable lives here:

* **Append-only events** with a hash chain, so a replay that produces a
  different state is detectable rather than merely unlucky.
* **Checkpoints** binding a sequence number to a workspace tree digest and an
  artifact manifest digest, so "resume" means resuming a *verified* state.
* **Idempotency keys** recorded with the digest of the effect they produced, so
  a duplicate delivery returns the first result instead of acting twice.
* **Lease fencing**: a worker holds a lease with a monotonically increasing
  fencing token; a resumed or duplicated worker with a stale token is refused
  even if its lease has not visibly expired.
* **A side-effect ledger** with an explicit cursor, which is what rollback and
  recovery replay backwards to compensate.

Persistence is optional and, when enabled, is confined to a host-approved
directory.  Nothing here can be pointed at a path by a task payload.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import (
    ContractError,
    canonical_json,
    integer_value,
    isoformat_utc,
    normalize_relative_path,
    optional_string,
    require_digest,
    require_identifier,
    require_mapping,
    require_string,
    sha256_payload,
    utc_now,
)

GENESIS_DIGEST = "sha256:" + "0" * 64

#: Events the runtime understands.  An unknown event type is a corruption
#: signal, not something to skip.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "run.created",
        "run.plan.frozen",
        "run.paused",
        "run.resumed",
        "run.cancelled",
        "run.completed",
        "run.failed",
        "step.scheduled",
        "step.started",
        "step.succeeded",
        "step.failed",
        "step.blocked",
        "step.skipped",
        "shard.started",
        "shard.succeeded",
        "shard.failed",
        "checkpoint.written",
        "approval.requested",
        "approval.recorded",
        "sideeffect.recorded",
        "sideeffect.compensated",
        "rollback.started",
        "rollback.completed",
        "budget.exhausted",
        "scope.expanded",
    }
)


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """One immutable entry in the hash-chained run log."""

    sequence: int
    run_id: str
    event_type: str
    occurred_at: datetime
    payload: Mapping[str, Any]
    previous_digest: str
    step_id: str | None = None
    shard_id: str | None = None
    idempotency_key: str | None = None

    @property
    def body(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sequence": self.sequence,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "occurred_at": isoformat_utc(self.occurred_at),
            "payload": dict(self.payload),
            "previous_digest": self.previous_digest,
        }
        if self.step_id is not None:
            payload["step_id"] = self.step_id
        if self.shard_id is not None:
            payload["shard_id"] = self.shard_id
        if self.idempotency_key is not None:
            payload["idempotency_key"] = self.idempotency_key
        return payload

    @property
    def digest(self) -> str:
        return sha256_payload(self.body)

    def to_payload(self) -> dict[str, Any]:
        return {**self.body, "digest": self.digest}

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> JournalEvent:
        from .contracts import parse_timestamp

        mapping = require_mapping(value, "event")
        event = cls(
            sequence=integer_value(mapping.get("sequence"), "event.sequence", minimum=1),
            run_id=require_identifier(mapping.get("run_id"), "event.run_id"),
            event_type=require_string(mapping.get("event_type"), "event.event_type", max_length=64),
            occurred_at=parse_timestamp(mapping.get("occurred_at"), "event.occurred_at"),
            payload=dict(require_mapping(mapping.get("payload", {}), "event.payload")),
            previous_digest=require_digest(mapping.get("previous_digest"), "event.previous_digest"),
            step_id=optional_string(mapping.get("step_id"), "event.step_id", max_length=128),
            shard_id=optional_string(mapping.get("shard_id"), "event.shard_id", max_length=128),
            idempotency_key=optional_string(mapping.get("idempotency_key"), "event.idempotency_key", max_length=256),
        )
        if event.event_type not in EVENT_TYPES:
            raise ContractError("unknown_event_type", f"unknown event type '{event.event_type}'")
        declared = mapping.get("digest")
        if declared is not None and declared != event.digest:
            raise ContractError("event_digest_mismatch", f"event {event.sequence} digest does not match its content")
        return event


@dataclass(frozen=True, slots=True)
class Checkpoint:
    checkpoint_id: str
    run_id: str
    step_id: str
    sequence: int
    created_at: datetime
    state_version: int
    workspace_tree_digest: str
    artifact_manifest_digest: str
    side_effect_cursor: int
    shard_id: str | None = None
    resume_token: str | None = None
    expires_at: datetime | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "checkpointId": self.checkpoint_id,
            "runId": self.run_id,
            "stepId": self.step_id,
            "sequence": self.sequence,
            "createdAt": isoformat_utc(self.created_at),
            "stateVersion": self.state_version,
            "workspaceTreeDigest": self.workspace_tree_digest,
            "artifactManifestDigest": self.artifact_manifest_digest,
            "sideEffectCursor": self.side_effect_cursor,
        }
        if self.shard_id:
            payload["shardId"] = self.shard_id
        if self.resume_token:
            payload["resumeToken"] = self.resume_token
        if self.expires_at:
            payload["expiresAt"] = isoformat_utc(self.expires_at)
        return payload

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class SideEffect:
    """An externally visible action that may need compensating."""

    cursor: int
    kind: str
    target: str
    idempotency_key: str
    recorded_at: datetime
    reversible: bool
    compensation: Mapping[str, Any] = field(default_factory=dict)
    detail: Mapping[str, Any] = field(default_factory=dict)
    compensated: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "cursor": self.cursor,
            "kind": self.kind,
            "target": self.target,
            "idempotencyKey": self.idempotency_key,
            "recordedAt": isoformat_utc(self.recorded_at),
            "reversible": self.reversible,
            "compensation": dict(self.compensation),
            "detail": dict(self.detail),
            "compensated": self.compensated,
        }


@dataclass(frozen=True, slots=True)
class Lease:
    run_id: str
    holder: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime

    def valid_at(self, moment: datetime) -> bool:
        return moment < self.expires_at

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "holder": self.holder,
            "fencingToken": self.fencing_token,
            "acquiredAt": isoformat_utc(self.acquired_at),
            "expiresAt": isoformat_utc(self.expires_at),
        }


class RunJournal:
    """The append-only log for exactly one run.

    Not thread-safe by design: one run is owned by one lease holder at a time,
    and concurrency is expressed by sharding, not by shared mutation.
    """

    __slots__ = (
        "_run_id",
        "_events",
        "_checkpoints",
        "_side_effects",
        "_idempotency",
        "_lease",
        "_next_token",
        "_sink",
    )

    def __init__(self, run_id: str, *, sink: JournalSink | None = None) -> None:
        self._run_id = require_identifier(run_id, "run_id")
        self._events: list[JournalEvent] = []
        self._checkpoints: list[Checkpoint] = []
        self._side_effects: list[SideEffect] = []
        self._idempotency: dict[str, dict[str, Any]] = {}
        self._lease: Lease | None = None
        self._next_token = 1
        self._sink = sink

    # -- identity --------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def sequence(self) -> int:
        return len(self._events)

    @property
    def head_digest(self) -> str:
        return self._events[-1].digest if self._events else GENESIS_DIGEST

    @property
    def events(self) -> tuple[JournalEvent, ...]:
        return tuple(self._events)

    @property
    def checkpoints(self) -> tuple[Checkpoint, ...]:
        return tuple(self._checkpoints)

    @property
    def side_effects(self) -> tuple[SideEffect, ...]:
        return tuple(self._side_effects)

    @property
    def side_effect_cursor(self) -> int:
        return len(self._side_effects)

    # -- leases ----------------------------------------------------------

    def acquire_lease(self, holder: str, *, ttl_seconds: int = 300, now: datetime | None = None) -> Lease:
        """Take the run lease, fencing out every previously issued token.

        A lease is granted only when no live lease exists, or when the current
        holder renews.  The fencing token always increases, so a worker that
        was partitioned and comes back cannot write with its old token even if
        it believes its lease is still valid.
        """

        moment = now or utc_now()
        current = self._lease
        if current is not None and current.valid_at(moment) and current.holder != holder:
            raise ContractError(
                "lease_held",
                f"run lease is held by '{current.holder}' until {isoformat_utc(current.expires_at)}",
                {"holder": current.holder, "fencing_token": current.fencing_token},
            )
        lease = Lease(
            run_id=self._run_id,
            holder=require_identifier(holder, "lease.holder"),
            fencing_token=self._next_token,
            acquired_at=moment,
            expires_at=moment + timedelta(seconds=integer_value(ttl_seconds, "ttl_seconds", minimum=1, maximum=86400)),
        )
        self._next_token += 1
        self._lease = lease
        return lease

    def check_fence(self, lease: Lease | None, *, now: datetime | None = None) -> None:
        """Refuse a write from a stale or foreign lease."""

        if self._lease is None:
            return
        if lease is None:
            raise ContractError("lease_required", "this run requires a valid lease to append events")
        if lease.fencing_token < self._lease.fencing_token:
            raise ContractError(
                "stale_fencing_token",
                "a newer worker holds this run; the stale writer is fenced out",
                {"presented": lease.fencing_token, "current": self._lease.fencing_token},
            )
        if not lease.valid_at(now or utc_now()):
            raise ContractError("lease_expired", "the presented lease has expired")

    # -- events ----------------------------------------------------------

    def append(
        self,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        step_id: str | None = None,
        shard_id: str | None = None,
        idempotency_key: str | None = None,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> JournalEvent:
        if event_type not in EVENT_TYPES:
            raise ContractError("unknown_event_type", f"unknown event type '{event_type}'")
        self.check_fence(lease, now=now)
        event = JournalEvent(
            sequence=self.sequence + 1,
            run_id=self._run_id,
            event_type=event_type,
            occurred_at=now or utc_now(),
            payload=dict(payload or {}),
            previous_digest=self.head_digest,
            step_id=step_id,
            shard_id=shard_id,
            idempotency_key=idempotency_key,
        )
        self._events.append(event)
        if self._sink is not None:
            self._sink.write(event.to_payload())
        return event

    def replay(self, events: Sequence[Mapping[str, Any]]) -> None:
        """Rebuild this journal from serialised events, verifying the chain."""

        if self._events:
            raise ContractError("journal_not_empty", "replay requires an empty journal")
        previous = GENESIS_DIGEST
        for index, raw in enumerate(events, start=1):
            event = JournalEvent.from_payload(raw)
            if event.run_id != self._run_id:
                raise ContractError("run_id_mismatch", f"event {index} belongs to a different run")
            if event.sequence != index:
                raise ContractError("sequence_gap", f"event {index} has sequence {event.sequence}")
            if event.previous_digest != previous:
                raise ContractError(
                    "hash_chain_broken",
                    f"event {index} does not chain onto its predecessor",
                    {"expected": previous, "found": event.previous_digest},
                )
            previous = event.digest
            self._events.append(event)

    def verify_chain(self) -> bool:
        previous = GENESIS_DIGEST
        for index, event in enumerate(self._events, start=1):
            if event.sequence != index or event.previous_digest != previous:
                return False
            previous = event.digest
        return True

    def events_of(self, event_type: str) -> tuple[JournalEvent, ...]:
        return tuple(event for event in self._events if event.event_type == event_type)

    # -- idempotency -----------------------------------------------------

    def remember(self, key: str, result: Mapping[str, Any]) -> dict[str, Any]:
        """Record the outcome for ``key``; a repeat returns the first outcome.

        Recording the *digest* of the outcome as well as the outcome itself
        means a duplicate delivery that would have produced something different
        is a detectable contract violation rather than a silent overwrite.
        """

        identity = require_string(key, "idempotency_key", max_length=256)
        payload = dict(require_mapping(result, "idempotent_result"))
        existing = self._idempotency.get(identity)
        if existing is not None:
            if existing["digest"] != sha256_payload(payload):
                raise ContractError(
                    "idempotency_conflict",
                    f"idempotency key '{identity}' was already used with a different result",
                    {"key": identity},
                )
            return dict(existing["result"])
        self._idempotency[identity] = {"result": payload, "digest": sha256_payload(payload)}
        return payload

    def recall(self, key: str) -> dict[str, Any] | None:
        entry = self._idempotency.get(key)
        return dict(entry["result"]) if entry is not None else None

    def seen(self, key: str) -> bool:
        return key in self._idempotency

    # -- side effects ----------------------------------------------------

    def record_side_effect(
        self,
        kind: str,
        target: str,
        *,
        idempotency_key: str,
        reversible: bool,
        compensation: Mapping[str, Any] | None = None,
        detail: Mapping[str, Any] | None = None,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> SideEffect:
        if self.seen(idempotency_key):
            existing = next(
                (effect for effect in self._side_effects if effect.idempotency_key == idempotency_key),
                None,
            )
            if existing is not None:
                return existing
        effect = SideEffect(
            cursor=len(self._side_effects) + 1,
            kind=require_string(kind, "side_effect.kind", max_length=64),
            target=require_string(target, "side_effect.target", max_length=1024),
            idempotency_key=require_string(idempotency_key, "side_effect.idempotency_key", max_length=256),
            recorded_at=now or utc_now(),
            reversible=bool(reversible),
            compensation=dict(compensation or {}),
            detail=dict(detail or {}),
        )
        self._side_effects.append(effect)
        self.remember(effect.idempotency_key, {"cursor": effect.cursor, "kind": effect.kind, "target": effect.target})
        self.append(
            "sideeffect.recorded",
            {"cursor": effect.cursor, "kind": effect.kind, "target": effect.target, "reversible": effect.reversible},
            idempotency_key=effect.idempotency_key,
            lease=lease,
            now=now,
        )
        return effect

    def mark_compensated(self, cursor: int, *, lease: Lease | None = None, now: datetime | None = None) -> SideEffect:
        index = integer_value(cursor, "cursor", minimum=1) - 1
        if index >= len(self._side_effects):
            raise ContractError("unknown_side_effect", f"no side effect at cursor {cursor}")
        effect = self._side_effects[index]
        if effect.compensated:
            return effect
        updated = SideEffect(
            cursor=effect.cursor,
            kind=effect.kind,
            target=effect.target,
            idempotency_key=effect.idempotency_key,
            recorded_at=effect.recorded_at,
            reversible=effect.reversible,
            compensation=effect.compensation,
            detail=effect.detail,
            compensated=True,
        )
        self._side_effects[index] = updated
        self.append(
            "sideeffect.compensated",
            {"cursor": updated.cursor, "kind": updated.kind, "target": updated.target},
            lease=lease,
            now=now,
        )
        return updated

    def uncompensated_since(self, cursor: int) -> tuple[SideEffect, ...]:
        """Side effects after ``cursor``, newest first — rollback order."""

        return tuple(
            effect
            for effect in reversed(self._side_effects)
            if effect.cursor > cursor and not effect.compensated
        )

    # -- checkpoints -----------------------------------------------------

    def write_checkpoint(
        self,
        *,
        step_id: str,
        workspace_tree_digest: str,
        artifact_manifest_digest: str,
        state_version: int,
        shard_id: str | None = None,
        ttl_seconds: int | None = None,
        lease: Lease | None = None,
        now: datetime | None = None,
    ) -> Checkpoint:
        moment = now or utc_now()
        checkpoint = Checkpoint(
            checkpoint_id=f"{self._run_id}:{self.sequence + 1:08d}",
            run_id=self._run_id,
            step_id=require_string(step_id, "checkpoint.step_id", max_length=128),
            sequence=self.sequence + 1,
            created_at=moment,
            state_version=integer_value(state_version, "checkpoint.state_version", minimum=1),
            workspace_tree_digest=require_digest(workspace_tree_digest, "checkpoint.workspace_tree_digest"),
            artifact_manifest_digest=require_digest(
                artifact_manifest_digest, "checkpoint.artifact_manifest_digest"
            ),
            side_effect_cursor=self.side_effect_cursor,
            shard_id=shard_id,
            expires_at=None
            if ttl_seconds is None
            else moment + timedelta(seconds=integer_value(ttl_seconds, "ttl_seconds", minimum=1)),
        )
        resume_token = sha256_payload(
            {
                "checkpoint": checkpoint.to_payload(),
                "head": self.head_digest,
            }
        )
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            run_id=checkpoint.run_id,
            step_id=checkpoint.step_id,
            sequence=checkpoint.sequence,
            created_at=checkpoint.created_at,
            state_version=checkpoint.state_version,
            workspace_tree_digest=checkpoint.workspace_tree_digest,
            artifact_manifest_digest=checkpoint.artifact_manifest_digest,
            side_effect_cursor=checkpoint.side_effect_cursor,
            shard_id=checkpoint.shard_id,
            resume_token=resume_token,
            expires_at=checkpoint.expires_at,
        )
        self._checkpoints.append(checkpoint)
        self.append(
            "checkpoint.written",
            {"checkpointId": checkpoint.checkpoint_id, "digest": checkpoint.digest},
            step_id=checkpoint.step_id,
            shard_id=shard_id,
            lease=lease,
            now=moment,
        )
        return checkpoint

    def latest_checkpoint(self, *, step_id: str | None = None, now: datetime | None = None) -> Checkpoint | None:
        moment = now or utc_now()
        for checkpoint in reversed(self._checkpoints):
            if step_id is not None and checkpoint.step_id != step_id:
                continue
            if checkpoint.expires_at is not None and checkpoint.expires_at <= moment:
                continue
            return checkpoint
        return None

    # -- export ----------------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self._run_id,
            "sequence": self.sequence,
            "headDigest": self.head_digest,
            "events": [event.to_payload() for event in self._events],
            "checkpoints": [checkpoint.to_payload() for checkpoint in self._checkpoints],
            "sideEffects": [effect.to_payload() for effect in self._side_effects],
        }

    def timeline(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "sequence": event.sequence,
                "at": isoformat_utc(event.occurred_at),
                "type": event.event_type,
                "step": event.step_id,
                "shard": event.shard_id,
                "digest": event.digest,
            }
            for event in self._events
        )


class JournalSink:
    """Append-only JSONL persistence inside a host-approved directory."""

    __slots__ = ("_path",)

    def __init__(self, root: Path, run_id: str) -> None:
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise ContractError("journal_root_not_directory", "approved journal root must be a directory")
        relative = normalize_relative_path(f"{require_identifier(run_id, 'run_id')}.jsonl", "journal.file")
        path = (resolved / relative).resolve()
        try:
            path.relative_to(resolved)
        except ValueError as exc:  # pragma: no cover - normalize_relative_path already blocks this
            raise ContractError("path_escape", "journal file escapes the approved root") from exc
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def write(self, payload: Mapping[str, Any]) -> None:
        line = canonical_json(payload) + "\n"
        with open(self._path, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def read(self) -> Iterator[dict[str, Any]]:
        if not self._path.exists():
            return iter(())
        with open(self._path, encoding="utf-8") as handle:
            return iter([json.loads(line) for line in handle if line.strip()])

    def snapshot(self, payload: Mapping[str, Any]) -> Path:
        """Atomically write a full-state snapshot next to the event log."""

        target = self._path.with_suffix(".snapshot.json")
        directory = target.parent
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False)
        try:
            handle.write(canonical_json(payload))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, target)
        return target


def idempotency_key(*parts: Any) -> str:
    """Deterministic key from run/step/shard/input identity."""

    return sha256_payload({"parts": [str(part) for part in parts]})


__all__ = [
    "EVENT_TYPES",
    "GENESIS_DIGEST",
    "Checkpoint",
    "JournalEvent",
    "JournalSink",
    "Lease",
    "RunJournal",
    "SideEffect",
    "idempotency_key",
]
