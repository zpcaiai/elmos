from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import elmos_autonomous_qa.project as project_module
from elmos_autonomous_qa.contracts import ContractError
from elmos_autonomous_qa.project import SnapshotPolicy, build_project_snapshot


class ProjectSnapshotTest(unittest.TestCase):
    def test_snapshot_is_deterministic_and_detects_stack_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
            (root / "src" / "add.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
            (root / "tests" / "test_add.py").write_text("def test_add(): assert 1 + 2 == 3\n", encoding="utf-8")
            first = build_project_snapshot(root, required_paths=("src/add.py",))
            second = build_project_snapshot(root, required_paths=("src/add.py",))
            self.assertEqual(first, second)
            self.assertEqual(first["technology_profile"]["languages"], ["Python"])
            self.assertIn("Python", first["technology_profile"]["frameworks"])
            self.assertTrue(first["complete"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_snapshot_never_follows_symlinks_or_exposes_secret_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            outside_file = Path(outside) / "secret.txt"
            outside_file.write_text("outside-secret", encoding="utf-8")
            os.symlink(outside_file, root / "linked.txt")
            (root / ".env").write_text("PASSWORD=do-not-load\n", encoding="utf-8")
            snapshot = build_project_snapshot(root)
            self.assertNotIn("linked.txt", {item["path"] for item in snapshot["files"]})
            env = next(item for item in snapshot["files"] if item["path"] == ".env")
            self.assertTrue(env["sensitive_content_not_exposed"])
            self.assertTrue(any(value.startswith("SYMLINK_FILE_SKIPPED") for value in snapshot["diagnostics"]))
            self.assertFalse(snapshot["inventory_complete"])
            self.assertFalse(snapshot["complete"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_snapshot_rejects_a_symlink_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as link_parent:
            root = Path(directory)
            link = Path(link_parent) / "project-link"
            os.symlink(root, link)
            with self.assertRaises(ContractError):
                build_project_snapshot(link)

    def test_missing_required_path_and_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.py").write_text("pass\n", encoding="utf-8")
            snapshot = build_project_snapshot(root, required_paths=("missing.py",))
            self.assertFalse(snapshot["complete"])
            with self.assertRaises(ContractError):
                build_project_snapshot(
                    root,
                    policy=SnapshotPolicy(
                        max_files=1,
                        max_total_bytes=1,
                        max_single_file_bytes=1024,
                    ),
                )

    def test_entry_and_required_diagnostic_limits_are_enforced_during_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(4):
                (root / f"file-{index}.txt").write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "entry limit"):
                build_project_snapshot(
                    root,
                    policy=SnapshotPolicy(max_entries=3),
                )

            with self.assertRaisesRegex(ContractError, "diagnostic limit"):
                build_project_snapshot(
                    root,
                    required_paths=("missing-a", "missing-b"),
                    policy=SnapshotPolicy(max_diagnostics=1),
                )

    def test_callers_cannot_hide_source_with_custom_exclusions(self) -> None:
        with self.assertRaisesRegex(ContractError, "exclusions are repository controlled"):
            SnapshotPolicy(excluded_dirs=frozenset({"src"}))
        with self.assertRaisesRegex(ContractError, "not broadened"):
            SnapshotPolicy(max_files=50_001)

    def test_concurrent_directory_insertion_cannot_yield_a_complete_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "initial.py").write_text("pass\n", encoding="utf-8")
            real_scandir = os.scandir
            injected = False

            class InjectAfterEnumeration:
                def __init__(self, delegate: os.ScandirIterator[str]) -> None:
                    self.delegate = delegate

                def __enter__(self) -> os.ScandirIterator[str]:
                    return self.delegate.__enter__()

                def __exit__(self, exc_type, exc, traceback) -> bool:
                    nonlocal injected
                    result = bool(self.delegate.__exit__(exc_type, exc, traceback))
                    (root / "late.py").write_text("pass\n", encoding="utf-8")
                    injected = True
                    return result

            def unstable_scandir(path):
                nonlocal injected
                delegate = real_scandir(path)
                if not injected:
                    return InjectAfterEnumeration(delegate)
                return delegate

            with patch.object(project_module.os, "scandir", side_effect=unstable_scandir):
                with self.assertRaisesRegex(
                    ContractError, "directory changed during snapshot"
                ):
                    build_project_snapshot(root)


if __name__ == "__main__":
    unittest.main()
