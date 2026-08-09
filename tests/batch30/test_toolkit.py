import hashlib
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

    def test_v2_supported_capabilities_require_exact_bindings(self):
        def missing_binding(capability):
            capability.pop("evidence_bindings")

        def unknown_fcm(capability):
            capability["fcm_capability_ids"] = ["missing-contract"]

        def wrong_semantic_fcm(capability):
            capability["fcm_capability_ids"] = ["health-lifecycle"]

        def drift_profile(capability):
            capability["target_profile_key"] = "wrong-profile"

        def missing_evidence(capability):
            capability["evidence_refs"] = ["certification/missing-evidence.json"]
            capability["evidence_bindings"][0]["path"] = "certification/missing-evidence.json"

        def drift_digest(capability):
            capability["evidence_bindings"][0]["sha256"] = "0" * 64

        def drift_bytes(capability):
            capability["evidence_bindings"][0]["bytes"] += 1

        cases = {
            "missing FCM binding": (
                lambda capability: capability.pop("fcm_capability_ids"),
                "supported capability lacks FCM bindings: web",
            ),
            "unknown FCM binding": (
                unknown_fcm,
                "supported capability references unknown or duplicate FCM ids: web: missing-contract",
            ),
            "wrong semantic FCM binding": (
                wrong_semantic_fcm,
                "supported capability FCM semantic binding mismatch: web",
            ),
            "target profile drift": (
                drift_profile,
                "supported capability target profile mismatch: web",
            ),
            "missing content binding": (
                missing_binding,
                "supported capability lacks content-addressed evidence bindings: web",
            ),
            "missing evidence file": (
                missing_evidence,
                "supported capability evidence binding web[0] path does not exist",
            ),
            "evidence digest drift": (
                drift_digest,
                "supported capability evidence binding web[0] sha256 mismatch",
            ),
            "evidence byte count drift": (
                drift_bytes,
                "supported capability evidence binding web[0] bytes mismatch",
            ),
        }
        for label, (mutate, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
                shutil.copytree(
                    ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                    pack,
                    ignore=shutil.ignore_patterns("target", "*.log"),
                )
                support_path = pack / "support-matrix.json"
                support = json.loads(support_path.read_text())
                web = next(item for item in support["capabilities"] if item["id"] == "web")
                mutate(web)
                support_path.write_text(json.dumps(support, indent=2) + "\n")

                rejected = subprocess.run(
                    [sys.executable, str(SCRIPTS / "validate_framework_pack.py"), str(pack)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
                self.assertIn(expected, rejected.stderr)

    def test_v2_supported_capabilities_require_semantic_evidence(self):
        def refresh_runtime_bindings(pack: Path) -> None:
            evidence_path = pack / "certification" / "local-reference-evidence.json"
            raw = evidence_path.read_bytes()
            support_path = pack / "support-matrix.json"
            support = json.loads(support_path.read_text())
            for capability in support["capabilities"]:
                for binding in capability.get("evidence_bindings", []):
                    if binding.get("role") == "runtime-equivalence":
                        binding["sha256"] = hashlib.sha256(raw).hexdigest()
                        binding["bytes"] = len(raw)
            support_path.write_text(json.dumps(support, indent=2) + "\n")

        def refresh_configuration_binding(pack: Path, role: str) -> None:
            support_path = pack / "support-matrix.json"
            support = json.loads(support_path.read_text())
            configuration = next(
                item for item in support["capabilities"] if item["id"] == "configuration"
            )
            binding = next(
                item for item in configuration["evidence_bindings"] if item["role"] == role
            )
            raw = (pack / binding["path"]).read_bytes()
            binding["sha256"] = hashlib.sha256(raw).hexdigest()
            binding["bytes"] = len(raw)
            support_path.write_text(json.dumps(support, indent=2) + "\n")

        cases = []

        def empty_obligations(pack: Path) -> None:
            fcm_path = pack / "contracts" / "framework-contract-model.json"
            fcm = json.loads(fcm_path.read_text())
            next(item for item in fcm["capabilities"] if item["id"] == "web-json-contract")[
                "obligations"
            ] = []
            fcm_path.write_text(json.dumps(fcm, indent=2) + "\n")

        cases.append(("empty FCM obligations", empty_obligations, "bound FCM capability has no semantic obligations"))

        def empty_source_traces(pack: Path) -> None:
            fcm_path = pack / "contracts" / "framework-contract-model.json"
            fcm = json.loads(fcm_path.read_text())
            next(item for item in fcm["capabilities"] if item["id"] == "web-json-contract")[
                "source_traces"
            ] = []
            fcm_path.write_text(json.dumps(fcm, indent=2) + "\n")

        cases.append(("empty FCM source traces", empty_source_traces, "bound FCM capability has no source traces"))

        def uncaptured_fcm(pack: Path) -> None:
            fcm_path = pack / "contracts" / "framework-contract-model.json"
            fcm = json.loads(fcm_path.read_text())
            next(item for item in fcm["capabilities"] if item["id"] == "web-json-contract")[
                "status"
            ] = "draft"
            fcm_path.write_text(json.dumps(fcm, indent=2) + "\n")

        cases.append(("uncaptured FCM", uncaptured_fcm, "bound FCM capability status must be captured"))

        def fcm_tuple_drift(pack: Path) -> None:
            fcm_path = pack / "contracts" / "framework-contract-model.json"
            fcm = json.loads(fcm_path.read_text())
            fcm["exact_tuple"]["version"] = "2.7.17"
            fcm_path.write_text(json.dumps(fcm, indent=2) + "\n")

        cases.append(("FCM source tuple drift", fcm_tuple_drift, "v2 FCM exact_tuple does not match"))

        def target_profile_drift(pack: Path) -> None:
            profile_path = pack / "target-profile" / "profile.json"
            profile = json.loads(profile_path.read_text())
            profile["runtime_versions"] = ["20"]
            profile_path.write_text(json.dumps(profile, indent=2) + "\n")

        cases.append(("target tuple drift", target_profile_drift, "v2 target profile does not match"))

        def runtime_build_failure(pack: Path) -> None:
            evidence_path = pack / "certification" / "local-reference-evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["source"]["build"] = "FAILED"
            evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
            refresh_runtime_bindings(pack)

        cases.append(("runtime build failure", runtime_build_failure, "runtime evidence source build must be PASSED"))

        def responses_differ(pack: Path) -> None:
            evidence_path = pack / "certification" / "local-reference-evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["target"]["runtime"]["responses"]["42"]["status"] = "DRIFTED"
            evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
            refresh_runtime_bindings(pack)

        cases.append(("web response drift", responses_differ, "web runtime evidence source/target responses differ"))

        def lifecycle_down(pack: Path) -> None:
            evidence_path = pack / "certification" / "local-reference-evidence.json"
            evidence = json.loads(evidence_path.read_text())
            evidence["target"]["runtime"]["health"]["status"] = "DOWN"
            evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
            refresh_runtime_bindings(pack)

        cases.append(("lifecycle health drift", lifecycle_down, "lifecycle runtime evidence target health must be UP"))

        def configuration_drift(pack: Path) -> None:
            properties = (
                pack
                / "corpus/development/migrated/src/main/resources/application.properties"
            )
            properties.write_text(
                properties.read_text().replace("server.shutdown=graceful", "server.shutdown=immediate")
            )
            refresh_configuration_binding(pack, "target-configuration")

        cases.append(("configuration content drift", configuration_drift, "configuration target-configuration content"))

        for label, mutate, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
                shutil.copytree(
                    ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                    pack,
                    ignore=shutil.ignore_patterns("target", "*.log"),
                )
                mutate(pack)
                rejected = subprocess.run(
                    [sys.executable, str(SCRIPTS / "validate_framework_pack.py"), str(pack)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
                self.assertIn(expected, rejected.stderr)

    def test_v1_support_matrix_remains_compatible(self):
        with tempfile.TemporaryDirectory() as td:
            pack = Path(td) / "spring-boot-2-7-18-to-3-5-3"
            shutil.copytree(
                ROOT / "framework-packs" / "spring-boot-2-7-18-to-3-5-3",
                pack,
                ignore=shutil.ignore_patterns("target", "*.log"),
            )
            support_path = pack / "support-matrix.json"
            support = json.loads(support_path.read_text())
            support["schema_version"] = 1
            for capability in support["capabilities"]:
                capability.pop("fcm_capability_ids", None)
                capability.pop("target_profile_key", None)
                capability.pop("evidence_bindings", None)
            support_path.write_text(json.dumps(support, indent=2) + "\n")

            accepted = subprocess.run(
                [sys.executable, str(SCRIPTS / "validate_framework_pack.py"), str(pack)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

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
