"""The kernel's four storage ports, implemented over the platform ``DurableStore``.

The merge that produced this package left one asymmetry.  For twenty-seven of the
thirty-one skills the kernel is strictly deeper than the legacy handler and the
bridge can simply delegate.  For the four run/authority/policy/lease skills the
*legacy* side owns something the kernel does not: a real transactional store.
The kernel's orchestrator is pure — it speaks to :mod:`elmos_autonomy_kernel.ports`
and its registry entry point instantiates the in-memory adapters — so a bridge that
merely forwarded to it would compute a better answer and write nothing down.  That
is a regression dressed as an upgrade.

This module closes the gap from the other side: it implements ``EventStore``,
``KeyValueStore``, ``ArtifactStore`` and ``LeaseStore`` on top of ``DurableStore``,
so kernel-computed facts land in the same SQLite tables, transactions and tenant
scoping the legacy engine has always used.

Three things are worth knowing before reading the code.

**These adapters raise the kernel's** :class:`elmos_autonomy_kernel.errors.KernelError`,
not this package's.  The kernel catches its own type; a platform ``ContractError``
crossing into kernel code would escape every ``except KernelError`` in it and be
normalised to ``FAILED_TERMINAL`` with the real reason thrown away.  Where a
``DurableStore`` call raises a platform error with a meaning the port already has a
code for, it is translated rather than wrapped.

**What ``DurableStore`` does not give, the adapter implements — it is never assumed.**
``DurableStore.append_event`` has no optimistic ``expected_sequence``, no
payload-comparing idempotency key, no fencing token and no hash chain.  Those four
are the whole point of the port, so they are built here, durably, out of the tables
that already exist (``events`` for the log, ``cache_entries`` as a keyed side table).
Nothing in ``storage.py`` is modified and no table is added.

**Where a guarantee is weaker than the in-process adapter's, it is stated, not
smoothed over.**  Each class carries a "Limits" paragraph naming exactly what it
cannot promise.  The three that matter:

* Every compare-then-write here (``expected_sequence``, key/value CAS, the lease
  holder check) spans two ``DurableStore`` calls and therefore two transactions.
  One lock per store, shared by every adapter over it, serialises callers *in
  this process*; two processes against one SQLite file can still interleave
  between the check and the write.  The
  in-memory and PostgreSQL adapters do both under one lock or one transaction.
* Lease and cache expiry read the real wall clock, because that is what
  ``DurableStore`` stamps into its rows.  There is no injectable ``Clock`` here, so
  the kernel's ``FixedClock``-driven expiry tests cannot be run against this backend.
* The event hash chain is computed by folding the stored log.  For events this
  adapter wrote it is *also* durable — the chain digest is stored as the row's
  ``event_id`` — so a rewritten payload no longer matches its own address.  For rows
  written directly by ``DurableStore`` (``RUN_CREATED``, ``STATE_CHANGED``,
  ``CHECKPOINT_CREATED``) the chain is derived only, and detects reordering and
  truncation but not a coordinated rewrite of the whole stream.
"""

from __future__ import annotations

import json
import threading
import weakref
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from elmos_autonomy_kernel.contracts import canonical_json, digest, digest_bytes
from elmos_autonomy_kernel.errors import KernelError

from .errors import KernelError as PlatformError
from .storage import DurableStore

__all__ = [
    "DurableStoreArtifactStore",
    "DurableStoreEventStore",
    "DurableStoreKeyValueStore",
    "DurableStoreLeaseStore",
    "DurableEvent",
    "GENESIS",
]

#: The chain value a stream starts from.  Identical to the in-memory adapter's, so
#: a stream written here and a stream written there hash to the same chain.
GENESIS = "sha256:" + "0" * 64

