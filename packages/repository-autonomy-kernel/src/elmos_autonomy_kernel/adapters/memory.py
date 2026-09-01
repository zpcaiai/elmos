"""In-process adapters.

These are not toys: the event store implements the same hash chain, optimistic
concurrency, idempotency and fencing rules as the PostgreSQL adapter, because
the invariant tests run against both.  If a rule can be violated here but not
there (or the reverse), the two adapters disagree and one of them is wrong.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..contracts import canonical_json, digest, digest_bytes, require_identifier
from ..errors import KernelError

__all__ = [
    "SystemClock",
    "FixedClock",
    "MemoryEvent",
    "InMemoryEventStore",
    "InMemoryKeyValueStore",
    "InMemoryArtifactStore",
    "InMemoryLeaseStore",
]

GENESIS = "sha256:" + "0" * 64


class SystemClock:
    """Real time."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class FixedClock:
    """Controllable time for tests and replay.

    ``advance`` moves both wall clock and the monotonic counter, so a test can
    expire a lease or exhaust a budget without sleeping.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._mono = 0

    def now(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return self._mono

    def advance(self, seconds: float = 0.0, *, ns: int = 0) -> None:
        self._now = self._now + timedelta(seconds=seconds)
        self._mono += int(seconds * 1_000_000_000) + ns


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    sequence: int
    event_id: str
    stream_id: str
    payload: Mapping[str, Any]
    hash_chain: str
    recorded_at: datetime

    def to_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "eventId": self.event_id,
            "streamId": self.stream_id,
            "payload": dict(self.payload),
            "hashChain": self.hash_chain,
        }


class InMemoryEventStore:
    """Append-only hash-chained log with per-stream optimistic concurrency."""

    def __init__(self, clock: Any | None = None) -> None:
        self._clock = clock or SystemClock()
        self._streams: dict[str, list[MemoryEvent]] = {}
        self._idempotency: dict[tuple[str, str], MemoryEvent] = {}
        self._fencing: dict[str, int] = {}
        self._ids = itertools.count(1)
        self._lock = threading.RLock()

    def append(self, stream_id: str, payload: Mapping[str, Any], *,
               expected_sequence: int | None = None,
               idempotency_key: str | None = None,
               fencing_token: int | None = None) -> MemoryEvent:
        require_identifier(stream_id, "stream_id")
        with self._lock:
            events = self._streams.setdefault(stream_id, [])

            if idempotency_key is not None:
                previous = self._idempotency.get((stream_id, idempotency_key))
                if previous is not None:
                    # A duplicate delivery must return the original event.
                    # Returning a *new* event here is how a side effect gets
                    # applied twice while both appear legitimate.
                    if canonical_json(previous.payload) != canonical_json(payload):
                        raise KernelError(
                            code="IDEMPOTENCY_CONFLICT",
                            message=(
                                f"idempotency key {idempotency_key!r} was already used on "
                                f"stream {stream_id!r} with a different payload"
                            ),
                            recommended_action="use a key derived from the payload digest",
                        )
                    return previous

            if fencing_token is not None:
                current = self._fencing.get(stream_id, 0)
                if fencing_token < current:
                    raise KernelError(
                        code="FENCING_REJECTED",
                        message=(
                            f"fencing token {fencing_token} is stale for stream "
                            f"{stream_id!r}; current is {current}"
                        ),
                        retryable=False,
                        recommended_action="re-acquire the lease and rebuild local state",
                    )
                self._fencing[stream_id] = fencing_token

            current_sequence = events[-1].sequence if events else 0
            if expected_sequence is not None and expected_sequence != current_sequence:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=(
                        f"stream {stream_id!r} is at sequence {current_sequence}, "
                        f"caller expected {expected_sequence}"
                    ),
                    retryable=True,
                    recommended_action="re-read the stream and retry the decision",
                )

            previous_hash = events[-1].hash_chain if events else GENESIS
            sequence = current_sequence + 1
            event_id = f"evt-{next(self._ids):012d}"
            chain = digest({
                "previous": previous_hash,
                "sequence": sequence,
                "streamId": stream_id,
                "payload": payload,
            })
            event = MemoryEvent(
                sequence=sequence,
                event_id=event_id,
                stream_id=stream_id,
                payload=dict(payload),
                hash_chain=chain,
                recorded_at=self._clock.now(),
            )
            events.append(event)
            if idempotency_key is not None:
                self._idempotency[(stream_id, idempotency_key)] = event
            return event

    def read(self, stream_id: str, *, from_sequence: int = 0) -> Sequence[MemoryEvent]:
        with self._lock:
            return tuple(
                event for event in self._streams.get(stream_id, ())
                if event.sequence > from_sequence
            )

    def head(self, stream_id: str) -> MemoryEvent | None:
        with self._lock:
            events = self._streams.get(stream_id)
            return events[-1] if events else None

    def streams(self) -> Sequence[str]:
        with self._lock:
            return tuple(sorted(self._streams))

    def verify_chain(self, stream_id: str) -> bool:
        """Recompute the hash chain; any edit to history breaks it."""

        with self._lock:
            previous = GENESIS
            for event in self._streams.get(stream_id, ()):
                expected = digest({
                    "previous": previous,
                    "sequence": event.sequence,
                    "streamId": stream_id,
                    "payload": event.payload,
                })
                if expected != event.hash_chain:
                    return False
                previous = event.hash_chain
            return True


class InMemoryKeyValueStore:
    """Versioned KV with compare-and-set semantics."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[Any, int]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> tuple[Any, int] | None:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: Any, *, expected_version: int | None = None) -> int:
        with self._lock:
            existing = self._data.get(key)
            current_version = existing[1] if existing else 0
            if expected_version is not None and expected_version != current_version:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=(
                        f"key {key!r} is at version {current_version}, "
                        f"caller expected {expected_version}"
                    ),
                    retryable=True,
                    recommended_action="re-read the key and retry",
                )
            version = current_version + 1
            self._data[key] = (value, version)
            return version

    def delete(self, key: str, *, expected_version: int | None = None) -> None:
        with self._lock:
            existing = self._data.get(key)
            if existing is None:
                return
            if expected_version is not None and expected_version != existing[1]:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=f"key {key!r} version mismatch on delete",
                    retryable=True,
                    recommended_action="re-read the key and retry",
                )
            del self._data[key]

    def scan(self, prefix: str) -> Iterator[tuple[str, Any, int]]:
        with self._lock:
            items = [(key, value, version) for key, (value, version) in self._data.items()
                     if key.startswith(prefix)]
        yield from sorted(items)


