"""Implementation of B01: Evidence DAG, content-addressing, Ed25519 envelope verification, and invalidation."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .contracts import canonical_json_bytes


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    public_key_base64: str
    control_domain: str
    revoked: bool = False

    def load_public_key(self) -> Ed25519PublicKey:
        raw_bytes = base64.b64decode(self.public_key_base64)
        return Ed25519PublicKey.from_public_bytes(raw_bytes)


@dataclass(frozen=True)
class EvidenceBlob:
    content: bytes

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class EvidenceEnvelope:
    envelope_id: str
    key_id: str
    algorithm: str
    signature_base64: str
    payload: dict[str, Any]

    def verify(
        self,
        trusted_keys: Mapping[str, TrustedKey],
        blobs: Mapping[str, bytes],
        expected_revision_digest: str,
        now: int,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []

        if self.key_id not in trusted_keys:
            return False, [f"UNTRUSTED_SIGNER: {self.key_id}"]

        key = trusted_keys[self.key_id]
        if key.revoked:
            return False, [f"SIGNER_REVOKED: {self.key_id}"]

        # Signature check
        try:
            pub_key = key.load_public_key()
            canonical_bytes = canonical_json_bytes(self.payload)
            sig_bytes = base64.b64decode(self.signature_base64)
            pub_key.verify(sig_bytes, canonical_bytes)
        except (InvalidSignature, Exception) as exc:
            return False, [f"EVIDENCE_SIGNATURE_INVALID: {type(exc).__name__}"]

        # Timestamps
        issued_at = self.payload.get("issued_at", 0)
        expires_at = self.payload.get("expires_at", 0)
        if issued_at > now or expires_at <= now:
            reasons.append("EVIDENCE_STALE_OR_FUTURE")

        # Revision binding
        rev_digest = self.payload.get("revision_set_digest")
        if rev_digest != expected_revision_digest:
            reasons.append(f"REVISION_SET_MISMATCH: expected {expected_revision_digest}, got {rev_digest}")

        # Blob matching
        report_digest = self.payload.get("report_digest")
        if report_digest:
            if report_digest not in blobs:
                reasons.append(f"REPORT_BLOB_MISSING: {report_digest}")
            else:
                actual_blob_sha = hashlib.sha256(blobs[report_digest]).hexdigest()
                if actual_blob_sha != report_digest:
                    reasons.append(f"REPORT_DIGEST_MISMATCH: {actual_blob_sha} != {report_digest}")

        return (len(reasons) == 0), reasons


class EvidenceGraph:
    """Manages the DAG of verified evidence artifacts with invalidation propagation."""

    def __init__(self, revision_digest: str) -> None:
        self.revision_digest = revision_digest
        self.envelopes: dict[str, EvidenceEnvelope] = {}
        self.blobs: dict[str, bytes] = {}
        self.dependencies: dict[str, set[str]] = {}  # evidence_id -> set of prerequisite evidence_ids
        self.invalidated_evidence: set[str] = set()

    def add_blob(self, content: bytes) -> str:
        b = EvidenceBlob(content)
        d = b.digest
        self.blobs[d] = content
        return d

    def add_envelope(self, envelope: EvidenceEnvelope, depends_on: set[str] | None = None) -> None:
        eid = envelope.payload.get("evidence_id", envelope.envelope_id)
        self.envelopes[eid] = envelope
        self.dependencies[eid] = set(depends_on or ())

    def invalidate_node(self, root_evidence_id: str) -> set[str]:
        """Propagates invalidation down the DAG."""
        to_invalidate = {root_evidence_id}
        queue = [root_evidence_id]
        while queue:
            curr = queue.pop(0)
            for eid, deps in self.dependencies.items():
                if curr in deps and eid not in to_invalidate:
                    to_invalidate.add(eid)
                    queue.append(eid)
        self.invalidated_evidence.update(to_invalidate)
        return to_invalidate
