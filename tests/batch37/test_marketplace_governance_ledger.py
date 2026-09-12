"""Tests for Batch 37 Marketplace governance ledger and dual-track disposition."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.batch37.marketplace_governance_ledger import (
    MarketplaceDispositionSummary,
    MarketplaceExtensionItem,
    MarketplaceGovernanceLedger,
    MarketplaceItemStatus,
)


class TestMarketplaceGovernanceLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = MarketplaceGovernanceLedger()

    def test_empty_scan(self) -> None:
        summary = self.ledger.scan_and_classify([])
        self.assertEqual(summary.total_items, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertFalse(summary.is_fully_dispositioned)

    def test_all_automated(self) -> None:
        items = [
            MarketplaceExtensionItem(
                extension_id="org.elmos.sql-formatter",
                version="1.2.0",
                publisher_id="pub-certified-01",
                status=MarketplaceItemStatus.CERTIFIED_ACTIVE,
                category="TRANSFORMATION",
            ),
            MarketplaceExtensionItem(
                extension_id="org.elmos.security-linter",
                version="2.0.1",
                publisher_id="pub-certified-02",
                status=MarketplaceItemStatus.AUTOMATED_SANDBOX_VERIFIED,
                category="SECURITY",
            ),
        ]
        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 2)
        self.assertEqual(summary.automated_verified_count, 2)
        self.assertEqual(summary.governance_handoff_count, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

    def test_mixed_dual_track_100_percent_disposition(self) -> None:
        items = [
            MarketplaceExtensionItem(
                extension_id="com.partner.abi-pack",
                version="3.0.0",
                publisher_id="pub-verified",
                status=MarketplaceItemStatus.ABI_COMPATIBLE,
                category="ADAPTER",
            ),
            MarketplaceExtensionItem(
                extension_id="com.unknown.unsigned-tool",
                version="0.0.1",
                publisher_id="pub-anonymous",
                status=MarketplaceItemStatus.UNSIGNED_PUBLISHER_BLOCKED,
                category="TOOL",
                priority="P0",
            ),
            MarketplaceExtensionItem(
                extension_id="com.partner.egress-scanner",
                version="1.1.0",
                publisher_id="pub-partner",
                status=MarketplaceItemStatus.UNAPPROVED_EGRESS_QUARANTINED,
                category="NETWORK",
                priority="P0",
            ),
            MarketplaceExtensionItem(
                extension_id="org.gpl.helper",
                version="4.5.0",
                publisher_id="pub-oss",
                status=MarketplaceItemStatus.LICENSE_COMPLIANCE_HOLD,
                category="LIBRARY",
                priority="P1",
            ),
            MarketplaceExtensionItem(
                extension_id="com.vendor.premium-model",
                version="2.1.0",
                publisher_id="pub-vendor",
                status=MarketplaceItemStatus.SETTLEMENT_DISPUTE_ESCALATED,
                category="COMMERCIAL",
                priority="P2",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 5)
        self.assertEqual(summary.automated_verified_count, 1)
        self.assertEqual(summary.governance_handoff_count, 4)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

        self.assertIn("corporate HSM signature", items[1].remediation_action)
        self.assertIn("microVM sandbox", items[2].remediation_action)

    def test_dossier_generation_and_write(self) -> None:
        items = [
            MarketplaceExtensionItem(
                extension_id="com.elmos.verified-adapter",
                version="1.0.0",
                publisher_id="pub-elmos",
                status=MarketplaceItemStatus.CERTIFIED_ACTIVE,
                category="ADAPTER",
            ),
            MarketplaceExtensionItem(
                extension_id="com.legacy.v1-driver",
                version="0.9.0",
                publisher_id="pub-legacy",
                status=MarketplaceItemStatus.ABI_INCOMPATIBLE_REVOKED,
                category="DRIVER",
                priority="P1",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        json_data = self.ledger.generate_governance_json(summary)
        self.assertEqual(json_data["total_items"], 2)
        self.assertEqual(json_data["automated_verified_count"], 1)
        self.assertEqual(json_data["governance_handoff_count"], 1)
        self.assertEqual(json_data["disposition_coverage_ratio"], 1.0)
        self.assertTrue(json_data["is_fully_dispositioned"])

        md_text = self.ledger.generate_markdown_dossier(summary)
        self.assertIn("Batch 37 Marketplace & Extension Ecosystem Disposition Dossier", md_text)
        self.assertIn("100% Accounted", md_text)
        self.assertIn("`com.legacy.v1-driver`", md_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = self.ledger.write_handoff_dossier(summary, Path(tmpdir))
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            saved_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_json["total_items"], 2)


if __name__ == "__main__":
    unittest.main()
