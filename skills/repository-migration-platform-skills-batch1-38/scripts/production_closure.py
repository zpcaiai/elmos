#!/usr/bin/env python3
"""Fail-closed production-closure control plane for migration executions.

The module records byte-bound customer snapshots, sealed independent holdouts,
cutover/rollback transitions, soak observations, and independent assessments.
It never reads credentials, invokes a provider, writes customer data, or emits a
certificate.  Provider effects remain the responsibility of trusted_adapters;
this control plane consumes their immutable receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from actor_trust import ActorTrustStore, canonical_digest, parse_time
import external_authority


MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
PRODUCTION_MIN_SOAK_SECONDS = 7 * 24 * 60 * 60
PRODUCTION_MAX_GAP_SECONDS = 6 * 60 * 60
PRODUCTION_OBSERVATION_SKEW_SECONDS = 15 * 60
MAX_CLOCK_SKEW_SECONDS = 5 * 60
MAX_SOAK_OBSERVATIONS = 100_000
LEGACY_PROVIDER_FIELDS = {
    "provider_id", "account_binding_sha256", "region", "adapter_id",
    "precheck_operation", "execute_operation", "verify_operation", "rollback_operation",
}
EXACT_PROVIDER_FIELDS = LEGACY_PROVIDER_FIELDS | {
    "profile_version", "provider_api_version", "account_model", "adapter_version",
    "iac_tool", "iac_tool_version", "state_backend_sha256", "identity_binding_sha256",
    "least_privilege_policy_sha256", "rollback_plan_sha256",
}
CUTOVER_TRANSITIONS = {
    "PLANNED": {"PRECHECKED", "CANCELLED"},
    "PRECHECKED": {"APPROVED", "CANCELLED"},
    "APPROVED": {"EXECUTING", "CANCELLED"},
    "EXECUTING": {"VERIFYING", "ROLLING_BACK", "UNKNOWN"},
    "VERIFYING": {"SUCCEEDED", "ROLLING_BACK", "UNKNOWN"},
    "ROLLING_BACK": {"ROLLED_BACK", "UNKNOWN"},
    "UNKNOWN": {"VERIFYING", "ROLLING_BACK"},
}
TRANSITION_ROLES = {
    "PRECHECKED": "operations-owner",
    "APPROVED": "production-approver",
    "EXECUTING": "operations-owner",
    "VERIFYING": "production-verifier",
    "SUCCEEDED": "production-verifier",
    "ROLLING_BACK": "operations-owner",
    "ROLLED_BACK": "production-verifier",
    "UNKNOWN": "operations-owner",
    "CANCELLED": "production-approver",
}


class ClosureError(ValueError):
    pass


class SystemEvidenceClock:
    """Non-injectable wall clock used by the CLI and real runtime paths."""

    mode = "system"

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)


class ControlledTestClock:
    """Explicit engineering clock; its output can never become production evidence."""

    mode = "controlled-test"

    def __init__(self, current: datetime):
        self.set(current)

    def set(self, current: datetime) -> None:
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ClosureError("controlled test clock must be timezone-aware")
        self._current = current.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._current


SYSTEM_EVIDENCE_CLOCK = SystemEvidenceClock()


def evidence_clock(clock: SystemEvidenceClock | ControlledTestClock | None = None) -> SystemEvidenceClock | ControlledTestClock:
    if clock is None or clock is SYSTEM_EVIDENCE_CLOCK:
        return SYSTEM_EVIDENCE_CLOCK
    if isinstance(clock, ControlledTestClock):
        return clock
    raise ClosureError("unsupported evidence clock")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def now_text() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def utc_now() -> datetime:
    """Compatibility wall clock; production evidence uses SYSTEM_EVIDENCE_CLOCK directly."""
    return SYSTEM_EVIDENCE_CLOCK.now()


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or any(character.isspace() for character in value):
        raise ClosureError(f"{label} must be a non-empty bounded identifier")
    return value


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise ClosureError(f"{label} must be sha256:<64 lowercase hex>")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ClosureError(f"{label} must be sha256:<64 lowercase hex>") from exc
    if value != value.lower():
        raise ClosureError(f"{label} must be lowercase")
    return value


def read_regular(path: Path, maximum: int, label: str) -> bytes:
    resolved = path.expanduser().resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode) or observed.st_size > maximum:
            raise ClosureError(f"{label} must be a bounded regular file")
        data = bytearray()
        while len(data) < observed.st_size:
            chunk = os.read(descriptor, min(65536, observed.st_size - len(data)))
            if not chunk:
                raise ClosureError(f"{label} changed while being read")
            data.extend(chunk)
        if os.read(descriptor, 1):
            raise ClosureError(f"{label} changed while being read")
        return bytes(data)
    finally:
        os.close(descriptor)


def confined(path: Path, roots: tuple[Path, ...], label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ClosureError(f"{label} escapes approved roots")
    return resolved


def artifact_ref(value: Any, roots: tuple[Path, ...], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"path", "sha256", "bytes"}:
        raise ClosureError(f"{label} reference fields are invalid")
    path = confined(Path(value["path"]), roots, label)
    data = read_regular(path, MAX_ARTIFACT_BYTES, label)
    expected = require_digest(value.get("sha256"), f"{label}.sha256")
    if sha256_bytes(data) != expected or value.get("bytes") != len(data):
        raise ClosureError(f"{label} byte/digest mismatch")
    return {"sha256": expected, "bytes": len(data)}


class ClosureStore:
    """SQLite WAL authority with hash-chained events and monotonic fencing."""

    def __init__(self, workspace: Path):
        self.root = workspace.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "production-closure.sqlite3"
        connection = self.connect()
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots(
                    snapshot_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    environment_class TEXT NOT NULL, manifest_sha256 TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS holdouts(
                    holdout_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    corpus_sha256 TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS holdout_results(
                    result_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    holdout_id TEXT NOT NULL, decision TEXT NOT NULL, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cutovers(
                    cutover_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, target_key TEXT NOT NULL,
                    state TEXT NOT NULL, fencing_token INTEGER NOT NULL,
                    plan_sha256 TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS soak_runs(
                    run_id TEXT PRIMARY KEY, cutover_id TEXT NOT NULL,
                    environment_class TEXT NOT NULL, state TEXT NOT NULL,
                    last_sequence INTEGER NOT NULL, last_observed_at TEXT,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assessments(
                    assessment_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    evidence_root TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL, record_sha256 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
            """)
            connection.execute("PRAGMA user_version=1")
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @staticmethod
    def _event(connection: sqlite3.Connection, event_type: str, aggregate_id: str,
               record_sha256: str, created_at: str) -> None:
        row = connection.execute("SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = row[0] if row else "GENESIS"
        event_hash = canonical_digest({"event_type": event_type, "aggregate_id": aggregate_id,
                                       "record_sha256": record_sha256, "previous_hash": previous,
                                       "created_at": created_at})
        connection.execute("INSERT INTO events(event_type,aggregate_id,record_sha256,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?)",
                           (event_type, aggregate_id, record_sha256, previous, event_hash, created_at))

    def insert(self, table: str, identity: str, columns: tuple[Any, ...], record: dict[str, Any], event: str) -> dict[str, Any]:
        if table not in {"snapshots", "holdouts", "holdout_results", "cutovers", "soak_runs", "assessments"}:
            raise ClosureError("invalid closure table")
        encoded = canonical_bytes(record).decode("utf-8")
        record_sha = sha256_bytes(encoded.encode("utf-8"))
        created = now_text()
        placeholders = ",".join("?" for _ in range(len(columns) + 1))
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            identity_column = {"snapshots": "snapshot_id", "holdouts": "holdout_id", "holdout_results": "result_id", "cutovers": "cutover_id",
                               "soak_runs": "run_id", "assessments": "assessment_id"}[table]
            existing = connection.execute(f"SELECT record_json FROM {table} WHERE {identity_column}=?", (identity,)).fetchone()
            if existing:
                observed = json.loads(existing[0])
                if observed != record:
                    raise ClosureError(f"{table[:-1]} id is already bound to another record")
                connection.commit()
                return observed
            connection.execute(f"INSERT INTO {table} VALUES({placeholders})", (*columns, encoded))
            self._event(connection, event, identity, record_sha, created)
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def row(self, table: str, identity: str) -> dict[str, Any]:
        if table not in {"snapshots", "holdouts", "holdout_results", "cutovers", "soak_runs", "assessments"}:
            raise ClosureError("invalid closure table")
        connection = self.connect()
        try:
            identity_column = {"snapshots": "snapshot_id", "holdouts": "holdout_id", "holdout_results": "result_id", "cutovers": "cutover_id",
                               "soak_runs": "run_id", "assessments": "assessment_id"}[table]
            row = connection.execute(f"SELECT record_json FROM {table} WHERE {identity_column}=?", (identity,)).fetchone()
        finally:
            connection.close()
        if row is None:
            raise ClosureError(f"{table[:-1]} does not exist")
        return json.loads(row[0])

    def transition_cutover(self, cutover_id: str, expected: str, target: str, fencing_token: int,
                           record: dict[str, Any]) -> dict[str, Any]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state,fencing_token FROM cutovers WHERE cutover_id=?", (cutover_id,)).fetchone()
            if row is None or row["state"] != expected:
                raise ClosureError(f"cutover state conflict; expected {expected}")
            if fencing_token <= int(row["fencing_token"]):
                raise ClosureError("cutover fencing token must increase")
            encoded = canonical_bytes(record).decode("utf-8")
            connection.execute("UPDATE cutovers SET state=?,fencing_token=?,record_json=? WHERE cutover_id=?",
                               (target, fencing_token, encoded, cutover_id))
            self._event(connection, f"CUTOVER_{target}", cutover_id, sha256_bytes(encoded.encode()), now_text())
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_soak(self, run_id: str, expected_sequence: int, observed_at: str,
                    record: dict[str, Any], state: str | None = None) -> dict[str, Any]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT last_sequence,last_observed_at,state FROM soak_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None or row["state"] != "RUNNING" or expected_sequence != int(row["last_sequence"]) + 1:
                raise ClosureError("soak observation sequence/state conflict")
            if row["last_observed_at"] and parse_time(observed_at, "observed_at") <= parse_time(row["last_observed_at"], "last_observed_at"):
                raise ClosureError("soak observation time must increase")
            encoded = canonical_bytes(record).decode("utf-8")
            connection.execute("UPDATE soak_runs SET state=?,last_sequence=?,last_observed_at=?,record_json=? WHERE run_id=?",
                               (state or "RUNNING", expected_sequence, observed_at, encoded, run_id))
            self._event(connection, "SOAK_OBSERVED" if state is None else f"SOAK_{state}", run_id,
                        sha256_bytes(encoded.encode()), now_text())
            connection.commit()
            return record
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def verify_event_chain(self) -> list[str]:
        connection = self.connect()
        try:
            rows = connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
            records = {
                "snapshots": connection.execute("SELECT snapshot_id AS identity,tenant_id,environment_class,record_json FROM snapshots").fetchall(),
                "holdouts": connection.execute("SELECT holdout_id AS identity,tenant_id,record_json FROM holdouts").fetchall(),
                "holdout_results": connection.execute("SELECT result_id AS identity,tenant_id,decision,record_json FROM holdout_results").fetchall(),
                "cutovers": connection.execute("SELECT cutover_id AS identity,tenant_id,state,fencing_token,record_json FROM cutovers").fetchall(),
                "soak_runs": connection.execute("SELECT run_id AS identity,state,last_sequence,last_observed_at,record_json FROM soak_runs").fetchall(),
                "assessments": connection.execute("SELECT assessment_id AS identity,tenant_id,record_json FROM assessments").fetchall(),
            }
        finally:
            connection.close()
        findings, previous, latest = [], "GENESIS", {}
        for row in rows:
            expected = canonical_digest({"event_type": row["event_type"], "aggregate_id": row["aggregate_id"],
                                         "record_sha256": row["record_sha256"], "previous_hash": previous,
                                         "created_at": row["created_at"]})
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                findings.append(f"event {row['sequence']} hash-chain mismatch")
            event_type = row["event_type"]
            table = ("holdout_results" if event_type.startswith("HOLDOUT_RESULT") else
                     "holdouts" if event_type.startswith("HOLDOUT") else
                     "snapshots" if event_type.startswith("SNAPSHOT") else
                     "cutovers" if event_type.startswith("CUTOVER") else
                     "soak_runs" if event_type.startswith("SOAK") else
                     "assessments" if event_type.startswith("ASSESSMENT") else None)
            if table is None:
                findings.append(f"event {row['sequence']} has unknown aggregate kind")
            else:
                latest[(table, row["aggregate_id"])] = row["record_sha256"]
            previous = row["event_hash"]
        for table, table_rows in records.items():
            for row in table_rows:
                identity = row["identity"]
                try:
                    record = json.loads(row["record_json"])
                except json.JSONDecodeError:
                    findings.append(f"{table}:{identity} record JSON is invalid")
                    continue
                observed_sha = sha256_bytes(canonical_bytes(record))
                if latest.get((table, identity)) != observed_sha:
                    findings.append(f"{table}:{identity} current record differs from latest event")
                if "tenant_id" in row.keys() and record.get("tenant_id") != row["tenant_id"]:
                    findings.append(f"{table}:{identity} tenant metadata mismatch")
                if table == "snapshots" and record.get("environment_class") != row["environment_class"]:
                    findings.append(f"{table}:{identity} environment metadata mismatch")
                if table == "holdout_results" and record.get("decision") != row["decision"]:
                    findings.append(f"{table}:{identity} decision metadata mismatch")
                if table == "cutovers" and (record.get("state") != row["state"] or
                        record.get("fencing_token") != row["fencing_token"]):
                    findings.append(f"{table}:{identity} state/fencing metadata mismatch")
                if table == "soak_runs" and (record.get("state") != row["state"] or
                        record.get("last_sequence") != row["last_sequence"] or
                        record.get("last_observed_at") != row["last_observed_at"]):
                    findings.append(f"{table}:{identity} state/sequence metadata mismatch")
        return findings


def load_manifest(path: Path, roots: tuple[Path, ...], label: str) -> tuple[dict[str, Any], str]:
    raw = read_regular(confined(path, roots, label), MAX_MANIFEST_BYTES, label)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClosureError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"{label} must be an object")
    return value, sha256_bytes(canonical_bytes(value))


