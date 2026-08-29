"""Root-level engine service execution tests."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.service import FoundryService


class EngineServiceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FoundryService()
        self.scope = TenantScope(tenant_id="tenant-root-01", project_id="proj-root-01")

    def test_meta_skill_routing_and_execution(self) -> None:
        # Route through 00-foundation-contracts
        atomic_list = self.service.route_meta_skill("elmos-00-foundation-contracts")
        self.assertGreater(len(atomic_list), 0)

        # Execute first atomic skill
        first_skill = atomic_list[0]
        res = self.service.execute_skill(
            skill_name=first_skill,
            inputs={"test": "data"},
            tenant_scope=self.scope,
        )
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("COMPLETED", str(res.outputs))

    def test_all_four_lifecycle_pipelines(self) -> None:
        # 1. knowledge-to-skill
        r1 = self.service.run_pipeline("knowledge-to-skill", {"source_id": "s1", "document_text": "Rules", "skill_name": "rule-skill"}, tenant_scope=self.scope)
        self.assertEqual(r1["status"], "COMPLETED")

        # 2. experience-to-dataset
        r2 = self.service.run_pipeline("experience-to-dataset", {"dataset_name": "ds1"}, tenant_scope=self.scope)
        self.assertEqual(r2["status"], "COMPLETED")

        # 3. train-certify-deploy
        r3 = self.service.run_pipeline("train-certify-deploy", {"base_model": "qwen", "adapter_name": "ad1", "dataset_id": "ds1", "skill_set": ["s1"]}, tenant_scope=self.scope)
        self.assertEqual(r3["status"], "COMPLETED")

        # 4. customer-private-adapter
        r4 = self.service.run_pipeline("customer-private-adapter", {"base_model": "deepseek", "adapter_name": "cust-ad", "customer_docs": ["Doc 1"]}, tenant_scope=self.scope)
        self.assertEqual(r4["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
