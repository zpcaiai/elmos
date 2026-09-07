"""Bounded budgets, ETA, failure classification, and retry decisions."""

from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractError,
    FailureClass,
    FallbackPolicy,
    ModelMode,
    Status,
    decimal_value,
    integer_value,
    require_mapping,
    require_string,
)
from .models import RegistrySnapshot, ResolvedModelSelection, RoutingTaskProfile
from .planning import DagPlan
from .routing import RouteDecision, route_model


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    currency: str
    hard_cost: Decimal
    soft_cost: Decimal
    max_calls: int
    max_tokens: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "BudgetLimits":
        value = require_mapping(payload, "budget_limits")
        currency = require_string(value.get("currency"), "budget_limits.currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ContractError("invalid_currency", "budget currency must be a three-letter code")
        hard = decimal_value(value.get("hard_cost"), "budget_limits.hard_cost", minimum=Decimal("0"))
        soft = decimal_value(value.get("soft_cost", value.get("hard_cost")), "budget_limits.soft_cost", minimum=Decimal("0"))
        if soft > hard:
            raise ContractError("invalid_budget", "soft_cost cannot exceed hard_cost")
        return cls(
            currency=currency,
            hard_cost=hard,
            soft_cost=soft,
            max_calls=integer_value(value.get("max_calls"), "budget_limits.max_calls", minimum=1),
            max_tokens=integer_value(value.get("max_tokens"), "budget_limits.max_tokens", minimum=1),
        )


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_id: str
    task_id: str
    model_alias: str
    estimated_cost: Decimal
    estimated_tokens: int
    currency: str
    status: Status
    settled_cost: Decimal | None = None
    settled_tokens: int | None = None
    reason: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "reservation_id": self.reservation_id,
            "task_id": self.task_id,
            "model_alias": self.model_alias,
            "estimated_cost": format(self.estimated_cost, "f"),
            "estimated_tokens": self.estimated_tokens,
            "currency": self.currency,
            "status": self.status.value,
            "settled_cost": None if self.settled_cost is None else format(self.settled_cost, "f"),
            "settled_tokens": self.settled_tokens,
            "reason": self.reason,
        }


