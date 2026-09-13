"""Unit tests for ClientHandoffLedger in batch32."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "batch32"))

from client_handoff_ledger import ClientComponentFinding, ClientHandoffLedger


class TestClientHandoffLedger(unittest.TestCase):
    def test_client_handoff_ledger_100_percent_coverage(self) -> None:
        findings = [
            ClientComponentFinding(
                component_id="COMP-001",
                component_name="UserProfileCard",
                file_path="src/components/UserProfileCard.vue",
                line_number=1,
                is_automated_converted=True,
                excerpt="<template><div class=\"profile\">...</div></template>",
            ),
            ClientComponentFinding(
                component_id="COMP-002",
                component_name="WeChatPayButton",
                file_path="src/components/WeChatPayButton.vue",
                line_number=45,
                is_automated_converted=False,
                hazard_code="PROPRIETARY_CONTAINER_API",
                hazard_reason="Calls wx.requestPayment directly in method",
                excerpt="wx.requestPayment({ timeStamp, nonceStr, package, ... })",
            ),
            ClientComponentFinding(
                component_id="COMP-003",
                component_name="StockChartCanvas",
                file_path="src/components/StockChartCanvas.vue",
                line_number=88,
                is_automated_converted=False,
                hazard_code="CUSTOM_CANVAS_WEBGL",
                hazard_reason="Direct HTML5 2D canvas context manipulation",
                excerpt="canvas.getContext('2d').beginPath();",
            ),
        ]

        ledger = ClientHandoffLedger.from_components(findings)

        self.assertEqual(ledger.total_components, 3)
        self.assertEqual(len(ledger.automated_converted), 1)
        self.assertEqual(len(ledger.handoff_items), 2)
        self.assertEqual(ledger.disposition_coverage, 1.0)
        self.assertTrue(ledger.is_100_percent_covered())

        data = ledger.to_dict()
        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["summary"]["coverage_rate"], 1.0)

        dossier = ledger.generate_markdown_dossier()
        self.assertIn("100% Accounted", dossier)
        self.assertIn("PROPRIETARY_CONTAINER_API", dossier)
        self.assertIn("CUSTOM_CANVAS_WEBGL", dossier)


if __name__ == "__main__":
    unittest.main()
