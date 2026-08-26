#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from quote_reference import calculate_quote  # noqa: E402


class QuoteReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads((ROOT / "examples" / "quote-calculator-input.example.json").read_text(encoding="utf-8"))

    def test_ranges_are_monotonic_and_cap_is_safe(self) -> None:
        result = calculate_quote(self.payload)
        costs = result["estimated_cost"]
        self.assertLessEqual(costs["p50_minor"], costs["p80_minor"])
        self.assertLessEqual(costs["p80_minor"], costs["p90_minor"])
        self.assertGreaterEqual(result["recommended_hard_cap_minor"], costs["p90_minor"])

    def test_byok_excludes_customer_owned_model_only(self) -> None:
        managed = calculate_quote(self.payload)
        byok_payload = dict(self.payload)
        byok_payload["byok"] = True
        byok = calculate_quote(byok_payload)
        self.assertLess(byok["estimated_cost"]["p50_minor"], managed["estimated_cost"]["p50_minor"])
        infra = [d for d in byok["resource_breakdown"] if d["category"] == "infrastructure"]
        self.assertTrue(all(not d["byok_excluded"] and d["customer_charge_minor"] > 0 for d in infra))
        models = [d for d in byok["resource_breakdown"] if d["category"] == "managed_model"]
        self.assertTrue(all(d["byok_excluded"] and d["customer_charge_minor"] == 0 for d in models))

    def test_machine_runtime_is_separate_from_human_effort(self) -> None:
        result = calculate_quote(self.payload)
        self.assertIn("machine_runtime", result)
        self.assertEqual(result["human_effort_reference"], {"value": 10, "unit": "person_days"})
        self.assertEqual(result["machine_runtime"]["p50_seconds"], 8400)

    def test_requested_cap_below_p50_is_rejected(self) -> None:
        baseline = calculate_quote(self.payload)
        payload = dict(self.payload)
        payload["requested_hard_cap_minor"] = baseline["estimated_cost"]["p50_minor"] - 1
        with self.assertRaises(ValueError):
            calculate_quote(payload)


if __name__ == "__main__":
    unittest.main()
