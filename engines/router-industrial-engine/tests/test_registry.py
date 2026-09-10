"""Tests for Model and Provider Registry."""

from __future__ import annotations

from pathlib import Path
import unittest

from elmos_router_industrial.domain.contracts import ExecutionLane, ModelLifecycle
from elmos_router_industrial.registry.registry import DeploymentRegistry

CONFIGS_DIR = Path(__file__).resolve().parents[4] / "skills/subskills/elmos-router-industrial-skillpack/configs"
if not CONFIGS_DIR.exists():
    CONFIGS_DIR = Path("/Users/stephen/.gemini/antigravity/brain/28d35f92-a69f-4629-8da0-fdda5777b2c7/scratch/elmos-router-industrial-skillpack/configs")


class TestRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DeploymentRegistry()
        with open(CONFIGS_DIR / "model-registry.example.yaml", "r", encoding="utf-8") as f:
            self.yaml_content = f.read()

    def test_load_from_yaml(self) -> None:
        snapshot = self.registry.load_from_yaml(self.yaml_content)
        self.assertEqual(snapshot.version, "2026-09-09.1")

        # Models
        model = snapshot.get_model("strategic-coding-high")
        self.assertIsNotNone(model)
        self.assertEqual(model.lifecycle, ModelLifecycle.STABLE)
        self.assertTrue(model.supportsToolCalling)
        self.assertEqual(model.taskBenchmarks.get("LARGE_REFACTOR"), 0.96)

        # Providers
        provider = snapshot.get_provider("openai-direct")
        self.assertIsNotNone(provider)
        self.assertTrue(provider.enabled)

        # Deployments
        deployments = snapshot.get_deployments_for_model("strategic-coding-high")
        self.assertEqual(len(deployments), 2)
        lanes = {d.lane for d in deployments}
        self.assertEqual(lanes, {ExecutionLane.NATIVE_DIRECT, ExecutionLane.OPENROUTER})

    def test_health_updates(self) -> None:
        self.registry.load_from_yaml(self.yaml_content)
        dep_id = "strategic-coding-high-openai-native"

        init_health = self.registry.current.get_health(dep_id)
        self.assertTrue(init_health.is_healthy())

        # Update health to degrade
        updated = self.registry.update_health(
            deployment_id=dep_id,
            availability=0.60,
            rate_limit_pressure=0.98,
            circuit_open=True,
        )
        self.assertEqual(updated.availability, 0.60)
        self.assertFalse(updated.is_healthy())
        self.assertTrue(self.registry.current.get_health(dep_id).circuitOpen)

    def test_version_rollback(self) -> None:
        v1 = self.registry.load_from_yaml(self.yaml_content)
        # Load v2 with different version
        v2_content = self.yaml_content.replace("2026-09-09.1", "2026-09-10.2")
        v2 = self.registry.load_from_yaml(v2_content)
        self.assertEqual(self.registry.current.version, "2026-09-10.2")

        # Rollback
        rolled = self.registry.rollback_to_version("2026-09-09.1")
        self.assertEqual(rolled.version, "2026-09-09.1")
        self.assertEqual(self.registry.current.version, "2026-09-09.1")


if __name__ == "__main__":
    unittest.main()
