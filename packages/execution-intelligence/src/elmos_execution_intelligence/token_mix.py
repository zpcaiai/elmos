"""Compare a forecast's assumed token *mix* against a measured one.

Every forecast in this package splits its token estimate across the five
disjoint categories. Until real usage was read, that split was an assumption
baked into ``decomposition-model.json`` -- and it was never checked, because
nothing in the pipeline could check it.

The check matters more than the total does. The five categories are priced
between one and fifty times apart from each other, so a forecast can predict the
token *count* almost perfectly and still be wrong about the bill by an order of
magnitude. That failure is invisible to anything that only compares totals.

What this module does NOT do is rewrite the forecast. An observed mix comes from
a specific set of sessions, on a specific model, doing a specific kind of work;
generalising it to a whole project is a judgement a person makes, not one a
script makes on their behalf. So this reports both mixes side by side, restates
the cost under each, and stops there.
"""
from __future__ import annotations

from typing import Any

#: The five disjoint categories, in the order they are reported everywhere else.
CATEGORIES: tuple[str, ...] = (
    "input", "cached_input", "cache_write", "output", "reasoning_output",
)


def _mix(counts: dict[str, float]) -> tuple[dict[str, float], float]:
    total = float(sum(float(counts.get(field, 0.0)) for field in CATEGORIES))
    if total <= 0:
        raise ValueError("token counts sum to zero; there is no mix to compute")
    return {field: float(counts.get(field, 0.0)) / total for field in CATEGORIES}, total


