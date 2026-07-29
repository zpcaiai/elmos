#!/usr/bin/env python3
"""ELMOS 单位经济性核算（关闭 costValidationStatus=NOT_RUN 的计算工具）

定价目录声明 ¥129/月含 2,000 万 token + 600 Credit，但 `costValidationStatus`
一直是 `NOT_RUN` —— 也就是**没人知道一单是赚是亏**。自助订阅意味着无法逐单审批，
定价上线后很难回调，所以这件事必须在开售前算清楚。

本工具**不发明任何单价**。所有成本输入必须由使用者提供真实报价；
任一必填输入缺失时输出 `BLOCKED` 而不是用"行业经验值"糊过去 ——
用假设算出来的毛利比不算更危险，因为它看起来像结论。

用法：
    python3 unit_economics.py --inputs my-costs.json --catalog <定价目录>
    python3 unit_economics.py --template > my-costs.json     # 生成待填模板

退出码：0 全部套餐贡献毛利为正；3 存在负毛利或输入不全；2 输入非法。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# 必填成本输入。值为 null 表示"尚未取得真实报价"，不得用默认值替代。
REQUIRED_INPUTS = {
    "modelInputPricePerMillionFen": "模型输入 token 单价（分 / 百万 token）",
    "modelOutputPricePerMillionFen": "模型输出 token 单价（分 / 百万 token）",
    "modelCacheReadPricePerMillionFen": "缓存读 token 单价（分 / 百万 token）",
    "modelCacheWritePricePerMillionFen": "缓存写 token 单价（分 / 百万 token）",
    "outputTokenShare": "输出 token 占总 token 的比例（0–1）",
    "cacheReadShare": "缓存读 token 占比（0–1）",
    "cacheWriteShare": "缓存写 token 占比（0–1）",
    "runnerCostPerCreditFen": "每个 Credit 对应的 Runner 机时成本（分）",
    "storageCostPerGbMonthFen": "对象存储单价（分 / GB·月）",
    "storageGbPerActiveProject": "每个活跃项目的平均产物体积（GB）",
    "egressCostPerGbFen": "出网单价（分 / GB）",
    "egressGbPerMonthPerAccount": "每账户月均下载量（GB）",
    "supportCostPerAccountMonthFen": "每账户月均人工支持成本（分）",
    "paymentFeeRate": "支付通道费率（0–1，支付宝/微信通常 0.006）",
    "taxRate": "适用税率（0–1；标价含税时用于倒算净收入）",
    "utilization": "额度实际使用率（0–1）。1.0 = 最坏情况，用满全部额度",
}

TEMPLATE = {key: None for key in REQUIRED_INPUTS}
TEMPLATE["_说明"] = (
    "所有字段必须填真实报价后才会输出毛利。任一为 null 则判定 BLOCKED。"
    "金额一律用分（整数或小数均可），比例用 0–1 之间的小数。"
)


class InputError(Exception):
    """输入无法评估。"""


def _d(value, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as error:  # noqa: BLE001
        raise InputError(f"{field} 不是数字：{value!r}") from error


def _fen(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _yuan(fen: Decimal) -> str:
    return f"¥{(fen / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def validate_inputs(raw: dict) -> tuple[dict, list[str]]:
    """返回 (已解析输入, 缺失项说明)。缺失项非空时不得计算毛利。"""
    missing: list[str] = []
    parsed: dict[str, Decimal] = {}
    for key, label in REQUIRED_INPUTS.items():
        if key not in raw or raw[key] is None:
            missing.append(f"{key}（{label}）")
            continue
        parsed[key] = _d(raw[key], key)

    if missing:
        return parsed, missing

    shares = (parsed["outputTokenShare"] + parsed["cacheReadShare"]
              + parsed["cacheWriteShare"])
    if shares > 1:
        missing.append(
            f"输出/缓存读/缓存写占比之和为 {shares}，超过 1；输入 token 占比会变成负数"
        )
    for key in ("outputTokenShare", "cacheReadShare", "cacheWriteShare",
                "paymentFeeRate", "taxRate", "utilization"):
        if not (Decimal(0) <= parsed[key] <= Decimal(1)):
            missing.append(f"{key} 必须在 0–1 之间，当前为 {parsed[key]}")
    return parsed, missing


def token_cost_fen(tokens: Decimal, cfg: dict) -> Decimal:
    """按四类 token 的占比加权计算成本。"""
    out_share = cfg["outputTokenShare"]
    cr_share = cfg["cacheReadShare"]
    cw_share = cfg["cacheWriteShare"]
    in_share = Decimal(1) - out_share - cr_share - cw_share
    per_million = (
        in_share * cfg["modelInputPricePerMillionFen"]
        + out_share * cfg["modelOutputPricePerMillionFen"]
        + cr_share * cfg["modelCacheReadPricePerMillionFen"]
        + cw_share * cfg["modelCacheWritePricePerMillionFen"]
    )
    return tokens / Decimal(1_000_000) * per_million


def evaluate_plan(plan: dict, cfg: dict) -> dict:
    """计算单个套餐的月度贡献毛利（分）。"""
    utilization = cfg["utilization"]

    # 收入：按月归一。年付按 12 个月摊，用目录自带的 effectiveMonthlyFen。
    gross_fen = _d(plan.get("effectiveMonthlyFen", 0), "effectiveMonthlyFen")

    # 含税标价需要倒算净收入
    net_fen = gross_fen / (Decimal(1) + cfg["taxRate"])
    payment_fee = gross_fen * cfg["paymentFeeRate"]

    tokens = _d(plan.get("tokens", 0), "tokens") * utilization
    credits = _d(plan.get("credits", 0), "credits") * utilization
    projects = _d(plan.get("activeProjects", 0), "activeProjects")
    retention_months = _d(plan.get("artifactRetentionDays", 0), "artifactRetentionDays") / 30

    model_cost = token_cost_fen(tokens, cfg)
    runner_cost = credits * cfg["runnerCostPerCreditFen"]
    storage_cost = (projects * cfg["storageGbPerActiveProject"]
                    * cfg["storageCostPerGbMonthFen"] * retention_months)
    egress_cost = cfg["egressGbPerMonthPerAccount"] * cfg["egressCostPerGbFen"]
    support_cost = cfg["supportCostPerAccountMonthFen"]

    total_cost = model_cost + runner_cost + storage_cost + egress_cost + support_cost
    margin = net_fen - payment_fee - total_cost
    margin_rate = (margin / net_fen) if net_fen > 0 else Decimal(0)

    return {
        "planId": plan.get("planId"),
        "grossRevenueFen": _fen(gross_fen),
        "netRevenueFen": _fen(net_fen),
        "costs": {
            "model": _fen(model_cost),
            "runner": _fen(runner_cost),
            "storage": _fen(storage_cost),
            "egress": _fen(egress_cost),
            "support": _fen(support_cost),
            "paymentFee": _fen(payment_fee),
        },
        "totalCostFen": _fen(total_cost + payment_fee),
        "contributionMarginFen": _fen(margin),
        "contributionMarginRate": float(margin_rate.quantize(Decimal("0.0001"))),
        "positive": margin > 0,
    }


def breakeven_utilization(plan: dict, cfg: dict) -> Decimal | None:
    """毛利归零时的额度使用率。高于 1 表示用满也不亏。"""
    low, high = Decimal(0), Decimal(4)
    probe = dict(cfg)
    probe["utilization"] = low
    if not evaluate_plan(plan, probe)["positive"]:
        return Decimal(0)          # 一分钱不用也亏（固定成本已经超过收入）
    probe["utilization"] = high
    if evaluate_plan(plan, probe)["positive"]:
        return None                # 4 倍额度仍不亏
    for _ in range(40):            # 二分，精度足够到小数点后 4 位
        mid = (low + high) / 2
        probe["utilization"] = mid
        if evaluate_plan(plan, probe)["positive"]:
            low = mid
        else:
            high = mid
    return low.quantize(Decimal("0.0001"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inputs", type=Path, help="成本输入 JSON")
    parser.add_argument("--catalog", type=Path,
                        default=Path("contracts/pricing-catalog-schema/"
                                     "elmos-cny-self-serve-v1.json"))
    parser.add_argument("--template", action="store_true", help="输出待填模板后退出")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    args = parser.parse_args(argv)

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return 0

    if not args.inputs:
        parser.error("需要 --inputs，或用 --template 先生成模板")

    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        raw = json.loads(args.inputs.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        print(f"DECISION=INVALID_INPUT\n  - 文件不存在：{error.filename}")
        return 2
    except json.JSONDecodeError as error:
        print(f"DECISION=INVALID_INPUT\n  - JSON 解析失败：{error}")
        return 2

    try:
        cfg, missing = validate_inputs(raw)
    except InputError as error:
        print(f"DECISION=INVALID_INPUT\n  - {error}")
        return 2

    if missing:
        payload = {"decision": "BLOCKED", "missing": missing,
                   "costValidationStatus": "NOT_RUN"}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("DECISION=BLOCKED")
            print("  以下输入尚未取得真实报价，拒绝输出毛利：")
            for item in missing:
                print(f"    - {item}")
            print("  说明：用假设值算出的毛利看起来像结论，比不算更危险。")
            print("        costValidationStatus 保持 NOT_RUN。")
        return 3

    paid = [p for p in catalog.get("plans", []) if p.get("priceFen", 0) > 0]
    trial = [p for p in catalog.get("plans", []) if p.get("priceFen", 0) == 0]

    results = [evaluate_plan(p, cfg) for p in paid]
    trial_costs = []
    for plan in trial:
        probe = evaluate_plan(plan, cfg)
        probe["note"] = "免费体验：这是获客成本，不是亏损"
        trial_costs.append(probe)

    all_positive = all(r["positive"] for r in results)

    if args.json:
        print(json.dumps({
            "decision": "MARGIN_POSITIVE" if all_positive else "MARGIN_NEGATIVE",
            "utilization": float(cfg["utilization"]),
            "paidPlans": results,
            "trialPlans": trial_costs,
            "breakeven": {
                p.get("planId"): (str(b) if (b := breakeven_utilization(p, cfg)) is not None
                                  else "never")
                for p in paid
            },
        }, ensure_ascii=False, indent=2, default=str))
        return 0 if all_positive else 3

    print(f"DECISION={'MARGIN_POSITIVE' if all_positive else 'MARGIN_NEGATIVE'}")
    print(f"  额度使用率假设 utilization={cfg['utilization']}"
          f"（1.0 = 用满全部额度，最坏情况）\n")
    for result in results + trial_costs:
        flag = "✓" if result["positive"] else "✗ 亏损"
        print(f"  {result['planId']}  {flag}")
        print(f"    月收入(含税) {_yuan(result['grossRevenueFen']):>10s}"
              f"   净收入 {_yuan(result['netRevenueFen']):>10s}")
        costs = result["costs"]
        print(f"    成本：模型 {_yuan(costs['model'])}  Runner {_yuan(costs['runner'])}"
              f"  存储 {_yuan(costs['storage'])}  出网 {_yuan(costs['egress'])}"
              f"  支持 {_yuan(costs['support'])}  通道费 {_yuan(costs['paymentFee'])}")
        print(f"    合计成本 {_yuan(result['totalCostFen'])}"
              f"   贡献毛利 {_yuan(result['contributionMarginFen'])}"
              f"（{result['contributionMarginRate']:.1%}）")
        if result.get("note"):
            print(f"    {result['note']}")
        print()

    print("  盈亏平衡使用率（超过此使用率即亏损）：")
    for plan in paid:
        point = breakeven_utilization(plan, cfg)
        if point is None:
            print(f"    {plan.get('planId')}: 用满 4 倍额度仍不亏")
        elif point == 0:
            print(f"    {plan.get('planId')}: 零使用即亏损（固定成本已超净收入）")
        else:
            print(f"    {plan.get('planId')}: {point}"
                  f"（约 {int(_d(plan.get('tokens', 0), 't') * point / 10000)} 万 token）")

    print("\n  本结果是计算，不是证据。把 costValidationStatus 改为 VALIDATED 之前，")
    print("  输入里的每个单价都必须能追溯到真实报价单或账单。")
    return 0 if all_positive else 3


if __name__ == "__main__":
    sys.exit(main())
