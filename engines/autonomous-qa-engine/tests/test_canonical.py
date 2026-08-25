from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import elmos_autonomous_qa.canonical as canonical_module
from elmos_autonomous_qa.canonical import UnsafePathError, sha256_file


class CanonicalFileTest(unittest.TestCase):
    def test_sha256_file_rejects_symlink_and_open_time_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.txt"
            target.write_bytes(b"trusted")
            link = root / "link.txt"
            link.symlink_to(target)
            with self.assertRaises(UnsafePathError):
                sha256_file(link)

            replacement = root / "replacement.txt"
            replacement.write_bytes(b"untrusted")
            real_open = canonical_module.os.open

            def replace_then_open(path: object, flags: int) -> int:
                target.unlink()
                target.symlink_to(replacement)
                return real_open(path, flags)

            with patch.object(
                canonical_module.os, "open", side_effect=replace_then_open
            ):
                with self.assertRaises(UnsafePathError):
                    sha256_file(target)


if __name__ == "__main__":
    unittest.main()
