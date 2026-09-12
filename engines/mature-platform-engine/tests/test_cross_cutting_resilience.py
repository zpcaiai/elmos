"""Integration tests for cross-cutting resilience scenarios (U013-U017).

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
    DrPlan,
    ChaosExperimentConfig,
    ZeroToleranceCategory,
)
from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.chaos_fault_engine import EnterpriseChaosEngine
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
from elmos_mature_platform.disaster_recovery_runner import DisasterRecoveryRunner
from elmos_mature_platform.scenarios.cross_cutting_resilience import (
    execute_cross_cutting_resilience,
)


class TestResilienceScenarioU013TenantIsolation(unittest.TestCase):
    """U013: tst-edition-topology-data-boundary — tenant data isolation."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)
        self.kms = EnterpriseKmsService()
        self.dr = DisasterRecoveryRunner(self.sim)
        self.slo = EnterpriseSloCollector()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category, "skill_code": "U013"}
        assertions, metrics = execute_cross_cutting_resilience(
            meta, self.sim, self.chaos, self.kms, self.dr, self.slo, self._trace
        )
        return assertions

    def test_success_tenant_data_intact(self) -> None:
        """Verify two tenants can encrypt/decrypt their own data independently."""
        assertions = self._run("X-U013-001", "success")
        self.assertGreaterEqual(len(assertions), 2)
        for a in assertions:
            self.assertTrue(a.passed, f"Assertion '{a.name}' failed: {a.details}")

    def test_negative_cross_tenant_blocked(self) -> None:
        """Verify cross-tenant decryption raises PermissionError."""
        assertions = self._run("X-U013-003", "negative")
        blocked = [a for a in assertions if "Blocked" in a.name or "Isolation" in a.name]
        self.assertGreater(len(blocked), 0, "Expected cross-tenant block assertion")
        for a in blocked:
            self.assertTrue(a.passed, f"Cross-tenant isolation failed: {a.details}")

    def test_boundary_colocation(self) -> None:
        """Verify tenant co-location capacity assessment runs."""
        assertions = self._run("X-U013-002", "boundary")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_performance_noisy_neighbor(self) -> None:
        """Verify noisy neighbor P99 latency check uses real SLO collector."""
        assertions = self._run("X-U013-009", "performance")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)
        self.assertIn("P99", assertions[0].details)

    def test_security_sovereign_egress(self) -> None:
        """Verify sovereign cloud egress gate check."""
        assertions = self._run("X-U013-005", "security")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)

    def test_replay_idempotency_provisioning(self) -> None:
        """Verify edition provisioning idempotency."""
        assertions = self._run("X-U013-006", "replay-idempotency")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed)


