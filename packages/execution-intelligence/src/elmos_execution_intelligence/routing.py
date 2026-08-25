"""Skill 14 — model routing optimizer.

Assigns each task to the cheapest model whose capability tier meets that task's
floor, then reports what the choice saves against an all-frontier baseline.

Two refusals are deliberate:

* a model with no capability profile is never routed to -- the optimizer does not
  assume a tier it has not been told;
* routing is optimised **within a currency**. Choosing a CNY model over a USD one
  because the number is smaller is not an optimisation, it is a unit error.
"""
from __future__ import annotations

from typing import Any

from .io_utils import fmt, markdown_table
from .simulation import TOKEN_FIELDS


def _floor_tier(task: dict[str, Any], capabilities: dict[str, Any]) -> str:
    order = capabilities["tier_order"]
    by_complexity = capabilities["complexity_floor"].get(task.get("complexity", "medium"), order[0])
    by_category = capabilities["category_floor"].get(task.get("category", ""), order[0])
    floor: str = max((by_complexity, by_category), key=order.index)
    return floor


def _task_cost(token_totals: dict[str, float], rates: dict[str, Any]) -> float:
    return sum(
        float(token_totals.get(field, 0.0)) / 1_000_000.0 * float(rates[field])
        for field in TOKEN_FIELDS
    )


def optimize_routing(
    task_document: dict[str, Any],
    pricing: dict[str, Any],
    capabilities: dict[str, Any],
    currency: str | None = None,
) -> dict[str, Any]:
    order: list[str] = capabilities["tier_order"]
    profiles: dict[str, Any] = capabilities["models"]

    candidates = []
    for model in pricing["models"]:
        profile = profiles.get(model["id"])
        if profile is None:
            continue
        candidates.append({
            "model_id": model["id"],
            "display_name": model.get("display_name", model["id"]),
            "currency": model.get("currency", pricing.get("base_currency", "USD")),
            "tier": profile["tier"],
            "max_context_tokens": profile.get("max_context_tokens"),
            "rates": model["rates_per_million"],
            "not_for_billing": bool(model.get("not_for_billing", False)),
        })
    if not candidates:
        raise ValueError(
            "BLOCKED — no priced model has a capability profile; routing cannot proceed without one"
        )

    currencies = sorted({candidate["currency"] for candidate in candidates})
    target_currency = currency or (currencies[0] if len(currencies) == 1 else None)
    if target_currency is None:
        # Optimise inside the currency that can actually cover every tier.
        for option in currencies:
            tiers = {c["tier"] for c in candidates if c["currency"] == option}
            if set(order) <= tiers or len(tiers) >= 2:
                target_currency = option
                break
        target_currency = target_currency or currencies[0]

    pool = [candidate for candidate in candidates if candidate["currency"] == target_currency]
    if not pool:
        raise ValueError(f"BLOCKED — no capability-profiled model priced in {target_currency}")

    frontier_pool = [c for c in pool if c["tier"] == order[-1]] or pool
    baseline_model = min(frontier_pool, key=lambda c: _task_cost({f: 1_000_000 for f in TOKEN_FIELDS}, c["rates"]))

    assignments = []
    optimized_total = 0.0
    baseline_total = 0.0
    unroutable: list[dict[str, Any]] = []

    context_enforced: list[str] = []
    context_undeclared: list[str] = []

    for task in task_document["tasks"]:
        profile = task["system"]["token_profile"]
        totals = {field: float(profile.get(field, 0.0)) for field in TOKEN_FIELDS}
        floor = _floor_tier(task, capabilities)
        eligible = [c for c in pool if order.index(c["tier"]) >= order.index(floor)]

        # Context window is a hard constraint, not a preference: a task whose peak
        # single-call context exceeds the window does not run more slowly on that
        # model, it fails. It is only enforced where the task says what its peak
        # is -- and where it does not, the task is named rather than silently
        # treated as if it fits.
        peak_context = task["system"].get("peak_context_tokens")
        if isinstance(peak_context, int | float) and peak_context > 0:
            context_enforced.append(task["id"])
            eligible = [
                candidate for candidate in eligible
                if candidate["max_context_tokens"] is None
                or float(candidate["max_context_tokens"]) >= float(peak_context)
            ]
        else:
            context_undeclared.append(task["id"])

        if not eligible:
            reason = f"no {target_currency} model reaches tier '{floor}'"
            if isinstance(peak_context, int | float) and peak_context > 0:
                widest = max((c["max_context_tokens"] or 0) for c in pool if
                             order.index(c["tier"]) >= order.index(floor)) if pool else 0
                if widest and widest < float(peak_context):
                    reason = (
                        f"peak context {int(peak_context):,} tokens exceeds the widest eligible "
                        f"{target_currency} window ({int(widest):,})"
                    )
            unroutable.append({
                "task_id": task["id"],
                "required_tier": floor,
                "peak_context_tokens": peak_context,
                "reason": reason,
            })
            continue

        priced = sorted(((c, _task_cost(totals, c["rates"])) for c in eligible), key=lambda pair: pair[1])
        chosen, chosen_cost = priced[0]
        baseline_cost = _task_cost(totals, baseline_model["rates"])
        optimized_total += chosen_cost
        baseline_total += baseline_cost
        assignments.append({
            "task_id": task["id"],
            "name": task.get("name", task["id"]),
            "category": task.get("category"),
            "complexity": task.get("complexity"),
            "required_tier": floor,
            "assigned_model": chosen["model_id"],
            "assigned_tier": chosen["tier"],
            "estimated_cost": round(chosen_cost, 4),
            "frontier_baseline_cost": round(baseline_cost, 4),
            "saving": round(baseline_cost - chosen_cost, 4),
        })

    tier_counts: dict[str, int] = {}
    for assignment in assignments:
        tier_counts[assignment["assigned_tier"]] = tier_counts.get(assignment["assigned_tier"], 0) + 1

    illustrative = any(c["not_for_billing"] for c in pool)
    return {
        "schema_version": "1.0.0",
        "artifact": "model-routing-plan",
        "currency": target_currency,
        "optimised_within_currency_only": True,
        "baseline_model": baseline_model["model_id"],
        "assignments": assignments,
        "unroutable_tasks": unroutable,
        "tier_distribution": dict(sorted(tier_counts.items())),
        "context_constraint": {
            "enforced_for": sorted(context_enforced),
            "not_declared_for": sorted(context_undeclared),
            "rule": (
                "A model is only eligible when its max_context_tokens covers the task's declared "
                "peak_context_tokens. Tasks that declare no peak are listed here rather than being "
                "assumed to fit."
            ),
        },
        "totals": {
            "optimized": round(optimized_total, 4),
            "frontier_baseline": round(baseline_total, 4),
            "saving": round(baseline_total - optimized_total, 4),
            "saving_ratio": round(
                (baseline_total - optimized_total) / baseline_total, 5) if baseline_total else None,
        },
        "rates_are_illustrative": illustrative,
        "caveats": [
            "Routing assumes the cheaper tier actually completes the task; if it fails and escalates, "
            "the retry cost eats the saving. Verify escalation rate before trusting the number.",
            "Costs use point token estimates (P50-equivalent), not the full distribution.",
        ]
        + ([f"{len(context_undeclared)} task(s) declare no peak_context_tokens, so the context window "
            "constraint could not be checked for them."] if context_undeclared else [])
        + (["Every rate in this plan is illustrative and must not back a budget."] if illustrative else []),
    }


