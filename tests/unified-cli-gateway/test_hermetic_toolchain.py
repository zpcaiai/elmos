"""Unit tests for Hermetic Proof Environment & Nix Toolchain Generator."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_formal_assurance.hermetic_environment_builder import (
    HermeticToolchainBuilder,
    export_hermetic_toolchain,
)
from elmos_cli.dispatcher import main


class HermeticToolchainBuilderTests(unittest.TestCase):
    """Test Nix Flake, Dockerfile, and DevContainer generation."""

    def setUp(self) -> None:
        self.builder = HermeticToolchainBuilder()

    def test_toolchain_manifest(self) -> None:
        manifest = self.builder.get_manifest()
        self.assertEqual(manifest.lean_version, "4.8.0")
        self.assertEqual(manifest.dafny_version, "4.4.0")
        self.assertEqual(manifest.z3_version, "4.12.2")
        self.assertEqual(manifest.cvc5_version, "1.1.2")
        self.assertEqual(len(manifest.manifest_digest), 64)

    def test_export_nix_flake(self) -> None:
        res = export_hermetic_toolchain(format_type="nix")
        self.assertEqual(res["filename"], "flake.nix")
        self.assertIn("lean4", res["content"])
        self.assertIn("z3", res["content"])
        self.assertIn("cvc5", res["content"])

    def test_export_dockerfile(self) -> None:
        res = export_hermetic_toolchain(format_type="docker")
        self.assertEqual(res["filename"], "Dockerfile.hermetic-proof")
        self.assertIn("FROM ubuntu:24.04", res["content"])
        self.assertIn("LEAN_VERSION=4.8.0", res["content"])

    def test_export_devcontainer_json(self) -> None:
        res = export_hermetic_toolchain(format_type="devcontainer")
        self.assertEqual(res["filename"], ".devcontainer/devcontainer.json")
        cfg = json.loads(res["content"])
        self.assertIn("leanprover.lean4", cfg["customizations"]["vscode"]["extensions"])

    def test_cli_assurance_export_hermetic_toolchain(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["assurance", "export-hermetic-toolchain", "--toolchain-format", "nix", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["filename"], "flake.nix")
            self.assertIn("manifest", data)
        finally:

            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
