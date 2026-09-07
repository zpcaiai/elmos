"""Tenant export, legal hold and evidence-bound retention execution."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from .artifacts import ContentAddressedStore
from .errors import ContractViolation, TenantIsolationError
from .models import ArtifactRef, Identity, canonical_json, digest_of, utc_now


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    policy_id: str
    tenant_id: str
    version: int
    record_class: str
    retention_seconds: int
    export_before_delete: bool = True
    deletion_mode: str = "crypto_shred"

    def __post_init__(self) -> None:
        if not self.policy_id or not self.tenant_id or self.version < 1 or not self.record_class or self.retention_seconds < 0:
            raise ContractViolation("retention policy is invalid")
        if self.deletion_mode not in {"crypto_shred", "provider_delete", "retain_immutable_index"}:
            raise ContractViolation("retention deletion mode is unsupported")


@dataclass(frozen=True, slots=True)
class GovernedObject:
    object_id: str
    tenant_id: str
    record_class: str
    reference: ArtifactRef
    policy_id: str
    policy_version: int
    created_at_epoch: float
    expires_at_epoch: float
    state: str
    legal_hold: bool
    export_digest: str | None


@dataclass(frozen=True, slots=True)
class RetentionReceipt:
    action_id: str
    tenant_id: str
    object_id: str
    action: str
    status: str
    actor: str
    independent_verifier_id: str
    approval_ref: str
    provider_receipt: str
    digest: str
    created_at: str


class RetentionController:
    """Durable retention state machine; deletion effects stay adapter-owned."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS retention_policies(policy_id TEXT NOT NULL,tenant_id TEXT NOT NULL,version INTEGER NOT NULL,record_class TEXT NOT NULL,retention_seconds INTEGER NOT NULL,export_before_delete INTEGER NOT NULL,deletion_mode TEXT NOT NULL,body_digest TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(policy_id,tenant_id,version));
               CREATE TABLE IF NOT EXISTS governed_objects(object_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,record_class TEXT NOT NULL,reference_json TEXT NOT NULL,reference_digest TEXT NOT NULL,policy_id TEXT NOT NULL,policy_version INTEGER NOT NULL,created_at_epoch REAL NOT NULL,expires_at_epoch REAL NOT NULL,state TEXT NOT NULL,legal_hold INTEGER NOT NULL DEFAULT 0,hold_reason TEXT,hold_actor TEXT,export_digest TEXT,version INTEGER NOT NULL DEFAULT 0);
               CREATE TABLE IF NOT EXISTS retention_actions(action_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,object_id TEXT NOT NULL,action TEXT NOT NULL,status TEXT NOT NULL,actor TEXT NOT NULL,independent_verifier_id TEXT NOT NULL,approval_ref TEXT NOT NULL,provider_receipt TEXT NOT NULL,body_digest TEXT NOT NULL,created_at TEXT NOT NULL);
               CREATE TRIGGER IF NOT EXISTS retention_actions_no_update BEFORE UPDATE ON retention_actions BEGIN SELECT RAISE(ABORT,'retention actions are append-only'); END;
               CREATE TRIGGER IF NOT EXISTS retention_actions_no_delete BEFORE DELETE ON retention_actions BEGIN SELECT RAISE(ABORT,'retention actions are append-only'); END;"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def put_policy(self, policy: RetentionPolicy) -> None:
        body = asdict(policy)
        body_digest = digest_of(body)
        with self._lock:
            existing = self._connection.execute("SELECT body_digest FROM retention_policies WHERE policy_id=? AND tenant_id=? AND version=?", (policy.policy_id, policy.tenant_id, policy.version)).fetchone()
            if existing is not None and existing["body_digest"] != body_digest:
                raise ContractViolation("retention policy version is immutable")
            latest = self._connection.execute("SELECT MAX(version) FROM retention_policies WHERE policy_id=? AND tenant_id=?", (policy.policy_id, policy.tenant_id)).fetchone()[0]
            if existing is None and ((latest is None and policy.version != 1) or (latest is not None and policy.version != int(latest) + 1)):
                raise ContractViolation("retention policy versions must be monotonic")
            self._connection.execute("INSERT OR IGNORE INTO retention_policies VALUES(?,?,?,?,?,?,?,?,?)", (policy.policy_id, policy.tenant_id, policy.version, policy.record_class, policy.retention_seconds, int(policy.export_before_delete), policy.deletion_mode, body_digest, utc_now()))

    def register(self, identity: Identity, reference: ArtifactRef, *, record_class: str, policy_id: str, created_at_epoch: float | None = None) -> GovernedObject:
        if reference.tenant_id != identity.tenant_id:
            raise TenantIsolationError("retention object belongs to another tenant")
        policy = self._policy(identity.tenant_id, policy_id, record_class)
        created = time.time() if created_at_epoch is None else created_at_epoch
        object_id = "retained_" + digest_of({"tenant": identity.tenant_id, "reference": reference.as_dict(), "class": record_class, "policy": [policy.policy_id, policy.version]}).split(":", 1)[1]
        expires = created + policy.retention_seconds
        with self._lock:
            row = self._connection.execute("SELECT * FROM governed_objects WHERE object_id=?", (object_id,)).fetchone()
            if row is not None:
                value = self._object(row)
                if value.reference != reference or value.policy_version != policy.version:
                    raise ContractViolation("retention object identity collision")
                return value
            self._connection.execute("INSERT INTO governed_objects VALUES(?,?,?,?,?,?,?,?,?,'active',0,NULL,NULL,NULL,0)", (object_id, identity.tenant_id, record_class, canonical_json(reference.as_dict()), reference.digest, policy.policy_id, policy.version, created, expires))
        return self.get(identity.tenant_id, object_id)

    def place_legal_hold(self, tenant_id: str, object_id: str, *, actor: str, reason: str) -> GovernedObject:
        if not actor or not reason:
            raise ContractViolation("legal hold requires actor and reason")
        self._require_object(tenant_id, object_id)
        updated = self._connection.execute("UPDATE governed_objects SET legal_hold=1,hold_reason=?,hold_actor=?,version=version+1 WHERE tenant_id=? AND object_id=? AND state NOT IN ('deleted','deletion_pending','deletion_unverified')", (reason, actor, tenant_id, object_id)).rowcount
        if updated != 1:
            raise ContractViolation("legal hold cannot be placed during or after deletion")
        return self.get(tenant_id, object_id)

    def release_legal_hold(self, tenant_id: str, object_id: str, *, actor: str, approver: str, reason: str) -> GovernedObject:
        if not actor or not approver or actor == approver or not reason:
            raise ContractViolation("legal hold release requires separate actor/approver and reason")
        self._require_object(tenant_id, object_id)
        updated = self._connection.execute("UPDATE governed_objects SET legal_hold=0,hold_reason=?,hold_actor=?,version=version+1 WHERE tenant_id=? AND object_id=? AND legal_hold=1", ("released:" + reason, actor + "+" + approver, tenant_id, object_id)).rowcount
        if updated != 1:
            raise ContractViolation("legal hold is not active")
        return self.get(tenant_id, object_id)

    def export_tenant(self, identity: Identity, artifacts: ContentAddressedStore, *, facts: Iterable[Mapping[str, Any]], authorization_ref: str) -> ArtifactRef:
        if not authorization_ref:
            raise ContractViolation("tenant export requires authorization")
        objects = self._connection.execute("SELECT * FROM governed_objects WHERE tenant_id=? ORDER BY object_id", (identity.tenant_id,)).fetchall()
        actions = self._connection.execute("SELECT * FROM retention_actions WHERE tenant_id=? ORDER BY created_at,action_id", (identity.tenant_id,)).fetchall()
        body = {
            "schema_version": "1.0",
            "tenant_id": identity.tenant_id,
            "authorization_ref": authorization_ref,
            "objects": [dict(row) for row in objects],
            "actions": [dict(row) for row in actions],
            "facts": [dict(value) for value in facts],
        }
        reference = artifacts.put(identity.tenant_id, canonical_json(body).encode("utf-8"), kind="tenant-export", media_type="application/json")
        self._connection.execute("UPDATE governed_objects SET export_digest=?,state=CASE WHEN state='active' THEN 'exported' ELSE state END,version=version+1 WHERE tenant_id=? AND state!='deleted'", (reference.digest, identity.tenant_id))
        return reference

    def due(self, tenant_id: str, *, now: float | None = None) -> tuple[GovernedObject, ...]:
        now = time.time() if now is None else now
        rows = self._connection.execute("SELECT * FROM governed_objects WHERE tenant_id=? AND expires_at_epoch<=? AND state IN ('active','exported') AND legal_hold=0 ORDER BY expires_at_epoch,object_id", (tenant_id, now)).fetchall()
        return tuple(self._object(row) for row in rows)

    def execute(
        self,
        tenant_id: str,
        object_id: str,
        *,
        actor: str,
        independent_verifier_id: str,
        approval_ref: str,
        deleter: Callable[[GovernedObject, RetentionPolicy, str], Mapping[str, Any]],
        verifier: Callable[[GovernedObject, RetentionPolicy, Mapping[str, Any]], bool],
        now: float | None = None,
    ) -> RetentionReceipt:
        now = time.time() if now is None else now
        if not actor or not independent_verifier_id or actor == independent_verifier_id or not approval_ref:
            raise ContractViolation("retention execution requires approval and an independent verifier")
        value = self.get(tenant_id, object_id)
        policy = self._policy(tenant_id, value.policy_id, value.record_class, version=value.policy_version)
        action_seed = {"tenant_id": tenant_id, "object_id": object_id, "policy": [policy.policy_id, policy.version, policy.deletion_mode], "approval": approval_ref}
        intent_id = "retention_" + digest_of(action_seed).split(":", 1)[1]
        completed = self._connection.execute("SELECT * FROM retention_actions WHERE tenant_id=? AND object_id=? AND action=? AND status='DELETED' ORDER BY created_at DESC LIMIT 1", (tenant_id, object_id, policy.deletion_mode)).fetchone()
        if value.state == "deleted" and completed is not None:
            return self._receipt(completed)
        if value.legal_hold or value.expires_at_epoch > now or value.state == "deletion_unverified":
            raise ContractViolation("retention object is held, not due, or requires reconciliation")
        if policy.export_before_delete and value.export_digest is None:
            raise ContractViolation("retention policy requires a completed tenant export")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                updated = self._connection.execute("UPDATE governed_objects SET state='deletion_pending',version=version+1 WHERE tenant_id=? AND object_id=? AND state IN ('active','exported','deletion_pending') AND legal_hold=0", (tenant_id, object_id)).rowcount
                if updated != 1:
                    raise ContractViolation("retention object changed before deletion intent")
                intent_body = {**action_seed, "intent_id": intent_id, "actor": actor, "verifier": independent_verifier_id}
                self._connection.execute("INSERT OR IGNORE INTO retention_actions VALUES(?,?,?,?,?,?,?,?,?,?,?)", (intent_id, tenant_id, object_id, policy.deletion_mode, "PENDING", actor, independent_verifier_id, approval_ref, "PENDING", digest_of(intent_body), utc_now()))
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        try:
            outcome = dict(deleter(value, policy, intent_id))
        except Exception as error:
            self._record_unverified(value, policy, intent_id, actor, independent_verifier_id, approval_ref, "PROVIDER_ERROR:" + type(error).__name__)
            raise ContractViolation("retention provider outcome is unknown and requires reconciliation") from error
        if outcome.get("status") != "DELETED" or not outcome.get("receipt"):
            self._record_unverified(value, policy, intent_id, actor, independent_verifier_id, approval_ref, "UNKNOWN_PROVIDER_OUTCOME")
            raise ContractViolation("retention provider did not return a conclusive deletion receipt")
        try:
            verified = bool(verifier(value, policy, outcome))
        except Exception as error:
            self._record_unverified(value, policy, intent_id, actor, independent_verifier_id, approval_ref, str(outcome["receipt"]))
            raise ContractViolation("retention verifier outcome is unknown and requires reconciliation") from error
        if not verified:
            self._record_unverified(value, policy, intent_id, actor, independent_verifier_id, approval_ref, str(outcome["receipt"]))
            raise ContractViolation("retention deletion receipt failed independent verification")
        return self._finalize(value, policy, intent_id, actor, independent_verifier_id, approval_ref, str(outcome["receipt"]))

    def reconcile(
        self,
        tenant_id: str,
        object_id: str,
        *,
        actor: str,
        independent_verifier_id: str,
        approval_ref: str,
        provider_receipt: str,
        verifier: Callable[[GovernedObject, RetentionPolicy, Mapping[str, Any]], bool],
    ) -> RetentionReceipt:
        value = self.get(tenant_id, object_id)
        if value.state not in {"deletion_pending", "deletion_unverified"} or not provider_receipt:
            raise ContractViolation("retention object has no ambiguous deletion to reconcile")
        if actor == independent_verifier_id or not actor or not independent_verifier_id or not approval_ref:
            raise ContractViolation("retention reconciliation roles/approval are invalid")
        policy = self._policy(tenant_id, value.policy_id, value.record_class, version=value.policy_version)
        outcome = {"status": "DELETED", "receipt": provider_receipt, "reconciled": True}
        try:
            verified = bool(verifier(value, policy, outcome))
        except Exception as error:
            raise ContractViolation("retention reconciliation verifier failed closed") from error
        if not verified:
            raise ContractViolation("retention reconciliation was not independently verified")
        intent_id = "retention_" + digest_of({"tenant_id": tenant_id, "object_id": object_id, "policy": [policy.policy_id, policy.version, policy.deletion_mode], "approval": approval_ref}).split(":", 1)[1]
        return self._finalize(value, policy, intent_id, actor, independent_verifier_id, approval_ref, provider_receipt)

    def get(self, tenant_id: str, object_id: str) -> GovernedObject:
        return self._object(self._require_object(tenant_id, object_id))

    def _require_object(self, tenant_id: str, object_id: str) -> sqlite3.Row:
        row = self._connection.execute("SELECT * FROM governed_objects WHERE object_id=?", (object_id,)).fetchone()
        if row is None:
            raise KeyError(object_id)
        if row["tenant_id"] != tenant_id:
            raise TenantIsolationError("retention object belongs to another tenant")
        return cast(sqlite3.Row, row)

    def _policy(self, tenant_id: str, policy_id: str, record_class: str, *, version: int | None = None) -> RetentionPolicy:
        if version is None:
            row = self._connection.execute("SELECT * FROM retention_policies WHERE tenant_id=? AND policy_id=? AND record_class=? ORDER BY version DESC LIMIT 1", (tenant_id, policy_id, record_class)).fetchone()
        else:
            row = self._connection.execute("SELECT * FROM retention_policies WHERE tenant_id=? AND policy_id=? AND record_class=? AND version=?", (tenant_id, policy_id, record_class, version)).fetchone()
        if row is None:
            raise ContractViolation("retention policy is unavailable for this tenant/class")
        return RetentionPolicy(row["policy_id"], row["tenant_id"], int(row["version"]), row["record_class"], int(row["retention_seconds"]), bool(row["export_before_delete"]), row["deletion_mode"])

    def _record_unverified(self, value: GovernedObject, policy: RetentionPolicy, intent_id: str, actor: str, verifier_id: str, approval_ref: str, receipt: str) -> None:
        created_at = utc_now()
        action_id = intent_id + ":unverified:" + digest_of(receipt).split(":", 1)[1][:16]
        body = {"intent_id": intent_id, "receipt": receipt, "status": "UNKNOWN", "created_at": created_at}
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("UPDATE governed_objects SET state='deletion_unverified',version=version+1 WHERE tenant_id=? AND object_id=? AND state='deletion_pending'", (value.tenant_id, value.object_id))
                self._connection.execute("INSERT OR IGNORE INTO retention_actions VALUES(?,?,?,?,?,?,?,?,?,?,?)", (action_id, value.tenant_id, value.object_id, policy.deletion_mode, "UNKNOWN", actor, verifier_id, approval_ref, receipt, digest_of(body), created_at))
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _finalize(self, value: GovernedObject, policy: RetentionPolicy, intent_id: str, actor: str, verifier_id: str, approval_ref: str, receipt: str) -> RetentionReceipt:
        created_at = utc_now()
        action_id = intent_id + ":deleted"
        body = {"intent_id": intent_id, "tenant_id": value.tenant_id, "object_id": value.object_id, "action": policy.deletion_mode, "status": "DELETED", "actor": actor, "verifier": verifier_id, "approval": approval_ref, "receipt": receipt, "created_at": created_at}
        body_digest = digest_of(body)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                updated = self._connection.execute("UPDATE governed_objects SET state='deleted',version=version+1 WHERE tenant_id=? AND object_id=? AND state IN ('deletion_pending','deletion_unverified') AND legal_hold=0", (value.tenant_id, value.object_id)).rowcount
                if updated != 1:
                    existing = self._connection.execute("SELECT * FROM retention_actions WHERE action_id=?", (action_id,)).fetchone()
                    if existing is None:
                        raise ContractViolation("retention object changed during final reconciliation")
                    self._connection.execute("COMMIT")
                    return self._receipt(existing)
                self._connection.execute("INSERT INTO retention_actions VALUES(?,?,?,?,?,?,?,?,?,?,?)", (action_id, value.tenant_id, value.object_id, policy.deletion_mode, "DELETED", actor, verifier_id, approval_ref, receipt, body_digest, created_at))
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return RetentionReceipt(action_id, value.tenant_id, value.object_id, policy.deletion_mode, "DELETED", actor, verifier_id, approval_ref, receipt, body_digest, created_at)

    @staticmethod
    def _receipt(row: sqlite3.Row) -> RetentionReceipt:
        return RetentionReceipt(row["action_id"], row["tenant_id"], row["object_id"], row["action"], row["status"], row["actor"], row["independent_verifier_id"], row["approval_ref"], row["provider_receipt"], row["body_digest"], row["created_at"])

    @staticmethod
    def _object(row: sqlite3.Row) -> GovernedObject:
        reference = ArtifactRef(**json.loads(row["reference_json"]))
        if reference.digest != row["reference_digest"]:
            raise ContractViolation("retention object reference digest is corrupt")
        return GovernedObject(row["object_id"], row["tenant_id"], row["record_class"], reference, row["policy_id"], int(row["policy_version"]), float(row["created_at_epoch"]), float(row["expires_at_epoch"]), row["state"], bool(row["legal_hold"]), row["export_digest"])