class InMemoryArtifactStore:
    """Content-addressed blobs held in memory."""

    def __init__(self) -> None:
        self._blobs: dict[str, tuple[bytes, str]] = {}
        self._lock = threading.RLock()

    def put(self, data: bytes, *, media_type: str, expected_digest: str | None = None) -> str:
        if not isinstance(data, (bytes, bytearray)):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="artifact payload must be bytes",
                recommended_action="encode the payload before storing it",
            )
        computed = digest_bytes(bytes(data))
        if expected_digest is not None and expected_digest != computed:
            raise KernelError(
                code="DIGEST_MISMATCH",
                message=(
                    f"artifact digest mismatch: caller claimed {expected_digest}, "
                    f"stored bytes hash to {computed}"
                ),
                recommended_action="re-produce the artifact; do not trust the claimed digest",
            )
        with self._lock:
            self._blobs[computed] = (bytes(data), media_type)
        return computed

    def get(self, artifact_digest: str) -> bytes:
        with self._lock:
            found = self._blobs.get(artifact_digest)
        if found is None:
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact or restore from backup",
            )
        data, _ = found
        if digest_bytes(data) != artifact_digest:  # pragma: no cover - defensive
            raise KernelError(
                code="DIGEST_MISMATCH",
                message=f"stored artifact {artifact_digest} no longer hashes to its address",
                recommended_action="treat the store as corrupt",
            )
        return data

    def exists(self, artifact_digest: str) -> bool:
        with self._lock:
            return artifact_digest in self._blobs

    def stat(self, artifact_digest: str) -> Mapping[str, Any]:
        with self._lock:
            found = self._blobs.get(artifact_digest)
        if found is None:
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact",
            )
        data, media_type = found
        return {"digest": artifact_digest, "byteCount": len(data), "mediaType": media_type}


