"""Host-owned authority verification for commercial Skill invocations."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .canonical import canonical_json_bytes
from .contracts import (
    CapabilityLease,
    Invocation,
    ObligationStatus,
    PolicyDecision,
    PolicyEffect,
    utc_now,
)
from .errors import AuthorizationError, ContractError

_SIGNATURE_RE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AuthorityProof:
    key_id: str
    invocation_digest: str
    policy_digest: str
    lease_digest: str
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.key_id, str) or not self.key_id:
            raise ContractError("authority proof key_id is required")
        for name in ("invocation_digest", "policy_digest", "lease_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
                raise ContractError(f"authority proof {name} is invalid")
        if not isinstance(self.signature, str) or _SIGNATURE_RE.fullmatch(self.signature) is None:
            raise ContractError("authority proof signature is invalid")

    def signed_payload(self) -> dict[str, str]:
        return {
            "invocation_digest": self.invocation_digest,
            "key_id": self.key_id,
            "lease_digest": self.lease_digest,
            "policy_digest": self.policy_digest,
        }


class AuthorityVerifier(Protocol):
    """Trusted host seam; implementations must not consult Skill payloads."""

    def verify(
        self,
        invocation: Invocation,
        decision: PolicyDecision,
        lease: CapabilityLease,
        proof: AuthorityProof | None,
        *,
        now: datetime | None = None,
    ) -> None:
        ...


class AuthorityRevocationSource(Protocol):
    """Host-owned dynamic revocation seam."""

    def is_revoked(self, *, decision_id: str, lease_id: str) -> bool:
        ...


class DenyAllAuthorityVerifier:
    """Safe default used when the host did not configure authority."""

    def verify(
        self,
        invocation: Invocation,
        decision: PolicyDecision,
        lease: CapabilityLease,
        proof: AuthorityProof | None,
        *,
        now: datetime | None = None,
    ) -> None:
        raise AuthorizationError(
            "no trusted authority verifier is configured",
            code="AUTHORITY_VERIFIER_UNAVAILABLE",
        )


def _normalized_keys(keys: Mapping[str, bytes]) -> dict[str, bytes]:
    if not keys:
        raise ContractError("authority key set requires at least one key")
    normalized: dict[str, bytes] = {}
    for key_id, key in keys.items():
        if not isinstance(key_id, str) or not key_id:
            raise ContractError("authority key id is invalid")
        if not isinstance(key, bytes) or len(key) < 32:
            raise ContractError("authority keys must contain at least 32 bytes")
        normalized[key_id] = bytes(key)
    return normalized


def _hmac_signature(key: bytes, payload: Mapping[str, str]) -> str:
    mac = hmac.new(key, canonical_json_bytes(payload), hashlib.sha256).hexdigest()
    return "hmac-sha256:" + mac


class LocalHMACAuthoritySigner:
    """Explicit local/test-only signer kept outside the runtime verifier."""

    def __init__(self, keys: Mapping[str, bytes]) -> None:
        self._keys = _normalized_keys(keys)

    def mint_proof(
        self,
        key_id: str,
        invocation: Invocation,
        decision: PolicyDecision,
        lease: CapabilityLease,
    ) -> AuthorityProof:
        key = self._keys.get(key_id)
        if key is None:
            raise AuthorizationError("unknown authority key", code="UNKNOWN_AUTHORITY_KEY")
        unsigned = AuthorityProof(
            key_id=key_id,
            invocation_digest=invocation.digest,
            policy_digest=decision.digest,
            lease_digest=lease.digest,
            signature="hmac-sha256:" + ("0" * 64),
        )
        return AuthorityProof(
            key_id=key_id,
            invocation_digest=unsigned.invocation_digest,
            policy_digest=unsigned.policy_digest,
            lease_digest=unsigned.lease_digest,
            signature=_hmac_signature(key, unsigned.signed_payload()),
        )


class HMACAuthorityVerifier:
    """Verify-only bounded local authority for tests and offline engineering.

    Symmetric HMAC is not a production trust-root architecture.  Production
    hosts should inject a verify-only public-key/KMS implementation through the
    :class:`AuthorityVerifier` protocol and a dynamic revocation source.
    """

    def __init__(
        self,
        keys: Mapping[str, bytes],
        *,
        revoked_decision_ids: frozenset[str] = frozenset(),
        revoked_lease_ids: frozenset[str] = frozenset(),
        revocation_source: AuthorityRevocationSource | None = None,
    ) -> None:
        self._keys = _normalized_keys(keys)
        self._revoked_decisions = frozenset(revoked_decision_ids)
        self._revoked_leases = frozenset(revoked_lease_ids)
        self._revocation_source = revocation_source

    def verify(
        self,
        invocation: Invocation,
        decision: PolicyDecision,
        lease: CapabilityLease,
        proof: AuthorityProof | None,
        *,
        now: datetime | None = None,
    ) -> None:
        current = now or utc_now()
        if proof is None:
            raise AuthorizationError("authority proof is required", code="AUTHORITY_PROOF_REQUIRED")
        key = self._keys.get(proof.key_id)
        if key is None:
            raise AuthorizationError("unknown authority key", code="UNKNOWN_AUTHORITY_KEY")
        expected_digests = (invocation.digest, decision.digest, lease.digest)
        observed_digests = (proof.invocation_digest, proof.policy_digest, proof.lease_digest)
        if expected_digests != observed_digests:
            raise AuthorizationError("authority proof digest binding mismatch", code="AUTHORITY_BINDING_MISMATCH")
        expected_signature = _hmac_signature(key, proof.signed_payload())
        if not hmac.compare_digest(expected_signature, proof.signature):
            raise AuthorizationError("authority proof signature mismatch", code="AUTHORITY_SIGNATURE_INVALID")
        if decision.decision_id in self._revoked_decisions or lease.lease_id in self._revoked_leases:
            raise AuthorizationError("authority has been revoked", code="AUTHORITY_REVOKED")
        if self._revocation_source is not None and self._revocation_source.is_revoked(
            decision_id=decision.decision_id,
            lease_id=lease.lease_id,
        ):
            raise AuthorizationError("authority has been dynamically revoked", code="AUTHORITY_REVOKED")
        if decision.effect is not PolicyEffect.ALLOW:
            raise AuthorizationError("policy did not explicitly allow execution", code="POLICY_DENIED")
        if current < decision.decided_at or current >= decision.expires_at:
            raise AuthorizationError("policy decision is not active", code="POLICY_EXPIRED")
        if (
            decision.invocation_id != invocation.invocation_id
            or decision.scope_digest != invocation.scope.digest
            or decision.skill_id != invocation.skill_id
            or decision.action != invocation.action
        ):
            raise AuthorizationError("policy binding mismatch", code="POLICY_BINDING_MISMATCH")
        if decision.digest != lease.policy_decision_digest or decision.decision_id != lease.policy_decision_id:
            raise AuthorizationError("lease is not bound to the policy decision", code="LEASE_POLICY_MISMATCH")
        if any(item.mandatory and item.status is not ObligationStatus.SATISFIED for item in decision.obligations):
            raise AuthorizationError("mandatory policy obligations are not satisfied", code="OBLIGATION_UNSATISFIED")
        lease.assert_authorized(invocation, now=current)
