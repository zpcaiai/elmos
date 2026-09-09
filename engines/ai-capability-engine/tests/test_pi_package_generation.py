"""Tests for elmos-target-pi-package-generator materialization."""

from __future__ import annotations

import json
import unittest

from elmos_ai_capability.runtime import AICapabilityRuntime


class PiPackageGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = AICapabilityRuntime()

    def test_pi_package_generation_dispatch(self) -> None:
        inputs = {
            "tenant_id": "tenant-corp-1",
            "project_id": "proj-agent-pi",
            "package_name": "corp-analyzer-pi",
            "version": "1.2.0",
            "model": "claude-3-5-sonnet",
            "skills": ["security-linter", "ast-analyzer"],
            "allowed_capabilities": ["repo.read", "tool.echo", "git.log"],
        }
        res = self.runtime.execute_skill("elmos-target-pi-package-generator", inputs)

        self.assertEqual(res.status, "SUCCESS")
        self.assertTrue(res.evidence_digest.startswith("sha256:"))
        self.assertEqual(res.outputs["package_name"], "corp-analyzer-pi")
        self.assertEqual(res.outputs["version"], "1.2.0")
        self.assertEqual(res.outputs["status"], "materialized")

        # Verify generated files
        generated_files = res.outputs["generated_files"]
        self.assertIn("targets/pi/package.json", generated_files)
        self.assertIn("targets/pi/.pi/settings.json", generated_files)
        self.assertIn("targets/pi/extensions/index.ts", generated_files)
        self.assertIn("targets/pi/prompts/system.md", generated_files)
        self.assertIn("targets/pi/tests/load_test.mjs", generated_files)
        self.assertIn("targets/pi/skills/security-linter/SKILL.md", generated_files)
        self.assertIn("targets/pi/skills/ast-analyzer/SKILL.md", generated_files)

        # Check manifest contents
        manifest = res.outputs["pi_package_manifest"]
        self.assertEqual(manifest["name"], "corp-analyzer-pi")
        self.assertEqual(manifest["version"], "1.2.0")
        self.assertEqual(manifest["type"], "module")
        self.assertIn("@pi/sdk", manifest["dependencies"])
        self.assertIn("skills/security-linter/SKILL.md", manifest["pi"]["skills"])

        # Check settings
        settings = res.outputs["settings"]
        self.assertEqual(settings["model"], "claude-3-5-sonnet")
        self.assertIn("repo.read", settings["permissions"]["allowed"])
        self.assertIn("host.exec", settings["permissions"]["denied"])
        self.assertTrue(settings["sandbox"]["enabled"])

    def test_pi_package_generation_fail_closed_tenant(self) -> None:
        res = self.runtime.execute_skill("elmos-target-pi-package-generator", {
            "tenant_id": "",
            "project_id": "p1",
        })
        self.assertEqual(res.status, "BLOCKED")
