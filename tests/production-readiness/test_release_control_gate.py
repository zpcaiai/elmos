from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release_control/run_release_gate.py"
SPEC = importlib.util.spec_from_file_location("release_control_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseControlGateTest(unittest.TestCase):
    def test_finds_nested_certified_decision(self) -> None:
        payload = {"status": "PASSED", "domain": [{"decision": "CERTIFIED_INDEPENDENT"}]}
        self.assertEqual(
            MODULE.decisive_certified_values(payload),
            ["$.domain[0].decision=CERTIFIED_INDEPENDENT"],
        )

    def test_not_certified_is_not_a_positive_claim(self) -> None:
        payload = {"decision": "NOT_CERTIFIED", "external_execution": "NOT_RUN"}
        self.assertEqual(MODULE.decisive_certified_values(payload), [])

    def test_cyclonedx_preserves_unknown_version_as_explicit_property(self) -> None:
        inventory = {
            "finishedAt": "2026-09-13T00:00:00Z",
            "components": [{
                "ecosystem": "maven", "group": "example", "name": "demo",
                "version": None, "versionResolution": "managed-by-bom", "purl": "pkg:maven/example/demo",
            }],
        }
        bom = MODULE.make_cyclonedx(inventory, "0" * 40)
        self.assertEqual(bom["bomFormat"], "CycloneDX")
        self.assertNotIn("version", bom["components"][0])
        self.assertEqual(bom["metadata"]["properties"][1]["value"], "PARTIAL_LOCAL_INVENTORY_ONLY")


if __name__ == "__main__":
    unittest.main()
