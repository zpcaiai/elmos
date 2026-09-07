from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from .canonical import canonical_json_bytes, sha256_digest


@dataclass(frozen=True)
class LedgerEvent:
    stream_id: str
    sequence: int
    event_id: str
    event_type: str
    payload: dict[str, Any]
    payload_digest: str
    previous_event_digest: str | None
    event_digest: str
    occurred_at: str


class RepositoryContextLedger:
    """In-memory teaching implementation of an append-only hash-linked ledger."""

    def __init__(self, stream_id: str) -> None:
        if not stream_id:
            raise ValueError("stream_id is required")
        self.stream_id = stream_id
        self._events: list[LedgerEvent] = []
        self._idempotency: dict[str, LedgerEvent] = {}

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        occurred_at: str | None = None,
    ) -> LedgerEvent:
        if idempotency_key in self._idempotency:
            existing = self._idempotency[idempotency_key]
            if existing.event_type != event_type or existing.payload_digest != sha256_digest(canonical_json_bytes(payload)):
                raise ValueError("idempotency key reused for different event")
            return existing
        sequence = len(self._events) + 1
        previous = self._events[-1].event_digest if self._events else None
        payload_digest = sha256_digest(canonical_json_bytes(payload))
        time_value = occurred_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        envelope = {
            "schema_version": "1.2.0",
            "stream_id": self.stream_id,
            "sequence": sequence,
            "event_id": idempotency_key,
            "event_type": event_type,
            "payload_digest": payload_digest,
            "previous_event_digest": previous,
            "occurred_at": time_value,
        }
        event = LedgerEvent(
            stream_id=self.stream_id,
            sequence=sequence,
            event_id=idempotency_key,
            event_type=event_type,
            payload=dict(payload),
            payload_digest=payload_digest,
            previous_event_digest=previous,
            event_digest=sha256_digest(canonical_json_bytes(envelope)),
            occurred_at=time_value,
        )
        self._events.append(event)
        self._idempotency[idempotency_key] = event
        return event

    def validate_chain(self) -> bool:
        previous: str | None = None
        for event in self._events:
            if event.previous_event_digest != previous:
                return False
            envelope = {
                "schema_version": "1.2.0",
                "stream_id": event.stream_id,
                "sequence": event.sequence,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "payload_digest": event.payload_digest,
                "previous_event_digest": event.previous_event_digest,
                "occurred_at": event.occurred_at,
            }
            if event.payload_digest != sha256_digest(canonical_json_bytes(event.payload)):
                return False
            if event.event_digest != sha256_digest(canonical_json_bytes(envelope)):
                return False
            previous = event.event_digest
        return True

    def current_file_state(self) -> dict[str, dict[str, Any]]:
        state: dict[str, dict[str, Any]] = {}
        for event in self._events:
            path = event.payload.get("logical_path")
            if not path:
                continue
            if event.event_type in {"FILE_READ", "CONTENT_REREAD"}:
                state[path] = {
                    "content_digest": event.payload["content_digest"],
                    "snapshot_digest": event.payload.get("snapshot_digest"),
                    "stale": False,
                    "source_event_id": event.event_id,
                }
            elif event.event_type in {"CONTENT_CHANGED", "CONTEXT_STALE"} and path in state:
                state[path] = {**state[path], "stale": True, "stale_event_id": event.event_id}
        return state

    def materialize_fresh_reads(self) -> list[dict[str, Any]]:
        state = self.current_file_state()
        return [
            {"logical_path": path, **value}
            for path, value in sorted(state.items())
            if not value["stale"]
        ]

    def checkpoint(self, *, repository_snapshot_digest: str, task_state: dict[str, Any]) -> dict[str, Any]:
        body = {
            "schema_version": "1.2.0",
            "stream_id": self.stream_id,
            "ledger_sequence": len(self._events),
            "repository_snapshot_digest": repository_snapshot_digest,
            "fresh_reads": self.materialize_fresh_reads(),
            "stale_reads": [
                {"logical_path": path, **value}
                for path, value in sorted(self.current_file_state().items())
                if value["stale"]
            ],
            "task_state": task_state,
        }
        return {**body, "checkpoint_digest": sha256_digest(canonical_json_bytes(body))}

    def corrupt_event_for_test(self, index: int, *, payload: dict[str, Any]) -> None:
        """Test-only hook used to prove hash-chain validation catches mutation."""
        self._events[index] = replace(self._events[index], payload=payload)
