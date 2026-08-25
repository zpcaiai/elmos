from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from elmos_cache_ref.canonical import action_key, canonical_json_bytes
from elmos_cache_ref.cas import DigestMismatch, LocalCAS
from elmos_cache_ref.publish import AtomicPublisher, TreeConflict
from elmos_cache_ref.recovery import plan_workspace_recovery
from elmos_cache_ref.staging import Workspace


class CanonicalTests(unittest.TestCase):
    def test_map_order_is_stable(self):
        self.assertEqual(
            canonical_json_bytes({"b": 2, "a": 1}),
            canonical_json_bytes({"a": 1, "b": 2}),
        )

    def test_action_key_ignores_derived_fields(self):
        base = {"stage_id": "x", "inputs": {"a": 1}}
        decorated = {
            **base,
            "action_key": "sha256:" + "0" * 64,
            "explanation": {"note": "derived"},
        }
        self.assertEqual(action_key(base), action_key(decorated))


class CASTests(unittest.TestCase):
    def test_put_get_and_expected_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            cas = LocalCAS(Path(directory))
            digest = cas.put_bytes(b"hello")
            self.assertEqual(cas.get_bytes(digest), b"hello")
            self.assertEqual(cas.put_bytes(b"hello"), digest)
            with self.assertRaises(DigestMismatch):
                cas.put_bytes(
                    b"hello",
                    expected_digest="sha256:" + "0" * 64,
                )

    def test_corruption_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            cas = LocalCAS(Path(directory))
            digest = cas.put_bytes(b"trusted")
            cas.path_for(digest).write_bytes(b"corrupt")
            with self.assertRaises(DigestMismatch):
                cas.verify(digest)


class StagingTests(unittest.TestCase):
    def test_reserve_write_seal_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cas = LocalCAS(root / "cas")
            workspace = Workspace(root / "workspaces", "run-1", cas)

            staged = workspace.reserve(
                "generate:file",
                1,
                "src/App.cs",
                lease_epoch=7,
                file_class="PUBLISH_CANDIDATE",
            )
            self.assertEqual(staged.status, "RESERVED")

            staged = workspace.write_and_seal(
                staged,
                io.BytesIO(b"class App {}\n"),
                current_lease_epoch=7,
            )
            self.assertEqual(staged.status, "SEALED")
            self.assertIsNotNone(staged.digest)

            staged = workspace.promote(staged)
            self.assertEqual(staged.status, "CAS_PROMOTED")
            self.assertEqual(cas.get_bytes(staged.digest), b"class App {}\n")

            events = workspace.journal.read_all()
            self.assertEqual(
                [event["event"] for event in events],
                [
                    "STAGED_FILE_RESERVED",
                    "STAGED_FILE_SEALED",
                    "STAGED_FILE_PROMOTED",
                ],
            )

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace(
                root / "workspaces",
                "run-1",
                LocalCAS(root / "cas"),
            )
            with self.assertRaises(ValueError):
                workspace.reserve("node", 1, "../escape", 1)

    def test_stale_lease_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace(
                root / "workspaces",
                "run-1",
                LocalCAS(root / "cas"),
            )
            staged = workspace.reserve("node", 1, "ok.txt", 2)
            with self.assertRaises(RuntimeError):
                workspace.write_and_seal(
                    staged,
                    io.BytesIO(b"x"),
                    current_lease_epoch=3,
                )

    def test_recovery_plan_uses_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = Workspace(
                root / "workspaces",
                "run-1",
                LocalCAS(root / "cas"),
            )
            workspace.reserve("node", 1, "a.txt", 1)
            plan = plan_workspace_recovery(workspace)
            self.assertEqual(plan[0]["recovery_action"], "RELEASE_OR_REASSIGN")


class PublicationTests(unittest.TestCase):
    def test_complete_tree_build_and_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cas = LocalCAS(root / "cas")
            app_digest = cas.put_bytes(b"class App {}\n")
            project_digest = cas.put_bytes(b"<Project />\n")
            publisher = AtomicPublisher(root / "publish", cas)

            entries = [
                {
                    "logical_path": "src/App.cs",
                    "artifact_digest": app_digest,
                    "mode": 0o644,
                },
                {
                    "logical_path": "App.csproj",
                    "artifact_digest": project_digest,
                    "mode": 0o644,
                },
            ]
            tree_digest, candidate = publisher.build_candidate(entries)
            pointer = publisher.publish(tree_digest, candidate)

            self.assertTrue(candidate.is_dir())
            self.assertEqual((candidate / "src/App.cs").read_bytes(), b"class App {}\n")
            self.assertTrue(pointer.exists() or pointer.is_symlink())

    def test_case_collision_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cas = LocalCAS(root / "cas")
            digest = cas.put_bytes(b"x")
            publisher = AtomicPublisher(root / "publish", cas)
            with self.assertRaises(TreeConflict):
                publisher.build_candidate(
                    [
                        {"logical_path": "src/App.cs", "artifact_digest": digest, "mode": 0o644},
                        {"logical_path": "src/app.cs", "artifact_digest": digest, "mode": 0o644},
                    ]
                )


if __name__ == "__main__":
    unittest.main()
