"""Unit tests for the 4 core lifecycle pipelines."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.service import FoundryService


class GoldenPipelinesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FoundryService()
        self.scope = TenantScope(tenant_id="tenant-gold-01", project_id="proj-gold-01")

    def test_knowledge_to_skill_pipeline(self) -> None:
        res = self.service.run_pipeline(
            "knowledge-to-skill",
            {
                "source_id": "doc-01",
                "document_text": "Specification for banking transaction isolation",
                "skill_name": "elmos-bank-tx-isolation",
            },
            tenant_scope=self.scope,
        )
        self.assertEqual(res["status"], "COMPLETED")
        self.assertIn("knowledge_object_id", res)
        self.assertIn("evidence_bundle_id", res)

    def test_experience_to_dataset_pipeline(self) -> None:
        res = self.service.run_pipeline(
            "experience-to-dataset",
            {
                "dataset_name": "fintech-code-dataset",
                "task_type": "sql_migration",
            },
            tenant_scope=self.scope,
        )
        self.assertEqual(res["status"], "COMPLETED")
        self.assertIn("dataset_id", res)
        self.assertGreater(res["item_count"], 0)

    def test_train_certify_deploy_pipeline(self) -> None:
        res = self.service.run_pipeline(
            "train-certify-deploy",
            {
                "base_model": "qwen2.5-coder-32b",
                "adapter_name": "sql-optimizer-lora",
                "dataset_id": "ds-01",
                "skill_set": ["00-foundation-contracts"],
            },
            tenant_scope=self.scope,
        )
        self.assertEqual(res["status"], "COMPLETED")
        self.assertIn("release_id", res)
        self.assertEqual(res["gate_level"], "GateLevel.E4_PRODUCTION_CERTIFIED")

    def test_customer_private_adapter_pipeline(self) -> None:
        res = self.service.run_pipeline(
            "customer-private-adapter",
            {
                "base_model": "deepseek-v3",
                "adapter_name": "acme-corp-private-adapter",
                "customer_docs": ["ACME internal proprietary billing APIs"],
            },
            tenant_scope=self.scope,
        )
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["tenant_id"], self.scope.tenant_id)
        self.assertIn("release_id", res)
        self.assertIn("dataset_id", res)


if __name__ == "__main__":
    unittest.main()
