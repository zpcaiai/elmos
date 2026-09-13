"""Tests for Pricing & Billing local qualification receipt and package invariants."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from elmos_pricing_billing.handlers import SKILL_REGISTRY

ROOT = Path(__file__).resolve().parents[1]


class TestQualificationContract(unittest.TestCase):
    """Validates local qualification receipt and fail-closed non-self-certification boundaries."""

    def test_local_qualification_receipt(self) -> None:
        receipt_file = ROOT / "qualification" / "local-qualification.json"
        self.assertTrue(receipt_file.exists())
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))

        self.assertEqual(receipt["package_id"], "elmos-pricing-billing-skills-v1.0.0")
        self.assertEqual(receipt["package_version"], "1.0.0")
        self.assertEqual(receipt["skills_count"], 18)
        self.assertEqual(receipt["qualification_state"], "QUALIFIED_SELF_ATTESTED")
        self.assertEqual(receipt["evidence_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertFalse(receipt["side_effects_authorized"])

        # Strict Non-Self-Certification Boundary
        self.assertEqual(receipt["certification"], "NOT_CERTIFIED")
        self.assertEqual(receipt["external_evidence_status"], "NOT_RUN")
        self.assertEqual(receipt["customer_evidence_status"], "NOT_RUN")

    def test_skills_count_matches_registry(self) -> None:
        receipt_file = ROOT / "qualification" / "local-qualification.json"
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        declared_count = receipt["skills_count"]
        self.assertEqual(len(SKILL_REGISTRY), declared_count)

    def test_all_skills_have_expected_prefix(self) -> None:
        for skill_name in SKILL_REGISTRY:
            self.assertTrue(skill_name.startswith("elmos-"), f"Unexpected skill name: {skill_name}")


if __name__ == "__main__":
    unittest.main()

