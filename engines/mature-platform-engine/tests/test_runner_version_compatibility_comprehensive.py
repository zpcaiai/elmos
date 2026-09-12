import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    RunnerCapability,
    RunnerRegistration,
    RunnerStatus
)
from elmos_mature_platform.runner_version_compatibility_engine import RunnerVersionCompatibilityEngine

class TestRunnerVersionCompatibilityComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = RunnerVersionCompatibilityEngine(
            control_plane_version="3.2.0",
            control_plane_protocol="3.0.0"
        )

    def _create_runner(self, runner_id="r-1", version="3.2.0", proto="3.0.0", caps=None, status=RunnerStatus.ACTIVE, jobs=0):
        return RunnerRegistration(
            runner_id=runner_id,
            hostname=f"host-{runner_id}",
            runner_version=version,
            protocol_version=proto,
            supported_capabilities=caps or [RunnerCapability.DOCKER_SANDBOX, RunnerCapability.GPU_PASSTHROUGH],
            status=status,
            active_jobs_count=jobs
        )

    def test_register_and_get_runner(self):
        runner = self._create_runner()
        self.engine.register_runner(runner)
        retrieved = self.engine.get_runner("r-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.runner_version, "3.2.0")

    def test_update_heartbeat(self):
        runner = self._create_runner()
        self.engine.register_runner(runner)
        ok = self.engine.update_heartbeat("r-1", active_jobs=2)
        self.assertTrue(ok)
        self.assertEqual(runner.active_jobs_count, 2)

    def test_compatibility_exact_match(self):
        res = self.engine.evaluate_compatibility("3.2.0", "3.0.0")
        self.assertTrue(res.compatible)
        self.assertEqual(res.version_relation, "exact")
        self.assertFalse(res.upgrade_required)

    def test_compatibility_n_minus_one(self):
        res = self.engine.evaluate_compatibility("3.1.5", "3.0.0")
        self.assertTrue(res.compatible)
        self.assertEqual(res.version_relation, "n_minus_1")
        self.assertFalse(res.upgrade_required)

    def test_compatibility_n_plus_one(self):
        res = self.engine.evaluate_compatibility("3.3.0", "3.0.0")
        self.assertTrue(res.compatible)
        self.assertEqual(res.version_relation, "n_plus_1")

    def test_compatibility_too_old_incompatible(self):
        res = self.engine.evaluate_compatibility("3.0.0", "3.0.0")
        self.assertFalse(res.compatible)
        self.assertEqual(res.version_relation, "too_old")
        self.assertTrue(res.upgrade_required)

    def test_compatibility_major_mismatch_incompatible(self):
        res = self.engine.evaluate_compatibility("2.9.0", "3.0.0")
        self.assertFalse(res.compatible)
        self.assertEqual(res.version_relation, "incompatible_major")

    def test_compatibility_protocol_mismatch_incompatible(self):
        res = self.engine.evaluate_compatibility("3.2.0", "2.0.0")
        self.assertFalse(res.compatible)
        self.assertEqual(res.version_relation, "incompatible_protocol")

    def test_compatibility_missing_required_capability(self):
        res = self.engine.evaluate_compatibility(
            "3.2.0", "3.0.0",
            required_capabilities=[RunnerCapability.AIRGAP_BUNDLE],
            runner_capabilities=[RunnerCapability.DOCKER_SANDBOX]
        )
        self.assertFalse(res.compatible)
        self.assertIn("airgap_bundle", res.unsupported_capabilities)

    def test_drain_and_complete_upgrade(self):
        runner = self._create_runner("r-1", version="3.1.0", jobs=1)
        self.engine.register_runner(runner)

        plan = self.engine.initiate_drain("r-1")
        self.assertIsNotNone(plan)
        self.assertEqual(runner.status, RunnerStatus.DRAINING)

        # Heartbeat finishes active jobs -> status changes to DRAINED
        self.engine.update_heartbeat("r-1", active_jobs=0)
        self.assertEqual(runner.status, RunnerStatus.DRAINED)

        # Complete upgrade
        ok = self.engine.complete_upgrade(plan.plan_id, new_runner_version="3.2.0", new_protocol_version="3.0.0")
        self.assertTrue(ok)
        self.assertEqual(runner.runner_version, "3.2.0")
        self.assertEqual(runner.status, RunnerStatus.ACTIVE)

    def test_fleet_compatibility_summary(self):
        self.engine.register_runner(self._create_runner("r1", version="3.2.0"))
        self.engine.register_runner(self._create_runner("r2", version="3.0.0"))  # too old

        summary = self.engine.get_fleet_compatibility_summary()
        self.assertEqual(summary["total_runners"], 2)
        self.assertEqual(summary["compatible_runners"], 1)
        self.assertEqual(summary["incompatible_runners"], 1)
        self.assertEqual(summary["upgrade_required_count"], 1)
        self.assertEqual(summary["compatibility_rate_pct"], 50.0)

if __name__ == "__main__":
    unittest.main()
