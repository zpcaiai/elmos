"""Private, exactly-attested SQLite state with tenant/project isolation."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time
import uuid
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_json,
    digest_bytes,
    require_identifier,
    strict_json_loads,
)
from .domain import CertificationStatus, EvidenceState, TenantScope


class StoreError(RuntimeError):
    pass


class StoreSecurityError(StoreError):
    pass


class StoreIntegrityError(StoreError):
    pass


class StoreClosed(StoreError):
    pass


class RecordNotFound(StoreError):
    pass


class RecordConflict(StoreError):
    pass


class IdempotencyConflict(RecordConflict):
    pass


class StateTransitionError(RecordConflict):
    pass


class StoreRollbackError(StoreError):
    pass


class RunState(str):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_STATES = {
    RunState.PENDING,
    RunState.RUNNING,
    RunState.VERIFYING,
    RunState.SUCCEEDED,
    RunState.BLOCKED,
    RunState.FAILED,
    RunState.CANCELLED,
}
_TRANSITIONS = {
    RunState.PENDING: {RunState.RUNNING, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED},
    RunState.RUNNING: {
        RunState.VERIFYING,
        RunState.SUCCEEDED,
        RunState.BLOCKED,
        RunState.FAILED,
        RunState.CANCELLED,
    },
    RunState.VERIFYING: {RunState.SUCCEEDED, RunState.BLOCKED, RunState.FAILED, RunState.CANCELLED},
}


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    tenant_id: str
    project_id: str
    operation: str
    idempotency_key: str
    request_digest: str
    request: Mapping[str, Any]
    state: str
    response: Mapping[str, Any] | None
    created_at: str
    updated_at: str
    context_digest: str


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    record: RunRecord
    replayed: bool


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    aggregate_id: str
    event_type: str
    sequence: int
    payload: Mapping[str, Any]
    payload_digest: str
    previous_digest: str
    event_digest: str
    created_at: str
    context_digest: str


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    target_id: str
    gate_level: str
    verdict: str
    payload: Mapping[str, Any]
    evidence_digest: str
    evidence_state: str
    certification_status: str
    created_at: str
    context_digest: str


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    checkpoint_id: str
    stream_id: str
    sequence: int
    payload: Mapping[str, Any]
    checkpoint_digest: str
    created_at: str
    context_digest: str


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    outbox_id: str
    topic: str
    idempotency_key: str
    payload: Mapping[str, Any]
    payload_digest: str
    created_at: str
    context_digest: str
    delivery_state: str = "PENDING"


@dataclass(frozen=True, slots=True)
class OutboxAttemptRecord:
    outbox_id: str
    attempt_id: str
    attempt_number: int
    outcome: str
    provider_receipt: Mapping[str, Any]
    attempt_digest: str
    created_at: str
    context_digest: str


OutboxReceiptVerifier = Callable[
    [TenantScope, OutboxRecord, str, str, Mapping[str, Any]], bool
]


_VERSION = "elmos.foundry.store.v1"
_SCHEMA = """
CREATE TABLE foundry_schema_metadata(singleton INTEGER PRIMARY KEY CHECK(singleton=1),schema_version TEXT NOT NULL,schema_digest TEXT NOT NULL) STRICT;
CREATE TABLE foundry_runs(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,run_id TEXT NOT NULL,operation TEXT NOT NULL,idempotency_key TEXT NOT NULL,request_json TEXT NOT NULL,request_digest TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN('PENDING','RUNNING','VERIFYING','SUCCEEDED','BLOCKED','FAILED','CANCELLED')),response_json TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,run_id),UNIQUE(tenant_id,project_id,operation,idempotency_key)) STRICT;
CREATE TABLE foundry_run_transitions(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,run_id TEXT NOT NULL,sequence INTEGER NOT NULL CHECK(sequence>=0),from_state TEXT,to_state TEXT NOT NULL,reason TEXT NOT NULL,response_digest TEXT,created_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,run_id,sequence),FOREIGN KEY(tenant_id,project_id,run_id) REFERENCES foundry_runs(tenant_id,project_id,run_id)) STRICT;
CREATE TABLE foundry_events(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,aggregate_id TEXT NOT NULL,sequence INTEGER NOT NULL CHECK(sequence>=1),event_id TEXT NOT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,payload_digest TEXT NOT NULL,previous_digest TEXT NOT NULL,event_digest TEXT NOT NULL,created_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,aggregate_id,sequence),UNIQUE(tenant_id,project_id,event_id)) STRICT;
CREATE TABLE foundry_evidence(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,evidence_id TEXT NOT NULL,target_id TEXT NOT NULL,gate_level TEXT NOT NULL,verdict TEXT NOT NULL,payload_json TEXT NOT NULL,evidence_digest TEXT NOT NULL,evidence_state TEXT NOT NULL,certification_status TEXT NOT NULL,created_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,evidence_id)) STRICT;
CREATE TABLE foundry_checkpoints(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,stream_id TEXT NOT NULL,sequence INTEGER NOT NULL CHECK(sequence>=1),checkpoint_id TEXT NOT NULL,payload_json TEXT NOT NULL,checkpoint_digest TEXT NOT NULL,created_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,stream_id,sequence),UNIQUE(tenant_id,project_id,checkpoint_id)) STRICT;
CREATE TABLE foundry_outbox(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,outbox_id TEXT NOT NULL,topic TEXT NOT NULL,idempotency_key TEXT NOT NULL,payload_json TEXT NOT NULL,payload_digest TEXT NOT NULL,created_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,outbox_id),UNIQUE(tenant_id,project_id,topic,idempotency_key)) STRICT;
CREATE TABLE foundry_outbox_attempts(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,outbox_id TEXT NOT NULL,attempt_number INTEGER NOT NULL CHECK(attempt_number>=1),attempt_id TEXT NOT NULL,outcome TEXT NOT NULL CHECK(outcome IN('DELIVERED','FAILED','UNKNOWN')),provider_receipt_json TEXT NOT NULL,attempt_digest TEXT NOT NULL,created_at TEXT NOT NULL,context_digest TEXT NOT NULL,PRIMARY KEY(tenant_id,project_id,outbox_id,attempt_number),UNIQUE(tenant_id,project_id,outbox_id,attempt_id),FOREIGN KEY(tenant_id,project_id,outbox_id) REFERENCES foundry_outbox(tenant_id,project_id,outbox_id)) STRICT;
CREATE INDEX foundry_runs_state_idx ON foundry_runs(tenant_id,project_id,state,updated_at);
CREATE INDEX foundry_evidence_target_idx ON foundry_evidence(tenant_id,project_id,target_id,created_at);
CREATE INDEX foundry_outbox_created_idx ON foundry_outbox(tenant_id,project_id,created_at);
CREATE TRIGGER foundry_schema_metadata_no_update BEFORE UPDATE ON foundry_schema_metadata BEGIN SELECT RAISE(ABORT,'foundry_schema_metadata is immutable'); END;
CREATE TRIGGER foundry_schema_metadata_no_delete BEFORE DELETE ON foundry_schema_metadata BEGIN SELECT RAISE(ABORT,'foundry_schema_metadata is immutable'); END;
CREATE TRIGGER foundry_runs_no_delete BEFORE DELETE ON foundry_runs BEGIN SELECT RAISE(ABORT,'foundry_runs cannot be deleted'); END;
CREATE TRIGGER foundry_run_transitions_no_update BEFORE UPDATE ON foundry_run_transitions BEGIN SELECT RAISE(ABORT,'foundry_run_transitions is immutable'); END;
CREATE TRIGGER foundry_run_transitions_no_delete BEFORE DELETE ON foundry_run_transitions BEGIN SELECT RAISE(ABORT,'foundry_run_transitions is immutable'); END;
CREATE TRIGGER foundry_events_no_update BEFORE UPDATE ON foundry_events BEGIN SELECT RAISE(ABORT,'foundry_events is immutable'); END;
CREATE TRIGGER foundry_events_no_delete BEFORE DELETE ON foundry_events BEGIN SELECT RAISE(ABORT,'foundry_events is immutable'); END;
CREATE TRIGGER foundry_evidence_no_update BEFORE UPDATE ON foundry_evidence BEGIN SELECT RAISE(ABORT,'foundry_evidence is immutable'); END;
CREATE TRIGGER foundry_evidence_no_delete BEFORE DELETE ON foundry_evidence BEGIN SELECT RAISE(ABORT,'foundry_evidence is immutable'); END;
CREATE TRIGGER foundry_checkpoints_no_update BEFORE UPDATE ON foundry_checkpoints BEGIN SELECT RAISE(ABORT,'foundry_checkpoints is immutable'); END;
CREATE TRIGGER foundry_checkpoints_no_delete BEFORE DELETE ON foundry_checkpoints BEGIN SELECT RAISE(ABORT,'foundry_checkpoints is immutable'); END;
CREATE TRIGGER foundry_outbox_no_update BEFORE UPDATE ON foundry_outbox BEGIN SELECT RAISE(ABORT,'foundry_outbox is immutable'); END;
CREATE TRIGGER foundry_outbox_no_delete BEFORE DELETE ON foundry_outbox BEGIN SELECT RAISE(ABORT,'foundry_outbox is immutable'); END;
CREATE TRIGGER foundry_outbox_attempts_no_update BEFORE UPDATE ON foundry_outbox_attempts BEGIN SELECT RAISE(ABORT,'foundry_outbox_attempts is immutable'); END;
CREATE TRIGGER foundry_outbox_attempts_no_delete BEFORE DELETE ON foundry_outbox_attempts BEGIN SELECT RAISE(ABORT,'foundry_outbox_attempts is immutable'); END;
"""
_SCHEMA_DIGEST = canonical_digest(
    {"schema_version": _VERSION, "ddl_digest": digest_bytes(_SCHEMA.encode())}
)


def _objects(connection: sqlite3.Connection) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (str(row[0]), str(row[1]), str(row[2]))
        for row in connection.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    )


def _expected() -> tuple[tuple[str, str, str], ...]:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.executescript(_SCHEMA)
        return _objects(connection)
    finally:
        connection.close()


_EXPECTED = _expected()


def _mapping(value: str) -> Mapping[str, Any]:
    result = strict_json_loads(value)
    if not isinstance(result, dict):
        raise StoreIntegrityError("stored canonical JSON is not an object")
    return result


class FoundryStore:
    READ_CAPABILITY = "foundry.store.read"
    WRITE_CAPABILITY = "foundry.store.write"
    OUTBOX_RECONCILE_CAPABILITY = "foundry.outbox.reconcile"

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        context_verifier: Callable[[TenantScope, str | None], TenantScope] | None,
        outbox_receipt_verifier: OutboxReceiptVerifier | None = None,
        clock: Callable[[], float] = time.time,
        allow_memory_for_tests: bool = False,
    ) -> None:
        if outbox_receipt_verifier is not None and not callable(outbox_receipt_verifier):
            raise TypeError("outbox_receipt_verifier must be callable")
        self._verifier = context_verifier
        self._outbox_receipt_verifier = outbox_receipt_verifier
        self._clock = clock
        self._lock = threading.RLock()
        self._closed = False
        self._memory = os.fspath(path) == ":memory:"
        self._path: Path | None = None
        self._identity: tuple[int, int] | None = None
        if self._memory:
            if not allow_memory_for_tests:
                raise StoreSecurityError("in-memory durability is disabled outside explicit tests")
            database = ":memory:"
        else:
            raw = Path(path).expanduser()
            if raw.exists() and raw.is_symlink():
                raise StoreSecurityError("database path must not be a symbolic link")
            resolved = raw.resolve(strict=False)
            resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            flags = (
                os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(resolved, flags, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
                status = os.fstat(descriptor)
                self._validate_file(status)
                self._identity = (status.st_dev, status.st_ino)
            finally:
                os.close(descriptor)
            self._path = resolved
            database = os.fspath(resolved)
        try:
            self._connection = sqlite3.connect(
                database, isolation_level=None, check_same_thread=False, timeout=5.0
            )
            self._connection.row_factory = sqlite3.Row
            self._configure()
            self._initialize()
            self._verify_file()
        except BaseException:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise

    @property
    def path(self) -> Path | None:
        return self._path

    @staticmethod
    def _validate_file(status: os.stat_result) -> None:
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.geteuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
        ):
            raise StoreSecurityError(
                "database must be a current-user regular file with nlink=1 and mode 0600"
            )

    def _verify_file(self) -> None:
        if self._memory:
            return
        assert self._path is not None and self._identity is not None
        try:
            status = os.lstat(self._path)
        except FileNotFoundError as exc:
            raise StoreSecurityError("database disappeared while open") from exc
        self._validate_file(status)
        if (status.st_dev, status.st_ino) != self._identity:
            raise StoreSecurityError("database path identity changed while open")

    def _configure(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA trusted_schema=OFF")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA temp_store=MEMORY")
        if (
            not self._memory
            and str(self._connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
            != "delete"
        ):
            raise StoreSecurityError("SQLite refused DELETE journal mode")
        if self._connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise StoreSecurityError("SQLite foreign-key enforcement is unavailable")

    def _initialize(self) -> None:
        count = self._connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        if count == 0:
            statement = (
                "BEGIN IMMEDIATE;"
                + _SCHEMA
                + "INSERT INTO foundry_schema_metadata VALUES(1,'"
                + _VERSION
                + "','"
                + _SCHEMA_DIGEST
                + "');COMMIT;"
            )
            try:
                self._connection.executescript(statement)
            except BaseException:
                if self._connection.in_transaction:
                    self._rollback()
                raise
        self._attest()

    def _attest(self) -> None:
        if _objects(self._connection) != _EXPECTED:
            raise StoreIntegrityError("SQLite schema differs from repository contract")
        rows = [
            tuple(row)
            for row in self._connection.execute(
                "SELECT singleton,schema_version,schema_digest FROM foundry_schema_metadata"
            )
        ]
        if rows != [(1, _VERSION, _SCHEMA_DIGEST)]:
            raise StoreIntegrityError("SQLite schema metadata attestation failed")

    def _rollback(self) -> None:
        try:
            self._connection.execute("ROLLBACK")
        except BaseException as exc:
            raise StoreRollbackError("SQLite rollback failed") from exc

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._closed:
                raise StoreClosed("store is closed")
            self._verify_file()
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._attest()
                yield self._connection
                self._connection.execute("COMMIT")
                self._verify_file()
            except BaseException:
                if self._connection.in_transaction:
                    self._rollback()
                raise

    def _authorize(self, scope: TenantScope, capability: str) -> TenantScope:
        if self._verifier is None:
            raise StoreSecurityError("no trusted context verifier is configured")
        try:
            verified = self._verifier(scope, capability)
        except Exception as exc:
            raise StoreSecurityError("host context verification failed") from exc
        if (
            not isinstance(verified, TenantScope)
            or not verified.authenticated
            or verified.binding_digest != scope.binding_digest
        ):
            raise StoreSecurityError("context verifier returned a mismatched scope")
        return verified

    def _now(self) -> str:
        return (
            datetime.fromtimestamp(self._clock(), timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            row["run_id"],
            row["tenant_id"],
            row["project_id"],
            row["operation"],
            row["idempotency_key"],
            row["request_digest"],
            _mapping(row["request_json"]),
            row["state"],
            None if row["response_json"] is None else _mapping(row["response_json"]),
            row["created_at"],
            row["updated_at"],
            row["context_digest"],
        )

    def begin_run(
        self,
        scope: TenantScope,
        operation: str,
        idempotency_key: str,
        request: Mapping[str, Any],
        *,
        run_id: str | None = None,
    ) -> IdempotencyDecision:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        require_identifier(operation, "operation")
        require_identifier(idempotency_key, "idempotency_key")
        request_json, request_digest = canonical_json(request), canonical_digest(request)
        identifier = require_identifier(run_id or f"run-{uuid.uuid4().hex}", "run_id")
        now = self._now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM foundry_runs WHERE tenant_id=? AND project_id=? AND operation=? AND idempotency_key=?",
                (scope.tenant_id, scope.project_id, operation, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_digest"] != request_digest:
                    raise IdempotencyConflict(
                        "idempotency key is bound to a different request digest"
                    )
                return IdempotencyDecision(self._run(row), True)
            connection.execute(
                "INSERT INTO foundry_runs VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    identifier,
                    operation,
                    idempotency_key,
                    request_json,
                    request_digest,
                    RunState.PENDING,
                    now,
                    now,
                    scope.binding_digest,
                ),
            )
            connection.execute(
                "INSERT INTO foundry_run_transitions VALUES(?,?,?,0,NULL,?,'run-created',NULL,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    identifier,
                    RunState.PENDING,
                    now,
                    scope.binding_digest,
                ),
            )
            row = connection.execute(
                "SELECT * FROM foundry_runs WHERE tenant_id=? AND project_id=? AND run_id=?",
                (scope.tenant_id, scope.project_id, identifier),
            ).fetchone()
            assert row is not None
            return IdempotencyDecision(self._run(row), False)

    def get_run(self, scope: TenantScope, run_id: str) -> RunRecord:
        scope = self._authorize(scope, self.READ_CAPABILITY)
        require_identifier(run_id, "run_id")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM foundry_runs WHERE tenant_id=? AND project_id=? AND run_id=?",
                (scope.tenant_id, scope.project_id, run_id),
            ).fetchone()
            if row is None:
                raise RecordNotFound("run was not found in authenticated scope")
            return self._run(row)

    def transition_run(
        self,
        scope: TenantScope,
        run_id: str,
        expected_state: str,
        target_state: str,
        *,
        reason: str,
        response: Mapping[str, Any] | None = None,
    ) -> RunRecord:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        require_identifier(run_id, "run_id")
        if (
            expected_state not in _STATES
            or target_state not in _STATES
            or target_state not in _TRANSITIONS.get(expected_state, set())
        ):
            raise StateTransitionError(
                f"illegal run transition from {expected_state} to {target_state}"
            )
        if not isinstance(reason, str) or not reason or len(reason.encode()) > 1024:
            raise ValueError("transition reason must be non-empty and bounded")
        response_json = None if response is None else canonical_json(response)
        response_digest = None if response is None else canonical_digest(response)
        now = self._now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM foundry_runs WHERE tenant_id=? AND project_id=? AND run_id=?",
                (scope.tenant_id, scope.project_id, run_id),
            ).fetchone()
            if row is None:
                raise RecordNotFound("run was not found in authenticated scope")
            if row["state"] != expected_state:
                raise RecordConflict(f"expected {expected_state}, observed {row['state']}")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence),-1)+1 FROM foundry_run_transitions WHERE tenant_id=? AND project_id=? AND run_id=?",
                (scope.tenant_id, scope.project_id, run_id),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO foundry_run_transitions VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    run_id,
                    sequence,
                    expected_state,
                    target_state,
                    reason,
                    response_digest,
                    now,
                    scope.binding_digest,
                ),
            )
            connection.execute(
                "UPDATE foundry_runs SET state=?,response_json=?,updated_at=?,context_digest=? WHERE tenant_id=? AND project_id=? AND run_id=?",
                (
                    target_state,
                    response_json,
                    now,
                    scope.binding_digest,
                    scope.tenant_id,
                    scope.project_id,
                    run_id,
                ),
            )
            return self._run(
                connection.execute(
                    "SELECT * FROM foundry_runs WHERE tenant_id=? AND project_id=? AND run_id=?",
                    (scope.tenant_id, scope.project_id, run_id),
                ).fetchone()
            )

    def append_event(
        self,
        scope: TenantScope,
        aggregate_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        event_id: str | None = None,
    ) -> EventRecord:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        require_identifier(aggregate_id, "aggregate_id")
        require_identifier(event_type, "event_type")
        identifier = require_identifier(event_id or f"evt-{uuid.uuid4().hex}", "event_id")
        payload_json = canonical_json(payload)
        payload_digest = canonical_digest(payload)
        now = self._now()
        with self._transaction() as connection:
            prior = connection.execute(
                "SELECT sequence,event_digest FROM foundry_events WHERE tenant_id=? AND project_id=? AND aggregate_id=? ORDER BY sequence DESC LIMIT 1",
                (scope.tenant_id, scope.project_id, aggregate_id),
            ).fetchone()
            sequence = 1 if prior is None else prior["sequence"] + 1
            previous = "sha256:" + "0" * 64 if prior is None else prior["event_digest"]
            document = {
                "schema_version": "elmos.foundry.event.v1",
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "aggregate_id": aggregate_id,
                "event_id": identifier,
                "event_type": event_type,
                "sequence": sequence,
                "payload_digest": payload_digest,
                "previous_digest": previous,
                "created_at": now,
                "context_digest": scope.binding_digest,
            }
            event_digest = canonical_digest(document)
            connection.execute(
                "INSERT INTO foundry_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    aggregate_id,
                    sequence,
                    identifier,
                    event_type,
                    payload_json,
                    payload_digest,
                    previous,
                    event_digest,
                    now,
                    scope.binding_digest,
                ),
            )
        return EventRecord(
            identifier,
            aggregate_id,
            event_type,
            sequence,
            _mapping(payload_json),
            payload_digest,
            previous,
            event_digest,
            now,
            scope.binding_digest,
        )

    def list_events(self, scope: TenantScope, aggregate_id: str) -> tuple[EventRecord, ...]:
        scope = self._authorize(scope, self.READ_CAPABILITY)
        require_identifier(aggregate_id, "aggregate_id")
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM foundry_events WHERE tenant_id=? AND project_id=? AND aggregate_id=? ORDER BY sequence",
                (scope.tenant_id, scope.project_id, aggregate_id),
            ).fetchall()
            return tuple(
                EventRecord(
                    row["event_id"],
                    row["aggregate_id"],
                    row["event_type"],
                    row["sequence"],
                    _mapping(row["payload_json"]),
                    row["payload_digest"],
                    row["previous_digest"],
                    row["event_digest"],
                    row["created_at"],
                    row["context_digest"],
                )
                for row in rows
            )

    def verify_event_chain(self, scope: TenantScope, aggregate_id: str) -> bool:
        events = self.list_events(scope, aggregate_id)
        previous = "sha256:" + "0" * 64
        for sequence, event in enumerate(events, 1):
            document = {
                "schema_version": "elmos.foundry.event.v1",
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "aggregate_id": event.aggregate_id,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "sequence": event.sequence,
                "payload_digest": event.payload_digest,
                "previous_digest": event.previous_digest,
                "created_at": event.created_at,
                "context_digest": event.context_digest,
            }
            if (
                event.sequence != sequence
                or event.previous_digest != previous
                or canonical_digest(event.payload) != event.payload_digest
                or canonical_digest(document) != event.event_digest
            ):
                return False
            previous = event.event_digest
        return True

    def append_evidence(
        self,
        scope: TenantScope,
        target_id: str,
        gate_level: str,
        verdict: str,
        payload: Mapping[str, Any],
        *,
        evidence_id: str | None = None,
        evidence_state: EvidenceState = EvidenceState.COLLECTED_SELF_ATTESTED,
        certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED,
    ) -> EvidenceRecord:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        require_identifier(target_id, "target_id")
        identifier = require_identifier(
            evidence_id or f"evidence-{uuid.uuid4().hex}", "evidence_id"
        )
        if evidence_state is EvidenceState.VERIFIED_INDEPENDENT:
            raise StoreSecurityError("local store cannot assert independently verified evidence")
        if certification_status is not CertificationStatus.NOT_CERTIFIED:
            raise StoreSecurityError("local store cannot assert certification")
        if verdict not in {"PASS", "FAIL", "INCONCLUSIVE", "CONDITIONAL"}:
            raise ValueError("evidence verdict is not recognized")
        payload_json, now = canonical_json(payload), self._now()
        document = {
            "schema_version": "elmos.foundry.evidence-record.v1",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "evidence_id": identifier,
            "target_id": target_id,
            "gate_level": gate_level,
            "verdict": verdict,
            "payload": payload,
            "evidence_state": evidence_state.value,
            "certification_status": certification_status.value,
            "created_at": now,
            "context_digest": scope.binding_digest,
        }
        digest = canonical_digest(document)
        with self._transaction() as connection:
            try:
                connection.execute(
                    "INSERT INTO foundry_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        scope.tenant_id,
                        scope.project_id,
                        identifier,
                        target_id,
                        gate_level,
                        verdict,
                        payload_json,
                        digest,
                        evidence_state.value,
                        certification_status.value,
                        now,
                        scope.binding_digest,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise RecordConflict("evidence identifier already exists") from exc
        return EvidenceRecord(
            identifier,
            target_id,
            gate_level,
            verdict,
            _mapping(payload_json),
            digest,
            evidence_state.value,
            certification_status.value,
            now,
            scope.binding_digest,
        )

    def get_evidence(self, scope: TenantScope, evidence_id: str) -> EvidenceRecord:
        scope = self._authorize(scope, self.READ_CAPABILITY)
        require_identifier(evidence_id, "evidence_id")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM foundry_evidence WHERE tenant_id=? AND project_id=? AND evidence_id=?",
                (scope.tenant_id, scope.project_id, evidence_id),
            ).fetchone()
            if row is None:
                raise RecordNotFound("evidence was not found in authenticated scope")
            return EvidenceRecord(
                row["evidence_id"],
                row["target_id"],
                row["gate_level"],
                row["verdict"],
                _mapping(row["payload_json"]),
                row["evidence_digest"],
                row["evidence_state"],
                row["certification_status"],
                row["created_at"],
                row["context_digest"],
            )

    def append_checkpoint(
        self,
        scope: TenantScope,
        stream_id: str,
        expected_sequence: int,
        payload: Mapping[str, Any],
        *,
        checkpoint_id: str | None = None,
    ) -> CheckpointRecord:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        require_identifier(stream_id, "stream_id")
        if (
            not isinstance(expected_sequence, int)
            or isinstance(expected_sequence, bool)
            or expected_sequence < 0
        ):
            raise ValueError("expected_sequence must be non-negative")
        identifier = require_identifier(
            checkpoint_id or f"checkpoint-{uuid.uuid4().hex}", "checkpoint_id"
        )
        payload_json, now = canonical_json(payload), self._now()
        with self._transaction() as connection:
            observed = connection.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM foundry_checkpoints WHERE tenant_id=? AND project_id=? AND stream_id=?",
                (scope.tenant_id, scope.project_id, stream_id),
            ).fetchone()[0]
            if observed != expected_sequence:
                raise RecordConflict(
                    f"checkpoint expected {expected_sequence}, observed {observed}"
                )
            sequence = observed + 1
            digest = canonical_digest(
                {
                    "schema_version": "elmos.foundry.checkpoint.v1",
                    "tenant_id": scope.tenant_id,
                    "project_id": scope.project_id,
                    "stream_id": stream_id,
                    "sequence": sequence,
                    "checkpoint_id": identifier,
                    "payload": payload,
                    "created_at": now,
                    "context_digest": scope.binding_digest,
                }
            )
            connection.execute(
                "INSERT INTO foundry_checkpoints VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    stream_id,
                    sequence,
                    identifier,
                    payload_json,
                    digest,
                    now,
                    scope.binding_digest,
                ),
            )
        return CheckpointRecord(
            identifier,
            stream_id,
            sequence,
            _mapping(payload_json),
            digest,
            now,
            scope.binding_digest,
        )

    def enqueue_outbox(
        self,
        scope: TenantScope,
        topic: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        *,
        outbox_id: str | None = None,
    ) -> tuple[OutboxRecord, bool]:
        scope = self._authorize(scope, self.WRITE_CAPABILITY)
        require_identifier(topic, "topic")
        require_identifier(idempotency_key, "idempotency_key")
        identifier = require_identifier(outbox_id or f"outbox-{uuid.uuid4().hex}", "outbox_id")
        payload_json, payload_digest, now = (
            canonical_json(payload),
            canonical_digest(payload),
            self._now(),
        )
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM foundry_outbox WHERE tenant_id=? AND project_id=? AND topic=? AND idempotency_key=?",
                (scope.tenant_id, scope.project_id, topic, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["payload_digest"] != payload_digest:
                    raise IdempotencyConflict(
                        "outbox idempotency key is bound to different payload"
                    )
                return self._outbox(row), True
            connection.execute(
                "INSERT INTO foundry_outbox VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    identifier,
                    topic,
                    idempotency_key,
                    payload_json,
                    payload_digest,
                    now,
                    scope.binding_digest,
                ),
            )
            row = connection.execute(
                "SELECT * FROM foundry_outbox WHERE tenant_id=? AND project_id=? AND outbox_id=?",
                (scope.tenant_id, scope.project_id, identifier),
            ).fetchone()
            return self._outbox(row), False

    @staticmethod
    def _outbox(row: sqlite3.Row) -> OutboxRecord:
        keys = set(row.keys())
        state = row["delivery_state"] if "delivery_state" in keys else "PENDING"
        return OutboxRecord(
            row["outbox_id"],
            row["topic"],
            row["idempotency_key"],
            _mapping(row["payload_json"]),
            row["payload_digest"],
            row["created_at"],
            row["context_digest"],
            state or "PENDING",
        )

    def pending_outbox(self, scope: TenantScope, *, limit: int = 100) -> tuple[OutboxRecord, ...]:
        scope = self._authorize(scope, self.READ_CAPABILITY)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValueError("outbox limit must be in [1,1000]")
        sql = """SELECT o.*,COALESCE((SELECT a.outcome FROM foundry_outbox_attempts a WHERE a.tenant_id=o.tenant_id AND a.project_id=o.project_id AND a.outbox_id=o.outbox_id ORDER BY a.attempt_number DESC LIMIT 1),'PENDING') delivery_state FROM foundry_outbox o WHERE o.tenant_id=? AND o.project_id=? AND NOT EXISTS(SELECT 1 FROM foundry_outbox_attempts d WHERE d.tenant_id=o.tenant_id AND d.project_id=o.project_id AND d.outbox_id=o.outbox_id AND d.outcome='DELIVERED') AND COALESCE((SELECT a.outcome FROM foundry_outbox_attempts a WHERE a.tenant_id=o.tenant_id AND a.project_id=o.project_id AND a.outbox_id=o.outbox_id ORDER BY a.attempt_number DESC LIMIT 1),'PENDING')<>'UNKNOWN' ORDER BY o.created_at,o.outbox_id LIMIT ?"""
        with self._transaction() as connection:
            return tuple(
                self._outbox(row)
                for row in connection.execute(sql, (scope.tenant_id, scope.project_id, limit))
            )

    def record_outbox_attempt(
        self,
        scope: TenantScope,
        outbox_id: str,
        attempt_id: str,
        outcome: str,
        provider_receipt: Mapping[str, Any],
    ) -> tuple[OutboxAttemptRecord, bool]:
        scope = self._authorize(scope, self.OUTBOX_RECONCILE_CAPABILITY)
        require_identifier(outbox_id, "outbox_id")
        require_identifier(attempt_id, "attempt_id")
        if outcome not in {"DELIVERED", "FAILED", "UNKNOWN"}:
            raise ValueError("outbox outcome is not recognized")
        with self._transaction() as connection:
            outbox_row = connection.execute(
                "SELECT * FROM foundry_outbox WHERE tenant_id=? AND project_id=? AND outbox_id=?",
                (scope.tenant_id, scope.project_id, outbox_id),
            ).fetchone()
            if outbox_row is None:
                raise RecordNotFound("outbox record was not found in scope")
            outbox_record = self._outbox(outbox_row)
        if self._outbox_receipt_verifier is None:
            raise StoreSecurityError(
                "outbox reconciliation requires a trusted provider-receipt verifier"
            )
        try:
            receipt_verified = self._outbox_receipt_verifier(
                scope,
                outbox_record,
                attempt_id,
                outcome,
                provider_receipt,
            )
        except Exception as exc:
            raise StoreSecurityError("provider-receipt verification failed closed") from exc
        if receipt_verified is not True:
            raise StoreSecurityError("provider receipt was denied or mismatched")
        receipt_json, now = canonical_json(provider_receipt), self._now()
        digest = canonical_digest(
            {
                "schema_version": "elmos.foundry.outbox-attempt.v1",
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "outbox_id": outbox_id,
                "attempt_id": attempt_id,
                "outcome": outcome,
                "provider_receipt": provider_receipt,
                "context_digest": scope.binding_digest,
            }
        )
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM foundry_outbox_attempts WHERE tenant_id=? AND project_id=? AND outbox_id=? AND attempt_id=?",
                (scope.tenant_id, scope.project_id, outbox_id, attempt_id),
            ).fetchone()
            if row is not None:
                if row["attempt_digest"] != digest:
                    raise IdempotencyConflict("attempt identifier reused with different evidence")
                return self._attempt(row), True
            if (
                connection.execute(
                    "SELECT 1 FROM foundry_outbox WHERE tenant_id=? AND project_id=? AND outbox_id=?",
                    (scope.tenant_id, scope.project_id, outbox_id),
                ).fetchone()
                is None
            ):
                raise RecordNotFound("outbox record was not found in scope")
            if connection.execute(
                "SELECT 1 FROM foundry_outbox_attempts WHERE tenant_id=? AND project_id=? AND outbox_id=? AND outcome='DELIVERED'",
                (scope.tenant_id, scope.project_id, outbox_id),
            ).fetchone():
                raise RecordConflict("outbox already durably delivered")
            number = connection.execute(
                "SELECT COALESCE(MAX(attempt_number),0)+1 FROM foundry_outbox_attempts WHERE tenant_id=? AND project_id=? AND outbox_id=?",
                (scope.tenant_id, scope.project_id, outbox_id),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO foundry_outbox_attempts VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    scope.project_id,
                    outbox_id,
                    number,
                    attempt_id,
                    outcome,
                    receipt_json,
                    digest,
                    now,
                    scope.binding_digest,
                ),
            )
            row = connection.execute(
                "SELECT * FROM foundry_outbox_attempts WHERE tenant_id=? AND project_id=? AND outbox_id=? AND attempt_id=?",
                (scope.tenant_id, scope.project_id, outbox_id, attempt_id),
            ).fetchone()
            return self._attempt(row), False

    @staticmethod
    def _attempt(row: sqlite3.Row) -> OutboxAttemptRecord:
        return OutboxAttemptRecord(
            row["outbox_id"],
            row["attempt_id"],
            row["attempt_number"],
            row["outcome"],
            _mapping(row["provider_receipt_json"]),
            row["attempt_digest"],
            row["created_at"],
            row["context_digest"],
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._connection.in_transaction:
                self._rollback()
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "FoundryStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


StateStore = FoundryStore
__all__ = [
    "CheckpointRecord",
    "EvidenceRecord",
    "EventRecord",
    "FoundryStore",
    "IdempotencyConflict",
    "IdempotencyDecision",
    "OutboxAttemptRecord",
    "OutboxRecord",
    "OutboxReceiptVerifier",
    "RecordConflict",
    "RecordNotFound",
    "RunRecord",
    "RunState",
    "StateStore",
    "StateTransitionError",
    "StoreClosed",
    "StoreError",
    "StoreIntegrityError",
    "StoreRollbackError",
    "StoreSecurityError",
]
