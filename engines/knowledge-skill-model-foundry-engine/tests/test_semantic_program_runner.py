"""Tests for the Universal Typed 7-Stage Semantic Contract Program Interpreter."""

from __future__ import annotations

import unittest

from elmos_foundry.kernel import ExecutionKernel, KernelSecurityError
from elmos_foundry.semantic_program_runner import SemanticProgramRunner
from elmos_foundry.skills import SkillCatalog, load_compiled_catalog


class SemanticProgramRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-alpha",
            project_id="project-prime",
            actor_id="actor-test",
            environment_id="env-local",
            workspace_digest="sha256:" + "a" * 64,
            revision_set_id="sha256:" + "b" * 64,
            purpose="test-semantic-program-runner",
            invocation_id="inv-workflow-001",
            lease_id="lease-001",
            ttl_seconds=600,
            capabilities=(
                "foundry.adapter.execute",
                "foundry.store.read",
                "foundry.store.write",
                "foundry.retrieval.read",
            ),
        )
        self.catalog = load_compiled_catalog()
        self.runner = SemanticProgramRunner(self.kernel)

    def test_run_program_typed_synthesis_all_7_stages(self) -> None:
        skill_record = self.catalog.atomic_skills["dataset-lineage-and-provenance"]
        payload = {
            "inputs": {
                "experience episode": {"id": "ds-01"},
                "knowledge object": {"source": "git"},
                "human feedback": {"decision": "accepted"},
                "verification evidence": {"passed": True},
            }
        }
        res = self.runner.run_program(
            skill=skill_record,
            payload=payload,
            tenant_scope=self.scope,
            invocation_id="inv-workflow-001",
            catalog_digest=self.catalog.content_sha256,
        )
        self.assertEqual(res.status, "SUCCESS")
        self.assertFalse(res.external_effects_performed)

        # Check declared outputs were synthesized
        for out_name in skill_record["outputs"]:
            self.assertIn(out_name, res.outputs)
            doc = res.outputs[out_name]
            self.assertEqual(doc["output_name"], out_name)
            self.assertEqual(doc["tenant_id"], self.scope.tenant_id)
            self.assertEqual(doc["certification_status"], "NOT_CERTIFIED")
            self.assertEqual(doc["external_evidence_status"], "NOT_RUN")

        # Check 7-stage workflow execution metadata
        workflow_meta = res.outputs["_workflow_execution"]
        self.assertEqual(workflow_meta["total_stages"], 7)
        self.assertEqual(
            workflow_meta["stages_completed"],
            ["authorize", "snapshot", "plan", "execute", "verify", "emit-evidence", "commit-or-rollback"],
        )
        self.assertEqual(workflow_meta["evidence_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(workflow_meta["external_evidence_status"], "NOT_RUN")
        self.assertEqual(workflow_meta["certification_status"], "NOT_CERTIFIED")
        self.assertEqual(workflow_meta["local_maximum_decision"], "READY_FOR_EXTERNAL_GATE")

    def test_run_program_mismatched_invocation_fails_authorize(self) -> None:
        skill_record = self.catalog.atomic_skills["dataset-lineage-and-provenance"]
        payload = {"inputs": {}}
        with self.assertRaises(KernelSecurityError):
            self.runner.run_program(
                skill=skill_record,
                payload=payload,
                tenant_scope=self.scope,
                invocation_id="inv-different",
                catalog_digest=self.catalog.content_sha256,
            )

    def test_run_program_missing_declared_input_fails_plan(self) -> None:
        skill_record = self.catalog.atomic_skills["dataset-lineage-and-provenance"]
        # Intentionally omit required inputs
        payload = {"inputs": {"dataset item": {"id": "ds-01"}}}
        with self.assertRaises(ValueError) as ctx:
            self.runner.run_program(
                skill=skill_record,
                payload=payload,
                tenant_scope=self.scope,
                invocation_id="inv-workflow-001",
                catalog_digest=self.catalog.content_sha256,
            )
        self.assertIn("declared input(s) missing or null", str(ctx.exception))

    def test_catalog_execute_skill_with_workflow_operation(self) -> None:
        skill_catalog = SkillCatalog(self.kernel)
        payload = {
            "operation": "workflow",
            "inputs": {
                "experience episode": {"id": "ds-02"},
                "knowledge object": {"source": "s3"},
                "human feedback": {"decision": "accepted"},
                "verification evidence": {"passed": True},
            },
        }
        res = skill_catalog.execute_skill(
            "dataset-lineage-and-provenance",
            payload,
            self.scope,
            invocation_id="inv-workflow-001",
        )
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("_workflow_execution", res.outputs)
        self.assertEqual(res.outputs["_workflow_execution"]["total_stages"], 7)


if __name__ == "__main__":
    unittest.main()
