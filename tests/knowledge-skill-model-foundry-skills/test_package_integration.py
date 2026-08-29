"""Root-level integration tests for the Knowledge-Skill-Model Foundry Skills package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_knowledge_skill_model_foundry_skills.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("foundry_importer", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load foundry importer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def test_pinned_archive_identity_and_sha256(self) -> None:
        archive_path = self.tool.resolve_archive()
        digest = self.tool.verify_archive(archive_path)
        self.assertEqual(digest, self.tool.EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(archive_path.stat().st_size, self.tool.EXPECTED_ARCHIVE_BYTES)

    def test_controlled_files_checksums(self) -> None:
        source_dir = ROOT / self.tool.SOURCE_RELATIVE
        controlled = source_dir / self.tool.PACKAGE_DIRECTORY if (source_dir / self.tool.PACKAGE_DIRECTORY).is_dir() else source_dir
        checked = self.tool.verify_controlled_files(controlled)
        self.assertEqual(len(checked), 2352)

    def test_extracted_source_counts(self) -> None:
        source_dir = ROOT / self.tool.SOURCE_RELATIVE
        controlled = source_dir / self.tool.PACKAGE_DIRECTORY if (source_dir / self.tool.PACKAGE_DIRECTORY).is_dir() else source_dir
        metrics = self.tool.validate_extracted_source(controlled)
        self.assertEqual(metrics["atomicSkills"], 458)
        self.assertEqual(metrics["metaSkills"], 17)
        self.assertEqual(metrics["packs"], 17)
        self.assertEqual(metrics["schemas"], 5)
        self.assertEqual(metrics["policies"], 3)
        self.assertEqual(metrics["pipelines"], 4)
        self.assertEqual(metrics["tables"], 25)

    def test_qualification_receipt_integrity(self) -> None:
        receipt_path = ROOT / "engines/knowledge-skill-model-foundry-engine/qualification/local-qualification.json"
        self.assertTrue(receipt_path.is_file(), f"Missing qualification receipt at {receipt_path}")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["package_id"], self.tool.PACKAGE_ID)
        self.assertEqual(receipt["qualification_state"], "QUALIFIED_SELF_ATTESTED")
        self.assertEqual(receipt["archive_sha256"], self.tool.EXPECTED_ARCHIVE_SHA256)


if __name__ == "__main__":
    unittest.main()