_EVENT_INDEX_LAYER = "kernel-event-stream-index"
_EVENT_IDEMPOTENCY_LAYER = "kernel-event-idempotency"
_EVENT_FENCING_LAYER = "kernel-event-fencing"
_KV_LAYER = "kernel-kv"
_KV_INDEX_LAYER = "kernel-kv-index"
_ARTIFACT_INDEX_LAYER = "kernel-artifact-index"
_LEASE_LAYER = "kernel-lease"
_INDEX_KEY = "__index__"

#: One re-entrant lock per ``DurableStore``, shared by every adapter over it.
#: Each adapter here does compare-then-write across two ``DurableStore`` calls,
#: and two of them can be constructed per dispatch (the lease kernel gets a lease
#: store *and* an event store).  A per-instance lock would serialise nothing:
#: the two racing callers would each hold their own.  Keyed weakly so a closed
#: store's lock is collected with it.
_STORE_LOCKS: weakref.WeakKeyDictionary[DurableStore, threading.RLock] = (
    weakref.WeakKeyDictionary()
)
_LOCK_REGISTRY = threading.Lock()


def _lock_for(store: DurableStore) -> threading.RLock:
    with _LOCK_REGISTRY:
        found = _STORE_LOCKS.get(store)
        if found is None:
            found = threading.RLock()
            _STORE_LOCKS[store] = found
        return found


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _malformed(message: str, action: str) -> KernelError:
    return KernelError(code="MALFORMED_INPUT", message=message, recommended_action=action)


def _require_stream(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise _malformed(f"{field_name} must be a non-empty string", f"supply {field_name}")
    return value


class _CacheBacked:
    """Shared helper for the side tables these adapters keep in ``cache_entries``.

    ``DurableStore`` exposes ``cache_get``/``cache_put`` as a general tenant-scoped
    key/value surface.  Reusing it is what keeps idempotency keys, fencing
    high-water marks, key indexes and artifact addresses *durable* instead of living
    in a process-local dict that a restart would silently empty — which would turn
    "this delivery is a duplicate" into "this delivery is new".
    """

    __slots__ = ("_store", "_tenant_id", "_lock")

    def __init__(self, store: DurableStore, tenant_id: str) -> None:
        self._store = store
        self._tenant_id = tenant_id
        self._lock = _lock_for(store)

    def _read(self, layer: str, key: str) -> Any | None:
        row = self._store.cache_get(tenant_id=self._tenant_id, layer=layer, key_hash=key)
        if row is None:
            return None
        value = row.get("value")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as exc:  # pragma: no cover - corrupt row
                raise KernelError(
                    code="DIGEST_MISMATCH",
                    message=f"cache row {layer}/{key} is not decodable JSON",
                    recommended_action="treat the side table as corrupt",
                ) from exc
        return value

    def _write(self, layer: str, key: str, value: Any) -> None:
        self._store.cache_put(
            tenant_id=self._tenant_id, layer=layer, key_hash=key, value=value,
            provenance={"producer": "kernel_store_adapter", "layer": layer},
        )

    def _index(self, layer: str) -> list[str]:
        found = self._read(layer, _INDEX_KEY)
        return [str(item) for item in found] if isinstance(found, list) else []

    def _index_add(self, layer: str, key: str) -> None:
        keys = self._index(layer)
        if key not in keys:
            keys.append(key)
            self._write(layer, _INDEX_KEY, sorted(keys))

    def _index_remove(self, layer: str, key: str) -> None:
        keys = self._index(layer)
        if key in keys:
            keys.remove(key)
            self._write(layer, _INDEX_KEY, sorted(keys))


@dataclass(frozen=True, slots=True)
class DurableEvent:
    """One row of the ``events`` table, presented as a kernel ``StoredEvent``."""

    sequence: int
    event_id: str
    stream_id: str
    payload: Mapping[str, Any]
    hash_chain: str
    event_type: str
    recorded_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "eventId": self.event_id,
            "streamId": self.stream_id,
            "payload": dict(self.payload),
            "hashChain": self.hash_chain,
        }


