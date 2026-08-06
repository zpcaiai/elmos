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


MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
PRODUCTION_MIN_SOAK_SECONDS = 7 * 24 * 60 * 60
PRODUCTION_MAX_GAP_SECONDS = 6 * 60 * 60
PRODUCTION_OBSERVATION_SKEW_SECONDS = 15 * 60
MAX_CLOCK_SKEW_SECONDS = 5 * 60
MAX_SOAK_OBSERVATIONS = 100_000
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


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def now_text() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def utc_now() -> datetime:
    """Single patchable UTC clock; production callers never provide the clock."""
    return datetime.now(timezone.utc)


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
        finally:
            connection.close()
        findings, previous = [], "GENESIS"
        for row in rows:
            expected = canonical_digest({"event_type": row["event_type"], "aggregate_id": row["aggregate_id"],
                                         "record_sha256": row["record_sha256"], "previous_hash": previous,
                                         "created_at": row["created_at"]})
            if row["previous_hash"] != previous or row["event_hash"] != expected:
                findings.append(f"event {row['sequence']} hash-chain mismatch")
            previous = row["event_hash"]
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


def provider_profile(value: Any) -> dict[str, str]:
    fields = {"provider_id", "account_binding_sha256", "region", "adapter_id",
              "precheck_operation", "execute_operation", "verify_operation", "rollback_operation"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ClosureError("cutover provider profile fields are invalid")
    result = {field: identifier(value.get(field), f"provider.{field}") for field in fields if field != "account_binding_sha256"}
    result["account_binding_sha256"] = require_digest(value.get("account_binding_sha256"),
                                                        "provider.account_binding_sha256")
    return result


def provider_transition_receipt(value: Any, roots: tuple[Path, ...], cutover: dict[str, Any],
                                target_state: str) -> dict[str, Any]:
    """Verify an exact provider/account/operation wrapper and its native receipt bytes."""
    outer = artifact_ref(value, roots, "cutover receipt")
    path = confined(Path(value["path"]), roots, "cutover receipt")
    try:
        payload = json.loads(read_regular(path, MAX_MANIFEST_BYTES, "cutover receipt"))
    except json.JSONDecodeError as exc:
        raise ClosureError("provider transition receipt is invalid JSON") from exc
    required = {"schema_version", "receipt_id", "cutover_id", "tenant_id", "target_key",
                "target_state", "provider", "operation", "adapter_receipt", "effect_state",
                "request_sha256", "issued_at"}
    if not isinstance(payload, dict) or set(payload) != required or payload.get("schema_version") != "1.0":
        raise ClosureError("provider transition receipt fields are invalid")
    if (identifier(payload.get("receipt_id"), "receipt_id") == cutover.get("cutover_id") or
            payload.get("cutover_id") != cutover.get("cutover_id") or
            payload.get("tenant_id") != cutover.get("tenant_id") or
            payload.get("target_key") != cutover.get("target_key") or payload.get("target_state") != target_state):
        raise ClosureError("provider transition receipt binding is invalid")
    profile = provider_profile(payload.get("provider"))
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
    return {**outer, "receipt_id": payload["receipt_id"], "provider": profile,
            "operation": payload.get("operation"),
            "effect_state": expected_effect, "request_sha256": request_sha,
            "adapter_receipt": native, "issued_at": payload["issued_at"]}


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
    required = {"schema_version", "holdout_id", "tenant_id", "environment_class", "corpus",
                "development_corpus_sha256", "transformation_author_ids", "executor_ids", "verifier_ids"}
    if set(manifest) != required or manifest.get("schema_version") != "1.0":
        raise ClosureError("holdout manifest fields are invalid")
    holdout_id = identifier(manifest.get("holdout_id"), "holdout_id")
    tenant_id = identifier(manifest.get("tenant_id"), "tenant_id")
    environment = manifest.get("environment_class")
    if environment not in {"test", "sandbox", "production"}:
        raise ClosureError("holdout environment is invalid")
    corpus = artifact_ref(manifest.get("corpus"), roots, "holdout corpus")
    development = require_digest(manifest.get("development_corpus_sha256"), "development_corpus_sha256")
    if corpus["sha256"] == development:
        raise ClosureError("Holdout corpus reuses development content")
    actor_sets = []
    for field in ("transformation_author_ids", "executor_ids", "verifier_ids"):
        values = manifest.get(field)
        if not isinstance(values, list) or not values or len(values) != len(set(values)) or any(not isinstance(v, str) or not v for v in values):
            raise ClosureError(f"{field} is invalid")
        actor_sets.append(set(values))
    if actor_sets[0] & (actor_sets[1] | actor_sets[2]) or actor_sets[1] & actor_sets[2]:
        raise ClosureError("Holdout authors, executors, and verifiers must be separate")
    trust = ActorTrustStore.load(trust_path)
    payload = authorization.get("payload") if isinstance(authorization, dict) else None
    custodian_id = payload.get("actor_id") if isinstance(payload, dict) else None
    if custodian_id in set().union(*actor_sets):
        raise ClosureError("Holdout custodian conflicts with author/executor/verifier")
    actor = trust.verify(authorization, "holdout-custodian", {"holdout_id": holdout_id, "tenant_id": tenant_id,
                         "manifest_sha256": manifest_sha, "corpus_sha256": corpus["sha256"],
                         "environment_class": environment})
    record = {"schema_version": "1.0", "holdout_id": holdout_id, "tenant_id": tenant_id,
              "environment_class": environment, "manifest_sha256": manifest_sha, "corpus": corpus,
              "sealed": True, "custodian": actor, "transformation_author_ids": manifest["transformation_author_ids"],
              "executor_ids": manifest["executor_ids"], "verifier_ids": manifest["verifier_ids"]}
    return ClosureStore(workspace).insert("holdouts", holdout_id,
        (holdout_id, tenant_id, corpus["sha256"]), record, "HOLDOUT_SEALED")


def record_holdout_result(workspace: Path, manifest_path: Path, executor_attestation: dict[str, Any],
                          verifier_attestation: dict[str, Any], trust_path: Path,
                          roots: tuple[Path, ...]) -> dict[str, Any]:
    value, manifest_sha = load_manifest(manifest_path, roots, "holdout result manifest")
    required = {"schema_version", "result_id", "holdout_id", "tenant_id", "target_release_sha256",
                "provider_account_sha256", "execution_receipt", "decision", "claim_results",
                "started_at", "finished_at"}
    if not isinstance(value, dict) or set(value) != required or value.get("schema_version") != "1.0":
        raise ClosureError("holdout result fields are invalid")
    result_id = identifier(value.get("result_id"), "result_id")
    holdout_id = identifier(value.get("holdout_id"), "holdout_id")
    tenant_id = identifier(value.get("tenant_id"), "tenant_id")
    holdout = ClosureStore(workspace).row("holdouts", holdout_id)
    if holdout["tenant_id"] != tenant_id:
        raise ClosureError("holdout result crosses tenant boundary")
    target_release = require_digest(value.get("target_release_sha256"), "target_release_sha256")
    provider_account = require_digest(value.get("provider_account_sha256"), "provider_account_sha256")
    execution_receipt = artifact_ref(value.get("execution_receipt"), roots, "holdout execution receipt")
    started, finished = parse_time(value.get("started_at"), "started_at"), parse_time(value.get("finished_at"), "finished_at")
    if finished <= started or finished > utc_now() + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("holdout execution time window is invalid")
    claim_results = value.get("claim_results")
    if not isinstance(claim_results, list) or not claim_results or len(claim_results) > 100_000:
        raise ClosureError("holdout claim results are invalid")
    normalized, claim_ids, outcomes = [], set(), []
    for index, item in enumerate(claim_results):
        if not isinstance(item, dict) or set(item) != {"claim_id", "outcome", "evidence"}:
            raise ClosureError("holdout claim result fields are invalid")
        claim_id = identifier(item.get("claim_id"), f"claim_results[{index}].claim_id")
        if claim_id in claim_ids or item.get("outcome") not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise ClosureError("holdout claim identity/outcome is invalid")
        evidence = artifact_ref(item.get("evidence"), roots, f"holdout claim evidence {index}")
        claim_ids.add(claim_id)
        outcomes.append(item["outcome"])
        normalized.append({"claim_id": claim_id, "outcome": item["outcome"], "evidence": evidence})
    derived = "FAIL" if "FAIL" in outcomes else ("INCONCLUSIVE" if "INCONCLUSIVE" in outcomes else "PASS")
    if value.get("decision") != derived:
        raise ClosureError("holdout decision differs from claim outcomes")
    evidence_root = canonical_digest({"holdout_corpus_sha256": holdout["corpus"]["sha256"],
        "execution_receipt_sha256": execution_receipt["sha256"], "claim_results": normalized})
    bindings = {"result_id": result_id, "holdout_id": holdout_id, "tenant_id": tenant_id,
                "manifest_sha256": manifest_sha, "evidence_root": evidence_root,
                "target_release_sha256": target_release, "provider_account_sha256": provider_account,
                "decision": derived}
    trust = ActorTrustStore.load(trust_path)
    executor = trust.verify(executor_attestation, "holdout-executor", bindings)
    verifier = trust.verify(verifier_attestation, "holdout-verifier", {**bindings, "executor_id": executor["actor_id"]})
    if (executor["actor_id"] not in holdout["executor_ids"] or verifier["actor_id"] not in holdout["verifier_ids"] or
            executor["actor_id"] == verifier["actor_id"] or
            {executor["actor_id"], verifier["actor_id"]} &
            ({holdout["custodian"]["actor_id"]} | set(holdout["transformation_author_ids"]))):
        raise ClosureError("holdout execution actors violate the sealed custody roles")
    record = {**value, "corpus_sha256": holdout["corpus"]["sha256"], "manifest_sha256": manifest_sha,
              "execution_receipt": execution_receipt, "claim_results": normalized,
              "evidence_root": evidence_root, "executor": executor, "verifier": verifier,
              "independent": True, "sealed_holdout_consumed": True}
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
    provider = provider_profile(plan.get("provider")) if schema_version == "2.0" else None
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
    if (not isinstance(plan.get("preconditions"), list) or not plan["preconditions"] or
            len(plan["preconditions"]) != len(set(plan["preconditions"])) or
            any(not isinstance(item, str) or not item for item in plan["preconditions"])):
        raise ClosureError("cutover preconditions are required")
    trust = ActorTrustStore.load(trust_path)
    actor = trust.verify(approval, "production-approver", {"cutover_id": cutover_id, "tenant_id": tenant_id,
                         "plan_sha256": plan_sha, "snapshot_id": snapshot["snapshot_id"],
                         "target_key": plan["target_key"]})
    record = {**plan, "plan_sha256": plan_sha, "environment_class": snapshot["environment_class"],
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
    transition = {"from": expected_state, "to": target_state, "fencing_token": fencing_token,
                  "receipt": evidence, "actor": actor, "recorded_at": now_text()}
    record = {**current, "state": target_state, "fencing_token": fencing_token,
              "transitions": [*current["transitions"], transition]}
    return store.transition_cutover(cutover_id, expected_state, target_state, fencing_token, record)


def start_soak(workspace: Path, cutover_id: str, run_id: str, environment_class: str,
               started_at: str, required_seconds: int, max_gap_seconds: int,
               minimum_availability: float = 0.0, maximum_error_rate: float = 1.0,
               minimum_observations: int = 1) -> dict[str, Any]:
    cutover = ClosureStore(workspace).row("cutovers", cutover_id)
    if cutover["state"] != "SUCCEEDED":
        raise ClosureError("soak run requires a successfully verified cutover")
    if environment_class not in {"test", "sandbox", "production"}:
        raise ClosureError("soak environment is invalid")
    started = parse_time(started_at, "started_at")
    if started > utc_now() + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
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
        if (max_gap_seconds > PRODUCTION_MAX_GAP_SECONDS or
                minimum_observations < required_observations or minimum_availability < 0.99 or
                maximum_error_rate > 0.01):
            raise ClosureError("production soak requires exact provider binding and conservative telemetry policy")
        last_transition = cutover.get("transitions", [])[-1] if cutover.get("transitions") else None
        if (not isinstance(last_transition, dict) or last_transition.get("to") != "SUCCEEDED" or
                started < parse_time(last_transition.get("recorded_at"), "cutover succeeded_at") or
                (utc_now() - started).total_seconds() > PRODUCTION_OBSERVATION_SKEW_SECONDS):
            raise ClosureError("production soak must start after cutover and near real time")
    record = {"schema_version": "1.0", "run_id": identifier(run_id, "run_id"), "cutover_id": cutover_id,
              "tenant_id": cutover["tenant_id"], "environment_class": environment_class, "state": "RUNNING",
              "started_at": started_at, "required_seconds": required_seconds, "max_gap_seconds": max_gap_seconds,
              "minimum_availability": float(minimum_availability),
              "maximum_error_rate": float(maximum_error_rate), "minimum_observations": minimum_observations,
              "last_sequence": 0, "last_observed_at": None, "observations": [], "critical_failures": 0,
              "total_requests": 0, "total_errors": 0, "minimum_observed_availability": 1.0,
              "observer_ids": []}
    return ClosureStore(workspace).insert("soak_runs", run_id,
        (run_id, cutover_id, environment_class, "RUNNING", 0, None), record, "SOAK_STARTED")


def observe_soak(workspace: Path, run_id: str, sequence: int, observed_at: str,
                 metrics: dict[str, Any], attestation: dict[str, Any], trust_path: Path) -> dict[str, Any]:
    store = ClosureStore(workspace)
    current = store.row("soak_runs", run_id)
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
    now = utc_now()
    if observed > now + timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise ClosureError("soak observation is future-dated")
    if (current["environment_class"] == "production" and
            abs((now - observed).total_seconds()) > PRODUCTION_OBSERVATION_SKEW_SECONDS):
        raise ClosureError("production soak observations must be recorded near real time")
    metrics_sha = canonical_digest(metrics)
    actor = ActorTrustStore.load(trust_path).verify(attestation, "operations-owner",
        {"run_id": run_id, "sequence": sequence, "observed_at": observed_at, "metrics_sha256": metrics_sha})
    observation = {"sequence": sequence, "observed_at": observed_at, "metrics": metrics,
                   "metrics_sha256": metrics_sha, "actor": actor}
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
        "minimum_observations": record.get("minimum_observations", 1), "observations": observations})


