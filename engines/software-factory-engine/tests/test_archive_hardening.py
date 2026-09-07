from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import elmos_software_factory.archive_contracts as archive_contracts
from elmos_software_factory.archive_contracts import ArchiveContractError, _scan


class ArchiveTraversalHardeningTests(unittest.TestCase):
    def test_scan_reads_regular_files_through_the_pinned_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            nested = root / "nested"
            nested.mkdir(parents=True)
            member = nested / "member.txt"
            member.write_bytes(b"bounded archive data\n")
            member.chmod(0o640)

            logical, mapping = _scan(root)

            self.assertEqual(
                logical,
                {
                    "nested/member.txt": (
                        b"bounded archive data\n",
                        0o640,
                        "nested/member.txt",
                    )
                },
            )
            self.assertEqual(mapping, {})

    def test_scan_rejects_every_executable_regular_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            executable = root / "unexpected-tool.bin"
            executable.write_bytes(b"untrusted executable bytes")
            executable.chmod(0o755)

            with self.assertRaisesRegex(
                ArchiveContractError,
                r"executable regular file: unexpected-tool\.bin$",
            ):
                _scan(root)

    def test_scan_rejects_a_symlink_member_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside.txt"
            outside.write_bytes(b"must not be read")
            root = base / "source"
            root.mkdir()
            (root / "member.txt").symlink_to(outside)

            with self.assertRaisesRegex(
                ArchiveContractError,
                r"contains a symlink: member\.txt$",
            ):
                _scan(root)

    def test_scan_detects_parent_replacement_and_stays_on_pinned_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            parent = base / "parent"
            root = parent / "source"
            root.mkdir(parents=True)
            (root / "inside.txt").write_bytes(b"original pinned tree")
            outside = base / "outside"
            outside.mkdir()
            (outside / "escape.txt").write_bytes(b"replacement tree")
            moved_parent = base / "moved-parent"
            real_listdir = os.listdir
            real_read = os.read
            replacement_done = False
            observed_bytes = bytearray()

            def replace_parent_after_enumeration(descriptor: int) -> list[str]:
                nonlocal replacement_done
                names = real_listdir(descriptor)
                if not replacement_done:
                    replacement_done = True
                    parent.rename(moved_parent)
                    parent.mkdir()
                    (parent / "source").symlink_to(outside, target_is_directory=True)
                return names

            def record_descriptor_reads(descriptor: int, maximum: int) -> bytes:
                chunk = real_read(descriptor, maximum)
                observed_bytes.extend(chunk)
                return chunk

            with (
                patch.object(
                    archive_contracts.os,
                    "listdir",
                    side_effect=replace_parent_after_enumeration,
                ),
                patch.object(
                    archive_contracts.os,
                    "read",
                    side_effect=record_descriptor_reads,
                ),
            ):
                with self.assertRaisesRegex(
                    ArchiveContractError,
                    r"root binding changed during inspection$",
                ):
                    _scan(root)

            self.assertTrue(replacement_done)
            self.assertEqual(observed_bytes, b"original pinned tree")


if __name__ == "__main__":
    unittest.main()
