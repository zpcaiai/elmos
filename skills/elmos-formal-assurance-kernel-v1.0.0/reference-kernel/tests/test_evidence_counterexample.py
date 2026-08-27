from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from elmos_formal_assurance.counterexample import to_scenario_dsl, to_pytest, CounterexampleError
from elmos_formal_assurance.evidence import build_manifest, verify_manifest

CEX = {
    "id":"cex-1","obligationId":"o-1","kind":"INPUT",
    "witness":{"amount":-1},"violatedProperty":"amount must be non-negative",
}

class EvidenceCounterexampleTests(unittest.TestCase):
    def test_manifest_verifies(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"a.txt").write_text("a")
            manifest = build_manifest([root/"a.txt"], root)
            self.assertEqual([], verify_manifest(manifest, root))

    def test_manifest_detects_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"a.txt").write_text("a")
            manifest = build_manifest([root/"a.txt"], root)
            (root/"a.txt").write_text("b")
            self.assertTrue(any("sha256 mismatch" in e for e in verify_manifest(manifest, root)))

    def test_manifest_detects_manifest_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/"a.txt").write_text("a")
            manifest = build_manifest([root/"a.txt"], root)
            manifest["files"][0]["sizeBytes"] = 999
            self.assertIn("manifest hash mismatch", verify_manifest(manifest, root))

    def test_scenario_dsl_contains_witness(self):
        dsl = to_scenario_dsl(CEX)
        self.assertIn('"amount": -1', dsl)
        self.assertIn("obligation o-1", dsl)

    def test_pytest_generation(self):
        code = to_pytest(CEX)
        compile(code, "<generated>", "exec")
        self.assertIn("test_cex_1", code)

    def test_missing_counterexample_field_fails(self):
        with self.assertRaises(CounterexampleError):
            to_scenario_dsl({"id":"x"})

if __name__ == "__main__":
    unittest.main()