def finish_soak(workspace: Path, run_id: str, sequence: int, observed_at: str,
                attestation: dict[str, Any], trust_path: Path) -> dict[str, Any]:
    store = ClosureStore(workspace)
    current = store.row("soak_runs", run_id)
    observed = parse_time(observed_at, "observed_at")
    if current["last_observed_at"] is None:
        raise ClosureError("soak run has no observations")
    last_observed = parse_time(current["last_observed_at"], "last_observed_at")
    if observed <= last_observed or (observed - last_observed).total_seconds() > current["max_gap_seconds"]:
        raise ClosureError("final soak observation is non-monotonic or exceeds gap policy")
    now = utc_now()
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
    record = {**current, "state": target, "last_sequence": sequence, "last_observed_at": observed_at,
              "duration_seconds": duration, "error_rate": error_rate, "evidence_root": evidence_root,
              "final_verifier": actor,
              "evidence_class": "production" if current["environment_class"] == "production" else "engineering-only"}
    return store.update_soak(run_id, sequence, observed_at, record, target)


def import_assessment(workspace: Path, report_path: Path, attestation: dict[str, Any],
                      trust_path: Path, roots: tuple[Path, ...]) -> dict[str, Any]:
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
    conflicts, eligible_soaks = [], {}
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
                if table == "holdouts":
                    conflicts.extend(value.get("executor_ids", []))
                    conflicts.extend(value.get("verifier_ids", []))
                if table == "cutovers":
                    conflicts.extend(item.get("actor", {}).get("actor_id") for item in value.get("transitions", []))
                if table == "soak_runs":
                    conflicts.extend(value.get("observer_ids", []))
    finally:
        connection.close()
    matched_soak = eligible_soaks.get(report["evidence_root"])
    if matched_soak is None:
        raise ClosureError("assessment evidence_root is not a PASSED tenant soak run")
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
    if actor_id in conflicts:
        raise ClosureError("independent certifier conflicts with execution/approval roles")
    actor = ActorTrustStore.load(trust_path).verify(attestation, "independent-certifier",
        {"assessment_id": assessment_id, "tenant_id": tenant_id, "report_sha256": report_sha,
         "evidence_root": report["evidence_root"], "decision": report["decision"]})
    record = {**report, "report_sha256": report_sha, "certifier": actor,
              "local_effect": "EXTERNAL_EVIDENCE_IMPORTED", "certified": False,
              "boundary": "An imported assessment cannot enable repository certification."}
    return store.insert("assessments", assessment_id,
        (assessment_id, tenant_id, report["evidence_root"]), record, "ASSESSMENT_IMPORTED")