class InMemoryLeaseStore:
    """Monotonic fencing tokens with expiry."""

    def __init__(self, clock: Any | None = None) -> None:
        self._clock = clock or SystemClock()
        self._tokens: dict[str, int] = {}
        self._holders: dict[str, tuple[str, int, datetime]] = {}
        self._lock = threading.RLock()

    def acquire(self, resource_id: str, owner_id: str, *, ttl_seconds: int) -> Mapping[str, Any]:
        require_identifier(resource_id, "resource_id")
        require_identifier(owner_id, "owner_id")
        if ttl_seconds <= 0:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="lease ttl must be positive",
                recommended_action="supply ttl_seconds > 0",
            )
        now = self._clock.now()
        with self._lock:
            holder = self._holders.get(resource_id)
            if holder is not None:
                held_by, _token, expires_at = holder
                if expires_at > now and held_by != owner_id:
                    raise KernelError(
                        code="LEASE_HELD_BY_OTHER",
                        message=(
                            f"resource {resource_id!r} is leased by {held_by!r} "
                            f"until {expires_at.isoformat()}"
                        ),
                        retryable=True,
                        recommended_action="wait for expiry or take over explicitly",
                    )
            token = self._tokens.get(resource_id, 0) + 1
            self._tokens[resource_id] = token
            expires = now + timedelta(seconds=ttl_seconds)
            self._holders[resource_id] = (owner_id, token, expires)
            return {
                "resourceId": resource_id,
                "ownerId": owner_id,
                "fencingToken": token,
                "expiresAt": expires,
            }

    def renew(self, resource_id: str, owner_id: str, fencing_token: int, *,
              ttl_seconds: int) -> Mapping[str, Any]:
        now = self._clock.now()
        with self._lock:
            holder = self._holders.get(resource_id)
            if holder is None:
                raise KernelError(
                    code="LEASE_LOST",
                    message=f"no lease exists for {resource_id!r}",
                    retryable=False,
                    recommended_action="re-acquire the lease and rebuild local state",
                )
            held_by, token, expires_at = holder
            if held_by != owner_id or token != fencing_token:
                raise KernelError(
                    code="LEASE_LOST",
                    message=(
                        f"lease on {resource_id!r} moved to token {token} "
                        f"(owner {held_by!r}); caller holds {fencing_token}"
                    ),
                    retryable=False,
                    recommended_action="stop writing immediately and re-acquire",
                )
            if expires_at <= now:
                raise KernelError(
                    code="LEASE_LOST",
                    message=f"lease on {resource_id!r} expired at {expires_at.isoformat()}",
                    retryable=False,
                    recommended_action="re-acquire the lease and rebuild local state",
                )
            expires = now + timedelta(seconds=ttl_seconds)
            self._holders[resource_id] = (owner_id, token, expires)
            return {
                "resourceId": resource_id,
                "ownerId": owner_id,
                "fencingToken": token,
                "expiresAt": expires,
            }

    def release(self, resource_id: str, owner_id: str, fencing_token: int) -> None:
        with self._lock:
            holder = self._holders.get(resource_id)
            if holder is None:
                return
            held_by, token, _ = holder
            if held_by != owner_id or token != fencing_token:
                raise KernelError(
                    code="LEASE_LOST",
                    message=f"cannot release {resource_id!r}: lease is held by {held_by!r}",
                    recommended_action="do not release a lease you no longer hold",
                )
            del self._holders[resource_id]

    def current_token(self, resource_id: str) -> int:
        with self._lock:
            return self._tokens.get(resource_id, 0)
