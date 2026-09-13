"""Honest industrial quality percentage. Never hard-code 100.0."""

from __future__ import annotations

from typing import Any


def industrial_quality_percent(campaign: dict[str, Any], extra_scores: dict[str, float] | None = None) -> float:
    total = int(campaign.get("pairs_total") or 0)
    passed = int(campaign.get("pairs_passed") or 0)
    if total <= 0:
        return 0.0
    route_score = passed / total
    extras = extra_scores or {}
    anti_template = float(extras.get("anti_template", 1.0 if not campaign.get("failures") else route_score))
    audit = float(extras.get("audit", 1.0))
    engines = float(extras.get("engines", 1.0))
    score = 100.0 * route_score * anti_template * audit * engines
    return round(min(score, 100.0), 4)
