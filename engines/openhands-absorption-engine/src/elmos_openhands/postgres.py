"""PostgreSQL implementation of the immutable execution ledger.

This module uses psycopg only when ``connect`` is called.  It implements the
same runtime-facing operations as :class:`EventLedger`, including per-run
sequence serialization, fenced leases, checkpointing, projection rebuilds and
the transactional outbox.  Every transaction sets the authenticated tenant in
``elmos.tenant_id`` so PostgreSQL RLS remains an enforcement boundary.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping, Protocol

from .errors import ContractViolation, CorruptState, IdempotencyConflict, LeaseLost, NotConfigured, TenantIsolationError
from .ledger import FencedLease, RunRecord
from .models import ArtifactRef, Event, Identity, SCHEMA_VERSION, Usage, canonical_json, digest_of, new_id, utc_now
from .persistence import OutboxRecord


class ArtifactStorePort(Protocol):
    def put(self, tenant_id: str, data: bytes, *, kind: str = "artifact", media_type: str = "application/octet-stream") -> ArtifactRef: ...

    def get(self, tenant_id: str, ref: ArtifactRef | str) -> bytes: ...


class PostgresEventLedger:
    """Psycopg-backed durable ledger with fail-closed tenant binding."""

    def __init__(
        self,
        connection: Any,
        *,
        artifacts: ArtifactStorePort | None = None,
        max_inline_payload_bytes: int = 262_144,
    ) -> None:
        if max_inline_payload_bytes < 1024:
            raise ContractViolation("inline event payload limit is too small")
        self._connection = connection
        self.artifacts = artifacts
        self.max_inline_payload_bytes = max_inline_payload_bytes
        self._lock = threading.RLock()

    @classmethod
    def connect(
        cls,
        dsn: str,
        *,
        artifacts: ArtifactStorePort | None = None,
        max_inline_payload_bytes: int = 262_144,
        connect_timeout_seconds: int = 10,
    ) -> "PostgresEventLedger":
        if not dsn or connect_timeout_seconds < 1:
            raise ContractViolation("PostgreSQL DSN and positive timeout are required")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise NotConfigured("psycopg 3 is required for PostgreSQL execution") from error
        connection = psycopg.connect(
            dsn,
            autocommit=False,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
            application_name="elmos-openhands",
        )
        return cls(connection, artifacts=artifacts, max_inline_payload_bytes=max_inline_payload_bytes)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self, tenant_id: str) -> Iterator[Any]:
        if not tenant_id:
            raise TenantIsolationError("tenant context is required for PostgreSQL operation")
        with self._lock:
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('elmos.tenant_id', %s, true)", (tenant_id,))
                    yield cursor

    def create_run(self, identity: Identity, manifest_hash: str, status: str = "queued") -> RunRecord:
        _validate_run_status(status)
        if not manifest_hash:
            raise ContractViolation("manifest hash is required")
        with self._transaction(identity.tenant_id) as cursor:
            cursor.execute(
                """INSERT INTO oh_execution_runs
                   (tenant_id,run_id,project_id,task_id,node_id,status,manifest_hash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (tenant_id,run_id,node_id) DO NOTHING""",
                (identity.tenant_id, identity.run_id, identity.project_id, identity.task_id, identity.node_id, status, manifest_hash),
            )
            cursor.execute(
                "SELECT * FROM oh_execution_runs WHERE tenant_id=%s AND run_id=%s AND node_id=%s",
                (identity.tenant_id, identity.run_id, identity.node_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise CorruptState("PostgreSQL run insert was not readable under tenant RLS")
            if (str(row["project_id"]), str(row["task_id"])) != (identity.project_id, identity.task_id):
                raise TenantIsolationError("run identifier is already bound to another project/task")
            if str(row["manifest_hash"]) != manifest_hash:
                raise IdempotencyConflict("run already exists with a different manifest")
            return _run_record(row)

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
        with self._transaction(identity.tenant_id) as cursor:
            # Nodes in the same run have distinct run rows, so row locking one
            # node is insufficient to serialize the run-wide event sequence.
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (identity.tenant_id + ":" + identity.run_id,),
            )
            cursor.execute(
                "SELECT manifest_hash FROM oh_execution_runs WHERE tenant_id=%s AND project_id=%s AND task_id=%s AND run_id=%s AND node_id=%s FOR UPDATE",
                (identity.tenant_id, identity.project_id, identity.task_id, identity.run_id, identity.node_id),
            )
            if cursor.fetchone() is None:
                raise TenantIsolationError("run is not registered in the authenticated tenant scope")
            if idempotency_key is not None:
                cursor.execute(
                    "SELECT * FROM oh_execution_events WHERE tenant_id=%s AND run_id=%s AND idempotency_key=%s",
                    (identity.tenant_id, identity.run_id, idempotency_key),
                )
                row = cursor.fetchone()
                if row is not None:
                    prior = self._event_from_row(row)
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
            cursor.execute(
                "SELECT seq,digest FROM oh_execution_events WHERE tenant_id=%s AND run_id=%s ORDER BY seq DESC LIMIT 1",
                (identity.tenant_id, identity.run_id),
            )
            last = cursor.fetchone()
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
                previous_digest=None if last is None else str(last["digest"]),
            )
            digest = event.computed_digest()
            event = _with_digest(event, digest)
            stored_payload, _ = self._externalize_payload(identity.tenant_id, payload)
            # The external payload reference lives inside ``stored_payload``.
            # Do not add it to the logical event's artifact_refs: the event
            # digest was calculated from the caller supplied references, and
            # changing that set at persistence time would make replay fail.
            stored_refs = artifact_refs
            cursor.execute(
                """INSERT INTO oh_execution_events
                   (tenant_id,run_id,seq,event_id,event_type,node_id,agent_id,causation_event_id,
                    correlation_id,idempotency_key,payload,artifact_refs,policy_decision,usage,cost,
                    previous_digest,digest,schema_version,event_timestamp)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,
                           %s::jsonb,%s::jsonb,%s,%s,%s,%s::timestamptz)""",
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
                    canonical_json(stored_payload),
                    canonical_json([ref.as_dict() for ref in stored_refs]),
                    None if policy_decision is None else canonical_json(policy_decision),
                    None if usage is None else canonical_json(usage.as_dict()),
                    None if cost is None else canonical_json(cost),
                    event.previous_digest,
                    digest,
                    SCHEMA_VERSION,
                    event.timestamp,
                ),
            )
            outbox_event = event.as_dict()
            outbox_event["payload"] = stored_payload
            outbox_event["artifact_refs"] = [ref.as_dict() for ref in stored_refs]
            cursor.execute(
                "INSERT INTO oh_execution_outbox(tenant_id,run_id,seq,event_json) VALUES (%s,%s,%s,%s::jsonb)",
                (identity.tenant_id, identity.run_id, seq, canonical_json(outbox_event)),
            )
            if event_type == "run.status":
                status = str(payload.get("status", ""))
                _validate_run_status(status)
                cursor.execute(
                    "UPDATE oh_execution_runs SET status=%s WHERE tenant_id=%s AND run_id=%s AND node_id=%s",
                    (status, identity.tenant_id, identity.run_id, identity.node_id),
                )
            return event

    def events(self, tenant_id: str, run_id: str, *, after_seq: int = -1, limit: int = 1000) -> list[Event]:
        if limit < 1 or limit > 100_000:
            raise ContractViolation("event page limit is out of bounds")
        with self._transaction(tenant_id) as cursor:
            self._require_run_cursor(cursor, tenant_id, run_id)
            cursor.execute(
                "SELECT * FROM oh_execution_events WHERE tenant_id=%s AND run_id=%s AND seq>%s ORDER BY seq LIMIT %s",
                (tenant_id, run_id, after_seq, limit),
            )
            return [self._event_from_row(row) for row in cursor.fetchall()]

    def event_by_idempotency(self, tenant_id: str, run_id: str, key: str) -> Event | None:
        with self._transaction(tenant_id) as cursor:
            self._require_run_cursor(cursor, tenant_id, run_id)
            cursor.execute(
                "SELECT * FROM oh_execution_events WHERE tenant_id=%s AND run_id=%s AND idempotency_key=%s",
                (tenant_id, run_id, key),
            )
            row = cursor.fetchone()
            return None if row is None else self._event_from_row(row)

    def run(self, tenant_id: str, run_id: str, node_id: str = "root") -> RunRecord:
        with self._transaction(tenant_id) as cursor:
            cursor.execute(
                "SELECT * FROM oh_execution_runs WHERE tenant_id=%s AND run_id=%s AND node_id=%s",
                (tenant_id, run_id, node_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise KeyError(run_id)
            return _run_record(row)

    def assert_identity(self, identity: Identity) -> RunRecord:
        with self._transaction(identity.tenant_id) as cursor:
            cursor.execute(
                "SELECT * FROM oh_execution_runs WHERE tenant_id=%s AND project_id=%s AND task_id=%s AND run_id=%s AND node_id=%s",
                (identity.tenant_id, identity.project_id, identity.task_id, identity.run_id, identity.node_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise TenantIsolationError("run does not belong to the authenticated project/task scope")
            return _run_record(row)

    def acquire_lease(self, identity: Identity, owner: str, ttl_seconds: float, now: float) -> FencedLease:
        if not owner or ttl_seconds <= 0:
            raise ContractViolation("lease owner and positive TTL are required")
        with self._transaction(identity.tenant_id) as cursor:
            self._require_identity_cursor(cursor, identity)
            cursor.execute(
                "SELECT * FROM oh_run_leases WHERE tenant_id=%s AND run_id=%s AND node_id=%s FOR UPDATE",
                (identity.tenant_id, identity.run_id, identity.node_id),
            )
            row = cursor.fetchone()
            if row is not None and float(row["expires_epoch"]) > now and str(row["owner"]) != owner:
                raise LeaseLost("run is leased by another worker")
            token = new_id()
            expires = now + ttl_seconds
            cursor.execute(
                """INSERT INTO oh_run_leases(tenant_id,run_id,node_id,owner,fencing_token,expires_epoch)
                   VALUES(%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(tenant_id,run_id,node_id) DO UPDATE
                   SET owner=excluded.owner,fencing_token=excluded.fencing_token,expires_epoch=excluded.expires_epoch""",
                (identity.tenant_id, identity.run_id, identity.node_id, owner, token, expires),
            )
            return FencedLease(identity, owner, token, expires)

    def renew_lease(self, lease: FencedLease, ttl_seconds: float, now: float) -> FencedLease:
        with self._transaction(lease.identity.tenant_id) as cursor:
            cursor.execute(
                """UPDATE oh_run_leases SET expires_epoch=%s
                   WHERE tenant_id=%s AND run_id=%s AND node_id=%s AND owner=%s
                     AND fencing_token=%s AND expires_epoch>%s""",
                (now + ttl_seconds, lease.identity.tenant_id, lease.identity.run_id, lease.identity.node_id, lease.owner, lease.fencing_token, now),
            )
            if cursor.rowcount != 1:
                raise LeaseLost("lease renewal lost fencing ownership")
            return FencedLease(lease.identity, lease.owner, lease.fencing_token, now + ttl_seconds)

    def assert_lease(self, lease: FencedLease, now: float) -> None:
        with self._transaction(lease.identity.tenant_id) as cursor:
            cursor.execute(
                """SELECT 1 FROM oh_run_leases WHERE tenant_id=%s AND run_id=%s AND node_id=%s
                   AND owner=%s AND fencing_token=%s AND expires_epoch>%s""",
                (lease.identity.tenant_id, lease.identity.run_id, lease.identity.node_id, lease.owner, lease.fencing_token, now),
            )
            if cursor.fetchone() is None:
                raise LeaseLost("fencing token is no longer current")

    def release_lease(self, lease: FencedLease) -> None:
        with self._transaction(lease.identity.tenant_id) as cursor:
            cursor.execute(
                """DELETE FROM oh_run_leases WHERE tenant_id=%s AND run_id=%s AND node_id=%s
                   AND owner=%s AND fencing_token=%s""",
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
        with self._transaction(identity.tenant_id) as cursor:
            self._require_identity_cursor(cursor, identity)
            cursor.execute(
                """INSERT INTO oh_checkpoints
                   (checkpoint_id,tenant_id,run_id,node_id,event_seq,manifest_hash,state_json,
                    workspace_ref,context_fingerprint,digest)
                   VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                   ON CONFLICT(checkpoint_id) DO NOTHING""",
                (checkpoint_id, identity.tenant_id, identity.run_id, identity.node_id, event_seq, manifest_hash, canonical_json(state), workspace_ref, context_fingerprint, digest),
            )
        return checkpoint_id

    def latest_checkpoint(self, tenant_id: str, run_id: str, node_id: str = "root") -> dict[str, Any] | None:
        rows = self.checkpoints(tenant_id, run_id, node_id=node_id, limit=1)
        return None if not rows else rows[0]

    def checkpoints(self, tenant_id: str, run_id: str, *, node_id: str = "root", limit: int = 100, verify: bool = True) -> tuple[dict[str, Any], ...]:
        if limit < 1 or limit > 10_000:
            raise ContractViolation("checkpoint page limit is out of bounds")
        with self._transaction(tenant_id) as cursor:
            self._require_run_cursor(cursor, tenant_id, run_id, node_id)
            cursor.execute(
                "SELECT * FROM oh_checkpoints WHERE tenant_id=%s AND run_id=%s AND node_id=%s ORDER BY event_seq DESC,created_at DESC LIMIT %s",
                (tenant_id, run_id, node_id, limit),
            )
            return tuple(self._checkpoint_from_row(row, verify=verify) for row in cursor.fetchall())

    def rebuild_projection(self, tenant_id: str, run_id: str) -> dict[str, Any]:
        current: dict[str, Any] = {
            "status": "queued",
            "last_event_seq": -1,
            "actions": {},
            "usage": {"input_tokens": 0, "output_tokens": 0, "cost_micros": 0},
        }
        for event in self.events(tenant_id, run_id, limit=100_000):
            current["last_event_seq"] = event.seq
            current["last_event_digest"] = event.digest
            if event.event_type == "run.status":
                current["status"] = str(event.payload.get("status", current["status"]))
            if event.event_type == "tool.observed":
                current["actions"][str(event.payload.get("action_id", ""))] = event.payload
            if event.usage is not None:
                current["usage"]["input_tokens"] += event.usage.input_tokens
                current["usage"]["output_tokens"] += event.usage.output_tokens
                current["usage"]["cost_micros"] += event.usage.cost_micros
        with self._transaction(tenant_id) as cursor:
            cursor.execute(
                """INSERT INTO oh_projections(tenant_id,run_id,projection_name,projection_json,event_seq,head_digest)
                   VALUES(%s,%s,'runtime',%s::jsonb,%s,%s)
                   ON CONFLICT(tenant_id,run_id,projection_name) DO UPDATE
                   SET projection_json=excluded.projection_json,event_seq=excluded.event_seq,head_digest=excluded.head_digest""",
                (tenant_id, run_id, canonical_json(current), current["last_event_seq"], current.get("last_event_digest", "genesis")),
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
        if not reason.strip() or not idempotency_key:
            raise ContractViolation("correction reason and idempotency key are required")
        with self._transaction(identity.tenant_id) as cursor:
            cursor.execute(
                "SELECT 1 FROM oh_execution_events WHERE tenant_id=%s AND run_id=%s AND event_id=%s",
                (identity.tenant_id, identity.run_id, corrected_event_id),
            )
            if cursor.fetchone() is None:
                raise TenantIsolationError("corrected event is not in the authenticated run scope")
        return self.append(
            identity,
            "event.corrected",
            {"corrected_event_id": corrected_event_id, "reason": reason.strip()[:1000], "replacement": replacement},
            idempotency_key=idempotency_key,
            causation_event_id=corrected_event_id,
        )

    def pending_outbox(self, *, limit: int = 100) -> tuple[OutboxRecord, ...]:
        if limit < 1 or limit > 10_000:
            raise ContractViolation("outbox page limit is out of bounds")
        # Outbox workers are infrastructure principals.  The migration grants
        # them an explicit bypass policy; application requests never call this.
        with self._lock:
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT * FROM oh_execution_outbox WHERE published_at IS NULL ORDER BY outbox_id LIMIT %s",
                        (limit,),
                    )
                    return tuple(
                        OutboxRecord(int(row["outbox_id"]), str(row["tenant_id"]), str(row["run_id"]), int(row["seq"]), _json_value(row["event_json"]))
                        for row in cursor.fetchall()
                    )

    def mark_outbox_published(self, outbox_ids: Iterable[int]) -> None:
        identifiers = tuple(outbox_ids)
        if not identifiers or any(identifier <= 0 for identifier in identifiers):
            raise ContractViolation("outbox identifiers must be positive")
        with self._lock:
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.executemany(
                        "UPDATE oh_execution_outbox SET published_at=now() WHERE outbox_id=%s AND published_at IS NULL",
                        ((identifier,) for identifier in identifiers),
                    )

    def _externalize_payload(self, tenant_id: str, payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ArtifactRef | None]:
        encoded = canonical_json(dict(payload)).encode("utf-8")
        if len(encoded) <= self.max_inline_payload_bytes:
            return dict(payload), None
        if self.artifacts is None:
            raise NotConfigured("large event payload requires a configured object store")
        reference = self.artifacts.put(tenant_id, encoded, kind="event-payload", media_type="application/json")
        return {
            "_external_payload": reference.as_dict(),
            "_payload_digest": digest_of(dict(payload)),
        }, reference

    def _hydrate_payload(self, tenant_id: str, value: Any) -> Mapping[str, Any]:
        payload = _json_value(value)
        if not isinstance(payload, Mapping):
            raise CorruptState("event payload is not a JSON object")
        external = payload.get("_external_payload")
        if external is None:
            return dict(payload)
        if self.artifacts is None or not isinstance(external, Mapping):
            raise CorruptState("external event payload cannot be resolved")
        reference = ArtifactRef(**dict(external))
        decoded = json.loads(self.artifacts.get(tenant_id, reference))
        if not isinstance(decoded, Mapping) or digest_of(dict(decoded)) != payload.get("_payload_digest"):
            raise CorruptState("external event payload digest mismatch")
        return dict(decoded)

    def _event_from_row(self, row: Mapping[str, Any]) -> Event:
        refs = tuple(ArtifactRef(**item) for item in _json_value(row.get("artifact_refs")) or [])
        usage_raw = _json_value(row.get("usage"))
        timestamp = row.get("event_timestamp") or row.get("created_at")
        event = Event(
            event_id=str(row["event_id"]),
            tenant_id=str(row["tenant_id"]),
            run_id=str(row["run_id"]),
            seq=int(row["seq"]),
            event_type=str(row["event_type"]),
            payload=self._hydrate_payload(str(row["tenant_id"]), row.get("payload")),
            timestamp=_timestamp(timestamp),
            node_id=None if row.get("node_id") is None else str(row["node_id"]),
            agent_id=None if row.get("agent_id") is None else str(row["agent_id"]),
            causation_event_id=None if row.get("causation_event_id") is None else str(row["causation_event_id"]),
            correlation_id=None if row.get("correlation_id") is None else str(row["correlation_id"]),
            idempotency_key=None if row.get("idempotency_key") is None else str(row["idempotency_key"]),
            artifact_refs=refs,
            policy_decision=None if row.get("policy_decision") is None else dict(_json_value(row["policy_decision"])),
            usage=None if usage_raw is None else Usage(**dict(usage_raw)),
            cost=None if row.get("cost") is None else dict(_json_value(row["cost"])),
            previous_digest=None if row.get("previous_digest") is None else str(row["previous_digest"]),
            digest=str(row["digest"]),
            schema_version=str(row.get("schema_version") or SCHEMA_VERSION),
        )
        if event.schema_version != SCHEMA_VERSION:
            raise CorruptState("event schema version is unsupported")
        return event

    @staticmethod
    def _checkpoint_from_row(row: Mapping[str, Any], *, verify: bool = True) -> dict[str, Any]:
        value = dict(row)
        try:
            state = _json_value(value["state_json"])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            if verify:
                raise CorruptState("checkpoint state JSON is corrupt") from error
            # ResumeCoordinator asks for unverified rows so it can reject a
            # corrupt newest checkpoint and continue to an older valid one.
            state = {"_corrupt_state_json": True}
        body = {
            "tenant_id": str(value["tenant_id"]),
            "run_id": str(value["run_id"]),
            "node_id": str(value["node_id"]),
            "event_seq": int(value["event_seq"]),
            "manifest_hash": str(value["manifest_hash"]),
            "state": state,
            "workspace_ref": value.get("workspace_ref"),
            "context_fingerprint": value.get("context_fingerprint"),
        }
        if verify and digest_of(body) != str(value["digest"]):
            raise CorruptState("checkpoint digest verification failed")
        value["state"] = state
        return value

    @staticmethod
    def _require_run_cursor(cursor: Any, tenant_id: str, run_id: str, node_id: str = "root") -> None:
        cursor.execute(
            "SELECT 1 FROM oh_execution_runs WHERE tenant_id=%s AND run_id=%s AND node_id=%s",
            (tenant_id, run_id, node_id),
        )
        if cursor.fetchone() is None:
            raise TenantIsolationError("run is not registered in the authenticated tenant scope")

    @staticmethod
    def _require_identity_cursor(cursor: Any, identity: Identity) -> None:
        cursor.execute(
            "SELECT 1 FROM oh_execution_runs WHERE tenant_id=%s AND project_id=%s AND task_id=%s AND run_id=%s AND node_id=%s",
            (identity.tenant_id, identity.project_id, identity.task_id, identity.run_id, identity.node_id),
        )
        if cursor.fetchone() is None:
            raise TenantIsolationError("run does not belong to the authenticated project/task scope")


def _with_digest(event: Event, digest: str) -> Event:
    return Event(
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
        schema_version=event.schema_version,
    )


def _run_record(row: Mapping[str, Any]) -> RunRecord:
    identity = Identity(
        str(row["tenant_id"]),
        str(row["project_id"]),
        str(row["task_id"]),
        str(row["run_id"]),
        str(row["node_id"]),
    )
    return RunRecord(identity, str(row["status"]), str(row["manifest_hash"]), _timestamp(row["created_at"]))


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        result: str = value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return result
    return str(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _validate_run_status(status: str) -> None:
    if status not in {"queued", "ready", "running", "waiting", "blocked", "succeeded", "failed", "cancelled"}:
        raise ContractViolation("run status is invalid")
