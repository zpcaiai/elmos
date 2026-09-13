"""Verify externally issued Foundry invocation permits.

This module is verify-only.  It deliberately contains no private key, signing
helper, development bypass, or default trust decision.  A production host must
inject its signature verifier and an explicit issuer/key allowlist.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import time
from types import MappingProxyType

from .adapters import AdapterBinding, InvocationPermit, InvocationRequest, PermitVerifier
from .canonical import require_identifier
from .domain import TenantScope


PermitSignatureVerifier = Callable[[str, str, str, str], bool]


@dataclass(frozen=True, slots=True)
class SignedPermitTrustPolicy:
    """Pinned authorization issuers, keys, epoch, and revocations."""

    trusted_issuer_keys: Mapping[str, Sequence[str]]
    trust_epoch: int
    revoked_issuers: frozenset[str] = field(default_factory=frozenset)
    revoked_keys: frozenset[str] = field(default_factory=frozenset)
    revoked_authorizations: frozenset[str] = field(default_factory=frozenset)
    revoked_permits: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if (
            isinstance(self.trust_epoch, bool)
            or not isinstance(self.trust_epoch, int)
            or self.trust_epoch <= 0
        ):
            raise ValueError("trust_epoch must be a positive integer")
        if not isinstance(self.trusted_issuer_keys, Mapping):
            raise ValueError("trusted_issuer_keys must be a non-empty object")
        normalized: dict[str, tuple[str, ...]] = {}
        for issuer, raw_keys in self.trusted_issuer_keys.items():
            require_identifier(issuer, "permit issuer")
            if isinstance(raw_keys, (str, bytes)) or not isinstance(raw_keys, Sequence):
                raise ValueError("each permit issuer must have at least one trusted key")
            keys = tuple(sorted(set(raw_keys)))
            if not keys:
                raise ValueError("each permit issuer must have at least one trusted key")
            for key in keys:
                require_identifier(key, "permit issuer key")
            normalized[issuer] = keys
        if not normalized:
            raise ValueError("trusted_issuer_keys must be a non-empty object")
        object.__setattr__(self, "trusted_issuer_keys", MappingProxyType(normalized))
        for field_name in (
            "revoked_issuers",
            "revoked_keys",
            "revoked_authorizations",
            "revoked_permits",
        ):
            raw_values = getattr(self, field_name)
            if isinstance(raw_values, (str, bytes)):
                raise ValueError(f"{field_name} must be a set of identifiers")
            values = frozenset(raw_values)
            for value in values:
                require_identifier(value, field_name)
            object.__setattr__(self, field_name, values)


def build_signed_permit_verifier(
    *,
    policy: SignedPermitTrustPolicy,
    signature_verifier: PermitSignatureVerifier,
    clock: Callable[[], float] = time.time,
) -> PermitVerifier:
    """Build a fail-closed verifier for the complete signed permit body."""

    if not callable(signature_verifier):
        raise TypeError("signature_verifier must be callable")
    if not callable(clock):
        raise TypeError("clock must be callable")

    def verify(
        permit: InvocationPermit,
        binding: AdapterBinding,
        scope: TenantScope,
        request: InvocationRequest,
    ) -> bool:
        if (
            permit.issuer_id is None
            or permit.key_id is None
            or permit.trust_epoch is None
            or permit.permit_digest is None
            or permit.signature is None
        ):
            return False
        trusted_keys = policy.trusted_issuer_keys.get(permit.issuer_id)
        if not isinstance(trusted_keys, tuple) or permit.key_id not in trusted_keys:
            return False
        if (
            permit.issuer_id in policy.revoked_issuers
            or permit.key_id in policy.revoked_keys
            or permit.authorization_id in policy.revoked_authorizations
            or permit.permit_id in policy.revoked_permits
            or permit.trust_epoch != policy.trust_epoch
        ):
            return False
        now = int(clock())
        if permit.issued_at > now + 5 or now >= permit.expires_at:
            return False
        if permit.issuer_id == permit.actor_id:
            return False
        if permit.permit_digest != permit.signing_digest:
            return False
        expected = {
            "adapter_id": binding.adapter_id,
            "adapter_version": binding.version,
            "adapter_digest": binding.digest,
            "invocation_id": request.invocation_id,
            "broker_id": request.broker_id,
            "broker_version": request.broker_version,
            "broker_digest": request.broker_digest,
            "route_id": request.route_id,
            "route_digest": request.route_digest,
            "skill_name": request.skill_name,
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "actor_id": scope.actor_id,
            "effect_class": request.effect_class,
            "operation": request.operation,
            "payload_digest": request.payload_digest,
            "purpose": scope.purpose,
            "environment_id": scope.environment_id,
            "workspace_digest": scope.workspace_digest,
            "revision_set_id": scope.revision_set_id,
            "authorized_tools": request.allowed_tools,
            "authorized_gates": request.required_gates,
            "semantic_program_digest": request.semantic_program_digest,
        }
        if any(getattr(permit, key) != value for key, value in expected.items()):
            return False
        try:
            return signature_verifier(
                permit.issuer_id,
                permit.key_id,
                permit.permit_digest,
                permit.signature,
            ) is True
        except Exception:
            return False

    return verify


__all__ = [
    "PermitSignatureVerifier",
    "SignedPermitTrustPolicy",
    "build_signed_permit_verifier",
]
