"""Tests for Batch 36 Developer Experience handoff ledger."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.batch36.devex_handoff_ledger import (
    DevExDispositionSummary,
    DevExHandoffLedger,
    DevExItem,
    DevExItemStatus,
)


class TestDevExHandoffLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = DevExHandoffLedger()

    def test_empty_scan(self) -> None:
        summary = self.ledger.scan_and_classify([])
        self.assertEqual(summary.total_items, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertFalse(summary.is_fully_dispositioned)

    def test_all_automated(self) -> None:
        items = [
            DevExItem(
                item_id="DEVEX-001",
                operation_name="import_organizer",
                category="LSP_DIAGNOSTIC",
                status=DevExItemStatus.LSP_DIAGNOSTIC_RESOLVED,
                target_file="src/index.ts",
                line_range="1-15",
            ),
            DevExItem(
                item_id="DEVEX-002",
                operation_name="unused_var_removal",
                category="QUICK_FIX",
                status=DevExItemStatus.AUTOMATED_QUICK_FIX_APPLIED,
                target_file="src/service.ts",
                line_range="45",
            ),
        ]
        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 2)
        self.assertEqual(summary.automated_success_count, 2)
        self.assertEqual(summary.handoff_count, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

    def test_mixed_dual_track_100_percent_disposition(self) -> None:
        items = [
            DevExItem(
                item_id="DEVEX-001",
                operation_name="auto_pr_lint",
                category="PR_BOT",
                status=DevExItemStatus.AUTOMATED_PR_REVIEWED,
                target_file="src/api.py",
            ),
            DevExItem(
                item_id="DEVEX-002",
                operation_name="proto_generated_shield",
                category="CODE_OWNERSHIP",
                status=DevExItemStatus.PROTECTED_REGION_BLOCKED,
                target_file="src/proto/service_pb2.py",
                line_range="1-500",
                priority="P0",
            ),
            DevExItem(
                item_id="DEVEX-003",
                operation_name="branch_divergence_merge",
                category="CONFLICT_RESOLUTION",
                status=DevExItemStatus.THREE_WAY_CONFLICT_ESCALATION,
                target_file="src/routes/auth.py",
                line_range="120-145",
                priority="P0",
            ),
            DevExItem(
                item_id="DEVEX-004",
                operation_name="offline_npm_sync",
                category="OFFLINE_WORKFLOW",
                status=DevExItemStatus.AIRGAP_CREDENTIAL_REQUIRED,
                target_file="package.json",
                priority="P1",
            ),
            DevExItem(
                item_id="DEVEX-005",
                operation_name="proprietary_cobol_lsp",
                category="IDE_PROTOCOL",
                status=DevExItemStatus.PROPRIETARY_LSP_UNAVAILABLE,
                target_file="cbl/BILLING.cbl",
                priority="P2",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 5)
        self.assertEqual(summary.automated_success_count, 1)
        self.assertEqual(summary.handoff_count, 4)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

        self.assertIn("@generated", items[1].suggested_action)
        self.assertIn("merge conflict editor", items[2].suggested_action)

    def test_dossier_generation_and_write(self) -> None:
        items = [
            DevExItem(
                item_id="DEVEX-101",
                operation_name="fix_typo",
                category="QUICK_FIX",
                status=DevExItemStatus.AUTOMATED_QUICK_FIX_APPLIED,
                target_file="src/main.rs",
            ),
            DevExItem(
                item_id="DEVEX-102",
                operation_name="custom_security_hook",
                category="CLI_HOOK",
                status=DevExItemStatus.UNRESOLVED_INTERNAL_HOOK,
                target_file=".git/hooks/pre-commit",
                priority="P1",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        json_data = self.ledger.generate_handoff_json(summary)
        self.assertEqual(json_data["total_items"], 2)
        self.assertEqual(json_data["automated_success_count"], 1)
        self.assertEqual(json_data["handoff_count"], 1)
        self.assertEqual(json_data["disposition_coverage_ratio"], 1.0)
        self.assertTrue(json_data["is_fully_dispositioned"])

        md_text = self.ledger.generate_markdown_dossier(summary)
        self.assertIn("Batch 36 Developer Experience & IDE/CLI Disposition Dossier", md_text)
        self.assertIn("100% Accounted", md_text)
        self.assertIn("`DEVEX-102`", md_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = self.ledger.write_handoff_dossier(summary, Path(tmpdir))
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            saved_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_json["total_items"], 2)


if __name__ == "__main__":
    unittest.main()
