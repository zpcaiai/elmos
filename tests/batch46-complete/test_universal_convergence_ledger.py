"""Tests for Universal Enterprise Convergence Ledger."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts/batch46-complete"

spec = importlib.util.spec_from_file_location(
    "universal_convergence_ledger",
    SCRIPTS_DIR / "universal_convergence_ledger.py",
)
ledger_module = importlib.util.module_from_spec(spec)
sys.modules["universal_convergence_ledger"] = ledger_module
spec.loader.exec_module(ledger_module)

ConvergenceDispositionSummary = ledger_module.ConvergenceDispositionSummary
ConvergenceItemStatus = ledger_module.ConvergenceItemStatus
ConvergenceModuleItem = ledger_module.ConvergenceModuleItem
UniversalEnterpriseConvergenceLedger = ledger_module.UniversalEnterpriseConvergenceLedger


class TestUniversalEnterpriseConvergenceLedger(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = UniversalEnterpriseConvergenceLedger()

    def test_empty_scan(self) -> None:
        summary = self.ledger.scan_and_classify([])
        self.assertEqual(summary.total_items, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertFalse(summary.is_fully_dispositioned)

    def test_all_automated(self) -> None:
        items = [
            ConvergenceModuleItem(
                module_id="CONV-001",
                subsystem="WORKFLOW_RUNTIME",
                status=ConvergenceItemStatus.CONVERGENCE_VERIFIED,
                target_repo_or_slice="core/workflow-engine",
            ),
            ConvergenceModuleItem(
                module_id="CONV-002",
                subsystem="POLICY_ENGINE",
                status=ConvergenceItemStatus.KERNEL_INTEGRATED,
                target_repo_or_slice="security/policy-bundle",
            ),
            ConvergenceModuleItem(
                module_id="CONV-003",
                subsystem="EVIDENCE_GRAPH",
                status=ConvergenceItemStatus.WORKFLOW_RUNTIME_ALIGNED,
                target_repo_or_slice="evidence/merkle-ledger",
            ),
        ]
        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 3)
        self.assertEqual(summary.automated_converged_count, 3)
        self.assertEqual(summary.governance_handoff_count, 0)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

    def test_mixed_dual_track_100_percent_disposition(self) -> None:
        items = [
            ConvergenceModuleItem(
                module_id="CONV-101",
                subsystem="CAPABILITY_REGISTRY",
                status=ConvergenceItemStatus.CONVERGENCE_VERIFIED,
                target_repo_or_slice="registry/capabilities.json",
            ),
            ConvergenceModuleItem(
                module_id="CONV-102",
                subsystem="DEPENDENCY_GRAPH",
                status=ConvergenceItemStatus.CIRCULAR_KERNEL_DEPENDENCY_DETECTED,
                target_repo_or_slice="subsystems/billing-to-auth",
                priority="P0",
            ),
            ConvergenceModuleItem(
                module_id="CONV-103",
                subsystem="POLICY_BUNDLE",
                status=ConvergenceItemStatus.POLICY_FAIL_OPEN_QUARANTINED,
                target_repo_or_slice="policies/custom-tenant-rules",
                priority="P0",
            ),
            ConvergenceModuleItem(
                module_id="CONV-104",
                subsystem="DESIGN_PARTNER",
                status=ConvergenceItemStatus.UNVERIFIED_DESIGN_PARTNER_WORKLOAD,
                target_repo_or_slice="partners/customer-c",
                priority="P1",
            ),
            ConvergenceModuleItem(
                module_id="CONV-105",
                subsystem="DELIVERY_MODEL",
                status=ConvergenceItemStatus.MARGIN_DEFICIT_DELIVERY_MODEL,
                target_repo_or_slice="finance/delivery-pilot.json",
                priority="P1",
            ),
            ConvergenceModuleItem(
                module_id="CONV-106",
                subsystem="SLA_PROOF",
                status=ConvergenceItemStatus.SLA_OBSERVATION_WINDOW_INSUFFICIENT,
                target_repo_or_slice="ops/soak-metrics.json",
                priority="P2",
            ),
            ConvergenceModuleItem(
                module_id="CONV-107",
                subsystem="LEGACY_MONOLITH",
                status=ConvergenceItemStatus.UNACCOUNTED_BLACKBOX_ENTERPRISE_MODULE,
                target_repo_or_slice="legacy/unmapped-service",
                priority="P1",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        self.assertEqual(summary.total_items, 7)
        self.assertEqual(summary.automated_converged_count, 1)
        self.assertEqual(summary.governance_handoff_count, 6)
        self.assertEqual(summary.disposition_coverage, 1.0)
        self.assertTrue(summary.is_fully_dispositioned)

        self.assertIn("acyclic mediator", items[1].remediation_strategy)
        self.assertIn("default deny", items[2].remediation_strategy)
        self.assertIn("rollback drill", items[3].remediation_strategy)

    def test_dossier_generation_and_write(self) -> None:
        items = [
            ConvergenceModuleItem(
                module_id="CONV-201",
                subsystem="KERNEL",
                status=ConvergenceItemStatus.KERNEL_INTEGRATED,
                target_repo_or_slice="kernel/runtime",
            ),
            ConvergenceModuleItem(
                module_id="CONV-202",
                subsystem="PARTNER_WORKLOAD",
                status=ConvergenceItemStatus.UNVERIFIED_DESIGN_PARTNER_WORKLOAD,
                target_repo_or_slice="partners/customer-x",
                priority="P0",
            ),
        ]

        summary = self.ledger.scan_and_classify(items)
        json_data = self.ledger.generate_convergence_json(summary)
        self.assertEqual(json_data["total_items"], 2)
        self.assertEqual(json_data["automated_converged_count"], 1)
        self.assertEqual(json_data["governance_handoff_count"], 1)
        self.assertEqual(json_data["disposition_coverage_ratio"], 1.0)
        self.assertTrue(json_data["is_fully_dispositioned"])

        md_text = self.ledger.generate_markdown_dossier(summary)
        self.assertIn("Batch 46 Complete Product Convergence Disposition Dossier", md_text)
        self.assertIn("100% Accounted", md_text)
        self.assertIn("`CONV-202`", md_text)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = self.ledger.write_handoff_dossier(summary, Path(tmpdir))
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

            saved_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_json["total_items"], 2)


if __name__ == "__main__":
    unittest.main()
