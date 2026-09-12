"""Adapters and receipts unit tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from elmos_semantic_assurance.adapters import AdapterError, AdapterReceipt, AdapterSet

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from fixtures import sha


class TestAdapters(unittest.TestCase):
    def test_valid_receipt_to_dict(self) -> None:
        receipt = AdapterReceipt(
            adapter_id="trusted-adapter-001",
            execution_id="exec-001",
            request_digest=sha("1"),
            scope_digest=sha("2"),
            status="PASS",
            evidence_digest=sha("3"),
            executor_id="executor-a",
            verifier_id="verifier-b",
            signed=True,
            output={"result": "ok"},
        )
        d = receipt.to_dict()
        self.assertEqual(d["adapterId"], "trusted-adapter-001")
        self.assertEqual(d["status"], "PASS")
        self.assertEqual(d["executorId"], "executor-a")
        self.assertEqual(d["verifierId"], "verifier-b")
        self.assertTrue(d["signed"])

    def test_invalid_status_raises(self) -> None:
        with self.assertRaisesRegex(AdapterError, "status is invalid"):
            AdapterReceipt(
                adapter_id="trusted-adapter-001",
                execution_id="exec-001",
                request_digest=sha("1"),
                scope_digest=sha("2"),
                status="INVALID_STATUS",
                evidence_digest=sha("3"),
                executor_id="executor-a",
                output={},
            )

    def test_self_verification_raises(self) -> None:
        with self.assertRaisesRegex(AdapterError, "must be independent"):
            AdapterReceipt(
                adapter_id="trusted-adapter-001",
                execution_id="exec-001",
                request_digest=sha("1"),
                scope_digest=sha("2"),
                status="PASS",
                evidence_digest=sha("3"),
                executor_id="same-party",
                verifier_id="same-party",
                output={},
            )

    def test_adapter_set_defaults(self) -> None:
        ad_set = AdapterSet()
        self.assertIsNone(ad_set.native)
        self.assertIsNone(ad_set.formal)
        self.assertIsNone(ad_set.fuzz)


if __name__ == "__main__":
    unittest.main()
