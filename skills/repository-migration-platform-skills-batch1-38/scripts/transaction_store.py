#!/usr/bin/env python3
"""SQLite WAL authority for repository-migration runtime state.

The filesystem object store contains immutable bytes. This database is the
transactional authority for metadata, Evidence, Verification, effects, gates,
certificate requests, and the hash-chained audit event stream.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 2
ZERO_HASH = "sha256:" + "0" * 64


class StoreConflict(Exception):
    """A uniqueness, fencing, or immutable-state conflict."""


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def decode_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise StoreConflict("stored JSON value is not an object")
    return payload


class TransactionStore:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.path = self.workspace / "runtime-state.sqlite3"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize_schema(self) -> None:
        connection = self.connect()
        try:
            current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current_version not in {0, SCHEMA_VERSION}:
                raise StoreConflict(
                    f"unsupported transactional state schema {current_version}; expected {SCHEMA_VERSION}"
                )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workspace_snapshot (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    snapshot_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    batch INTEGER NOT NULL CHECK(batch BETWEEN 1 AND 38),
                    claim_type TEXT NOT NULL CHECK(claim_type IN ('output','test','external')),
                    claim_index INTEGER NOT NULL CHECK(claim_index >= 0),
                    object_sha256 TEXT NOT NULL,
                    identity_sha256 TEXT NOT NULL UNIQUE,
                    record_sha256 TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL,
                    created_revision INTEGER NOT NULL REFERENCES events(revision),
                    UNIQUE(batch, claim_type, claim_index, identity_sha256)
                );

                CREATE TABLE IF NOT EXISTS verifications (
                    verification_id TEXT PRIMARY KEY,
                    batch INTEGER NOT NULL CHECK(batch BETWEEN 1 AND 38),
                    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
                    evidence_sha256 TEXT NOT NULL,
                    verifier_id TEXT NOT NULL,
                    outcome TEXT NOT NULL CHECK(outcome IN ('PASS','FAIL','INCONCLUSIVE')),
                    record_sha256 TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL,
                    created_revision INTEGER NOT NULL REFERENCES events(revision),
                    UNIQUE(evidence_id, evidence_sha256, verifier_id, outcome)
                );

                CREATE TABLE IF NOT EXISTS effects (
                    idempotency_key TEXT PRIMARY KEY,
                    effect_id TEXT NOT NULL UNIQUE,
                    batch INTEGER NOT NULL CHECK(batch BETWEEN 1 AND 38),
                    target TEXT NOT NULL,
                    fencing_token INTEGER NOT NULL CHECK(fencing_token >= 0),
                    identity_sha256 TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_revision INTEGER NOT NULL REFERENCES events(revision),
                    UNIQUE(target, fencing_token)
                );

                CREATE TABLE IF NOT EXISTS gate_results (
                    batch INTEGER NOT NULL CHECK(batch BETWEEN 1 AND 38),
                    mode TEXT NOT NULL CHECK(mode IN ('local','certification')),
                    decision TEXT NOT NULL,
                    evidence_root TEXT NOT NULL,
                    evaluated_revision INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    created_revision INTEGER NOT NULL REFERENCES events(revision),
                    PRIMARY KEY(batch, mode)
                );

                CREATE TABLE IF NOT EXISTS certificate_requests (
                    batch INTEGER PRIMARY KEY CHECK(batch BETWEEN 1 AND 38),
                    request_id TEXT NOT NULL UNIQUE,
                    request_sha256 TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_revision INTEGER NOT NULL REFERENCES events(revision)
                );

                CREATE TABLE IF NOT EXISTS certificates (
                    batch INTEGER PRIMARY KEY CHECK(batch BETWEEN 1 AND 38),
                    certificate_sha256 TEXT NOT NULL UNIQUE,
                    policy_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    certificate_json TEXT NOT NULL,
                    created_revision INTEGER NOT NULL REFERENCES events(revision)
                );
                """
            )
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        finally:
            connection.close()

    @contextmanager
    def transaction(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        begun = False
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            begun = True
            yield connection
            connection.execute("COMMIT")
            begun = False
        except Exception:
            if begun:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _append_event(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> int:
        row = connection.execute("SELECT event_hash FROM events ORDER BY revision DESC LIMIT 1").fetchone()
        previous_hash = str(row["event_hash"]) if row else ZERO_HASH
        material = {
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "payload": payload,
            "previous_hash": previous_hash,
            "created_at": created_at,
        }
        event_hash = sha256_bytes(canonical_bytes(material))
        event_id = "event-" + event_hash.split(":", 1)[1][:24]
        cursor = connection.execute(
            "INSERT INTO events(event_id,event_type,aggregate_id,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?)",
            (event_id, event_type, aggregate_id, canonical_bytes(payload).decode("utf-8"), previous_hash, event_hash, created_at),
        )
        return int(cursor.lastrowid)

    def initialize_metadata(self, metadata: dict[str, Any], snapshot: dict[str, Any], created_at: str) -> dict[str, Any]:
        with self.transaction() as connection:
            existing_rows = connection.execute("SELECT key,value_json FROM metadata").fetchall()
            if existing_rows:
                existing = {row["key"]: json.loads(row["value_json"]) for row in existing_rows}
                if existing.get("source_root") != metadata.get("source_root") or existing.get("target_objective") != metadata.get("target_objective"):
                    raise StoreConflict("workspace is already bound to a different source or target objective")
                return existing
            for key, value in metadata.items():
                connection.execute("INSERT INTO metadata(key,value_json) VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False, sort_keys=True)))
            connection.execute(
                "INSERT INTO workspace_snapshot(singleton,snapshot_json) VALUES(1,?)",
                (canonical_bytes(snapshot).decode("utf-8"),),
            )
            revision = self._append_event(connection, "WORKSPACE_INITIALIZED", "workspace", {"metadata": metadata, "snapshot_fingerprint": snapshot["fingerprint"]}, created_at)
            connection.execute("INSERT INTO metadata(key,value_json) VALUES(?,?)", ("initialized_revision", json.dumps(revision)))
            return {**metadata, "initialized_revision": revision}

    def snapshot(self) -> dict[str, Any]:
        connection = self.connect()
        try:
            row = connection.execute("SELECT snapshot_json FROM workspace_snapshot WHERE singleton=1").fetchone()
            if row is None:
                raise StoreConflict("transactional source snapshot is missing")
            return decode_object(row["snapshot_json"])
        finally:
            connection.close()

    def recover_snapshot(self, snapshot: dict[str, Any], created_at: str) -> None:
        with self.transaction() as connection:
            existing = connection.execute("SELECT 1 FROM workspace_snapshot WHERE singleton=1").fetchone()
            if existing:
                return
            metadata_row = connection.execute("SELECT value_json FROM metadata WHERE key='source_fingerprint'").fetchone()
            if metadata_row is None or json.loads(metadata_row["value_json"]) != snapshot.get("fingerprint"):
                raise StoreConflict("snapshot recovery does not match the bound source fingerprint")
            connection.execute(
                "INSERT INTO workspace_snapshot(singleton,snapshot_json) VALUES(1,?)",
                (canonical_bytes(snapshot).decode("utf-8"),),
            )
            self._append_event(
                connection,
                "SOURCE_SNAPSHOT_RECOVERED",
                "workspace",
                {"snapshot_fingerprint": snapshot["fingerprint"]},
                created_at,
            )

    def metadata(self) -> dict[str, Any]:
        connection = self.connect()
        try:
            return {row["key"]: json.loads(row["value_json"]) for row in connection.execute("SELECT key,value_json FROM metadata")}
        finally:
            connection.close()

    def event_count(self) -> int:
        connection = self.connect()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        finally:
            connection.close()

    def revision(self) -> int:
        connection = self.connect()
        try:
            return int(connection.execute("SELECT COALESCE(MAX(revision),0) FROM events").fetchone()[0])
        finally:
            connection.close()

    def record_evidence(
        self,
        record: dict[str, Any],
        identity_sha256: str,
        record_sha256: str,
    ) -> tuple[dict[str, Any], bool]:
        evidence_id = record["evidence_id"]
        with self.transaction() as connection:
            existing = connection.execute("SELECT record_json,identity_sha256 FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
            if existing:
                if existing["identity_sha256"] != identity_sha256:
                    raise StoreConflict(f"immutable evidence id collision: {evidence_id}")
                return decode_object(existing["record_json"]), False
            revision = self._append_event(connection, "EVIDENCE_RECORDED", evidence_id, record, record["recorded_at"])
            connection.execute(
                "INSERT INTO evidence(evidence_id,batch,claim_type,claim_index,object_sha256,identity_sha256,record_sha256,record_json,created_revision) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    evidence_id,
                    record["batch"],
                    record["claim_type"],
                    record["claim_index"],
                    record["object"]["sha256"],
                    identity_sha256,
                    record_sha256,
                    canonical_bytes(record).decode("utf-8"),
                    revision,
                ),
            )
            return record, True

    def evidence(self, batch: int | None = None) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            query = "SELECT record_json FROM evidence"
            parameters: tuple[Any, ...] = ()
            if batch is not None:
                query += " WHERE batch=?"
                parameters = (batch,)
            query += " ORDER BY created_revision,evidence_id"
            return [decode_object(row["record_json"]) for row in connection.execute(query, parameters)]
        finally:
            connection.close()

    def evidence_row(self, evidence_id: str) -> sqlite3.Row | None:
        connection = self.connect()
        try:
            return connection.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
        finally:
            connection.close()

    def record_verification(self, record: dict[str, Any], record_sha256: str) -> tuple[dict[str, Any], bool]:
        verification_id = record["verification_id"]
        with self.transaction() as connection:
            evidence = connection.execute("SELECT record_sha256 FROM evidence WHERE evidence_id=?", (record["evidence_id"],)).fetchone()
            if not evidence:
                raise StoreConflict(f"evidence does not exist: {record['evidence_id']}")
            if evidence["record_sha256"] != record["evidence_sha256"]:
                raise StoreConflict("verification does not bind the current Evidence digest")
            existing = connection.execute("SELECT record_json FROM verifications WHERE verification_id=?", (verification_id,)).fetchone()
            if existing:
                return decode_object(existing["record_json"]), False
            revision = self._append_event(connection, "EVIDENCE_VERIFIED", verification_id, record, record["verified_at"])
            connection.execute(
                "INSERT INTO verifications(verification_id,batch,evidence_id,evidence_sha256,verifier_id,outcome,record_sha256,record_json,created_revision) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    verification_id,
                    record["batch"],
                    record["evidence_id"],
                    record["evidence_sha256"],
                    record["verifier_id"],
                    record["outcome"],
                    record_sha256,
                    canonical_bytes(record).decode("utf-8"),
                    revision,
                ),
            )
            return record, True

    def verifications(self, batch: int | None = None) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            query = "SELECT record_json FROM verifications"
            parameters: tuple[Any, ...] = ()
            if batch is not None:
                query += " WHERE batch=?"
                parameters = (batch,)
            query += " ORDER BY created_revision,verification_id"
            return [decode_object(row["record_json"]) for row in connection.execute(query, parameters)]
        finally:
            connection.close()

    def evidence_root(self, batch: int) -> tuple[str, int]:
        with self.transaction(immediate=False) as connection:
            evidence_rows = connection.execute(
                "SELECT record_sha256,created_revision FROM evidence WHERE batch=? ORDER BY evidence_id", (batch,)
            ).fetchall()
            verification_rows = connection.execute(
                "SELECT record_sha256,created_revision FROM verifications WHERE batch=? ORDER BY verification_id", (batch,)
            ).fetchall()
            revision = max(
                [0, *[int(row["created_revision"]) for row in evidence_rows], *[int(row["created_revision"]) for row in verification_rows]]
            )
            return sha256_bytes(
                canonical_bytes(
                    {
                        "evidence": [str(row["record_sha256"]) for row in evidence_rows],
                        "verifications": [str(row["record_sha256"]) for row in verification_rows],
                    }
                )
            ), revision

    @staticmethod
    def _gate_input_revision(
        evidence_rows: list[sqlite3.Row],
        verification_rows: list[sqlite3.Row],
        dependency_rows: list[sqlite3.Row],
    ) -> int:
        revisions = [
            *[int(row["created_revision"]) for row in evidence_rows],
            *[int(row["created_revision"]) for row in verification_rows],
            *[int(row["created_revision"]) for row in dependency_rows],
        ]
        return max([0, *revisions])

    def gate_snapshot(self, batch: int) -> dict[str, Any]:
        with self.transaction(immediate=False) as connection:
            evidence_rows = connection.execute(
                "SELECT record_json,record_sha256,created_revision FROM evidence WHERE batch=? ORDER BY evidence_id", (batch,)
            ).fetchall()
            verification_rows = connection.execute(
                "SELECT record_json,record_sha256,created_revision FROM verifications WHERE batch=? ORDER BY verification_id", (batch,)
            ).fetchall()
            dependency_rows = connection.execute(
                "SELECT batch,decision,created_revision FROM gate_results WHERE mode='local' AND batch<>? ORDER BY batch", (batch,)
            ).fetchall()
            states = {
                int(row["batch"]): str(row["decision"])
                for row in connection.execute("SELECT batch,decision FROM gate_results WHERE mode='local'")
            }
            certificate_row = connection.execute(
                "SELECT certificate_sha256,created_revision FROM certificates WHERE batch=?", (batch,)
            ).fetchone()
            revision = self._gate_input_revision(evidence_rows, verification_rows, dependency_rows)
            root = sha256_bytes(
                canonical_bytes(
                    {
                        "evidence": [str(row["record_sha256"]) for row in evidence_rows],
                        "verifications": [str(row["record_sha256"]) for row in verification_rows],
                    }
                )
            )
            return {
                "evidence": [decode_object(row["record_json"]) for row in evidence_rows],
                "verifications": [decode_object(row["record_json"]) for row in verification_rows],
                "gate_states": states,
                "revision": revision,
                "evidence_root": root,
                "certificate_state_sha256": str(certificate_row["certificate_sha256"]) if certificate_row else ZERO_HASH,
            }

    def record_effect(self, record: dict[str, Any], identity_sha256: str) -> tuple[dict[str, Any], bool]:
        with self.transaction() as connection:
            existing = connection.execute("SELECT identity_sha256,record_json FROM effects WHERE idempotency_key=?", (record["idempotency_key"],)).fetchone()
            if existing:
                if existing["identity_sha256"] != identity_sha256:
                    raise StoreConflict("idempotency key already binds a different effect")
                return decode_object(existing["record_json"]), False
            maximum = connection.execute("SELECT MAX(fencing_token) FROM effects WHERE target=?", (record["target"],)).fetchone()[0]
            if maximum is not None and record["fencing_token"] <= int(maximum):
                raise StoreConflict(f"fencing token must be greater than {maximum} for target {record['target']}")
            revision = self._append_event(connection, "EFFECT_PLANNED", record["effect_id"], record, record["recorded_at"])
            connection.execute(
                "INSERT INTO effects(idempotency_key,effect_id,batch,target,fencing_token,identity_sha256,record_json,created_revision) VALUES(?,?,?,?,?,?,?,?)",
                (
                    record["idempotency_key"], record["effect_id"], record["batch"], record["target"],
                    record["fencing_token"], identity_sha256, canonical_bytes(record).decode("utf-8"), revision,
                ),
            )
            return record, True

    def effects(self) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            return [decode_object(row[0]) for row in connection.execute("SELECT record_json FROM effects ORDER BY created_revision")]
        finally:
            connection.close()

    def gate_states(self) -> dict[int, str]:
        connection = self.connect()
        try:
            rows = connection.execute("SELECT batch,decision FROM gate_results WHERE mode='local'")
            return {int(row["batch"]): str(row["decision"]) for row in rows}
        finally:
            connection.close()

    def record_gate(self, result: dict[str, Any]) -> dict[str, Any]:
        with self.transaction() as connection:
            batch = int(result["batch"])
            evidence_rows = connection.execute(
                "SELECT created_revision FROM evidence WHERE batch=?", (batch,)
            ).fetchall()
            verification_rows = connection.execute(
                "SELECT created_revision FROM verifications WHERE batch=?", (batch,)
            ).fetchall()
            dependency_rows = connection.execute(
                "SELECT created_revision FROM gate_results WHERE mode='local' AND batch<>?", (batch,)
            ).fetchall()
            certificate_row = connection.execute(
                "SELECT certificate_sha256 FROM certificates WHERE batch=?", (batch,)
            ).fetchone()
            current_revision = self._gate_input_revision(evidence_rows, verification_rows, dependency_rows)
            if result["evaluated_revision"] != current_revision:
                raise StoreConflict("gate input revision changed during evaluation; retry")
            current_certificate = str(certificate_row["certificate_sha256"]) if certificate_row else ZERO_HASH
            if result["certificate_state_sha256"] != current_certificate:
                raise StoreConflict("certificate state changed during gate evaluation; retry")
            revision = self._append_event(connection, "GATE_EVALUATED", f"batch-{result['batch']:02d}:{result['mode']}", result, result["evaluated_at"])
            connection.execute(
                "INSERT INTO gate_results(batch,mode,decision,evidence_root,evaluated_revision,result_json,created_revision) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(batch,mode) DO UPDATE SET decision=excluded.decision,evidence_root=excluded.evidence_root,evaluated_revision=excluded.evaluated_revision,result_json=excluded.result_json,created_revision=excluded.created_revision",
                (
                    result["batch"], result["mode"], result["decision"], result["evidence_root"],
                    result["evaluated_revision"], canonical_bytes(result).decode("utf-8"), revision,
                ),
            )
            return result

    def gate_result(self, batch: int, mode: str = "local") -> dict[str, Any] | None:
        connection = self.connect()
        try:
            row = connection.execute("SELECT result_json FROM gate_results WHERE batch=? AND mode=?", (batch, mode)).fetchone()
            return decode_object(row["result_json"]) if row else None
        finally:
            connection.close()

    def store_certificate_request(self, request: dict[str, Any], request_sha256: str) -> dict[str, Any]:
        with self.transaction() as connection:
            revision = self._append_event(connection, "CERTIFICATE_REQUESTED", request["request_id"], request, request["requested_at"])
            connection.execute(
                "INSERT INTO certificate_requests(batch,request_id,request_sha256,request_json,created_revision) VALUES(?,?,?,?,?) "
                "ON CONFLICT(batch) DO UPDATE SET request_id=excluded.request_id,request_sha256=excluded.request_sha256,request_json=excluded.request_json,created_revision=excluded.created_revision",
                (request["batch"], request["request_id"], request_sha256, canonical_bytes(request).decode("utf-8"), revision),
            )
            return request

    def certificate_request(self, batch: int) -> tuple[dict[str, Any], str] | None:
        connection = self.connect()
        try:
            row = connection.execute("SELECT request_json,request_sha256 FROM certificate_requests WHERE batch=?", (batch,)).fetchone()
            return (decode_object(row["request_json"]), str(row["request_sha256"])) if row else None
        finally:
            connection.close()

    def record_certificate(self, certificate: dict[str, Any], certificate_sha256: str, policy_id: str, created_at: str) -> None:
        with self.transaction() as connection:
            revision = self._append_event(connection, "CERTIFICATE_IMPORTED", f"batch-{certificate['batch']:02d}", certificate, created_at)
            connection.execute(
                "INSERT INTO certificates(batch,certificate_sha256,policy_id,expires_at,certificate_json,created_revision) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(batch) DO UPDATE SET certificate_sha256=excluded.certificate_sha256,policy_id=excluded.policy_id,expires_at=excluded.expires_at,certificate_json=excluded.certificate_json,created_revision=excluded.created_revision",
                (certificate["batch"], certificate_sha256, policy_id, certificate["expires_at"], canonical_bytes(certificate).decode("utf-8"), revision),
            )

    def certificate(self, batch: int) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            row = connection.execute("SELECT certificate_json FROM certificates WHERE batch=?", (batch,)).fetchone()
            return decode_object(row["certificate_json"]) if row else None
        finally:
            connection.close()

    def verify_event_chain(self) -> list[str]:
        errors: list[str] = []
        previous = ZERO_HASH
        expected_revision = 1
        connection = self.connect()
        try:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                errors.append(f"SQLite integrity check failed: {integrity}")
            for row in connection.execute("SELECT * FROM events ORDER BY revision"):
                if int(row["revision"]) != expected_revision:
                    errors.append(f"event revision gap before {row['revision']}")
                expected_revision = int(row["revision"]) + 1
                payload = decode_object(row["payload_json"])
                material = {
                    "event_type": row["event_type"],
                    "aggregate_id": row["aggregate_id"],
                    "payload": payload,
                    "previous_hash": previous,
                    "created_at": row["created_at"],
                }
                expected = sha256_bytes(canonical_bytes(material))
                if row["previous_hash"] != previous or row["event_hash"] != expected:
                    errors.append(f"event chain mismatch at revision {row['revision']}")
                if row["event_id"] != "event-" + expected.split(":", 1)[1][:24]:
                    errors.append(f"event id mismatch at revision {row['revision']}")
                previous = str(row["event_hash"])
            bindings = (
                ("evidence", "evidence_id", "EVIDENCE_RECORDED"),
                ("verifications", "verification_id", "EVIDENCE_VERIFIED"),
                ("effects", "effect_id", "EFFECT_PLANNED"),
                ("certificate_requests", "request_id", "CERTIFICATE_REQUESTED"),
            )
            for table, aggregate_column, event_type in bindings:
                rows = connection.execute(
                    f"SELECT t.{aggregate_column} AS aggregate_id,t.created_revision,e.event_type,e.aggregate_id AS event_aggregate "
                    f"FROM {table} t LEFT JOIN events e ON e.revision=t.created_revision"
                )
                for row in rows:
                    if row["event_type"] != event_type or row["event_aggregate"] != row["aggregate_id"]:
                        errors.append(f"{table} event binding mismatch at revision {row['created_revision']}")
            for row in connection.execute(
                "SELECT g.batch,g.mode,g.created_revision,e.event_type,e.aggregate_id FROM gate_results g "
                "LEFT JOIN events e ON e.revision=g.created_revision"
            ):
                expected_aggregate = f"batch-{int(row['batch']):02d}:{row['mode']}"
                if row["event_type"] != "GATE_EVALUATED" or row["aggregate_id"] != expected_aggregate:
                    errors.append(f"gate event binding mismatch at revision {row['created_revision']}")
            for row in connection.execute(
                "SELECT c.batch,c.created_revision,e.event_type,e.aggregate_id FROM certificates c "
                "LEFT JOIN events e ON e.revision=c.created_revision"
            ):
                expected_aggregate = f"batch-{int(row['batch']):02d}"
                if row["event_type"] != "CERTIFICATE_IMPORTED" or row["aggregate_id"] != expected_aggregate:
                    errors.append(f"certificate event binding mismatch at revision {row['created_revision']}")
        finally:
            connection.close()
        return errors
