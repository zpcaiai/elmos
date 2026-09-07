from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tooling.integrate_ai_optimization_skills import (
    ARCHIVE_RELATIVE,
    EXPECTED_ARCHIVE_BYTES,
    EXPECTED_ARCHIVE_SHA256,
    EXPECTED_ENTRY_COUNT,
    IntegrationError,
    check_integration,
    inspect_archive,
    write_integration,
)


ROOT = Path(__file__).resolve().parents[2]


class ArchiveIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.archive_path = ROOT / ARCHIVE_RELATIVE
        self.assertTrue(self.archive_path.is_file(), f"Archive missing: {self.archive_path}")

    def test_archive_digest_and_size(self) -> None:
        raw = self.archive_path.read_bytes()
        self.assertEqual(len(raw), EXPECTED_ARCHIVE_BYTES)
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest, EXPECTED_ARCHIVE_SHA256)

    def test_inspect_archive_snapshot(self) -> None:
        snapshot = inspect_archive(self.archive_path)
        self.assertEqual(snapshot.entry_count, EXPECTED_ENTRY_COUNT)
        self.assertEqual(len(snapshot.tasks), 30)
        self.assertEqual(len(snapshot.acceptance_cases), 60)
        self.assertEqual(len(snapshot.schemas), 14)
        self.assertEqual(len(snapshot.examples), 14)
        self.assertEqual(snapshot.manifest["name"], "elmos-ai-optimization-skills")
        self.assertEqual(snapshot.manifest["new_elmos_routes"], 0)
        self.assertEqual(snapshot.manifest["codex_discoverable_skills"], 1)

    def test_safe_extract_and_check_in_isolated_temp(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            # Create subskills dir and copy archive
            (temp_root / "skills" / "subskills").mkdir(parents=True)
            shutil.copy2(self.archive_path, temp_root / ARCHIVE_RELATIVE)

            # Check fails before extraction
            with self.assertRaises(IntegrationError):
                check_integration(temp_root, temp_root / ARCHIVE_RELATIVE)

            # Write extracts and installs
            res = write_integration(temp_root, temp_root / ARCHIVE_RELATIVE)
            self.assertEqual(res["status"], "SOURCE_EXTRACTED_AND_SKILLS_INSTALLED")

            # Check passes after extraction
            check_res = check_integration(temp_root, temp_root / ARCHIVE_RELATIVE)
            self.assertEqual(check_res["status"], "INSTALLATION_VERIFIED")


if __name__ == "__main__":
    unittest.main()
