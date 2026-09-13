from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

class LedgerVerificationError(ValueError):
    pass

@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    ledger: str
    sequence: int
    timestamp: str
    payload: dict[str, Any]
    previous_hash: str
    hash: str

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

class AppendOnlyLedger:
    def __init__(self, ledger: str) -> None:
        if not ledger:
            raise ValueError("ledger is required")
        self.ledger = ledger
        self._events: list[LedgerEvent] = []

    @property
    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    def append(self, event_id: str, payload: dict[str, Any], timestamp: str | None = None) -> LedgerEvent:
        if any(e.event_id == event_id for e in self._events):
            raise ValueError(f"duplicate event_id: {event_id}")
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].hash if self._events else "GENESIS"
        timestamp = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = {"event_id": event_id, "ledger": self.ledger, "sequence": sequence, "timestamp": timestamp, "payload": payload, "previous_hash": previous_hash}
        digest = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
        event = LedgerEvent(hash=digest, **body)
        self._events.append(event)
        return event

    def verify(self) -> bool:
        previous = "GENESIS"
        for expected_sequence, event in enumerate(self._events, 1):
            if event.sequence != expected_sequence or event.previous_hash != previous or event.ledger != self.ledger:
                raise LedgerVerificationError("ledger sequence or linkage mismatch")
            body = {"event_id": event.event_id, "ledger": event.ledger, "sequence": event.sequence, "timestamp": event.timestamp, "payload": event.payload, "previous_hash": event.previous_hash}
            digest = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
            if digest != event.hash:
                raise LedgerVerificationError("ledger hash mismatch")
            previous = event.hash
        return True
