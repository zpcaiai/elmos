"""Foundry service facade tests for truthful local preparation behavior."""

from __future__ import annotations

import unittest

from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.service import FoundryService


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FoundryService()
        cls.scope = cls.service.kernel.mint_context(
            tenant_id="tenant-svc-01",
            project_id="proj-svc-01",
            actor_id="actor-svc-01",
            environment_id="env-svc-01",
            workspace_digest="sha256:" + "2" * 64,
            revision_set_id="sha256:" + "b" * 64,
            purpose="service-tests",
            capabilities=("foundry.pipeline.prepare", "foundry.skill.prepare"),
            ttl_seconds=600,
            invocation_id="inv-service-01",
            lease_id="lease-service-01",
        )

    def test_status_reports_bounded_runtime_not_certification(self) -> None:
        status = self.service.status()
        self.assertEqual(status["status"], "LOCAL_RUNTIME_BOUND")
        self.assertEqual(status["atomic_skills"], 1310)
        self.assertEqual(status["meta_skills"], 41)
        self.assertEqual(status["bindings"], 1310)
        self.assertEqual(
            status["implementation_status"], "MIXED_LOCAL_AND_PREPARE_ONLY"
        )
        self.assertEqual(status["capability_states"], {"LOCAL": 26, "PREPARE_ONLY": 1_284})
        self.assertEqual(status["local_evidence_status"], "NOT_RUN")
        self.assertEqual(
            status["local_evidence_ceiling"], "LOCAL_EXECUTED_SELF_ATTESTED"
        )
        self.assertEqual(status["external_evidence_status"], "NOT_RUN")
        self.assertEqual(status["certification_status"], "NOT_CERTIFIED")

    def test_service_routes_with_bounded_activation(self) -> None:
        matches = self.service.route_meta_skill("elmos-00-foundation-contracts", activation_limit=3)
        self.assertGreater(len(matches), 0)
        self.assertLessEqual(len(matches), 3)

    def test_service_prepare_skill_preserves_fail_closed_states(self) -> None:
        skill = self.service.route_meta_skill("elmos-00-foundation-contracts")[0]
        record = self.service.skills.get_skill_record(skill)
        assert record is not None
        incomplete = self.service.execute_skill(
            skill,
            {"operation": "prepare"},
            tenant_scope=self.scope,
        )
        self.assertEqual(incomplete.status, "BLOCKED")
        self.assertTrue(incomplete.outputs["missing_declared_inputs"])
        payload = {name: f"fixture-for-{name}" for name in record["inputs"]}
        payload["operation"] = "prepare"
        result = self.service.execute_skill(
            skill,
            payload,
            tenant_scope=self.scope,
        )
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.outputs["outcome"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(result.outputs["semantic_execution_status"], "NOT_RUN")
        self.assertEqual(result.outputs["maximum_local_decision"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(result.outputs["certification_status"], "NOT_CERTIFIED")

    def test_pipeline_service_has_no_synthetic_defaults(self) -> None:
        blocked = self.service.run_pipeline("knowledge-to-skill", {}, tenant_scope=self.scope)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(set(blocked["missing_required_inputs"]), {"source_id", "document_text", "skill_name"})
        self.assertEqual(blocked["execution_status"], "NOT_RUN")

    def test_unknown_pipeline_is_explicit(self) -> None:
        result = self.service.run_pipeline("invented-pipeline", {}, tenant_scope=self.scope)
        self.assertEqual(result["status"], "UNKNOWN_PIPELINE")
        self.assertEqual(result["execution_status"], "NOT_RUN")

    def test_injected_kernel_is_the_service_authority(self) -> None:
        kernel = ExecutionKernel()
        service = FoundryService(kernel=kernel)
        self.assertIs(service.kernel, kernel)
        scope = kernel.mint_context(
            tenant_id="tenant-injected-01",
            project_id="project-injected-01",
            actor_id="actor-injected-01",
            environment_id="env-injected-01",
            workspace_digest="sha256:" + "5" * 64,
            revision_set_id="sha256:" + "e" * 64,
            purpose="injected-kernel-test",
            capabilities=("foundry.pipeline.prepare",),
            ttl_seconds=600,
            invocation_id="inv-injected-01",
            lease_id="lease-injected-01",
        )
        result = service.run_pipeline("knowledge-to-skill", {}, tenant_scope=scope)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["execution_status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
