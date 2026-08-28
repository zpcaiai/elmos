"""Digest-bound canary deployment, observation, promotion, and rollback."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast

from .canonical import canonical_bytes, digest, require_nonempty, require_uuid, utc_now
from .models import ConflictError, NotFoundError
from .production import ApprovalGrant, ExactTarget


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class DeploymentManifest:
    release_id: str
    artifact_digest: str
    sbom_digest: str
    provenance_digest: str
    configuration_digest: str
    database_migration_digest: str
    workflow_build_id: str
    target: ExactTarget
    rollback_artifact_digest: str
    required_slos: Mapping[str, float]

    def __post_init__(self) -> None:
        require_uuid(self.release_id, "release_id")
        if not isinstance(self.required_slos, Mapping):
            raise ValueError("required_slos must be an object")
        slos = dict(self.required_slos)
        for name in (
            "artifact_digest",
            "sbom_digest",
            "provenance_digest",
            "configuration_digest",
            "database_migration_digest",
            "rollback_artifact_digest",
        ):
            value = require_nonempty(getattr(self, name), name, 256)
            if not _DIGEST.fullmatch(value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        require_nonempty(self.workflow_build_id, "workflow_build_id", 256)
        if self.artifact_digest == self.rollback_artifact_digest:
            raise ValueError("rollback artifact must differ from the candidate artifact")
        if not slos or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in slos.values()
        ):
            raise ValueError("required_slos must contain finite numeric thresholds")
        if any(
            not isinstance(name, str)
            or not name
            or not name.endswith(("_min", "_max"))
            for name in slos
        ):
            raise ValueError("every required SLO must end in _min or _max")
        object.__setattr__(self, "required_slos", MappingProxyType(slos))

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "artifact_digest": self.artifact_digest,
            "sbom_digest": self.sbom_digest,
            "provenance_digest": self.provenance_digest,
            "configuration_digest": self.configuration_digest,
            "database_migration_digest": self.database_migration_digest,
            "workflow_build_id": self.workflow_build_id,
            "target": self.target.to_dict(),
            "rollback_artifact_digest": self.rollback_artifact_digest,
            "required_slos": dict(self.required_slos),
        }

    @property
    def manifest_digest(self) -> str:
        return digest(self.to_dict())


class DeploymentAdapter(Protocol):
    target: ExactTarget

    def deploy_canary(
        self, manifest: DeploymentManifest, *, idempotency_key: str
    ) -> Mapping[str, Any]: ...
    def observe(
        self, native_release_id: str, required_slos: Mapping[str, float]
    ) -> Mapping[str, Any]: ...
    def promote(
        self, native_release_id: str, *, idempotency_key: str
    ) -> Mapping[str, Any]: ...
    def rollback(
        self,
        native_release_id: str,
        rollback_artifact_digest: str,
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any]: ...

    def reconcile(
        self,
        release_id: str,
        native_release_id: str | None,
        expected_state: str,
    ) -> Mapping[str, Any]: ...


DEPLOYMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS deployment_run (
  release_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  manifest_digest TEXT NOT NULL,
  approval_json TEXT NOT NULL,
  state TEXT NOT NULL,
  native_release_id TEXT,
  observation_json TEXT,
  evidence_digest TEXT,
  pending_state TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deployment_event (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  release_id TEXT NOT NULL REFERENCES deployment_run(release_id),
  state TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  evidence_digest TEXT,
  created_at TEXT NOT NULL
);
"""


