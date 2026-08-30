from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from elmos_pdhi.canonical import digest_bytes
from elmos_pdhi.transactions import (
    Postcondition,
    ScopeFence,
    TransactionManager,
    TransactionStatus,
    WriteIntent,
    revision_digest,
)


class TransactionTests(unittest.TestCase):
    def _manager(self, root: Path) -> TransactionManager:
        return TransactionManager(ScopeFence(str(root), ("src",), "fence-7"))

    def test_path_traversal_scope_escape_and_symlink_are_rejected(self) -> None:
        with TemporaryDirectory() as repository, TemporaryDirectory() as outside:
            root = Path(repository)
            (root / "src").mkdir()
            outside_file = Path(outside) / "outside.py"
            outside_file.write_text("outside\n", encoding="utf-8")
            os.symlink(outside_file, root / "src" / "link.py")
            manager = self._manager(root)
            with self.assertRaises(ValueError):
                manager.content_hash_anchor("../outside.py")
            with self.assertRaises(PermissionError):
                manager.scope.authorize("README.md", "fence-7")
            with self.assertRaises(OSError):
                manager.content_hash_anchor("src/link.py")

    def test_stale_anchor_rejects_patch_without_mutation(self) -> None:
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "src").mkdir()
            target = root / "src" / "app.py"
            target.write_bytes(b"old\n")
            manager = self._manager(root)
            expected = manager.content_hash_anchor("src/app.py")
            write = WriteIntent("src/app.py", expected, b"new\n")
            base = revision_digest(manager, (), (write,))
            plan = manager.patch_intent_contract(
                transaction_id="tx-stale",
                base_revision=base,
                intent="bounded fixture change",
                read_set=(),
                write_set=(write,),
                postconditions=(Postcondition("digest", "src/app.py", expected_digest=digest_bytes(b"new\n")),),
            )
            target.write_bytes(b"concurrent\n")
            receipt = manager.transactional_patch(plan, fence_token="fence-7")
            self.assertEqual(TransactionStatus.PRECONDITION_FAILED, receipt.status)
            self.assertEqual(b"concurrent\n", target.read_bytes())
            self.assertEqual(("src/app.py",), receipt.stale_paths)

    def test_postcondition_failure_rolls_back_from_cas_snapshot(self) -> None:
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "src").mkdir()
            target = root / "src" / "app.py"
            target.write_bytes(b"before\n")
            manager = self._manager(root)
            expected = manager.content_hash_anchor("src/app.py")
            write = WriteIntent("src/app.py", expected, b"after\n")
            plan = manager.patch_intent_contract(
                transaction_id="tx-rollback",
                base_revision=revision_digest(manager, (), (write,)),
                intent="exercise postcondition rollback",
                read_set=(),
                write_set=(write,),
                postconditions=(Postcondition("contains", "src/app.py", expected_bytes=b"never-present"),),
            )
            receipt = manager.transactional_patch(plan, fence_token="fence-7")
            self.assertEqual(TransactionStatus.ROLLED_BACK, receipt.status)
            self.assertIsNotNone(receipt.rollback)
            assert receipt.rollback is not None
            self.assertEqual("RESTORED", receipt.rollback.status)
            self.assertEqual(b"before\n", target.read_bytes())
            self.assertTrue(receipt.atomic_file_replacement)
            self.assertEqual("COMPENSATED_NOT_GLOBALLY_ATOMIC", receipt.multi_file_atomicity)

    def test_successful_atomic_patch_and_fence_rejection(self) -> None:
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "src").mkdir()
            target = root / "src" / "app.py"
            target.write_bytes(b"before\n")
            manager = self._manager(root)
            expected = manager.content_hash_anchor("src/app.py")
            symbol = manager.symbol_identity_anchor("src/app.py", "python:app", 0, 6)
            write = WriteIntent("src/app.py", expected, b"after\n", symbol_anchor=symbol)
            plan = manager.patch_intent_contract(
                transaction_id="tx-success",
                base_revision=revision_digest(manager, (), (write,)),
                intent="atomic fixture change",
                read_set=(),
                write_set=(write,),
                postconditions=(Postcondition("digest", "src/app.py", expected_digest=digest_bytes(b"after\n")),),
            )
            with self.assertRaises(PermissionError):
                manager.transactional_patch(plan, fence_token="stale-fence")
            receipt = manager.transactional_patch(plan, fence_token="fence-7")
            self.assertEqual(TransactionStatus.COMMITTED, receipt.status)
            self.assertEqual(b"after\n", target.read_bytes())


if __name__ == "__main__":
    unittest.main()
