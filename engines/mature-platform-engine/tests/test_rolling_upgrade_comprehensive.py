import unittest
from elmos_mature_platform.rolling_upgrade_orchestrator import RollingUpgradeOrchestrator
from elmos_mature_platform.types import (
    CanaryDecision,
    CanaryObservation,
    CanaryWaveSpec,
)


class TestRollingUpgradeComprehensive(unittest.TestCase):
    def setUp(self):
        self.orchestrator = RollingUpgradeOrchestrator()
        self.waves = [
            CanaryWaveSpec(wave_number=1, traffic_percentage=5.0),
            CanaryWaveSpec(wave_number=2, traffic_percentage=25.0),
            CanaryWaveSpec(wave_number=3, traffic_percentage=100.0),
        ]

    def test_create_valid_upgrade_plan(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.assertEqual(len(plan.waves), 3)
        self.assertEqual(plan.source_version, "v1")
        self.assertEqual(plan.target_version, "v2")
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertEqual(status["phase"], "CREATED")

    def test_initiate_upgrade(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        msg = self.orchestrator.initiate_upgrade(plan.plan_id)
        self.assertEqual(msg, "Upgrade initiated successfully.")
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertEqual(status["phase"], "IN_PROGRESS")
        self.assertEqual(status["active_instances"]["target"], 1)

    def test_wave_1_passes_slo_gate(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        obs = CanaryObservation(
            wave_number=1,
            total_requests=1000,
            error_requests=0,
            p95_latency_ms=20.0,
            p99_latency_ms=50.0,
            error_rate=0.0
        )
        decision = self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)
        self.assertEqual(decision, CanaryDecision.PROCEED)
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertIn(1, status["completed_waves"])
        self.assertNotIn(1, status["pending_waves"])

    def test_wave_high_error_rate_triggers_rollback(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        obs = CanaryObservation(
            wave_number=1,
            total_requests=1000,
            error_requests=10,
            p95_latency_ms=20.0,
            p99_latency_ms=50.0,
            error_rate=0.01  # 1% > 0.1% max
        )
        decision = self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)
        self.assertEqual(decision, CanaryDecision.ROLLBACK)
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertEqual(status["phase"], "ROLLED_BACK")

    def test_wave_high_latency_triggers_rollback(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        obs = CanaryObservation(
            wave_number=1,
            total_requests=1000,
            error_requests=0,
            p95_latency_ms=20.0,
            p99_latency_ms=150.0,  # > 100 max
            error_rate=0.0
        )
        decision = self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)
        self.assertEqual(decision, CanaryDecision.ROLLBACK)
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertEqual(status["phase"], "ROLLED_BACK")

    def test_auto_rollback_disabled_holds(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        plan.auto_rollback_on_breach = False
        self.orchestrator.initiate_upgrade(plan.plan_id)
        obs = CanaryObservation(
            wave_number=1,
            total_requests=1000,
            error_requests=10,
            p95_latency_ms=20.0,
            p99_latency_ms=50.0,
            error_rate=0.01
        )
        decision = self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)
        self.assertEqual(decision, CanaryDecision.HOLD)
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertEqual(status["phase"], "IN_PROGRESS")

    def test_instance_draining_succeeds(self):
        results = self.orchestrator.drain_instances(["i-123", "i-456"], timeout_s=10.0)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertTrue(r.drained_successfully)
            self.assertEqual(r.inflight_requests, 0)

    def test_instance_draining_timeout(self):
        results = self.orchestrator.drain_instances(["i-123"], timeout_s=2.0)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].drained_successfully)
        self.assertEqual(results[0].inflight_requests, 5)

    def test_complete_upgrade_after_all_waves(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        
        for w in self.waves:
            obs = CanaryObservation(
                wave_number=w.wave_number, total_requests=100, error_requests=0, p95_latency_ms=10, p99_latency_ms=20, error_rate=0
            )
            self.orchestrator.execute_canary_wave(plan.plan_id, w, obs)
            
        status = self.orchestrator.complete_upgrade(plan.plan_id)
        self.assertEqual(status["phase"], "COMPLETED")
        self.assertEqual(status["active_instances"]["target"], 100)
        self.assertEqual(status["active_instances"]["source"], 0)

    def test_cannot_complete_with_pending_waves(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        with self.assertRaises(RuntimeError):
            self.orchestrator.complete_upgrade(plan.plan_id)

    def test_rollback_restores_source_version(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        record = self.orchestrator.trigger_rollback(plan.plan_id, "manual")
        self.assertEqual(record.restored_version, "v1")
        status = self.orchestrator.get_upgrade_status(plan.plan_id)
        self.assertEqual(status["active_instances"]["source"], 100)
        self.assertEqual(status["active_instances"]["target"], 0)

    def test_expand_contract_schema_add_col_ok(self):
        res = self.orchestrator.validate_expand_contract_schema(["a"], ["a", "b"], [])
        self.assertTrue(res["valid"])

    def test_expand_contract_schema_premature_remove_rejected(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        # Source instances still active
        with self.assertRaises(ValueError):
            self.orchestrator.validate_expand_contract_schema(["a", "b"], ["a"], ["b"])

    def test_upgrade_history_tracking(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        self.orchestrator.trigger_rollback(plan.plan_id, "test")
        history = self.orchestrator.list_upgrade_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "ROLLED_BACK")

    def test_multiple_concurrent_upgrades_rejected(self):
        plan1 = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan1.plan_id)
        with self.assertRaises(RuntimeError):
            self.orchestrator.create_upgrade_plan("v2", "v3", self.waves)

    def test_invalid_plan_no_waves_rejected(self):
        with self.assertRaises(ValueError):
            self.orchestrator.create_upgrade_plan("v1", "v2", [])

    def test_invalid_plan_bad_traffic_rejected(self):
        bad_waves = [
            CanaryWaveSpec(wave_number=1, traffic_percentage=105.0)
        ]
        with self.assertRaises(ValueError):
            self.orchestrator.create_upgrade_plan("v1", "v2", bad_waves)

    def test_evaluate_wave_gate_direct(self):
        obs = CanaryObservation(1, 100, 0, 10, 20, 0)
        decision = self.orchestrator.evaluate_wave_gate(obs, self.waves[0])
        self.assertEqual(decision, CanaryDecision.PROCEED)

    def test_plan_not_found(self):
        with self.assertRaises(ValueError):
            self.orchestrator.initiate_upgrade("invalid")

    def test_execute_wave_wrong_phase(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        obs = CanaryObservation(1, 100, 0, 10, 20, 0)
        with self.assertRaises(RuntimeError):
            self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)

    def test_execute_non_pending_wave(self):
        plan = self.orchestrator.create_upgrade_plan("v1", "v2", self.waves)
        self.orchestrator.initiate_upgrade(plan.plan_id)
        obs = CanaryObservation(1, 100, 0, 10, 20, 0)
        self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)
        with self.assertRaises(ValueError):
            # execute same wave again
            self.orchestrator.execute_canary_wave(plan.plan_id, self.waves[0], obs)

    def test_final_wave_not_100_rejected(self):
        bad_waves = [
            CanaryWaveSpec(wave_number=1, traffic_percentage=50.0)
        ]
        with self.assertRaises(ValueError):
            self.orchestrator.create_upgrade_plan("v1", "v2", bad_waves)

    def test_traffic_not_strictly_increasing(self):
        bad_waves = [
            CanaryWaveSpec(wave_number=1, traffic_percentage=50.0),
            CanaryWaveSpec(wave_number=2, traffic_percentage=50.0),
            CanaryWaveSpec(wave_number=3, traffic_percentage=100.0)
        ]
        with self.assertRaises(ValueError):
            self.orchestrator.create_upgrade_plan("v1", "v2", bad_waves)

    def test_drain_instances_all_succeed(self):
        results = self.orchestrator.drain_instances(["1", "2", "3", "4", "5"], 15.0)
        self.assertTrue(all(r.drained_successfully for r in results))

    def test_get_upgrade_status_not_found(self):
        with self.assertRaises(ValueError):
            self.orchestrator.get_upgrade_status("fake")

    def test_trigger_rollback_not_found(self):
        with self.assertRaises(ValueError):
            self.orchestrator.trigger_rollback("fake", "reason")

    def test_complete_upgrade_not_found(self):
        with self.assertRaises(ValueError):
            self.orchestrator.complete_upgrade("fake")

    def test_validate_expand_contract_schema_no_active_plan(self):
        # Should be fine if no plan is active
        res = self.orchestrator.validate_expand_contract_schema(["a"], [], ["a"])
        self.assertTrue(res["valid"])

    def test_execute_wave_not_found_plan(self):
        obs = CanaryObservation(1, 100, 0, 10, 20, 0)
        with self.assertRaises(ValueError):
            self.orchestrator.execute_canary_wave("fake", self.waves[0], obs)

if __name__ == "__main__":
    unittest.main()
