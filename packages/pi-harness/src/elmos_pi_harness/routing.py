"""Deterministic capability/budget-aware model routing without provider calls."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypedDict


@dataclass(frozen=True)
class ModelCapability:
    alias: str
    provider: str
    model_id: str
    quality: Decimal
    cost_per_million: Decimal
    latency_ms: int
    capabilities: frozenset[str]
    enabled: bool = True


@dataclass(frozen=True)
class RoutingRequest:
    required_capabilities: frozenset[str]
    max_cost_usd: Decimal | None = None
    preferred: str | None = None


class RoutingCandidate(TypedDict):
    alias: str
    provider: str
    model_id: str
    eligible: bool
    reasons: list[str]
    score: str


def route(request: RoutingRequest, models: Iterable[ModelCapability]) -> dict[str, Any]:
    candidates: list[RoutingCandidate] = []
    for model in models:
        reasons: list[str] = []
        if not model.enabled:
            reasons.append("disabled")
        reasons.extend("missing_capability:" + item for item in sorted(request.required_capabilities - model.capabilities))
        if request.max_cost_usd is not None and model.cost_per_million > request.max_cost_usd:
            reasons.append("cost_limit_exceeded")
        candidates.append({"alias": model.alias, "provider": model.provider, "model_id": model.model_id, "eligible": not reasons, "reasons": reasons, "score": str(model.quality / max(model.cost_per_million, Decimal("0.000001")))})
    eligible = [item for item in candidates if item["eligible"]]
    if request.preferred:
        preferred = [item for item in eligible if item["alias"] == request.preferred]
        chosen = preferred[0] if preferred else None
    else:
        chosen = max(eligible, key=lambda item: (Decimal(item["score"]), item["alias"])) if eligible else None
    return {"status": "PLANNED" if chosen else "BLOCKED", "chosen": chosen, "candidates": candidates, "provider_calls": 0}
