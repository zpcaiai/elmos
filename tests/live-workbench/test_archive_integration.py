from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LiveWorkbenchArchiveIntegrationTest(unittest.TestCase):
    def test_pinned_source_archive_and_mirror_validate_without_executing_package_scripts(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/live_workbench/validate_archive.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK: live workbench source archive", result.stdout)


if __name__ == "__main__":
    unittest.main()
