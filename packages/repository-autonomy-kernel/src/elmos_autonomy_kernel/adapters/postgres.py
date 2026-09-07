"""PostgreSQL adapters.

These implement exactly the same contract as :mod:`.memory`, and the same
invariant tests run against both.  That symmetry is the point: an invariant that
holds in a single process and fails under two connections is not an invariant,
it is a coincidence, and the only way to find out is to run the identical
assertions against a real server.

Three concurrency decisions are worth stating up front, because they are the
ones a reviewer should attack first:

* Every ``append`` takes a transaction-scoped **advisory lock** on the stream.
  Deriving ``sequence = head + 1`` without it is a lost-update race: two workers
  read the same head and one of their events vanishes behind the other's primary
  key.  The lock is keyed by a hash of the stream id, so it costs one integer
  and is released by COMMIT whatever happens.
* The **fencing high-water mark lives in its own table**, not in the lease row.
  Releasing a lease deletes the row; if the next token were derived from the
  remaining rows it would restart, and a paused worker holding the old token
  would find itself current again.
* Reads **re-verify** what they return: an artifact is re-hashed, a chain is
  recomputable.  A store that trusts its own bytes cannot detect corruption, and
  silent corruption in an evidence store is worse than an outage.

``psycopg`` (v3) is an optional dependency; importing this module without it
raises a kernel error naming the missing package rather than an ImportError
somewhere deep in a call stack.
"""

from __future__ import annotations

import json
import threading
import zlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..contracts import canonical_json, digest, digest_bytes, require_identifier
from ..errors import KernelError
from .memory import GENESIS, SystemClock

try:  # pragma: no cover - exercised by the absence path only
    import psycopg  # noqa: F401 - imported to prove the driver is installed
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover
    raise KernelError(
        code="MISSING_REQUIRED_INPUT",
        message="the PostgreSQL adapters need the optional 'psycopg' dependency",
        recommended_action="pip install 'elmos-autonomy-kernel[postgres]'",
    ) from exc

__all__ = [
    "PostgresEventStore",
    "PostgresKeyValueStore",
    "PostgresArtifactStore",
    "PostgresLeaseStore",
    "PostgresEvent",
    "apply_migrations",
    "MIGRATIONS",
]

#: Migration files are applied in name order.  Kept as a tuple rather than a
#: directory scan so that an unexpected file cannot silently become schema.
#:
#: V007 is where the core's stream tables sit in the merged package: V001-V006
#: are the platform half's control-plane schema and are applied by its own
#: migration runner.  The two are additive on purpose - the core's log is
#: chain-verified and keyed by an arbitrary stream id, which ``autonomy_events``
#: (a uuid FK to ``autonomy_runs``, with no hash column) cannot express.
MIGRATIONS: tuple[str, ...] = ("V007__autonomy_kernel_core_streams.sql",)


def _advisory_key(stream_id: str) -> int:
    """A stable 63-bit advisory-lock key for a stream id."""

    return zlib.crc32(stream_id.encode("utf-8")) & 0x7FFF_FFFF


def apply_migrations(connection: Any, migration_dir: str) -> tuple[str, ...]:
    """Apply the kernel's migrations in order and return the names applied."""

    from pathlib import Path

    applied: list[str] = []
    for name in MIGRATIONS:
        path = Path(migration_dir) / name
        if not path.exists():
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"migration {name} not found under {migration_dir}",
                recommended_action="ship db/migration alongside the package",
            )
        with connection.cursor() as cursor:
            cursor.execute(path.read_text(encoding="utf-8"))
        applied.append(name)
    connection.commit()
    return tuple(applied)


@dataclass(frozen=True, slots=True)
class PostgresEvent:
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