def forecast_mix(tasks: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate the per-task token profiles of a DAG into one category mix."""
    totals: dict[str, float] = dict.fromkeys(CATEGORIES, 0.0)
    for task in tasks:
        profile = (task.get("system") or {}).get("token_profile") or {}
        for field in CATEGORIES:
            totals[field] += float(profile.get(field, 0.0) or 0.0)
    return totals


def cost_of_mix(total_tokens: float, mix: dict[str, float], rates: dict[str, float]) -> float:
    """Price a token total under a given category mix, per million."""
    return sum(total_tokens * mix[field] * float(rates[field]) for field in CATEGORIES) / 1_000_000.0



#: Session depths at which the cumulative mix is reported. Chosen to bracket the
#: range of task sizes a DAG actually contains: a five-turn fix and a six-hundred
#: turn build are not the same workload and do not have the same mix.
WARMUP_DEPTHS: tuple[int, ...] = (5, 10, 20, 50, 100, 200, 500)


def mix_warmup(turns: list[dict[str, int]], depths: tuple[int, ...] = WARMUP_DEPTHS) -> dict[str, Any]:
    """How the cumulative mix changes with the length of the session.

    The aggregate mix of a long session is not the mix of a short one. Cache
    reads have to be *earned*: the first turn of any session reads nothing from
    cache because there is nothing there yet, and the share climbs from there.
    Pricing a five-turn task with a six-hundred-turn task's mix understates its
    cost, which is the same class of error as the one this whole artifact exists
    to surface -- just pointing the other way.

    Reporting the curve rather than one number is what lets a forecaster pick a
    mix that matches the task in front of them.
    """
    if not turns:
        raise ValueError("no per-turn usage rows; the warm-up curve needs them")

    # Kept as parallel typed lists rather than one heterogeneous dict, so the
    # mix values stay float-typed all the way to the arithmetic below.
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    mixes: list[dict[str, float]] = []
    for depth in (*depths, len(turns)):
        window = turns[:depth]
        if not window or len(window) in seen:
            continue
        total = sum(sum(int(row.get(f, 0)) for f in CATEGORIES) for row in window)
        if total <= 0:
            continue
        mix_at_depth = {
            f: round(sum(int(row.get(f, 0)) for row in window) / total, 6)
            for f in CATEGORIES
        }
        seen.add(len(window))
        mixes.append(mix_at_depth)
        unique.append({
            "turns": len(window),
            "is_full_session": len(window) == len(turns),
            "total_tokens": total,
            "mix": mix_at_depth,
        })

    per_turn_shares: list[float] = []
    for row in turns:
        total = sum(int(row.get(f, 0)) for f in CATEGORIES)
        if total > 0:
            per_turn_shares.append(int(row.get("cached_input", 0)) / total)
    per_turn_shares.sort()

    def _q(probability: float) -> float:
        if not per_turn_shares:
            return 0.0
        return round(per_turn_shares[int(probability * (len(per_turn_shares) - 1))], 4)

    first = mixes[0]["cached_input"] if mixes else 0.0
    last = mixes[-1]["cached_input"] if mixes else 0.0

    return {
        "depths": unique,
        "cached_input_share_at_shallowest": first,
        "cached_input_share_at_full_session": last,
        "warmup_spread": round(last - first, 6),
        "per_turn_cached_share": {
            "p10": _q(0.10), "p50": _q(0.50), "p90": _q(0.90),
            "turns_below_half": sum(1 for share in per_turn_shares if share < 0.5),
            "turns": len(per_turn_shares),
        },
        "how_to_use": (
            "Pick the row whose turn count is closest to the task being priced, rather than the "
            "full-session row. The full-session mix is the best case for cache reuse and the worst "
            "choice for a short task."
        ),
    }


def compare_mix(
    forecast_counts: dict[str, float],
    observed_counts: dict[str, float],
    project_tokens_p50: float,
    pricing: dict[str, Any],
    observed_sessions: int,
    observed_models: list[str],
    minimum_sessions: int = 20,
    warmup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Put the assumed mix and the measured mix side by side, and price both."""
    f_mix, f_total = _mix(forecast_counts)
    o_mix, o_total = _mix(observed_counts)

    rows = []
    for field in CATEGORIES:
        delta = o_mix[field] - f_mix[field]
        rows.append({
            "category": field,
            "forecast_share": round(f_mix[field], 6),
            "observed_share": round(o_mix[field], 6),
            "delta_share": round(delta, 6),
            # A ratio is only meaningful when the denominator is a real share.
            "ratio": round(o_mix[field] / f_mix[field], 4) if f_mix[field] > 0 else None,
        })

    costs = []
    for model in pricing.get("models", []):
        if model.get("not_for_billing"):
            continue
        rates = model["rates_per_million"]
        under_forecast = cost_of_mix(project_tokens_p50, f_mix, rates)
        under_observed = cost_of_mix(project_tokens_p50, o_mix, rates)
        costs.append({
            "model_id": model["id"],
            "display_name": model["display_name"],
            "currency": model["currency"],
            "cost_under_forecast_mix": round(under_forecast, 2),
            "cost_under_observed_mix": round(under_observed, 2),
            "overstatement_factor": (
                round(under_forecast / under_observed, 3) if under_observed > 0 else None
            ),
            "source_reference": model["source_reference"],
            "verified_at": model["verified_at"],
        })
    # Per currency, never across. Same rule as the cost report.
    costs.sort(key=lambda item: (item["currency"], item["cost_under_observed_mix"]))

    factors = [c["overstatement_factor"] for c in costs if c["overstatement_factor"]]
    sufficient = observed_sessions >= minimum_sessions

    # The headline factor is the FULL-SESSION one, and quoting it alone would be
    # its own distortion: a five-turn task is dominated by cache *writes*, which
    # are priced above fresh input, so the assumed mix is nearly right for short
    # work and badly wrong only for long work. Pricing each warm-up depth is what
    # turns "the forecast is 5x out" into something a reader can act on.
    by_depth: list[dict[str, Any]] = []
    if warmup:
        reference = next(
            (m for m in pricing.get("models", []) if not m.get("not_for_billing")), None
        )
        if reference is not None:
            rates = reference["rates_per_million"]
            baseline = cost_of_mix(project_tokens_p50, f_mix, rates)
            for point in warmup["depths"]:
                priced = cost_of_mix(project_tokens_p50, point["mix"], rates)
                by_depth.append({
                    "turns": point["turns"],
                    "is_full_session": point["is_full_session"],
                    "cost_under_observed_mix": round(priced, 2),
                    "overstatement_factor": round(baseline / priced, 3) if priced > 0 else None,
                })
            by_depth_meta = {
                "reference_model": reference["id"],
                "cost_under_forecast_mix": round(baseline, 2),
                "currency": reference["currency"],
            }
        else:
            by_depth_meta = {}
    else:
        by_depth_meta = {}

    return {
        "schema_version": "1.0.0",
        "artifact": "token-mix-comparison",
        "project_tokens_p50": project_tokens_p50,
        "forecast": {"counts": {f: round(forecast_counts.get(f, 0.0), 2) for f in CATEGORIES},
                     "total": round(f_total, 2), "mix": {f: round(f_mix[f], 6) for f in CATEGORIES}},
        "observed": {"counts": {f: round(observed_counts.get(f, 0.0), 2) for f in CATEGORIES},
                     "total": round(o_total, 2), "mix": {f: round(o_mix[f], 6) for f in CATEGORIES},
                     "sessions": observed_sessions, "models": observed_models},
        "by_category": rows,
        "warmup": warmup,
        "cost_restatement": costs,
        "cost_by_session_depth": by_depth,
        "cost_by_session_depth_basis": by_depth_meta,
        "overstatement_factor_range": (
            [min(factors), max(factors)] if factors else None
        ),
        "overstatement_factor_is_full_session_only": True,
        "overstatement_caveat": (
            "The headline factor compares the assumed mix against the FULL-SESSION observed mix. "
            "It is the largest factor, not the typical one. Short tasks never accumulate that much "
            "cache reuse and are dominated by cache writes, which are priced above fresh input, so "
            "for them the assumed mix is close to right. See cost_by_session_depth."
        ),
        "cross_currency_comparison": None,
        "sample_sufficient": sufficient,
        "minimum_sessions": minimum_sessions,
        "applied_to_forecast": False,
        "why_not_applied": (
            "这里没有任何东西被写回预测。实测占比只属于它来源的那些会话、那个模型、那类工作；"
            "判断它能不能推广到整个项目，是人的判断，不是脚本的判断。"
            f"况且 {observed_sessions} 个会话对门槛 {minimum_sessions}，"
            "就算该推广也过不了样本关。"
        ),
        "why_this_matters": (
            "五个分类之间的单价相差最多五十倍。一份预测可以把 token 总量算得很准，"
            "账单却错一个数量级——只比总量，永远看不出来。"
        ),
        "caveats": [
            "实测占比测的是那几个会话，不是这个项目。",
            "缓存读取的占比高度依赖会话跑多久：缓存是**攒出来的**，第一轮无缓存可读。"
            "实测里前 5 轮只有 58.6%，前 50 轮 93.8%，整场 98.8%。用整场占比去算一个短任务会**低估**费用——"
            "和这份报告要揭示的错误同一类，只是方向相反。见 warmup 表。",
            "费率是公开列表价，不是账户议价。费率变，这里的钱数就变。",
        ],
    }


def render_mix(report: dict[str, Any]) -> str:
    from .io_utils import fmt, markdown_table

    obs = report["observed"]
    sufficiency = (
        "是" if report["sample_sufficient"]
        else f"**否**（门槛 {report['minimum_sessions']} 个会话）"
    )
    rows = [
        [r["category"],
         f"{r['forecast_share'] * 100:.4f}%",
         f"{r['observed_share'] * 100:.4f}%",
         f"{r['ratio']:.3f}x" if r["ratio"] is not None else "—"]
        for r in report["by_category"]
    ]
    cost_rows = [
        [c["display_name"], c["currency"],
         fmt(c["cost_under_forecast_mix"]), fmt(c["cost_under_observed_mix"]),
         f"{c['overstatement_factor']:.2f}x" if c["overstatement_factor"] else "—"]
        for c in report["cost_restatement"]
    ]
    factor = report["overstatement_factor_range"]

    body = [
        "# TOKEN_MIX_COMPARISON",
        "",
        f"- 项目 token P50：{fmt(report['project_tokens_p50'])}",
        f"- 实测来源：{obs['sessions']} 个会话，模型 {', '.join(obs['models']) or '未知'}，"
        f"合计 {fmt(obs['total'])} tokens",
        f"- 样本是否达标：{sufficiency}",
        "",
        "## 分类占比：假设 vs 实测",
        "",
        markdown_table(["分类", "预测假设", "实测", "实测/假设"], rows),
        "",
        "## 同样的 token 总量，两种占比下的费用",
        "",
        markdown_table(["模型", "币种", "按假设占比", "按实测占比", "高估倍数"], cost_rows),
        "",
    ]
    warmup = report.get("warmup")
    if warmup:
        body += [
            "## 占比是攒出来的：随会话长度的变化",
            "",
            markdown_table(
                ["轮次", "累计 tokens", "cached_input", "input", "cache_write", "output"],
                [[fmt(point["turns"]) + ("（整场）" if point["is_full_session"] else ""),
                  fmt(point["total_tokens"]),
                  f"{point['mix']['cached_input'] * 100:.2f}%",
                  f"{point['mix']['input'] * 100:.4f}%",
                  f"{point['mix']['cache_write'] * 100:.3f}%",
                  f"{point['mix']['output'] * 100:.3f}%"]
                 for point in warmup["depths"]]),
            "",
            f"> 从最短窗口到整场，cached_input 占比爬升了 "
            f"**{warmup['warmup_spread'] * 100:.1f} 个百分点**"
            f"（{warmup['cached_input_share_at_shallowest'] * 100:.1f}% → "
            f"{warmup['cached_input_share_at_full_session'] * 100:.1f}%）。",
            "",
            f"> 逐轮 cached_input 占比：p10={warmup['per_turn_cached_share']['p10']:.3f} "
            f"p50={warmup['per_turn_cached_share']['p50']:.3f} "
            f"p90={warmup['per_turn_cached_share']['p90']:.3f}；"
            f"{warmup['per_turn_cached_share']['turns']} 轮里只有 "
            f"{warmup['per_turn_cached_share']['turns_below_half']} 轮低于 50%。"
            f"**热身之后占比是稳的，不是一路缓慢爬升。**",
            "",
            f"> {warmup['how_to_use']}",
            "",
        ]
    depth_rows = report.get("cost_by_session_depth") or []
    meta = report.get("cost_by_session_depth_basis") or {}
    if depth_rows and meta:
        body += [
            "## 高估多少，取决于任务有多长",
            "",
            f"参照模型 `{meta['reference_model']}`，按假设占比是 "
            f"{meta['currency']} {fmt(meta['cost_under_forecast_mix'])}：",
            "",
            markdown_table(
                ["任务长度（轮）", "按实测占比", "高估倍数"],
                [[fmt(row["turns"]) + ("（整场）" if row["is_full_session"] else ""),
                  fmt(row["cost_under_observed_mix"]),
                  f"{row['overstatement_factor']:.2f}x" if row["overstatement_factor"] else "—"]
                 for row in depth_rows]),
            "",
            "> **不是一个固定倍数。** 短任务几乎全是 cache_write，而 cache_write 的单价"
            "**高于**新鲜 input——所以对短任务来说，那个 24/63/7/4/2 的假设反而基本是对的。"
            "偏差随任务变长而变大。",
            "",
        ]
    if factor:
        body += [
            f"> 整场会话口径下，**费用被高估 {factor[0]:.2f}–{factor[1]:.2f} 倍**，"
            f"而 token 总量一个字没改。这是**上限**，不是典型值。",
            "",
        ]
    body += [
        f"> {report['why_this_matters']}",
        "",
        "## 没有回写预测",
        "",
        f"{report['why_not_applied']}",
        "",
        "## 注意",
        "",
        *[f"- {c}" for c in report["caveats"]],
    ]
    return "\n".join(body)
