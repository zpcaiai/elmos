"""Unit tests for Hermetic Proof Environment & Nix Toolchain Generator."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_formal_assurance.hermetic_environment_builder import (
    ToolchainArtifact,
    ToolchainManifest,
    HermeticToolchainBuilder,
    export_hermetic_toolchain,
)
from elmos_cli.dispatcher import main


class HermeticToolchainBuilderTests(unittest.TestCase):
    """Test Nix Flake, Dockerfile, and DevContainer generation."""

    def setUp(self) -> None:
        digest = "sha256:" + "a" * 64
        self.manifest = ToolchainManifest(
            target_platform="darwin/arm64",
            base_image="ubuntu",
            base_image_digest=digest,
            nixpkgs_revision="b" * 40,
            nixpkgs_source_digest=digest,
            toolchains=(
                ToolchainArtifact("lean", "4.8.0", "/usr/bin/lean", digest),
                ToolchainArtifact("z3", "4.12.2", "/usr/bin/z3", digest),
            ),
        )
        self.builder = HermeticToolchainBuilder(self.manifest)

    def test_toolchain_manifest(self) -> None:
        manifest = self.builder.get_manifest()
        self.assertEqual(manifest.target_platform, "darwin/arm64")
        self.assertEqual(manifest.nixpkgs_revision, "b" * 40)
        self.assertEqual([item.name for item in manifest.toolchains], ["lean", "z3"])
        self.assertTrue(manifest.manifest_digest.startswith("sha256:"))

    def test_export_nix_flake(self) -> None:
        res = export_hermetic_toolchain(format_type="nix", manifest=self.manifest)
        self.assertEqual(res["filename"], "flake.nix")
        self.assertIn("Nix realization and digest checks are NOT_RUN", res["content"])
        self.assertIn(self.manifest.manifest_digest, res["content"])

    def test_export_dockerfile(self) -> None:
        res = export_hermetic_toolchain(format_type="docker", manifest=self.manifest)
        self.assertEqual(res["filename"], "Dockerfile.formal-toolchain-plan")
        self.assertIn("FROM ubuntu@sha256:", res["content"])
        self.assertIn("Image build/runtime verification is NOT_RUN", res["content"])

    def test_export_devcontainer_json(self) -> None:
        res = export_hermetic_toolchain(format_type="devcontainer", manifest=self.manifest)
        self.assertEqual(res["filename"], ".devcontainer/devcontainer.json")
        cfg = json.loads(res["content"])
        self.assertEqual(cfg["remoteUser"], "65532")
        self.assertIn("--network=none", cfg["runArgs"])

    def test_cli_assurance_export_hermetic_toolchain(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["assurance", "export-hermetic-toolchain", "--toolchain-format", "nix", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "NOT_RUN")
            self.assertEqual(data["required_input"], "ToolchainManifest")
        finally:

            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
