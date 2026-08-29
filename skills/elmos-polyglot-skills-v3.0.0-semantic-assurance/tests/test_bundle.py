from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_module("validate_bundle", ROOT / "scripts" / "validate_bundle.py")
        cls.manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

    def test_static_validator(self):
        result = self.validator.validate_bundle(ROOT)
        self.assertTrue(result.passed, "\n".join(result.errors))

    def test_skill_inventory(self):
        skills = self.manifest["skills"]
        self.assertEqual(64, len(skills))
        self.assertEqual(64, len({s["id"] for s in skills}))
        self.assertEqual(64, len({s["name"] for s in skills}))
        self.assertTrue(all(s["readiness"] == "not-run" for s in skills))

    def test_exact_technology_order(self):
        self.assertEqual(
            ["java","kotlin","python","csharp","go","rust","cpp","php","typescript","react","objc","swift","flutter","javascript"],
            self.manifest["technologies"],
        )

    def test_route_matrix(self):
        with (ROOT / "route-matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(196, len(rows))
        self.assertEqual(196, len({(r["source"], r["target"]) for r in rows}))
        self.assertTrue(all(r["readiness"] == "not-run" for r in rows))

    def test_reference_routes(self):
        registry = json.loads((ROOT / "route-registry.json").read_text(encoding="utf-8"))
        profiles = registry["spec"]["profiles"]
        self.assertEqual(18, len(profiles))
        self.assertTrue(all((ROOT / p["profile"]).exists() for p in profiles))

    def test_schema_inventory(self):
        schemas = list((ROOT / "schemas").glob("*.json"))
        self.assertEqual(15, len(schemas))
        for path in schemas:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", payload["$schema"])
            self.assertTrue(payload["title"])

    def test_cli_route(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "elmos_skills.py"),
             "route", "--source", "java", "--target", "csharp", "--json"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual("route-java-spring-to-csharp-aspnet-core", payload["profile"]["id"])
        self.assertEqual("not-run", payload["matrix"]["readiness"])

    def test_cli_scaffold_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "job.yaml"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "elmos_skills.py"),
                 "scaffold-job", "--source", "javascript", "--target", "typescript",
                 "--mode", "modernize", "--output", str(output)],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            text = output.read_text(encoding="utf-8")
            self.assertIn("source:\n  technology: javascript", text)
            self.assertIn("target:\n  technology: typescript", text)
            self.assertIn("readiness: not-run", text)


if __name__ == "__main__":
    unittest.main()
