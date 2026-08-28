"""Digest-bound canary deployment, observation, promotion, and rollback."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_bytes, digest, require_nonempty, require_uuid, utc_now
from .models import ConflictError, NotFoundError
from .production import ApprovalGrant, ExactTarget


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
        for name in (
            "artifact_digest",
            "sbom_digest",
            "provenance_digest",
            "configuration_digest",
            "database_migration_digest",
            "workflow_build_id",
            "rollback_artifact_digest",
        ):
            require_nonempty(getattr(self, name), name, 256)
        if not self.required_slos or any(
            not isinstance(value, (int, float)) for value in self.required_slos.values()
        ):
            raise ValueError("required_slos must contain numeric thresholds")

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
        self.adapter = adapter
        self._connection = sqlite3.connect(journal_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
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
                if existing["manifest_digest"] != manifest.manifest_digest:
                    raise ConflictError(
                        "release id was reused with a different manifest"
                    )
                return self._row(existing) | {"replayed": True}
            self._connection.execute(
                "INSERT INTO deployment_run(release_id,tenant_id,actor_id,manifest_json,manifest_digest,approval_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    manifest.release_id,
                    tenant_id,
                    actor_id,
                    canonical_bytes(manifest.to_dict()).decode(),
                    manifest.manifest_digest,
                    canonical_bytes(approval.__dict__).decode(),
                    "APPROVED",
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
        try:
            native = dict(
                self.adapter.deploy_canary(
                    manifest, idempotency_key=manifest.release_id
                )
            )
        except Exception as exc:  # noqa: BLE001 - unknown provider outcomes must be reconciled
            # A timeout after submission is not a safe failure. The release is
            # blocked until the provider-native id/status is reconciled.
            self._update(
                manifest.release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
                pending_state="CANARY",
            )
            return self.get(tenant_id, manifest.release_id)
        native_id = native.get("native_release_id")
        if not native_id:
            self._update(
                manifest.release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                native,
                pending_state="CANARY",
            )
            return self.get(tenant_id, manifest.release_id)
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE deployment_run SET state='CANARY',native_release_id=?,observation_json=?,evidence_digest=?,updated_at=? WHERE release_id=?",
                (
                    native_id,
                    canonical_bytes(native).decode(),
                    digest(native),
                    utc_now(),
                    manifest.release_id,
                ),
            )
            self._event(manifest.release_id, "CANARY", actor_id, digest(native))
        return self.get(tenant_id, manifest.release_id) | {"replayed": False}

    def observe_canary(
        self, tenant_id: str, release_id: str, *, actor_id: str
    ) -> dict[str, Any]:
        row = self._required_state(tenant_id, release_id, {"CANARY", "OBSERVING"})
        manifest = _manifest(row)
        observation = dict(
            self.adapter.observe(row["native_release_id"], manifest.required_slos)
        )
        metrics = observation.get("metrics")
        if not isinstance(metrics, Mapping) or not observation.get(
            "raw_evidence_digest"
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
        )
        return self.get(tenant_id, release_id)

    def promote(
        self, tenant_id: str, release_id: str, approval: ApprovalGrant, *, actor_id: str
    ) -> dict[str, Any]:
        row = self._required_state(tenant_id, release_id, {"CANARY_PASS"})
        manifest = _manifest(row)
        approval.assert_valid(
            operation_id=release_id,
            request_digest=manifest.manifest_digest,
            target=manifest.target,
            action="promote_release",
            actor_id=actor_id,
        )
        native = dict(
            self.adapter.promote(
                row["native_release_id"], idempotency_key=approval.approval_id
            )
        )
        if native.get("status") != "SUCCEEDED" or not native.get("raw_evidence_digest"):
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                native,
                pending_state="PROMOTED",
            )
        else:
            self._update(release_id, "PROMOTED", actor_id, native)
        return self.get(tenant_id, release_id)

    def rollback(
        self, tenant_id: str, release_id: str, approval: ApprovalGrant, *, actor_id: str
    ) -> dict[str, Any]:
        row = self._required_state(
            tenant_id,
            release_id,
            {
                "CANARY",
                "CANARY_FAIL",
                "CANARY_PASS",
                "PROMOTED",
                "RECONCILIATION_REQUIRED",
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
        if not row["native_release_id"]:
            raise ConflictError(
                "native release identity must be reconciled before rollback"
            )
        native = dict(
            self.adapter.rollback(
                row["native_release_id"],
                manifest.rollback_artifact_digest,
                idempotency_key=approval.approval_id,
            )
        )
        if native.get("status") != "SUCCEEDED" or not native.get("raw_evidence_digest"):
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                native,
                pending_state="ROLLED_BACK",
            )
        else:
            self._update(release_id, "ROLLED_BACK", actor_id, native)
        return self.get(tenant_id, release_id)

    def reconcile(
        self, tenant_id: str, release_id: str, *, actor_id: str
    ) -> dict[str, Any]:
        row = self._required_state(tenant_id, release_id, {"RECONCILIATION_REQUIRED"})
        expected_state = row["pending_state"]
        if expected_state not in {"CANARY", "PROMOTED", "ROLLED_BACK"}:
            raise ConflictError("deployment reconciliation intent is missing")
        evidence = dict(
            self.adapter.reconcile(release_id, row["native_release_id"], expected_state)
        )
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
                self._connection.execute(
                    "UPDATE deployment_run SET native_release_id=?,updated_at=? WHERE release_id=? AND native_release_id IS NULL",
                    (observed_native_id, utc_now(), release_id),
                )
            row = self._required_state(
                tenant_id, release_id, {"RECONCILIATION_REQUIRED"}
            )
        observed_state = evidence.get("state")
        identity_bound = expected_state != "CANARY" or bool(row["native_release_id"])
        if (
            observed_state == expected_state
            and evidence.get("raw_evidence_digest")
            and identity_bound
        ):
            self._update(
                release_id, expected_state, actor_id, evidence, pending_state=None
            )
        elif observed_state in {"FAILED", "ROLLED_BACK"} and evidence.get(
            "raw_evidence_digest"
        ):
            self._update(
                release_id, str(observed_state), actor_id, evidence, pending_state=None
            )
        else:
            self._update(
                release_id,
                "RECONCILIATION_REQUIRED",
                actor_id,
                evidence,
                pending_state=expected_state,
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
        self.get(tenant_id, release_id)
        row = self._connection.execute(
            "SELECT * FROM deployment_run WHERE tenant_id=? AND release_id=?",
            (tenant_id, release_id),
        ).fetchone()
        if row["state"] not in states:
            raise ConflictError(
                f"deployment state {row['state']} does not allow this operation"
            )
        return row

    def _update(
        self,
        release_id: str,
        state: str,
        actor_id: str,
        evidence: Mapping[str, Any],
        *,
        pending_state: str | None = None,
    ) -> None:
        evidence_value = dict(evidence)
        with self._lock, self._connection:
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
    }
    missing = sorted(name for name in required if not config.get(name))
    denials: list[str] = []
    if config.get("database_backend") in {None, "sqlite"}:
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
    return {
        "valid": not missing and not denials,
        "missing": missing,
        "policy_denials": denials,
        "certified": False,
    }


def _manifest(row: sqlite3.Row) -> DeploymentManifest:
    value = json.loads(row["manifest_json"])
    value["target"] = ExactTarget(**value["target"])
    return DeploymentManifest(**value)


def _slos_met(metrics: Mapping[str, Any], required: Mapping[str, float]) -> bool:
    for name, threshold in required.items():
        value = metrics.get(name)
        if not isinstance(value, (int, float)):
            return False
        if name.endswith("_max") and value > threshold:
            return False
        if name.endswith("_min") and value < threshold:
            return False
    return True
