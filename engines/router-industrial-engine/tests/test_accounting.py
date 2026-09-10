"""Tests for budget management, rate limiting, and cost accounting."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from elmos_router_industrial.accounting.accounting import (
    AccountingEvent,
    BudgetManager,
    CostLedger,
    RateLimiter,
    UsageReconciler,
)
from elmos_router_industrial.domain.contracts import (
    BudgetEnvelope,
    DataClassification,
    RouteRequest,
    TaskClass,
    UsageReport,
)


class TestAccounting(unittest.TestCase):
    def test_budget_manager_reservation_and_settlement(self) -> None:
        bm = BudgetManager()
        bm.set_budget("tenant:t_corp", 10.00)

        # Successful reservation
        res1 = bm.reserve("t_corp", "task_01", 3.50, "res_01")
        self.assertTrue(res1)
        self.assertAlmostEqual(bm.get_remaining_budget("tenant:t_corp"), 6.50)

        # Rejection when exceeding remaining budget
        res2 = bm.reserve("t_corp", "task_02", 8.00, "res_02")
        self.assertFalse(res2)

        # Settle res1: actual spend was only 2.00, returning 1.50
        bm.settle("t_corp", "task_01", 2.00, "res_01")
        self.assertAlmostEqual(bm.get_remaining_budget("tenant:t_corp"), 8.00)

    def test_rate_limiter_concurrency_and_token_bucket(self) -> None:
        rl = RateLimiter(default_tps=10.0, default_burst=2.0, max_concurrent=2)

        # Acquire 1
        self.assertTrue(rl.try_acquire("t_1", "dep_1", 100, now=10.0))
        # Acquire 2
        self.assertTrue(rl.try_acquire("t_1", "dep_1", 100, now=10.0))
        # Concurrency limit reached (max 2)
        self.assertFalse(rl.try_acquire("t_1", "dep_1", 100, now=10.0))

        # Release one
        rl.release("t_1", "dep_1")
        # Token bucket is now empty at now=10.0
        self.assertFalse(rl.try_acquire("t_1", "dep_1", 100, now=10.0))

        # Advance time by 0.5s (replenishing 5 tokens)
        self.assertTrue(rl.try_acquire("t_1", "dep_1", 100, now=10.5))

    def test_usage_reconciliation(self) -> None:
        req = RouteRequest(
            tenantId="t_01",
            taskId="task_01",
            stepId="step_01",
            attemptId="att_01",
            taskClass=TaskClass.CODE_GENERATION,
            dataClassification=(DataClassification.INTERNAL,),
            securityContextRef="sec",
            capabilityLeaseRef="lease",
            budgetEnvelope=BudgetEnvelope("USD", 5.0),
            deadline=datetime.now(timezone.utc),
            idempotencyKey="idem",
            maxInputTokens=2000,
            expectedOutputTokens=1000,
        )

        # Provider report available
        p_usage = UsageReport(promptTokens=1800, completionTokens=950, totalTokens=2750)
        reconciled = UsageReconciler.reconcile(p_usage, None, req)
        self.assertEqual(reconciled.source, "PROVIDER")
        self.assertEqual(reconciled.confidence, 1.0)
        self.assertEqual(reconciled.usage.totalTokens, 2750)

        # Fallback to tokenizer estimate when usage is missing
        reconciled_fallback = UsageReconciler.reconcile(None, None, req)
        self.assertEqual(reconciled_fallback.source, "TOKENIZER_ESTIMATE")
        self.assertEqual(reconciled_fallback.confidence, 0.75)

    def test_cost_ledger(self) -> None:
        ledger = CostLedger()
        event1 = AccountingEvent(
            eventId="ev_1",
            taskId="task_01",
            stepId="step_01",
            attemptId="att_01",
            tenantId="tenant_x",
            modelAlias="gpt-4o",
            deploymentId="dep_1",
            providerId="openai",
            promptTokens=100,
            completionTokens=50,
            totalTokens=150,
            reasoningTokens=0,
            cachedTokens=0,
            estimatedCost=0.010,
            reconciledCost=0.008,
            currency="USD",
            recordedAt=datetime.now(timezone.utc),
            pricingVersion="1",
        )
        ledger.append(event1)
        self.assertEqual(len(ledger.list_all()), 1)
        self.assertEqual(ledger.get_total_spend_for_tenant("tenant_x"), 0.008)


if __name__ == "__main__":
    unittest.main()