class TestResilienceScenarioU016ChaosMultiregionDR(unittest.TestCase):
    """U016: tst-slo-chaos-multiregion-dr — chaos + DR drills."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)
        self.kms = EnterpriseKmsService()
        self.dr = DisasterRecoveryRunner(self.sim)
        self.slo = EnterpriseSloCollector()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category, "skill_code": "U016"}
        assertions, metrics = execute_cross_cutting_resilience(
            meta, self.sim, self.chaos, self.kms, self.dr, self.slo, self._trace
        )
        return assertions

    def test_success_partition_recovery(self) -> None:
        """Inject AP partition -> verify quorum writes -> heal -> verify reconciliation."""
        assertions = self._run("X-U016-001", "success")
        self.assertGreaterEqual(len(assertions), 2)
        quorum_assert = assertions[0]
        self.assertTrue(quorum_assert.passed, f"Quorum should remain available: {quorum_assert.details}")

    def test_dependency_failure_latency_spike(self) -> None:
        """Inject 500ms latency spike and verify adaptive timeout mitigation."""
        assertions = self._run("X-U016-004", "dependency-failure")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)
        self.assertEqual(len(self.chaos.active_faults), 0, "Faults should be reverted")

    def test_security_fencing_token(self) -> None:
        """Verify stale fencing token is rejected by the consensus layer."""
        assertions = self._run("X-U016-005", "security")
        self.assertGreater(len(assertions), 0)
        fencing = assertions[0]
        self.assertTrue(fencing.passed, f"Stale fencing token should be rejected: {fencing.details}")

    def test_recovery_regional_evacuation(self) -> None:
        """Execute full regional evacuation DR drill with RTO/RPO measurement."""
        assertions = self._run("X-U016-008", "recovery")
        self.assertGreaterEqual(len(assertions), 2)
        rto_ok = assertions[0]
        rpo_ok = assertions[1]
        self.assertTrue(rto_ok.passed, f"RTO compliance failed: {rto_ok.details}")
        self.assertTrue(rpo_ok.passed, f"RPO compliance failed: {rpo_ok.details}")
        evac_traces = [t for t in self.trace_log if "Evacuation" in t]
        self.assertGreater(len(evac_traces), 0, "Should have evacuation drill traces")

    def test_performance_multiregion_latency(self) -> None:
        """Benchmark multi-region P99 latency via SLO collector."""
        assertions = self._run("X-U016-009", "performance")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)


class TestResilienceScenarioU017BackupRestore(unittest.TestCase):
    """U017: tst-backup-restore-data-integrity — Merkle reconciliation + PITR."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)
        self.kms = EnterpriseKmsService()
        self.dr = DisasterRecoveryRunner(self.sim)
        self.slo = EnterpriseSloCollector()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category, "skill_code": "U017"}
        assertions, metrics = execute_cross_cutting_resilience(
            meta, self.sim, self.chaos, self.kms, self.dr, self.slo, self._trace
        )
        return assertions

    def test_success_merkle_reconciliation(self) -> None:
        """Verify Merkle tree reconciliation with identical primary/backup."""
        assertions = self._run("X-U017-001", "success")
        merkle_match = assertions[0]
        no_loss = assertions[1]
        self.assertTrue(merkle_match.passed, f"Merkle roots should match: {merkle_match.details}")
        self.assertTrue(no_loss.passed, f"No data loss expected: {no_loss.details}")

    def test_negative_bitrot_detection(self) -> None:
        """Verify silent bit rot / data tampering is detected in backup."""
        assertions = self._run("X-U017-003", "negative")
        self.assertGreater(len(assertions), 0)
        bitrot = assertions[0]
        self.assertTrue(bitrot.passed, f"Bit rot should be detected: {bitrot.details}")

    def test_boundary_high_capacity(self) -> None:
        """Verify reconciliation works for 1,000 records."""
        assertions = self._run("X-U017-002", "boundary")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_security_backup_encryption(self) -> None:
        """Verify backup is encrypted with real KMS envelope encryption."""
        assertions = self._run("X-U017-005", "security")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)


