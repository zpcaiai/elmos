import unittest
from pathlib import Path
import sys

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
        controller = (root / (
            "apps/control-plane/src/main/java/io/elmos/controlplane/"
            "ExecutionJobController.java"
        )).read_text(encoding="utf-8")
        runtime_dockerfile = (root / (
            "apps/modernization-proof-worker/Dockerfile.runtime"
        )).read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
