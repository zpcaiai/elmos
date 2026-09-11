from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import read_regular_file_snapshot


class RegularFileSnapshotTest(unittest.TestCase):
    def test_preserves_crlf_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence.json"
            raw = b'{\r\n  "status": "NOT_CERTIFIED"\r\n}\r\n'
            evidence.write_bytes(raw)

            snapshot = read_regular_file_snapshot(
                evidence,
                max_bytes=1024,
                label="CRLF evidence",
            )

            self.assertEqual(snapshot.content, raw)
            self.assertEqual(snapshot.stat_result.st_size, len(raw))


if __name__ == "__main__":
    unittest.main()
