from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Any

from .canonical import validate_digest, validate_identifier
from .contracts import Scope, TrustedIdentity, utc_now
from .store import StateStore, StoreError


class GovernanceError(ValueError):
    """Raised when a governance mutation is unauthorised or malformed."""


class GovernanceAuthorizationError(PermissionError):
    """Raised when authenticated authority is insufficient for a mutation."""


_ADMIN_ROLES = frozenset({"admin", "formal-assurance-admin"})
_TCB_ROLES = frozenset({"formal-assurance-tcb-admin", *_ADMIN_ROLES})
_DRIFT_ROLES = frozenset({"formal-assurance-drift", *_ADMIN_ROLES})
_WAIVER_APPROVER_ROLES = frozenset(
    {
        "formal-assurance-waiver-approver",
        "formal-assurance-waiver-security",
        "formal-assurance-waiver-business",
        *_ADMIN_ROLES,
    }
)


def _timestamp(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise GovernanceError(f"{path} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise GovernanceError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise GovernanceError(f"{path} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _exact_fields(
    document: dict[str, Any], *, required: set[str], allowed: set[str], path: str
) -> None:
    missing = sorted(required - set(document))
    unknown = sorted(set(document) - allowed)
    if missing:
        raise GovernanceError(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        raise GovernanceError(f"{path} contains unknown fields: {', '.join(unknown)}")


def _tenant_scope(document: dict[str, Any], scope: Scope, path: str) -> None:
    tenant = document.get("tenant")
    if not isinstance(tenant, dict):
        raise GovernanceError(f"{path}.tenant must be an object")
    _exact_fields(
        tenant,
        required={"tenantId", "accountId"},
        allowed={"tenantId", "accountId", "projectId", "dataClassification"},
        path=f"{path}.tenant",
    )
    expected = {
        "tenantId": scope.tenant_id,
        "accountId": scope.account_id,
        "projectId": scope.project_id,
    }
    for key, value in expected.items():
        if tenant.get(key) != value:
            raise GovernanceError(f"{path}.tenant.{key} does not match trusted scope")
    classification = tenant.get("dataClassification")
    if classification is not None and classification != scope.data_classification:
        raise GovernanceError(
            f"{path}.tenant.dataClassification does not match trusted scope"
        )


def _artifact_ref(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GovernanceError(f"{path} must be an object")
    _exact_fields(
        value,
        required={"uri", "sha256", "mediaType"},
        allowed={
            "uri",
            "sha256",
            "mediaType",
            "sizeBytes",
            "encryptionKeyRef",
            "redacted",
        },
        path=path,
    )
    for field in ("uri", "mediaType"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise GovernanceError(f"{path}.{field} must be non-empty")
    validate_digest(value["sha256"], f"{path}.sha256")
    if "sizeBytes" in value and (
        not isinstance(value["sizeBytes"], int)
        or isinstance(value["sizeBytes"], bool)
        or value["sizeBytes"] < 0
    ):
        raise GovernanceError(f"{path}.sizeBytes is invalid")
    if "redacted" in value and not isinstance(value["redacted"], bool):
        raise GovernanceError(f"{path}.redacted must be boolean")
    return value


def _require_owner_or_admin(identity: TrustedIdentity, owner: Any, path: str) -> str:
    owner_id = validate_identifier(owner, path)
    if owner_id != identity.actor_id and not set(identity.roles) & _ADMIN_ROLES:
        raise GovernanceAuthorizationError(
            "governance owner must match the authenticated actor"
        )
    return owner_id


def _version() -> str:
    return f"v{time.time_ns()}"


class GovernanceService:
    """Fail-closed assumption, TCB, waiver and drift lifecycle service."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def register_assumption(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(document, dict):
            raise GovernanceError("assumption must be an object")
        required = {
            "id",
            "tenant",
            "statement",
            "riskLevel",
            "owner",
            "status",
            "hash",
            "createdAt",
        }
        allowed = required | {
            "formalExpression",
            "expiresAt",
            "monitorId",
            "evidence",
        }
        _exact_fields(document, required=required, allowed=allowed, path="assumption")
        _tenant_scope(document, scope, "assumption")
        identifier = validate_identifier(document["id"], "assumption.id")
        statement = document["statement"]
        if not isinstance(statement, str) or not statement.strip():
            raise GovernanceError("assumption.statement must be non-empty")
        risk = str(document["riskLevel"])
        if risk not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise GovernanceError("assumption.riskLevel is invalid")
        status = str(document["status"])
        if status not in {"PROPOSED", "ACTIVE", "VIOLATED", "EXPIRED", "REVOKED"}:
            raise GovernanceError("assumption.status is invalid")
        _require_owner_or_admin(identity, document["owner"], "assumption.owner")
        assumption_hash = validate_digest(document["hash"], "assumption.hash")
        created_at = _timestamp(document["createdAt"], "assumption.createdAt")
        if created_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise GovernanceError("assumption.createdAt is in the future")
        expiry = None
        if document.get("expiresAt") is not None:
            expiry = _timestamp(document["expiresAt"], "assumption.expiresAt")
            if expiry <= created_at:
                raise GovernanceError("assumption.expiresAt must follow createdAt")
        if risk in {"HIGH", "CRITICAL"}:
            if expiry is None or not document.get("monitorId"):
                raise GovernanceError(
                    "high-risk assumptions require owner, expiry and monitor"
                )
        monitor = document.get("monitorId")
        if monitor is not None:
            validate_identifier(monitor, "assumption.monitorId")
        evidence = document.get("evidence", [])
        if not isinstance(evidence, list):
            raise GovernanceError("assumption.evidence must be an array")
        for index, artifact in enumerate(evidence):
            _artifact_ref(artifact, f"assumption.evidence[{index}]")
        previous_hash: str | None = None
        try:
            previous = self.store.get_document(scope, "proof_assumption", identifier)
            previous_hash = validate_digest(
                previous["document"]["hash"], "storedAssumption.hash"
            )
        except StoreError:
            pass
        registration = self.store.put_document(
            scope,
            "proof_assumption",
            identifier,
            dict(document),
            version=_version(),
        )
        dependency = self.store.register_dependency(
            scope,
            subject_type="assumption",
            subject_id=identifier,
            dependency_kind="ASSUMPTION",
            dependency_id=identifier,
            dependency_hash=assumption_hash,
        )
        drift = None
        if previous_hash is not None and previous_hash != assumption_hash:
            drift = self.store.mark_dependency_drift(
                scope,
                dependency_kind="ASSUMPTION",
                dependency_id=identifier,
                new_hash=assumption_hash,
            )
        return {
            "assumptionId": identifier,
            "status": status,
            "hash": assumption_hash,
            "registration": registration,
            "dependency": dependency,
            "drift": drift,
            "certification": "NOT_CERTIFIED",
        }

    def register_trusted_component(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        if not set(identity.roles) & _TCB_ROLES:
            raise GovernanceAuthorizationError(
                "trusted component mutation requires TCB admin role"
            )
        if identity.authorization_ref is None:
            raise GovernanceAuthorizationError(
                "trusted component mutation requires authorizationRef"
            )
        if not isinstance(document, dict):
            raise GovernanceError("trusted component must be an object")
        required = {
            "id",
            "name",
            "componentType",
            "version",
            "digest",
            "trustReason",
            "status",
        }
        allowed = required | {
            "signatureRef",
            "sbomRef",
            "affectedProofCount",
        }
        _exact_fields(
            document,
            required=required,
            allowed=allowed,
            path="trustedComponent",
        )
        identifier = validate_identifier(document["id"], "trustedComponent.id")
        if document["componentType"] not in {
            "PARSER",
            "SEMANTICS",
            "ADAPTER",
            "SOLVER",
            "KERNEL",
            "COMPILER",
            "RUNTIME",
            "DATABASE",
            "EXTERNAL_CONTRACT",
        }:
            raise GovernanceError("trustedComponent.componentType is invalid")
        if document["status"] not in {
            "PROPOSED",
            "PINNED",
            "REVOKED",
            "VULNERABLE",
            "UNKNOWN",
        }:
            raise GovernanceError("trustedComponent.status is invalid")
        for field in ("name", "version", "trustReason"):
            if not isinstance(document[field], str) or not document[field].strip():
                raise GovernanceError(f"trustedComponent.{field} is required")
        signature_ref = document.get("signatureRef")
        if signature_ref is not None and (
            not isinstance(signature_ref, str) or not signature_ref.strip()
        ):
            raise GovernanceError("trustedComponent.signatureRef is invalid")
        if document.get("sbomRef") is not None:
            _artifact_ref(document["sbomRef"], "trustedComponent.sbomRef")
        component_digest = validate_digest(
            document["digest"], "trustedComponent.digest"
        )
        affected = document.get("affectedProofCount", 0)
        if not isinstance(affected, int) or isinstance(affected, bool) or affected < 0:
            raise GovernanceError("trustedComponent.affectedProofCount is invalid")
        previous_digest: str | None = None
        try:
            previous = self.store.get_document(scope, "trusted_component", identifier)
            previous_digest = validate_digest(
                previous["document"]["digest"], "storedComponent.digest"
            )
        except StoreError:
            pass
        registration = self.store.put_document(
            scope,
            "trusted_component",
            identifier,
            {**document, "authorizationRef": identity.authorization_ref},
            version=_version(),
        )
        dependency = self.store.register_dependency(
            scope,
            subject_type="trusted_component",
            subject_id=identifier,
            dependency_kind="TCB",
            dependency_id=identifier,
            dependency_hash=component_digest,
        )
        drift = None
        if previous_digest is not None and previous_digest != component_digest:
            drift = self.store.mark_dependency_drift(
                scope,
                dependency_kind="TCB",
                dependency_id=identifier,
                new_hash=component_digest,
            )
        return {
            "trustedComponentId": identifier,
            "status": document["status"],
            "digest": component_digest,
            "registration": registration,
            "dependency": dependency,
            "drift": drift,
            "certification": "NOT_CERTIFIED",
        }

    def propose_waiver(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(document, dict):
            raise GovernanceError("waiver must be an object")
        required = {
            "id",
            "tenant",
            "obligationId",
            "reason",
            "risk",
            "owner",
            "approvals",
            "createdAt",
            "expiresAt",
            "status",
        }
        allowed = required | {"compensatingControls"}
        _exact_fields(document, required=required, allowed=allowed, path="waiver")
        _tenant_scope(document, scope, "waiver")
        identifier = validate_identifier(document["id"], "waiver.id")
        validate_identifier(document["obligationId"], "waiver.obligationId")
        owner = _require_owner_or_admin(identity, document["owner"], "waiver.owner")
        if document["status"] != "PROPOSED":
            raise GovernanceAuthorizationError(
                "waivers must enter as PROPOSED; body-supplied approvals cannot activate risk"
            )
        if document["risk"] not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            raise GovernanceError("waiver.risk is invalid")
        if (
            not isinstance(document["reason"], str)
            or len(document["reason"].strip()) < 20
        ):
            raise GovernanceError("waiver.reason must contain at least 20 characters")
        controls = document.get("compensatingControls", [])
        if (
            not isinstance(controls, list)
            or not controls
            or any(not isinstance(item, str) or not item.strip() for item in controls)
        ):
            raise GovernanceError("waiver.compensatingControls must be non-empty")
        created = _timestamp(document["createdAt"], "waiver.createdAt")
        expires = _timestamp(document["expiresAt"], "waiver.expiresAt")
        if expires <= max(created, datetime.now(timezone.utc)):
            raise GovernanceError("waiver.expiresAt must be in the future")
        requested = document["approvals"]
        if not isinstance(requested, list) or len(requested) < 2:
            raise GovernanceError(
                "waiver.approvals must request at least two independent approvers"
            )
        requested_actors: set[str] = set()
        for index, item in enumerate(requested):
            if not isinstance(item, dict):
                raise GovernanceError(f"waiver.approvals[{index}] must be an object")
            _exact_fields(
                item,
                required={"approver", "role", "approvedAt"},
                allowed={"approver", "role", "approvedAt"},
                path=f"waiver.approvals[{index}]",
            )
            approver = validate_identifier(
                item.get("approver"), f"waiver.approvals[{index}].approver"
            )
            if approver == owner:
                raise GovernanceAuthorizationError(
                    "waiver owner cannot approve their own waiver"
                )
            if approver in requested_actors:
                raise GovernanceError("waiver requested approvers must be unique")
            requested_actors.add(approver)
            if not isinstance(item.get("role"), str) or not item["role"].strip():
                raise GovernanceError(f"waiver.approvals[{index}].role is required")
            _timestamp(item.get("approvedAt"), f"waiver.approvals[{index}].approvedAt")
        aggregate = {
            "format": "elmos-proof-waiver-lifecycle/v1",
            "waiver": dict(document),
            "state": "PROPOSED",
            "trustedApprovals": [],
            "bodyApprovalClaimsTrusted": False,
            "createdBy": identity.actor_id,
            "createdAt": utc_now(),
        }
        registration = self.store.put_document(
            scope, "proof_waiver", identifier, aggregate, version=_version()
        )
        return {
            "waiverId": identifier,
            "state": "PROPOSED",
            "trustedApprovalCount": 0,
            "registration": registration,
            "certificationOverride": False,
        }

    def approve_waiver(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        waiver_id: str,
        approval_role: str,
    ) -> dict[str, Any]:
        waiver_id = validate_identifier(waiver_id, "waiverId")
        if not set(identity.roles) & _WAIVER_APPROVER_ROLES:
            raise GovernanceAuthorizationError(
                "waiver approval requires an approver role"
            )
        if identity.authorization_ref is None:
            raise GovernanceAuthorizationError(
                "waiver approval requires authorizationRef"
            )
        if not isinstance(approval_role, str) or not approval_role.strip():
            raise GovernanceError("approval role is required")
        if (
            approval_role not in identity.roles
            and not set(identity.roles) & _ADMIN_ROLES
        ):
            raise GovernanceAuthorizationError(
                "approval role is not bound to authenticated identity"
            )
        stored = self.store.get_document(scope, "proof_waiver", waiver_id)
        aggregate = stored["document"]
        if (
            not isinstance(aggregate, dict)
            or aggregate.get("format") != "elmos-proof-waiver-lifecycle/v1"
        ):
            raise GovernanceError("stored waiver lifecycle is invalid")
        if aggregate.get("state") not in {"PROPOSED", "APPROVED"}:
            raise GovernanceError("waiver is not approvable")
        waiver = aggregate.get("waiver")
        if not isinstance(waiver, dict):
            raise GovernanceError("stored waiver document is invalid")
        if identity.actor_id == waiver.get("owner"):
            raise GovernanceAuthorizationError(
                "waiver owner cannot approve their own waiver"
            )
        if _timestamp(waiver.get("expiresAt"), "waiver.expiresAt") <= datetime.now(
            timezone.utc
        ):
            raise GovernanceError("expired waiver cannot be approved")
        approvals = list(aggregate.get("trustedApprovals", []))
        if any(item.get("approver") == identity.actor_id for item in approvals):
            raise GovernanceError("approver has already recorded a decision")
        approvals.append(
            {
                "approver": identity.actor_id,
                "role": approval_role,
                "approvedAt": utc_now(),
                "authorizationRef": identity.authorization_ref,
            }
        )
        actors = {item["approver"] for item in approvals}
        roles = {item["role"] for item in approvals}
        state = "APPROVED" if len(actors) >= 2 and len(roles) >= 2 else "PROPOSED"
        updated = {
            **aggregate,
            "state": state,
            "trustedApprovals": approvals,
            "updatedAt": utc_now(),
        }
        registration = self.store.put_document(
            scope, "proof_waiver", waiver_id, updated, version=_version()
        )
        return {
            "waiverId": waiver_id,
            "state": state,
            "trustedApprovalCount": len(approvals),
            "fourEyes": len(actors) >= 2 and len(roles) >= 2,
            "registration": registration,
            "certificationOverride": False,
        }

    def revoke_waiver(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        waiver_id: str,
        reason: str,
    ) -> dict[str, Any]:
        waiver_id = validate_identifier(waiver_id, "waiverId")
        if not isinstance(reason, str) or len(reason.strip()) < 10:
            raise GovernanceError("waiver revocation reason is too short")
        stored = self.store.get_document(scope, "proof_waiver", waiver_id)
        aggregate = stored["document"]
        waiver = aggregate.get("waiver", {}) if isinstance(aggregate, dict) else {}
        if (
            identity.actor_id != waiver.get("owner")
            and not set(identity.roles) & _ADMIN_ROLES
        ):
            raise GovernanceAuthorizationError(
                "only the owner or an administrator may revoke a waiver"
            )
        updated = {
            **aggregate,
            "state": "REVOKED",
            "revokedBy": identity.actor_id,
            "revokedAt": utc_now(),
            "revocationReason": " ".join(reason.split()),
        }
        registration = self.store.put_document(
            scope, "proof_waiver", waiver_id, updated, version=_version()
        )
        return {
            "waiverId": waiver_id,
            "state": "REVOKED",
            "registration": registration,
            "certificationOverride": False,
        }

    def report_drift(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        if not set(identity.roles) & _DRIFT_ROLES:
            raise GovernanceAuthorizationError(
                "proof drift mutation requires drift role"
            )
        if identity.authorization_ref is None:
            raise GovernanceAuthorizationError(
                "proof drift mutation requires authorizationRef"
            )
        if not isinstance(document, dict):
            raise GovernanceError("drift event must be an object")
        _exact_fields(
            document,
            required={"dependencyKind", "dependencyId", "newHash"},
            allowed={"dependencyKind", "dependencyId", "newHash"},
            path="driftEvent",
        )
        return self.store.mark_dependency_drift(
            scope,
            dependency_kind=validate_identifier(
                document["dependencyKind"], "driftEvent.dependencyKind"
            ),
            dependency_id=validate_identifier(
                document["dependencyId"], "driftEvent.dependencyId"
            ),
            new_hash=validate_digest(document["newHash"], "driftEvent.newHash"),
        )


__all__ = [
    "GovernanceAuthorizationError",
    "GovernanceError",
    "GovernanceService",
]
