"""Unit tests for native archive inspection bridge."""

import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from elmos_multimodal_intake.native_archive_bridge import inspect_archive_native


class TestNativeArchiveBridge(unittest.TestCase):

    def test_inspect_zip_archive(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with zipfile.ZipFile(tmp_path, "w") as zf:
                zf.writestr("src/index.js", "console.log('hello');")
                zf.writestr("package.json", '{"name": "test-pkg"}')

            res = inspect_archive_native(tmp_path)
            self.assertIsNotNone(res)
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("container_format"), "ZIP")
            self.assertEqual(res.get("entry_count"), 2)
            self.assertTrue(res.get("merkle_root", "").startswith("sha256:"))
            paths = {e["path"] for e in res.get("entries", [])}
            self.assertIn("src/index.js", paths)
            self.assertIn("package.json", paths)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
