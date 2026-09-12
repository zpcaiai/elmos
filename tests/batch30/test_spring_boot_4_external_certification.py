from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = ROOT / "scripts/operations/run_spring_boot_4_external_gate.py"

SPRING_BOOT_4_PACK_KEYS = [
    "spring-boot-1-5-to-4-1-0",
    "spring-boot-2-0-2-6-to-4-1-0",
    "spring-boot-2-7-18-to-4-1-0",
    "spring-boot-3-0-3-4-to-4-1-0",
    "spring-boot-3-5-to-4-1-0",
    "spring-boot-2-x-gradle-to-4-1-0",
    "spring-framework-5-3-mvc-to-boot-4-1-0",
]


class SpringBoot4ExternalCertificationTests(TestCase):
    def test_all_seven_framework_packs_exist_and_certified(self) -> None:
        for pack_key in SPRING_BOOT_4_PACK_KEYS:
            with self.subTest(pack=pack_key):
                pack_dir = ROOT / "framework-packs" / pack_key
                self.assertTrue(pack_dir.is_dir(), f"Pack directory missing: {pack_dir}")

                manifest = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
                evidence = json.loads((pack_dir / "certification" / "evidence.json").read_text(encoding="utf-8"))
                certification = json.loads((pack_dir / "certification" / "certification.json").read_text(encoding="utf-8"))
                admission = json.loads((pack_dir / "certification" / "external-admission.json").read_text(encoding="utf-8"))

                self.assertEqual("certified", manifest.get("status"))
                self.assertEqual("certified", certification.get("status"))
                self.assertEqual("CERTIFIED", certification.get("certification_decision"))
                self.assertEqual("PASSED", evidence.get("external_execution_status"))
                self.assertEqual(13, len(admission.get("verified_evidence_types", [])))

    def test_zero_tolerance_invariants_across_all_packs(self) -> None:
        zero_fields = (
            "critical_data_regressions",
            "critical_security_regressions",
            "critical_transaction_regressions",
            "critical_unknowns",
            "silent_framework_drops",
            "duplicate_message_or_job_effects",
            "test_integrity_violations",
        )
        for pack_key in SPRING_BOOT_4_PACK_KEYS:
            with self.subTest(pack=pack_key):
                pack_dir = ROOT / "framework-packs" / pack_key
                evidence = json.loads((pack_dir / "certification" / "evidence.json").read_text(encoding="utf-8"))
                for field in zero_fields:
                    self.assertEqual(0, evidence.get(field), f"{pack_key} field {field} must be 0")

    def test_independent_dossier_cryptographic_signature(self) -> None:
        dossier_dir = ROOT / "certification" / "dossiers" / "spring-boot-4-modernization-v1"
        manifest_path = dossier_dir / "dossier-manifest.json"
        req_path = dossier_dir / "certification-request.json"
        sig_path = dossier_dir / "certification-request.sig"
        pub_key_path = ROOT / "certification" / "keys" / "ethan-independent-certifier.pub.pem"

        self.assertTrue(manifest_path.exists())
        self.assertTrue(req_path.exists())
        self.assertTrue(sig_path.exists())
        self.assertTrue(pub_key_path.exists())

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        req = json.loads(req_path.read_text(encoding="utf-8"))

        self.assertEqual(7, manifest.get("target_count"))
        self.assertEqual(manifest.get("dossier_sha256"), req.get("dossier_sha256"))
        self.assertEqual("ethan-independent-certifier", req.get("signer_id"))

        res = subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-verify",
                str(pub_key_path),
                "-signature",
                str(sig_path),
                str(req_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, res.returncode, f"Signature verification failed: {res.stderr}")

    def test_full_spring_boot_4_external_gate_script_execution(self) -> None:
        res = subprocess.run(
            [sys.executable, str(GATE_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            0,
            res.returncode,
            f"Spring Boot 4 external gate failed:\nStdout:\n{res.stdout}\nStderr:\n{res.stderr}",
        )
        self.assertIn("ALL 7 SPRING BOOT 4.X MODERNIZATION PRODUCTION ROUTES 100% CERTIFIED!", res.stdout)


if __name__ == "__main__":
    main()
