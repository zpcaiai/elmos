from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "commercial" / "unit_economics.py"


def load_module():
    spec = importlib.util.spec_from_file_location("elmos_unit_economics", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unit_economics module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UnitEconomicsGateTest(unittest.TestCase):
    def test_empty_template_blocks_every_required_input_without_margin(self) -> None:
        module = load_module()
        result = module.check_fail_closed_contract()

        self.assertEqual("CHECK_PASSED", result["decision"])
        self.assertEqual("NOT_RUN", result["costValidationStatus"])
        self.assertEqual(len(module.REQUIRED_INPUTS), result["blockedInputCount"])
        self.assertFalse(result["marginProduced"])
        self.assertEqual([], result["errors"])

    def test_check_cli_is_machine_readable_and_successful(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--check", "--json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("CHECK_PASSED", payload["decision"])
        self.assertEqual("NOT_RUN", payload["costValidationStatus"])
        self.assertFalse(payload["marginProduced"])

    def test_check_cannot_be_combined_with_real_inputs(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--check", "--inputs", "costs.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("not allowed with argument", completed.stderr)


if __name__ == "__main__":
    unittest.main()
