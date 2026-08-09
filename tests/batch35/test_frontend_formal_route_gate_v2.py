from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/batch35/run_verification_gate.py"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def frozen_v2_pack_available(default: Path, environment_name: str) -> bool:
    configured = os.environ.get(environment_name)
    candidate = Path(configured).resolve() if configured else default
    campaign_path = (
        candidate / "formal-campaign/frontend-formal-route-campaign-v2.json"
    )
    try:
        campaign = load(campaign_path)
        driver = campaign["profiles"][0]["runtime_driver_contract"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False
    return (
        isinstance(driver, dict)
        and driver.get("observer_protocol")
        == "block-specific-runtime-observation-v1"
        and driver.get("native_required_not_run_blocks") == ["api-network"]
    )


class FrontendFormalRouteGateV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("ELMOS_FRONTEND_V2_VERIFICATION_PACK")
        cls.pack = (
            Path(configured).resolve()
            if configured
            else ROOT / "verification-packs/frontend-72-route-formal-equivalence-v2"
        )

    def run_gate(self, pack: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GATE), str(pack)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    @unittest.skipUnless(
        frozen_v2_pack_available(
            ROOT / "verification-packs/frontend-72-route-formal-equivalence-v2",
            "ELMOS_FRONTEND_V2_VERIFICATION_PACK",
        ),
        "frozen block-specific v2 pack has not been staged or published",
    )
    def test_experimental_gate_reports_five_dimensions_without_certifying(self) -> None:
        completed = self.run_gate(self.pack)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = load(self.pack / "certification/gate-result.json")
        self.assertEqual("PASSED", result["structural_status"])
        self.assertTrue(result["model_formal_ready"])
        self.assertFalse(result["browser_ready"])
        self.assertFalse(result["native_ready"])
        self.assertFalse(result["runtime_ready"])
        self.assertFalse(result["independent_ready"])
        self.assertFalse(result["certification_ready"])
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])

    @unittest.skipUnless(
        frozen_v2_pack_available(
            ROOT / "verification-packs/frontend-72-route-formal-equivalence-v2",
            "ELMOS_FRONTEND_V2_VERIFICATION_PACK",
        ),
        "frozen block-specific v2 pack has not been staged or published",
    )
    def test_certified_claim_fails_on_runtime_and_independent_gaps(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="frontend-v2-gate-negative-"
        ) as directory:
            pack = Path(directory) / "pack"
            shutil.copytree(self.pack, pack)
            manifest = load(pack / "pack.json")
            manifest["status"] = "certified"
            write(pack / "pack.json", manifest)
            certification = load(pack / "certification/certification.json")
            certification["status"] = "certified"
            write(pack / "certification/certification.json", certification)
            completed = self.run_gate(pack)
            self.assertEqual(2, completed.returncode)
            for field in (
                "browser_ready",
                "native_ready",
                "runtime_ready",
                "independent_ready",
                "certification_ready",
            ):
                self.assertIn(field, completed.stderr)


if __name__ == "__main__":
    unittest.main()
