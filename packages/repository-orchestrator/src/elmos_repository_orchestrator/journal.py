"""Append-only in-memory journal with idempotency and a SHA-256 hash chain."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractError,
    canonical_json,
    normalize_relative_path,
    parse_timestamp,
    require_mapping,
    require_string,
    sha256_payload,
    utc_now,
)


GENESIS_HASH = "sha256:" + "0" * 64
MAX_EVENT_BYTES = 65_536

try:  # pragma: no cover - exercised on the supported Unix repository hosts
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class JournalEvent:
    sequence: int
    idempotency_key: str
    event_type: str
    payload: Mapping[str, Any]
    occurred_at: datetime
    previous_hash: str
    event_hash: str

    def hash_body(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "idempotency_key": self.idempotency_key,
            "event_type": self.event_type,
            "payload": self.payload,
            "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "previous_hash": self.previous_hash,
        }

    def to_payload(self) -> dict[str, Any]:
        return {**self.hash_body(), "event_hash": self.event_hash}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "JournalEvent":
        value = require_mapping(payload, "journal_event")
        sequence = value.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ContractError("invalid_sequence", "journal sequence must be a positive integer")
        event_payload = require_mapping(value.get("payload"), "journal_event.payload")
        canonical_json(event_payload)
        return cls(
            sequence=sequence,
            idempotency_key=require_string(value.get("idempotency_key"), "journal_event.idempotency_key"),
            event_type=require_string(value.get("event_type"), "journal_event.event_type"),
            payload=dict(event_payload),
            occurred_at=parse_timestamp(value.get("occurred_at"), "journal_event.occurred_at"),
            previous_hash=require_string(value.get("previous_hash"), "journal_event.previous_hash"),
            event_hash=require_string(value.get("event_hash"), "journal_event.event_hash"),
        )


class AppendOnlyJournal:
    def __init__(self, events: Sequence[JournalEvent] = ()):
        self._events: list[JournalEvent] = list(events)
        self.verify()
        self._by_key = {event.idempotency_key: event for event in self._events}
        if len(self._by_key) != len(self._events):
            raise ContractError("duplicate_idempotency_key", "journal contains duplicate idempotency keys")

    @classmethod
    def from_payloads(cls, payloads: Sequence[Mapping[str, Any]]) -> "AppendOnlyJournal":
        return cls(tuple(JournalEvent.from_payload(item) for item in payloads))

    @property
    def events(self) -> tuple[JournalEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        *,
        idempotency_key: str,
        event_type: str,
        payload: Mapping[str, Any],
        occurred_at: datetime | None = None,
    ) -> JournalEvent:
        key = require_string(idempotency_key, "idempotency_key")
        kind = require_string(event_type, "event_type")
        body = dict(require_mapping(payload, "payload"))
        canonical_json(body)
        existing = self._by_key.get(key)
        if existing is not None:
            if existing.event_type != kind or canonical_json(existing.payload) != canonical_json(body):
                raise ContractError("idempotency_conflict", "journal key reused with different event content")
            return existing
        timestamp = occurred_at or utc_now()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ContractError("naive_timestamp", "journal timestamp must be timezone-aware")
        previous = self._events[-1].event_hash if self._events else GENESIS_HASH
        draft = JournalEvent(len(self._events) + 1, key, kind, body, timestamp.astimezone(timezone.utc), previous, "")
        event = JournalEvent(
            draft.sequence,
            draft.idempotency_key,
            draft.event_type,
            draft.payload,
            draft.occurred_at,
            draft.previous_hash,
            sha256_payload(draft.hash_body()),
        )
        self._events.append(event)
        self._by_key[key] = event
        return event

    def verify(self) -> None:
        previous = GENESIS_HASH
        for expected_sequence, event in enumerate(self._events, start=1):
            if event.sequence != expected_sequence:
                raise ContractError("journal_sequence_gap", "journal sequence is not monotonic and contiguous")
            if event.previous_hash != previous:
                raise ContractError("journal_chain_broken", f"journal previous hash mismatch at {expected_sequence}")
            if sha256_payload(event.hash_body()) != event.event_hash:
                raise ContractError("journal_hash_mismatch", f"journal event hash mismatch at {expected_sequence}")
            previous = event.event_hash

    def replay_state(self) -> dict[str, Any]:
        self.verify()
        state: dict[str, Any] = {"tasks": {}, "last_sequence": 0, "head_hash": GENESIS_HASH}
        for event in self._events:
            task_id = event.payload.get("task_id")
            status = event.payload.get("status")
            if isinstance(task_id, str) and isinstance(status, str):
                state["tasks"][task_id] = status
            state["last_sequence"] = event.sequence
            state["head_hash"] = event.event_hash
        return state


def _approved_store_path(root: Path, relative_path: str) -> Path:
    normalized = normalize_relative_path(relative_path, "journal.relative_path")
    approved_root = root.resolve(strict=True)
    candidate = approved_root.joinpath(*normalized.split("/"))
    parent = candidate.parent.resolve(strict=True)
    if approved_root != parent and approved_root not in parent.parents:
        raise ContractError("journal_path_escape", "journal path escapes the approved root")
    cursor = approved_root
    for part in normalized.split("/"):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ContractError("journal_symlink", "journal path crosses a symlink")
    if candidate.exists() and not candidate.is_file():
        raise ContractError("journal_not_file", "journal path is not a regular file")
    return candidate


def _decode_events(raw: bytes) -> tuple[JournalEvent, ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\n"):
        raise ContractError("journal_truncated", "journal does not end at an event boundary")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ContractError("journal_encoding", "journal must be UTF-8 JSON Lines") from exc
    events: list[JournalEvent] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError("journal_json", f"invalid journal JSON at line {line_number}") from exc
        events.append(JournalEvent.from_payload(require_mapping(parsed, f"journal line {line_number}")))
    return tuple(events)


class DurableJournalStore:
    """Caller-rooted JSONL journal using locks, O_APPEND, fsync, and hash replay."""

    def __init__(self, *, approved_root: Path, relative_path: str):
        if fcntl is None:
            raise ContractError("journal_lock_unavailable", "durable journal requires advisory file locking")
        self.approved_root = approved_root.resolve(strict=True)
        self.relative_path = normalize_relative_path(relative_path, "journal.relative_path")
        self.path = _approved_store_path(self.approved_root, self.relative_path)

    @staticmethod
    def _read_fd(fd: int) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def _open(self) -> int:
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError as exc:
            raise ContractError("journal_open_failed", f"cannot open approved journal: {exc.strerror}") from exc
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ContractError("journal_not_file", "journal path is not a regular file")
        return fd

    def load(self) -> AppendOnlyJournal:
        fd = self._open()
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            return AppendOnlyJournal(_decode_events(self._read_fd(fd)))
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def append(
        self,
        *,
        idempotency_key: str,
        event_type: str,
        payload: Mapping[str, Any],
        occurred_at: datetime,
    ) -> tuple[AppendOnlyJournal, JournalEvent, bool]:
        fd = self._open()
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            journal = AppendOnlyJournal(_decode_events(self._read_fd(fd)))
            before = len(journal.events)
            event = journal.append(
                idempotency_key=idempotency_key,
                event_type=event_type,
                payload=payload,
                occurred_at=occurred_at,
            )
            appended = len(journal.events) != before
            if appended:
                encoded = canonical_json(event.to_payload()).encode("utf-8") + b"\n"
                if len(encoded) > MAX_EVENT_BYTES:
                    raise ContractError("journal_event_too_large", f"journal event exceeds {MAX_EVENT_BYTES} bytes")
                written = os.write(fd, encoded)
                if written != len(encoded):
                    raise ContractError("journal_short_write", "journal append was incomplete and replay will fail closed")
                os.fsync(fd)
            journal.verify()
            return journal, event, appended
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
