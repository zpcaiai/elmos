"""Unit tests for SLSA Provenance Attestation & CycloneDX SBOM Signer."""

import io
import json
import sys
import unittest

from elmos_cli.dispatcher import main
from elmos_formal_assurance.sbom_attestation_signer import (
    HmacLocalAttestationSigner,
    SbomComponent,
    SbomAttestationSigner,
    sign_artifact_sbom,
)


class SbomAttestationSignerTests(unittest.TestCase):
    def setUp(self) -> None:
        digest = "sha256:" + "a" * 64
        self.component = SbomComponent(
            name="z3",
            version="4.12.2",
            purl="pkg:generic/z3@4.12.2",
            component_type="library",
            hashes={"SHA-256": digest},
        )
        self.local_signer = HmacLocalAttestationSigner(b"k" * 32, key_id="test-key")
        self.signer = SbomAttestationSigner(self.local_signer)
        self.kwargs = {
            "artifact_name": "payment-gateway.jar",
            "artifact_version": "1.0.0",
            "artifact_digest": digest,
            "components": [self.component],
            "issued_at": "2026-08-31T00:00:00Z",
        }

    def test_generate_cyclonedx_sbom(self) -> None:
        sbom = self.signer.generate_cyclonedx_sbom(**self.kwargs)
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertEqual(sbom["metadata"]["component"]["name"], "payment-gateway.jar")
        self.assertEqual(len(sbom["components"]), 1)
        names = [c["name"] for c in sbom["components"]]
        self.assertIn("z3", names)

    def test_sign_slsa_provenance(self) -> None:
        stmt = self.signer.sign_slsa_provenance(
            artifact_name="payment-gateway.jar",
            artifact_digest=self.kwargs["artifact_digest"],
            builder_id="builder://test",
            build_type="https://example.test/build",
            invocation_digest="sha256:" + "b" * 64,
            environment_digest="sha256:" + "c" * 64,
            materials=[{"uri": "pkg:generic/source@1", "sha256": "sha256:" + "d" * 64}],
            issued_at=self.kwargs["issued_at"],
        )
        self.assertEqual(stmt.statement["_type"], "https://in-toto.io/Statement/v1")
        self.assertEqual(stmt.statement["predicateType"], "https://slsa.dev/provenance/v1")
        self.assertEqual(stmt.statement["subject"][0]["name"], "payment-gateway.jar")
        self.assertIn("builder", stmt.statement["predicate"]["runDetails"])
        self.assertIsNotNone(stmt.signature)
        self.assertEqual(stmt.evidence_classification, "LOCAL_EXECUTED_SELF_ATTESTED")

    def test_cli_assurance_sign_sbom(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["assurance", "sign-sbom", "--artifact", "my-app.jar", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "NOT_RUN")
            self.assertIn("artifact_version", data["required_inputs"])
            self.assertEqual(data["certification_status"], "NOT_CERTIFIED")
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
