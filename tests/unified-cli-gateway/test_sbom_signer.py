"""Unit tests for SLSA Provenance Attestation & CycloneDX SBOM Signer."""

import io
import json
import sys
import unittest

from elmos_cli.dispatcher import main
from elmos_formal_assurance.sbom_attestation_signer import (
    SbomAttestationSigner,
    sign_artifact_sbom,
)


class SbomAttestationSignerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signer = SbomAttestationSigner()

    def test_generate_cyclonedx_sbom(self) -> None:
        sbom = self.signer.generate_cyclonedx_sbom("payment-gateway.jar")
        self.assertEqual(sbom["bomFormat"], "CycloneDX")
        self.assertEqual(sbom["specVersion"], "1.5")
        self.assertEqual(sbom["metadata"]["component"]["name"], "payment-gateway.jar")
        self.assertTrue(len(sbom["components"]) >= 4)
        names = [c["name"] for c in sbom["components"]]
        self.assertIn("lean4", names)
        self.assertIn("z3", names)

    def test_sign_slsa_provenance(self) -> None:
        stmt = self.signer.sign_slsa_provenance("payment-gateway.jar")
        self.assertEqual(stmt.statement_type, "https://in-toto.io/Statement/v0.1")
        self.assertEqual(stmt.predicate_type, "https://slsa.dev/provenance/v1")
        self.assertEqual(stmt.subject[0]["name"], "payment-gateway.jar")
        self.assertIn("builder", stmt.predicate)
        self.assertIn("signature_value", stmt.__dict__)
        self.assertTrue(len(stmt.signature_value) > 10)

    def test_cli_assurance_sign_sbom(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["assurance", "sign-sbom", "--artifact", "my-app.jar", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "SIGNED_SUCCESS")
            self.assertEqual(data["artifact_name"], "my-app.jar")
            self.assertIn("cyclonedx_sbom", data)
            self.assertIn("slsa_provenance", data)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
