"""Integration tests for cross-cutting orchestration scenarios (U001-U004).

These tests execute the actual scenario functions with real engine instances.
Every assertion is verified by the test harness — not just format-checked.
"""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    RegionId,
    FaultType,
    FaultDescriptor,
    ChaosExperimentConfig,
)
from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.chaos_fault_engine import EnterpriseChaosEngine
from elmos_mature_platform.scenarios.cross_cutting_orchestration import (
    execute_cross_cutting_orchestration,
)


class TestOrchestrationScenarioBase(unittest.TestCase):
    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, skill_code: str, category: str, case_id: str = "test-case-id") -> tuple[list, dict]:
        meta = {"case_id": case_id, "category": category, "skill_code": skill_code}
        assertions, metrics = execute_cross_cutting_orchestration(
            meta, self.sim, self.chaos, self._trace
        )
        return assertions, metrics


class TestOrchestrationU001(TestOrchestrationScenarioBase):
    """U001: tst-b38-45-strict-suite-orchestrator"""
    
    def test_u001_success(self) -> None:
        assertions, metrics = self._run("U001", "success")
        self.assertGreater(len(assertions), 0)
        for a in assertions:
            self.assertTrue(a.passed, f"Assertion '{a.name}' failed: {a.details}")
        self.assertIn("orchestration_duration_ms", metrics)

    def test_u001_boundary(self) -> None:
        assertions, _ = self._run("U001", "boundary")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u001_negative(self) -> None:
        assertions, _ = self._run("U001", "negative")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u001_dependency_failure(self) -> None:
        assertions, _ = self._run("U001", "dependency-failure")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)


class TestOrchestrationU002(TestOrchestrationScenarioBase):
    """U002: tst-b38-45-capability-traceability"""
    
    def test_u002_success(self) -> None:
        assertions, metrics = self._run("U002", "success")
        self.assertGreater(len(assertions), 0)
        for a in assertions:
            self.assertTrue(a.passed)

    def test_u002_boundary(self) -> None:
        assertions, _ = self._run("U002", "boundary")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u002_replay_idempotency(self) -> None:
        # Exercises deterministic hashing
        assertions, _ = self._run("U002", "replay-idempotency")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)
        self.assertIn("Deterministic Traceability Hash", assertions[0].name)

    def test_u002_evidence_tamper(self) -> None:
        assertions, _ = self._run("U002", "evidence-tamper")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)


class TestOrchestrationU003(TestOrchestrationScenarioBase):
    """U003: tst-b38-45-environment-fixture-chaos-factory"""

    def test_u003_success(self) -> None:
        # Exercises real chaos.inject_fault and chaos.revert_fault
        assertions, metrics = self._run("U003", "success")
        self.assertGreater(len(assertions), 0)
        for a in assertions:
            self.assertTrue(a.passed)
        self.assertEqual(len(self.chaos.active_faults), 0)

    def test_u003_boundary(self) -> None:
        assertions, _ = self._run("U003", "boundary")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u003_negative(self) -> None:
        assertions, _ = self._run("U003", "negative")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u003_dependency_failure(self) -> None:
        # Injects CLOCK_SKEW_DRIFT and reverts it
        assertions, _ = self._run("U003", "dependency-failure")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)
        self.assertEqual(len(self.chaos.active_faults), 0)

    def test_u003_security(self) -> None:
        assertions, _ = self._run("U003", "security")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u003_replay_idempotency(self) -> None:
        assertions, _ = self._run("U003", "replay-idempotency")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u003_version_drift(self) -> None:
        assertions, _ = self._run("U003", "version-drift")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_u003_evidence_tamper(self) -> None:
        assertions, _ = self._run("U003", "evidence-tamper")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)


class TestOrchestrationU004(TestOrchestrationScenarioBase):
    """U004: tst-b38-45-evidence-integrity-anti-cheating"""
    
    def test_u004_success(self) -> None:
        assertions, metrics = self._run("U004", "success")
        self.assertGreater(len(assertions), 0)
        for a in assertions:
            self.assertTrue(a.passed)

    def test_u004_boundary(self) -> None:
        assertions, _ = self._run("U004", "boundary")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)
        
    def test_u004_security(self) -> None:
        assertions, _ = self._run("U004", "security")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)
            
    def test_u004_evidence_tamper(self) -> None:
        # Computes SHA-256 hashes to verify tamper detection
        assertions, _ = self._run("U004", "evidence-tamper")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)
        self.assertIn("Log Tamper Detection", assertions[0].name)


class TestDirectChaosEngine(unittest.TestCase):
    """Direct tests for the EnterpriseChaosEngine alongside scenario tests."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)

    def test_direct_fault_injection_and_revert(self) -> None:
        """Inject a fault directly and verify it is tracked and reverted."""
        fault = FaultDescriptor(
            fault_id="direct-latency-test",
            fault_type=FaultType.LATENCY_INJECTION,
            target_region=RegionId.US_EAST_1,
            target_node_ids=["us-node-1"],
            parameters={"latency_ms": 150.0},
        )
        success = self.chaos.inject_fault(fault)
        self.assertTrue(success)
        self.assertIn("direct-latency-test", self.chaos.active_faults)
        
        reverted = self.chaos.revert_fault("direct-latency-test")
        self.assertTrue(reverted)
        self.assertEqual(len(self.chaos.active_faults), 0)

    def test_direct_clock_skew_fault(self) -> None:
        """Inject clock skew directly."""
        fault = FaultDescriptor(
            fault_id="direct-clock-skew",
            fault_type=FaultType.CLOCK_SKEW_DRIFT,
            target_region=RegionId.EU_WEST_1,
            target_node_ids=[],
            parameters={"offset_seconds": 45.0},
        )
        success = self.chaos.inject_fault(fault)
        self.assertTrue(success)
        self.assertIn("direct-clock-skew", self.chaos.active_faults)
        
        self.chaos.revert_fault("direct-clock-skew")
        self.assertEqual(len(self.chaos.active_faults), 0)

    def test_direct_experiment_runner(self) -> None:
        """Test the run_chaos_experiment method."""
        fault = FaultDescriptor(
            fault_id="exp-fault-1",
            fault_type=FaultType.NETWORK_PARTITION,
            target_region=RegionId.AP_SOUTHEAST_1,
            target_node_ids=["ap-node-1"],
        )
        config = ChaosExperimentConfig(
            experiment_id="direct-exp-1",
            title="Direct Test Exp",
            target_faults=[fault],
            max_duration_seconds=2.0,
            allowed_error_rate_threshold=0.1,
        )
        
        result = self.chaos.run_chaos_experiment(config)
        self.assertEqual(result.faults_executed, 1)
        self.assertEqual(result.faults_reverted, 1)
        self.assertEqual(len(self.chaos.active_faults), 0)


if __name__ == "__main__":
    unittest.main()