class DurableStoreEventStore(_CacheBacked):
    """The kernel ``EventStore`` over ``DurableStore``'s append-only ``events`` table.

    A kernel *stream* is a durable *run*.  If ``stream_id`` names an existing run in
    this tenant the adapter writes into that run's log — which is the case that
    matters, because it puts the kernel's hash-chained events into the same log as
    the legacy engine's ``STATE_CHANGED`` rows rather than into a parallel universe.
    Otherwise a run is created for the stream, keyed by an idempotency key derived
    from the stream id, so resolving the same stream twice never forks it.

    ``event_type`` is not part of the port, so the adapter derives one from the
    payload's ``eventType`` and prefixes it (``KERNEL_RUN_STATE_CHANGED``).  The
    prefix is not cosmetic: ``DurableStore.replay_state`` folds ``RUN_CREATED`` and
    ``STATE_CHANGED`` rows to check its materialised state against its own log, and
    an unprefixed kernel ``RUN_CREATED`` landing after a legacy transition would
    make that check fail on a run that is perfectly consistent.

    Limits
    ------
    * ``expected_sequence`` is checked in this adapter and the append happens in a
      second ``DurableStore`` transaction.  The per-store lock makes that atomic for
      callers in this process only.
    * Sequences are ``DurableStore``'s own, so a stream backed by a run created
      through ``create_run`` starts at 2: sequence 1 is that run's ``RUN_CREATED``
      row.  This is deliberate — the store's log is the truth and hiding its first
      event would be a lie about what is recorded — but it means the port's
      "first append is sequence 1" reading does not hold here.
    * The chain is stored as ``event_id`` for events written through this adapter
      and derived for rows written directly by ``DurableStore``; see the module
      docstring for exactly what each detects.
    """

    __slots__ = ("_account_id", "_prefix", "_runs")

    def __init__(self, store: DurableStore, *, tenant_id: str = "local",
                 account_id: str = "local", event_type_prefix: str = "KERNEL_") -> None:
        super().__init__(store, tenant_id)
        self._account_id = account_id
        self._prefix = event_type_prefix
        self._runs: dict[str, str] = {}

    # --- stream resolution ---------------------------------------------------

    def _run_id(self, stream_id: str) -> str:
        _require_stream(stream_id, "stream_id")
        with self._lock:
            known = self._runs.get(stream_id)
            if known is not None:
                return known
            existing = self._store.get_run(stream_id, tenant_id=self._tenant_id)
            if existing is not None:
                run_id = str(existing["run_id"])
            else:
                created = self._store.create_run(
                    tenant_id=self._tenant_id, account_id=self._account_id,
                    task_spec_hash=digest({"kernelStream": stream_id}),
                    workflow_version="2.0.0", repo_snapshot_sha=None,
                    payload={"kernelStream": stream_id},
                    idempotency_key=f"kernel-stream:{stream_id}",
                )
                run_id = str(created["run_id"])
            self._runs[stream_id] = run_id
            self._index_add(_EVENT_INDEX_LAYER, stream_id)
            return run_id

    def _event_type(self, payload: Mapping[str, Any]) -> str:
        declared = payload.get("eventType") if isinstance(payload, Mapping) else None
        if isinstance(declared, str) and declared.replace("_", "").isalnum():
            return f"{self._prefix}{declared}"
        return f"{self._prefix}EVENT"

    def _records(self, stream_id: str, run_id: str) -> list[DurableEvent]:
        rows = self._store.events_since(run_id, 0, tenant_id=self._tenant_id)
        chain = GENESIS
        events: list[DurableEvent] = []
        for row in rows:
            payload = row.get("payload")
            payload = dict(payload) if isinstance(payload, Mapping) else {"raw": payload}
            sequence = int(row["sequence_no"])
            chain = digest({
                "previous": chain,
                "sequence": sequence,
                "streamId": stream_id,
                "payload": payload,
            })
            events.append(DurableEvent(
                sequence=sequence,
                event_id=str(row["event_id"]),
                stream_id=stream_id,
                payload=payload,
                hash_chain=chain,
                event_type=str(row["event_type"]),
                recorded_at=str(row.get("occurred_at", "")),
            ))
        return events

    # --- port ----------------------------------------------------------------

    def append(self, stream_id: str, payload: Mapping[str, Any], *,
               expected_sequence: int | None = None,
               idempotency_key: str | None = None,
               fencing_token: int | None = None) -> DurableEvent:
        """Append one event, honouring the port's three concurrency contracts."""

        if not isinstance(payload, Mapping):
            raise _malformed("event payload must be a mapping", "supply a JSON object")
        run_id = self._run_id(stream_id)
        with self._lock:
            if idempotency_key is not None:
                replay = self._replayed(stream_id, run_id, idempotency_key, payload)
                if replay is not None:
                    return replay
            if fencing_token is not None:
                self._check_fencing(stream_id, fencing_token)
            existing = self._records(stream_id, run_id)
            current = existing[-1].sequence if existing else 0
            if expected_sequence is not None and expected_sequence != current:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=(
                        f"stream {stream_id!r} is at sequence {current}, "
                        f"caller expected {expected_sequence}"
                    ),
                    retryable=True,
                    recommended_action="re-read the stream and retry the decision",
                )
            previous = existing[-1].hash_chain if existing else GENESIS
            chain = digest({
                "previous": previous,
                "sequence": current + 1,
                "streamId": stream_id,
                "payload": dict(payload),
            })
            try:
                self._store.append_event(
                    run_id, self._event_type(payload), dict(payload),
                    event_id=chain, tenant_id=self._tenant_id,
                )
            except PlatformError as exc:  # pragma: no cover - run vanished mid-call
                raise KernelError(
                    code="ORCHESTRATOR_INCONSISTENT",
                    message=f"durable append to {stream_id!r} failed: {exc.info.code}",
                    recommended_action="verify the run row still exists in this tenant",
                ) from exc
            stored = self._records(stream_id, run_id)[-1]
            if stored.hash_chain != chain:  # pragma: no cover - concurrent writer
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=(
                        f"stream {stream_id!r} moved while this append was in flight; "
                        "the computed chain does not match the stored one"
                    ),
                    retryable=True,
                    recommended_action="re-read the stream and retry the decision",
                )
            if idempotency_key is not None:
                self._write(_EVENT_IDEMPOTENCY_LAYER, self._idem_key(stream_id, idempotency_key),
                            {"sequence": stored.sequence, "eventId": stored.event_id,
                             "payload": dict(payload)})
            return stored

    def read(self, stream_id: str, *, from_sequence: int = 0) -> Sequence[DurableEvent]:
        run_id = self._run_id(stream_id)
        return tuple(item for item in self._records(stream_id, run_id)
                     if item.sequence > from_sequence)

    def head(self, stream_id: str) -> DurableEvent | None:
        events = self.read(stream_id)
        return events[-1] if events else None

    def streams(self) -> Sequence[str]:
        """Streams this adapter has resolved, read back from its durable index.

        Not "every run in the store": ``DurableStore`` has no run enumeration, and a
        run that was never addressed as a kernel stream has no chain to report.  The
        index is written on resolution, so the answer survives a restart rather than
        emptying itself into a plausible-looking lie.
        """

        with self._lock:
            return tuple(sorted(set(self._index(_EVENT_INDEX_LAYER)) | set(self._runs)))

    def verify_chain(self, stream_id: str) -> bool:
        """Recompute the chain, and check it against every chain stored as an id.

        Events this adapter wrote carry their chain digest as their ``event_id``, so
        for those the check is genuinely tamper-evident.  Rows ``DurableStore`` wrote
        itself carry a UUID; they still contribute to the fold, so reordering or
        truncating them breaks every later link.
        """

        run_id = self._run_id(stream_id)
        for event in self._records(stream_id, run_id):
            if event.event_id.startswith("sha256:") and event.event_id != event.hash_chain:
                return False
        return True

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _idem_key(stream_id: str, idempotency_key: str) -> str:
        return digest({"stream": stream_id, "key": idempotency_key})

    def _replayed(self, stream_id: str, run_id: str, idempotency_key: str,
                  payload: Mapping[str, Any]) -> DurableEvent | None:
        record = self._read(_EVENT_IDEMPOTENCY_LAYER, self._idem_key(stream_id, idempotency_key))
        if not isinstance(record, Mapping):
            return None
        if canonical_json(record.get("payload")) != canonical_json(dict(payload)):
            raise KernelError(
                code="IDEMPOTENCY_CONFLICT",
                message=(
                    f"idempotency key {idempotency_key!r} was already used on stream "
                    f"{stream_id!r} with a different payload"
                ),
                recommended_action="use a key derived from the payload digest",
            )
        wanted = int(record.get("sequence", 0))
        for event in self._records(stream_id, run_id):
            if event.sequence == wanted:
                return event
        raise KernelError(  # pragma: no cover - log truncated under an idempotency key
            code="EVIDENCE_MISSING",
            message=(
                f"idempotency key {idempotency_key!r} points at sequence {wanted} on "
                f"{stream_id!r}, which is no longer in the log"
            ),
            recommended_action="treat the stream as truncated; do not re-apply the effect",
        )

    def _check_fencing(self, stream_id: str, fencing_token: int) -> None:
        key = digest({"stream": stream_id})
        record = self._read(_EVENT_FENCING_LAYER, key)
        current = int(record.get("token", 0)) if isinstance(record, Mapping) else 0
        if fencing_token < current:
            raise KernelError(
                code="FENCING_REJECTED",
                message=(
                    f"fencing token {fencing_token} is stale for stream {stream_id!r}; "
                    f"current is {current}"
                ),
                retryable=False,
                recommended_action="re-acquire the lease and rebuild local state",
            )
        if fencing_token != current:
            self._write(_EVENT_FENCING_LAYER, key, {"token": int(fencing_token)})


