"""Tests for the typed local semantic workflow runner."""

from __future__ import annotations

import unittest

from elmos_foundry.canonical import canonical_digest
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

    def test_run_program_without_exact_handler_fails_closed(self) -> None:
        skill_record = self.catalog.atomic_skills["dataset-lineage-and-provenance"]
        payload = {
            "inputs": {
                "experience episode": {"id": "ds-01"},
                "knowledge object": {"source": "git"},
                "human feedback": {"decision": "accepted"},
                "verification evidence": {"passed": True},
            }
        }
        with self.assertRaisesRegex(KernelSecurityError, "no exact local semantic handler"):
            self.runner.run_program(
                skill=skill_record,
                payload=payload,
                tenant_scope=self.scope,
                invocation_id="inv-workflow-001",
                catalog_digest=self.catalog.content_sha256,
            )

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
        episode = {
            "nodes": [
                {
                    "tenant_id": self.scope.tenant_id,
                    "project_id": self.scope.project_id,
                    "node_id": "source-a",
                    "kind": "object",
                    "version": "1.0.0",
                    "content_digest": "sha256:" + "1" * 64,
                },
                {
                    "tenant_id": self.scope.tenant_id,
                    "project_id": self.scope.project_id,
                    "node_id": "sample-a",
                    "kind": "sample",
                    "version": "1.0.0",
                    "content_digest": "sha256:" + "2" * 64,
                },
            ],
            "edges": [
                {"parent": "source-a", "child": "sample-a", "relation": "derived-from"}
            ],
        }
        payload = {
            "operation": "workflow",
            "inputs": {
                "experience episode": episode,
                "knowledge object": {"experience_digest": canonical_digest(episode)},
                "human feedback": {"status": "NOT_RUN"},
                "verification evidence": {"status": "NOT_RUN"},
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