def render_routing_comparison(plan: dict[str, Any]) -> str:
    rows = [
        [a["task_id"], a["complexity"], a["required_tier"], a["assigned_model"],
         fmt(a["estimated_cost"], 4), fmt(a["frontier_baseline_cost"], 4), fmt(a["saving"], 4)]
        for a in plan["assignments"]
    ]
    totals = plan["totals"]
    body = [
        "# MODEL_ROUTING_COMPARISON",
        "",
        f"- 币种：`{plan['currency']}`（只在同一币种内优化）",
        f"- 全 frontier 基线模型：`{plan['baseline_model']}`",
        f"- 分层分布：{plan['tier_distribution']}",
        "",
        "## 总量",
        "",
        markdown_table(
            ["方案", "费用"],
            [["全 frontier 基线", fmt(totals["frontier_baseline"], 4)],
             ["能力约束下的最优路由", fmt(totals["optimized"], 4)],
             ["节省", f"{fmt(totals['saving'], 4)}"
                     f"（{fmt((totals['saving_ratio'] or 0) * 100, 1)}%）"]]),
        "",
        "## 每个任务的路由",
        "",
        markdown_table(
            ["任务", "复杂度", "能力下限", "分配模型", "费用", "frontier 基线", "节省"], rows),
        "",
    ]
    context = plan.get("context_constraint", {})
    body += [
        "## 上下文窗口约束",
        "",
        f"- 已强制：{len(context.get('enforced_for', []))} 个任务",
        f"- 未声明 `peak_context_tokens`、无法检查：{len(context.get('not_declared_for', []))} 个任务",
        "",
        f"> {context.get('rule', '')}",
        "",
    ]
    if plan["unroutable_tasks"]:
        body += [
            "## 无法路由的任务",
            "",
            markdown_table(["任务", "需要层级", "峰值上下文", "原因"],
                           [[u["task_id"], u["required_tier"],
                             fmt(u.get("peak_context_tokens")), u["reason"]]
                            for u in plan["unroutable_tasks"]]),
            "",
            "> 无法路由不是可以忽略的告警：这些任务没有可用模型，计划不完整。",
            "",
        ]
    body += ["## 注意"] + [""] + [f"- {caveat}" for caveat in plan["caveats"]]
    return "\n".join(body)