def provider_profile(value: Any, *, require_exact: bool = False) -> dict[str, str]:
    if not isinstance(value, dict) or frozenset(value) not in {frozenset(LEGACY_PROVIDER_FIELDS), frozenset(EXACT_PROVIDER_FIELDS)}:
        raise ClosureError("cutover provider profile fields are invalid")
    exact = set(value) == EXACT_PROVIDER_FIELDS
    if require_exact and not exact:
        raise ClosureError("production cutover requires an exact versioned Provider/IaC profile")
    if exact and value.get("profile_version") != "2.0":
        raise ClosureError("exact provider profile_version must be 2.0")
    digest_fields = {"account_binding_sha256"}
    if exact:
        digest_fields |= {"state_backend_sha256", "identity_binding_sha256",
                          "least_privilege_policy_sha256", "rollback_plan_sha256"}
    result: dict[str, str] = {}
    for field in value:
        result[field] = (require_digest(value.get(field), f"provider.{field}") if field in digest_fields
                         else identifier(value.get(field), f"provider.{field}"))
    return result


def production_actor_groups(trust: ActorTrustStore, groups: dict[str, list[str]]) -> dict[str, list[str]]:
    """Resolve exact organizations and reject actor aliases masquerading as independence."""
    if trust.schema_version != "2.0" or trust.purpose != "workspace-actors":
        raise ClosureError("production evidence requires a version 2 workspace Actor Trust Store")
    organizations: dict[str, list[str]] = {}
    role_by_group = {
        "data_owner": "data-owner", "transformation_authors": "transformation-author",
        "custodian": "holdout-custodian", "executors": "holdout-executor",
        "verifiers": "holdout-verifier", "oracle_owners": "oracle-owner",
    }
    for group, actor_ids in groups.items():
        expected_role = role_by_group[group]
        observed: set[str] = set()
        for actor_id in actor_ids:
            actor = trust.actors.get(actor_id)
            if (actor is None or expected_role not in actor.roles or not actor.organization_id or
                    not actor.authority_class):
                raise ClosureError(f"production actor group {group} is not organization/role bound")
            observed.add(actor.organization_id)
        if not observed:
            raise ClosureError(f"production actor group {group} is empty")
        organizations[group] = sorted(observed)
    items = list(organizations.items())
    for left, (left_name, left_orgs) in enumerate(items):
        for right_name, right_orgs in items[left + 1:]:
            if set(left_orgs) & set(right_orgs):
                raise ClosureError(f"production organizations overlap: {left_name}/{right_name}")
    return organizations


def provider_transition_receipt(value: Any, roots: tuple[Path, ...], cutover: dict[str, Any],
                                target_state: str) -> dict[str, Any]:
    """Verify an exact provider/account/operation wrapper and its native receipt bytes."""
    outer = artifact_ref(value, roots, "cutover receipt")
    path = confined(Path(value["path"]), roots, "cutover receipt")
    try:
        payload = json.loads(read_regular(path, MAX_MANIFEST_BYTES, "cutover receipt"))
    except json.JSONDecodeError as exc:
        raise ClosureError("provider transition receipt is invalid JSON") from exc
    base = {"schema_version", "receipt_id", "cutover_id", "tenant_id", "target_key",
            "target_state", "provider", "operation", "adapter_receipt", "effect_state",
            "request_sha256", "issued_at"}
    exact_profile = isinstance(payload, dict) and isinstance(payload.get("provider"), dict) and \
        payload["provider"].get("profile_version") == "2.0"
    required = base | ({"control_evidence", "control_decisions"} if exact_profile else set())
    expected_schema = "2.0" if exact_profile else "1.0"
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != expected_schema:
        raise ClosureError("provider transition receipt fields are invalid")
    if (identifier(payload.get("receipt_id"), "receipt_id") == cutover.get("cutover_id") or
            payload.get("cutover_id") != cutover.get("cutover_id") or
            payload.get("tenant_id") != cutover.get("tenant_id") or
            payload.get("target_key") != cutover.get("target_key") or payload.get("target_state") != target_state):
        raise ClosureError("provider transition receipt binding is invalid")
    profile = provider_profile(payload.get("provider"), require_exact=bool(cutover.get("environment_class") == "production"))
    expected_profile = cutover.get("provider")
    if not isinstance(expected_profile, dict) or profile != expected_profile:
        raise ClosureError("provider transition receipt tuple differs from the approved plan")
    operation_by_state = {
        "PRECHECKED": "precheck_operation", "EXECUTING": "execute_operation",
        "VERIFYING": "verify_operation", "SUCCEEDED": "verify_operation",
        "ROLLING_BACK": "rollback_operation", "ROLLED_BACK": "rollback_operation",
    }
    operation_field = operation_by_state.get(target_state)
    if operation_field and profile[operation_field] != payload.get("operation"):
        raise ClosureError("provider operation differs from the approved plan")
    if target_state == "UNKNOWN" and payload.get("operation") not in {
            profile["execute_operation"], profile["verify_operation"], profile["rollback_operation"]}:
        raise ClosureError("unknown provider outcome is not bound to an approved mutating operation")
    expected_effect = "UNKNOWN" if target_state == "UNKNOWN" else "SUCCEEDED"
    if payload.get("effect_state") != expected_effect:
        raise ClosureError(f"provider receipt effect_state must be {expected_effect}")
    request_sha = require_digest(payload.get("request_sha256"), "provider receipt request_sha256")
    issued = parse_time(payload.get("issued_at"), "provider receipt issued_at")
    if issued > utc_now() + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("provider receipt is future-dated")
    native = artifact_ref(payload.get("adapter_receipt"), roots, "native adapter receipt")
    controls: dict[str, Any] | None = None
    if exact_profile:
        decisions = payload.get("control_decisions")
        evidence = payload.get("control_evidence")
        control_keys = {"identity", "least_privilege", "state_backend", "rollback"}
        if (not isinstance(decisions, dict) or set(decisions) != control_keys or
                any(decisions[key] != "PASS" for key in control_keys) or
                not isinstance(evidence, dict) or set(evidence) != control_keys):
            raise ClosureError("provider control decisions/evidence are incomplete or non-passing")
        refs = {key: artifact_ref(evidence[key], roots, f"provider {key} evidence") for key in control_keys}
        expected_digests = {
            "identity": profile["identity_binding_sha256"],
            "least_privilege": profile["least_privilege_policy_sha256"],
            "state_backend": profile["state_backend_sha256"],
            "rollback": profile["rollback_plan_sha256"],
        }
        if any(refs[key]["sha256"] != expected_digests[key] for key in control_keys):
            raise ClosureError("provider control evidence differs from the approved exact profile")
        controls = {"decisions": decisions, "evidence": refs}
    return {**outer, "receipt_id": payload["receipt_id"], "provider": profile,
            "operation": payload.get("operation"),
            "effect_state": expected_effect, "request_sha256": request_sha,
            "adapter_receipt": native, "issued_at": payload["issued_at"],
            **({"controls": controls} if controls is not None else {})}


