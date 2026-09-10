import unittest
import time
from elmos_mature_platform.types import (
    RegionConfig,
    RegionHealthStatus,
    FailoverMode,
    FailoverTrigger,
    FailoverEvent,
    TrafficShift
)
from elmos_mature_platform.multiregion_failover_engine import MultiregionFailoverEngine

class TestMultiregionFailoverEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MultiregionFailoverEngine(replication_lag_threshold_ms=500.0)
        self.r1 = RegionConfig(
            region_id="us-east-1",
            is_primary=True,
            failover_mode=FailoverMode.ACTIVE_PASSIVE,
            health_status=RegionHealthStatus.HEALTHY,
            traffic_weight=100.0,
            replication_lag_ms=0.0,
            data_residency_zone="US"
        )
        self.r2 = RegionConfig(
            region_id="us-west-2",
            is_primary=False,
            failover_mode=FailoverMode.ACTIVE_PASSIVE,
            health_status=RegionHealthStatus.HEALTHY,
            traffic_weight=0.0,
            replication_lag_ms=100.0,
            data_residency_zone="US"
        )
        self.engine.register_region(self.r1)
        self.engine.register_region(self.r2)

    def test_register_region(self):
        r3 = RegionConfig("eu-west-1", False, FailoverMode.WARM_STANDBY, data_residency_zone="EU")
        self.engine.register_region(r3)
        self.assertEqual(self.engine.get_region_status("eu-west-1").region_id, "eu-west-1")

    def test_get_region_status(self):
        status = self.engine.get_region_status("us-east-1")
        self.assertTrue(status.is_primary)

    def test_get_region_status_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_region_status("invalid")

    def test_update_health(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.DEGRADED, 250.0)
        status = self.engine.get_region_status("us-west-2")
        self.assertEqual(status.health_status, RegionHealthStatus.DEGRADED)
        self.assertEqual(status.replication_lag_ms, 250.0)

    def test_update_health_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.update_health("invalid", RegionHealthStatus.HEALTHY, 0)

    def test_initiate_failover_success(self):
        event = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        self.assertIsInstance(event, FailoverEvent)
        self.assertEqual(event.source_region, "us-east-1")
        
        r1 = self.engine.get_region_status("us-east-1")
        r2 = self.engine.get_region_status("us-west-2")
        self.assertEqual(r1.traffic_weight, 0.0)
        self.assertEqual(r2.traffic_weight, 100.0)

    def test_initiate_failover_invalid_region(self):
        with self.assertRaises(ValueError):
            self.engine.initiate_failover("invalid", "us-west-2", FailoverTrigger.MANUAL)

    def test_initiate_failover_target_unhealthy(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.UNREACHABLE, 0)
        with self.assertRaises(ValueError):
            self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)

    def test_initiate_failover_target_draining(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.DRAINING, 0)
        with self.assertRaises(ValueError):
            self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)

    def test_initiate_failover_data_residency_mismatch(self):
        r3 = RegionConfig("eu-west-1", False, FailoverMode.WARM_STANDBY, data_residency_zone="EU")
        self.engine.register_region(r3)
        with self.assertRaises(ValueError):
            self.engine.initiate_failover("us-east-1", "eu-west-1", FailoverTrigger.MANUAL)

    def test_initiate_failover_automatic_lag_exceeded(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.HEALTHY, 1000.0)
        with self.assertRaises(ValueError):
            self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.AUTOMATIC)

    def test_initiate_failover_manual_lag_exceeded(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.HEALTHY, 1000.0)
        # Should not raise
        self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)

    def test_complete_failover_success(self):
        event = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        time.sleep(0.01) # to simulate time passing for RTO
        completed = self.engine.complete_failover(event.event_id, True, 500)
        
        self.assertTrue(completed.success)
        self.assertTrue(completed.dns_propagation_complete)
        self.assertGreater(completed.rto_seconds, 0)
        self.assertEqual(completed.rpo_data_loss_bytes, 500)
        
        self.assertFalse(self.engine.get_region_status("us-east-1").is_primary)
        self.assertTrue(self.engine.get_region_status("us-west-2").is_primary)

    def test_complete_failover_failure(self):
        event = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        completed = self.engine.complete_failover(event.event_id, False, 0)
        self.assertFalse(completed.success)

    def test_complete_failover_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_failover("invalid", True, 0)

    def test_rollback_failover(self):
        event = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        self.engine.complete_failover(event.event_id, True, 0)
        
        rollback = self.engine.rollback_failover(event.event_id)
        self.assertFalse(rollback.success)
        self.assertFalse(rollback.rollback_available)
        
        self.assertTrue(self.engine.get_region_status("us-east-1").is_primary)
        self.assertFalse(self.engine.get_region_status("us-west-2").is_primary)
        self.assertEqual(self.engine.get_region_status("us-east-1").traffic_weight, 100.0)

    def test_rollback_failover_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.rollback_failover("invalid")

    def test_rollback_failover_unavailable(self):
        event = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        self.engine.complete_failover(event.event_id, True, 0)
        self.engine.rollback_failover(event.event_id)
        
        # Second rollback should fail
        with self.assertRaises(ValueError):
            self.engine.rollback_failover(event.event_id)

    def test_shift_traffic(self):
        shift = self.engine.shift_traffic("us-east-1", "us-west-2", 20.0)
        self.assertTrue(shift.completed)
        self.assertEqual(self.engine.get_region_status("us-east-1").traffic_weight, 80.0)
        self.assertEqual(self.engine.get_region_status("us-west-2").traffic_weight, 20.0)

    def test_shift_traffic_invalid_regions(self):
        with self.assertRaises(ValueError):
            self.engine.shift_traffic("invalid", "us-west-2", 20.0)

    def test_shift_traffic_invalid_percentage_high(self):
        with self.assertRaises(ValueError):
            self.engine.shift_traffic("us-east-1", "us-west-2", 150.0)

    def test_shift_traffic_invalid_percentage_low(self):
        with self.assertRaises(ValueError):
            self.engine.shift_traffic("us-east-1", "us-west-2", -10.0)

    def test_get_active_regions(self):
        active = self.engine.get_active_regions()
        self.assertEqual(len(active), 2)
        
        self.engine.update_health("us-west-2", RegionHealthStatus.UNREACHABLE, 0)
        active = self.engine.get_active_regions()
        self.assertEqual(len(active), 1)

    def test_validate_failover_readiness_ready(self):
        res = self.engine.validate_failover_readiness("us-east-1", "us-west-2")
        self.assertTrue(res["ready"])

    def test_validate_failover_readiness_unhealthy(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.UNREACHABLE, 0)
        res = self.engine.validate_failover_readiness("us-east-1", "us-west-2")
        self.assertFalse(res["ready"])
        self.assertEqual(res["target_health"], RegionHealthStatus.UNREACHABLE)

    def test_validate_failover_readiness_lag(self):
        self.engine.update_health("us-west-2", RegionHealthStatus.HEALTHY, 1000.0)
        res = self.engine.validate_failover_readiness("us-east-1", "us-west-2")
        self.assertFalse(res["ready"])
        self.assertFalse(res["replication_lag_ok"])

    def test_validate_failover_readiness_residency(self):
        r3 = RegionConfig("eu-west-1", False, FailoverMode.WARM_STANDBY, data_residency_zone="EU")
        self.engine.register_region(r3)
        res = self.engine.validate_failover_readiness("us-east-1", "eu-west-1")
        self.assertFalse(res["ready"])
        self.assertFalse(res["data_residency_match"])

    def test_validate_failover_readiness_invalid_regions(self):
        with self.assertRaises(ValueError):
            self.engine.validate_failover_readiness("invalid", "us-west-2")

    def test_run_dr_drill(self):
        event = self.engine.run_dr_drill("us-east-1", "us-west-2")
        self.assertFalse(event.success) # Rollback makes it False
        self.assertFalse(event.rollback_available)
        self.assertEqual(event.trigger, FailoverTrigger.DR_DRILL)
        
        # Verify state is rolled back
        self.assertTrue(self.engine.get_region_status("us-east-1").is_primary)
        self.assertFalse(self.engine.get_region_status("us-west-2").is_primary)

    def test_get_failover_history(self):
        self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        history = self.engine.get_failover_history()
        self.assertEqual(len(history), 2)

    def test_get_rto_rpo_report_empty(self):
        report = self.engine.get_rto_rpo_report()
        self.assertEqual(report["total_events"], 0)
        self.assertEqual(report["average_rto_seconds"], 0.0)

    def test_get_rto_rpo_report(self):
        e1 = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        self.engine.complete_failover(e1.event_id, True, 100)
        
        e2 = self.engine.initiate_failover("us-east-1", "us-west-2", FailoverTrigger.MANUAL)
        self.engine.complete_failover(e2.event_id, True, 200)
        
        report = self.engine.get_rto_rpo_report()
        self.assertEqual(report["total_events"], 2)
        self.assertEqual(report["average_rpo_bytes"], 150.0)
        self.assertGreaterEqual(report["average_rto_seconds"], 0.0)

    def test_normalize_weights_zero(self):
        self.engine.get_region_status("us-east-1").traffic_weight = 0.0
        self.engine.get_region_status("us-west-2").traffic_weight = 0.0
        
        self.engine._normalize_weights()
        
        self.assertEqual(self.engine.get_region_status("us-east-1").traffic_weight, 100.0)
        self.assertEqual(self.engine.get_region_status("us-west-2").traffic_weight, 0.0)

if __name__ == "__main__":
    unittest.main()
