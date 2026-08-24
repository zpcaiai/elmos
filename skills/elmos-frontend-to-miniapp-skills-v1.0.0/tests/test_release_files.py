from __future__ import annotations

import os
import unittest

from _support import ROOT
from common import canonical_files
from verify_package import validate_checksums


class ReleaseFileTests(unittest.TestCase):
    def test_cross_platform_wrappers_exist(self) -> None:
        for name in ["install.sh", "uninstall.sh", "verify.sh", "install.ps1", "uninstall.ps1", "verify.ps1"]:
            self.assertTrue((ROOT / name).is_file(), name)
        for name in ["install.sh", "uninstall.sh", "verify.sh"]:
            self.assertTrue(os.access(ROOT / name, os.X_OK), name)

    def test_checksum_file_when_present(self) -> None:
        if not (ROOT / "CHECKSUMS.sha256").exists():
            self.skipTest("Checksums are generated at release time")
        self.assertEqual(validate_checksums(ROOT), [])
        checksum_lines = [line for line in (ROOT / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(checksum_lines), len(canonical_files(ROOT)))


if __name__ == "__main__":
    unittest.main()
