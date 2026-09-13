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
        self.assertIn("targets/pi/tsconfig.json", generated_files)
        self.assertIn("targets/pi/.editorconfig", generated_files)
        self.assertIn("targets/pi/.gitignore", generated_files)
        self.assertIn("targets/pi/README.md", generated_files)
        self.assertIn("targets/pi/.pi/settings.json", generated_files)
        self.assertIn("targets/pi/extensions/index.ts", generated_files)
        self.assertIn("targets/pi/prompts/system.md", generated_files)
        self.assertIn("targets/pi/tests/load_test.mjs", generated_files)
        self.assertIn("targets/pi/skills/security-linter/SKILL.md", generated_files)
        self.assertIn("targets/pi/skills/ast-analyzer/SKILL.md", generated_files)

        # Check extension code contents (path traversal security & 4 tools)
        file_contents = res.outputs["file_contents"]
        ext_code = file_contents["targets/pi/extensions/index.ts"]
        self.assertIn("assertSafePath", ext_code)
        self.assertIn("read_file", ext_code)
        self.assertIn("write_file", ext_code)
        self.assertIn("list_files", ext_code)
        self.assertIn("diagnostics", ext_code)

        # Check SKILL.md specification
        skill_doc = file_contents["targets/pi/skills/security-linter/SKILL.md"]
        self.assertIn("---", skill_doc)
        self.assertIn("name: security-linter", skill_doc)
        self.assertIn("## Operational Workflow", skill_doc)

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

    def test_pi_package_generation_disk_export(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            inputs = {
                "tenant_id": "tenant-corp-1",
                "project_id": "proj-agent-pi",
                "package_name": "disk-exported-pi",
                "version": "1.0.0",
                "target_dir": tmpdir,
                "skills": ["unit-test-runner"],
            }
            res = self.runtime.execute_skill("elmos-target-pi-package-generator", inputs)
            self.assertEqual(res.status, "SUCCESS")
            self.assertEqual(res.outputs.get("disk_export_status"), "SUCCESS")

            # Check physical files exist on disk
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "package.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "tsconfig.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, ".gitignore")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "README.md")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "extensions", "index.ts")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "skills", "unit-test-runner", "SKILL.md")))

    def test_pi_package_generation_fail_closed_tenant(self) -> None:
        res = self.runtime.execute_skill("elmos-target-pi-package-generator", {
            "tenant_id": "",
            "project_id": "p1",
        })
        self.assertEqual(res.status, "BLOCKED")
