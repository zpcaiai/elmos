import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.types import (
    ResourceType, BudgetPeriod, BudgetAction,
    AgentBudget, ResourceConsumption, BudgetDecision
)
from elmos_mature_platform.agent_budget_limits_engine import AgentBudgetLimitsEngine

class TestAgentBudgetLimitsComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = AgentBudgetLimitsEngine()
        
    def test_create_budget_initializes_remaining(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.assertEqual(b.remaining, 1000.0)
        self.assertEqual(b.used, 0.0)

    def test_request_resource_allow(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 500, "t1")
        self.assertEqual(dec.action, BudgetAction.ALLOW)

    def test_request_resource_deny_hard_limit(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, hard_limit=True)
        self.engine.create_budget(b)
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 1500, "t1")
        self.assertEqual(dec.action, BudgetAction.DENY)

    def test_request_resource_throttle(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 910))
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 10, "t1")
        self.assertEqual(dec.action, BudgetAction.THROTTLE)

    def test_request_resource_alert_warning_threshold(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, warning_threshold_pct=80)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 800))
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 10, "t1")
        self.assertEqual(dec.action, BudgetAction.ALERT)

    def test_request_resource_no_budget_raises(self):
        with self.assertRaises(ValueError):
            self.engine.request_resource("a1", ResourceType.TOKENS, 100, "t1")

    def test_consume_resource_deducts_correctly(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 300))
        self.assertEqual(b.used, 300)
        self.assertEqual(b.remaining, 700)

    def test_consume_resource_no_budget_raises(self):
        with self.assertRaises(ValueError):
            self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 300))

    def test_get_budget(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        fetched = self.engine.get_budget("a1", ResourceType.TOKENS)
        self.assertEqual(fetched.budget_id, "b1")

    def test_get_budget_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_budget("a1", ResourceType.TOKENS)

    def test_get_all_budgets(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        self.engine.create_budget(AgentBudget("b2", "a1", ResourceType.API_CALLS, BudgetPeriod.DAILY, 500))
        self.engine.create_budget(AgentBudget("b3", "a2", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        budgets = self.engine.get_all_budgets("a1")
        self.assertEqual(len(budgets), 2)

    def test_reset_budget(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 300))
        self.engine.reset_budget("b1")
        self.assertEqual(b.used, 0.0)
        self.assertEqual(b.remaining, 1000.0)

    def test_reset_budget_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.reset_budget("nonexistent")

    def test_reset_expired_budgets(self):
        b1 = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, reset_at="2024-01-01T10:00:00Z")
        b2 = AgentBudget("b2", "a2", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, reset_at="2024-01-01T12:00:00Z")
        self.engine.create_budget(b1)
        self.engine.create_budget(b2)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100))
        self.engine.consume_resource(ResourceConsumption("c2", "a2", ResourceType.TOKENS, 100))
        
        reset_ids = self.engine.reset_expired_budgets("2024-01-01T11:00:00Z")
        self.assertEqual(len(reset_ids), 1)
        self.assertEqual(reset_ids[0], "b1")
        self.assertEqual(b1.used, 0)
        self.assertEqual(b2.used, 100)

    def test_get_consumption_history_all(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100))
        self.engine.consume_resource(ResourceConsumption("c2", "a1", ResourceType.TOKENS, 200))
        history = self.engine.get_consumption_history("a1")
        self.assertEqual(len(history), 2)

    def test_get_consumption_history_filtered(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        self.engine.create_budget(AgentBudget("b2", "a1", ResourceType.API_CALLS, BudgetPeriod.DAILY, 1000))
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100))
        self.engine.consume_resource(ResourceConsumption("c2", "a1", ResourceType.API_CALLS, 200))
        history = self.engine.get_consumption_history("a1", ResourceType.TOKENS)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].consumption_id, "c1")

    def test_get_top_consumers(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        self.engine.create_budget(AgentBudget("b2", "a2", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        self.engine.create_budget(AgentBudget("b3", "a3", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100))
        self.engine.consume_resource(ResourceConsumption("c2", "a2", ResourceType.TOKENS, 300))
        self.engine.consume_resource(ResourceConsumption("c3", "a3", ResourceType.TOKENS, 200))
        
        top = self.engine.get_top_consumers(ResourceType.TOKENS, n=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["agent_id"], "a2")
        self.assertEqual(top[1]["agent_id"], "a3")

    def test_forecast_exhaustion_no_history(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        forecast = self.engine.forecast_exhaustion("a1", ResourceType.TOKENS)
        self.assertEqual(forecast["exhausts_in_seconds"], -1)

    def test_forecast_exhaustion_with_history(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100, timestamp="2024-01-01T10:00:00Z"))
        self.engine.consume_resource(ResourceConsumption("c2", "a1", ResourceType.TOKENS, 100, timestamp="2024-01-01T10:00:10Z"))
        forecast = self.engine.forecast_exhaustion("a1", ResourceType.TOKENS)
        self.assertTrue(forecast["rate_per_sec"] > 0)
        self.assertTrue(forecast["exhausts_in_seconds"] > 0)

    def test_forecast_exhaustion_no_budget(self):
        with self.assertRaises(ValueError):
            self.engine.forecast_exhaustion("a1", ResourceType.TOKENS)

    def test_get_budget_report(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, warning_threshold_pct=80))
        self.engine.create_budget(AgentBudget("b2", "a2", ResourceType.API_CALLS, BudgetPeriod.DAILY, 1000))
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 900))
        
        report = self.engine.get_budget_report()
        self.assertEqual(report["total_budgets"], 2)
        self.assertEqual(report["agents_near_limits"], 1)
        self.assertEqual(report["usage_by_type"][ResourceType.TOKENS.value], 900)

    def test_request_resource_exact_limit_deny(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, hard_limit=True)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 1000))
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 1, "t1")
        self.assertEqual(dec.action, BudgetAction.DENY)

    def test_request_resource_soft_limit_over(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, hard_limit=False)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 1000))
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 100, "t1")
        self.assertEqual(dec.action, BudgetAction.ALERT)

    def test_reset_budget_restores_limit(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 500))
        self.engine.reset_budget("b1")
        self.assertEqual(b.remaining, 1000)
        self.assertEqual(b.used, 0)

    def test_request_resource_throttle_exact_boundary(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 900))
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 1, "t1")
        self.assertEqual(dec.action, BudgetAction.THROTTLE)

    def test_consume_resource_multiple_times(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100))
        self.engine.consume_resource(ResourceConsumption("c2", "a1", ResourceType.TOKENS, 200))
        self.engine.consume_resource(ResourceConsumption("c3", "a1", ResourceType.TOKENS, 300))
        self.assertEqual(b.used, 600)
        self.assertEqual(b.remaining, 400)

    def test_get_all_budgets_empty(self):
        budgets = self.engine.get_all_budgets("a1")
        self.assertEqual(len(budgets), 0)

    def test_reset_expired_budgets_none_expired(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, reset_at="2024-01-01T12:00:00Z")
        self.engine.create_budget(b)
        reset_ids = self.engine.reset_expired_budgets("2024-01-01T11:00:00Z")
        self.assertEqual(len(reset_ids), 0)

    def test_forecast_exhaustion_zero_delta(self):
        self.engine.create_budget(AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000))
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 100, timestamp="2024-01-01T10:00:00Z"))
        self.engine.consume_resource(ResourceConsumption("c2", "a1", ResourceType.TOKENS, 100, timestamp="2024-01-01T10:00:00Z"))
        forecast = self.engine.forecast_exhaustion("a1", ResourceType.TOKENS)
        self.assertEqual(forecast["exhausts_in_seconds"], -1)
        
    def test_request_resource_deny_hard_limit_remaining(self):
        b = AgentBudget("b1", "a1", ResourceType.TOKENS, BudgetPeriod.DAILY, 1000, hard_limit=True)
        self.engine.create_budget(b)
        self.engine.consume_resource(ResourceConsumption("c1", "a1", ResourceType.TOKENS, 900))
        dec = self.engine.request_resource("a1", ResourceType.TOKENS, 200, "t1")
        self.assertEqual(dec.action, BudgetAction.DENY)
        
    def test_get_top_consumers_empty(self):
        top = self.engine.get_top_consumers(ResourceType.TOKENS)
        self.assertEqual(len(top), 0)

if __name__ == '__main__':
    unittest.main()
