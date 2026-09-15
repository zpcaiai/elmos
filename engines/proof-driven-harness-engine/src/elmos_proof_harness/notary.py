"""Industrial-grade Cryptographic Evidence Notary with Tamper-Evident Envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger("elmos_proof_harness.notary")


class NotaryError(Exception):
    """Base exception for notary operations."""


class SignatureVerificationError(NotaryError):
    """Raised when evidence signature or envelope digest is invalid or tampered with."""


@dataclass(frozen=True)
class NotarizedEvidenceEnvelope:
    envelope_id: str
    evidence_id: str
    evidence_type: str
    payload_digest: str
    notary_id: str
    timestamp: str
    algorithm: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "payload_digest": self.payload_digest,
            "notary_id": self.notary_id,
            "timestamp": self.timestamp,
            "algorithm": self.algorithm,
            "signature": self.signature,
        }

    @property
    def signing_content(self) -> bytes:
        """Deterministic byte representation of envelope metadata used for signing and verification."""
        fields = [
            self.envelope_id,
            self.evidence_id,
            self.evidence_type,
            self.payload_digest,
            self.notary_id,
            self.timestamp,
            self.algorithm,
        ]
        return "|".join(fields).encode("utf-8")


class CryptographicNotary:
    """Provides independent cryptographic sealing, signing, and verification of evidence."""

    def __init__(
        self,
        notary_id: str = "elmos-independent-notary-01",
        secret_key: bytes | None = None,
    ) -> None:
        self.notary_id = notary_id
        # Use provided HMAC key or generate a deterministic one
        self._key = secret_key or hashlib.sha256(f"notary-key-{notary_id}".encode("utf-8")).digest()

    def _sign_bytes(self, data: bytes) -> str:
        """Produce HMAC-SHA256 signature in URL-safe base64."""
        import hmac
        sig = hmac.new(self._key, data, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii")

    def notarize_evidence(
        self,
        evidence_id: str,
        evidence_type: str,
        payload: Mapping[str, Any] | str | bytes,
    ) -> NotarizedEvidenceEnvelope:
        """Compute canonical payload digest and sign evidence envelope."""
        if isinstance(payload, bytes):
            raw_bytes = payload
        elif isinstance(payload, str):
            raw_bytes = payload.encode("utf-8")
        else:
            raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

        payload_digest = hashlib.sha256(raw_bytes).hexdigest()
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        env_id = f"notary-env-{hashlib.sha256((evidence_id + ts).encode('utf-8')).hexdigest()[:16]}"

        temp_envelope = NotarizedEvidenceEnvelope(
            envelope_id=env_id,
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            payload_digest=payload_digest,
            notary_id=self.notary_id,
            timestamp=ts,
            algorithm="HMAC-SHA256",
            signature="",
        )

        signature = self._sign_bytes(temp_envelope.signing_content)

        return NotarizedEvidenceEnvelope(
            envelope_id=env_id,
            evidence_id=evidence_id,
            evidence_type=evidence_type,
            payload_digest=payload_digest,
            notary_id=self.notary_id,
            timestamp=ts,
            algorithm="HMAC-SHA256",
            signature=signature,
        )

    def verify_envelope(
        self,
        envelope: NotarizedEvidenceEnvelope,
        actual_payload: Mapping[str, Any] | str | bytes | None = None,
    ) -> bool:
        """Verify that envelope signature is valid and payload matches the sealed digest."""
        import hmac

        # 1. Verify digital signature over envelope fields
        expected_sig = self._sign_bytes(envelope.signing_content)
        if not hmac.compare_digest(expected_sig, envelope.signature):
            raise SignatureVerificationError(
                f"Digital signature verification failed for envelope {envelope.envelope_id}"
            )

        # 2. If payload is supplied, verify it matches payload_digest
        if actual_payload is not None:
            if isinstance(actual_payload, bytes):
                raw_bytes = actual_payload
            elif isinstance(actual_payload, str):
                raw_bytes = actual_payload.encode("utf-8")
            else:
                raw_bytes = json.dumps(actual_payload, sort_keys=True).encode("utf-8")

            actual_digest = hashlib.sha256(raw_bytes).hexdigest()
            if not hmac.compare_digest(actual_digest, envelope.payload_digest):
                raise SignatureVerificationError(
                    f"Payload digest mismatch for envelope {envelope.envelope_id}: "
                    f"expected {envelope.payload_digest}, got {actual_digest}"
                )

        return True
