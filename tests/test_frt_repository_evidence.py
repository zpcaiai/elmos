from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "frt" / "repository_evidence.py"
PACK = ROOT / "client-packs" / "frt-g01-g30-platform"


class FrtRepositoryEvidenceTest(unittest.TestCase):
    def check(self, pack: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "check",
                "--repo-root",
                str(ROOT),
                "--pack",
                str(pack),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def copied_pack(self, directory: str) -> Path:
        copied = Path(directory) / PACK.name
        shutil.copytree(PACK, copied)
        return copied

    def test_checked_in_repository_evidence_is_content_bound(self) -> None:
        result = self.check(PACK)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("artifacts=3", result.stdout)
        self.assertIn("external=NOT_RUN", result.stdout)

    def test_rejects_tampered_materialized_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = self.copied_pack(directory)
            manifest = json.loads(
                (copied / "repository-evidence" / "manifest.json").read_text()
            )
            artifact = copied / manifest["artifacts"][0]["path"]
            artifact.write_bytes(artifact.read_bytes() + b"tampered")
            result = self.check(copied)
            self.assertEqual(2, result.returncode)
            self.assertIn("content drift", result.stderr)

    def test_rejects_path_escape_even_with_existing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = self.copied_pack(directory)
            manifest_path = copied / "repository-evidence" / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["artifacts"][0]["path"] = "../outside.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            result = self.check(copied)
            self.assertEqual(2, result.returncode)
            self.assertIn("safe relative path", result.stderr)


if __name__ == "__main__":
    unittest.main()
