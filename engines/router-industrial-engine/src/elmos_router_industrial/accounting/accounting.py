"""Budget management, rate limiting, token usage reconciliation, and cost ledger.

Provides hierarchical budget enforcement, concurrency control, and auditable accounting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import threading
import time
from typing import Any, Mapping

from ..domain.contracts import (
    ModelExecutionPlan,
    ReconciledUsage,
    RouteRequest,
    UsageReport,
)
from ..domain.errors import ErrorTaxonomyClass, ProviderError


@dataclass(frozen=True)
class AccountingEvent:
    eventId: str
    taskId: str
    stepId: str
    attemptId: str
    tenantId: str
    modelAlias: str
    deploymentId: str
    providerId: str
    promptTokens: int
    completionTokens: int
    totalTokens: int
    reasoningTokens: int
    cachedTokens: int
    estimatedCost: float
    reconciledCost: float
    currency: str
    recordedAt: datetime
    pricingVersion: str


class BudgetManager:
    """Hierarchical budget manager (Platform -> Tenant -> Project -> Task -> Step)."""

    def __init__(self) -> None:
        self._budgets: dict[str, float] = {}  # scope_key -> remaining_budget
        self._reservations: dict[str, float] = {}  # reservation_id -> reserved_amount
        self._lock = threading.Lock()

    def set_budget(self, scope_key: str, amount: float) -> None:
        with self._lock:
            self._budgets[scope_key] = float(amount)

    def get_remaining_budget(self, scope_key: str) -> float:
        with self._lock:
            return self._budgets.get(scope_key, float("inf"))

    def reserve(
        self,
        tenant_id: str,
        task_id: str,
        estimated_cost: float,
        reservation_id: str,
    ) -> bool:
        """Atomically reserves funds at tenant and task scopes."""
        with self._lock:
            tenant_key = f"tenant:{tenant_id}"
            task_key = f"task:{task_id}"

            tenant_rem = self._budgets.get(tenant_key, float("inf"))
            task_rem = self._budgets.get(task_key, float("inf"))

            if estimated_cost > tenant_rem or estimated_cost > task_rem:
                return False

            if tenant_key in self._budgets:
                self._budgets[tenant_key] -= estimated_cost
            if task_key in self._budgets:
                self._budgets[task_key] -= estimated_cost

            self._reservations[reservation_id] = estimated_cost
            return True

    def settle(
        self,
        tenant_id: str,
        task_id: str,
        actual_cost: float,
        reservation_id: str,
    ) -> None:
        """Settles reservation by returning unused funds or deducting additional spend."""
        with self._lock:
            reserved = self._reservations.pop(reservation_id, 0.0)
            diff = reserved - actual_cost

            tenant_key = f"tenant:{tenant_id}"
            task_key = f"task:{task_id}"

            if tenant_key in self._budgets:
                self._budgets[tenant_key] += diff
            if task_key in self._budgets:
                self._budgets[task_key] += diff


class RateLimiter:
    """Multi-dimensional token bucket rate limiter and concurrency semaphore."""

    def __init__(
        self,
        default_tps: float = 50.0,
        default_burst: float = 100.0,
        max_concurrent: int = 20,
    ) -> None:
        self.default_tps = default_tps
        self.default_burst = default_burst
        self.max_concurrent = max_concurrent

        # Token bucket state: key -> (tokens, last_update_time)
        self._buckets: dict[str, tuple[float, float]] = {}
        # Concurrency state: key -> current_concurrency
        self._concurrency: dict[str, int] = {}
        self._lock = threading.Lock()

    def try_acquire(
        self,
        tenant_id: str,
        deployment_id: str,
        estimated_tokens: int,
        now: float | None = None,
    ) -> bool:
        current_time = now if now is not None else time.time()
        keys = [f"tenant:{tenant_id}", f"deployment:{deployment_id}"]

        with self._lock:
            # 1. Check concurrency limits
            for k in keys:
                if self._concurrency.get(k, 0) >= self.max_concurrent:
                    return False

            # 2. Check token bucket rate limit
            for k in keys:
                tokens, last_update = self._buckets.get(k, (self.default_burst, current_time))
                # Replenish
                elapsed = max(0.0, current_time - last_update)
                tokens = min(self.default_burst, tokens + elapsed * self.default_tps)
                if tokens < 1.0:
                    return False

            # 3. Commit acquisition
            for k in keys:
                tokens, last_update = self._buckets.get(k, (self.default_burst, current_time))
                elapsed = max(0.0, current_time - last_update)
                tokens = min(self.default_burst, tokens + elapsed * self.default_tps)
                self._buckets[k] = (tokens - 1.0, current_time)
                self._concurrency[k] = self._concurrency.get(k, 0) + 1

            return True

    def release(self, tenant_id: str, deployment_id: str) -> None:
        keys = [f"tenant:{tenant_id}", f"deployment:{deployment_id}"]
        with self._lock:
            for k in keys:
                cur = self._concurrency.get(k, 0)
                if cur > 0:
                    self._concurrency[k] = cur - 1


class UsageReconciler:
    """3-Way reconciliation: Provider Reported -> Gateway Reported -> Tokenizer Estimate."""

    @staticmethod
    def reconcile(
        provider_usage: UsageReport | None,
        gateway_usage: UsageReport | None,
        request: RouteRequest,
        deployment_rates: tuple[float, float] = (0.003, 0.015),
    ) -> ReconciledUsage:
        price_in, price_out = deployment_rates

        if provider_usage and provider_usage.totalTokens > 0:
            usage = provider_usage
            source = "PROVIDER"
            conf = 1.0
        elif gateway_usage and gateway_usage.totalTokens > 0:
            usage = gateway_usage
            source = "GATEWAY"
            conf = 0.95
        else:
            # Fallback character estimation (approx 4 chars / token)
            prompt_toks = max(1, request.maxInputTokens // 2)
            comp_toks = max(1, request.expectedOutputTokens // 2)
            usage = UsageReport(promptTokens=prompt_toks, completionTokens=comp_toks, totalTokens=prompt_toks + comp_toks)
            source = "TOKENIZER_ESTIMATE"
            conf = 0.75

        est_cost = (request.maxInputTokens / 1000.0) * price_in + (request.expectedOutputTokens / 1000.0) * price_out
        reconciled_cost = (usage.promptTokens / 1000.0) * price_in + (usage.completionTokens / 1000.0) * price_out

        return ReconciledUsage(
            source=source,
            usage=usage,
            estimatedCost=round(est_cost, 6),
            reconciledCost=round(reconciled_cost, 6),
            currency=request.budgetEnvelope.currency,
            confidence=conf,
        )


class CostLedger:
    """Thread-safe append-only cost and token usage accounting ledger."""

    def __init__(self) -> None:
        self._records: list[AccountingEvent] = []
        self._lock = threading.Lock()

    def append(self, event: AccountingEvent) -> None:
        with self._lock:
            self._records.append(event)

    def get_events_for_tenant(self, tenant_id: str) -> list[AccountingEvent]:
        with self._lock:
            return [e for e in self._records if e.tenantId == tenant_id]

    def get_total_spend_for_tenant(self, tenant_id: str) -> float:
        with self._lock:
            return sum(e.reconciledCost for e in self._records if e.tenantId == tenant_id)

    def list_all(self) -> list[AccountingEvent]:
        with self._lock:
            return list(self._records)
