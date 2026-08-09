from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch35"


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class FrontendFormalRouteGateTests(unittest.TestCase):
    def test_certified_pack_without_any_formal_campaign_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_verification_pack.py"),
                    "--pack-key",
                    "certified-without-formal-campaign",
                    "--migration-route",
                    "fixture-route",
                    "--workload-key",
                    "fixture-workload",
                    "--repo-root",
                    str(repository),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            pack = (
                repository / "verification-packs" / "certified-without-formal-campaign"
            )
            manifest = load(pack / "pack.json")
            manifest["status"] = "certified"
            manifest["owner"] = "formal-team"
            manifest["maintenance_owner"] = "formal-team"
            write(pack / "pack.json", manifest)
            certification = load(pack / "certification" / "certification.json")
            certification["status"] = "certified"
            certification["owner"] = "formal-team"
            write(pack / "certification" / "certification.json", certification)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_verification_gate.py"),
                    str(pack),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn(
                "certified pack must declare a strict formal route campaign",
                completed.stderr,
            )


if __name__ == "__main__":
    unittest.main()
