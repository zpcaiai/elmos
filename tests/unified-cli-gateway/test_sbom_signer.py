"""Unit tests for SLSA Provenance Attestation & CycloneDX SBOM Signer."""

import hashlib
import io
import json
import sys
import unittest
from datetime import datetime, timezone

from elmos_cli.dispatcher import main
from elmos_formal_assurance.sbom_attestation_signer import (
    HmacLocalAttestationSigner,
    SbomAttestationSigner,
    SbomComponent,
    sign_artifact_sbom,
)


class SbomAttestationSignerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.local_signer = HmacLocalAttestationSigner(
            b"test-secret-key-at-least-32-bytes-long!!", key_id="key-test"
        )
        self.signer = SbomAttestationSigner(signer=self.local_signer)
        self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_generate_cyclonedx_sbom(self) -> None:
        comp = SbomComponent(
            name="z3",
            version="4.12.2",
            purl="pkg:generic/z3@4.12.2",
            component_type="library",
            hashes={"SHA-256": "sha256:" + "0" * 64},
        )
        sbom = self.signer.generate_cyclonedx_sbom(
            artifact_name="payment-gateway.jar",
            artifact_version="1.0.0",
            artifact_digest="sha256:" + hashlib.sha256(b"payment-gateway").hexdigest(),
            components=[comp],
            issued_at=self.timestamp,
        )
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertEqual(sbom["metadata"]["component"]["name"], "payment-gateway.jar")
        self.assertEqual(len(sbom["components"]), 1)
        self.assertEqual(sbom["components"][0]["name"], "z3")

    def test_sign_slsa_provenance(self) -> None:
        stmt = self.signer.sign_slsa_provenance(
            artifact_name="payment-gateway.jar",
            artifact_digest="sha256:" + hashlib.sha256(b"payment-gateway").hexdigest(),
            builder_id="https://elmos.local/builder/v1",
            build_type="https://elmos.local/build/v1",
            invocation_digest="sha256:" + "1" * 64,
            environment_digest="sha256:" + "2" * 64,
            materials=[],
            issued_at=self.timestamp,
        )
        self.assertEqual(stmt.statement["_type"], "https://in-toto.io/Statement/v1")
        self.assertEqual(stmt.statement["predicateType"], "https://slsa.dev/provenance/v1")
        self.assertEqual(stmt.statement["subject"][0]["name"], "payment-gateway.jar")
        self.assertIn("builder", stmt.statement["predicate"]["runDetails"])
        self.assertIsNotNone(stmt.signature)
        self.assertTrue(len(stmt.signature.value) > 10)

    def test_cli_assurance_sign_sbom(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["assurance", "sign-sbom", "--artifact", "my-app.jar", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "LOCAL_EXECUTED_SELF_ATTESTED")
            self.assertEqual(data["artifactName"], "my-app.jar")
            self.assertIn("cycloneDxSbom", data)
            self.assertIn("provenance", data)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()

