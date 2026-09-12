"""Comprehensive CLI tests for Functional Assurance & Certification Engine."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from elmos_functional_assurance.cli import main as cli_main


class TestCliComprehensive(unittest.TestCase):
    """Tests for all CLI commands, arguments, and failure modes."""

    def test_evaluate_with_inline_payload(self) -> None:
        payload = json.dumps({"measurand": "accuracy", "nominal_value": 0.95})
        code = cli_main([
            "evaluate",
            "--skill", "elmos-measurement-uncertainty-budget-engine",
            "--candidate-digest", "sha256:" + "a" * 64,
            "--payload", payload,
        ])
        self.assertEqual(code, 0)

    def test_evaluate_with_payload_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            pfile = tmp_path / "payload.json"
            pfile.write_text(json.dumps({"calibration_set_size": 200}), encoding="utf-8")

            code = cli_main([
                "evaluate",
                "--skill", "elmos-ai-conformal-coverage-certifier",
                "--candidate-digest", "sha256:" + "b" * 64,
                "--payload-file", str(pfile),
            ])
            self.assertEqual(code, 0)

    def test_evaluate_default_payload(self) -> None:
        code = cli_main([
            "evaluate",
            "--skill", "elmos-slo-error-budget-release-governor",
            "--candidate-digest", "sha256:" + "c" * 64,
        ])
        self.assertEqual(code, 0)

    def test_certify_with_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            cert_out = tmp_path / "campaign_cert.json"

            code = cli_main([
                "certify",
                "--candidate-digest", "sha256:" + "d" * 64,
                "--tenant-id", "TENANT_CLI_TEST",
                "--project-id", "PROJ_CLI_TEST",
                "--assurance-level", "E5",
                "--sector", "AVIATION",
                "--output", str(cert_out),
            ])
            self.assertEqual(code, 0)
            self.assertTrue(cert_out.exists())

            data = json.loads(cert_out.read_text(encoding="utf-8"))
            self.assertEqual(data["campaign_status"], "COMPLETED")
            self.assertEqual(data["certificate"]["assurance_level"], "E5")
            self.assertEqual(data["certificate"]["sector"], "AVIATION")

    def test_certify_sectors(self) -> None:
        for sector in ["MEDICAL", "AUTOMOTIVE", "RAIL", "FINANCIAL"]:
            code = cli_main([
                "certify",
                "--candidate-digest", "sha256:" + "e" * 64,
                "--assurance-level", "E4",
                "--sector", sector,
            ])
            self.assertEqual(code, 0)

    def test_verify_certificate_valid_and_tampered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            campaign_file = tmp_path / "campaign.json"

            # 1. Generate certificate
            code = cli_main([
                "certify",
                "--candidate-digest", "sha256:" + "f" * 64,
                "--assurance-level", "E4",
                "--output", str(campaign_file),
            ])
            self.assertEqual(code, 0)

            campaign_data = json.loads(campaign_file.read_text(encoding="utf-8"))
            cert_obj = campaign_data["certificate"]

            # Save single certificate
            single_cert_file = tmp_path / "valid_cert.json"
            single_cert_file.write_text(json.dumps(cert_obj), encoding="utf-8")

            # Verify valid certificate
            verify_code = cli_main([
                "verify-certificate",
                "--cert-file", str(single_cert_file),
            ])
            self.assertEqual(verify_code, 0)

            # 2. Tamper with certificate payload
            tampered_obj = dict(cert_obj)
            tampered_obj["subject_candidate_digest"] = "sha256:" + "0" * 64
            tampered_file = tmp_path / "tampered_cert.json"
            tampered_file.write_text(json.dumps(tampered_obj), encoding="utf-8")

            tampered_code = cli_main([
                "verify-certificate",
                "--cert-file", str(tampered_file),
            ])
            self.assertEqual(tampered_code, 1)

    def test_missing_subcommand_raises_system_exit(self) -> None:
        with self.assertRaises(SystemExit):
            cli_main([])

    def test_invalid_subcommand_raises_system_exit(self) -> None:
        with self.assertRaises(SystemExit):
            cli_main(["invalid-cmd"])

    def test_certify_missing_required_candidate_digest(self) -> None:
        with self.assertRaises(SystemExit):
            cli_main(["certify"])


if __name__ == "__main__":
    unittest.main()
