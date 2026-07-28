import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch29"


class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_skill_bundle.py"), str(ROOT / ".agents/skills")], check=True
        )

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "templates").mkdir()
            # point scaffolder at bundle templates through its fallback
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_route.py"),
                    "--source",
                    "java",
                    "--target",
                    "csharp",
                    "--repo-root",
                    str(root),
                ],
                check=True,
            )
            route = root / "routes" / "java-to-csharp"
            data = json.loads((route / "route.json").read_text())
            data["owner"] = "test-owner"
            data["source"]["versions"] = ["21"]
            data["target"]["versions"] = ["13"]
            (route / "route.json").write_text(json.dumps(data, indent=2) + "\n")
            subprocess.run([sys.executable, str(SCRIPTS / "validate_route.py"), str(route)], check=True)

    def test_route_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "in.json"
            out = td / "out.json"
            inp.write_text(
                json.dumps(
                    {
                        "weights": {"customer_demand": 1.0},
                        "candidates": [
                            {"route_key": "java-to-csharp", "customer_demand": 4, "evidence_notes": ["customer"]}
                        ],
                    }
                )
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "score_routes.py"), str(inp), "--output", str(out)], check=True
            )
            self.assertEqual(json.loads(out.read_text())["results"][0]["decision"], "approve")

    def test_limited_route_gate_is_evidence_bound(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            passed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("status=limited decision=NOT_CERTIFIED", passed.stdout)

            evidence_path = route / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["execution_status"] = "NOT_RUN"
            evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
            blocked = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_route_gate.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("local execution evidence did not pass", blocked.stderr)

    def test_route_validator_rejects_manual_status_edit(self):
        with tempfile.TemporaryDirectory() as td:
            route = Path(td) / "python-to-typescript"
            shutil.copytree(ROOT / "routes" / "python-to-typescript", route)
            manifest_path = route / "route.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "certified"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_route.py"), str(route)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("route and certification statuses must match", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
