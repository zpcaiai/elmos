"""Token -> money conversion.

No vendor rate is hard-coded anywhere in this package. Rates arrive through a
versioned registry that must carry ``effective_date``, ``verified_at`` and
``source_reference``; anything flagged ``not_for_billing`` is illustrative and is
kept out of every ranking.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .io_utils import summarize
from .simulation import TOKEN_FIELDS


def mix_verification(mix_report: dict[str, Any] | None) -> dict[str, Any]:
    """State whether the category mix backing these costs has been measured.

    Every number in a cost report is the product of a token count and a category
    mix. The count gets scrutiny because it is large and visible; the mix is a
    handful of ratios in a config file and gets none. Since the categories are
    priced up to fifty times apart, an unexamined mix can be the single largest
    error in the report while every other input is correct.

    So the cost report now has to declare the state of that input, the same way
    it already declares the provenance of its rates.
    """
    if not mix_report:
        return {
            "checked": False,
            "detail": (
                "这些费用背后的分类占比是**假设值**，从未与真实用量对照过。"
                "跑 `token-mix` 之后这里会换成实测结论。"
            ),
        }

    observed = mix_report.get("observed") or {}
    depths = mix_report.get("cost_by_session_depth") or []
    return {
        "checked": True,
        "sessions": int(observed.get("sessions", 0)),
        "minimum_sessions": mix_report.get("minimum_sessions"),
        "sample_sufficient": bool(mix_report.get("sample_sufficient")),
        "observed_cached_input_share": (mix_report.get("observed") or {}).get(
            "mix", {}).get("cached_input"),
        "forecast_cached_input_share": (mix_report.get("forecast") or {}).get(
            "mix", {}).get("cached_input"),
        "overstatement_by_depth": [
            {"turns": row["turns"], "factor": row.get("overstatement_factor")}
            for row in depths
        ],
        "detail": (
            "分类占比已与真实用量对照过（见 TOKEN_MIX_COMPARISON.md）。"
            "**下表的费用建立在未经校准的假设占比上**，实测显示它对长任务高估明显、"
            "对短任务基本准确——具体倍数看那份报告的曲线，不要套一个固定倍数。"
        ),
    }


def estimate_costs(
    token_samples: list[dict[str, float]],
    registry: dict[str, Any],
    worst_probability: float = 0.99,
    mix_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not token_samples:
        raise ValueError("Cannot estimate cost without token samples")
    base_currency = registry.get("base_currency", "USD")
    results: list[dict[str, Any]] = []

    for model in registry["models"]:
        rates = model["rates_per_million"]
        sample_costs: list[float] = []
        category_totals = {field: 0.0 for field in TOKEN_FIELDS}
        for sample in token_samples:
            cost = 0.0
            for field in TOKEN_FIELDS:
                component = float(sample[field]) / 1_000_000.0 * float(rates[field])
                cost += component
                category_totals[field] += component
            sample_costs.append(cost)
        divisor = float(len(sample_costs))
        results.append({
            "model_id": model["id"],
            "provider": model.get("provider"),
            "display_name": model.get("display_name", model["id"]),
            "currency": model.get("currency", base_currency),
            "effective_date": model.get("effective_date"),
            "verified_at": model.get("verified_at"),
            "source_reference": model.get("source_reference"),
            "billing_mode": model.get("billing_mode"),
            "not_for_billing": bool(model.get("not_for_billing", False)),
            "cost": summarize(sample_costs, worst_probability, digits=4),
            "mean_cost_by_category": {
                key: round(value / divisor, 6) for key, value in category_totals.items()
            },
        })

    # Ranking only ever happens inside one currency. Comparing a CNY rate card
    # with a USD rate card without a dated FX rate produces a wrong answer that
    # looks right, so it is refused rather than approximated.
    by_currency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in results:
        by_currency[entry["currency"]].append(entry)

    rankings = {}
    for currency, entries in sorted(by_currency.items()):
        billable = [entry for entry in entries if not entry["not_for_billing"]]
        pool = billable or entries
        ordered = sorted(pool, key=lambda entry: entry["cost"]["p50"])
        rankings[currency] = {
            "ranked_model_ids_by_p50": [entry["model_id"] for entry in ordered],
            "cheapest_p50": ordered[0]["model_id"] if ordered else None,
            "ranking_pool": "verified_rates" if billable else "illustrative_rates",
        }

    return {
        "registry_version": registry.get("registry_version"),
        "base_currency": base_currency,
        "currencies": sorted(by_currency),
        "models": results,
        "rankings_by_currency": rankings,
        "cross_currency_comparison": None,
        "mix_verification": mix_verification(mix_report),
        "cross_currency_note": (
            "Models priced in different currencies are never ranked against each other here. "
            "Supply a dated FX rate and do that conversion explicitly if it is needed."
        ),
        "warning": (
            "Any model marked not_for_billing uses illustrative rates. It validates the arithmetic only "
            "and must not back a financial commitment."
        ),
    }
