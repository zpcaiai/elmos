"""Unit tests for 17 meta-skills and 458 atomic skills catalog and router."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.skills import SkillCatalog


class SkillCatalogAndMetaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = SkillCatalog()
        self.scope = TenantScope(tenant_id="tenant-skill-01", project_id="proj-skill-01")

    def test_catalog_counts(self) -> None:
        self.assertEqual(self.catalog.total_atomic_skills, 458)
        self.assertEqual(self.catalog.total_meta_skills, 17)

    def test_meta_skill_routing(self) -> None:
        # Route through 00-foundation-contracts
        matches = self.catalog.route_meta_skill("elmos-00-foundation-contracts")
        self.assertGreater(len(matches), 0)

        # Lexical search query
        filtered = self.catalog.route_meta_skill("elmos-00-foundation-contracts", query="contract")
        self.assertGreater(len(filtered), 0)

    def test_atomic_skill_execution(self) -> None:
        res = self.catalog.execute_skill(
            "00-foundation-contracts",
            {"input_data": "sample"},
            tenant_scope=self.scope,
        )
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("COMPLETED", str(res.outputs))
        self.assertTrue(res.evidence_digest.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
