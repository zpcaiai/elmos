from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tooling/integrate_formal_assurance_kernel.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("formal_assurance_importer", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load formal assurance importer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def test_pinned_archive_and_internal_checksums(self) -> None:
        files, modes, archive_digest = self.tool.read_archive(
            ROOT / self.tool.ARCHIVE_RELATIVE
        )
        self.assertEqual(archive_digest, self.tool.EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(len(files), 538)
        self.assertEqual(len(modes), 538)
        self.tool.verify_internal_checksums(files)
        package = self.tool.validate_package(files)
        self.assertEqual(len(package["skills"]), 60)
        self.assertEqual(len(package["workflows"]), 10)
        self.assertEqual(package["schemaCount"], 17)

    def test_immutable_source_mirror_has_no_drift_or_symlink(self) -> None:
        files, _, _ = self.tool.read_archive(ROOT / self.tool.ARCHIVE_RELATIVE)
        source = ROOT / self.tool.SOURCE_RELATIVE
        self.assertTrue(self.tool.source_matches(source, files))
        self.assertFalse(any(path.is_symlink() for path in source.rglob("*")))
        self.assertFalse(
            any(
                path.is_file() and path.stat().st_mode & 0o111
                for path in source.rglob("*")
            )
        )
        self.assertEqual(self.tool.tree_digest(source).count("sha256:"), 1)

    def test_generated_registry_matches_runtime_contract(self) -> None:
        metadata_path = ROOT / self.tool.DOC_RELATIVE / "skill-registry.json"
        document = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(document["packageId"], self.tool.PACKAGE_ID)
        self.assertEqual(
            document["sourceArchiveSha256"],
            "sha256:" + self.tool.EXPECTED_ARCHIVE_SHA256,
        )
        self.assertEqual(len(document["skills"]), 60)
        self.assertTrue(
            all(
                item["implementationState"] == "PRODUCTION_CODE_COMPLETE"
                for item in document["skills"]
            )
        )
        self.assertFalse(
            any("PARTIAL" in item["capabilityState"] for item in document["skills"])
        )
        self.assertTrue(
            all(
                item["externalEvidenceStatus"] == "NOT_RUN"
                for item in document["skills"]
            )
        )
        self.assertTrue(
            all(
                item["certificationStatus"] == "NOT_CERTIFIED"
                for item in document["skills"]
            )
        )


if __name__ == "__main__":
    unittest.main()
