"""Hexagonal boundaries.

The kernel's decision logic is pure and synchronous.  Everything that touches
the world — a clock, a database, an object store, a subprocess, a model
provider — enters through one of these Protocols.  That is what makes the
invariants testable: a fencing-token race, a crash between side effect and
commit, or a provider timeout can all be *provoked* by an adapter rather than
waited for.

Every port is fail-closed by construction: an adapter that cannot answer must
raise, never return an empty or zero value.  A zero is a legal business value
almost everywhere in this system (zero cost, zero remaining budget, zero
findings), so "fell back to zero" and "measured zero" must not be the same
observation.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Clock",
    "EventStore",
    "KeyValueStore",
    "ArtifactStore",
    "LeaseStore",
    "RepositoryReader",
    "ToolInvoker",
    "ProcessRunner",
    "ModelProvider",
    "StoredEvent",
]


@runtime_checkable
class Clock(Protocol):
    """Injected time.

    Nothing in the kernel calls ``datetime.now`` directly.  Leases, budgets,
    ETAs and retention windows all read this, so tests can move time without
    sleeping and a replay can be reproduced exactly.
    """

    def now(self) -> datetime: ...

    def monotonic_ns(self) -> int:
        """Monotonic nanoseconds for measuring durations.

        Wall-clock deltas are not durations: an NTP step would otherwise turn a
        200 ms step into a negative one.
        """


class StoredEvent(Protocol):
    """An event as it exists after the store has accepted it."""

    @property
    def sequence(self) -> int: ...
    @property
    def event_id(self) -> str: ...
    @property
    def payload(self) -> Mapping[str, Any]: ...
    @property
    def hash_chain(self) -> str: ...


@runtime_checkable
class EventStore(Protocol):
    """Append-only, hash-chained, per-stream event log.

    The store is the execution truth.  The transcript is not, the in-memory
    materialised state is not, and a worker's local belief certainly is not.
    """

    def append(
        self,
        stream_id: str,
        payload: Mapping[str, Any],
        *,
        expected_sequence: int | None = None,
        idempotency_key: str | None = None,
        fencing_token: int | None = None,
    ) -> StoredEvent:
        """Append one event.

        ``expected_sequence`` is optimistic concurrency: if the stream has
        moved on, the append must raise ``WRITE_CONFLICT`` rather than
        overwrite.  ``idempotency_key`` makes a duplicate delivery return the
        *original* event instead of appending a second one.  ``fencing_token``
        rejects an append from a worker whose lease has been superseded.
        """

    def read(self, stream_id: str, *, from_sequence: int = 0) -> Sequence[StoredEvent]: ...

    def head(self, stream_id: str) -> StoredEvent | None: ...

    def streams(self) -> Sequence[str]: ...


@runtime_checkable
class KeyValueStore(Protocol):
    """Compare-and-set key/value storage for materialised state and caches."""

    def get(self, key: str) -> tuple[Any, int] | None:
        """Return ``(value, version)`` or ``None`` when absent."""

    def put(self, key: str, value: Any, *, expected_version: int | None = None) -> int:
        """Write and return the new version; raise ``WRITE_CONFLICT`` on mismatch."""

    def delete(self, key: str, *, expected_version: int | None = None) -> None: ...

    def scan(self, prefix: str) -> Iterator[tuple[str, Any, int]]: ...


@runtime_checkable
class ArtifactStore(Protocol):
    """Content-addressed blob storage.

    ``put`` returns the digest it actually computed over the stored bytes, not
    the digest the caller claimed.  A caller-supplied digest is verified, never
    trusted.
    """

    def put(self, data: bytes, *, media_type: str, expected_digest: str | None = None) -> str: ...

    def get(self, artifact_digest: str) -> bytes: ...

    def exists(self, artifact_digest: str) -> bool: ...

    def stat(self, artifact_digest: str) -> Mapping[str, Any]: ...


@runtime_checkable
class LeaseStore(Protocol):
    """Monotonic fencing-token issuance for exclusive resources."""

    def acquire(self, resource_id: str, owner_id: str, *,
                ttl_seconds: int) -> Mapping[str, Any]: ...

    def renew(self, resource_id: str, owner_id: str, fencing_token: int, *,
              ttl_seconds: int) -> Mapping[str, Any]: ...

    def release(self, resource_id: str, owner_id: str, fencing_token: int) -> None: ...

    def current_token(self, resource_id: str) -> int: ...


@runtime_checkable
class RepositoryReader(Protocol):
    """Read-only view of a repository snapshot.

    The snapshot is immutable and identified by ``snapshot_sha``.  Any read
    against a different snapshot must raise ``STALE_SNAPSHOT`` instead of
    silently serving newer content.
    """

    @property
    def snapshot_sha(self) -> str: ...

    def list_paths(self) -> Sequence[str]: ...

    def read_text(self, path: str) -> str: ...

    def read_bytes(self, path: str) -> bytes: ...

    def stat(self, path: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ToolInvoker(Protocol):
    """Executes a validated tool call inside a permission profile."""

    def invoke(self, descriptor_id: str, arguments: Mapping[str, Any], *,
               authority: Any) -> Mapping[str, Any]: ...


@runtime_checkable
class ProcessRunner(Protocol):
    """Runs a command inside a sandbox profile and reports a bounded result."""

    def run(self, argv: Sequence[str], *, cwd: str, env: Mapping[str, str],
            timeout_seconds: int, network: str) -> Mapping[str, Any]: ...


@runtime_checkable
class ModelProvider(Protocol):
    """A model endpoint.

    ``complete`` returns token accounting alongside the text so that cost and
    cache attribution are measured, not estimated, wherever the provider
    reports them.
    """

    @property
    def model_id(self) -> str: ...

    def complete(self, prompt_blocks: Sequence[Mapping[str, Any]], *,
                 max_output_tokens: int, stop: Sequence[str] = ()) -> Mapping[str, Any]: ...
