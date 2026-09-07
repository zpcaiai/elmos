"""Unit tests for Hermetic Proof Environment & Nix Toolchain Generator."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_formal_assurance.hermetic_environment_builder import (
    HermeticToolchainBuilder,
    ToolchainArtifact,
    ToolchainManifest,
    export_hermetic_toolchain,
)
from elmos_cli.dispatcher import main


class HermeticToolchainBuilderTests(unittest.TestCase):
    """Test Nix Flake, Dockerfile, and DevContainer generation."""

    def setUp(self) -> None:
        self.manifest = ToolchainManifest(
            target_platform="linux/amd64",
            base_image="docker.io/library/ubuntu",
            base_image_digest="0" * 64,
            nixpkgs_revision="a" * 40,
            nixpkgs_source_digest="b" * 64,
            toolchains=(
                ToolchainArtifact(
                    name="lean4",
                    version="4.8.0",
                    executable_path="/usr/bin/lean",
                    sha256="c" * 64,
                ),
                ToolchainArtifact(
                    name="z3",
                    version="4.12.2",
                    executable_path="/usr/bin/z3",
                    sha256="d" * 64,
                ),
            ),
        )
        self.builder = HermeticToolchainBuilder(self.manifest)

    def test_toolchain_manifest(self) -> None:
        manifest = self.builder.get_manifest()
        self.assertEqual(manifest.target_platform, "linux/amd64")
        self.assertEqual(manifest.base_image, "docker.io/library/ubuntu")
        self.assertEqual(len(manifest.toolchains), 2)
        self.assertTrue(manifest.manifest_digest.startswith("sha256:"))

    def test_export_nix_flake(self) -> None:
        res = export_hermetic_toolchain("nix", manifest=self.manifest)
        self.assertEqual(res["filename"], "flake.nix")
        self.assertIn("inputs.nixpkgs.url", res["content"])
        self.assertIn(self.manifest.nixpkgs_revision, res["content"])
        self.assertEqual(res["planStatus"], "GENERATED")
        self.assertEqual(res["nativeBuildStatus"], "NOT_RUN")

    def test_export_dockerfile(self) -> None:
        res = export_hermetic_toolchain("docker", manifest=self.manifest)
        self.assertEqual(res["filename"], "Dockerfile.formal-toolchain-plan")
        self.assertIn("FROM docker.io/library/ubuntu@sha256:", res["content"])
        self.assertIn("USER 65532:65532", res["content"])

    def test_export_devcontainer_json(self) -> None:
        res = export_hermetic_toolchain("devcontainer", manifest=self.manifest)
        self.assertEqual(res["filename"], ".devcontainer/devcontainer.json")
        cfg = json.loads(res["content"])
        self.assertIn("--network=none", cfg["runArgs"])
        self.assertEqual(cfg["containerEnv"]["ELMOS_ENVIRONMENT_CLAIM"], "PLAN_NOT_EXECUTED")

    def test_cli_assurance_export_hermetic_toolchain(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["assurance", "export-hermetic-toolchain", "--toolchain-format", "nix", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["filename"], "flake.nix")
            self.assertIn("manifest", data)
            self.assertEqual(data["planStatus"], "GENERATED")
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()

