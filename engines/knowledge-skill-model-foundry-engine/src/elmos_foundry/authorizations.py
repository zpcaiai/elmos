"""Trusted, request-bound authorization verification for local Foundry assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope


class AuthorizationBoundaryError(RuntimeError):
    """An operation lacks trusted, exact, current authorization."""


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Digest-bound request handed to a host-owned receipt verifier."""

    authorization_type: str
    receipt_digest: str
    request_digest: str
    context_digest: str
    tenant_id: str
    project_id: str
    actor_id: str

    def __post_init__(self) -> None:
        require_identifier(self.authorization_type, "authorization_type")
        validate_digest(self.receipt_digest, "receipt_digest")
        validate_digest(self.request_digest, "request_digest")
        validate_digest(self.context_digest, "context_digest")


class AuthorizationVerifier(Protocol):
    """Host trust boundary; implementations verify signature, expiry and revocation."""

    def __call__(self, request: AuthorizationRequest, scope: TenantScope) -> bool: ...


def require_authorization(
    verifier: AuthorizationVerifier | None,
    *,
    authorization_type: str,
    receipt_digest: str | None,
    request: Mapping[str, Any],
    scope: TenantScope,
) -> AuthorizationRequest:
    """Verify an authorization receipt against the exact request and host context."""

    require_identifier(authorization_type, "authorization_type")
    if not isinstance(receipt_digest, str):
        raise AuthorizationBoundaryError("authorization receipt digest is required")
    validate_digest(receipt_digest, "receipt_digest")
    normalized = canonical_value(request)
    if not isinstance(normalized, dict):
        raise AuthorizationBoundaryError("authorization request must be an object")
    request_digest = canonical_digest(
        {
            "schema_version": "elmos.foundry.authorization-request.v1",
            "authorization_type": authorization_type,
            "context_digest": scope.binding_digest,
            "request": normalized,
        }
    )
    bound = AuthorizationRequest(
        authorization_type=authorization_type,
        receipt_digest=receipt_digest,
        request_digest=request_digest,
        context_digest=scope.binding_digest,
        tenant_id=scope.tenant_id,
        project_id=scope.project_id,
        actor_id=scope.actor_id,
    )
    if verifier is None:
        raise AuthorizationBoundaryError(
            f"{authorization_type} requires a trusted receipt verifier"
        )
    try:
        accepted = verifier(bound, scope)
    except Exception as exc:
        raise AuthorizationBoundaryError(
            f"{authorization_type} verifier failed closed"
        ) from exc
    if accepted is not True:
        raise AuthorizationBoundaryError(
            f"{authorization_type} receipt was denied or did not match the request"
        )
    return bound


__all__ = [
    "AuthorizationBoundaryError",
    "AuthorizationRequest",
    "AuthorizationVerifier",
    "require_authorization",
]