def register_snapshot(workspace: Path, manifest_path: Path, authorization: dict[str, Any],
                      trust_path: Path, roots: tuple[Path, ...]) -> dict[str, Any]:
    manifest, manifest_sha = load_manifest(manifest_path, roots, "customer snapshot manifest")
    required = {"schema_version", "snapshot_id", "tenant_id", "environment_class", "classification",
                "purpose", "read_only", "files"}
    if set(manifest) != required or manifest.get("schema_version") != "1.0":
        raise ClosureError("customer snapshot manifest fields are invalid")
    snapshot_id = identifier(manifest.get("snapshot_id"), "snapshot_id")
    tenant_id = identifier(manifest.get("tenant_id"), "tenant_id")
    environment = manifest.get("environment_class")
    if (environment not in {"test", "sandbox", "production"} or
            not isinstance(manifest.get("classification"), str) or not manifest["classification"] or
            not isinstance(manifest.get("purpose"), str) or not manifest["purpose"]):
        raise ClosureError("snapshot environment/classification is invalid")
    if manifest.get("read_only") is not True:
        raise ClosureError("customer snapshot intake must be read-only")
    files = manifest.get("files")
    if not isinstance(files, list) or not files or len(files) > 100_000:
        raise ClosureError("customer snapshot files are invalid")
    observed, total = set(), 0
    for index, item in enumerate(files):
        reference = artifact_ref(item, roots, f"snapshot file {index}")
        if reference["sha256"] in observed:
            raise ClosureError("snapshot contains duplicate content")
        observed.add(reference["sha256"])
        total += reference["bytes"]
    trust = ActorTrustStore.load(trust_path)
    actor = trust.verify(authorization, "data-owner", {"snapshot_id": snapshot_id, "tenant_id": tenant_id,
                         "manifest_sha256": manifest_sha, "environment_class": environment,
                         "purpose": manifest.get("purpose")})
    if environment == "production":
        production_actor_groups(trust, {"data_owner": [actor["actor_id"]]})
    record = {"schema_version": "1.0", "snapshot_id": snapshot_id, "tenant_id": tenant_id,
              "environment_class": environment, "classification": manifest["classification"],
              "purpose": manifest["purpose"], "manifest_sha256": manifest_sha, "file_count": len(files),
              "total_bytes": total, "content_root": canonical_digest(sorted(observed)), "read_only": True,
              "data_minimization": "metadata-and-content-digests-only", "authorization": actor}
    return ClosureStore(workspace).insert("snapshots", snapshot_id,
        (snapshot_id, tenant_id, environment, manifest_sha), record, "SNAPSHOT_REGISTERED")


def register_holdout(workspace: Path, manifest_path: Path, authorization: dict[str, Any],
                     trust_path: Path, roots: tuple[Path, ...]) -> dict[str, Any]:
    manifest, manifest_sha = load_manifest(manifest_path, roots, "holdout manifest")
    base = {"schema_version", "holdout_id", "tenant_id", "environment_class", "corpus",
            "development_corpus_sha256", "transformation_author_ids", "executor_ids", "verifier_ids"}
    version = manifest.get("schema_version")
    required = base | ({"oracle_owner_ids", "oracle_registry_sha256", "claim_oracle_map",
                        "development_partition_id", "holdout_partition_id"} if version == "2.0" else set())
    if set(manifest) != required or version not in {"1.0", "2.0"}:
        raise ClosureError("holdout manifest fields are invalid")
    holdout_id = identifier(manifest.get("holdout_id"), "holdout_id")
    tenant_id = identifier(manifest.get("tenant_id"), "tenant_id")
    environment = manifest.get("environment_class")
    if environment not in {"test", "sandbox", "production"}:
        raise ClosureError("holdout environment is invalid")
    if environment == "production" and version != "2.0":
        raise ClosureError("production Holdout requires Claim-specific Oracle and partition bindings")
    corpus = artifact_ref(manifest.get("corpus"), roots, "holdout corpus")
    development = require_digest(manifest.get("development_corpus_sha256"), "development_corpus_sha256")
    if corpus["sha256"] == development:
        raise ClosureError("Holdout corpus reuses development content")
    actor_sets = []
    actor_fields = ["transformation_author_ids", "executor_ids", "verifier_ids"]
    if version == "2.0":
        actor_fields.append("oracle_owner_ids")
    for field in actor_fields:
        values = manifest.get(field)
        if (not isinstance(values, list) or not values or len(values) != len(set(values)) or
                any(not isinstance(v, str) or not v for v in values)):
            raise ClosureError(f"{field} is invalid")
        actor_sets.append(set(values))
    if any(actor_sets[left] & actor_sets[right] for left in range(len(actor_sets)) for right in range(left + 1, len(actor_sets))):
        raise ClosureError("Holdout authors, executors, verifiers, and Oracle owners must be separate")
    oracle_registry_sha = None
    claim_oracle_map: list[dict[str, str]] = []
    claim_oracle_root = None
    if version == "2.0":
        development_partition = identifier(manifest.get("development_partition_id"), "development_partition_id")
        holdout_partition = identifier(manifest.get("holdout_partition_id"), "holdout_partition_id")
        if development_partition == holdout_partition:
            raise ClosureError("Holdout and development partitions must be physically distinct")
        oracle_registry_sha = require_digest(manifest.get("oracle_registry_sha256"), "oracle_registry_sha256")
        mappings = manifest.get("claim_oracle_map")
        if not isinstance(mappings, list) or not mappings or len(mappings) > 100_000:
            raise ClosureError("claim_oracle_map is invalid")
        seen_claims = set()
        for index, mapping in enumerate(mappings):
            if not isinstance(mapping, dict) or set(mapping) != {"claim_id", "oracle_id", "oracle_version"}:
                raise ClosureError("claim_oracle_map fields are invalid")
            normalized_mapping = {key: identifier(mapping.get(key), f"claim_oracle_map[{index}].{key}")
                                  for key in ("claim_id", "oracle_id", "oracle_version")}
            if normalized_mapping["claim_id"] in seen_claims:
                raise ClosureError("claim_oracle_map contains duplicate claims")
            seen_claims.add(normalized_mapping["claim_id"])
            claim_oracle_map.append(normalized_mapping)
        claim_oracle_root = canonical_digest(claim_oracle_map)
    trust = ActorTrustStore.load(trust_path)
    payload = authorization.get("payload") if isinstance(authorization, dict) else None
    custodian_id = payload.get("actor_id") if isinstance(payload, dict) else None
    if custodian_id in set().union(*actor_sets):
        raise ClosureError("Holdout custodian conflicts with author/executor/verifier")
    bindings = {"holdout_id": holdout_id, "tenant_id": tenant_id, "manifest_sha256": manifest_sha,
                "corpus_sha256": corpus["sha256"], "environment_class": environment}
    if version == "2.0":
        bindings.update({"oracle_registry_sha256": oracle_registry_sha, "claim_oracle_root": claim_oracle_root,
                         "development_partition_id": manifest["development_partition_id"],
                         "holdout_partition_id": manifest["holdout_partition_id"]})
    actor = trust.verify(authorization, "holdout-custodian", bindings)
    organizations = None
    if environment == "production":
        organizations = production_actor_groups(trust, {
            "transformation_authors": manifest["transformation_author_ids"],
            "custodian": [actor["actor_id"]], "executors": manifest["executor_ids"],
            "verifiers": manifest["verifier_ids"], "oracle_owners": manifest["oracle_owner_ids"],
        })
    record = {"schema_version": version, "holdout_id": holdout_id, "tenant_id": tenant_id,
              "environment_class": environment, "manifest_sha256": manifest_sha, "corpus": corpus,
              "sealed": True, "custodian": actor, "transformation_author_ids": manifest["transformation_author_ids"],
              "executor_ids": manifest["executor_ids"], "verifier_ids": manifest["verifier_ids"],
              **({"oracle_owner_ids": manifest["oracle_owner_ids"], "oracle_registry_sha256": oracle_registry_sha,
                  "claim_oracle_map": claim_oracle_map, "claim_oracle_root": claim_oracle_root,
                  "development_partition_id": manifest["development_partition_id"],
                  "holdout_partition_id": manifest["holdout_partition_id"]} if version == "2.0" else {}),
              **({"organization_bound": True, "independence_organizations": organizations,
                  "actor_trust_store_sha256": trust.digest} if organizations is not None else {})}
    return ClosureStore(workspace).insert("holdouts", holdout_id,
        (holdout_id, tenant_id, corpus["sha256"]), record, "HOLDOUT_SEALED")