class DeploymentController:
    def __init__(
        self, adapter: DeploymentAdapter, journal_path: str = ":memory:"
    ) -> None:
        if journal_path != ":memory:" and not Path(journal_path).is_absolute():
            raise ValueError("deployment journal path must be absolute")
        if journal_path != ":memory:":
            path = Path(journal_path)
            if path.is_symlink():
                raise ValueError("deployment journal must not be a symbolic link")
            if not path.parent.is_dir() or path.parent.is_symlink():
                raise ValueError("deployment journal parent must be a safe directory")
            current = Path(path.anchor)
            for part in path.parent.parts[1:]:
                current = current / part
                if current.is_symlink():
                    raise ValueError(
                        "deployment journal path must not traverse symbolic links"
                    )
        self.adapter = adapter
        self._connection = sqlite3.connect(journal_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=30000")
        if journal_path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            os.chmod(journal_path, 0o600)
        self._connection.executescript(DEPLOYMENT_SCHEMA)
        self._lock = threading.RLock()

    def start_canary(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        manifest: DeploymentManifest,
        approval: ApprovalGrant,
    ) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        actor_id = require_nonempty(actor_id, "actor_id", 256)
        if manifest.target.environment.lower() not in {"prod", "production"}:
            raise ConflictError("production deployment target must be production")
        if digest(self.adapter.target.to_dict()) != digest(manifest.target.to_dict()):
            raise ConflictError(
                "deployment adapter target does not match the release manifest"
            )
        approval.assert_valid(
            operation_id=manifest.release_id,
            request_digest=manifest.manifest_digest,
            target=manifest.target,
            action="deploy_canary",
            actor_id=actor_id,
        )
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM deployment_run WHERE release_id=?",
                (manifest.release_id,),
            ).fetchone()
            if existing:
                if existing["tenant_id"] != tenant_id:
                    raise ConflictError(
                        "release identity is already bound to another tenant"
                    )
                if existing["manifest_digest"] != manifest.manifest_digest:
                    raise ConflictError(
                        "release id was reused with a different manifest"
                    )
                if existing["approval_json"] != canonical_bytes(
                    approval.__dict__
                ).decode():
                    raise ConflictError(
                        "canary replay used a different approval grant"
                    )
                return self._row(existing) | {"replayed": True}
            self._connection.execute(
                "INSERT INTO deployment_run(release_id,tenant_id,actor_id,manifest_json,manifest_digest,approval_json,state,pending_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    manifest.release_id,
                    tenant_id,
                    actor_id,
                    canonical_bytes(manifest.to_dict()).decode(),
                    manifest.manifest_digest,
                    canonical_bytes(approval.__dict__).decode(),
                    "SUBMITTING_CANARY",
                    "CANARY",
                    utc_now(),
                    utc_now(),
                ),
            )
            self._event(
                manifest.release_id,
                "APPROVED",
                approval.approved_by,
                digest(approval.__dict__),
            )
            self._event(
                manifest.release_id,
                "SUBMITTING_CANARY",
                actor_id,
                manifest.manifest_digest,
            )
        try:
            native = dict(
                self.adapter.deploy_canary(
                    manifest, idempotency_key=manifest.release_id
                )
            )
            canonical_bytes(native)
        except Exception as exc:  # noqa: BLE001 - unknown provider outcomes must be reconciled
            # A timeout after submission is not a safe failure. The release is
            # blocked until the provider-native id/status is reconciled.
            self._update(
                manifest.release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                _error_evidence(exc, "deploy_canary"),
                pending_state="CANARY",
                expected_states={"SUBMITTING_CANARY"},
            )
            return self.get(tenant_id, manifest.release_id)
        native_id = native.get("native_release_id")
        if (
            native.get("status") != "SUCCEEDED"
            or not native_id
            or not _is_digest(native.get("raw_evidence_digest"))
        ):
            self._update(
                manifest.release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                native,
                pending_state="CANARY",
                expected_states={"SUBMITTING_CANARY"},
            )
            return self.get(tenant_id, manifest.release_id)
        with self._lock, self._connection:
            updated = self._connection.execute(
                "UPDATE deployment_run SET state='CANARY',native_release_id=?,observation_json=?,evidence_digest=?,pending_state=NULL,updated_at=? WHERE release_id=? AND state='SUBMITTING_CANARY'",
                (
                    native_id,
                    canonical_bytes(native).decode(),
                    digest(native),
                    utc_now(),
                    manifest.release_id,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError(
                    "deployment state changed while canary submission was in flight"
                )
            self._event(manifest.release_id, "CANARY", actor_id, digest(native))
        return self.get(tenant_id, manifest.release_id) | {"replayed": False}

    def observe_canary(
        self, tenant_id: str, release_id: str, *, actor_id: str
    ) -> dict[str, Any]:
        actor_id = require_nonempty(actor_id, "actor_id", 256)
        row = self._required_state(tenant_id, release_id, {"CANARY", "OBSERVING"})
        manifest = _manifest(row)
        if row["state"] == "OBSERVING":
            return self.get(tenant_id, release_id) | {"replayed": True}
        self._update(
            release_id,
            "OBSERVING",
            actor_id,
            {"status": "STARTED", "native_release_id": row["native_release_id"]},
            pending_state="CANARY",
            expected_states={"CANARY"},
        )
        try:
            observation = dict(
                self.adapter.observe(
                    row["native_release_id"], manifest.required_slos
                )
            )
            canonical_bytes(observation)
        except Exception as exc:  # noqa: BLE001 - observation outcome is unknown
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                _error_evidence(exc, "observe_canary"),
                pending_state="CANARY",
                expected_states={"OBSERVING"},
            )
            return self.get(tenant_id, release_id)
        metrics = observation.get("metrics")
        if (
            observation.get("status") != "SUCCEEDED"
            or not isinstance(metrics, Mapping)
            or not _is_digest(observation.get("raw_evidence_digest"))
        ):
            state = "RECONCILIATION_REQUIRED"
        else:
            state = (
                "CANARY_PASS"
                if _slos_met(metrics, manifest.required_slos)
                else "CANARY_FAIL"
            )
        self._update(
            release_id,
            state,
            actor_id,
            observation,
            pending_state="CANARY" if state == "RECONCILIATION_REQUIRED" else None,
            expected_states={"OBSERVING"},
        )
        return self.get(tenant_id, release_id)

    def promote(
        self, tenant_id: str, release_id: str, approval: ApprovalGrant, *, actor_id: str
    ) -> dict[str, Any]:
        actor_id = require_nonempty(actor_id, "actor_id", 256)
        row = self._required_state(
            tenant_id, release_id, {"CANARY_PASS", "PROMOTING"}
        )
        manifest = _manifest(row)
        approval.assert_valid(
            operation_id=release_id,
            request_digest=manifest.manifest_digest,
            target=manifest.target,
            action="promote_release",
            actor_id=actor_id,
        )
        if row["state"] == "PROMOTING":
            if _approval_digest_from_row(row) != digest(approval.__dict__):
                raise ConflictError("promotion replay used a different approval")
            return self.get(tenant_id, release_id) | {"replayed": True}
        self._update(
            release_id,
            "PROMOTING",
            actor_id,
            {
                "status": "APPROVED",
                "approval_digest": digest(approval.__dict__),
            },
            pending_state="PROMOTED",
            expected_states={"CANARY_PASS"},
        )
        try:
            native = dict(
                self.adapter.promote(
                    row["native_release_id"], idempotency_key=approval.approval_id
                )
            )
            canonical_bytes(native)
        except Exception as exc:  # noqa: BLE001 - provider outcome may be unknown
            native = _error_evidence(exc, "promote_release")
        if native.get("status") != "SUCCEEDED" or not _is_digest(
            native.get("raw_evidence_digest")
        ):
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                native,
                pending_state="PROMOTED",
                expected_states={"PROMOTING"},
            )
        else:
            self._update(
                release_id,
                "PROMOTED",
                actor_id,
                native,
                expected_states={"PROMOTING"},
            )
        return self.get(tenant_id, release_id)

    def rollback(
        self, tenant_id: str, release_id: str, approval: ApprovalGrant, *, actor_id: str
    ) -> dict[str, Any]:
        actor_id = require_nonempty(actor_id, "actor_id", 256)
        row = self._required_state(
            tenant_id,
            release_id,
            {
                "CANARY",
                "CANARY_FAIL",
                "CANARY_PASS",
                "PROMOTED",
                "RECONCILIATION_REQUIRED",
                "ROLLING_BACK",
            },
        )
        manifest = _manifest(row)
        approval.assert_valid(
            operation_id=release_id,
            request_digest=manifest.manifest_digest,
            target=manifest.target,
            action="rollback_release",
            actor_id=actor_id,
        )
        if row["state"] == "ROLLING_BACK":
            if _approval_digest_from_row(row) != digest(approval.__dict__):
                raise ConflictError("rollback replay used a different approval")
            return self.get(tenant_id, release_id) | {"replayed": True}
        if not row["native_release_id"]:
            raise ConflictError(
                "native release identity must be reconciled before rollback"
            )
        original_state = str(row["state"])
        self._update(
            release_id,
            "ROLLING_BACK",
            actor_id,
            {
                "status": "APPROVED",
                "approval_digest": digest(approval.__dict__),
            },
            pending_state="ROLLED_BACK",
            expected_states={original_state},
        )
        try:
            native = dict(
                self.adapter.rollback(
                    row["native_release_id"],
                    manifest.rollback_artifact_digest,
                    idempotency_key=approval.approval_id,
                )
            )
            canonical_bytes(native)
        except Exception as exc:  # noqa: BLE001 - provider outcome may be unknown
            native = _error_evidence(exc, "rollback_release")
        if native.get("status") != "SUCCEEDED" or not _is_digest(
            native.get("raw_evidence_digest")
        ):
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                native,
                pending_state="ROLLED_BACK",
                expected_states={"ROLLING_BACK"},
            )
        else:
            self._update(
                release_id,
                "ROLLED_BACK",
                actor_id,
                native,
                expected_states={"ROLLING_BACK"},
            )
        return self.get(tenant_id, release_id)

    def reconcile(
        self, tenant_id: str, release_id: str, *, actor_id: str
    ) -> dict[str, Any]:
        actor_id = require_nonempty(actor_id, "actor_id", 256)
        row = self._required_state(
            tenant_id,
            release_id,
            {
                "RECONCILIATION_REQUIRED",
                "SUBMITTING_CANARY",
                "OBSERVING",
                "PROMOTING",
                "ROLLING_BACK",
            },
        )
        original_state = str(row["state"])
        expected_state = row["pending_state"]
        if expected_state not in {"CANARY", "PROMOTED", "ROLLED_BACK"}:
            raise ConflictError("deployment reconciliation intent is missing")
        try:
            evidence = dict(
                self.adapter.reconcile(
                    release_id, row["native_release_id"], expected_state
                )
            )
            canonical_bytes(evidence)
        except Exception as exc:  # noqa: BLE001 - reconciliation can remain unknown
            evidence = _error_evidence(exc, "reconcile") | {"state": "UNKNOWN"}
        observed_native_id = evidence.get("native_release_id")
        if row["native_release_id"] and observed_native_id not in {
            None,
            row["native_release_id"],
        }:
            raise ConflictError(
                "deployment provider identity changed during reconciliation"
            )
        if not row["native_release_id"] and observed_native_id:
            with self._lock, self._connection:
                updated = self._connection.execute(
                    "UPDATE deployment_run SET native_release_id=?,updated_at=? WHERE release_id=? AND native_release_id IS NULL AND state=?",
                    (observed_native_id, utc_now(), release_id, original_state),
                )
                if updated.rowcount != 1:
                    raise ConflictError(
                        "deployment state changed during identity reconciliation"
                    )
            row = self._required_state(tenant_id, release_id, {original_state})
        observed_state = evidence.get("state")
        identity_bound = expected_state != "CANARY" or bool(row["native_release_id"])
        evidence_bound = _is_digest(evidence.get("raw_evidence_digest"))
        if (
            observed_state == expected_state
            and evidence_bound
            and identity_bound
        ):
            self._update(
                release_id,
                expected_state,
                actor_id,
                evidence,
                pending_state=None,
                expected_states={original_state},
            )
        elif observed_state in {"FAILED", "ROLLED_BACK"} and evidence_bound:
            self._update(
                release_id,
                str(observed_state),
                actor_id,
                evidence,
                pending_state=None,
                expected_states={original_state},
            )
        else:
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                evidence,
                pending_state=expected_state,
                expected_states={original_state},
            )
        return self.get(tenant_id, release_id)

    def get(self, tenant_id: str, release_id: str) -> dict[str, Any]:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        release_id = require_uuid(release_id, "release_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM deployment_run WHERE tenant_id=? AND release_id=?",
                (tenant_id, release_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("deployment run not found")
            return self._row(row)

    def _required_state(
        self, tenant_id: str, release_id: str, states: set[str]
    ) -> sqlite3.Row:
        tenant_id = require_uuid(tenant_id, "tenant_id")
        release_id = require_uuid(release_id, "release_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM deployment_run WHERE tenant_id=? AND release_id=?",
                (tenant_id, release_id),
            ).fetchone()
            if row is None:
                raise NotFoundError("deployment run not found")
            if row["state"] not in states:
                raise ConflictError(
                    f"deployment state {row['state']} does not allow this operation"
                )
            return cast(sqlite3.Row, row)

    def _update(
        self,
        release_id: str,
        state: str,
        actor_id: str,
        evidence: Mapping[str, Any],
        *,
        pending_state: str | None = None,
        expected_states: set[str] | None = None,
    ) -> None:
        evidence_value = dict(evidence)
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT state FROM deployment_run WHERE release_id=?", (release_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("deployment run not found")
            if expected_states is not None and row["state"] not in expected_states:
                raise ConflictError(
                    "deployment state changed while an external operation was in flight"
                )
            self._connection.execute(
                "UPDATE deployment_run SET state=?,observation_json=?,evidence_digest=?,pending_state=?,updated_at=? WHERE release_id=?",
                (
                    state,
                    canonical_bytes(evidence_value).decode(),
                    digest(evidence_value),
                    pending_state,
                    utc_now(),
                    release_id,
                ),
            )
            self._event(release_id, state, actor_id, digest(evidence_value))

    def _event(
        self, release_id: str, state: str, actor_id: str, evidence_digest: str | None
    ) -> None:
        self._connection.execute(
            "INSERT INTO deployment_event(release_id,state,actor_id,evidence_digest,created_at) VALUES(?,?,?,?,?)",
            (release_id, state, actor_id, evidence_digest, utc_now()),
        )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "release_id": row["release_id"],
            "tenant_id": row["tenant_id"],
            "manifest_digest": row["manifest_digest"],
            "state": row["state"],
            "native_release_id": row["native_release_id"],
            "evidence_digest": row["evidence_digest"],
            "pending_state": row["pending_state"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "certified": False,
        }

    def close(self) -> None:
        self._connection.close()


def validate_production_configuration(config: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "postgres_dsn_reference",
        "temporal_target",
        "oidc_issuer",
        "oidc_audience",
        "mtls_trust_domain",
        "artifact_store",
        "cloud_provider",
        "region",
        "account_id",
        "backup_policy_id",
        "verifier_trust_store",
        "slo_profile",
        "immutable_evidence_store",
        "private_endpoints",
        "database_backend",
        "static_api_token_enabled",
        "tls_mode",
        "allow_public_ingress",
        "default_network_egress",
    }
    missing = sorted(name for name in required if not config.get(name))
    # Explicit false values are required for these controls and therefore are
    # not missing merely because bool(False) is false.
    missing = [
        name
        for name in missing
        if name not in {"static_api_token_enabled", "allow_public_ingress"}
        or name not in config
    ]
    denials: list[str] = []
    if config.get("database_backend") != "postgresql":
        denials.append("production_database_must_be_postgresql")
    if config.get("static_api_token_enabled") is not False:
        denials.append("static_api_token_must_be_disabled")
    if config.get("tls_mode") != "mutual":
        denials.append("mutual_tls_required")
    if config.get("allow_public_ingress") is not False:
        denials.append("public_ingress_not_approved")
    if config.get("default_network_egress") != "deny":
        denials.append("default_network_egress_must_be_deny")
    if config.get("secrets_inline"):
        denials.append("inline_secrets_forbidden")
    dsn_reference = config.get("postgres_dsn_reference")
    if not isinstance(dsn_reference, str) or not dsn_reference.startswith(
        ("secret://", "vault://", "aws-secretsmanager://")
    ):
        denials.append("postgres_dsn_must_be_an_external_secret_reference")
    issuer = config.get("oidc_issuer")
    if not isinstance(issuer, str) or not issuer.startswith("https://"):
        denials.append("oidc_issuer_must_use_https")
    if not isinstance(config.get("oidc_audience"), str):
        denials.append("oidc_audience_must_be_explicit")
    for field in (
        "oidc_audience",
        "mtls_trust_domain",
        "backup_policy_id",
        "verifier_trust_store",
        "slo_profile",
    ):
        value = config.get(field)
        if not isinstance(value, str) or not value.strip():
            denials.append(f"{field}_must_be_explicit")
    temporal = config.get("temporal_target")
    if not isinstance(temporal, Mapping) or not all(
        temporal.get(name) for name in ("endpoint", "namespace", "server_version")
    ):
        denials.append("temporal_exact_target_is_incomplete")
    else:
        endpoint = temporal.get("endpoint")
        if temporal.get("mtls") is not True:
            denials.append("temporal_mtls_is_required")
        if not isinstance(endpoint, str) or endpoint.startswith(
            ("http://", "grpc://")
        ):
            denials.append("temporal_endpoint_must_not_use_plaintext_transport")
    account_id = config.get("account_id")
    region = config.get("region")
    if not isinstance(account_id, str) or re.fullmatch(r"[0-9]{12}", account_id) is None:
        denials.append("cloud_account_id_is_invalid")
    if not isinstance(region, str) or re.fullmatch(
        r"[a-z]{2}(?:-[a-z0-9]+)+-[0-9]+", region
    ) is None:
        denials.append("cloud_region_is_invalid")
    if config.get("cloud_provider") != "aws":
        denials.append("unsupported_cloud_provider")
    for field in ("artifact_store", "immutable_evidence_store"):
        store = config.get(field)
        if not isinstance(store, Mapping):
            denials.append(f"{field}_is_incomplete")
            continue
        kms_key_arn = store.get("kms_key_arn")
        if (
            not store.get("bucket")
            or store.get("region") != region
            or store.get("account_id") != account_id
            or not isinstance(kms_key_arn, str)
            or f":kms:{region}:{account_id}:key/" not in kms_key_arn
            or store.get("public_access") is not False
        ):
            denials.append(f"{field}_exact_target_or_security_mismatch")
    evidence_store = config.get("immutable_evidence_store")
    if isinstance(evidence_store, Mapping) and (
        evidence_store.get("object_lock") is not True
        or evidence_store.get("versioning") is not True
        or evidence_store.get("retention_mode") != "COMPLIANCE"
        or not isinstance(evidence_store.get("retention_days"), int)
        or isinstance(evidence_store.get("retention_days"), bool)
        or evidence_store.get("retention_days", 0) < 90
    ):
        denials.append("immutable_evidence_store_requires_compliance_object_lock")
    endpoints = config.get("private_endpoints")
    if (
        not isinstance(endpoints, list)
        or not endpoints
        or any(not isinstance(item, str) or not item.strip() for item in endpoints)
        or len(set(endpoints)) != len(endpoints)
    ):
        denials.append("private_endpoints_are_required")
    return {
        "valid": not missing and not denials,
        "missing": missing,
        "policy_denials": sorted(set(denials)),
        "certified": False,
    }


def _manifest(row: sqlite3.Row) -> DeploymentManifest:
    value = json.loads(row["manifest_json"])
    value["target"] = ExactTarget(**value["target"])
    return DeploymentManifest(**value)


def _approval_digest_from_row(row: sqlite3.Row) -> str | None:
    try:
        value = json.loads(row["observation_json"] or "{}")
    except json.JSONDecodeError:
        return None
    return value.get("approval_digest") if isinstance(value, dict) else None


def _error_evidence(exc: Exception, phase: str) -> dict[str, str]:
    return {
        "phase": phase,
        "error_type": type(exc).__name__,
        "error_message_digest": digest({"message": str(exc)[:4096]}),
    }


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _slos_met(metrics: Mapping[str, Any], required: Mapping[str, float]) -> bool:
    for name, threshold in required.items():
        value = metrics.get(name)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            return False
        if name.endswith("_max") and value > threshold:
            return False
        if name.endswith("_min") and value < threshold:
            return False
    return True
