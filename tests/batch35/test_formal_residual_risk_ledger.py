"""Tests for Batch 35 formal residual risk ledger and dual-track disposition."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.batch35.formal_residual_risk_ledger import (
    FormalDispositionSummary,
    FormalItemStatus,
    FormalResidualRiskLedger,
    FormalVerificationItem,
)


class TestFormalResidualRiskLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = FormalResidualRiskLedger()

    def test_empty_scan(self) -> None:
        summary = self.ledger.scan_and_classify([])
        self.assertEqual(summary.total_items, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertFalse(summary.is_fully_dispositioned)

    def test_all_proved(self) -> None:
        items = [
            FormalVerificationItem(
                item_id="FORMAL-001",
                property_name="balance_non_negative",
                category="INVARIANT",
                status=FormalItemStatus.PROVED,
                expression="balance >= 0",
                file_path="src/account.smt2",
                line_number=42,
            ),
            FormalVerificationItem(
                item_id="FORMAL-002",
                property_name="transfer_conservation",
                category="CONSERVATION",
                status=FormalItemStatus.BOUNDED_VERIFIED,
                expression="total_after == total_before",
                file_path="src/transfer.smt2",
                line_number=88,
            ),
        ]
        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 2)
        self.assertEqual(summary.automated_proved_count, 2)
        self.assertEqual(summary.residual_risk_count, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

    def test_mixed_dual_track_100_percent_disposition(self) -> None:
        items = [
            FormalVerificationItem(
                item_id="FORMAL-001",
                property_name="lock_acquisition_order",
                category="CONCURRENCY_SAFETY",
                status=FormalItemStatus.PROVED,
                expression="ordered(lockA, lockB)",
                file_path="src/concurrency/manager.rs",
                line_number=105,
            ),
            FormalVerificationItem(
                item_id="FORMAL-002",
                property_name="cubic_root_convergence",
                category="SMT_ARITHMETIC",
                status=FormalItemStatus.UNDECIDABLE_NON_LINEAR,
                expression="x^3 + 2x - 5 == 0",
                file_path="src/math/solver.py",
                line_number=210,
                priority="P0",
            ),
            FormalVerificationItem(
                item_id="FORMAL-003",
                property_name="distributed_consensus_liveness",
                category="MODEL_CHECKING_LIVENESS",
                status=FormalItemStatus.STATE_EXPLOSION,
                expression="[](request => <>response)",
                file_path="specs/raft.tla",
                line_number=315,
                priority="P1",
            ),
            FormalVerificationItem(
                item_id="FORMAL-004",
                property_name="bounded_queue_deadlock_free",
                category="CONCURRENCY_SAFETY",
                status=FormalItemStatus.COUNTEREXAMPLE_FOUND,
                expression="!deadlock",
                file_path="src/queue/ring_buffer.c",
                line_number=77,
                counterexample={"thread1_state": "WAIT", "thread2_state": "WAIT"},
                priority="P0",
            ),
            FormalVerificationItem(
                item_id="FORMAL-005",
                property_name="hash_ring_partition_fairness",
                category="SMT_ARITHMETIC",
                status=FormalItemStatus.SOLVER_TIMEOUT,
                expression="forall node. weight(node) > min_weight",
                file_path="specs/hash_ring.smt2",
                line_number=50,
                priority="P2",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 5)
        self.assertEqual(summary.automated_proved_count, 1)
        self.assertEqual(summary.residual_risk_count, 4)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

        # Check default remediation filled in
        self.assertIn("Bit-Vector", items[1].recommended_remediation)
        self.assertIn("partial order reduction", items[2].recommended_remediation)

    def test_dossier_generation_and_write(self) -> None:
        items = [
            FormalVerificationItem(
                item_id="FORMAL-101",
                property_name="matrix_multiplication_associative",
                category="ALGEBRAIC",
                status=FormalItemStatus.PROVED,
                expression="(A * B) * C == A * (B * C)",
                file_path="src/matrix.py",
                line_number=12,
            ),
            FormalVerificationItem(
                item_id="FORMAL-102",
                property_name="deep_recursive_tree_traversal",
                category="TERMINATION",
                status=FormalItemStatus.UNBOUNDED_RECURSION,
                expression="terminates(traverse(tree))",
                file_path="src/ast_tree.py",
                line_number=88,
                priority="P1",
            ),
        ]
        summary = self.ledger.scan_and_classify(items)
        json_data = self.ledger.generate_assurance_dossier_json(summary)

        self.assertEqual(json_data["total_items"], 2)
        self.assertEqual(json_data["automated_proved_count"], 1)
        self.assertEqual(json_data["residual_risk_count"], 1)
        self.assertEqual(json_data["disposition_coverage_ratio"], 1.0)
        self.assertTrue(json_data["is_fully_dispositioned"])
        self.assertEqual(len(json_data["proved_items"]), 1)
        self.assertEqual(len(json_data["residual_risks"]), 1)

        md_text = self.ledger.generate_markdown_dossier(summary)
        self.assertIn("Batch 35 Formal Verification Residual Risk", md_text)
        self.assertIn("100% Accounted", md_text)
        self.assertIn("`FORMAL-102`", md_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = self.ledger.write_handoff_dossier(summary, Path(tmpdir))
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            saved_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_json["total_items"], 2)


if __name__ == "__main__":
    unittest.main()