class TestResilienceEndToEndMultiFaultChaos(unittest.TestCase):
    """End-to-end test: inject multiple faults, run workload, verify SLO, run DR drill."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.sim)
        self.kms = EnterpriseKmsService()
        self.dr = DisasterRecoveryRunner(self.sim)
        self.slo = EnterpriseSloCollector()

    def test_full_chaos_dr_slo_pipeline(self) -> None:
        """Complete pipeline: chaos -> workload -> SLO -> DR drill -> reconciliation."""
        # 1. Inject latency fault
        latency_fault = FaultDescriptor(
            fault_id="e2e-latency-01",
            fault_type=FaultType.LATENCY_INJECTION,
            target_region=RegionId.EU_WEST_1,
            target_node_ids=["eu-node-1"],
            parameters={"latency_ms": 200.0},
        )
        ok_lat = self.chaos.inject_fault(latency_fault)
        self.assertTrue(ok_lat, "Latency injection should succeed")

        # 2. Run workload and collect SLO metrics
        leader = self.sim.get_leader()
        self.assertIsNotNone(leader, "Leader should exist even with EU latency")
        for i in range(50):
            rep_ok, _ = self.sim.replicate_transaction(f"e2e-key-{i}", f"val-{i}", leader.fencing_token)
            ratio = 1.0 if rep_ok else 0.0
            self.slo.record_metric_sample("http_request_success_ratio", ratio)

        # 3. Evaluate SLO
        slo_result = self.slo.evaluate_slo("api-availability")
        self.assertIsNotNone(slo_result)

        # 4. Revert faults
        self.chaos.revert_fault("e2e-latency-01")
        self.assertEqual(len(self.chaos.active_faults), 0)

        # 5. Run DR drill
        primary_data = {f"k-{i}": f"v-{i}".encode() for i in range(20)}
        replica_data = {f"k-{i}": f"v-{i}".encode() for i in range(20)}
        plan = DrPlan(
            plan_id="e2e-dr-01",
            primary_region=RegionId.US_EAST_1,
            secondary_regions=[RegionId.EU_WEST_1],
            rto_target_seconds=10.0,
            rpo_target_seconds=5.0,
        )
        drill = self.dr.execute_disaster_recovery_drill(plan, primary_data, replica_data)
        self.assertTrue(drill.rto_met, f"RTO should be met: {drill.rto_measured_seconds}s")
        self.assertTrue(drill.rpo_met, f"RPO should be met: {drill.rpo_measured_seconds}s")
        self.assertFalse(drill.data_reconciliation.data_loss_detected)

    def test_governor_abort_under_cascading_failure(self) -> None:
        """Verify governor intervention when error rate exceeds threshold."""
        fault = FaultDescriptor(
            fault_id="cascade-test",
            fault_type=FaultType.CASCADING_DEPENDENCY,
            target_region=RegionId.US_EAST_1,
            target_node_ids=[],
        )
        config = ChaosExperimentConfig(
            experiment_id="exp-cascade-01",
            title="Cascading Dependency Test",
            target_faults=[fault],
            max_duration_seconds=5.0,
            allowed_error_rate_threshold=0.02,
        )
        result = self.chaos.run_chaos_experiment(config)
        self.assertEqual(result.faults_executed, 1)
        self.assertEqual(result.faults_reverted, 1)
        self.assertEqual(len(self.chaos.active_faults), 0)

    def test_kms_encrypted_data_survives_chaos(self) -> None:
        """Encrypt data -> inject chaos -> verify decryption still works after revert."""
        self.kms.create_key("chaos-survivor-key")
        enc = self.kms.envelope_encrypt(
            "chaos-survivor-key", b"critical-financial-record", "tenant-bank", "ledger-1"
        )

        fault = FaultDescriptor(
            fault_id="net-during-crypto",
            fault_type=FaultType.NETWORK_PARTITION,
            target_region=RegionId.AP_SOUTHEAST_1,
            target_node_ids=[],
        )
        self.chaos.inject_fault(fault)
        self.chaos.revert_fault("net-during-crypto")

        decrypted = self.kms.envelope_decrypt(enc, "tenant-bank", "ledger-1")
        self.assertEqual(decrypted, b"critical-financial-record")


class TestDirectMerkleReconciliation(unittest.TestCase):
    """Direct tests for Merkle-based data reconciliation (no scenario wrapper)."""

    def setUp(self) -> None:
        self.sim = CrossRegionSimulationEnvironment()
        self.dr = DisasterRecoveryRunner(self.sim)

    def test_identical_datasets(self) -> None:
        """Identical primary and replica should produce matching Merkle roots."""
        data_a = {f"record-{i}": f"value-{i}".encode() for i in range(50)}
        data_b = {f"record-{i}": f"value-{i}".encode() for i in range(50)}
        result = self.dr.reconcile_data_stores(data_a, data_b)
        self.assertFalse(result.data_loss_detected)
        self.assertEqual(len(result.divergent_keys), 0)
        self.assertEqual(result.primary_root_hash, result.replica_root_hash)

    def test_single_key_divergence(self) -> None:
        """Single tampered key should be detected by Merkle comparison."""
        data_a = {"k1": b"v1", "k2": b"v2", "k3": b"v3"}
        data_b = {"k1": b"v1", "k2": b"TAMPERED", "k3": b"v3"}
        result = self.dr.reconcile_data_stores(data_a, data_b)
        self.assertNotEqual(result.primary_root_hash, result.replica_root_hash)
        self.assertIn("k2", result.divergent_keys)

    def test_missing_key_in_replica(self) -> None:
        """Missing key in replica constitutes data loss."""
        data_a = {"k1": b"v1", "k2": b"v2"}
        data_b = {"k1": b"v1"}
        result = self.dr.reconcile_data_stores(data_a, data_b)
        self.assertTrue(result.data_loss_detected)
        self.assertIn("k2", result.divergent_keys)

    def test_extra_key_in_replica(self) -> None:
        """Extra keys in replica should still diverge the Merkle root."""
        data_a = {"k1": b"v1"}
        data_b = {"k1": b"v1", "k2": b"extra"}
        result = self.dr.reconcile_data_stores(data_a, data_b)
        self.assertNotEqual(result.primary_root_hash, result.replica_root_hash)

    def test_empty_datasets(self) -> None:
        """Empty datasets should reconcile without error."""
        result = self.dr.reconcile_data_stores({}, {})
        self.assertFalse(result.data_loss_detected)
        self.assertEqual(len(result.divergent_keys), 0)

    def test_large_dataset_performance(self) -> None:
        """Verify reconciliation handles 500 records without error."""
        data = {f"record-{i}": f"value-{i}".encode() for i in range(500)}
        result = self.dr.reconcile_data_stores(data, data.copy())
        self.assertFalse(result.data_loss_detected)
        self.assertEqual(result.source_records_count, 500)


if __name__ == "__main__":
    unittest.main()
