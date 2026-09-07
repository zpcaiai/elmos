#!/usr/bin/env python3
"""定价可行性的边界分析：在**不知道**内部用量的前提下，能算出什么。

`unit_economics.py` 需要 16 个成本输入，其中 8 个只能从自己系统里实测
（token 结构、Runner 单位成本、人均产物体积、出网量、支持成本、使用率）。
那 8 个今天拿不到，于是 `costValidationStatus` 卡在 `NOT_RUN`。

但有一件事**不需要**那 8 个输入就能算：

    给定标价与额度，扣掉税和支付通道费之后，
    每个套餐还剩多少钱可以花在成本上？
    其中 token 要吃掉多少？剩下的够不够付 Runner + 存储 + 出网 + 支持？

这不是毛利，是**毛利的上界**。上界为负 → 这个价格无论如何都亏，
不用等实测。上界为正 → 还不能下结论，但至少知道离红线多远，
以及**哪个变量最要命**。

本工具同样不发明任何单价：模型价格是外部公开报价，必须由 `--prices` 传入，
带 `source` 与 `checkedOn` 字段；没有来源的价格会被拒绝。

用法：
    python3 break_even_token_price.py --catalog <目录json> --prices <价格json>

退出码：0 分析完成；2 输入非法；3 缺少必要输入（NOT_RUN）。
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")


def yuan(fen: Decimal) -> str:
    return f"{(fen / 100).quantize(CENT, ROUND_HALF_UP)}"


def q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), ROUND_HALF_UP)


class Blocked(Exception):
    """缺少必要输入，无法给出结论。"""


def load_prices(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for field in ("fxUsdToCny", "models", "checkedOn"):
        if field not in raw:
            raise Blocked(f"价格文件缺少 {field}")
    if not raw["models"]:
        raise Blocked("价格文件里没有任何模型")
    for name, model in raw["models"].items():
        for field in ("inputPerMillionUsd", "outputPerMillionUsd", "source"):
            if field not in model:
                raise Blocked(f"模型 {name} 缺少 {field}")
        # 没有来源的价格不接受：这类数字最容易被"我记得大概是"污染
        if not str(model["source"]).startswith("http"):
            raise Blocked(f"模型 {name} 的 source 必须是可核对的 URL")
    return raw


def analyse(catalog: dict, prices: dict, tax_rate: Decimal, payment_rate: Decimal,
            tax_inclusive: bool) -> None:
    fx = Decimal(str(prices["fxUsdToCny"]))

    print("=" * 78)
    print("定价可行性边界分析")
    print("=" * 78)
    print(f"目录版本      {catalog['catalogVersion']}   币种 {catalog['currency']}")
    print(f"标价含税      {'是' if tax_inclusive else '否'}"
          f"   （目录 taxPresentation = {catalog['taxPresentation']}）")
    if catalog["taxPresentation"] == "UNSPECIFIED":
        print()
        print("  ⚠ 目录没有声明标价是否含税。这不是文档问题：")
        print("    含税与不含税之间差 6%，而下面算出来的 token 余量本身就在")
        print("    数倍的量级上博弈——6% 不至于翻盘，但它会直接改变'离红线多远'。")
        print("    发布目录前必须把 taxPresentation 定下来。")
    print(f"增值税率      {tax_rate}   支付通道费率 {payment_rate}")
    print(f"汇率          1 USD = {fx} CNY   （{prices['checkedOn']}）")
    print()

    # ---------------------------------------------------------------- 模型单价
    print("-" * 78)
    print("一、外部公开报价（可核对，非估算）")
    print("-" * 78)
    blended_rows = []
    for name, model in prices["models"].items():
        in_usd = Decimal(str(model["inputPerMillionUsd"]))
        out_usd = Decimal(str(model["outputPerMillionUsd"]))
        print(f"  {name}")
        print(f"    输入 ${in_usd}/M   输出 ${out_usd}/M   来源 {model['source']}")
        blended_rows.append((name, in_usd, out_usd))
    print()

    # ---------------------------------------------------------------- 净收入
    print("-" * 78)
    print("二、每个付费套餐每月的净收入（扣税与通道费后）")
    print("-" * 78)
    plans = []
    for plan in catalog["plans"]:
        if plan["priceFen"] == 0:
            continue
        price_fen = Decimal(plan["priceFen"])
        months = Decimal(plan["termDays"]) / Decimal("30.44")  # 平均月长
        gross_month = price_fen / months
        net = gross_month / (1 + tax_rate) if tax_inclusive else gross_month
        net = net * (1 - payment_rate)
        plans.append((plan, net))
        print(f"  {plan['planId']}")
        print(f"    标价 ¥{yuan(price_fen)} / {plan['termDays']} 天"
              f"  ≈ ¥{yuan(gross_month)}/月")
        print(f"    扣税与通道费后 ≈ ¥{yuan(net)}/月"
              f"   额度 {plan['tokens']:,} token + {plan['credits']} Credit")
    print()

    # ---------------------------------------------------------------- token 成本
    print("-" * 78)
    print("三、token 要吃掉多少（按输出占比与使用率扫描）")
    print("-" * 78)
    print("  说明：额度是一个笼统的 token 数，但输入与输出单价差 2–3 倍，")
    print("        所以'输出占比'是这张表里最敏感的变量，必须实测。")
    print()

    worst = []
    for plan, net in plans:
        tokens_million = Decimal(plan["tokens"]) / Decimal(1_000_000)
        print(f"  【{plan['planId']}】净收入 ¥{yuan(net)}/月，额度 "
              f"{tokens_million}M token")
        header = "    输出占比 |" + "".join(
            f" {name[:16]:>16} |" for name, _, _ in blended_rows)
        print(header)
        print("    " + "-" * (len(header) - 4))
        for out_share in (Decimal("0.1"), Decimal("0.3"), Decimal("0.5")):
            cells = []
            for name, in_usd, out_usd in blended_rows:
                blended_usd = in_usd * (1 - out_share) + out_usd * out_share
                cost_fen = blended_usd * fx * tokens_million * 100
                remaining = net - cost_fen
                cells.append(f" {'¥' + yuan(remaining):>16} |")
                if remaining < 0:
                    worst.append((plan["planId"], name, out_share, remaining))
            print(f"    {out_share:>8} |" + "".join(cells))
        print("      ↑ 表内数字 = 100% 用满额度时，付完 token 后**还剩多少钱**"
              "可以花在\n        Runner / 存储 / 出网 / 人工支持 / 退款 / 坏账上。")
        print()
        # 把余量换算成"每分钟 Runner 机时的可承受上界"。
        # 这一步不引入任何新假设：Credit 与机时的换算写在目录里
        # （isolated-runner-minute = 1 Credit），余量除以分钟数就是上界。
        # 它的价值在于把一个抽象的"还剩多少钱"变成一个**能去云厂商价格页
        # 直接比对**的数字。
        minutes = Decimal(plan["credits"])
        print(f"      换算：若这些 Credit 全部用于隔离机时（{minutes} 分钟/月），")
        print("            则每分钟机时的可承受成本上界为：")
        for out_share in (Decimal("0.3"),):
            for name, in_usd, out_usd in blended_rows:
                blended_usd = in_usd * (1 - out_share) + out_usd * out_share
                cost_fen = blended_usd * fx * tokens_million * 100
                remaining = net - cost_fen
                ceiling = remaining / minutes
                verdict = "已为负，不可行" if ceiling <= 0 else f"≤ ¥{q4(ceiling / 100)}/分钟"
                print(f"              {name:<20} {verdict}")
        print("            （输出占比按 0.3 计；这是**上界**，还没扣存储、"
              "出网与支持）")
        print()

    # ---------------------------------------------------------------- Credit
    print("-" * 78)
    print("四、Credit 额度换算成什么")
    print("-" * 78)
    rates = {r["operationKey"]: Decimal(r["credits"]) for r in catalog["creditRates"]}
    for plan, _ in plans:
        credits = Decimal(plan["credits"])
        print(f"  {plan['planId']}：{credits} Credit/月 相当于其中之一")
        for key, cost in sorted(rates.items(), key=lambda kv: kv[1]):
            print(f"    {credits / cost:>8.0f} × {key}（{cost} Credit）")
        print()
    print("  Runner 机时是这里唯一直接对应真实账单的项。"
          "isolated-runner-minute = 1 Credit，")
    print("  所以最坏情况下一个月付套餐可以换 "
          f"{plans[0][0]['credits']} 分钟隔离机时。")
    print("  该值乘以你的实例单价，就是 runnerCostPerCreditFen 的下界——"
          "这一项**可以今天就算出来**，")
    print("  只要确定用哪种机型。")
    print()

    # ---------------------------------------------------------------- 结论
    print("=" * 78)
    print("结论")
    print("=" * 78)
    if worst:
        print("  以下组合在 100% 使用率下，**光 token 成本就超过净收入**：")
        for plan_id, model, share, remaining in worst:
            print(f"    {plan_id} × {model} × 输出占比 {share} "
                  f"→ 缺口 ¥{yuan(-remaining)}/月")
        print()
        print("  这些组合不需要等实测就可以排除。")
    else:
        print("  在所列模型与输出占比范围内，token 成本均未超过净收入。")
        print("  但这**不等于盈利**——表中余量还要覆盖 Runner、存储、出网、"
              "支持与坏账。")
    print()
    print("  仍然 NOT_RUN 的：真实输出占比、缓存命中率、实际使用率、")
    print("  Runner 单位成本、人均产物体积与出网量、人工支持成本。")
    print("  在它们落地之前，costValidationStatus 必须保持 NOT_RUN，")
    print("  目录必须保持 DRAFT。")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--tax-rate", default="0.06",
                        help="增值税率。一般纳税人现代服务 0.06；"
                             "小规模纳税人 2026–2027 减按 0.01")
    parser.add_argument("--payment-rate", default="0.006",
                        help="支付通道费率")
    parser.add_argument("--tax-exclusive", action="store_true",
                        help="标价不含税（默认按含税处理，符合大陆 B2C 惯例）")
    arguments = parser.parse_args()

    try:
        catalog = json.loads(arguments.catalog.read_text(encoding="utf-8"))
        prices = load_prices(arguments.prices)
    except Blocked as blocked:
        print(f"NOT_RUN: {blocked}")
        return 3
    except (OSError, json.JSONDecodeError) as error:
        print(f"输入无法读取: {error}")
        return 2

    analyse(catalog, prices,
            Decimal(arguments.tax_rate), Decimal(arguments.payment_rate),
            tax_inclusive=not arguments.tax_exclusive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
