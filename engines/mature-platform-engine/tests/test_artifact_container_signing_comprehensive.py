"""Comprehensive test suite for ArtifactContainerSigningEngine (B40 - Skill 1386)."""

import base64
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.artifact_container_signing_engine import (
    ArtifactContainerSigningEngine,
)
from elmos_mature_platform.types import (
    ArtifactKind,
    ArtifactSignatureRecord,
    SignatureAlgorithm,
    SignedArtifactManifest,
    SigningAdmissionVerdict,
)


class TestArtifactContainerSigningComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = ArtifactContainerSigningEngine(trust_domain="production.elmos.io")
        self.valid_sig_b64 = base64.b64encode(b"valid-cryptographic-signature-bytes-123456").decode("utf-8")
        self.dummy_digest = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_initialization(self):
        self.assertEqual(self.engine.trust_domain, "production.elmos.io")
        self.assertEqual(len(self.engine.get_audit_trail()), 0)

    def test_register_trusted_key(self):
        self.engine.register_trusted_key(
            key_id="key-rel-01",
            signer_identity="release-signer@elmos.io",
            algorithm=SignatureAlgorithm.ES256,
            public_key_pem="-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...",
        )
        self.assertIn("key-rel-01", self.engine._trusted_keys)
        trail = self.engine.get_audit_trail()
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["action"], "key_registered")

    def test_revoke_key_success_and_failure(self):
        self.engine.register_trusted_key(
            key_id="key-sec-01",
            signer_identity="security-team@elmos.io",
            algorithm=SignatureAlgorithm.ED25519,
        )
        # Successful revocation
        res = self.engine.revoke_key("key-sec-01", reason="Compromised HSM partition")
        self.assertTrue(res)
        self.assertIn("key-sec-01", self.engine._revoked_keys)

        # Revoking unknown key fails
        res2 = self.engine.revoke_key("unknown-key")
        self.assertFalse(res2)

    def test_register_and_get_manifest(self):
        manifest = SignedArtifactManifest(
            artifact_id="oci://registry.elmos.io/runner:v3.2.0",
            artifact_kind=ArtifactKind.OCI_CONTAINER_IMAGE,
            artifact_digest=self.dummy_digest,
            artifact_size_bytes=104857600,
        )
        self.engine.register_artifact_manifest(manifest)
        fetched = self.engine.get_manifest("oci://registry.elmos.io/runner:v3.2.0")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.artifact_size_bytes, 104857600)
        self.assertTrue(len(fetched.created_at) > 0)

    def test_get_nonexistent_manifest(self):
        self.assertIsNone(self.engine.get_manifest("oci://nonexistent"))

    def test_attach_signature_success(self):
        self.engine.register_trusted_key(
            key_id="k-1",
            signer_identity="builder@elmos.io",
            algorithm=SignatureAlgorithm.RS256,
        )
        manifest = SignedArtifactManifest(
            artifact_id="art-1",
            artifact_kind=ArtifactKind.RUNNER_BINARY,
            artifact_digest=self.dummy_digest,
            artifact_size_bytes=5242880,
        )
        self.engine.register_artifact_manifest(manifest)

        sig = self.engine.attach_signature(
            artifact_id="art-1",
            key_id="k-1",
            signer_identity="builder@elmos.io",
            algorithm=SignatureAlgorithm.RS256,
            signature_base64=self.valid_sig_b64,
            in_toto_statement_digest="sha256:in-toto-statement-12345",
        )
        self.assertIsNotNone(sig)
        self.assertEqual(sig.signed_digest, self.dummy_digest)
        self.assertEqual(len(manifest.signatures), 1)

    def test_attach_signature_to_missing_artifact(self):
        sig = self.engine.attach_signature(
            artifact_id="missing-art",
            key_id="k-1",
            signer_identity="builder@elmos.io",
            algorithm=SignatureAlgorithm.RS256,
            signature_base64=self.valid_sig_b64,
        )
        self.assertIsNone(sig)

    def test_attach_signature_with_revoked_key(self):
        self.engine.register_trusted_key("k-rev", "builder@elmos.io", SignatureAlgorithm.RS256)
        self.engine.revoke_key("k-rev", "test revocation")
        manifest = SignedArtifactManifest("art-rev", ArtifactKind.MIGRATION_RECIPE_BUNDLE, self.dummy_digest, 1024)
        self.engine.register_artifact_manifest(manifest)

        sig = self.engine.attach_signature("art-rev", "k-rev", "builder@elmos.io", SignatureAlgorithm.RS256, self.valid_sig_b64)
        self.assertIsNone(sig)
        self.assertEqual(len(manifest.signatures), 0)

    def test_revoke_signature(self):
        self.engine.register_trusted_key("k-sigrev", "builder@elmos.io", SignatureAlgorithm.RS256)
        manifest = SignedArtifactManifest("art-sigrev", ArtifactKind.RUNNER_BINARY, self.dummy_digest, 1024)
        self.engine.register_artifact_manifest(manifest)
        sig = self.engine.attach_signature("art-sigrev", "k-sigrev", "builder@elmos.io", SignatureAlgorithm.RS256, self.valid_sig_b64)
        self.assertIsNotNone(sig)
        self.assertFalse(sig.is_revoked)

        self.engine.revoke_signature(sig.signature_id, reason="Bad build pipeline run")
        self.assertTrue(sig.is_revoked)
        self.assertIn(sig.signature_id, self.engine._revoked_signatures)

    def test_evaluate_admission_missing_manifest(self):
        verdict = self.engine.evaluate_admission("nonexistent-art")
        self.assertFalse(verdict.admitted)
        self.assertIn("Artifact manifest not found", verdict.rejection_reasons)

    def test_evaluate_admission_fully_valid(self):
        self.engine.register_trusted_key("k-adm-1", "ci-builder@elmos.io", SignatureAlgorithm.ED25519)
        manifest = SignedArtifactManifest("art-adm", ArtifactKind.OCI_CONTAINER_IMAGE, self.dummy_digest, 4096)
        self.engine.register_artifact_manifest(manifest)
        self.engine.attach_signature(
            "art-adm",
            "k-adm-1",
            "ci-builder@elmos.io",
            SignatureAlgorithm.ED25519,
            self.valid_sig_b64,
            in_toto_statement_digest="sha256:in-toto-attest-99",
        )

        verdict = self.engine.evaluate_admission(
            artifact_id="art-adm",
            required_signers=["ci-builder@elmos.io"],
            min_signatures=1,
            require_in_toto_attestation=True,
        )
        self.assertTrue(verdict.admitted)
        self.assertTrue(verdict.signature_valid)
        self.assertTrue(verdict.required_signers_satisfied)
        self.assertTrue(verdict.not_revoked)
        self.assertEqual(len(verdict.rejection_reasons), 0)

    def test_evaluate_admission_untrusted_key(self):
        # Manifest with signature from key not in keystore
        manifest = SignedArtifactManifest("art-untrusted", ArtifactKind.RUNNER_BINARY, self.dummy_digest, 4096)
        sig = ArtifactSignatureRecord(
            signature_id="sig-untrusted",
            key_id="rogue-key-id",
            signer_identity="unknown@external.io",
            algorithm=SignatureAlgorithm.RS256,
            signature_base64=self.valid_sig_b64,
            signed_digest=self.dummy_digest,
            timestamp="2026-09-11T00:00:00Z",
        )
        manifest.signatures.append(sig)
        self.engine.register_artifact_manifest(manifest)

        verdict = self.engine.evaluate_admission("art-untrusted")
        self.assertFalse(verdict.admitted)
        self.assertTrue(any("untrusted" in r for r in verdict.rejection_reasons))

    def test_evaluate_admission_digest_mismatch(self):
        self.engine.register_trusted_key("k-dig", "signer@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-dig", ArtifactKind.OCI_CONTAINER_IMAGE, self.dummy_digest, 4096)
        sig = ArtifactSignatureRecord(
            signature_id="sig-dig",
            key_id="k-dig",
            signer_identity="signer@elmos.io",
            algorithm=SignatureAlgorithm.ES256,
            signature_base64=self.valid_sig_b64,
            signed_digest="sha256:different-tampered-digest-0000000000000000000",
            timestamp="2026-09-11T00:00:00Z",
        )
        manifest.signatures.append(sig)
        self.engine.register_artifact_manifest(manifest)

        verdict = self.engine.evaluate_admission("art-dig")
        self.assertFalse(verdict.admitted)
        self.assertTrue(any("digest mismatch" in r for r in verdict.rejection_reasons))

    def test_evaluate_admission_truncated_and_invalid_base64(self):
        self.engine.register_trusted_key("k-trunc", "signer@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-trunc", ArtifactKind.OCI_CONTAINER_IMAGE, self.dummy_digest, 4096)
        
        # Truncated (< 8 bytes)
        short_b64 = base64.b64encode(b"short").decode("utf-8")
        sig_trunc = ArtifactSignatureRecord(
            signature_id="sig-trunc",
            key_id="k-trunc",
            signer_identity="signer@elmos.io",
            algorithm=SignatureAlgorithm.ES256,
            signature_base64=short_b64,
            signed_digest=self.dummy_digest,
            timestamp="2026-09-11T00:00:00Z",
        )
        manifest.signatures.append(sig_trunc)
        self.engine.register_artifact_manifest(manifest)

        verdict = self.engine.evaluate_admission("art-trunc")
        self.assertFalse(verdict.admitted)
        self.assertTrue(any("payload is truncated" in r for r in verdict.rejection_reasons))

        # Invalid non-base64
        manifest.signatures.clear()
        sig_bad_b64 = ArtifactSignatureRecord(
            signature_id="sig-badb64",
            key_id="k-trunc",
            signer_identity="signer@elmos.io",
            algorithm=SignatureAlgorithm.ES256,
            signature_base64="not-valid-base64!!!",
            signed_digest=self.dummy_digest,
            timestamp="2026-09-11T00:00:00Z",
        )
        manifest.signatures.append(sig_bad_b64)
        verdict2 = self.engine.evaluate_admission("art-trunc")
        self.assertFalse(verdict2.admitted)
        self.assertTrue(any("not valid base64" in r for r in verdict2.rejection_reasons))

    def test_evaluate_admission_missing_in_toto_attestation(self):
        self.engine.register_trusted_key("k-in-toto", "signer@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-in-toto", ArtifactKind.MODEL_WEIGHT_BUNDLE, self.dummy_digest, 8192)
        self.engine.register_artifact_manifest(manifest)
        self.engine.attach_signature(
            "art-in-toto",
            "k-in-toto",
            "signer@elmos.io",
            SignatureAlgorithm.ES256,
            self.valid_sig_b64,
            in_toto_statement_digest="",  # Missing
        )

        verdict = self.engine.evaluate_admission(
            "art-in-toto",
            require_in_toto_attestation=True,
        )
        self.assertFalse(verdict.admitted)
        self.assertTrue(any("lacks required in-toto provenance attestation" in r for r in verdict.rejection_reasons))

    def test_evaluate_admission_insufficient_min_signatures(self):
        self.engine.register_trusted_key("k-m1", "signer1@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-min", ArtifactKind.OCI_CONTAINER_IMAGE, self.dummy_digest, 8192)
        self.engine.register_artifact_manifest(manifest)
        self.engine.attach_signature("art-min", "k-m1", "signer1@elmos.io", SignatureAlgorithm.ES256, self.valid_sig_b64)

        # Requires 2 signatures, only has 1
        verdict = self.engine.evaluate_admission("art-min", min_signatures=2)
        self.assertFalse(verdict.admitted)
        self.assertTrue(any("Insufficient valid signatures" in r for r in verdict.rejection_reasons))

    def test_evaluate_admission_missing_required_cosigners(self):
        self.engine.register_trusted_key("k-co1", "builder@elmos.io", SignatureAlgorithm.ES256)
        self.engine.register_trusted_key("k-co2", "qa-lead@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-cosign", ArtifactKind.OCI_CONTAINER_IMAGE, self.dummy_digest, 8192)
        self.engine.register_artifact_manifest(manifest)
        self.engine.attach_signature("art-cosign", "k-co1", "builder@elmos.io", SignatureAlgorithm.ES256, self.valid_sig_b64)

        # Requires both builder and qa-lead
        verdict = self.engine.evaluate_admission(
            "art-cosign",
            required_signers=["builder@elmos.io", "qa-lead@elmos.io"],
            min_signatures=2,
        )
        self.assertFalse(verdict.admitted)
        self.assertFalse(verdict.required_signers_satisfied)
        self.assertTrue(any("Missing required signers" in r for r in verdict.rejection_reasons))

    def test_evaluate_admission_revoked_key_and_signature(self):
        self.engine.register_trusted_key("k-rev-adm", "builder@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-rev-adm", ArtifactKind.OCI_CONTAINER_IMAGE, self.dummy_digest, 8192)
        self.engine.register_artifact_manifest(manifest)
        sig = self.engine.attach_signature("art-rev-adm", "k-rev-adm", "builder@elmos.io", SignatureAlgorithm.ES256, self.valid_sig_b64)
        
        # Revoke signature directly
        self.engine.revoke_signature(sig.signature_id)
        verdict = self.engine.evaluate_admission("art-rev-adm")
        self.assertFalse(verdict.admitted)
        self.assertFalse(verdict.not_revoked)

        # Reset signature revocation, revoke key instead
        self.engine._revoked_signatures.clear()
        sig.is_revoked = False
        self.engine.revoke_key("k-rev-adm")
        verdict2 = self.engine.evaluate_admission("art-rev-adm")
        self.assertFalse(verdict2.admitted)
        self.assertFalse(verdict2.not_revoked)

    def test_audit_trail_captures_all_lifecycle_events(self):
        self.engine.register_trusted_key("k-all", "dev@elmos.io", SignatureAlgorithm.ES256)
        manifest = SignedArtifactManifest("art-all", ArtifactKind.PROVENANCE_ATTESTATION, self.dummy_digest, 1024)
        self.engine.register_artifact_manifest(manifest)
        self.engine.attach_signature("art-all", "k-all", "dev@elmos.io", SignatureAlgorithm.ES256, self.valid_sig_b64)
        self.engine.evaluate_admission("art-all")
        self.engine.revoke_key("k-all")

        trail = self.engine.get_audit_trail()
        actions = [t["action"] for t in trail]
        self.assertIn("key_registered", actions)
        self.assertIn("manifest_registered", actions)
        self.assertIn("signature_attached", actions)
        self.assertIn("admission_evaluated", actions)
        self.assertIn("key_revoked", actions)


if __name__ == "__main__":
    unittest.main()
