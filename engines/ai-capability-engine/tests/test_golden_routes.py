"""Tests for Golden Route execution and validation."""

from __future__ import annotations

import unittest
from elmos_ai_capability.golden_routes import GoldenRouteEngine


class GoldenRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = GoldenRouteEngine()

    def test_23_golden_routes_present(self) -> None:
        routes = self.engine.list_routes()
        self.assertEqual(len(routes), 23)
        self.assertIn("acp-coding-agent-client", routes)
        self.assertIn("mcp-2026-modernization", routes)
        self.assertIn("zero-trust-confidential-agent", routes)

    def test_execute_acp_route(self) -> None:
        res = self.engine.execute_route("acp-coding-agent-client")
        self.assertEqual(res.status, "QUALIFIED")
        self.assertGreater(len(res.targets), 0)
        self.assertTrue(res.evidence_digest.startswith("sha256:"))

    def test_validate_all_routes(self) -> None:
        results = self.engine.validate_all_routes()
        self.assertEqual(len(results), 23)
        for name, res in results.items():
            self.assertEqual(res.status, "QUALIFIED", f"Route {name} did not qualify")


if __name__ == "__main__":
    unittest.main()