class _Pooled:
    """Minimal connection holder.

    A real deployment hands in a pool; this keeps one connection and serialises
    access with a lock so the adapters are safe to share between threads in
    tests and single-process tools without pulling in a pooling dependency.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._lock = threading.RLock()

    def cursor(self) -> Any:
        return self._connection.cursor(row_factory=dict_row)

    @property
    def connection(self) -> Any:
        return self._connection

    @property
    def lock(self) -> threading.RLock:
        return self._lock


class PostgresEventStore(_Pooled):
    """Append-only hash-chained log backed by ``autonomy_kernel_event``."""

    def __init__(self, connection: Any, clock: Any | None = None) -> None:
        super().__init__(connection)
        self._clock = clock or SystemClock()

    def append(self, stream_id: str, payload: Mapping[str, Any], *,
               expected_sequence: int | None = None,
               idempotency_key: str | None = None,
               fencing_token: int | None = None) -> PostgresEvent:
        require_identifier(stream_id, "stream_id")
        body = json.loads(canonical_json(payload))
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_advisory_key(stream_id),))

            if idempotency_key is not None:
                cursor.execute(
                    "SELECT sequence, event_id, payload, hash_chain, recorded_at "
                    "FROM autonomy_kernel_event WHERE stream_id = %s AND idempotency_key = %s",
                    (stream_id, idempotency_key),
                )
                previous = cursor.fetchone()
                if previous is not None:
                    if canonical_json(previous["payload"]) != canonical_json(body):
                        raise KernelError(
                            code="IDEMPOTENCY_CONFLICT",
                            message=(
                                f"idempotency key {idempotency_key!r} was already used on "
                                f"stream {stream_id!r} with a different payload"
                            ),
                            recommended_action="derive the key from the payload digest",
                        )
                    return _row_to_event(stream_id, previous)

            cursor.execute(
                "SELECT sequence, hash_chain, fencing_token FROM autonomy_kernel_event "
                "WHERE stream_id = %s ORDER BY sequence DESC LIMIT 1",
                (stream_id,),
            )
            head = cursor.fetchone()
            current_sequence = head["sequence"] if head else 0
            previous_hash = head["hash_chain"] if head else GENESIS

            if fencing_token is not None:
                cursor.execute(
                    "SELECT max(fencing_token) AS token FROM autonomy_kernel_event "
                    "WHERE stream_id = %s",
                    (stream_id,),
                )
                row = cursor.fetchone()
                seen = row["token"] if row and row["token"] is not None else 0
                if fencing_token < seen:
                    raise KernelError(
                        code="FENCING_REJECTED",
                        message=(
                            f"fencing token {fencing_token} is stale for stream "
                            f"{stream_id!r}; the log has already accepted {seen}"
                        ),
                        retryable=False,
                        recommended_action="re-acquire the lease and rebuild local state",
                    )

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

            sequence = current_sequence + 1
            chain = digest({
                "previous": previous_hash,
                "sequence": sequence,
                "streamId": stream_id,
                "payload": body,
            })
            event_id = f"evt-{digest({'s': stream_id, 'n': sequence})[7:19]}"
            recorded_at = self._clock.now()
            cursor.execute(
                "INSERT INTO autonomy_kernel_event "
                "(stream_id, sequence, event_id, payload, hash_chain, idempotency_key, "
                " fencing_token, recorded_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (stream_id, sequence, event_id, json.dumps(body), chain,
                 idempotency_key, fencing_token, recorded_at),
            )
            return PostgresEvent(
                sequence=sequence, event_id=event_id, stream_id=stream_id,
                payload=body, hash_chain=chain, recorded_at=recorded_at,
            )

    def read(self, stream_id: str, *, from_sequence: int = 0) -> Sequence[PostgresEvent]:
        with self.lock, self.cursor() as cursor:
            cursor.execute(
                "SELECT sequence, event_id, payload, hash_chain, recorded_at "
                "FROM autonomy_kernel_event WHERE stream_id = %s AND sequence > %s "
                "ORDER BY sequence",
                (stream_id, from_sequence),
            )
            return tuple(_row_to_event(stream_id, row) for row in cursor.fetchall())

    def head(self, stream_id: str) -> PostgresEvent | None:
        with self.lock, self.cursor() as cursor:
            cursor.execute(
                "SELECT sequence, event_id, payload, hash_chain, recorded_at "
                "FROM autonomy_kernel_event WHERE stream_id = %s ORDER BY sequence DESC LIMIT 1",
                (stream_id,),
            )
            row = cursor.fetchone()
            return None if row is None else _row_to_event(stream_id, row)

    def streams(self) -> Sequence[str]:
        with self.lock, self.cursor() as cursor:
            cursor.execute("SELECT DISTINCT stream_id FROM autonomy_kernel_event ORDER BY stream_id")
            return tuple(row["stream_id"] for row in cursor.fetchall())

    def verify_chain(self, stream_id: str) -> bool:
        """Recompute the chain from stored rows; any edit to history breaks it."""

        previous = GENESIS
        for event in self.read(stream_id):
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


def _row_to_event(stream_id: str, row: Mapping[str, Any]) -> PostgresEvent:
    return PostgresEvent(
        sequence=row["sequence"],
        event_id=row["event_id"],
        stream_id=stream_id,
        payload=row["payload"],
        hash_chain=row["hash_chain"],
        recorded_at=row["recorded_at"],
    )


class PostgresKeyValueStore(_Pooled):
    """Versioned KV with compare-and-set semantics."""

    def get(self, key: str) -> tuple[Any, int] | None:
        with self.lock, self.cursor() as cursor:
            cursor.execute("SELECT value, version FROM autonomy_kernel_kv WHERE key = %s", (key,))
            row = cursor.fetchone()
            return None if row is None else (row["value"], row["version"])

    def put(self, key: str, value: Any, *, expected_version: int | None = None) -> int:
        body = json.loads(canonical_json(value))
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute(
                "SELECT version FROM autonomy_kernel_kv WHERE key = %s FOR UPDATE", (key,))
            row = cursor.fetchone()
            current = row["version"] if row else 0
            if expected_version is not None and expected_version != current:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=(
                        f"key {key!r} is at version {current}, "
                        f"caller expected {expected_version}"
                    ),
                    retryable=True,
                    recommended_action="re-read the key and retry",
                )
            version = current + 1
            cursor.execute(
                "INSERT INTO autonomy_kernel_kv (key, value, version) VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                "version = EXCLUDED.version, updated_at = now()",
                (key, json.dumps(body), version),
            )
            return version

    def delete(self, key: str, *, expected_version: int | None = None) -> None:
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute(
                "SELECT version FROM autonomy_kernel_kv WHERE key = %s FOR UPDATE", (key,))
            row = cursor.fetchone()
            if row is None:
                return
            if expected_version is not None and expected_version != row["version"]:
                raise KernelError(
                    code="WRITE_CONFLICT",
                    message=f"key {key!r} version mismatch on delete",
                    retryable=True,
                    recommended_action="re-read the key and retry",
                )
            cursor.execute("DELETE FROM autonomy_kernel_kv WHERE key = %s", (key,))

    def scan(self, prefix: str) -> Iterator[tuple[str, Any, int]]:
        with self.lock, self.cursor() as cursor:
            # LIKE with an escaped prefix: a key containing % or _ must not turn
            # into a wildcard and hand back somebody else's tenant.
            escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            cursor.execute(
                "SELECT key, value, version FROM autonomy_kernel_kv "
                "WHERE key LIKE %s ESCAPE '\\' ORDER BY key",
                (escaped + "%",),
            )
            rows = cursor.fetchall()
        for row in rows:
            yield row["key"], row["value"], row["version"]


class PostgresArtifactStore(_Pooled):
    """Content-addressed blobs in ``autonomy_kernel_artifact``."""

    def put(self, data: bytes, *, media_type: str, expected_digest: str | None = None) -> str:
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
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO autonomy_kernel_artifact (digest, media_type, byte_count, body) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (digest) DO NOTHING",
                (computed, media_type, len(data), data),
            )
        return computed

    def get(self, artifact_digest: str) -> bytes:
        with self.lock, self.cursor() as cursor:
            cursor.execute(
                "SELECT body FROM autonomy_kernel_artifact WHERE digest = %s", (artifact_digest,))
            row = cursor.fetchone()
        if row is None:
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact or restore from backup",
            )
        data = bytes(row["body"])
        if digest_bytes(data) != artifact_digest:
            raise KernelError(
                code="DIGEST_MISMATCH",
                message=f"artifact {artifact_digest} failed re-verification on read",
                recommended_action="treat the store as corrupt and quarantine it",
            )
        return data

    def exists(self, artifact_digest: str) -> bool:
        with self.lock, self.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM autonomy_kernel_artifact WHERE digest = %s", (artifact_digest,))
            return cursor.fetchone() is not None

    def stat(self, artifact_digest: str) -> Mapping[str, Any]:
        with self.lock, self.cursor() as cursor:
            cursor.execute(
                "SELECT media_type, byte_count FROM autonomy_kernel_artifact WHERE digest = %s",
                (artifact_digest,),
            )
            row = cursor.fetchone()
        if row is None:
            raise KernelError(
                code="EVIDENCE_MISSING",
                message=f"artifact {artifact_digest} is not in the store",
                recommended_action="re-produce the artifact",
            )
        return {"digest": artifact_digest, "byteCount": row["byte_count"],
                "mediaType": row["media_type"]}


class PostgresLeaseStore(_Pooled):
    """Monotonic fencing tokens with expiry, backed by two tables.

    The watermark table is the reason a released-and-reacquired resource never
    reissues a token: the lease row is the *current* holder, the watermark is
    the highest token ever handed out for that resource.
    """

    def __init__(self, connection: Any, clock: Any | None = None) -> None:
        super().__init__(connection)
        self._clock = clock or SystemClock()

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
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_advisory_key(resource_id),))
            cursor.execute(
                "SELECT owner_id, fencing_token, expires_at FROM autonomy_kernel_lease "
                "WHERE resource_id = %s",
                (resource_id,),
            )
            holder = cursor.fetchone()
            if holder is not None:
                expires_at = _as_utc(holder["expires_at"])
                if expires_at > now and holder["owner_id"] != owner_id:
                    raise KernelError(
                        code="LEASE_HELD_BY_OTHER",
                        message=(
                            f"resource {resource_id!r} is leased by "
                            f"{holder['owner_id']!r} until {expires_at.isoformat()}"
                        ),
                        retryable=True,
                        recommended_action="wait for expiry or take over explicitly",
                    )
            cursor.execute(
                "INSERT INTO autonomy_kernel_lease_watermark (resource_id, issued_token) "
                "VALUES (%s, 1) ON CONFLICT (resource_id) DO UPDATE "
                "SET issued_token = autonomy_kernel_lease_watermark.issued_token + 1 "
                "RETURNING issued_token",
                (resource_id,),
            )
            token = cursor.fetchone()["issued_token"]
            expires = now + timedelta(seconds=ttl_seconds)
            cursor.execute(
                "INSERT INTO autonomy_kernel_lease (resource_id, owner_id, fencing_token, expires_at) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (resource_id) DO UPDATE "
                "SET owner_id = EXCLUDED.owner_id, fencing_token = EXCLUDED.fencing_token, "
                "expires_at = EXCLUDED.expires_at, acquired_at = now()",
                (resource_id, owner_id, token, expires),
            )
            return {"resourceId": resource_id, "ownerId": owner_id,
                    "fencingToken": token, "expiresAt": expires}

    def renew(self, resource_id: str, owner_id: str, fencing_token: int, *,
              ttl_seconds: int) -> Mapping[str, Any]:
        now = self._clock.now()
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute(
                "SELECT owner_id, fencing_token, expires_at FROM autonomy_kernel_lease "
                "WHERE resource_id = %s FOR UPDATE",
                (resource_id,),
            )
            holder = cursor.fetchone()
            if holder is None:
                raise KernelError(
                    code="LEASE_LOST",
                    message=f"no lease exists for {resource_id!r}",
                    recommended_action="re-acquire the lease and rebuild local state",
                )
            if holder["owner_id"] != owner_id or holder["fencing_token"] != fencing_token:
                raise KernelError(
                    code="LEASE_LOST",
                    message=(
                        f"lease on {resource_id!r} moved to token "
                        f"{holder['fencing_token']} (owner {holder['owner_id']!r}); "
                        f"caller holds {fencing_token}"
                    ),
                    recommended_action="stop writing immediately and re-acquire",
                )
            if _as_utc(holder["expires_at"]) <= now:
                raise KernelError(
                    code="LEASE_LOST",
                    message=f"lease on {resource_id!r} has expired",
                    recommended_action="re-acquire the lease and rebuild local state",
                )
            expires = now + timedelta(seconds=ttl_seconds)
            cursor.execute(
                "UPDATE autonomy_kernel_lease SET expires_at = %s WHERE resource_id = %s",
                (expires, resource_id),
            )
            return {"resourceId": resource_id, "ownerId": owner_id,
                    "fencingToken": fencing_token, "expiresAt": expires}

    def release(self, resource_id: str, owner_id: str, fencing_token: int) -> None:
        with self.lock, self.connection.transaction(), self.cursor() as cursor:
            cursor.execute(
                "SELECT owner_id, fencing_token FROM autonomy_kernel_lease "
                "WHERE resource_id = %s FOR UPDATE",
                (resource_id,),
            )
            holder = cursor.fetchone()
            if holder is None:
                return
            if holder["owner_id"] != owner_id or holder["fencing_token"] != fencing_token:
                raise KernelError(
                    code="LEASE_LOST",
                    message=(
                        f"cannot release {resource_id!r}: it is held by "
                        f"{holder['owner_id']!r}"
                    ),
                    recommended_action="do not release a lease you no longer hold",
                )
            cursor.execute("DELETE FROM autonomy_kernel_lease WHERE resource_id = %s", (resource_id,))

    def current_token(self, resource_id: str) -> int:
        with self.lock, self.cursor() as cursor:
            cursor.execute(
                "SELECT issued_token FROM autonomy_kernel_lease_watermark WHERE resource_id = %s",
                (resource_id,),
            )
            row = cursor.fetchone()
            return 0 if row is None else row["issued_token"]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
