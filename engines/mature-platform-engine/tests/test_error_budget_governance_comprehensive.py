import unittest
from datetime import datetime, timedelta
import time
from typing import List

from elmos_mature_platform.error_budget_governance_engine import ErrorBudgetGovernanceEngine
from elmos_mature_platform.types import (
    ErrorBudgetSlo,
    BurnRateWindow,
    ReleaseFreezeAction,
    ErrorBudgetWaiver
)

class TestErrorBudgetGovernanceEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ErrorBudgetGovernanceEngine()
        
    def _create_slo(self, slo_id: str, service: str, target: float = 99.9) -> ErrorBudgetSlo:
        return ErrorBudgetSlo(
            slo_id=slo_id,
            service_name=service,
            indicator="availability",
            target=target
        )
        
    def _future_date(self, days=1):
        return (datetime.utcnow() + timedelta(days=days)).isoformat()
        
    def _past_date(self, days=1):
        return (datetime.utcnow() - timedelta(days=days)).isoformat()

    def test_register_slo(self):
        slo = self._create_slo("slo-1", "svc-1")
        self.engine.register_slo(slo)
        self.assertEqual(self.engine.get_remaining_budget("slo-1"), 100.0)
        
    def test_record_error_event(self):
        slo = self._create_slo("slo-1", "svc-1", 99.0) # 1% error budget
        self.engine.register_slo(slo)
        
        # 1000 requests, 5 errors -> 0.5% error rate -> consumes 50% of budget
        self.engine.record_error_event("slo-1", 5, 1000)
        self.assertAlmostEqual(self.engine.get_remaining_budget("slo-1"), 50.0)
        
    def test_record_error_event_budget_exhausted(self):
        slo = self._create_slo("slo-1", "svc-1", 99.0)
        self.engine.register_slo(slo)
        
        # 1000 requests, 15 errors -> 1.5% error rate -> consumes 150% of budget -> caps at 100% consumed, 0% remaining
        self.engine.record_error_event("slo-1", 15, 1000)
        self.assertEqual(self.engine.get_remaining_budget("slo-1"), 0.0)
        
    def test_record_error_event_invalid_slo(self):
        with self.assertRaises(ValueError):
            self.engine.record_error_event("invalid", 1, 100)
            
    def test_record_error_event_invalid_counts(self):
        slo = self._create_slo("slo-1", "svc-1")
        self.engine.register_slo(slo)
        with self.assertRaises(ValueError):
            self.engine.record_error_event("slo-1", 10, 5)
            
    def test_compute_burn_rate_normal(self):
        slo = self._create_slo("slo-1", "svc-1", 99.9) # 0.1% error budget
        self.engine.register_slo(slo)
        
        # 10,000 reqs, 1 error -> 0.01% error rate -> 0.1 burn rate
        self.engine.record_error_event("slo-1", 1, 10000)
        alert = self.engine.compute_burn_rate("slo-1", BurnRateWindow.ONE_HOUR)
        self.assertAlmostEqual(alert.burn_rate, 0.1, places=5)
        self.assertEqual(alert.alert_severity, "log")
        
    def test_compute_burn_rate_high(self):
        slo = self._create_slo("slo-1", "svc-1", 99.9) # 0.1% budget
        self.engine.register_slo(slo)
        
        # 10,000 reqs, 10 errors -> 0.1% error rate -> 1.0 burn rate
        self.engine.record_error_event("slo-1", 10, 10000)
        alert = self.engine.compute_burn_rate("slo-1", BurnRateWindow.ONE_HOUR)
        self.assertAlmostEqual(alert.burn_rate, 1.0, places=5)
        
    def test_compute_burn_rate_page(self):
        slo = self._create_slo("slo-1", "svc-1", 99.9) # 0.1% budget
        self.engine.register_slo(slo)
        
        # 10,000 reqs, 150 errors -> 1.5% error rate -> 15.0 burn rate
        self.engine.record_error_event("slo-1", 150, 10000)
        alert = self.engine.compute_burn_rate("slo-1", BurnRateWindow.ONE_HOUR)
        self.assertTrue(alert.burn_rate > 14.4)
        self.assertEqual(alert.alert_severity, "page")
        
    def test_compute_burn_rate_ticket(self):
        slo = self._create_slo("slo-1", "svc-1", 99.9) # 0.1% budget
        self.engine.register_slo(slo)
        
        # 10,000 reqs, 70 errors -> 0.7% error rate -> 7.0 burn rate
        self.engine.record_error_event("slo-1", 70, 10000)
        alert = self.engine.compute_burn_rate("slo-1", BurnRateWindow.ONE_HOUR)
        self.assertTrue(6.0 < alert.burn_rate <= 14.4)
        self.assertEqual(alert.alert_severity, "ticket")
        
    def test_get_remaining_budget(self):
        slo = self._create_slo("slo-1", "svc-1")
        self.engine.register_slo(slo)
        self.engine.record_error_event("slo-1", 0, 1000)
        self.assertEqual(self.engine.get_remaining_budget("slo-1"), 100.0)
        
    def test_evaluate_release_gate_allow(self):
        slo = self._create_slo("slo-1", "svc-1")
        self.engine.register_slo(slo)
        decision = self.engine.evaluate_release_gate("svc-1")
        self.assertEqual(decision.action, ReleaseFreezeAction.ALLOW)
        
    def test_evaluate_release_gate_warn(self):
        slo = self._create_slo("slo-1", "svc-1", 99.0)
        self.engine.register_slo(slo)
        # Consume 80% of budget, 20% remaining
        self.engine.record_error_event("slo-1", 8, 1000)
        decision = self.engine.evaluate_release_gate("svc-1")
        self.assertEqual(decision.action, ReleaseFreezeAction.WARN)
        
    def test_evaluate_release_gate_freeze(self):
        slo = self._create_slo("slo-1", "svc-1", 99.0)
        self.engine.register_slo(slo)
        # Consume 95% of budget, 5% remaining (< 10%)
        self.engine.record_error_event("slo-1", 95, 10000)
        decision = self.engine.evaluate_release_gate("svc-1")
        self.assertEqual(decision.action, ReleaseFreezeAction.FREEZE)
        
    def test_evaluate_release_gate_no_slos(self):
        decision = self.engine.evaluate_release_gate("unknown-svc")
        self.assertEqual(decision.action, ReleaseFreezeAction.ALLOW)
        
    def test_grant_waiver(self):
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Emergency fix", "admin", self._future_date())
        self.engine.grant_waiver(waiver)
        self.assertEqual(len(self.engine._waivers), 1)
        
    def test_grant_expired_waiver(self):
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Emergency fix", "admin", self._past_date())
        with self.assertRaises(ValueError):
            self.engine.grant_waiver(waiver)
            
    def test_use_waiver_success(self):
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Emergency fix", "admin", self._future_date(), max_deploys=2)
        self.engine.grant_waiver(waiver)
        self.assertTrue(self.engine.use_waiver("svc-1"))
        self.assertEqual(self.engine._waivers["w-1"].deploys_used, 1)
        
    def test_use_waiver_exhausted(self):
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Emergency fix", "admin", self._future_date(), max_deploys=1)
        self.engine.grant_waiver(waiver)
        self.assertTrue(self.engine.use_waiver("svc-1"))
        self.assertFalse(self.engine.use_waiver("svc-1"))
        
    def test_use_waiver_expired_during_use(self):
        # Difficult to test strictly with time, but test logic
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Emergency fix", "admin", self._future_date())
        self.engine.grant_waiver(waiver)
        waiver.expires_at = self._past_date() # simulate expire
        self.assertFalse(self.engine.use_waiver("svc-1"))
        
    def test_use_waiver_wrong_service(self):
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Emergency fix", "admin", self._future_date())
        self.engine.grant_waiver(waiver)
        self.assertFalse(self.engine.use_waiver("svc-2"))
        
    def test_release_gate_with_waiver(self):
        slo = self._create_slo("slo-1", "svc-1", 99.0)
        self.engine.register_slo(slo)
        self.engine.record_error_event("slo-1", 15, 1000) # Exhausts budget
        
        decision = self.engine.evaluate_release_gate("svc-1")
        self.assertEqual(decision.action, ReleaseFreezeAction.FREEZE)
        
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "Fix", "admin", self._future_date())
        self.engine.grant_waiver(waiver)
        
        decision_override = self.engine.evaluate_release_gate("svc-1")
        self.assertEqual(decision_override.action, ReleaseFreezeAction.ALLOW)
        self.assertTrue(decision_override.override_allowed)
        self.assertEqual(decision_override.waiver_id, "w-1")
        
    def test_get_multi_window_burn_rates(self):
        slo = self._create_slo("slo-1", "svc-1")
        self.engine.register_slo(slo)
        self.engine.record_error_event("slo-1", 1, 1000)
        
        rates = self.engine.get_multi_window_burn_rates("slo-1")
        self.assertEqual(len(rates), len(BurnRateWindow))
        windows = [r.window for r in rates]
        self.assertIn(BurnRateWindow.ONE_HOUR, windows)
        self.assertIn(BurnRateWindow.THIRTY_DAYS, windows)
        
    def test_get_budget_forecast(self):
        slo = self._create_slo("slo-1", "svc-1", 99.0)
        self.engine.register_slo(slo)
        self.engine.record_error_event("slo-1", 5, 1000) # 50% budget gone, burn rate > 0
        
        forecast = self.engine.get_budget_forecast("slo-1", 7)
        self.assertEqual(forecast["slo_id"], "slo-1")
        self.assertAlmostEqual(forecast["current_remaining_pct"], 50.0)
        self.assertGreater(forecast["1d_burn_rate"], 0)
        self.assertGreater(forecast["projected_exhaustion_hours"], 0)
        
    def test_get_governance_report(self):
        slo1 = self._create_slo("slo-1", "svc-1", 99.0)
        slo2 = self._create_slo("slo-2", "svc-2", 99.0)
        self.engine.register_slo(slo1)
        self.engine.register_slo(slo2)
        
        self.engine.record_error_event("slo-1", 10, 1000) # Exhausts
        
        waiver = ErrorBudgetWaiver("w-1", "svc-1", "fix", "admin", self._future_date())
        self.engine.grant_waiver(waiver)
        
        report = self.engine.get_governance_report()
        self.assertEqual(set(report["services_tracked"]), {"svc-1", "svc-2"})
        self.assertEqual(report["frozen_services"], []) # waiver exists for svc-1
        self.assertIn("w-1", report["active_waivers"])
        
    def test_governance_report_frozen(self):
        slo1 = self._create_slo("slo-1", "svc-1", 99.0)
        self.engine.register_slo(slo1)
        self.engine.record_error_event("slo-1", 10, 1000) # Exhausts
        
        report = self.engine.get_governance_report()
        self.assertEqual(report["frozen_services"], ["svc-1"])

    def test_forecast_no_burn(self):
        slo = self._create_slo("slo-1", "svc-1")
        self.engine.register_slo(slo)
        self.engine.record_error_event("slo-1", 0, 1000)
        
        forecast = self.engine.get_budget_forecast("slo-1", 7)
        self.assertEqual(forecast["projected_exhaustion_hours"], 0.0)
        self.assertFalse(forecast["exhausts_within_forecast"])
        
    def test_burn_rate_zero_target(self):
        slo = self._create_slo("slo-1", "svc-1", 100.0)
        self.engine.register_slo(slo)
        
        alert = self.engine.compute_burn_rate("slo-1", BurnRateWindow.ONE_HOUR)
        self.assertEqual(alert.burn_rate, 0.0)

    def test_invalid_slo_forecast(self):
        with self.assertRaises(ValueError):
            self.engine.get_budget_forecast("unknown", 7)
            
    def test_invalid_slo_burn_rates(self):
        with self.assertRaises(ValueError):
            self.engine.get_multi_window_burn_rates("unknown")

if __name__ == "__main__":
    unittest.main()
