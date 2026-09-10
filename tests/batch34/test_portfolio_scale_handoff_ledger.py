"""Unit tests for PortfolioScaleHandoffLedger in batch34."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "batch34"))

from portfolio_scale_handoff_ledger import (
    PortfolioScaleHandoffLedger,
    PortfolioWorkUnitFinding,
)


class TestPortfolioScaleHandoffLedger(unittest.TestCase):
    def test_portfolio_scale_handoff_ledger_100_percent_coverage(self) -> None:
        findings = [
            PortfolioWorkUnitFinding(
                unit_id="WU-00001",
                repository_id="core-auth-service",
                path="services/auth",
                is_automated_scheduled=True,
                excerpt="package com.enterprise.auth...",
            ),
            PortfolioWorkUnitFinding(
                unit_id="WU-00002",
                repository_id="legacy-crm-module",
                path="modules/crm",
                is_automated_scheduled=False,
                hazard_code="CIRCULAR_REPO_DEPENDENCY",
                hazard_reason="Cyclic dependency detected: crm -> billing -> crm",
                excerpt="dependency crm -> billing",
            ),
            PortfolioWorkUnitFinding(
                unit_id="WU-00003",
                repository_id="external-vendor-sdk",
                path="submodules/vendor-sdk",
                is_automated_scheduled=False,
                hazard_code="DECOUPLED_EXTERNAL_SUBMODULE",
                hazard_reason="Private Git submodule commit not mirrored in internal cache",
                excerpt="git submodule update --init",
            ),
        ]

        ledger = PortfolioScaleHandoffLedger.from_work_units(findings)

        self.assertEqual(ledger.total_units, 3)
        self.assertEqual(len(ledger.automated_scheduled), 1)
        self.assertEqual(len(ledger.handoff_items), 2)
        self.assertEqual(ledger.disposition_coverage, 1.0)
        self.assertTrue(ledger.is_100_percent_covered())

        data = ledger.to_dict()
        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["summary"]["coverage_rate"], 1.0)

        dossier = ledger.generate_markdown_dossier()
        self.assertIn("100% Accounted", dossier)
        self.assertIn("CIRCULAR_REPO_DEPENDENCY", dossier)
        self.assertIn("DECOUPLED_EXTERNAL_SUBMODULE", dossier)


if __name__ == "__main__":
    unittest.main()