class DurableStoreKeyValueStore(_CacheBacked):
    """The kernel ``KeyValueStore`` over ``DurableStore``'s ``cache_entries`` table.

    Versions are carried in the stored envelope because the table has no version
    column, and a delete is a tombstone because the table has no delete method.  A
    tombstone is the honest shape anyway: the row is what proves the key was removed
    rather than never written.

    Limits
    ------
    * Compare-and-set is a read followed by a write in a second transaction; the
      per-store lock covers this process only.
    * ``scan`` reads a durable key index maintained on every write, so a prefix scan
      is O(keys) per write rather than a table scan per read.  ``DurableStore``
      exposes no listing over ``cache_entries``, and answering a scan from a
      process-local set would silently under-report after a restart.
    """

    __slots__ = ("_layer", "_index_layer")

    def __init__(self, store: DurableStore, *, tenant_id: str = "local",
                 layer: str = _KV_LAYER) -> None:
        super().__init__(store, tenant_id)
        self._layer = layer
        self._index_layer = f"{_KV_INDEX_LAYER}:{layer}"

    def get(self, key: str) -> tuple[Any, int] | None:
        record = self._read(self._layer, _require_stream(key, "key"))
        if not isinstance(record, Mapping) or record.get("deleted"):
            return None
        return record.get("value"), int(record.get("version", 0))

    def put(self, key: str, value: Any, *, expected_version: int | None = None) -> int:
        _require_stream(key, "key")
        with self._lock:
            record = self._read(self._layer, key)
            current = int(record.get("version", 0)) if isinstance(record, Mapping) else 0
            if expected_version is not None and expected_version != current:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=(
                        f"key {key!r} is at version {current}, caller expected "
                        f"{expected_version}"
                    ),
                    retryable=True,
                    recommended_action="re-read the key and retry",
                )
            version = current + 1
            self._write(self._layer, key, {"value": value, "version": version, "deleted": False})
            self._index_add(self._index_layer, key)
            return version

    def delete(self, key: str, *, expected_version: int | None = None) -> None:
        _require_stream(key, "key")
        with self._lock:
            record = self._read(self._layer, key)
            if not isinstance(record, Mapping) or record.get("deleted"):
                return
            current = int(record.get("version", 0))
            if expected_version is not None and expected_version != current:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=f"key {key!r} version mismatch on delete",
                    retryable=True,
                    recommended_action="re-read the key and retry",
                )
            self._write(self._layer, key, {"value": None, "version": current, "deleted": True})
            self._index_remove(self._index_layer, key)

    def scan(self, prefix: str) -> Iterator[tuple[str, Any, int]]:
        with self._lock:
            keys = [key for key in self._index(self._index_layer) if key.startswith(prefix)]
            found = []
            for key in sorted(keys):
                entry = self.get(key)
                if entry is not None:
                    found.append((key, entry[0], entry[1]))
        yield from found


