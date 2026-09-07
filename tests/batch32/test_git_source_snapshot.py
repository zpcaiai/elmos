from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "batch32" / "materialize_git_source_snapshot.py"


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class GitSourceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.email", "snapshot@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "config", "user.name", "Snapshot Test"],
            check=True,
        )
        source = self.repo / "apps" / "web-console"
        source.mkdir(parents=True)
        (source / "a.txt").write_bytes(b"alpha\n")
        (source / "nested").mkdir()
        (source / "nested" / "b.json").write_bytes(b'{"value": 2}\n')
        subprocess.run(["git", "-C", str(self.repo), "add", "apps/web-console"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "fixture"], check=True)
        self.revision = subprocess.check_output(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True
        ).strip()
        self.pack = self.repo / "client-packs" / "fixture"
        (self.pack / "source-snapshots").mkdir(parents=True)
        files = []
        for path in sorted(source.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                files.append(
                    {
                        "path": path.relative_to(self.repo).as_posix(),
                        "sha256": sha256(data),
                        "bytes": len(data),
                    }
                )
        legacy = sha256(
            json.dumps(
                [{"path": item["path"], "sha256": item["sha256"]} for item in files],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        manifest = {
            "schema_version": 1,
            "kind": "elmos.git-source-snapshot-manifest",
            "source_revision": self.revision,
            "repository_relative_root": "apps/web-console",
            "file_count": len(files),
            "files": files,
            "snapshot_digest": legacy,
        }
        (self.pack / "source-snapshots" / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        (self.pack / "fingerprint.json").write_text(
            json.dumps({"snapshot_digest": legacy}, indent=2) + "\n"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_script(self, mode: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                mode,
                str(self.pack),
                "--repo-root",
                str(self.repo),
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_materializes_exact_git_tree_and_rewrites_digest_bindings(self) -> None:
        completed = self.run_script("materialize")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        manifest = json.loads(
            (self.pack / "source-snapshots" / "manifest.json").read_text()
        )
        self.assertEqual(manifest["source_root"], "source-snapshots/files")
        self.assertEqual(manifest["snapshot_digest"], manifest["aggregate_digest"])
        self.assertEqual(manifest["total_bytes"], 19)
        fingerprint = json.loads((self.pack / "fingerprint.json").read_text())
        self.assertEqual(fingerprint["snapshot_digest"], manifest["aggregate_digest"])
        self.assertEqual(
            (self.pack / "source-snapshots" / "files" / "apps" / "web-console" / "a.txt").read_bytes(),
            b"alpha\n",
        )
        checked = self.run_script("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_check_rejects_materialized_byte_tampering(self) -> None:
        completed = self.run_script("materialize")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        target = self.pack / "source-snapshots" / "files" / "apps" / "web-console" / "a.txt"
        target.write_bytes(b"tampered\n")
        checked = self.run_script("check")
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn("materialized snapshot drift", checked.stderr)

    def test_rejects_path_escape_before_writing(self) -> None:
        manifest_path = self.pack / "source-snapshots" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][0]["path"] = "../outside.txt"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        completed = self.run_script("materialize")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unsafe", completed.stderr)
        self.assertFalse((self.pack / "outside.txt").exists())

    def test_rejects_snapshot_files_hidden_by_gitignore(self) -> None:
        (self.repo / ".gitignore").write_text("**/nested/\n")
        completed = self.run_script("materialize")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ignored by Git", completed.stderr)
        self.assertFalse((self.pack / "source-snapshots" / "files").exists())


if __name__ == "__main__":
    unittest.main()
