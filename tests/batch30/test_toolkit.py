import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "batch30"


class ToolkitTests(unittest.TestCase):
    def test_skill_bundle(self):
        subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_skill_bundle.py"), str(ROOT / ".agents" / "skills")],
            check=True,
        )

    def test_scaffold_and_validate(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "scaffold_framework_pack.py"),
                    "--source-framework",
                    "spring-boot",
                    "--target-framework",
                    "aspnet-core",
                    "--source-runtime",
                    "java",
                    "--target-runtime",
                    "dotnet",
                    "--repo-root",
                    str(repo),
                ],
                check=True,
            )
            pack = repo / "framework-packs" / "spring-boot-to-aspnet-core"
            manifest = json.loads((pack / "pack.json").read_text())
            manifest["owner"] = "framework-team"
            manifest["maintenance_owner"] = "framework-team"
            manifest["source"]["framework_versions"] = ["3.5.1"]
            manifest["source"]["runtime_versions"] = ["21"]
            manifest["target"]["framework_versions"] = ["10.0"]
            manifest["target"]["runtime_versions"] = ["10.0"]
            (pack / "pack.json").write_text(json.dumps(manifest, indent=2) + "\n")
            profile = json.loads((pack / "target-profile" / "profile.json").read_text())
            profile["owner"] = "framework-team"
            profile["framework_versions"] = ["10.0"]
            profile["runtime_versions"] = ["10.0"]
            profile["architecture_style"] = "controller-service-repository"
            profile["build"] = {"commands": ["dotnet build"], "toolchain_digests": ["sha256:test"]}
            profile["startup"] = {"command": "dotnet run", "health_check": "/health"}
            (pack / "target-profile" / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
            subprocess.run([sys.executable, str(SCRIPTS / "validate_framework_pack.py"), str(pack)], check=True)

    def test_framework_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "candidates.json"
            target = td / "result.json"
            source.write_text(
                json.dumps(
                    {
                        "weights": {"customer_demand": 1.0},
                        "candidates": [
                            {"pack_key": "spring-upgrade", "customer_demand": 4, "evidence_notes": ["customer"]}
                        ],
                    }
                )
            )
            subprocess.run(
                [sys.executable, str(SCRIPTS / "score_framework_packs.py"), str(source), "--output", str(target)],
                check=True,
            )
            self.assertEqual(json.loads(target.read_text())["results"][0]["decision"], "approve")

    def test_limited_framework_gate_is_evidence_bound(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
            shutil.copytree(
                ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                pack,
                ignore=shutil.ignore_patterns("target", "*.log"),
            )
            passed = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_framework_gate.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            self.assertIn("status=limited decision=NOT_CERTIFIED", passed.stdout)

            certification_path = pack / "certification" / "certification.json"
            certification = json.loads(certification_path.read_text())
            certification["gate_results"]["public_holdout"] = "NOT_RUN"
            certification_path.write_text(json.dumps(certification, indent=2) + "\n")
            blocked = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_framework_gate.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn(
                "limited pack requires public_holdout PASSED_LOCAL_ENGINEERING",
                blocked.stderr,
            )

    def test_framework_validator_rejects_manual_status_edit(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
            shutil.copytree(
                ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                pack,
                ignore=shutil.ignore_patterns("target", "*.log"),
            )
            manifest_path = pack / "pack.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "certified"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_framework_pack.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("pack and certification statuses must match", rejected.stderr)

    def test_certified_gate_rejects_status_only_external_claims(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
            shutil.copytree(
                ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                pack,
                ignore=shutil.ignore_patterns("target", "*.log"),
            )
            manifest_path = pack / "pack.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "certified"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

            support_path = pack / "support-matrix.json"
            support = json.loads(support_path.read_text())
            for capability in support["capabilities"]:
                if capability.get("status") == "supported":
                    capability["status"] = "certified"
            support_path.write_text(json.dumps(support, indent=2) + "\n")

            evidence_path = pack / "certification" / "evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["external_execution_status"] = "PASSED"
            evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")

            certification_path = pack / "certification" / "certification.json"
            certification = json.loads(certification_path.read_text())
            certification["status"] = "certified"
            certification["certification_decision"] = "CERTIFIED"
            for field in (
                "authorized_customer_repository",
                "customer_holdout",
                "rootless_runner",
                "rootless_transformer",
                "rootless_verifier",
                "independent_review",
            ):
                certification["gate_results"][field] = "PASSED"
            certification_path.write_text(json.dumps(certification, indent=2) + "\n")

            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_framework_gate.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
            self.assertIn(
                "certified status remains disabled: verified external intake is review-only",
                rejected.stderr,
            )

    def test_limited_gate_rejects_zero_test_public_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
            shutil.copytree(
                ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                pack,
                ignore=shutil.ignore_patterns("target", "*.log"),
            )
            public_path = pack / "certification" / "public-reference-route-evidence.json"
            public = json.loads(public_path.read_text())
            public["holdout_public_repository"]["target_tests"]["executed"] = 0
            public_path.write_text(json.dumps(public, indent=2) + "\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_framework_gate.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn(
                "public holdout target tests executed must be a positive integer",
                rejected.stderr,
            )

    def test_limited_gate_rejects_public_tuple_drift(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
            shutil.copytree(
                ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                pack,
                ignore=shutil.ignore_patterns("target", "*.log"),
            )
            public_path = pack / "certification" / "public-reference-route-evidence.json"
            public = json.loads(public_path.read_text())
            public["route"]["target_spring_boot"] = "3.5.4"
            public_path.write_text(json.dumps(public, indent=2) + "\n")
            rejected = subprocess.run(
                [sys.executable, str(SCRIPTS / "run_framework_gate.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("public evidence route target_spring_boot mismatch", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
