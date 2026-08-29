"""Root-level integration tests for the Pricing & Billing Skills package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_pricing_billing_skills.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("pricing_billing_importer", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pricing billing importer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PricingBillingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def test_pinned_archive_and_sha256(self) -> None:
        archive_path = self.tool.resolve_archive()
        digest = self.tool.verify_archive(archive_path)
        self.assertEqual(digest, self.tool.EXPECTED_ARCHIVE_SHA256)

    def test_controlled_files_checksums(self) -> None:
        source_dir = ROOT / self.tool.SOURCE_RELATIVE
        controlled = source_dir / self.tool.PACKAGE_DIRECTORY if (source_dir / self.tool.PACKAGE_DIRECTORY).is_dir() else source_dir
        checked = self.tool.verify_controlled_files(controlled)
        self.assertEqual(len(checked), 129)

    def test_dual_root_installed_skills_parity(self) -> None:
        ws_skills = ROOT / ".agents/skills"
        rt_skills = ROOT / "agent-skills/runtime"

        skills = [
            "elmos-billing-admin-ux",
            "elmos-billing-observability-ops",
            "elmos-billing-orchestrator",
            "elmos-billing-testing-certification",
            "elmos-cost-margin-analytics",
            "elmos-credit-wallet-ledger",
            "elmos-enterprise-byok",
            "elmos-payments-reconciliation",
            "elmos-plan-catalog-entitlements",
            "elmos-pricing-product-model",
            "elmos-project-pricing-contracts",
            "elmos-quote-budget-guard",
            "elmos-refunds-disputes",
            "elmos-rollout-migration",
            "elmos-security-compliance",
            "elmos-subscription-invoicing",
            "elmos-task-cost-estimation",
            "elmos-usage-metering",
        ]
        for skill in skills:
            ws_target = ws_skills / skill / "SKILL.md"
            rt_target = rt_skills / skill / "SKILL.md"
            self.assertTrue(ws_target.is_file(), f"Missing {ws_target}")
            self.assertTrue(rt_target.is_file(), f"Missing {rt_target}")
            self.assertEqual(ws_target.read_bytes(), rt_target.read_bytes(), f"Parity mismatch on {skill}")

    def test_qualification_receipt(self) -> None:
        receipt_path = ROOT / "engines/pricing-billing-engine/qualification/local-qualification.json"
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["package_id"], self.tool.PACKAGE_ID)
        self.assertEqual(receipt["qualification_state"], "QUALIFIED_SELF_ATTESTED")
        self.assertEqual(receipt["skills_count"], 18)


if __name__ == "__main__":
    unittest.main()
