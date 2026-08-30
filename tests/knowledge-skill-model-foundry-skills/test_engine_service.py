"""Root-level runtime integration tests for the compiled Foundry catalog."""

from __future__ import annotations

import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.kernel import ExecutionKernel, KernelSecurityError
from elmos_foundry.service import FoundryService
from elmos_foundry.skills import EXPECTED_PIPELINES


def digest(character: str) -> str:
    return "sha256:" + character * 64


class EngineServiceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.service = FoundryService(kernel=self.kernel)
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-root-01",
            project_id="project-root-01",
            actor_id="actor-root-01",
            environment_id="integration",
            workspace_digest=digest("a"),
            revision_set_id=digest("b"),
            purpose="integration-test",
            capabilities=("foundry.pipeline.prepare", "foundry.skill.prepare"),
            ttl_seconds=600,
        )

    def test_meta_route_and_atomic_binding_are_bounded_prepare_only(self) -> None:
        atomic = self.service.route_meta_skill("elmos-00-foundation-contracts")
        self.assertGreater(len(atomic), 0)
        self.assertLessEqual(len(atomic), 8)
        record = self.service.skills.get_skill_record(atomic[0])
        assert record is not None
        payload = {name: f"fixture-for-{name}" for name in record["inputs"]}
        first_input = record["inputs"][0]
        payload[first_input] = "must-not-echo"
        payload["operation"] = "prepare"
        result = self.service.execute_skill(
            atomic[0],
            payload,
            tenant_scope=self.scope,
        )
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.outputs["semantic_execution_status"], "NOT_RUN")
        self.assertEqual(result.outputs["external_evidence_status"], "NOT_RUN")
        self.assertEqual(result.outputs["certification_status"], "NOT_CERTIFIED")
        self.assertNotIn("must-not-echo", str(result.outputs))

    def test_all_14_pipelines_prepare_without_external_effects(self) -> None:
        self.assertEqual(len(EXPECTED_PIPELINES), 14)
        for pipeline in sorted(EXPECTED_PIPELINES):
            plan = self.service.run_pipeline(pipeline, {}, tenant_scope=self.scope)
            self.assertEqual(plan["pipeline"], pipeline)
            self.assertEqual(plan["status"], "BLOCKED")
            self.assertEqual(plan["execution_status"], "NOT_RUN")
            self.assertFalse(plan["side_effects_authorized"])
            self.assertEqual(plan["certification_status"], "NOT_CERTIFIED")

    def test_directly_constructed_scope_has_no_runtime_authority(self) -> None:
        forged = TenantScope(tenant_id="tenant-root-01", project_id="project-root-01")
        with self.assertRaises(KernelSecurityError):
            self.service.run_pipeline("knowledge-to-skill", {}, tenant_scope=forged)


if __name__ == "__main__":
    unittest.main()
