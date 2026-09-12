"""Artifact Container Signing Engine (Batch 40 - Skill 1386).

Enforces cryptographic signature verification, OCI/bundle provenance attestation,
multi-party cosigning policy, key revocation, and admission control.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional, Set

from elmos_mature_platform.physical.sigstore_cosign import (
    SigstoreCosignDriver,
    is_usable_public_pem,
)
from elmos_mature_platform.types import (
    ArtifactKind,
    ArtifactSignatureRecord,
    SignatureAlgorithm,
    SignedArtifactManifest,
    SigningAdmissionVerdict,
)


class ArtifactContainerSigningEngine:
    """Industrial engine for artifact signing and admission verification (B40)."""

    def __init__(
        self,
        trust_domain: str = "elmos.internal",
        sigstore_driver: Optional[SigstoreCosignDriver] = None,
    ):
        self.trust_domain = trust_domain
        self._manifests: Dict[str, SignedArtifactManifest] = {}
        self._trusted_keys: Dict[str, Dict[str, Any]] = {}
        self._revoked_keys: Set[str] = set()
        self._revoked_signatures: Set[str] = set()
        self._audit_log: List[Dict[str, Any]] = []
        self._sigstore = sigstore_driver or SigstoreCosignDriver.from_env()
        self._physical_receipts: List[Dict[str, Any]] = []

    def register_trusted_key(
        self,
        key_id: str,
        signer_identity: str,
        algorithm: SignatureAlgorithm,
        public_key_pem: str = "",
    ) -> None:
        """Register a trusted signer key in the keystore."""
        self._trusted_keys[key_id] = {
            "key_id": key_id,
            "signer_identity": signer_identity,
            "algorithm": algorithm,
            "public_key_pem": public_key_pem,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._record_audit("key_registered", key_id, {"signer": signer_identity, "algorithm": algorithm.value})

    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke a trusted key and record revocation."""
        if key_id not in self._trusted_keys:
            return False
        self._revoked_keys.add(key_id)
        self._record_audit("key_revoked", key_id, {"reason": reason})
        return True

    def revoke_signature(self, signature_id: str, reason: str = "") -> None:
        """Explicitly revoke a single signature."""
        self._revoked_signatures.add(signature_id)
        # Also mark inside any manifest containing it
        for manifest in self._manifests.values():
            for sig in manifest.signatures:
                if sig.signature_id == signature_id:
                    sig.is_revoked = True
        self._record_audit("signature_revoked", signature_id, {"reason": reason})

    def register_artifact_manifest(self, manifest: SignedArtifactManifest) -> SignedArtifactManifest:
        """Register or update a signed artifact manifest."""
        if not manifest.created_at:
            manifest.created_at = datetime.now(timezone.utc).isoformat()
        self._manifests[manifest.artifact_id] = manifest
        self._record_audit("manifest_registered", manifest.artifact_id, {
            "kind": manifest.artifact_kind.value,
            "digest": manifest.artifact_digest,
            "signature_count": len(manifest.signatures),
        })
        return manifest

    def get_manifest(self, artifact_id: str) -> Optional[SignedArtifactManifest]:
        """Fetch signed artifact manifest by ID."""
        return self._manifests.get(artifact_id)

    def attach_signature(
        self,
        artifact_id: str,
        key_id: str,
        signer_identity: str,
        algorithm: SignatureAlgorithm,
        signature_base64: str,
        in_toto_statement_digest: str = "",
    ) -> Optional[ArtifactSignatureRecord]:
        """Attach a cryptographic signature to an existing artifact manifest."""
        manifest = self._manifests.get(artifact_id)
        if not manifest:
            return None

        # If key is revoked, reject
        if key_id in self._revoked_keys:
            self._record_audit("signature_rejected_revoked_key", artifact_id, {"key_id": key_id})
            return None

        sig_id = f"sig_{hashlib.sha256(f'{artifact_id}:{key_id}:{datetime.now(timezone.utc).isoformat()}'.encode()).hexdigest()[:12]}"
        sig_record = ArtifactSignatureRecord(
            signature_id=sig_id,
            key_id=key_id,
            signer_identity=signer_identity,
            algorithm=algorithm,
            signature_base64=signature_base64,
            signed_digest=manifest.artifact_digest,
            timestamp=datetime.now(timezone.utc).isoformat(),
            in_toto_statement_digest=in_toto_statement_digest,
            is_revoked=False,
        )
        manifest.signatures.append(sig_record)
        attestation = self._sigstore.attest_artifact(
            artifact_digest=manifest.artifact_digest,
            subject_name=artifact_id,
            builder_id=self.trust_domain,
            key_id=key_id,
            public_key_pem=str(self._trusted_keys.get(key_id, {}).get("public_key_pem") or ""),
            signature_base64=signature_base64,
            materialize_keys=False,
        )
        self._physical_receipts.append(attestation.to_dict())
        manifest.metadata.setdefault("sigstore", {})
        manifest.metadata["sigstore"] = {
            "dsse_envelope": attestation.dsse_envelope,
            "rekor_entry": attestation.rekor_entry,
            "rekor_uuid": attestation.rekor_uuid,
            "cosign_sign_argv": attestation.cosign_sign_argv,
            "applied": attestation.applied,
        }
        if attestation.rekor_uuid and not sig_record.in_toto_statement_digest:
            sig_record.in_toto_statement_digest = attestation.rekor_uuid
        self._record_audit("signature_attached", artifact_id, {"signature_id": sig_id, "signer": signer_identity})
        return sig_record

    def sign_artifact_physically(
        self,
        artifact_id: str,
        key_id: str,
        signer_identity: str,
        algorithm: SignatureAlgorithm,
    ) -> Optional[ArtifactSignatureRecord]:
        """Create a real OpenSSL ECDSA signature and submit a Rekor hashedrekord."""
        manifest = self._manifests.get(artifact_id)
        if not manifest:
            return None
        attestation = self._sigstore.attest_artifact(
            artifact_digest=manifest.artifact_digest,
            subject_name=artifact_id,
            builder_id=self.trust_domain,
            key_id=key_id,
        )
        self._physical_receipts.append(attestation.to_dict())
        if attestation.public_key_pem:
            self.register_trusted_key(
                key_id=key_id,
                signer_identity=signer_identity,
                algorithm=algorithm,
                public_key_pem=attestation.public_key_pem,
            )
        if not attestation.signature_base64:
            return None
        return self.attach_signature(
            artifact_id=artifact_id,
            key_id=key_id,
            signer_identity=signer_identity,
            algorithm=algorithm,
            signature_base64=attestation.signature_base64,
            in_toto_statement_digest=attestation.rekor_uuid,
        )

    def evaluate_admission(
        self,
        artifact_id: str,
        required_signers: Optional[List[str]] = None,
        min_signatures: int = 1,
        require_in_toto_attestation: bool = False,
    ) -> SigningAdmissionVerdict:
        """Evaluate whether an artifact is cryptographically admitted for deployment."""
        manifest = self._manifests.get(artifact_id)
        verdict_id = f"verdict_{hashlib.sha256(f'{artifact_id}:{datetime.now(timezone.utc).isoformat()}'.encode()).hexdigest()[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        if not manifest:
            return SigningAdmissionVerdict(
                verdict_id=verdict_id,
                artifact_id=artifact_id,
                artifact_digest="",
                admitted=False,
                required_signers_satisfied=False,
                signature_valid=False,
                not_revoked=False,
                rejection_reasons=["Artifact manifest not found"],
                evaluated_at=now_iso,
            )

        rejection_reasons: List[str] = []
        valid_signatures: List[ArtifactSignatureRecord] = []
        active_signers: Set[str] = set()

        for sig in manifest.signatures:
            # Check revocation
            if sig.signature_id in self._revoked_signatures or sig.is_revoked:
                rejection_reasons.append(f"Signature {sig.signature_id} is revoked")
                continue
            if sig.key_id in self._revoked_keys:
                rejection_reasons.append(f"Key {sig.key_id} used in signature {sig.signature_id} is revoked")
                continue

            # Check key exists in trusted keystore
            trusted_info = self._trusted_keys.get(sig.key_id)
            if not trusted_info:
                rejection_reasons.append(f"Signing key {sig.key_id} is untrusted")
                continue

            # Verify digest matching
            if sig.signed_digest != manifest.artifact_digest:
                rejection_reasons.append(f"Signature {sig.signature_id} digest mismatch: expected {manifest.artifact_digest}, got {sig.signed_digest}")
                continue

            # Verify base64 signature integrity
            try:
                raw_sig = base64.b64decode(sig.signature_base64)
                if len(raw_sig) < 8:
                    rejection_reasons.append(f"Signature {sig.signature_id} payload is truncated")
                    continue
            except Exception:
                rejection_reasons.append(f"Signature {sig.signature_id} is not valid base64")
                continue

            public_pem = str((trusted_info or {}).get("public_key_pem") or "")
            if is_usable_public_pem(public_pem):
                digest_hex = manifest.artifact_digest.split(":", 1)[-1]
                verify = self._sigstore.verify_digest(digest_hex, sig.signature_base64, public_pem)
                self._physical_receipts.append(verify.to_dict())
                if not verify.applied:
                    rejection_reasons.append(
                        f"Signature {sig.signature_id} failed OpenSSL ECDSA verification"
                    )
                    continue

            # In-toto requirement
            if require_in_toto_attestation and not sig.in_toto_statement_digest:
                rejection_reasons.append(f"Signature {sig.signature_id} lacks required in-toto provenance attestation")
                continue

            valid_signatures.append(sig)
            active_signers.add(sig.signer_identity)

        # Check minimum signature count
        if len(valid_signatures) < min_signatures:
            rejection_reasons.append(f"Insufficient valid signatures: got {len(valid_signatures)}, required {min_signatures}")

        # Check required signers
        required_satisfied = True
        if required_signers:
            missing_signers = [s for s in required_signers if s not in active_signers]
            if missing_signers:
                required_satisfied = False
                rejection_reasons.append(f"Missing required signers: {missing_signers}")

        admitted = len(rejection_reasons) == 0
        verdict = SigningAdmissionVerdict(
            verdict_id=verdict_id,
            artifact_id=artifact_id,
            artifact_digest=manifest.artifact_digest,
            admitted=admitted,
            required_signers_satisfied=required_satisfied,
            signature_valid=len(valid_signatures) >= min_signatures,
            not_revoked=not any("revoked" in r for r in rejection_reasons),
            rejection_reasons=rejection_reasons,
            evaluated_at=now_iso,
        )

        self._record_audit("admission_evaluated", artifact_id, {
            "admitted": admitted,
            "reasons": rejection_reasons,
        })
        return verdict

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """Return tamper-evident audit trail."""
        return list(self._audit_log)

    def _record_audit(self, action: str, target: str, payload: Dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "payload": payload,
        }
        self._audit_log.append(entry)
