from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_json, digest_value, validate_identifier
from .contracts import ProofResult, ProofRunState, Scope, TERMINAL_RUN_STATES, utc_now
from .gate import validate_result


class StoreError(RuntimeError):
    pass


_ALLOWED_TRANSITIONS = {
    ProofRunState.QUEUED: {ProofRunState.LEASED, ProofRunState.CANCELLED},
    ProofRunState.LEASED: {
        ProofRunState.RUNNING,
        ProofRunState.QUEUED,
        ProofRunState.CANCEL_REQUESTED,
    },
    ProofRunState.RUNNING: {
        ProofRunState.PAUSED,
        ProofRunState.CANCEL_REQUESTED,
        ProofRunState.SUCCEEDED,
        ProofRunState.FAILED,
        ProofRunState.TIMED_OUT,
    },
    ProofRunState.PAUSED: {ProofRunState.LEASED, ProofRunState.CANCELLED},
    ProofRunState.CANCEL_REQUESTED: {ProofRunState.CANCELLED, ProofRunState.FAILED},
    ProofRunState.SUCCEEDED: set(),
    ProofRunState.FAILED: set(),
    ProofRunState.CANCELLED: set(),
    ProofRunState.TIMED_OUT: set(),
}


class StateStore:
    """Tenant-scoped durable local state used by the trusted service boundary.

    PostgreSQL 17 migrations in the imported package are the production
    persistence contract. SQLite is deliberately limited to local execution,
    tests and offline replay; it preserves the same fail-closed invariants.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            state_path = Path(path).expanduser()
            if state_path.is_symlink():
                raise StoreError("state database path must not be a symlink")
            state_path.parent.mkdir(parents=True, exist_ok=True)
            path = state_path
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
              tenant_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              response_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS events (
              tenant_id TEXT NOT NULL,
              aggregate_type TEXT NOT NULL,
              aggregate_id TEXT NOT NULL,
              sequence INTEGER NOT NULL,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              previous_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, aggregate_type, aggregate_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS proof_runs (
              tenant_id TEXT NOT NULL,
              run_id TEXT NOT NULL,
              account_id TEXT NOT NULL,
              obligation_id TEXT NOT NULL,
              state TEXT NOT NULL,
              owner_id TEXT,
              fencing_token INTEGER NOT NULL,
              lease_expires_at TEXT,
              result_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, run_id)
            );
            CREATE TABLE IF NOT EXISTS cache_entries (
              tenant_id TEXT NOT NULL,
              cache_key TEXT NOT NULL,
              result_json TEXT NOT NULL,
              stale INTEGER NOT NULL DEFAULT 0,
              expires_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, cache_key)
            );
            CREATE TABLE IF NOT EXISTS invocations (
              tenant_id TEXT NOT NULL,
              invocation_id TEXT NOT NULL,
              skill_id TEXT NOT NULL,
              subject_id TEXT NOT NULL,
              request_digest TEXT NOT NULL,
              outcome_digest TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY (tenant_id, invocation_id)
            );
            """
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def get_idempotent(
        self, tenant_id: str, key: str, request_digest: str
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT request_digest, response_json FROM idempotency WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, key),
            ).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise StoreError("idempotency key was reused with a different request")
        return json.loads(row["response_json"])

    def put_idempotent(
        self, tenant_id: str, key: str, request_digest: str, response: dict[str, Any]
    ) -> None:
        payload = canonical_json(response).decode("utf-8")
        with self._lock, self._connection:
            try:
                self._connection.execute(
                    "INSERT INTO idempotency VALUES (?, ?, ?, ?, ?)",
                    (tenant_id, key, request_digest, payload, utc_now()),
                )
            except sqlite3.IntegrityError:
                existing = self.get_idempotent(tenant_id, key, request_digest)
                if existing != response:
                    raise StoreError("idempotency record conflict")

    def record_invocation(
        self,
        scope: Scope,
        invocation_id: str,
        skill_id: str,
        subject_id: str,
        request_digest: str,
        outcome: dict[str, Any],
    ) -> None:
        validate_identifier(invocation_id, "invocationId")
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO invocations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    invocation_id,
                    skill_id,
                    subject_id,
                    request_digest,
                    digest_value(outcome),
                    utc_now(),
                ),
            )

    def complete_idempotent_invocation(
        self,
        scope: Scope,
        invocation_id: str,
        skill_id: str,
        subject_id: str,
        request_digest: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist idempotency, invocation and audit event in one transaction."""
        validate_identifier(invocation_id, "invocationId")
        response_json = canonical_json(response).decode("utf-8")
        outcome_digest = digest_value(response)
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT request_digest, response_json FROM idempotency WHERE tenant_id=? AND idempotency_key=?",
                (scope.tenant_id, invocation_id),
            ).fetchone()
            if existing is not None:
                if existing["request_digest"] != request_digest:
                    raise StoreError(
                        "idempotency key was reused with a different request"
                    )
                return json.loads(existing["response_json"])
            self._connection.execute(
                "INSERT INTO idempotency VALUES (?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    invocation_id,
                    request_digest,
                    response_json,
                    utc_now(),
                ),
            )
            self._connection.execute(
                "INSERT INTO invocations VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    invocation_id,
                    skill_id,
                    subject_id,
                    request_digest,
                    outcome_digest,
                    utc_now(),
                ),
            )
            row = self._connection.execute(
                "SELECT sequence, event_hash FROM events WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=? ORDER BY sequence DESC LIMIT 1",
                (scope.tenant_id, "skill_invocation", invocation_id),
            ).fetchone()
            sequence = 1 if row is None else int(row["sequence"]) + 1
            previous_hash = "0" * 64 if row is None else row["event_hash"]
            unsigned = {
                "tenantId": scope.tenant_id,
                "aggregateType": "skill_invocation",
                "aggregateId": invocation_id,
                "sequence": sequence,
                "eventType": "completed",
                "payload": {
                    "skillId": skill_id,
                    "outcomeDigest": outcome_digest,
                    "proofStatus": response["proofStatus"],
                },
                "previousHash": previous_hash,
            }
            event_hash = digest_value(unsigned)
            self._connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    "skill_invocation",
                    invocation_id,
                    sequence,
                    "completed",
                    canonical_json(unsigned["payload"]).decode("utf-8"),
                    previous_hash,
                    event_hash,
                    utc_now(),
                ),
            )
        return response

    def append_event(
        self,
        scope: Scope,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT sequence, event_hash FROM events WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=? ORDER BY sequence DESC LIMIT 1",
                (scope.tenant_id, aggregate_type, aggregate_id),
            ).fetchone()
            sequence = 1 if row is None else int(row["sequence"]) + 1
            previous_hash = "0" * 64 if row is None else row["event_hash"]
            unsigned = {
                "tenantId": scope.tenant_id,
                "aggregateType": aggregate_type,
                "aggregateId": aggregate_id,
                "sequence": sequence,
                "eventType": event_type,
                "payload": payload,
                "previousHash": previous_hash,
            }
            event_hash = digest_value(unsigned)
            event = {**unsigned, "eventHash": event_hash, "createdAt": utc_now()}
            self._connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    aggregate_type,
                    aggregate_id,
                    sequence,
                    event_type,
                    canonical_json(payload).decode("utf-8"),
                    previous_hash,
                    event_hash,
                    event["createdAt"],
                ),
            )
        return event

    def events(
        self, scope: Scope, aggregate_type: str, aggregate_id: str
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=? ORDER BY sequence",
                (scope.tenant_id, aggregate_type, aggregate_id),
            ).fetchall()
        return [
            {
                "tenantId": row["tenant_id"],
                "aggregateType": row["aggregate_type"],
                "aggregateId": row["aggregate_id"],
                "sequence": row["sequence"],
                "eventType": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "previousHash": row["previous_hash"],
                "eventHash": row["event_hash"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def submit_run(
        self,
        scope: Scope,
        run_id: str,
        obligation_id: str,
        account_concurrency: int = 3,
    ) -> dict[str, Any]:
        validate_identifier(run_id, "runId")
        validate_identifier(obligation_id, "obligationId")
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
            if existing is not None:
                raise StoreError("duplicate proof run")
            active = self._connection.execute(
                "SELECT count(*) FROM proof_runs WHERE tenant_id=? AND account_id=? AND state NOT IN (?, ?, ?, ?)",
                (
                    scope.tenant_id,
                    scope.account_id,
                    *(state.value for state in TERMINAL_RUN_STATES),
                ),
            ).fetchone()[0]
            if active >= account_concurrency:
                raise StoreError("top-level account concurrency limit exceeded")
            now = utc_now()
            self._connection.execute(
                "INSERT INTO proof_runs(tenant_id,run_id,account_id,obligation_id,state,owner_id,fencing_token,lease_expires_at,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    scope.tenant_id,
                    run_id,
                    scope.account_id,
                    obligation_id,
                    ProofRunState.QUEUED.value,
                    None,
                    1,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        self.append_event(scope, "proof_run", run_id, "submitted", {"fencingToken": 1})
        return self.get_run(scope, run_id)

    def get_run(self, scope: Scope, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
        if row is None:
            raise StoreError("unknown proof run")
        return dict(row)

    def lease_run(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        expected_token: int,
        lease_seconds: int = 900,
    ) -> dict[str, Any]:
        if lease_seconds < 1 or lease_seconds > 86_400:
            raise StoreError("lease duration is outside the allowed bound")
        now = datetime.now(timezone.utc)
        expiry = (
            (now + timedelta(seconds=lease_seconds))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise StoreError("unknown proof run")
            state = ProofRunState(row["state"])
            if state not in {
                ProofRunState.QUEUED,
                ProofRunState.PAUSED,
                ProofRunState.LEASED,
            }:
                raise StoreError("run is not leasable")
            if int(row["fencing_token"]) != expected_token:
                raise StoreError("fencing token mismatch")
            if (
                state == ProofRunState.LEASED
                and row["owner_id"] != worker_id
                and row["lease_expires_at"]
                and row["lease_expires_at"] > utc_now()
            ):
                raise StoreError("active lease belongs to another worker")
            new_token = expected_token + 1
            self._connection.execute(
                "UPDATE proof_runs SET state=?, owner_id=?, fencing_token=?, lease_expires_at=?, updated_at=? WHERE tenant_id=? AND run_id=? AND fencing_token=?",
                (
                    ProofRunState.LEASED.value,
                    worker_id,
                    new_token,
                    expiry,
                    utc_now(),
                    scope.tenant_id,
                    run_id,
                    expected_token,
                ),
            )
        self.append_event(
            scope,
            "proof_run",
            run_id,
            "leased",
            {"ownerId": worker_id, "fencingToken": new_token},
        )
        return self.get_run(scope, run_id)

    def start_run(
        self, scope: Scope, run_id: str, worker_id: str, token: int
    ) -> dict[str, Any]:
        self._authorized_transition(
            scope, run_id, worker_id, token, ProofRunState.RUNNING
        )
        return self.get_run(scope, run_id)

    def transition_run(
        self, scope: Scope, run_id: str, new_state: ProofRunState
    ) -> dict[str, Any]:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT * FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise StoreError("unknown proof run")
            current = ProofRunState(row["state"])
            if new_state not in _ALLOWED_TRANSITIONS[current]:
                raise StoreError(
                    f"invalid transition {current.value}->{new_state.value}"
                )
            self._connection.execute(
                "UPDATE proof_runs SET state=?, updated_at=? WHERE tenant_id=? AND run_id=?",
                (new_state.value, utc_now(), scope.tenant_id, run_id),
            )
        self.append_event(
            scope, "proof_run", run_id, "state_changed", {"state": new_state.value}
        )
        return self.get_run(scope, run_id)

    def authorized_transition(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        token: int,
        new_state: ProofRunState,
    ) -> dict[str, Any]:
        self._authorized_transition(scope, run_id, worker_id, token, new_state)
        return self.get_run(scope, run_id)

    def commit_run(
        self, scope: Scope, run_id: str, worker_id: str, token: int, result: ProofResult
    ) -> dict[str, Any]:
        if result.obligation_id != self.get_run(scope, run_id)["obligation_id"]:
            raise StoreError("result obligation mismatch")
        try:
            validate_result(result)
        except ValueError as exc:
            raise StoreError(f"invalid proof result: {exc}") from exc
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT state,owner_id,fencing_token,lease_expires_at FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
            if row is None:
                raise StoreError("unknown proof run")
            if row["state"] != ProofRunState.RUNNING.value:
                raise StoreError("only a running owner may commit")
            if row["owner_id"] != worker_id or int(row["fencing_token"]) != token:
                raise StoreError("stale or non-owner worker")
            if row["lease_expires_at"] and row["lease_expires_at"] <= utc_now():
                raise StoreError("worker lease has expired")
            self._connection.execute(
                "UPDATE proof_runs SET state=?, result_json=?, updated_at=? WHERE tenant_id=? AND run_id=? AND owner_id=? AND fencing_token=? AND state=?",
                (
                    ProofRunState.SUCCEEDED.value,
                    canonical_json(result_to_dict(result)).decode("utf-8"),
                    utc_now(),
                    scope.tenant_id,
                    run_id,
                    worker_id,
                    token,
                    ProofRunState.RUNNING.value,
                ),
            )
        self.append_event(
            scope,
            "proof_run",
            run_id,
            "evidence_committed",
            {"fencingToken": token, "status": result.status.value},
        )
        return self.get_run(scope, run_id)

    def _authorized_transition(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        token: int,
        new_state: ProofRunState,
    ) -> None:
        with self._lock:
            row = self._connection.execute(
                "SELECT state,owner_id,fencing_token,lease_expires_at FROM proof_runs WHERE tenant_id=? AND run_id=?",
                (scope.tenant_id, run_id),
            ).fetchone()
        if row is None:
            raise StoreError("unknown proof run")
        if row["owner_id"] != worker_id or int(row["fencing_token"]) != token:
            raise StoreError("stale or non-owner worker")
        if row["lease_expires_at"] and row["lease_expires_at"] <= utc_now():
            raise StoreError("worker lease has expired")
        current = ProofRunState(row["state"])
        if new_state not in _ALLOWED_TRANSITIONS[current]:
            raise StoreError(f"invalid transition {current.value}->{new_state.value}")
        self.transition_run(scope, run_id, new_state)

    def put_cache(
        self,
        scope: Scope,
        cache_key: str,
        result: dict[str, Any],
        ttl_seconds: int = 86_400,
    ) -> None:
        if ttl_seconds < 1 or ttl_seconds > 31_536_000:
            raise StoreError("cache TTL is outside the allowed bound")
        expires = (
            (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO cache_entries VALUES (?, ?, ?, 0, ?) ON CONFLICT(tenant_id,cache_key) DO UPDATE SET result_json=excluded.result_json, stale=0, expires_at=excluded.expires_at",
                (
                    scope.tenant_id,
                    cache_key,
                    canonical_json(result).decode("utf-8"),
                    expires,
                ),
            )

    def get_cache(self, scope: Scope, cache_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT result_json, stale, expires_at FROM cache_entries WHERE tenant_id=? AND cache_key=?",
                (scope.tenant_id, cache_key),
            ).fetchone()
        if row is None or row["stale"] or row["expires_at"] <= utc_now():
            return None
        return json.loads(row["result_json"])

    def invalidate_cache(self, scope: Scope, dependency_id: str) -> int:
        with self._lock, self._connection:
            # Cache records are keyed by a canonical dependency tuple.  The
            # dependency id is intentionally matched only in stored metadata.
            rows = self._connection.execute(
                "SELECT cache_key,result_json FROM cache_entries WHERE tenant_id=? AND stale=0",
                (scope.tenant_id,),
            ).fetchall()
            affected = 0
            for row in rows:
                value = json.loads(row["result_json"])
                if dependency_id in value.get("dependencies", []):
                    self._connection.execute(
                        "UPDATE cache_entries SET stale=1 WHERE tenant_id=? AND cache_key=?",
                        (scope.tenant_id, row["cache_key"]),
                    )
                    affected += 1
            return affected

    def verify_event_chain(
        self, scope: Scope, aggregate_type: str, aggregate_id: str
    ) -> list[str]:
        """Verify the append-only hash chain without trusting stored hashes."""
        errors: list[str] = []
        previous = "0" * 64
        for event in self.events(scope, aggregate_type, aggregate_id):
            if event["previousHash"] != previous:
                errors.append(f"sequence {event['sequence']}: previous hash mismatch")
            unsigned = {
                "tenantId": event["tenantId"],
                "aggregateType": event["aggregateType"],
                "aggregateId": event["aggregateId"],
                "sequence": event["sequence"],
                "eventType": event["eventType"],
                "payload": event["payload"],
                "previousHash": event["previousHash"],
            }
            expected = digest_value(unsigned)
            if event["eventHash"] != expected:
                errors.append(f"sequence {event['sequence']}: event hash mismatch")
            previous = event["eventHash"]
        return errors


def result_to_dict(result: ProofResult) -> dict[str, Any]:
    return {
        "runId": result.run_id,
        "obligationId": result.obligation_id,
        "status": result.status.value,
        "assuranceLevel": result.assurance_level.value,
        "engine": result.engine,
        "mode": result.mode,
        "assumptionHash": result.assumption_hash,
        "tcbHash": result.tcb_hash,
        "formulaHash": result.formula_hash,
        "bound": result.bound,
        "artifacts": list(result.artifact_refs),
        "counterexampleId": result.counterexample_id,
        "diagnostics": list(result.diagnostics),
        "createdAt": result.created_at,
        "stale": result.stale,
    }
