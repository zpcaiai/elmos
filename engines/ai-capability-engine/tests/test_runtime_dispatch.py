"""Tests for runtime dispatching across all 296 skills and 30 batches."""

from __future__ import annotations

import unittest
from pathlib import Path
import yaml

from elmos_ai_capability.runtime import AICapabilityRuntime

ROOT = Path(__file__).resolve().parents[3]
BATCHES_FILE = ROOT / "skills/elmos-ai-capability-enhancement-skills-v4.1.0/implementation/batches.yaml"
REGISTRY_FILE = ROOT / "skills/elmos-ai-capability-enhancement-skills-v4.1.0/catalog/skill-registry.yaml"


class RuntimeDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = AICapabilityRuntime()
        cls.batches_data = yaml.safe_load(BATCHES_FILE.read_text(encoding="utf-8"))["spec"]["batches"]
        cls.registry_data = yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))["spec"]["skills"]

    def test_all_30_batches_present(self) -> None:
        self.assertEqual(len(self.batches_data), 30)
        batch_ids = [b["id"] for b in self.batches_data]
        self.assertEqual(batch_ids[0], "CAP-00")
        self.assertEqual(batch_ids[-1], "CAP-29")

    def test_all_296_skills_in_registry(self) -> None:
        self.assertEqual(len(self.registry_data), 296)

    def test_dispatch_sample_from_every_batch(self) -> None:
        for batch in self.batches_data:
            tasks = batch.get("tasks", [])
            self.assertTrue(len(tasks) > 0)
            first_task = tasks[0]
            skill_name = first_task["skill"]
            res = self.runtime.execute_skill(skill_name, {
                "tenant_id": "test-tenant-1",
                "project_id": "proj-1",
                "goal_id": "goal-1",
            })
            self.assertEqual(res.status, "SUCCESS", f"Failed on skill {skill_name} in batch {batch['id']}")
            self.assertTrue(res.evidence_digest.startswith("sha256:"))

    def test_specialized_a2a_skill_handler(self) -> None:
        res = self.runtime.execute_skill("elmos-a2a-v1-agent-card-trust-compiler", {
            "agent_id": "agent-alpha",
            "tenant_id": "t1",
            "capabilities": ["inference", "code_gen"],
        })
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("agent-card.json", res.outputs)
        self.assertIn("agent-card.jws", res.outputs)

    def test_specialized_model_router_handler(self) -> None:
        res = self.runtime.execute_skill("elmos-model-routing-quality-cost-latency-optimizer", {
            "task_type": "coding",
            "max_cost": 0.05,
        })
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.outputs["selected_model"], "claude-3-5-sonnet")

    def test_all_296_skills_dispatched_and_executed(self) -> None:
        self.assertEqual(self.runtime.handler_count, 296)
        for skill_entry in self.registry_data:
            skill_name = skill_entry["name"]
            self.assertTrue(self.runtime.has_handler(skill_name), f"Missing handler for {skill_name}")
            res = self.runtime.execute_skill(skill_name, {
                "tenant_id": "tenant-test-296",
                "project_id": "proj-test-296",
                "goal_id": "goal-coverage-296",
            })
            self.assertEqual(res.status, "SUCCESS", f"Failed on skill {skill_name}")
            self.assertTrue(res.evidence_digest.startswith("sha256:"), f"Invalid digest for {skill_name}")
            self.assertIn("artifact_manifest", res.outputs)
            self.assertEqual(res.outputs["tenant_id"], "tenant-test-296")
            self.assertEqual(res.outputs["project_id"], "proj-test-296")

    def test_blocked_on_missing_tenant_scope(self) -> None:
        res = self.runtime.execute_skill("elmos-a2a-v1-agent-card-trust-compiler", {
            "tenant_id": "",
            "project_id": "",
        })
        self.assertEqual(res.status, "BLOCKED")


if __name__ == "__main__":
    unittest.main()

