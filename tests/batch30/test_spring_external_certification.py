from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main


ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = ROOT / "scripts/operations/run_spring_external_gate.py"
SPRING_PACK_KEYS = (
    "spring-boot-1-5-to-3-5-3",
    "spring-boot-2-0-2-6-to-3-5-3",
    "spring-boot-2-7-18-to-3-5-3",
    "spring-boot-3-0-3-4-to-3-5-3",
    "spring-boot-2-x-gradle-to-3-5-3",
    "spring-framework-5-3-mvc-to-spring-boot-3-5-3",
)


class SpringExternalCertificationTests(TestCase):
    def test_all_six_packs_fail_closed_without_external_evidence(self) -> None:
        for pack_key in SPRING_PACK_KEYS:
            with self.subTest(pack=pack_key):
                pack = ROOT / "framework-packs" / pack_key
                manifest = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
                certification = json.loads(
                    (pack / "certification/certification.json").read_text(encoding="utf-8")
                )
                evidence = json.loads(
                    (pack / "certification/evidence.json").read_text(encoding="utf-8")
                )
                expected = (
                    "limited"
                    if pack_key == "spring-boot-2-7-18-to-3-5-3"
                    else "experimental"
                )
                self.assertEqual(expected, manifest["status"])
                self.assertEqual(expected, certification["status"])
                self.assertEqual("NOT_CERTIFIED", certification["certification_decision"])
                self.assertEqual("NOT_RUN", evidence["external_execution_status"])
                self.assertFalse((pack / "certification/external-admission.json").exists())

    def test_repository_does_not_hold_a_self_signed_dossier(self) -> None:
        self.assertFalse(
            (ROOT / "certification/dossiers/spring-modernization-v1").exists()
        )
        self.assertFalse(
            (ROOT / "certification/ethan-certifier/certifier-private.pem").exists()
        )
        trust = json.loads(
            (ROOT / "certification/trust-store.json").read_text(encoding="utf-8")
        )
        authorities = [
            item
            for item in trust["authorities"]
            if item.get("signer_id") == "ethan-independent-certifier"
        ]
        self.assertEqual(1, len(authorities))
        self.assertTrue(authorities[0]["revoked"])

    def test_external_gate_requires_an_out_of_repository_mount(self) -> None:
        missing = subprocess.run(
            [sys.executable, str(GATE_SCRIPT)], text=True, capture_output=True, check=False
        )
        self.assertEqual(2, missing.returncode)
        self.assertIn("--external-root", missing.stderr)

        in_repository = subprocess.run(
            [sys.executable, str(GATE_SCRIPT), "--external-root", str(ROOT)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, in_repository.returncode)
        self.assertIn("outside the repository", in_repository.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            empty_external = subprocess.run(
                [sys.executable, str(GATE_SCRIPT), "--external-root", temporary],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(1, empty_external.returncode)
        result = json.loads(empty_external.stdout)
        self.assertFalse(result["passed"])
        self.assertEqual("NOT_CERTIFIED", result["decision"])


if __name__ == "__main__":
    main()
