"""Unit test for native repository snapshot scanner bridge."""

import os
from pathlib import Path
import tempfile
import unittest

from elmos_project_intelligence.contracts import SnapshotLimits, SnapshotRequest
from elmos_project_intelligence.native_snapshot_bridge import scan_repository_native


class TestNativeSnapshotScanner(unittest.TestCase):

    def test_native_scan_basic_and_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text(
                "export AWS_KEY=\"AKIA1234567890ABCDEF\"\npassword = 'SuperSecretPassword123!'\n",
                encoding="utf-8"
            )
            (root / "README.md").write_text("# Project Docs\n", encoding="utf-8")

            req = SnapshotRequest(
                tenant_id="t1",
                project_id="p1",
                run_id="r1",
                root=root,
                limits=SnapshotLimits(max_files=100, max_total_bytes=1000000, max_file_bytes=100000),
            )

            res = scan_repository_native(req, include_text=True)
            self.assertIsNotNone(res)
            self.assertTrue(res.ok)
            self.assertEqual(res.value.file_count, 2)
            self.assertEqual(res.value.symlink_count, 0)
            self.assertTrue(res.value.snapshot_digest.startswith("sha256:"))

            # Verify secret fingerprints were captured
            main_entry = next(e for e in res.value.entries if e.path == "src/main.py")
            self.assertTrue(len(main_entry.secret_fingerprints) >= 2)
            kinds = {fp.kind for fp in main_entry.secret_fingerprints}
            self.assertIn("aws-access-key", kinds)
            self.assertIn("credential-assignment", kinds)
