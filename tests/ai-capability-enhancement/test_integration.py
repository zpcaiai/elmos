"""Integration tests for AI Capability Enhancement Skills package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_ai_capability_enhancement_skills.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("ai_capability_importer", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ai capability importer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def test_pinned_archive_and_digest(self) -> None:
        archive_path = self.tool.resolve_archive()
        digest = self.tool.verify_archive(archive_path)
        self.assertEqual(digest, self.tool.EXPECTED_ARCHIVE_SHA256)

    def test_controlled_files_checksums(self) -> None:
        source_dir = ROOT / self.tool.SOURCE_RELATIVE
        checked = self.tool.verify_controlled_files(source_dir)
        self.assertEqual(len(checked), self.tool.EXPECTED_CONTROLLED_FILES)

    def test_package_metrics_and_counts(self) -> None:
        source_dir = ROOT / self.tool.SOURCE_RELATIVE
        res = self.tool.validate_extracted_source(source_dir)
        self.assertEqual(res["status"], "VALID")
        self.assertEqual(len(res["skills"]), 296)
        self.assertEqual(len(res["adapters"]), 264)
        self.assertEqual(len(res["goldenRoutes"]), 23)
        self.assertEqual(len(res["workflows"]), 35)

    def test_dual_root_installed_skills_parity(self) -> None:
        ws_skills = ROOT / ".agents/skills"
        rt_skills = ROOT / "agent-skills/runtime"
        source_skills = ROOT / self.tool.SOURCE_RELATIVE / "agent-skills/runtime"

        for sdir in source_skills.iterdir():
            if not sdir.is_dir():
                continue
            ws_target = ws_skills / sdir.name / "SKILL.md"
            rt_target = rt_skills / sdir.name / "SKILL.md"
            self.assertTrue(ws_target.is_file(), f"Missing {ws_target}")
            self.assertTrue(rt_target.is_file(), f"Missing {rt_target}")
            self.assertEqual(ws_target.read_bytes(), rt_target.read_bytes(), f"Parity mismatch on {sdir.name}")

    def test_qualification_receipt(self) -> None:
        receipt_path = ROOT / "docs/ai-capability-enhancement/local-qualification.json"
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["packageId"], self.tool.PACKAGE_ID)
        self.assertEqual(receipt["validationStatus"], "PASS")
        self.assertEqual(receipt["skillsCount"], 296)


if __name__ == "__main__":
    unittest.main()
