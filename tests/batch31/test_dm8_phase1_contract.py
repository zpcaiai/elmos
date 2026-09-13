import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts/batch31/validate_dm8_phase1_contract.py"
PACK = ROOT / "database-packs/postgresql-to-dm8"


class Dm8Phase1ContractTests(unittest.TestCase):
    def test_repository_contract_is_complete_but_not_externally_ready(self):
        structural = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(structural.returncode, 0, structural.stderr)
        self.assertIn("CERTIFICATION: NOT_CERTIFIED", structural.stdout)

        external = subprocess.run(
            [sys.executable, str(VALIDATOR), "--require-external-ready"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(external.returncode, 3, external.stderr)
        self.assertIn("runnerAttestationDigest", external.stdout)

    def test_missing_negative_surface_case_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            copied_pack = Path(directory) / PACK.name
            shutil.copytree(PACK, copied_pack)
            path = copied_pack / "corpus/development/dm8-phase1-cases.json"
            cases = json.loads(path.read_text())
            cases["surfaces"]["triggers"]["negative"] = []
            path.write_text(json.dumps(cases, indent=2) + "\n")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--pack-dir",
                    str(copied_pack),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "surface triggers requires positive and negative cases", result.stderr
            )


if __name__ == "__main__":
    unittest.main()