def record_holdout_result(workspace: Path, manifest_path: Path, executor_attestation: dict[str, Any],
                          verifier_attestation: dict[str, Any], trust_path: Path,
                          roots: tuple[Path, ...]) -> dict[str, Any]:
    value, manifest_sha = load_manifest(manifest_path, roots, "holdout result manifest")
    required = {"schema_version", "result_id", "holdout_id", "tenant_id", "target_release_sha256",
                "provider_account_sha256", "execution_receipt", "decision", "claim_results",
                "started_at", "finished_at"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") not in {"1.0", "2.0"}:
        raise ClosureError("holdout result fields are invalid")
    result_id = identifier(value.get("result_id"), "result_id")
    holdout_id = identifier(value.get("holdout_id"), "holdout_id")
    tenant_id = identifier(value.get("tenant_id"), "tenant_id")
    holdout = ClosureStore(workspace).row("holdouts", holdout_id)
    if holdout["tenant_id"] != tenant_id:
        raise ClosureError("holdout result crosses tenant boundary")
    if value["schema_version"] != holdout.get("schema_version"):
        raise ClosureError("holdout result schema does not match the sealed Holdout contract")
    target_release = require_digest(value.get("target_release_sha256"), "target_release_sha256")
    provider_account = require_digest(value.get("provider_account_sha256"), "provider_account_sha256")
    execution_receipt = artifact_ref(value.get("execution_receipt"), roots, "holdout execution receipt")
    started, finished = parse_time(value.get("started_at"), "started_at"), parse_time(value.get("finished_at"), "finished_at")
    if finished <= started or finished > utc_now() + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("holdout execution time window is invalid")
    claim_results = value.get("claim_results")
    if not isinstance(claim_results, list) or not claim_results or len(claim_results) > 100_000:
        raise ClosureError("holdout claim results are invalid")
    normalized, claim_ids, outcomes, oracle_actor_ids = [], set(), [], set()
    expected_oracles = {item["claim_id"]: item for item in holdout.get("claim_oracle_map", [])}
    trust = ActorTrustStore.load(trust_path)
    if holdout.get("environment_class") == "production" and (
            trust.schema_version != "2.0" or trust.digest != holdout.get("actor_trust_store_sha256")):
        raise ClosureError("production Holdout result must use the exact sealed organization Trust Store")
    for index, item in enumerate(claim_results):
        expected_fields = ({"claim_id", "outcome", "evidence", "oracle_id", "oracle_version", "oracle_attestation"}
                           if value["schema_version"] == "2.0" else {"claim_id", "outcome", "evidence"})
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise ClosureError("holdout claim result fields are invalid")
        claim_id = identifier(item.get("claim_id"), f"claim_results[{index}].claim_id")
        if claim_id in claim_ids or item.get("outcome") not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise ClosureError("holdout claim identity/outcome is invalid")
        evidence = artifact_ref(item.get("evidence"), roots, f"holdout claim evidence {index}")
        claim_ids.add(claim_id)
        outcomes.append(item["outcome"])
        normalized_item: dict[str, Any] = {"claim_id": claim_id, "outcome": item["outcome"], "evidence": evidence}
        if value["schema_version"] == "2.0":
            mapping = expected_oracles.get(claim_id)
            oracle_id = identifier(item.get("oracle_id"), f"claim_results[{index}].oracle_id")
            oracle_version = identifier(item.get("oracle_version"), f"claim_results[{index}].oracle_version")
            if mapping is None or oracle_id != mapping["oracle_id"] or oracle_version != mapping["oracle_version"]:
                raise ClosureError("holdout Claim differs from the sealed Claim-specific Oracle map")
            oracle_bindings = {"result_id": result_id, "holdout_id": holdout_id, "tenant_id": tenant_id,
                "claim_id": claim_id, "oracle_id": oracle_id, "oracle_version": oracle_version,
                "outcome": item["outcome"], "evidence_sha256": evidence["sha256"],
                "target_release_sha256": target_release, "provider_account_sha256": provider_account,
                "oracle_registry_sha256": holdout["oracle_registry_sha256"]}
            oracle_actor = trust.verify(item.get("oracle_attestation"), "oracle-owner", oracle_bindings)
            if oracle_actor["actor_id"] not in holdout["oracle_owner_ids"]:
                raise ClosureError("Claim Oracle attestation is not owned by the sealed Holdout Oracle set")
            oracle_actor_ids.add(oracle_actor["actor_id"])
            normalized_item.update({"oracle_id": oracle_id, "oracle_version": oracle_version,
                                    "oracle": oracle_actor})
        normalized.append(normalized_item)
    if value["schema_version"] == "2.0" and claim_ids != set(expected_oracles):
        raise ClosureError("holdout result does not cover the exact sealed Claim set")
    derived = "FAIL" if "FAIL" in outcomes else ("INCONCLUSIVE" if "INCONCLUSIVE" in outcomes else "PASS")
    if value.get("decision") != derived:
        raise ClosureError("holdout decision differs from claim outcomes")
    evidence_root = canonical_digest({"holdout_corpus_sha256": holdout["corpus"]["sha256"],
        "execution_receipt_sha256": execution_receipt["sha256"], "claim_results": normalized})
    bindings = {"result_id": result_id, "holdout_id": holdout_id, "tenant_id": tenant_id,
                "manifest_sha256": manifest_sha, "evidence_root": evidence_root,
                "target_release_sha256": target_release, "provider_account_sha256": provider_account,
                "decision": derived}
    executor = trust.verify(executor_attestation, "holdout-executor", bindings)
    verifier = trust.verify(verifier_attestation, "holdout-verifier", {**bindings, "executor_id": executor["actor_id"]})
    if (executor["actor_id"] not in holdout["executor_ids"] or verifier["actor_id"] not in holdout["verifier_ids"] or
            executor["actor_id"] == verifier["actor_id"] or
            {executor["actor_id"], verifier["actor_id"]} &
            ({holdout["custodian"]["actor_id"]} | set(holdout["transformation_author_ids"]) |
             set(holdout.get("oracle_owner_ids", []))) or
            oracle_actor_ids & {executor["actor_id"], verifier["actor_id"]}):
        raise ClosureError("holdout execution actors violate the sealed custody roles")
    if holdout.get("environment_class") == "production":
        expected_orgs = holdout.get("independence_organizations", {})
        oracle_orgs = {trust.actors[item].organization_id for item in oracle_actor_ids}
        if (executor.get("organization_id") not in expected_orgs.get("executors", []) or
                verifier.get("organization_id") not in expected_orgs.get("verifiers", []) or
                executor.get("organization_id") == verifier.get("organization_id") or
                not oracle_orgs.issubset(set(expected_orgs.get("oracle_owners", [])))):
            raise ClosureError("production Holdout result violates organization-level independence")
    record = {**value, "corpus_sha256": holdout["corpus"]["sha256"], "manifest_sha256": manifest_sha,
              "execution_receipt": execution_receipt, "claim_results": normalized,
              "evidence_root": evidence_root, "executor": executor, "verifier": verifier,
              "independent": True, "sealed_holdout_consumed": True,
              "oracle_bound": value["schema_version"] == "2.0"}
    return ClosureStore(workspace).insert("holdout_results", result_id,
        (result_id, tenant_id, holdout_id, derived), record, "HOLDOUT_RESULT_RECORDED")


def plan_cutover(workspace: Path, plan_path: Path, approval: dict[str, Any], trust_path: Path,
                 roots: tuple[Path, ...]) -> dict[str, Any]:
    plan, plan_sha = load_manifest(plan_path, roots, "cutover plan")
    base = {"schema_version", "cutover_id", "tenant_id", "snapshot_id", "target_key",
            "target_release_sha256", "rollback_adapter_id", "rollback_operation", "preconditions"}
    schema_version = plan.get("schema_version")
    required = base | ({"provider", "holdout_result_id"} if schema_version == "2.0" else set())
    if set(plan) != required or schema_version not in {"1.0", "2.0"}:
        raise ClosureError("cutover plan fields are invalid")
    cutover_id = identifier(plan.get("cutover_id"), "cutover_id")
    tenant_id = identifier(plan.get("tenant_id"), "tenant_id")
    identifier(plan.get("target_key"), "target_key")
    identifier(plan.get("rollback_adapter_id"), "rollback_adapter_id")
    identifier(plan.get("rollback_operation"), "rollback_operation")
    snapshot = ClosureStore(workspace).row("snapshots", identifier(plan.get("snapshot_id"), "snapshot_id"))
    if snapshot["tenant_id"] != tenant_id:
        raise ClosureError("cutover snapshot crosses tenant boundary")
    require_digest(plan.get("target_release_sha256"), "target_release_sha256")
    provider = provider_profile(plan.get("provider"), require_exact=snapshot["environment_class"] == "production") if schema_version == "2.0" else None
    if snapshot["environment_class"] == "production" and provider is None:
        raise ClosureError("production cutover requires an exact provider/account profile")
    if provider and (provider["adapter_id"] != plan["rollback_adapter_id"] or
                     provider["rollback_operation"] != plan["rollback_operation"]):
        raise ClosureError("cutover rollback does not match the provider profile")
    if provider:
        holdout_result = ClosureStore(workspace).row(
            "holdout_results", identifier(plan.get("holdout_result_id"), "holdout_result_id"))
        if (holdout_result["tenant_id"] != tenant_id or holdout_result["decision"] != "PASS" or
                holdout_result["target_release_sha256"] != plan["target_release_sha256"] or
                holdout_result["provider_account_sha256"] != provider["account_binding_sha256"]):
            raise ClosureError("production cutover is not bound to a passing exact Holdout result")
        if (snapshot["environment_class"] == "production" and
                (holdout_result.get("schema_version") != "2.0" or
                 holdout_result.get("independent") is not True or holdout_result.get("oracle_bound") is not True)):
            raise ClosureError("production cutover requires independently verified Claim-specific Oracle Holdout evidence")
    if (not isinstance(plan.get("preconditions"), list) or not plan["preconditions"] or
            len(plan["preconditions"]) != len(set(plan["preconditions"])) or
            any(not isinstance(item, str) or not item for item in plan["preconditions"])):
        raise ClosureError("cutover preconditions are required")
    trust = ActorTrustStore.load(trust_path)
    actor = trust.verify(approval, "production-approver", {"cutover_id": cutover_id, "tenant_id": tenant_id,
                         "plan_sha256": plan_sha, "snapshot_id": snapshot["snapshot_id"],
                         "target_key": plan["target_key"]})
    if snapshot["environment_class"] == "production":
        holdout = ClosureStore(workspace).row("holdouts", holdout_result["holdout_id"])
        if (trust.schema_version != "2.0" or trust.digest != snapshot["authorization"].get("trust_store_sha256") or
                trust.digest != holdout.get("actor_trust_store_sha256") or not actor.get("organization_id")):
            raise ClosureError("production cutover approval must use the exact organization-bound Trust Store")
        forbidden = set().union(*(holdout["independence_organizations"][name]
                                  for name in ("transformation_authors", "executors", "verifiers", "oracle_owners")))
        if actor["organization_id"] in forbidden:
            raise ClosureError("production approver organization conflicts with Holdout execution or Oracle roles")
    record = {**plan, "provider": provider, "plan_sha256": plan_sha, "environment_class": snapshot["environment_class"],
              "state": "PLANNED", "fencing_token": 0,
              "approval": actor, "transitions": []}
    return ClosureStore(workspace).insert("cutovers", cutover_id,
        (cutover_id, tenant_id, plan["target_key"], "PLANNED", 0, plan_sha), record, "CUTOVER_PLANNED")


def transition_cutover(workspace: Path, cutover_id: str, expected_state: str, target_state: str,
                       fencing_token: int, receipt: dict[str, Any], attestation: dict[str, Any],
                       trust_path: Path, roots: tuple[Path, ...]) -> dict[str, Any]:
    store = ClosureStore(workspace)
    current = store.row("cutovers", cutover_id)
    if target_state not in CUTOVER_TRANSITIONS.get(expected_state, set()) or current["state"] != expected_state:
        raise ClosureError("cutover transition is not allowed")
    if not isinstance(fencing_token, int) or isinstance(fencing_token, bool) or fencing_token <= current["fencing_token"]:
        raise ClosureError("cutover fencing token must increase")
    provider_states = {"PRECHECKED", "EXECUTING", "VERIFYING", "SUCCEEDED",
                       "ROLLING_BACK", "ROLLED_BACK", "UNKNOWN"}
    if target_state in provider_states and current.get("provider"):
        evidence = provider_transition_receipt(receipt, roots, current, target_state)
        used_receipt_ids = {item.get("receipt", {}).get("receipt_id") for item in current.get("transitions", [])}
        used_requests = {item.get("receipt", {}).get("request_sha256") for item in current.get("transitions", [])}
        if evidence.get("receipt_id") in used_receipt_ids or evidence.get("request_sha256") in used_requests:
            raise ClosureError("provider receipt/request is already bound to another cutover transition")
    else:
        evidence = artifact_ref(receipt, roots, "cutover receipt")
    role = TRANSITION_ROLES[target_state]
    trust = ActorTrustStore.load(trust_path)
    actor = trust.verify(attestation, role, {"cutover_id": cutover_id, "tenant_id": current["tenant_id"],
                         "expected_state": expected_state, "target_state": target_state,
                         "fencing_token": fencing_token, "receipt_sha256": evidence["sha256"]})
    if target_state in {"SUCCEEDED", "ROLLED_BACK"} and actor["actor_id"] == current["approval"]["actor_id"]:
        raise ClosureError("cutover final verifier must be independent from approver")
    if current.get("environment_class") == "production":
        if (trust.schema_version != "2.0" or trust.digest != current["approval"].get("trust_store_sha256") or
                not actor.get("organization_id")):
            raise ClosureError("production transition must use the approved organization Trust Store")
        if target_state in {"SUCCEEDED", "ROLLED_BACK"}:
            conflicted_orgs = {current["approval"].get("organization_id")}
            conflicted_orgs.update(item.get("actor", {}).get("organization_id")
                                   for item in current.get("transitions", [])
                                   if item.get("to") in {"PRECHECKED", "EXECUTING", "ROLLING_BACK", "UNKNOWN"})
            if actor["organization_id"] in conflicted_orgs:
                raise ClosureError("cutover final verifier organization conflicts with approval or execution")
    transition = {"from": expected_state, "to": target_state, "fencing_token": fencing_token,
                  "receipt": evidence, "actor": actor, "recorded_at": now_text()}
    record = {**current, "state": target_state, "fencing_token": fencing_token,
              "transitions": [*current["transitions"], transition]}
    return store.transition_cutover(cutover_id, expected_state, target_state, fencing_token, record)


def production_telemetry_profile(value: Any, cutover: dict[str, Any], max_gap_seconds: int) -> dict[str, Any]:
    required = {"schema_version", "monitor_id", "provider_account_sha256", "metrics_source_sha256",
                "collection_interval_seconds", "raw_evidence_required"}
    provider = cutover.get("provider")
    if (not isinstance(value, dict) or set(value) != required or value.get("schema_version") != "1.0" or
            value.get("raw_evidence_required") is not True or not isinstance(provider, dict)):
        raise ClosureError("production telemetry profile is invalid")
    monitor_id = identifier(value.get("monitor_id"), "telemetry monitor_id")
    account = require_digest(value.get("provider_account_sha256"), "telemetry provider_account_sha256")
    source = require_digest(value.get("metrics_source_sha256"), "telemetry metrics_source_sha256")
    interval = value.get("collection_interval_seconds")
    if (account != provider.get("account_binding_sha256") or not isinstance(interval, int) or
            isinstance(interval, bool) or interval <= 0 or interval > max_gap_seconds):
        raise ClosureError("production telemetry profile differs from Provider account or gap policy")
    return {"schema_version": "1.0", "monitor_id": monitor_id, "provider_account_sha256": account,
            "metrics_source_sha256": source, "collection_interval_seconds": interval,
            "raw_evidence_required": True}


def telemetry_observation_receipt(value: Any, roots: tuple[Path, ...], current: dict[str, Any],
                                  sequence: int, observed_at: str, metrics: dict[str, Any]) -> dict[str, Any]:
    outer = artifact_ref(value, roots, "telemetry receipt")
    path = confined(Path(value["path"]), roots, "telemetry receipt")
    try:
        payload = json.loads(read_regular(path, MAX_MANIFEST_BYTES, "telemetry receipt"))
    except json.JSONDecodeError as exc:
        raise ClosureError("telemetry receipt is invalid JSON") from exc
    required = {"schema_version", "monitor_id", "run_id", "sequence", "observed_at",
                "provider_account_sha256", "metrics_source_sha256", "source_event_id", "metrics"}
    profile = current.get("telemetry_profile")
    if (not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != "1.0" or
            not isinstance(profile, dict) or payload.get("monitor_id") != profile.get("monitor_id") or
            payload.get("run_id") != current.get("run_id") or payload.get("sequence") != sequence or
            payload.get("observed_at") != observed_at or
            payload.get("provider_account_sha256") != profile.get("provider_account_sha256") or
            payload.get("metrics_source_sha256") != profile.get("metrics_source_sha256") or
            payload.get("metrics") != metrics):
        raise ClosureError("telemetry receipt differs from the exact soak observation tuple")
    source_event_id = identifier(payload.get("source_event_id"), "telemetry source_event_id")
    return {**outer, "monitor_id": profile["monitor_id"], "source_event_id": source_event_id,
            "provider_account_sha256": profile["provider_account_sha256"],
            "metrics_source_sha256": profile["metrics_source_sha256"]}


def start_soak(workspace: Path, cutover_id: str, run_id: str, environment_class: str,
               started_at: str, required_seconds: int, max_gap_seconds: int,
               minimum_availability: float = 0.0, maximum_error_rate: float = 1.0,
               minimum_observations: int = 1,
               clock: SystemEvidenceClock | ControlledTestClock | None = None,
               telemetry_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    selected_clock = evidence_clock(clock)
    cutover = ClosureStore(workspace).row("cutovers", cutover_id)
    if cutover["state"] != "SUCCEEDED":
        raise ClosureError("soak run requires a successfully verified cutover")
    if environment_class not in {"test", "sandbox", "production"}:
        raise ClosureError("soak environment is invalid")
    started = parse_time(started_at, "started_at")
    if started > selected_clock.now() + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("soak start is future-dated")
    if cutover.get("environment_class", environment_class) != environment_class:
        raise ClosureError("soak environment differs from the cutover snapshot")
    if (not isinstance(required_seconds, int) or required_seconds <= 0 or
            not isinstance(max_gap_seconds, int) or max_gap_seconds <= 0 or max_gap_seconds > required_seconds):
        raise ClosureError("soak duration/gap policy is invalid")
    if (not isinstance(minimum_availability, (int, float)) or isinstance(minimum_availability, bool) or
            not 0 <= minimum_availability <= 1 or
            not isinstance(maximum_error_rate, (int, float)) or isinstance(maximum_error_rate, bool) or
            not 0 <= maximum_error_rate <= 1 or
            not isinstance(minimum_observations, int) or isinstance(minimum_observations, bool) or
            minimum_observations < 1 or minimum_observations > MAX_SOAK_OBSERVATIONS):
        raise ClosureError("soak acceptance profile is invalid")
    if environment_class == "production" and required_seconds < PRODUCTION_MIN_SOAK_SECONDS:
        raise ClosureError("production soak window must be at least seven days")
    if environment_class == "production":
        required_observations = (required_seconds + max_gap_seconds - 1) // max_gap_seconds
        try:
            holdout_result = ClosureStore(workspace).row(
                "holdout_results", identifier(cutover.get("holdout_result_id"), "holdout_result_id"))
        except ClosureError as exc:
            raise ClosureError("production soak requires an exact passing Holdout result") from exc
        provider = cutover.get("provider")
        if (not isinstance(provider, dict) or holdout_result.get("decision") != "PASS" or
                holdout_result.get("tenant_id") != cutover["tenant_id"] or
                holdout_result.get("target_release_sha256") != cutover.get("target_release_sha256") or
                holdout_result.get("provider_account_sha256") != provider.get("account_binding_sha256")):
            raise ClosureError("production soak Holdout result differs from the cutover tuple")
        provider_profile(provider, require_exact=True)
        if (holdout_result.get("schema_version") != "2.0" or holdout_result.get("independent") is not True or
                holdout_result.get("oracle_bound") is not True):
            raise ClosureError("production soak requires independent Claim-specific Oracle Holdout evidence")
        holdout = ClosureStore(workspace).row("holdouts", holdout_result["holdout_id"])
        if holdout.get("organization_bound") is not True:
            raise ClosureError("production soak requires organization-independent Holdout evidence")
        if (max_gap_seconds > PRODUCTION_MAX_GAP_SECONDS or
                minimum_observations < required_observations or minimum_availability < 0.99 or
                maximum_error_rate > 0.01):
            raise ClosureError("production soak requires exact provider binding and conservative telemetry policy")
        last_transition = cutover.get("transitions", [])[-1] if cutover.get("transitions") else None
        if (not isinstance(last_transition, dict) or last_transition.get("to") != "SUCCEEDED" or
                started < parse_time(last_transition.get("recorded_at"), "cutover succeeded_at") or
                (selected_clock.now() - started).total_seconds() > PRODUCTION_OBSERVATION_SKEW_SECONDS):
            raise ClosureError("production soak must start after cutover and near real time")
        normalized_telemetry = production_telemetry_profile(telemetry_profile, cutover, max_gap_seconds)
    else:
        if telemetry_profile is not None:
            raise ClosureError("production telemetry profile cannot be attached to a non-production soak")
        normalized_telemetry = None
    clock_mode = selected_clock.mode
    evidence_class = ("production-pending" if environment_class == "production" and clock_mode == "system"
                      else "engineering-only")
    record = {"schema_version": "1.0", "run_id": identifier(run_id, "run_id"), "cutover_id": cutover_id,
              "tenant_id": cutover["tenant_id"], "environment_class": environment_class, "state": "RUNNING",
              "started_at": started_at, "required_seconds": required_seconds, "max_gap_seconds": max_gap_seconds,
              "minimum_availability": float(minimum_availability),
              "maximum_error_rate": float(maximum_error_rate), "minimum_observations": minimum_observations,
              "last_sequence": 0, "last_observed_at": None, "observations": [], "critical_failures": 0,
              "total_requests": 0, "total_errors": 0, "minimum_observed_availability": 1.0,
              "observer_ids": [], "clock_mode": clock_mode, "evidence_class": evidence_class,
              "production_protocol_simulated": environment_class == "production" and clock_mode != "system",
              "real_seven_day_elapsed": False,
              **({"telemetry_profile": normalized_telemetry,
                  "telemetry_profile_sha256": canonical_digest(normalized_telemetry)}
                 if normalized_telemetry is not None else {})}
    return ClosureStore(workspace).insert("soak_runs", run_id,
        (run_id, cutover_id, environment_class, "RUNNING", 0, None), record, "SOAK_STARTED")


def observe_soak(workspace: Path, run_id: str, sequence: int, observed_at: str,
                  metrics: dict[str, Any], attestation: dict[str, Any], trust_path: Path,
                  clock: SystemEvidenceClock | ControlledTestClock | None = None,
                  telemetry_receipt: dict[str, Any] | None = None,
                  roots: tuple[Path, ...] = ()) -> dict[str, Any]:
    selected_clock = evidence_clock(clock)
    store = ClosureStore(workspace)
    current = store.row("soak_runs", run_id)
    if current.get("clock_mode", "system") != selected_clock.mode:
        raise ClosureError("soak evidence clock mode cannot change during a run")
    if len(current.get("observations", [])) >= MAX_SOAK_OBSERVATIONS:
        raise ClosureError("soak observation budget is exhausted")
    if set(metrics) != {"requests", "errors", "critical_failures", "availability"}:
        raise ClosureError("soak metrics fields are invalid")
    requests, errors, critical, availability = (metrics[key] for key in ("requests", "errors", "critical_failures", "availability"))
    if (not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in (requests, errors, critical)) or
            errors > requests or not isinstance(availability, (int, float)) or isinstance(availability, bool) or not 0 <= availability <= 1):
        raise ClosureError("soak metrics values are invalid")
    observed = parse_time(observed_at, "observed_at")
    previous = parse_time(current["last_observed_at"] or current["started_at"], "previous observation")
    if observed <= previous or (observed - previous).total_seconds() > current["max_gap_seconds"]:
        raise ClosureError("soak observation time is non-monotonic or exceeds policy")
    now = selected_clock.now()
    if observed > now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("soak observation is future-dated")
    if (current["environment_class"] == "production" and
            abs((now - observed).total_seconds()) > PRODUCTION_OBSERVATION_SKEW_SECONDS):
        raise ClosureError("production soak observations must be recorded near real time")
    receipt = None
    if current["environment_class"] == "production":
        if telemetry_receipt is None or not roots:
            raise ClosureError("production soak observation requires a raw telemetry receipt")
        receipt = telemetry_observation_receipt(telemetry_receipt, roots, current, sequence, observed_at, metrics)
        metrics_sha = canonical_digest({"metrics": metrics, "telemetry_receipt_sha256": receipt["sha256"],
                                        "telemetry_profile_sha256": current["telemetry_profile_sha256"]})
    else:
        if telemetry_receipt is not None:
            raise ClosureError("non-production soak cannot import production telemetry evidence")
        metrics_sha = canonical_digest(metrics)
    actor = ActorTrustStore.load(trust_path).verify(attestation, "operations-owner",
        {"run_id": run_id, "sequence": sequence, "observed_at": observed_at, "metrics_sha256": metrics_sha})
    if current["environment_class"] == "production":
        trust = ActorTrustStore.load(trust_path)
        cutover = store.row("cutovers", current["cutover_id"])
        if (trust.schema_version != "2.0" or trust.digest != cutover["approval"].get("trust_store_sha256") or
                not actor.get("organization_id")):
            raise ClosureError("production soak observation must use the approved organization Trust Store")
    observation = {"sequence": sequence, "observed_at": observed_at, "metrics": metrics,
                   "metrics_sha256": metrics_sha, "actor": actor,
                   **({"telemetry_receipt": receipt} if receipt is not None else {})}
    observer_ids = list(current.get("observer_ids", []))
    if actor["actor_id"] not in observer_ids:
        observer_ids.append(actor["actor_id"])
    record = {**current, "last_sequence": sequence, "last_observed_at": observed_at,
              "observations": [*current["observations"], observation],
              "critical_failures": current["critical_failures"] + critical,
              "total_requests": current.get("total_requests", 0) + requests,
              "total_errors": current.get("total_errors", 0) + errors,
              "minimum_observed_availability": min(current.get("minimum_observed_availability", 1.0),
                                                   float(availability)),
              "observer_ids": observer_ids}
    return store.update_soak(run_id, sequence, observed_at, record)


def soak_evidence_root(record: dict[str, Any]) -> str:
    observations = [{"sequence": item["sequence"], "observed_at": item["observed_at"],
                     "metrics_sha256": item["metrics_sha256"],
                     "actor_sha256": item["actor"]["payload_sha256"]}
                    for item in record["observations"]]
    return canonical_digest({"run_id": record["run_id"], "cutover_id": record["cutover_id"],
        "started_at": record["started_at"], "required_seconds": record["required_seconds"],
        "max_gap_seconds": record["max_gap_seconds"],
        "minimum_availability": record.get("minimum_availability", 0.0),
        "maximum_error_rate": record.get("maximum_error_rate", 1.0),
        "minimum_observations": record.get("minimum_observations", 1),
        "clock_mode": record.get("clock_mode", "system"),
        "production_protocol_simulated": record.get("production_protocol_simulated", False),
        "telemetry_profile_sha256": record.get("telemetry_profile_sha256"),
        "observations": observations})


def soak_status(workspace: Path, run_id: str,
                clock: SystemEvidenceClock | ControlledTestClock | None = None) -> dict[str, Any]:
    """Return a clock-bound watchdog view without mutating soak evidence."""
    selected_clock = evidence_clock(clock)
    current = ClosureStore(workspace).row("soak_runs", identifier(run_id, "run_id"))
    if current.get("clock_mode", "system") != selected_clock.mode:
        raise ClosureError("soak evidence clock mode cannot change during a run")
    now = selected_clock.now()
    started = parse_time(current["started_at"], "started_at")
    heartbeat = parse_time(current.get("last_observed_at") or current["started_at"], "heartbeat base")
    deadline = heartbeat + timedelta(seconds=current["max_gap_seconds"])
    running = current.get("state") == "RUNNING"
    return {
        "schema_version": "1.0", "run_id": current["run_id"], "state": current["state"],
        "clock_mode": selected_clock.mode,
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "next_sequence": current["last_sequence"] + 1 if running else None,
        "heartbeat_deadline": deadline.isoformat().replace("+00:00", "Z"),
        "heartbeat_overdue": bool(running and now > deadline),
        "elapsed_seconds": max(0, int((now - started).total_seconds())),
        "remaining_required_seconds": max(0, int(current["required_seconds"] - (now - started).total_seconds())),
        "evidence_class": current.get("evidence_class", "engineering-only"),
        "real_seven_day_elapsed": current.get("real_seven_day_elapsed", False),
    }


def expire_soak(workspace: Path, run_id: str, observed_at: str,
                attestation: dict[str, Any], trust_path: Path,
                clock: SystemEvidenceClock | ControlledTestClock | None = None) -> dict[str, Any]:
    """Fail a running soak atomically after a missed heartbeat deadline."""
    selected_clock = evidence_clock(clock)
    store = ClosureStore(workspace)
    current = store.row("soak_runs", identifier(run_id, "run_id"))
    status = soak_status(workspace, run_id, selected_clock)
    if current.get("state") != "RUNNING" or status["heartbeat_overdue"] is not True:
        raise ClosureError("soak heartbeat is not overdue")
    observed = parse_time(observed_at, "observed_at")
    now = selected_clock.now()
    deadline = parse_time(status["heartbeat_deadline"], "heartbeat_deadline")
    if observed <= deadline or observed > now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("soak expiration time does not prove a missed heartbeat")
    if (current["environment_class"] == "production" and
            abs((now - observed).total_seconds()) > PRODUCTION_OBSERVATION_SKEW_SECONDS):
        raise ClosureError("production soak expiration must be recorded near real time")
    sequence = current["last_sequence"] + 1
    evidence_root = soak_evidence_root(current)
    payload = {"run_id": run_id, "sequence": sequence, "observed_at": observed_at,
               "target_state": "FAILED", "evidence_root": evidence_root,
               "heartbeat_deadline": status["heartbeat_deadline"], "reason": "HEARTBEAT_TIMEOUT"}
    trust = ActorTrustStore.load(trust_path)
    actor = trust.verify(attestation, "production-verifier", payload)
    cutover = store.row("cutovers", current["cutover_id"])
    if actor["actor_id"] in set(current.get("observer_ids", [])) | {cutover["approval"]["actor_id"]}:
        raise ClosureError("soak timeout verifier must be independent from observers and cutover approver")
    if current["environment_class"] == "production":
        observer_orgs = {item.get("actor", {}).get("organization_id") for item in current["observations"]}
        if (trust.schema_version != "2.0" or trust.digest != cutover["approval"].get("trust_store_sha256") or
                not actor.get("organization_id") or
                actor["organization_id"] in observer_orgs | {cutover["approval"].get("organization_id")}):
            raise ClosureError("soak timeout verifier organization conflicts with observers or approver")
    record = {**current, "state": "FAILED", "last_sequence": sequence, "last_observed_at": observed_at,
              "duration_seconds": max(0, (observed - parse_time(current["started_at"], "started_at")).total_seconds()),
              "evidence_root": evidence_root, "final_verifier": actor,
              "terminal_reason": "HEARTBEAT_TIMEOUT", "heartbeat_deadline": status["heartbeat_deadline"],
              "real_seven_day_elapsed": False,
              "evidence_class": ("production" if current["environment_class"] == "production" and
                                   selected_clock.mode == "system" else "engineering-only")}
    return store.update_soak(run_id, sequence, observed_at, record, "FAILED")


def finish_soak(workspace: Path, run_id: str, sequence: int, observed_at: str,
                attestation: dict[str, Any], trust_path: Path,
                clock: SystemEvidenceClock | ControlledTestClock | None = None) -> dict[str, Any]:
    selected_clock = evidence_clock(clock)
    store = ClosureStore(workspace)
    current = store.row("soak_runs", run_id)
    if current.get("clock_mode", "system") != selected_clock.mode:
        raise ClosureError("soak evidence clock mode cannot change during a run")
    observed = parse_time(observed_at, "observed_at")
    if current["last_observed_at"] is None:
        raise ClosureError("soak run has no observations")
    last_observed = parse_time(current["last_observed_at"], "last_observed_at")
    if observed <= last_observed or (observed - last_observed).total_seconds() > current["max_gap_seconds"]:
        raise ClosureError("final soak observation is non-monotonic or exceeds gap policy")
    now = selected_clock.now()
    if observed > now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("final soak observation is future-dated")
    if (current["environment_class"] == "production" and
            abs((now - observed).total_seconds()) > PRODUCTION_OBSERVATION_SKEW_SECONDS):
        raise ClosureError("production soak must finish near real time")
    duration = (observed - parse_time(current["started_at"], "started_at")).total_seconds()
    total_requests = current.get("total_requests", 0)
    error_rate = current.get("total_errors", 0) / total_requests if total_requests else 1.0
    passed = (duration >= current["required_seconds"] and current["critical_failures"] == 0 and
              len(current["observations"]) >= current.get("minimum_observations", 1) and
              current.get("minimum_observed_availability", 0.0) >= current.get("minimum_availability", 0.0) and
              error_rate <= current.get("maximum_error_rate", 1.0))
    target = "PASSED" if passed else "FAILED"
    evidence_root = soak_evidence_root(current)
    actor = ActorTrustStore.load(trust_path).verify(attestation, "production-verifier",
        {"run_id": run_id, "sequence": sequence, "observed_at": observed_at,
         "target_state": target, "evidence_root": evidence_root})
    cutover = store.row("cutovers", current["cutover_id"])
    if actor["actor_id"] in set(current.get("observer_ids", [])) | {cutover["approval"]["actor_id"]}:
        raise ClosureError("final soak verifier must be independent from observers and cutover approver")
    if current["environment_class"] == "production":
        trust = ActorTrustStore.load(trust_path)
        observer_orgs = {item.get("actor", {}).get("organization_id") for item in current["observations"]}
        if (trust.schema_version != "2.0" or trust.digest != cutover["approval"].get("trust_store_sha256") or
                not actor.get("organization_id") or
                actor["organization_id"] in observer_orgs | {cutover["approval"].get("organization_id")}):
            raise ClosureError("final soak verifier organization conflicts with observers or approver")
    record = {**current, "state": target, "last_sequence": sequence, "last_observed_at": observed_at,
              "duration_seconds": duration, "error_rate": error_rate, "evidence_root": evidence_root,
              "final_verifier": actor,
              "real_seven_day_elapsed": bool(current["environment_class"] == "production" and
                                               selected_clock.mode == "system" and
                                               duration >= PRODUCTION_MIN_SOAK_SECONDS),
              "evidence_class": ("production" if current["environment_class"] == "production" and
                                  selected_clock.mode == "system" else "engineering-only")}
    return store.update_soak(run_id, sequence, observed_at, record, target)


def import_assessment(workspace: Path, report_path: Path, attestation: dict[str, Any],
                      trust_path: Path, roots: tuple[Path, ...], *,
                      authority_policy_path: Path | None = None,
                      authority_approval: dict[str, Any] | None = None,
                      internal_trust_path: Path | None = None) -> dict[str, Any]:
    report, report_sha = load_manifest(report_path, roots, "independent assessment")
    base = {"schema_version", "assessment_id", "tenant_id", "scope", "decision", "evidence_root",
            "limitations", "issued_at", "expires_at"}
    schema_version = report.get("schema_version")
    required = base | ({"run_id", "cutover_id", "target_release_sha256", "provider_account_sha256"}
                       if schema_version == "2.0" else set())
    if set(report) != required or schema_version not in {"1.0", "2.0"} or report.get("decision") not in {
            "NOT_CERTIFIED", "INCONCLUSIVE", "CERTIFIED"}:
        raise ClosureError("independent assessment fields/decision are invalid")
    assessment_id = identifier(report.get("assessment_id"), "assessment_id")
    tenant_id = identifier(report.get("tenant_id"), "tenant_id")
    require_digest(report.get("evidence_root"), "evidence_root")
    issued, expires, observed = (parse_time(report.get("issued_at"), "issued_at"),
                                 parse_time(report.get("expires_at"), "expires_at"), utc_now())
    if not issued <= observed < expires:
        raise ClosureError("assessment validity window is invalid")
    if (not isinstance(report.get("scope"), str) or not report["scope"] or
            not isinstance(report.get("limitations"), list) or
            any(not isinstance(item, str) for item in report["limitations"])):
        raise ClosureError("assessment scope/limitations are invalid")
    payload = attestation.get("payload") if isinstance(attestation, dict) else None
    actor_id = payload.get("actor_id") if isinstance(payload, dict) else None
    store = ClosureStore(workspace)
    conflicts, conflict_organizations, eligible_soaks = [], [], {}
    connection = store.connect()
    try:
        for table, fields in (("snapshots", ("authorization",)), ("holdouts", ("custodian",)),
                              ("holdout_results", ("executor", "verifier")),
                              ("cutovers", ("approval",)), ("soak_runs", ("final_verifier",))):
            for row in connection.execute(f"SELECT record_json FROM {table}").fetchall():
                value = json.loads(row[0])
                if value.get("tenant_id") != tenant_id:
                    continue
                if table == "soak_runs" and value.get("state") == "PASSED":
                    eligible_soaks[value.get("evidence_root")] = value
                for field in fields:
                    if isinstance(value.get(field), dict):
                        conflicts.append(value[field].get("actor_id"))
                        conflict_organizations.append(value[field].get("organization_id"))
                if table == "holdouts":
                    conflicts.extend(value.get("executor_ids", []))
                    conflicts.extend(value.get("verifier_ids", []))
                    conflicts.extend(value.get("oracle_owner_ids", []))
                if table == "cutovers":
                    conflicts.extend(item.get("actor", {}).get("actor_id") for item in value.get("transitions", []))
                    conflict_organizations.extend(item.get("actor", {}).get("organization_id")
                                                  for item in value.get("transitions", []))
                if table == "soak_runs":
                    conflicts.extend(value.get("observer_ids", []))
                    conflict_organizations.extend(item.get("actor", {}).get("organization_id")
                                                  for item in value.get("observations", []))
    finally:
        connection.close()
    matched_soak = eligible_soaks.get(report["evidence_root"])
    if matched_soak is None:
        raise ClosureError("assessment evidence_root is not a PASSED tenant soak run")
    external_authority_record = None
    assessment_trust = ActorTrustStore.load(trust_path)
    if matched_soak.get("environment_class") == "production":
        cutover = store.row("cutovers", matched_soak["cutover_id"])
        provider = cutover.get("provider")
        if (schema_version != "2.0" or report.get("run_id") != matched_soak["run_id"] or
                report.get("cutover_id") != cutover["cutover_id"] or
                report.get("target_release_sha256") != cutover["target_release_sha256"] or
                not isinstance(provider, dict) or
                report.get("provider_account_sha256") != provider.get("account_binding_sha256")):
            raise ClosureError("production assessment is not bound to the exact run, release, and provider account")
        require_digest(report.get("target_release_sha256"), "target_release_sha256")
        require_digest(report.get("provider_account_sha256"), "provider_account_sha256")
        if authority_policy_path is None or authority_approval is None or internal_trust_path is None:
            raise ClosureError("production assessment requires a digest-pinned external certification authority")
        try:
            assessment_trust, external_authority_record = external_authority.authorize(
                authority_policy_path, authority_approval, internal_trust_path, trust_path,
                tenant_id, "independent-certification", roots)
        except external_authority.ExternalAuthorityError as exc:
            raise ClosureError(str(exc)) from exc
    if actor_id in conflicts:
        raise ClosureError("independent certifier conflicts with execution/approval roles")
    actor = assessment_trust.verify(attestation, "independent-certifier",
        {"assessment_id": assessment_id, "tenant_id": tenant_id, "report_sha256": report_sha,
         "evidence_root": report["evidence_root"], "decision": report["decision"]})
    if (matched_soak.get("environment_class") == "production" and
            (actor.get("authority_class") != "certification-body" or
             actor.get("organization_id") in set(conflict_organizations))):
        raise ClosureError("production certifier organization is not independent from execution")
    record = {**report, "report_sha256": report_sha, "certifier": actor,
              "local_effect": "EXTERNAL_EVIDENCE_IMPORTED", "certified": False,
              "external_authority_authorized": external_authority_record is not None,
              **({"external_authority": external_authority_record}
                 if external_authority_record is not None else {}),
              "boundary": "An imported assessment cannot enable repository certification."}
    return store.insert("assessments", assessment_id,
        (assessment_id, tenant_id, report["evidence_root"]), record, "ASSESSMENT_IMPORTED")


def readiness(workspace: Path, tenant_id: str) -> dict[str, Any]:
    store = ClosureStore(workspace)
    records: dict[str, list[dict[str, Any]]] = {}
    connection = store.connect()
    try:
        for table in ("snapshots", "holdouts", "holdout_results", "cutovers", "soak_runs", "assessments"):
            rows = [json.loads(row[0]) for row in connection.execute(
                f"SELECT record_json FROM {table} WHERE tenant_id=?" if table != "soak_runs" else
                "SELECT record_json FROM soak_runs", (tenant_id,) if table != "soak_runs" else ()).fetchall()]
            if table == "soak_runs":
                rows = [row for row in rows if row.get("tenant_id") == tenant_id]
            records[table] = rows
    finally:
        connection.close()

    counts = {table: len(rows) for table, rows in records.items()}
    integrity_findings = store.verify_event_chain()
    if not any(counts.values()):
        decision = "NOT_RUN"
        return {"schema_version": "1.0", "tenant_id": tenant_id, "decision": decision,
                "certified": False, "counts": counts, "findings": integrity_findings,
                "selected_chain": None, "evaluated_chains": 0, "ignored_historical_chains": 0,
                "external_runtime_status": "NOT_RUN", "production_status": "NOT_CERTIFIED"}

    snapshots = {row.get("snapshot_id"): row for row in records["snapshots"]}
    holdouts = {row.get("holdout_id"): row for row in records["holdouts"]}
    results = {row.get("result_id"): row for row in records["holdout_results"]}
    cutovers = {row.get("cutover_id"): row for row in records["cutovers"]}

    def evaluate(soak: dict[str, Any]) -> dict[str, Any]:
        chain_findings: list[str] = []
        cutover = cutovers.get(soak.get("cutover_id"))
        if cutover is None or cutover.get("tenant_id") != tenant_id:
            chain_findings.append("soak does not resolve to a same-tenant cutover")
        elif cutover.get("state") != "SUCCEEDED":
            chain_findings.append("cutover has not reached SUCCEEDED")

        snapshot = snapshots.get(cutover.get("snapshot_id")) if cutover else None
        if snapshot is None or snapshot.get("tenant_id") != tenant_id:
            chain_findings.append("cutover does not resolve to a same-tenant snapshot")

        result = results.get(cutover.get("holdout_result_id")) if cutover else None
        if cutover and result is None and cutover.get("schema_version") == "1.0":
            legacy = [row for row in records["holdout_results"]
                      if row.get("target_release_sha256") == cutover.get("target_release_sha256")]
            if len(legacy) == 1:
                result = legacy[0]
            else:
                chain_findings.append("legacy cutover does not resolve exactly one Holdout result")
        if result is None or result.get("tenant_id") != tenant_id:
            chain_findings.append("cutover does not resolve to a same-tenant Holdout result")
        elif result.get("decision") != "PASS" or result.get("independent") is not True:
            chain_findings.append("independent Holdout result has not passed")

        holdout = holdouts.get(result.get("holdout_id")) if result else None
        if holdout is None or holdout.get("tenant_id") != tenant_id:
            chain_findings.append("Holdout result does not resolve to a same-tenant sealed Holdout")

        if soak.get("state") != "PASSED":
            chain_findings.append("soak run has not reached PASSED")
        evidence_root = soak.get("evidence_root")
        matching_assessments = [row for row in records["assessments"]
                                if row.get("evidence_root") == evidence_root]
        valid_assessments = []
        for assessment in matching_assessments:
            try:
                unexpired = parse_time(assessment.get("expires_at"), "assessment expires_at") > utc_now()
            except ClosureError:
                unexpired = False
            if unexpired and assessment.get("decision") != "INCONCLUSIVE":
                valid_assessments.append(assessment)
        if not valid_assessments:
            chain_findings.append("soak evidence lacks a current conclusive independent assessment")

        production = bool(
            snapshot and holdout and result and cutover and
            snapshot.get("environment_class") == "production" and
            holdout.get("environment_class") == "production" and
            cutover.get("environment_class") == "production" and
            soak.get("environment_class") == "production" and soak.get("clock_mode") == "system" and
            soak.get("real_seven_day_elapsed") is True and soak.get("evidence_class") == "production")
        if production:
            provider = cutover.get("provider")
            if (cutover.get("schema_version") != "2.0" or result.get("schema_version") != "2.0" or
                    result.get("oracle_bound") is not True or not isinstance(provider, dict) or
                    result.get("target_release_sha256") != cutover.get("target_release_sha256") or
                    result.get("provider_account_sha256") != provider.get("account_binding_sha256")):
                chain_findings.append("production chain lacks exact release, Provider, and Claim-Oracle bindings")
            positive = [row for row in valid_assessments if row.get("decision") == "CERTIFIED" and
                        row.get("external_authority_authorized") is True and
                        row.get("schema_version") == "2.0" and row.get("run_id") == soak.get("run_id") and
                        row.get("cutover_id") == cutover.get("cutover_id") and
                        row.get("target_release_sha256") == cutover.get("target_release_sha256") and
                        isinstance(provider, dict) and
                        row.get("provider_account_sha256") == provider.get("account_binding_sha256")]
            if not positive:
                chain_findings.append("production soak evidence lacks exact positive independent assessment coverage")

        return {"run_id": soak.get("run_id"), "production": production, "findings": chain_findings,
                "chain": {"snapshot_id": snapshot.get("snapshot_id") if snapshot else None,
                          "holdout_id": holdout.get("holdout_id") if holdout else None,
                          "result_id": result.get("result_id") if result else None,
                          "cutover_id": cutover.get("cutover_id") if cutover else None,
                          "run_id": soak.get("run_id"),
                          "assessment_ids": sorted(row["assessment_id"] for row in valid_assessments)}}

    evaluations = [evaluate(soak) for soak in records["soak_runs"]]
    eligible = [item for item in evaluations if not item["findings"]]
    eligible.sort(key=lambda item: (item["production"], item["run_id"] or ""), reverse=True)
    selected = eligible[0] if eligible else (min(evaluations, key=lambda item: len(item["findings"]))
                                             if evaluations else None)
    findings = [*integrity_findings, *(selected["findings"] if selected and not eligible else [])]
    if not evaluations:
        findings.append("tenant has no soak evidence chain")
    if integrity_findings or not eligible:
        decision = "BLOCKED"
    else:
        decision = "READY_FOR_EXTERNAL_GATE" if selected["production"] else "LOCAL_TOOLKIT_PASS"
    return {"schema_version": "1.0", "tenant_id": tenant_id, "decision": decision,
            "certified": False, "counts": counts, "findings": findings,
            "selected_chain": selected["chain"] if selected else None,
            "evaluated_chains": len(evaluations),
            "ignored_historical_chains": max(0, len(evaluations) - (1 if selected else 0)),
            "external_runtime_status": "NOT_RUN" if decision != "READY_FOR_EXTERNAL_GATE" else "EVIDENCE_IMPORTED",
            "production_status": "NOT_CERTIFIED"}


def json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(read_regular(path, MAX_MANIFEST_BYTES, label))
    except json.JSONDecodeError as exc:
        raise ClosureError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"{label} must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def evidence_command(name: str) -> argparse.ArgumentParser:
        command = sub.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--trust-store", type=Path, required=True)
        command.add_argument("--evidence-root", type=Path, action="append", required=True)
        return command

    snapshot = evidence_command("register-snapshot")
    snapshot.add_argument("--manifest", type=Path, required=True)
    snapshot.add_argument("--authorization", type=Path, required=True)
    holdout = evidence_command("register-holdout")
    holdout.add_argument("--manifest", type=Path, required=True)
    holdout.add_argument("--authorization", type=Path, required=True)
    holdout_result = evidence_command("record-holdout-result")
    holdout_result.add_argument("--manifest", type=Path, required=True)
    holdout_result.add_argument("--executor-attestation", type=Path, required=True)
    holdout_result.add_argument("--verifier-attestation", type=Path, required=True)
    cutover = evidence_command("plan-cutover")
    cutover.add_argument("--plan", type=Path, required=True)
    cutover.add_argument("--approval", type=Path, required=True)
    transition = evidence_command("transition-cutover")
    transition.add_argument("--cutover-id", required=True)
    transition.add_argument("--expected-state", required=True)
    transition.add_argument("--target-state", required=True)
    transition.add_argument("--fencing-token", type=int, required=True)
    transition.add_argument("--receipt", type=Path, required=True)
    transition.add_argument("--attestation", type=Path, required=True)
    start = sub.add_parser("start-soak")
    start.add_argument("--workspace", type=Path, required=True)
    start.add_argument("--cutover-id", required=True)
    start.add_argument("--run-id", required=True)
    start.add_argument("--environment-class", choices=("test", "sandbox", "production"), required=True)
    start.add_argument("--started-at", required=True)
    start.add_argument("--required-seconds", type=int, required=True)
    start.add_argument("--max-gap-seconds", type=int, required=True)
    start.add_argument("--minimum-availability", type=float, default=0.0)
    start.add_argument("--maximum-error-rate", type=float, default=1.0)
    start.add_argument("--minimum-observations", type=int, default=1)
    start.add_argument("--telemetry-profile", type=Path)
    observe = sub.add_parser("observe-soak")
    observe.add_argument("--workspace", type=Path, required=True)
    observe.add_argument("--run-id", required=True)
    observe.add_argument("--sequence", type=int, required=True)
    observe.add_argument("--observed-at", required=True)
    observe.add_argument("--metrics", type=Path, required=True)
    observe.add_argument("--attestation", type=Path, required=True)
    observe.add_argument("--trust-store", type=Path, required=True)
    observe.add_argument("--telemetry-receipt", type=Path)
    observe.add_argument("--evidence-root", type=Path, action="append")
    finish = sub.add_parser("finish-soak")
    finish.add_argument("--workspace", type=Path, required=True)
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--sequence", type=int, required=True)
    finish.add_argument("--observed-at", required=True)
    finish.add_argument("--attestation", type=Path, required=True)
    finish.add_argument("--trust-store", type=Path, required=True)
    watchdog = sub.add_parser("soak-status")
    watchdog.add_argument("--workspace", type=Path, required=True)
    watchdog.add_argument("--run-id", required=True)
    expire = sub.add_parser("expire-soak")
    expire.add_argument("--workspace", type=Path, required=True)
    expire.add_argument("--run-id", required=True)
    expire.add_argument("--observed-at", required=True)
    expire.add_argument("--attestation", type=Path, required=True)
    expire.add_argument("--trust-store", type=Path, required=True)
    assessment = evidence_command("import-assessment")
    assessment.add_argument("--report", type=Path, required=True)
    assessment.add_argument("--attestation", type=Path, required=True)
    assessment.add_argument("--external-authority-policy", type=Path)
    assessment.add_argument("--authority-approval", type=Path)
    assessment.add_argument("--internal-trust-store", type=Path)
    status = sub.add_parser("readiness")
    status.add_argument("--workspace", type=Path, required=True)
    status.add_argument("--tenant-id", required=True)
    args = parser.parse_args()

    if args.command in {"register-snapshot", "register-holdout", "record-holdout-result", "plan-cutover",
                        "transition-cutover", "import-assessment"}:
        roots = tuple(path.expanduser().resolve(strict=True) for path in args.evidence_root)
    if args.command == "register-snapshot":
        result = register_snapshot(args.workspace, args.manifest, json_file(args.authorization, "authorization"), args.trust_store, roots)
    elif args.command == "register-holdout":
        result = register_holdout(args.workspace, args.manifest, json_file(args.authorization, "authorization"), args.trust_store, roots)
    elif args.command == "record-holdout-result":
        result = record_holdout_result(args.workspace, args.manifest,
            json_file(args.executor_attestation, "executor attestation"),
            json_file(args.verifier_attestation, "verifier attestation"), args.trust_store, roots)
    elif args.command == "plan-cutover":
        result = plan_cutover(args.workspace, args.plan, json_file(args.approval, "approval"), args.trust_store, roots)
    elif args.command == "transition-cutover":
        result = transition_cutover(args.workspace, args.cutover_id, args.expected_state, args.target_state,
            args.fencing_token, json_file(args.receipt, "receipt reference"),
            json_file(args.attestation, "attestation"), args.trust_store, roots)
    elif args.command == "start-soak":
        result = start_soak(args.workspace, args.cutover_id, args.run_id, args.environment_class,
                            args.started_at, args.required_seconds, args.max_gap_seconds,
                            args.minimum_availability, args.maximum_error_rate, args.minimum_observations,
                            telemetry_profile=(json_file(args.telemetry_profile, "telemetry profile")
                                               if args.telemetry_profile else None))
    elif args.command == "observe-soak":
        observe_roots = tuple(path.expanduser().resolve(strict=True) for path in (args.evidence_root or []))
        result = observe_soak(args.workspace, args.run_id, args.sequence, args.observed_at,
            json_file(args.metrics, "metrics"), json_file(args.attestation, "attestation"), args.trust_store,
            telemetry_receipt=(json_file(args.telemetry_receipt, "telemetry receipt reference")
                               if args.telemetry_receipt else None), roots=observe_roots)
    elif args.command == "finish-soak":
        result = finish_soak(args.workspace, args.run_id, args.sequence, args.observed_at,
                             json_file(args.attestation, "attestation"), args.trust_store)
    elif args.command == "soak-status":
        result = soak_status(args.workspace, args.run_id)
    elif args.command == "expire-soak":
        result = expire_soak(args.workspace, args.run_id, args.observed_at,
                             json_file(args.attestation, "attestation"), args.trust_store)
    elif args.command == "import-assessment":
        result = import_assessment(args.workspace, args.report, json_file(args.attestation, "attestation"),
                                   args.trust_store, roots,
                                   authority_policy_path=args.external_authority_policy,
                                   authority_approval=(json_file(args.authority_approval, "authority approval")
                                                       if args.authority_approval else None),
                                   internal_trust_path=args.internal_trust_store)
    elif args.command == "readiness":
        result = readiness(args.workspace, args.tenant_id)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
