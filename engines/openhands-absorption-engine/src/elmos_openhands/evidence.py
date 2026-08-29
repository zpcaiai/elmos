"""Evidence trust store and cryptographic verification for independent security reviews."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .errors import ContractViolation


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    algorithm: str
    key_id: str
    signature: str


@dataclass(frozen=True, slots=True)
class TrustKey:
    key_id: str
    actor_id: str
    role: str
    public_key_bytes: bytes


def ed25519_trust_key(
    raw_public_bytes: bytes,
    *,
    key_id: str,
    actor_id: str,
    role: str,
) -> TrustKey:
    return TrustKey(
        key_id=key_id,
        actor_id=actor_id,
        role=role,
        public_key_bytes=raw_public_bytes,
    )


class EvidenceTrustStore:
    def __init__(self, keys: Iterable[TrustKey] | Mapping[str, TrustKey]) -> None:
        if isinstance(keys, Mapping):
            self._keys = dict(keys)
        else:
            self._keys = {k.key_id: k for k in keys}

    def verify(
        self,
        data: bytes,
        envelope: SignatureEnvelope,
        *,
        required_role: str | None = None,
    ) -> str:
        trust_key = self._keys.get(envelope.key_id)
        if trust_key is None:
            raise ContractViolation(f"untrusted or missing key_id: {envelope.key_id}")
        if required_role and trust_key.role != required_role:
            raise ContractViolation(f"key role {trust_key.role} does not match required {required_role}")
        if envelope.algorithm != "Ed25519":
            raise ContractViolation(f"unsupported signature algorithm: {envelope.algorithm}")
        try:
            raw_sig = base64.b64decode(envelope.signature)
            public_key = Ed25519PublicKey.from_public_bytes(trust_key.public_key_bytes)
            public_key.verify(raw_sig, data)
        except (InvalidSignature, ValueError, TypeError) as e:
            raise ContractViolation(f"invalid signature: {e}") from e
        return trust_key.actor_id
