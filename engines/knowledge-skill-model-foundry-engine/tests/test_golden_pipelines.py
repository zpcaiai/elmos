"""All 14 pipelines are deterministic plans, never synthetic execution."""

from __future__ import annotations

import unittest

from elmos_foundry.pipelines import PIPELINE_PROFILE_REGISTRY
from elmos_foundry.service import FoundryService


class GoldenPipelinesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FoundryService()
        cls.scope = cls.service.kernel.mint_context(
            tenant_id="tenant-gold-01",
            project_id="proj-gold-01",
            actor_id="actor-gold-01",
            environment_id="env-gold-01",
            workspace_digest="sha256:" + "3" * 64,
            revision_set_id="sha256:" + "c" * 64,
            purpose="pipeline-tests",
            capabilities=("foundry.pipeline.prepare",),
            ttl_seconds=600,
            invocation_id="inv-pipeline-01",
            lease_id="lease-pipeline-01",
        )

    @staticmethod
    def _complete_params(required: tuple[str, ...]) -> dict[str, object]:
        params: dict[str, object] = {}
        for name in required:
            if name in {"skill_set", "customer_docs"}:
                params[name] = [f"{name}-item"]
            elif name.endswith("contract") or name == "acceptance_criteria":
                params[name] = {"id": f"{name}-v1"}
            else:
                params[name] = f"{name}-v1"
        return params

    def test_exact_14_pipeline_registry_prepares_without_effects(self) -> None:
        self.assertEqual(len(PIPELINE_PROFILE_REGISTRY), 14)
        for name, profile in PIPELINE_PROFILE_REGISTRY.items():
            with self.subTest(pipeline=name):
                result = self.service.run_pipeline(name, self._complete_params(profile.required_inputs), tenant_scope=self.scope)
                self.assertEqual(result["status"], "READY_FOR_EXTERNAL_GATE")
                self.assertEqual(result["execution_mode"], "PREPARE_ONLY")
                self.assertEqual(result["execution_status"], "NOT_RUN")
                self.assertFalse(result["side_effects_authorized"])
                self.assertEqual(result["external_evidence_status"], "NOT_RUN")
                self.assertEqual(result["certification_status"], "NOT_CERTIFIED")
                self.assertTrue(result["required_adapters"])
                self.assertTrue(result["external_effects"])
                self.assertRegex(result["plan_digest"], r"^[0-9a-f]{64}$")
                self.assertNotIn("release_id", result)
                self.assertNotIn("evidence_bundle_id", result)

    def test_pipeline_plan_is_deterministic_and_does_not_echo_sensitive_values(self) -> None:
        params = {"base_model": "model-private", "adapter_name": "adapter-private", "customer_docs": ["secret customer rule that must not be echoed"]}
        first = self.service.run_pipeline("customer-private-adapter", params, tenant_scope=self.scope)
        second = self.service.run_pipeline("customer-private-adapter", params, tenant_scope=self.scope)
        self.assertEqual(first["plan_digest"], second["plan_digest"])
        self.assertNotIn("secret customer rule", str(first))
        self.assertEqual(first["execution_status"], "NOT_RUN")

    def test_missing_pipeline_inputs_are_validation_failure_not_readiness(self) -> None:
        result = self.service.run_pipeline(
            "knowledge-to-skill", {}, tenant_scope=self.scope
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["local_validation_status"], "FAILED_SELF_ATTESTED")
        self.assertEqual(result["local_evidence_status"], "NOT_RUN")
        self.assertEqual(result["maximum_local_decision"], "NOT_READY")
        self.assertEqual(result["execution_status"], "NOT_RUN")
        self.assertEqual(
            set(result["missing_required_inputs"]),
            {"source_id", "document_text", "skill_name"},
        )

    def test_legacy_four_workflow_methods_are_preparation_only(self) -> None:
        plans = (
            self.service.pipelines.run_knowledge_to_skill_pipeline("source-1", "document", "skill-1", tenant_scope=self.scope),
            self.service.pipelines.run_experience_to_dataset_pipeline("dataset-1", tenant_scope=self.scope),
            self.service.pipelines.run_train_certify_deploy_pipeline("base", "adapter", "dataset-1", ["skill-1"], tenant_scope=self.scope),
            self.service.pipelines.run_customer_private_adapter_pipeline("base", "adapter", ["private doc"], tenant_scope=self.scope),
        )
        for plan in plans:
            self.assertEqual(plan["status"], "READY_FOR_EXTERNAL_GATE")
            self.assertEqual(plan["execution_status"], "NOT_RUN")
            self.assertEqual(plan["certification_status"], "NOT_CERTIFIED")
        self.assertFalse(self.service.knowledge._objects)
        self.assertFalse(self.service.memory._episodes)
        self.assertFalse(self.service.model._releases)


if __name__ == "__main__":
    unittest.main()
