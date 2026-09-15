from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class AuthoritativeBusinessLineStatusTest(unittest.TestCase):
    def test_polyglot_inventory_is_conservative(self) -> None:
        inventory = load("routes/inventory.json")
        routes = inventory["routes"]
        self.assertEqual(len(routes), 210)
        self.assertEqual(Counter(route["status"] for route in routes), {"limited": 90, "research": 120})
        self.assertEqual(inventory["certified_route_count"], 0)
        for field in (
            "local_execution_evidence",
            "independent_verification_evidence",
            "external_certification_evidence",
        ):
            self.assertEqual(inventory[field], "NOT_RUN")

    def test_project_synthesis_ceiling_is_eight_limited_profiles(self) -> None:
        support = load("docs/project-synthesis/bundled-emitter-support.json")
        self.assertEqual(len(support["profiles"]), 8)
        self.assertEqual({profile["maturity"] for profile in support["profiles"]}, {"limited"})
        self.assertEqual(support["claim_ceiling"], "limited")
        self.assertEqual(support["independent_verification_status"], "NOT_RUN")
        self.assertEqual(support["external_evidence_status"], "NOT_RUN")
        self.assertEqual(support["certification_status"], "NOT_CERTIFIED")

    def test_frontend_miniapp_remains_declared(self) -> None:
        gate = load("client-packs/web-console-next16-react19-wechat-v1/certification/gate-result.json")
        external = load("client-packs/web-console-next16-react19-wechat-v1/certification/external-evidence-status.json")
        self.assertEqual(gate["pack_status"], "declared")
        self.assertEqual(gate["certification_decision"], "NOT_CERTIFIED")
        self.assertEqual(external["external_verification_status"], "NOT_RUN")
        self.assertEqual(external["certification"], "NOT_CERTIFIED")

    def test_all_repository_trust_anchors_are_revoked(self) -> None:
        for relative in (
            "certification/trust-store.json",
            "certification/batch1-37-trust-store.json",
            "certification/batch38-45-trust-store.json",
        ):
            trust = load(relative)
            self.assertTrue(trust["authorities"])
            self.assertTrue(all(anchor["revoked"] is True for anchor in trust["authorities"]))
        mature = load("certification/mature-product-trust-store.json")
        self.assertTrue(mature["keys"])
        self.assertTrue(all(anchor["revoked"] is True for anchor in mature["keys"]))

    def test_mature_product_external_records_are_not_accepted(self) -> None:
        for name in ("customer-alpha.json", "customer-beta.json", "independent-review.json"):
            record = load(f"test-suites/batch38-45-strict/external/{name}")
            self.assertIs(record["accepted"], False)
            self.assertIs(record["independent"], False)
        for batch in range(38, 46):
            gate = load(f"test-suites/batch38-45-strict/external/batch{batch}-gate.json")
            self.assertEqual(gate["status"], "BLOCKED")
            self.assertIs(gate["eligible"], False)


if __name__ == "__main__":
    unittest.main()
