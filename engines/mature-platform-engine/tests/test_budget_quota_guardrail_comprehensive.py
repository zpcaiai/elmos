import unittest
from elmos_mature_platform.types import (
    QuotaResourceType,
    GuardrailAction,
    QuotaDefinition,
    BudgetAllocation,
    GuardrailDecision
)
from elmos_mature_platform.budget_quota_guardrail_engine import BudgetQuotaGuardrailEngine

class TestBudgetQuotaGuardrailEngine(unittest.TestCase):
    def setUp(self):
        self.engine = BudgetQuotaGuardrailEngine()
        self.tenant_id = "tenant-123"

    def test_create_quota(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        self.assertIn(self.tenant_id, self.engine.quotas)

    def test_create_budget(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.assertIn(self.tenant_id, self.engine.budgets)

    def test_check_quota_allow(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        decision = self.engine.check_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        self.assertEqual(decision.action, GuardrailAction.ALLOW)

    def test_check_quota_warn(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0, warn_threshold_pct=80.0)
        self.engine.create_quota(q)
        decision = self.engine.check_quota(self.tenant_id, QuotaResourceType.COMPUTE, 85.0)
        self.assertEqual(decision.action, GuardrailAction.WARN)

    def test_check_quota_deny(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        decision = self.engine.check_quota(self.tenant_id, QuotaResourceType.COMPUTE, 105.0)
        self.assertEqual(decision.action, GuardrailAction.DENY)

    def test_check_quota_no_quota(self):
        decision = self.engine.check_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        self.assertEqual(decision.action, GuardrailAction.DENY)
        self.assertIn("No quota defined", decision.reason)

    def test_consume_quota_allow(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.COMPUTE].current_usage, 50.0)

    def test_consume_quota_warn(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0, warn_threshold_pct=80.0)
        self.engine.create_quota(q)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 85.0)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.COMPUTE].current_usage, 85.0)

    def test_consume_quota_deny(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 105.0)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.COMPUTE].current_usage, 0.0)

    def test_check_budget_allow(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        decision = self.engine.check_budget(self.tenant_id, 500.0)
        self.assertEqual(decision.action, GuardrailAction.ALLOW)

    def test_check_budget_warn(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0, alert_threshold_pct=80.0)
        self.engine.create_budget(b)
        decision = self.engine.check_budget(self.tenant_id, 850.0)
        self.assertEqual(decision.action, GuardrailAction.WARN)

    def test_check_budget_deny(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        decision = self.engine.check_budget(self.tenant_id, 1050.0)
        self.assertEqual(decision.action, GuardrailAction.DENY)

    def test_check_budget_no_budget(self):
        decision = self.engine.check_budget(self.tenant_id, 500.0)
        self.assertEqual(decision.action, GuardrailAction.DENY)
        self.assertIn("No budget defined", decision.reason)

    def test_spend_budget_allow(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.spend_budget(self.tenant_id, 500.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].spent, 500.0)

    def test_spend_budget_warn(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0, alert_threshold_pct=80.0)
        self.engine.create_budget(b)
        self.engine.spend_budget(self.tenant_id, 850.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].spent, 850.0)

    def test_spend_budget_deny(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.spend_budget(self.tenant_id, 1050.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].spent, 0.0)

    def test_reserve_budget(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.reserve_budget(self.tenant_id, 200.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].reserved, 200.0)

    def test_reserve_budget_deny(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.reserve_budget(self.tenant_id, 1200.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].reserved, 0.0)

    def test_release_reservation(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.reserve_budget(self.tenant_id, 200.0)
        self.engine.release_reservation(self.tenant_id, 100.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].reserved, 100.0)

    def test_release_reservation_over(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.reserve_budget(self.tenant_id, 200.0)
        self.engine.release_reservation(self.tenant_id, 500.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].reserved, 0.0)

    def test_get_quota_usage(self):
        q1 = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        q2 = QuotaDefinition(quota_id="q2", resource_type=QuotaResourceType.STORAGE, tenant_id=self.tenant_id, limit=500.0)
        self.engine.create_quota(q1)
        self.engine.create_quota(q2)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        usage = self.engine.get_quota_usage(self.tenant_id)
        self.assertEqual(usage["compute"]["current_usage"], 50.0)
        self.assertEqual(usage["storage"]["current_usage"], 0.0)

    def test_get_quota_usage_empty(self):
        usage = self.engine.get_quota_usage("nonexistent")
        self.assertEqual(usage, {})

    def test_get_budget_status(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.spend_budget(self.tenant_id, 100.0)
        self.engine.reserve_budget(self.tenant_id, 200.0)
        status = self.engine.get_budget_status(self.tenant_id)
        self.assertEqual(status["spent"], 100.0)
        self.assertEqual(status["reserved"], 200.0)
        self.assertEqual(status["available"], 700.0)

    def test_get_budget_status_empty(self):
        status = self.engine.get_budget_status("nonexistent")
        self.assertEqual(status, {})

    def test_reset_quotas_specific(self):
        q1 = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        q2 = QuotaDefinition(quota_id="q2", resource_type=QuotaResourceType.STORAGE, tenant_id=self.tenant_id, limit=500.0)
        self.engine.create_quota(q1)
        self.engine.create_quota(q2)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.STORAGE, 100.0)
        self.engine.reset_quotas(self.tenant_id, QuotaResourceType.COMPUTE)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.COMPUTE].current_usage, 0.0)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.STORAGE].current_usage, 100.0)

    def test_reset_quotas_all(self):
        q1 = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        q2 = QuotaDefinition(quota_id="q2", resource_type=QuotaResourceType.STORAGE, tenant_id=self.tenant_id, limit=500.0)
        self.engine.create_quota(q1)
        self.engine.create_quota(q2)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.STORAGE, 100.0)
        self.engine.reset_quotas(self.tenant_id)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.COMPUTE].current_usage, 0.0)
        self.assertEqual(self.engine.quotas[self.tenant_id][QuotaResourceType.STORAGE].current_usage, 0.0)

    def test_get_guardrail_report(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        
        self.engine.consume_quota(self.tenant_id, QuotaResourceType.COMPUTE, 50.0)
        self.engine.spend_budget(self.tenant_id, 1500.0)  # Should deny
        
        report = self.engine.get_guardrail_report()
        self.assertEqual(report["total_tenants_with_quotas"], 1)
        self.assertEqual(report["total_tenants_with_budgets"], 1)
        self.assertEqual(report["total_decisions_made"], 2)  # consume check, spend check
        self.assertTrue("decisions_by_action" in report)

    def test_quota_remaining_budget_field(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=100.0)
        self.engine.create_quota(q)
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        
        decision = self.engine.check_quota(self.tenant_id, QuotaResourceType.COMPUTE, 10.0)
        self.assertEqual(decision.remaining_budget, 1000.0)

    def test_budget_spend_reserves(self):
        b = BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0)
        self.engine.create_budget(b)
        self.engine.reserve_budget(self.tenant_id, 500.0)
        decision = self.engine.spend_budget(self.tenant_id, 600.0)
        self.assertEqual(decision.action, GuardrailAction.DENY)
        
    def test_release_reservation_no_budget(self):
        with self.assertRaises(ValueError):
            self.engine.release_reservation("nonexistent", 100.0)

    def test_check_quota_zero_limit(self):
        q = QuotaDefinition(quota_id="q1", resource_type=QuotaResourceType.COMPUTE, tenant_id=self.tenant_id, limit=0.0)
        self.engine.create_quota(q)
        decision = self.engine.check_quota(self.tenant_id, QuotaResourceType.COMPUTE, 10.0)
        self.assertEqual(decision.action, GuardrailAction.DENY)

    def test_multiple_tenants_isolation(self):
        t2 = "tenant-456"
        self.engine.create_budget(BudgetAllocation(budget_id="b1", tenant_id=self.tenant_id, total_budget=1000.0))
        self.engine.create_budget(BudgetAllocation(budget_id="b2", tenant_id=t2, total_budget=500.0))
        self.engine.spend_budget(self.tenant_id, 600.0)
        self.assertEqual(self.engine.budgets[self.tenant_id].spent, 600.0)
        self.assertEqual(self.engine.budgets[t2].spent, 0.0)

if __name__ == '__main__':
    unittest.main()