class BudgetLedger:
    """Thread-safe local reservation ledger preventing concurrent overbooking."""

    def __init__(self, limits: BudgetLimits):
        self.limits = limits
        self._reservations: dict[str, BudgetReservation] = {}
        self._lock = threading.Lock()

    def _usage(self) -> tuple[Decimal, int, int]:
        cost = Decimal("0")
        tokens = 0
        calls = 0
        for item in self._reservations.values():
            if item.status not in {Status.READY, Status.LOCAL_ENGINEERING_VALIDATED} and item.settled_cost is None:
                continue
            cost += item.settled_cost if item.settled_cost is not None else item.estimated_cost
            tokens += item.settled_tokens if item.settled_tokens is not None else item.estimated_tokens
            calls += 1
        return cost, tokens, calls

    def reserve(
        self,
        *,
        reservation_id: str,
        task_id: str,
        model_alias: str,
        estimated_cost: Decimal | str | int,
        estimated_tokens: int,
        currency: str,
    ) -> BudgetReservation:
        rid = require_string(reservation_id, "reservation_id")
        cost = decimal_value(estimated_cost, "estimated_cost", minimum=Decimal("0"))
        tokens = integer_value(estimated_tokens, "estimated_tokens")
        currency = require_string(currency, "currency").upper()
        with self._lock:
            existing = self._reservations.get(rid)
            candidate_identity = (task_id, model_alias, cost, tokens, currency)
            if existing is not None:
                existing_identity = (
                    existing.task_id,
                    existing.model_alias,
                    existing.estimated_cost,
                    existing.estimated_tokens,
                    existing.currency,
                )
                if existing_identity != candidate_identity:
                    raise ContractError("idempotency_conflict", "reservation id reused with different inputs")
                return existing
            if currency != self.limits.currency:
                result = BudgetReservation(rid, task_id, model_alias, cost, tokens, currency, Status.BLOCKED, reason="currency_mismatch")
            else:
                used_cost, used_tokens, used_calls = self._usage()
                reason = None
                if used_cost + cost > self.limits.hard_cost:
                    reason = "hard_cost_exceeded"
                elif used_tokens + tokens > self.limits.max_tokens:
                    reason = "token_budget_exceeded"
                elif used_calls + 1 > self.limits.max_calls:
                    reason = "call_budget_exceeded"
                result = BudgetReservation(
                    rid,
                    task_id,
                    model_alias,
                    cost,
                    tokens,
                    currency,
                    Status.BLOCKED if reason else Status.READY,
                    reason=reason,
                )
            self._reservations[rid] = result
            return result

    def settle(self, reservation_id: str, *, actual_cost: Decimal | str | int, actual_tokens: int) -> BudgetReservation:
        cost = decimal_value(actual_cost, "actual_cost", minimum=Decimal("0"))
        tokens = integer_value(actual_tokens, "actual_tokens")
        with self._lock:
            existing = self._reservations.get(reservation_id)
            if existing is None:
                raise ContractError("unknown_reservation", "cannot settle an unknown reservation")
            if existing.status is Status.BLOCKED:
                raise ContractError("blocked_reservation", "cannot settle a blocked reservation")
            if existing.settled_cost is not None:
                if existing.settled_cost != cost or existing.settled_tokens != tokens:
                    raise ContractError("settlement_conflict", "reservation already settled with different usage")
                return existing
            settled = replace(existing, settled_cost=cost, settled_tokens=tokens, status=Status.LOCAL_ENGINEERING_VALIDATED)
            self._reservations[reservation_id] = settled
            used_cost, used_tokens, _ = self._usage()
            if used_cost > self.limits.hard_cost or used_tokens > self.limits.max_tokens:
                settled = replace(settled, status=Status.BLOCKED, reason="actual_usage_exceeded_budget")
                self._reservations[reservation_id] = settled
            return settled

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            cost, tokens, calls = self._usage()
            return {
                "currency": self.limits.currency,
                "reserved_or_spent_cost": format(cost, "f"),
                "reserved_or_spent_tokens": tokens,
                "calls": calls,
                "hard_cost": format(self.limits.hard_cost, "f"),
                "max_tokens": self.limits.max_tokens,
                "max_calls": self.limits.max_calls,
                "reservations": [self._reservations[key].to_payload() for key in sorted(self._reservations)],
                "certification": Status.NOT_CERTIFIED.value,
            }


@dataclass(frozen=True, slots=True)
class EtaEstimate:
    p50_seconds: Decimal
    p90_seconds: Decimal
    critical_path: tuple[str, ...]
    confidence: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "p50_seconds": format(self.p50_seconds, "f"),
            "p90_seconds": format(self.p90_seconds, "f"),
            "critical_path": list(self.critical_path),
            "confidence": self.confidence,
            "kind": "autonomous_machine_wall_clock",
        }


def estimate_eta(
    plan: DagPlan,
    duration_seconds: Mapping[str, Any],
    *,
    concurrency: int,
    p90_multiplier: Decimal | str | int = "1.5",
) -> EtaEstimate:
    slots = integer_value(concurrency, "concurrency", minimum=1)
    missing = sorted(set(plan.tasks) - set(duration_seconds))
    extra = sorted(set(duration_seconds) - set(plan.tasks))
    if missing or extra:
        raise ContractError("duration_task_mismatch", f"duration task mismatch; missing={missing}, extra={extra}")
    durations = {task_id: decimal_value(duration_seconds[task_id], f"duration.{task_id}", minimum=Decimal("0")) for task_id in plan.tasks}
    multiplier = decimal_value(p90_multiplier, "p90_multiplier", minimum=Decimal("1"))
    total = Decimal("0")
    for wave in plan.waves:
        heaps = [Decimal("0") for _ in range(min(slots, len(wave)))]
        heapq.heapify(heaps)
        for task_id in sorted(wave, key=lambda item: (-durations[item], item)):
            available = heapq.heappop(heaps)
            heapq.heappush(heaps, available + durations[task_id])
        total += max(heaps, default=Decimal("0"))
    confidence = "low" if len(plan.tasks) < 5 else "medium"
    return EtaEstimate(total, total * multiplier, plan.critical_path, confidence)


