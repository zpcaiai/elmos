"""Durable append-only event ledger and rebuildable projections."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .errors import ContractViolation, CorruptState, IdempotencyConflict, LeaseLost, TenantIsolationError
from .models import (
    ArtifactRef,
    Event,
    Identity,
    SCHEMA_VERSION,
    Usage,
    canonical_json,
    new_id,
    utc_now,
)
from .persistence import OutboxRecord


@dataclass(frozen=True, slots=True)
class RunRecord:
    identity: Identity
    status: str
    manifest_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class FencedLease:
    identity: Identity
    owner: str
    fencing_token: str
    expires_at: float


class EventLedger:
    """SQLite reference implementation with PostgreSQL-compatible invariants.

    A deployment may replace this class with a PostgreSQL adapter without
    changing the runtime contracts. SQLite uses ``BEGIN IMMEDIATE`` so sequence
    allocation and idempotency checks are one atomic writer operation.
    """

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _init_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS execution_runs (
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                manifest_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS execution_events (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                node_id TEXT,
                agent_id TEXT,
                causation_event_id TEXT,
                correlation_id TEXT,
                idempotency_key TEXT,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL,
                artifact_refs TEXT NOT NULL,
                policy_decision TEXT,
                usage TEXT,
                cost TEXT,
                previous_digest TEXT,
                digest TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id, seq),
                UNIQUE (tenant_id, event_id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS execution_events_idem
                ON execution_events(tenant_id, run_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
            CREATE TABLE IF NOT EXISTS outbox (
                outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                published_at TEXT
            );
            CREATE TABLE IF NOT EXISTS run_leases (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                owner TEXT NOT NULL,
                fencing_token TEXT NOT NULL,
                expires_at REAL NOT NULL,
                PRIMARY KEY (tenant_id, run_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                event_seq INTEGER NOT NULL,
                manifest_hash TEXT NOT NULL,
                state_json TEXT NOT NULL,
                workspace_ref TEXT,
                context_fingerprint TEXT,
                digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projections (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                projection_name TEXT NOT NULL,
                projection_json TEXT NOT NULL,
                event_seq INTEGER NOT NULL,
                head_digest TEXT NOT NULL,
                PRIMARY KEY (tenant_id, run_id, projection_name)
            );
            """
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")

    def create_run(self, identity: Identity, manifest_hash: str, status: str = "queued") -> RunRecord:
        if not manifest_hash:
            raise ContractViolation("manifest hash is required")
        if status not in {"queued", "ready", "running", "waiting", "blocked", "succeeded", "failed", "cancelled"}:
            raise ContractViolation("run status is invalid")
        with self._transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO execution_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (*identity.scope(), status, manifest_hash, utc_now()),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM execution_runs WHERE tenant_id=? AND run_id=? AND node_id=?",
                    (identity.tenant_id, identity.run_id, identity.node_id),
                ).fetchone()
                if row is not None and (row["project_id"], row["task_id"]) != (identity.project_id, identity.task_id):
                    raise TenantIsolationError("run identifier is already bound to another project/task")
                if row is None or row["manifest_hash"] != manifest_hash:
                    raise IdempotencyConflict("run already exists with a different manifest")
                return self._run_record(row)
            return RunRecord(identity, status, manifest_hash, connection.execute("SELECT created_at FROM execution_runs WHERE tenant_id=? AND run_id=? AND node_id=?", (identity.tenant_id, identity.run_id, identity.node_id)).fetchone()[0])

    def append(
        self,
        identity: Identity,
        event_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        artifact_refs: tuple[ArtifactRef, ...] = (),
        policy_decision: dict[str, Any] | None = None,
        usage: Usage | None = None,
        cost: dict[str, Any] | None = None,
        causation_event_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Event:
        if not event_type or not event_type.replace(".", "").replace("_", "").isalnum():
            raise ContractViolation("event_type must be a bounded dotted identifier")
        self._require_run(identity)
        with self._transaction() as connection:
            if idempotency_key is not None:
                existing = connection.execute(
                    "SELECT * FROM execution_events WHERE tenant_id=? AND run_id=? AND idempotency_key=?",
                    (identity.tenant_id, identity.run_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    prior = self._event_from_row(existing)
                    if (
                        prior.event_type != event_type
                        or dict(prior.payload) != dict(payload)
                        or prior.artifact_refs != artifact_refs
                        or prior.policy_decision != policy_decision
                        or prior.usage != usage
                        or prior.cost != cost
                    ):
                        raise IdempotencyConflict("idempotency key was reused for different event content")
                    return prior
            last = connection.execute(
                "SELECT seq, digest FROM execution_events WHERE tenant_id=? AND run_id=? ORDER BY seq DESC LIMIT 1",
                (identity.tenant_id, identity.run_id),
            ).fetchone()
            seq = 0 if last is None else int(last["seq"]) + 1
            event = Event(
                event_id=new_id(),
                tenant_id=identity.tenant_id,
                run_id=identity.run_id,
                seq=seq,
                event_type=event_type,
                payload=payload,
                timestamp=utc_now(),
                node_id=identity.node_id,
                agent_id=identity.agent_id,
                causation_event_id=causation_event_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                artifact_refs=artifact_refs,
                policy_decision=policy_decision,
                usage=usage,
                cost=cost,
                previous_digest=None if last is None else last["digest"],
            )
            digest = event.computed_digest()
            event = Event(**{**event.__dict__, "digest": digest}) if hasattr(event, "__dict__") else Event(
                event_id=event.event_id,
                tenant_id=event.tenant_id,
                run_id=event.run_id,
                seq=event.seq,
                event_type=event.event_type,
                payload=event.payload,
                timestamp=event.timestamp,
                node_id=event.node_id,
                agent_id=event.agent_id,
                causation_event_id=event.causation_event_id,
                correlation_id=event.correlation_id,
                idempotency_key=event.idempotency_key,
                artifact_refs=event.artifact_refs,
                policy_decision=event.policy_decision,
                usage=event.usage,
                cost=event.cost,
                previous_digest=event.previous_digest,
                digest=digest,
            )
            connection.execute(
                """INSERT INTO execution_events
                (tenant_id,run_id,seq,event_id,event_type,node_id,agent_id,causation_event_id,
                 correlation_id,idempotency_key,timestamp,payload,artifact_refs,policy_decision,
                 usage,cost,previous_digest,digest,schema_version)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.tenant_id,
                    event.run_id,
                    event.seq,
                    event.event_id,
                    event.event_type,
                    event.node_id,
                    event.agent_id,
                    event.causation_event_id,
                    event.correlation_id,
                    event.idempotency_key,
                    event.timestamp,
                    canonical_json(dict(event.payload)),
                    canonical_json([ref.as_dict() for ref in event.artifact_refs]),
                    None if event.policy_decision is None else canonical_json(dict(event.policy_decision)),
                    None if event.usage is None else canonical_json(event.usage.as_dict()),
                    None if event.cost is None else canonical_json(dict(event.cost)),
                    event.previous_digest,
                    event.digest,
                    SCHEMA_VERSION,
                ),
            )
            connection.execute(
                "INSERT INTO outbox(tenant_id,run_id,seq,event_json) VALUES (?,?,?,?)",
                (event.tenant_id, event.run_id, event.seq, canonical_json(event.as_dict())),
            )
            self._update_status_from_event(connection, event)
            return event

    def events(self, tenant_id: str, run_id: str, *, after_seq: int = -1, limit: int = 1000) -> list[Event]:
        self._require_tenant_run(tenant_id, run_id)
        if limit < 1 or limit > 100_000:
            raise ContractViolation("event page limit is out of bounds")
        rows = self._connection.execute(
            "SELECT * FROM execution_events WHERE tenant_id=? AND run_id=? AND seq>? ORDER BY seq LIMIT ?",
            (tenant_id, run_id, after_seq, limit),
        ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def event_by_idempotency(self, tenant_id: str, run_id: str, key: str) -> Event | None:
        self._require_tenant_run(tenant_id, run_id)
        row = self._connection.execute(
            "SELECT * FROM execution_events WHERE tenant_id=? AND run_id=? AND idempotency_key=?",
            (tenant_id, run_id, key),
        ).fetchone()
        return None if row is None else self._event_from_row(row)

    def run(self, tenant_id: str, run_id: str, node_id: str = "root") -> RunRecord:
        row = self._connection.execute(
            "SELECT * FROM execution_runs WHERE tenant_id=? AND run_id=? AND node_id=?",
            (tenant_id, run_id, node_id),
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return self._run_record(row)

    def assert_identity(self, identity: Identity) -> RunRecord:
        """Bind a run lookup to the full authenticated project/task scope."""

        record = self.run(identity.tenant_id, identity.run_id, identity.node_id)
        if record.identity.scope() != identity.scope():
            raise TenantIsolationError("run does not belong to the authenticated project/task scope")
        return record

    def acquire_lease(self, identity: Identity, owner: str, ttl_seconds: float, now: float) -> FencedLease:
        if not owner or ttl_seconds <= 0:
            raise ContractViolation("lease owner and positive TTL are required")
        self._require_run(identity)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM run_leases WHERE tenant_id=? AND run_id=? AND node_id=?",
                (identity.tenant_id, identity.run_id, identity.node_id),
            ).fetchone()
            if row is not None and float(row["expires_at"]) > now and row["owner"] != owner:
                raise LeaseLost("run is leased by another worker")
            token = new_id()
            expires = now + ttl_seconds
            connection.execute(
                "INSERT INTO run_leases VALUES(?,?,?,?,?,?) ON CONFLICT(tenant_id,run_id,node_id) DO UPDATE SET owner=excluded.owner, fencing_token=excluded.fencing_token, expires_at=excluded.expires_at",
                (identity.tenant_id, identity.run_id, identity.node_id, owner, token, expires),
            )
            return FencedLease(identity, owner, token, expires)

    def renew_lease(self, lease: FencedLease, ttl_seconds: float, now: float) -> FencedLease:
        with self._transaction() as connection:
            updated = connection.execute(
                "UPDATE run_leases SET expires_at=? WHERE tenant_id=? AND run_id=? AND node_id=? AND owner=? AND fencing_token=? AND expires_at>?",
                (now + ttl_seconds, lease.identity.tenant_id, lease.identity.run_id, lease.identity.node_id, lease.owner, lease.fencing_token, now),
            ).rowcount
            if updated != 1:
                raise LeaseLost("lease renewal lost fencing ownership")
            return FencedLease(lease.identity, lease.owner, lease.fencing_token, now + ttl_seconds)

    def assert_lease(self, lease: FencedLease, now: float) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM run_leases WHERE tenant_id=? AND run_id=? AND node_id=? AND owner=? AND fencing_token=? AND expires_at>?",
            (lease.identity.tenant_id, lease.identity.run_id, lease.identity.node_id, lease.owner, lease.fencing_token, now),
        ).fetchone()
        if row is None:
            raise LeaseLost("fencing token is no longer current")

    def release_lease(self, lease: FencedLease) -> None:
        with self._transaction() as connection:
            connection.execute(
                "DELETE FROM run_leases WHERE tenant_id=? AND run_id=? AND node_id=? AND owner=? AND fencing_token=?",
                (lease.identity.tenant_id, lease.identity.run_id, lease.identity.node_id, lease.owner, lease.fencing_token),
            )

    def save_checkpoint(
        self,
        identity: Identity,
        *,
        event_seq: int,
        manifest_hash: str,
        state: dict[str, Any],
        workspace_ref: str | None = None,
        context_fingerprint: str | None = None,
    ) -> str:
        from .models import digest_of

        self._require_run(identity)
        if event_seq < -1 or not manifest_hash:
            raise ContractViolation("checkpoint sequence and manifest hash are required")
        body = {
            "tenant_id": identity.tenant_id,
            "run_id": identity.run_id,
            "node_id": identity.node_id,
            "event_seq": event_seq,
            "manifest_hash": manifest_hash,
            "state": state,
            "workspace_ref": workspace_ref,
            "context_fingerprint": context_fingerprint,
        }
        digest = digest_of(body)
        checkpoint_id = "checkpoint_" + digest.removeprefix("sha256:")
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO checkpoints VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (checkpoint_id, identity.tenant_id, identity.run_id, identity.node_id, event_seq, manifest_hash, canonical_json(state), workspace_ref, context_fingerprint, digest, utc_now()),
            )
        return checkpoint_id

    def latest_checkpoint(self, tenant_id: str, run_id: str, node_id: str = "root") -> dict[str, Any] | None:
        rows = self.checkpoints(tenant_id, run_id, node_id=node_id, limit=1)
        return None if not rows else rows[0]

    def checkpoints(self, tenant_id: str, run_id: str, *, node_id: str = "root", limit: int = 100, verify: bool = True) -> tuple[dict[str, Any], ...]:
        self._require_tenant_run(tenant_id, run_id, node_id)
        if limit < 1 or limit > 10_000:
            raise ContractViolation("checkpoint page limit is out of bounds")
        rows = self._connection.execute(
            "SELECT * FROM checkpoints WHERE tenant_id=? AND run_id=? AND node_id=? ORDER BY event_seq DESC,created_at DESC LIMIT ?",
            (tenant_id, run_id, node_id, limit),
        ).fetchall()
        return tuple(self._checkpoint_from_row(row, verify=verify) for row in rows)

    def rebuild_projection(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        current: dict[str, Any] = {"status": "queued", "last_event_seq": -1, "actions": {}, "usage": {"input_tokens": 0, "output_tokens": 0, "cost_micros": 0}}
        events = self.events(tenant_id, run_id, limit=100_000)
        for event in events:
            current["last_event_seq"] = event.seq
            current["last_event_digest"] = event.digest
            if event.event_type == "run.status":
                current["status"] = str(event.payload.get("status", current["status"]))
            if event.event_type == "tool.observed":
                action_id = str(event.payload.get("action_id", ""))
                current["actions"][action_id] = event.payload
            if event.usage is not None:
                current["usage"]["input_tokens"] += event.usage.input_tokens
                current["usage"]["output_tokens"] += event.usage.output_tokens
                current["usage"]["cost_micros"] += event.usage.cost_micros
        head = current.get("last_event_digest", "genesis")
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO projections VALUES(?,?,?,?,?,?) ON CONFLICT(tenant_id,run_id,projection_name) DO UPDATE SET projection_json=excluded.projection_json,event_seq=excluded.event_seq,head_digest=excluded.head_digest",
                (tenant_id, run_id, "runtime", canonical_json(current), current["last_event_seq"], head),
            )
        return current

    def verify_chain(self, tenant_id: str, run_id: str) -> bool:
        previous: str | None = None
        expected_seq = 0
        for event in self.events(tenant_id, run_id, limit=100_000):
            if event.seq != expected_seq or event.previous_digest != previous or event.digest != event.computed_digest():
                raise CorruptState(f"event chain verification failed at sequence {event.seq}")
            previous = event.digest
            expected_seq += 1
        return True

    def append_correction(
        self,
        identity: Identity,
        *,
        corrected_event_id: str,
        reason: str,
        replacement: dict[str, Any],
        idempotency_key: str,
    ) -> Event:
        """Append a correction fact without mutating immutable history."""

        if not corrected_event_id or not reason:
            raise ContractViolation("correction requires an event and reason")
        original = self._connection.execute(
            "SELECT 1 FROM execution_events WHERE tenant_id=? AND run_id=? AND event_id=?",
            (identity.tenant_id, identity.run_id, corrected_event_id),
        ).fetchone()
        if original is None:
            raise TenantIsolationError("corrected event is not in the authenticated run scope")
        return self.append(
            identity,
            "event.corrected",
            {
                "corrected_event_id": corrected_event_id,
                "reason": reason[:1000],
                "replacement": replacement,
            },
            idempotency_key=idempotency_key,
            causation_event_id=corrected_event_id,
        )

    def projection_matches_rebuild(self, tenant_id: str, run_id: str) -> bool:
        rebuilt = self.rebuild_projection(tenant_id, run_id)
        row = self._connection.execute(
            "SELECT projection_json,event_seq,head_digest FROM projections WHERE tenant_id=? AND run_id=? AND projection_name='runtime'",
            (tenant_id, run_id),
        ).fetchone()
        if row is None:
            return False
        stored = json.loads(row["projection_json"])
        return (
            stored == rebuilt
            and int(row["event_seq"]) == int(rebuilt["last_event_seq"])
            and row["head_digest"] == rebuilt.get("last_event_digest", "genesis")
        )

    def pending_outbox(self, limit: int = 1000) -> tuple[OutboxRecord, ...]:
        if limit < 1 or limit > 10_000:
            raise ContractViolation("outbox page limit is out of bounds")
        rows = self._connection.execute(
            "SELECT * FROM outbox WHERE published_at IS NULL ORDER BY outbox_id LIMIT ?", (limit,)
        ).fetchall()
        return tuple(
            OutboxRecord(
                int(row["outbox_id"]),
                str(row["tenant_id"]),
                str(row["run_id"]),
                int(row["seq"]),
                json.loads(row["event_json"]),
            )
            for row in rows
        )

    def mark_outbox_published(self, outbox_ids: int | Iterator[int] | list[int] | tuple[int, ...], published_at: str | None = None) -> None:
        identifiers = (outbox_ids,) if isinstance(outbox_ids, int) else tuple(outbox_ids)
        if not identifiers or any(not isinstance(identifier, int) or identifier <= 0 for identifier in identifiers):
            raise ContractViolation("outbox identifiers must be positive integers")
        with self._transaction() as connection:
            timestamp = published_at or utc_now()
            connection.executemany(
                "UPDATE outbox SET published_at=? WHERE outbox_id=? AND published_at IS NULL",
                ((timestamp, identifier) for identifier in identifiers),
            )

    def _require_run(self, identity: Identity) -> None:
        self.assert_identity(identity)

    def _require_tenant_run(self, tenant_id: str, run_id: str, node_id: str = "root") -> None:
        row = self._connection.execute(
            "SELECT 1 FROM execution_runs WHERE tenant_id=? AND run_id=? AND node_id=?",
            (tenant_id, run_id, node_id),
        ).fetchone()
        if row is None:
            raise TenantIsolationError("run is not registered in the tenant scope")

    @staticmethod
    def _run_record(row: sqlite3.Row) -> RunRecord:
        identity = Identity(row["tenant_id"], row["project_id"], row["task_id"], row["run_id"], row["node_id"])
        return RunRecord(identity, row["status"], row["manifest_hash"], row["created_at"])

    @staticmethod
    def _checkpoint_from_row(row: sqlite3.Row, *, verify: bool = True) -> dict[str, Any]:
        value = dict(row)
        try:
            state = json.loads(value["state_json"])
        except (TypeError, json.JSONDecodeError):
            if verify:
                raise CorruptState("checkpoint state is not valid JSON")
            state = None
        body = {
            "tenant_id": value["tenant_id"],
            "run_id": value["run_id"],
            "node_id": value["node_id"],
            "event_seq": value["event_seq"],
            "manifest_hash": value["manifest_hash"],
            "state": state,
            "workspace_ref": value["workspace_ref"],
            "context_fingerprint": value["context_fingerprint"],
        }
        from .models import digest_of

        if verify and digest_of(body) != value["digest"]:
            raise CorruptState("checkpoint digest verification failed")
        value["state"] = state
        return value

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> Event:
        artifact_refs = tuple(ArtifactRef(**item) for item in json.loads(row["artifact_refs"]))
        usage_data = None if row["usage"] is None else Usage(**json.loads(row["usage"]))
        event = Event(
            event_id=row["event_id"], tenant_id=row["tenant_id"], run_id=row["run_id"], seq=row["seq"],
            event_type=row["event_type"], payload=json.loads(row["payload"]), timestamp=row["timestamp"],
            node_id=row["node_id"], agent_id=row["agent_id"], causation_event_id=row["causation_event_id"],
            correlation_id=row["correlation_id"], idempotency_key=row["idempotency_key"],
            artifact_refs=artifact_refs, policy_decision=None if row["policy_decision"] is None else json.loads(row["policy_decision"]),
            usage=usage_data, cost=None if row["cost"] is None else json.loads(row["cost"]),
            previous_digest=row["previous_digest"], digest=row["digest"], schema_version=row["schema_version"],
        )
        if event.schema_version != SCHEMA_VERSION:
            raise CorruptState("event schema version is unsupported")
        return event

    @staticmethod
    def _update_status_from_event(connection: sqlite3.Connection, event: Event) -> None:
        if event.event_type != "run.status":
            return
        status = event.payload.get("status")
        if status not in {"queued", "ready", "running", "waiting", "blocked", "succeeded", "failed", "cancelled"}:
            raise ContractViolation("run.status event has an invalid status")
        connection.execute(
            "UPDATE execution_runs SET status=? WHERE tenant_id=? AND run_id=? AND node_id=?",
            (status, event.tenant_id, event.run_id, event.node_id or "root"),
        )
