import unittest
from pathlib import Path
import sys
import json
import subprocess
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_modernization_proof_image as subject


class BuildModernizationProofImageTest(unittest.TestCase):
    def valid_inspect(self):
        return {
            "Os": "linux",
            "Architecture": "arm64",
            "Config": {
                "User": subject.EXPECTED_USER,
                "Entrypoint": subject.EXPECTED_ENTRYPOINT,
                "Labels": {"io.elmos.runner.capability": subject.EXPECTED_CAPABILITY},
            },
            "RepoDigests": [
                "localhost:5000/elmos/modernization-proof-worker@sha256:" + "a" * 64
            ],
        }

    def test_accepts_exact_non_root_image_contract(self):
        subject.validate_image_config(self.valid_inspect())

    def test_rejects_root_image(self):
        document = self.valid_inspect()
        document["Config"]["User"] = "0"
        with self.assertRaises(subject.BuildFailure):
            subject.validate_image_config(document)

    def test_selects_only_exact_repository_digest(self):
        reference = subject.select_repository_digest(
            self.valid_inspect(), "localhost:5000/elmos/modernization-proof-worker"
        )
        self.assertTrue(subject.IMMUTABLE_REFERENCE.fullmatch(reference))

    def test_mutable_tag_never_counts_as_immutable(self):
        self.assertIsNone(
            subject.IMMUTABLE_REFERENCE.fullmatch(
                "localhost:5000/elmos/modernization-proof-worker:latest"
            )
        )

    def test_missing_repository_digest_fails_closed(self):
        document = self.valid_inspect()
        document["RepoDigests"] = []
        with self.assertRaises(subject.BuildFailure):
            subject.select_repository_digest(
                document, "localhost:5000/elmos/modernization-proof-worker"
            )

    def test_image_capability_matches_control_plane_dispatch_contract(self):
        root = Path(__file__).resolve().parents[2]
        controller = (
            root
            / (
                "apps/control-plane/src/main/java/io/elmos/controlplane/"
                "ExecutionJobController.java"
            )
        ).read_text(encoding="utf-8")
        runtime_dockerfile = (
            root / ("apps/modernization-proof-worker/Dockerfile.runtime")
        ).read_text(encoding="utf-8")
        self.assertIn(
            f'new RuntimeProfile("modernization:execute", "{subject.EXPECTED_CAPABILITY}"',
            controller,
        )
        self.assertIn(
            f'io.elmos.runner.capability="{subject.EXPECTED_CAPABILITY}"',
            runtime_dockerfile,
        )

    def test_every_supported_platform_pins_runtime_apk_bytes_and_digest(self):
        self.assertEqual({"linux/arm64", "linux/amd64"}, set(subject.RUNTIME_APKS))
        for contracts in subject.RUNTIME_APKS.values():
            self.assertEqual(8, len(contracts))
            names = {contract[1] for contract in contracts}
            self.assertIn("openjdk21-jre-headless-21.0.11_p10-r0.apk", names)
            for repository, name, digest, byte_count in contracts:
                self.assertIn(repository, {"main", "community"})
                self.assertTrue(name.endswith(".apk"))
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
                self.assertGreater(byte_count, 1)

    def test_scout_scan_requires_a_real_empty_sarif_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "scout.sarif.json"
            report.write_text(json.dumps({"runs": [{"results": []}]}), encoding="utf-8")
            result = subject.classify_scout_scan(0, report)
        self.assertEqual("PASSED", result["status"])
        self.assertEqual(0, result["finding_count"])

    def test_scout_findings_fail_instead_of_passing_or_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "scout.sarif.json"
            report.write_text(
                json.dumps({"runs": [{"results": [{"ruleId": "CVE-test"}]}]}),
                encoding="utf-8",
            )
            result = subject.classify_scout_scan(2, report)
        self.assertEqual("FAILED", result["status"])
        self.assertEqual(1, result["finding_count"])

    def test_scout_auth_or_network_failure_stays_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "missing.sarif.json"
            result = subject.classify_scout_scan(1, report)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("DOCKER_SCOUT_REPORT_MISSING", result["reason"])

    def test_scout_login_failure_has_an_exact_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "missing.sarif.json"
            result = subject.classify_scout_scan(
                1,
                report,
                "Log in with your Docker ID or email address to use docker scout.",
            )
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("DOCKER_SCOUT_AUTHENTICATION_REQUIRED", result["reason"])

    def test_untracked_source_file_makes_worktree_dirty(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@elmos.invalid"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "ELMOS Test"], cwd=repository, check=True
            )
            tracked = repository / "tracked.txt"
            tracked.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "--quiet", "-m", "fixture"],
                cwd=repository,
                check=True,
            )
            self.assertTrue(subject.source_worktree_is_clean(repository))
            (repository / "untracked.txt").write_text("untracked\n", encoding="utf-8")
            self.assertFalse(subject.source_worktree_is_clean(repository))

    def test_local_registry_and_not_run_external_evidence_block_production(self):
        external = subject.initial_external_boundaries()
        artifact, production = subject.evaluate_readiness(
            repository="localhost:5000/elmos/worker",
            immutable_reference="localhost:5000/elmos/worker@sha256:" + "a" * 64,
            source_clean=True,
            image_contract={"status": "PASSED"},
            smoke={"status": "PASSED"},
            scan={"status": "PASSED"},
            external_boundaries=external,
        )
        self.assertEqual("READY_FOR_EXTERNAL_GATE", artifact["status"])
        self.assertEqual("NOT_READY", production["status"])
        self.assertIn("EXTERNAL_REGISTRY_NOT_CONFIGURED", production["blockers"])
        self.assertIn("REAL_CLOUD_PROVIDER_NOT_RUN", production["blockers"])

    def test_incomplete_external_boundary_map_fails_closed(self):
        with self.assertRaises(ValueError):
            subject.evaluate_readiness(
                repository="localhost:5000/elmos/worker",
                immutable_reference="localhost:5000/elmos/worker@sha256:" + "a" * 64,
                source_clean=True,
                image_contract={"status": "PASSED"},
                smoke={"status": "PASSED"},
                scan={"status": "PASSED"},
                external_boundaries={"REAL_CLOUD_PROVIDER": "NOT_RUN"},
            )


if __name__ == "__main__":
    unittest.main()
