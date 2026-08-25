from __future__ import annotations

import json
import unittest

import yaml

from _support import ROOT


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.yaml_manifest = yaml.safe_load((ROOT / "skill-manifest.yaml").read_text(encoding="utf-8"))
        cls.json_manifest = json.loads((ROOT / "skill-manifest.json").read_text(encoding="utf-8"))

    def test_yaml_and_json_are_identical(self) -> None:
        self.assertEqual(self.yaml_manifest, self.json_manifest)

    def test_declared_counts_match(self) -> None:
        package = self.yaml_manifest["package"]
        self.assertEqual(package["skill_count"], len(self.yaml_manifest["skills"]))
        task_ids = [tid for skill in self.yaml_manifest["skills"] for tid in skill["task_ids"]]
        self.assertEqual(package["task_count"], len(task_ids))
        self.assertEqual(package["schema_count"], len(list((ROOT / "schemas").glob("*.schema.json"))))

    def test_runtime_locations_are_explicit(self) -> None:
        locations = self.yaml_manifest["package"]["runtime_locations"]
        self.assertEqual(locations["codex_repo"], ".agents/skills")
        self.assertEqual(locations["claude_code_repo"], ".claude/skills")

    def test_native_first_safety_defaults(self) -> None:
        defaults = self.yaml_manifest["defaults"]
        self.assertTrue(defaults["native_output_required"])
        self.assertEqual(defaults["webview_fallback"], "deny")
        self.assertEqual(defaults["full_page_canvas_fallback"], "deny")
        self.assertEqual(defaults["silent_feature_drop"], "deny")


if __name__ == "__main__":
    unittest.main()
