from __future__ import annotations

import sys
import hashlib
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (
    read_regular_file_snapshot,
    verify_content_reference,
)


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

    def test_file_uri_round_trips_on_the_current_platform(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            evidence = root / "evidence.json"
            raw = b'{"status":"NOT_CERTIFIED"}\n'
            evidence.write_bytes(raw)

            verified = verify_content_reference(
                {
                    "uri": evidence.as_uri(),
                    "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                },
                (root,),
            )

            self.assertEqual(evidence, Path(verified["resolved_path"]))


if __name__ == "__main__":
    unittest.main()
