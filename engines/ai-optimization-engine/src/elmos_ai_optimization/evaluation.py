"""Evaluation metrics, percentile calculations, and paired comparison analytics."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .contracts import ContractError, require_finite_float


def ranked_metrics(
    ranking: Sequence[str],
    relevance: Mapping[str, int],
    k: int = 5,
) -> dict[str, Any]:
    """Compute Recall@k, MRR, and NDCG@k against multi-grade relevance."""
    if k < 1:
        raise ContractError("k must be >= 1")
    for key, grade in relevance.items():
        if not isinstance(grade, int) or not 0 <= grade <= 3:
            raise ContractError(f"Relevance grade for {key} must be int in [0, 3], got {grade}")

    # Deduplicate ranking preserving order
    deduped_ranks = list(dict.fromkeys(ranking))[:k]
    positive_items = {item for item, grade in relevance.items() if grade > 0}

    if not positive_items:
        return {
            "answerable": False,
            "recall": None,
            "mrr": None,
            "ndcg": None,
            "returned_any": bool(deduped_ranks),
        }

    hits = set(deduped_ranks) & positive_items
    recall = len(hits) / len(positive_items)

    first_hit_rank = None
    for idx, item in enumerate(deduped_ranks):
        if relevance.get(item, 0) > 0:
            first_hit_rank = idx + 1
            break
    mrr = 1.0 / first_hit_rank if first_hit_rank else 0.0

    dcg = sum(
        (2 ** relevance.get(item, 0) - 1) / math.log2(idx + 2)
        for idx, item in enumerate(deduped_ranks)
    )
    ideal_grades = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(
        (2 ** g - 1) / math.log2(idx + 2)
        for idx, g in enumerate(ideal_grades)
    )
    ndcg = (dcg / idcg) if idcg > 0.0 else 0.0

    return {
        "answerable": True,
        "recall": recall,
        "mrr": mrr,
        "ndcg": ndcg,
        "returned_any": bool(deduped_ranks),
    }


def nearest_rank(samples: Sequence[float], percentile: float) -> float:
    """Compute nearest-rank percentile over non-negative samples."""
    if not samples:
        raise ContractError("samples cannot be empty")
    if not 0.0 < percentile <= 1.0:
        raise ContractError(f"percentile must be in (0, 1], got {percentile}")

    clean: list[float] = []
    for s in samples:
        clean.append(require_finite_float(s, "sample"))

    sorted_samples = sorted(clean)
    idx = math.ceil(percentile * len(sorted_samples)) - 1
    return sorted_samples[idx]


def cost_per_accepted(
    attempt_costs: Sequence[float],
    accepted_count: int,
    amortization: float = 0.0,
) -> float | None:
    """Calculate cost per accepted module including retries, repairs, and amortization."""
    if not isinstance(accepted_count, int) or accepted_count < 0:
        raise ContractError("accepted_count must be non-negative integer")
    amort = require_finite_float(amortization, "amortization")
    if amort < 0:
        raise ContractError("amortization must be non-negative")

    total_cost = amort
    for c in attempt_costs:
        cost = require_finite_float(c, "attempt_cost")
        if cost < 0:
            raise ContractError("attempt_cost must be non-negative")
        total_cost += cost

    if accepted_count == 0:
        return None
    return total_cost / accepted_count


def compare_paired(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    min_quality_delta: float = 0.03,
    max_latency_ratio: float = 1.10,
    max_cost_ratio: float = 1.10,
) -> dict[str, Any]:
    """Strict paired comparison with guardrails preventing quality/cost regression."""
    for key in ["dataset_digest", "environment_digest", "scope_digest", "model_profile", "warm_state"]:
        if key not in baseline or baseline[key] != candidate.get(key):
            raise ContractError(f"Incomparable evaluation runs: mismatch on {key}")

    b_cases = baseline.get("cases", {})
    c_cases = candidate.get("cases", {})
    if not b_cases or set(b_cases.keys()) != set(c_cases.keys()):
        raise ContractError("Paired comparison requires identical non-empty case sets")

    quality_deltas: list[float] = []
    latency_ratios: list[float] = []
    cost_ratios: list[float] = []

    for cid in b_cases:
        b_obs = b_cases[cid]
        c_obs = c_cases[cid]

        # Security check: any leak is immediate rejection
        if c_obs.get("leaks", 0) > 0:
            return {
                "decision": "REJECTED",
                "reason": f"Security leak detected in case {cid}",
                "qualified": False,
            }

        q_delta = c_obs["quality"] - b_obs["quality"]
        quality_deltas.append(q_delta)

        b_lat = b_obs["latency_ms"]
        c_lat = c_obs["latency_ms"]
        if b_lat > 0:
            latency_ratios.append(c_lat / b_lat)

        b_cost = b_obs.get("cost", 0.0)
        c_cost = c_obs.get("cost", 0.0)
        if b_cost > 0:
            cost_ratios.append(c_cost / b_cost)

    avg_quality_delta = sum(quality_deltas) / len(quality_deltas)
    avg_latency_ratio = sum(latency_ratios) / len(latency_ratios) if latency_ratios else 1.0
    avg_cost_ratio = sum(cost_ratios) / len(cost_ratios) if cost_ratios else 1.0

    qualified = (
        avg_quality_delta >= min_quality_delta
        and avg_latency_ratio <= max_latency_ratio
        and avg_cost_ratio <= max_cost_ratio
    )

    return {
        "decision": "QUALIFIED" if qualified else "REJECTED",
        "avg_quality_delta": avg_quality_delta,
        "avg_latency_ratio": avg_latency_ratio,
        "avg_cost_ratio": avg_cost_ratio,
        "qualified": qualified,
    }
