"""Unit tests for Pricing & Billing CLI."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout

from elmos_pricing_billing.cli import main
from elmos_pricing_billing.handlers import SKILL_REGISTRY


class TestCli(unittest.TestCase):
    def test_list_skills(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["list-skills"])
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["count"], 18)
        self.assertEqual(len(out["skills"]), 18)
        self.assertIn("elmos-pricing-product-model", out["skills"])
        self.assertIn("elmos-billing-orchestrator", out["skills"])

    def test_dispatch_valid_skill(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([
                "dispatch",
                "elmos-task-cost-estimation",
                "--tenant", "t-001",
                "--payload", json.dumps({"prompt_tokens": 1000, "completion_tokens": 500}),
            ])
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["skill"], "elmos-task-cost-estimation")
        self.assertEqual(out["status"], "SUCCESS")
        self.assertIn("estimated_cost_usd", out["outputs"])

    def test_dispatch_unknown_skill(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["dispatch", "unknown-skill"])
        self.assertEqual(code, 1)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["status"], "BLOCKED")

    def test_help_or_no_args(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()

