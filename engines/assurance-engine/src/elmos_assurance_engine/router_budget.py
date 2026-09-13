"""Implementation of B01: Model router budget, resource governance, and execution limits."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .contracts import GateDecision


class BudgetExhaustedError(RuntimeError):
    pass


@dataclass
class ResourceBudget:
    max_tokens: int = 1_000_000
    max_cost_cents: int = 5000  # $50.00
    max_wall_seconds: float = 3600.0  # 1 hour
    max_memory_mb: int = 8192

    consumed_tokens: int = 0
    consumed_cost_cents: int = 0
    consumed_wall_seconds: float = 0.0
    start_time: float = field(default_factory=time.time)

    def consume(
        self,
        tokens: int = 0,
        cost_cents: int = 0,
        wall_seconds: float | None = None,
    ) -> None:
        self.consumed_tokens += tokens
        self.consumed_cost_cents += cost_cents
        if wall_seconds is not None:
            self.consumed_wall_seconds += wall_seconds
        else:
            self.consumed_wall_seconds = time.time() - self.start_time

        if self.consumed_tokens > self.max_tokens:
            raise BudgetExhaustedError(
                f"TOKEN_BUDGET_EXHAUSTED: {self.consumed_tokens} > {self.max_tokens}"
            )
        if self.consumed_cost_cents > self.max_cost_cents:
            raise BudgetExhaustedError(
                f"COST_BUDGET_EXHAUSTED: {self.consumed_cost_cents} > {self.max_cost_cents}"
            )
        if self.consumed_wall_seconds > self.max_wall_seconds:
            raise BudgetExhaustedError(
                f"WALL_CLOCK_BUDGET_EXHAUSTED: {self.consumed_wall_seconds:.1f}s > {self.max_wall_seconds:.1f}s"
            )

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.max_tokens - self.consumed_tokens)

    @property
    def cost_cents_remaining(self) -> int:
        return max(0, self.max_cost_cents - self.consumed_cost_cents)

    def check_status(self) -> tuple[GateDecision, str]:
        if self.consumed_tokens > self.max_tokens or \
           self.consumed_cost_cents > self.max_cost_cents or \
           self.consumed_wall_seconds > self.max_wall_seconds:
            return GateDecision.INCONCLUSIVE, "PAUSED_BUDGET_EXHAUSTED"
        return GateDecision.PASS, "BUDGET_WITHIN_LIMITS"