class DurableStoreArtifactStore(_CacheBacked):
    """The kernel ``ArtifactStore`` over ``DurableStore.put_artifact``/``read_artifact``.

    ``DurableStore`` addresses a blob by a generated ``artifact_id`` and only
    incidentally by content hash, while the port addresses by digest alone.  The
    adapter keeps the digest -> artifact-id map in the same durable side table it
    uses everywhere else, so ``get`` after a restart still resolves.

    Limits
    ------
    * ``exists`` and ``get`` answer from that index, so a blob written into
      ``artifacts`` by some other code path is invisible here even though its bytes
      are present.  Reporting it as present without an address we can resolve would
      be worse: the next ``get`` would fail after ``exists`` said yes.
    """

    __slots__ = ("_kind",)

    def __init__(self, store: DurableStore, *, tenant_id: str = "local",
                 kind: str = "kernel-artifact") -> None:
        super().__init__(store, tenant_id)
        self._kind = kind

    def put(self, data: bytes, *, media_type: str, expected_digest: str | None = None) -> str:
        if not isinstance(data, (bytes, bytearray)):
            raise _malformed("artifact payload must be bytes",
                             "encode the payload before storing it")
        raw = bytes(data)
        computed = digest_bytes(raw)
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
            row = self._store.put_artifact(
                tenant_id=self._tenant_id, content=raw, kind=self._kind, media_type=media_type,
                metadata={"digest": computed},
            )
            self._write(_ARTIFACT_INDEX_LAYER, computed, {
                "artifactId": str(row["artifact_id"]),
                "byteCount": len(raw),
                "mediaType": media_type,
            })
        return computed

    def _entry(self, artifact_digest: str) -> Mapping[str, Any]:
        record = self._read(_ARTIFACT_INDEX_LAYER, _require_stream(artifact_digest, "digest"))
        if not isinstance(record, Mapping):
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact or restore from backup",
            )
        return record

    def get(self, artifact_digest: str) -> bytes:
        record = self._entry(artifact_digest)
        try:
            data = self._store.read_artifact(str(record["artifactId"]),
                                             tenant_id=self._tenant_id)
        except PlatformError as exc:
            raise KernelError(
                code="DIGEST_MISMATCH" if exc.info.code == "ARTIFACT_CORRUPT"
                else "EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} could not be read: {exc.info.code}",
                recommended_action="treat the store as corrupt for this address",
            ) from exc
        if digest_bytes(data) != artifact_digest:  # pragma: no cover - defensive
            raise KernelError(
                code="DIGEST_MISMATCH",
                message=f"stored artifact {artifact_digest} no longer hashes to its address",
                recommended_action="treat the store as corrupt",
            )
        return data

    def exists(self, artifact_digest: str) -> bool:
        return isinstance(
            self._read(_ARTIFACT_INDEX_LAYER, _require_stream(artifact_digest, "digest")),
            Mapping,
        )

    def stat(self, artifact_digest: str) -> Mapping[str, Any]:
        record = self._entry(artifact_digest)
        return {
            "digest": artifact_digest,
            "byteCount": int(record.get("byteCount", 0)),
            "mediaType": str(record.get("mediaType", "application/octet-stream")),
        }