def classify_failure(payload: Mapping[str, Any]) -> FailureClass:
    value = require_mapping(payload, "failure_signals")
    explicit = value.get("failure_class")
    if explicit is not None:
        try:
            return FailureClass(explicit)
        except ValueError as exc:
            raise ContractError("invalid_failure_class", f"unsupported failure_class: {explicit!r}") from exc
    priority = (
        ("security_policy_violation", FailureClass.SECURITY_POLICY_VIOLATION),
        ("forbidden_path_write", FailureClass.FORBIDDEN_PATH_WRITE),
        ("budget_hard_stop", FailureClass.BUDGET_HARD_STOP),
        ("safety_refusal", FailureClass.SAFETY_REFUSAL),
        ("provider_unavailable", FailureClass.PROVIDER_UNAVAILABLE),
        ("context_loss", FailureClass.CONTEXT_LOSS),
        ("architecture_error", FailureClass.ARCHITECTURAL),
        ("integration_error", FailureClass.INTEGRATION),
        ("semantic_error", FailureClass.SEMANTIC),
        ("repeated_test_failure", FailureClass.REPEATED_TEST_FAILURE),
        ("localized_test_failure", FailureClass.LOCALIZED_TEST_FAILURE),
        ("formatting_error", FailureClass.FORMATTING),
        ("transient_tool", FailureClass.TRANSIENT_TOOL),
    )
    for key, failure in priority:
        item = value.get(key, False)
        if not isinstance(item, bool):
            raise ContractError("invalid_failure_signal", f"{key} must be boolean")
        if item:
            return failure
    return FailureClass.UNKNOWN


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    same_model_max_attempts: int = 2
    max_total_attempts: int = 4


@dataclass(frozen=True, slots=True)
class RetryDecision:
    status: Status
    action: str
    model_alias: str | None
    reason: str
    route: RouteDecision | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "action": self.action,
            "model_alias": self.model_alias,
            "reason": self.reason,
            "route": None if self.route is None else self.route.to_dict(),
            "certification": Status.NOT_CERTIFIED.value,
        }


def decide_retry(
    *,
    failure: FailureClass,
    current_model: str,
    attempt_models: Sequence[str],
    selection: ResolvedModelSelection,
    task: RoutingTaskProfile,
    registry: RegistrySnapshot,
    currency: str,
    now: datetime | None = None,
    policy: RetryPolicy = RetryPolicy(),
) -> RetryDecision:
    total = len(attempt_models)
    same = sum(1 for alias in attempt_models if alias == current_model)
    terminal = {
        FailureClass.FORBIDDEN_PATH_WRITE,
        FailureClass.SECURITY_POLICY_VIOLATION,
        FailureClass.BUDGET_HARD_STOP,
        FailureClass.SAFETY_REFUSAL,
    }
    if failure in terminal:
        return RetryDecision(Status.BLOCKED, "stop", None, failure.value)
    if failure is FailureClass.UNKNOWN:
        return RetryDecision(Status.INCONCLUSIVE, "stop", None, "unknown_failure_requires_review")
    if total >= policy.max_total_attempts:
        return RetryDecision(Status.FAILED, "stop", None, "max_total_attempts_reached")
    retry_same = {FailureClass.TRANSIENT_TOOL, FailureClass.FORMATTING, FailureClass.LOCALIZED_TEST_FAILURE}
    if failure in retry_same and same < policy.same_model_max_attempts:
        return RetryDecision(Status.PLANNED, "retry_same", current_model, "bounded_same_model_retry")
    if selection.mode is ModelMode.MANUAL and selection.fallback_policy is FallbackPolicy.STRICT:
        return RetryDecision(Status.BLOCKED, "reselect", None, "model_reselection_required")
    route = route_model(
        task,
        selection,
        registry,
        currency=currency,
        fallback_from_model=current_model,
        failure_class=failure.value,
        excluded_models=attempt_models,
        now=now,
    )
    if route.status is not Status.PLANNED:
        return RetryDecision(route.status, "stop", None, route.reason, route)
    return RetryDecision(Status.PLANNED, "fallback", route.chosen_model, "classified_allowlisted_fallback", route)