def readiness(workspace: Path, tenant_id: str) -> dict[str, Any]:
    store = ClosureStore(workspace)
    counts: dict[str, int] = {}
    production = True
    state_findings: list[str] = []
    connection = store.connect()
    try:
        for table in ("snapshots", "holdouts", "holdout_results", "cutovers", "soak_runs", "assessments"):
            rows = [json.loads(row[0]) for row in connection.execute(
                f"SELECT record_json FROM {table} WHERE tenant_id=?" if table != "soak_runs" else
                "SELECT record_json FROM soak_runs", (tenant_id,) if table != "soak_runs" else ()).fetchall()]
            if table == "soak_runs":
                rows = [row for row in rows if row.get("tenant_id") == tenant_id]
            counts[table] = len(rows)
            if table in {"snapshots", "holdouts", "soak_runs"}:
                production = production and bool(rows) and all(row.get("environment_class") == "production" for row in rows)
            if table == "cutovers" and any(row.get("state") != "SUCCEEDED" for row in rows):
                state_findings.append("cutover has not reached SUCCEEDED")
            if table == "holdout_results" and any(row.get("decision") != "PASS" for row in rows):
                state_findings.append("independent Holdout result has not passed")
            if table == "soak_runs" and any(row.get("state") != "PASSED" for row in rows):
                state_findings.append("soak run has not reached PASSED")
            if table == "assessments" and any(row.get("decision") == "INCONCLUSIVE" for row in rows):
                state_findings.append("independent assessment is INCONCLUSIVE")
            if table == "assessments" and any(parse_time(row.get("expires_at"), "assessment expires_at") <= utc_now() for row in rows):
                state_findings.append("independent assessment has expired")
    finally:
        connection.close()
    findings = [*store.verify_event_chain(), *state_findings]
    if production:
        connection = store.connect()
        try:
            assessment_rows = [json.loads(row[0]) for row in connection.execute(
                "SELECT record_json FROM assessments WHERE tenant_id=?", (tenant_id,)).fetchall()]
        finally:
            connection.close()
        connection = store.connect()
        try:
            soak_rows = [json.loads(row[0]) for row in connection.execute(
                "SELECT record_json FROM soak_runs").fetchall()]
        finally:
            connection.close()
        required_roots = {row.get("evidence_root") for row in soak_rows
                          if row.get("tenant_id") == tenant_id and row.get("environment_class") == "production"
                          and row.get("state") == "PASSED"}
        positive_roots = {row.get("evidence_root") for row in assessment_rows
                          if row.get("decision") == "CERTIFIED" and
                          parse_time(row.get("expires_at"), "assessment expires_at") > utc_now()}
        if not required_roots or not required_roots.issubset(positive_roots):
            findings.append("production soak evidence lacks exact positive independent assessment coverage")
    if not any(counts.values()):
        decision = "NOT_RUN"
    elif findings or any(counts[name] == 0 for name in counts):
        decision = "BLOCKED"
    elif production:
        decision = "READY_FOR_EXTERNAL_GATE"
    else:
        decision = "LOCAL_TOOLKIT_PASS"
    return {"schema_version": "1.0", "tenant_id": tenant_id, "decision": decision,
            "certified": False, "counts": counts, "findings": findings,
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
    observe = sub.add_parser("observe-soak")
    observe.add_argument("--workspace", type=Path, required=True)
    observe.add_argument("--run-id", required=True)
    observe.add_argument("--sequence", type=int, required=True)
    observe.add_argument("--observed-at", required=True)
    observe.add_argument("--metrics", type=Path, required=True)
    observe.add_argument("--attestation", type=Path, required=True)
    observe.add_argument("--trust-store", type=Path, required=True)
    finish = sub.add_parser("finish-soak")
    finish.add_argument("--workspace", type=Path, required=True)
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--sequence", type=int, required=True)
    finish.add_argument("--observed-at", required=True)
    finish.add_argument("--attestation", type=Path, required=True)
    finish.add_argument("--trust-store", type=Path, required=True)
    assessment = evidence_command("import-assessment")
    assessment.add_argument("--report", type=Path, required=True)
    assessment.add_argument("--attestation", type=Path, required=True)
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
                            args.minimum_availability, args.maximum_error_rate, args.minimum_observations)
    elif args.command == "observe-soak":
        result = observe_soak(args.workspace, args.run_id, args.sequence, args.observed_at,
            json_file(args.metrics, "metrics"), json_file(args.attestation, "attestation"), args.trust_store)
    elif args.command == "finish-soak":
        result = finish_soak(args.workspace, args.run_id, args.sequence, args.observed_at,
                             json_file(args.attestation, "attestation"), args.trust_store)
    elif args.command == "import-assessment":
        result = import_assessment(args.workspace, args.report, json_file(args.attestation, "attestation"),
                                   args.trust_store, roots)
    elif args.command == "readiness":
        result = readiness(args.workspace, args.tenant_id)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