class DurableStoreLeaseStore(_CacheBacked):
    """The kernel ``LeaseStore`` over ``DurableStore``'s lease table.

    Monotonicity across release is the guarantee the kernel actually depends on: a
    worker that paused past its TTL must never see its old token become current
    again.  ``DurableStore.acquire_lease`` mints ``MAX(fencing_token) + 1`` over
    *every* row for the resource, released rows included, and nothing in this
    package deletes a lease row — so the guarantee holds today.  It is not, however,
    enforced by a constraint: a retention job that pruned released leases would
    silently reintroduce the exact bug fencing exists to prevent, and nothing would
    fail.  So this adapter keeps its own durable high-water mark and refuses a token
    that is not strictly greater than every token it has already issued, rather than
    trusting a property of the table that a future migration could remove.

    ``DurableStore.acquire_lease`` also does not refuse a second live owner — it just
    mints the next token — so the ``LEASE_HELD_BY_OTHER`` check is implemented here,
    against a durable holder record rather than a process-local dict.

    Limits
    ------
    * The holder check and the mint are two ``DurableStore`` transactions; the
      per-store lock serialises them within this process only.  If a second live
      acquisition did slip through, the high-water mark still guarantees the newer
      token wins, which is the property that keeps writes safe.
    * Expiry is real wall-clock, because that is what ``DurableStore`` stamps into
      the row.  There is no injectable clock, so a test cannot expire a lease here
      without waiting.
    """

    __slots__ = ("_resource_type",)

    def __init__(self, store: DurableStore, *, tenant_id: str = "local",
                 resource_type: str = "workspace") -> None:
        super().__init__(store, tenant_id)
        self._resource_type = resource_type

    def _key(self, resource_id: str) -> str:
        return digest({"resourceType": self._resource_type, "resourceId": resource_id})

    def _record(self, resource_id: str) -> Mapping[str, Any]:
        found = self._read(_LEASE_LAYER, self._key(resource_id))
        return found if isinstance(found, Mapping) else {}

    def _lost(self, message: str, **details: Any) -> KernelError:
        return KernelError(
            code="LEASE_LOST", message=message, retryable=False,
            recommended_action="stop writing immediately, re-acquire and rebuild local state",
            details=details,
        )

    def _lease_row(self, record: Mapping[str, Any], resource_id: str) -> dict[str, Any]:
        return {
            "lease_id": str(record.get("leaseId", "")),
            "resource_type": self._resource_type,
            "resource_id": resource_id,
            "owner_id": str(record.get("ownerId", "")),
            "fencing_token": int(record.get("fencingToken", 0)),
        }

    def acquire(self, resource_id: str, owner_id: str, *,
                ttl_seconds: int) -> Mapping[str, Any]:
        _require_stream(resource_id, "resource_id")
        _require_stream(owner_id, "owner_id")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise _malformed("lease ttl must be positive", "supply ttl_seconds > 0")
        with self._lock:
            record = self._record(resource_id)
            if (record.get("state") == "ACTIVE" and record.get("ownerId") != owner_id
                    and str(record.get("expiresAt", "")) > _iso(_now())):
                raise KernelError(
                    code="LEASE_HELD_BY_OTHER",
                    message=(
                        f"resource {resource_id!r} is leased by {record.get('ownerId')!r} "
                        f"until {record.get('expiresAt')}"
                    ),
                    retryable=True,
                    recommended_action="wait for expiry or take over explicitly",
                )
            high_water = int(record.get("highWater", 0))
            row = self._store.acquire_lease(self._resource_type, resource_id, owner_id,
                                            ttl_seconds=ttl_seconds)
            token = int(row["fencing_token"])
            if token <= high_water:
                raise KernelError(
                    code="ORCHESTRATOR_INCONSISTENT",
                    message=(
                        f"lease table issued token {token} for {resource_id!r} but "
                        f"{high_water} was already handed out; tokens are not monotonic"
                    ),
                    retryable=False,
                    recommended_action=(
                        "stop issuing leases for this resource; released lease rows have "
                        "been pruned and fencing is no longer sound"
                    ),
                    details={"issued": token, "highWater": high_water},
                )
            self._persist(resource_id, row, token, ttl_seconds)
            return self._payload(resource_id, owner_id, token, str(row["expires_at"]))

    def renew(self, resource_id: str, owner_id: str, fencing_token: int, *,
              ttl_seconds: int) -> Mapping[str, Any]:
        with self._lock:
            record = self._record(resource_id)
            if not record or record.get("state") != "ACTIVE":
                raise self._lost(f"no live lease exists for {resource_id!r}",
                                 resourceId=resource_id, presentedToken=fencing_token)
            if (record.get("ownerId") != owner_id
                    or int(record.get("fencingToken", 0)) != fencing_token):
                raise self._lost(
                    f"lease on {resource_id!r} is at token {record.get('fencingToken')} "
                    f"(owner {record.get('ownerId')!r}); caller holds {fencing_token}",
                    resourceId=resource_id, presentedToken=fencing_token,
                )
            try:
                row = self._store.heartbeat_lease(self._lease_row(record, resource_id),
                                                  ttl_seconds=ttl_seconds)
            except PlatformError as exc:
                raise self._lost(
                    f"lease on {resource_id!r} is no longer current: {exc.info.code}",
                    resourceId=resource_id, presentedToken=fencing_token,
                ) from exc
            expires = str(row["expires_at"])
            self._write(_LEASE_LAYER, self._key(resource_id), {
                **dict(record), "expiresAt": expires, "state": "ACTIVE",
            })
            return self._payload(resource_id, owner_id, fencing_token, expires)

    def release(self, resource_id: str, owner_id: str, fencing_token: int) -> None:
        with self._lock:
            record = self._record(resource_id)
            if not record or record.get("state") != "ACTIVE":
                return
            if (record.get("ownerId") != owner_id
                    or int(record.get("fencingToken", 0)) != fencing_token):
                raise self._lost(
                    f"cannot release {resource_id!r}: it is held by "
                    f"{record.get('ownerId')!r} at token {record.get('fencingToken')}",
                    resourceId=resource_id, presentedToken=fencing_token,
                )
            try:
                self._store.release_lease(self._lease_row(record, resource_id))
            except PlatformError:  # pragma: no cover - already released or superseded
                pass
            self._write(_LEASE_LAYER, self._key(resource_id), {
                **dict(record), "state": "RELEASED",
            })

    def current_token(self, resource_id: str) -> int:
        """The highest token ever issued for ``resource_id``; ``0`` if never leased.

        Read from the high-water mark, not from the live row, so a release does not
        make an old token current again.
        """

        return int(self._record(resource_id).get("highWater", 0))

    # --- helpers -------------------------------------------------------------

    def _persist(self, resource_id: str, row: Mapping[str, Any], token: int,
                 ttl_seconds: int) -> None:
        self._write(_LEASE_LAYER, self._key(resource_id), {
            "leaseId": str(row["lease_id"]),
            "ownerId": str(row["owner_id"]),
            "fencingToken": token,
            "highWater": token,
            "state": "ACTIVE",
            "expiresAt": str(row["expires_at"]),
            "ttlSeconds": int(ttl_seconds),
        })

    @staticmethod
    def _payload(resource_id: str, owner_id: str, token: int,
                 expires_at: str) -> Mapping[str, Any]:
        return {
            "resourceId": resource_id,
            "ownerId": owner_id,
            "fencingToken": token,
            "expiresAt": expires_at,
        }
