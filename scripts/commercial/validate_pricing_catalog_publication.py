#!/usr/bin/env python3
"""Fail-closed publication gate for the ELMOS pricing catalog.

The catalog at ``contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json``
drives whether paid checkout is reachable. Flipping ``status`` to ``PUBLISHED``
is a commercial act: it asserts that a seller legal entity exists, tax treatment
is decided, a payment merchant is live, and unit economics have actually been
computed. This script refuses to let that assertion be made implicitly.

Two modes:

``verify`` (default)
    Assert the catalog is internally consistent and that, *if* it claims
    ``PUBLISHED``, every publication precondition is genuinely satisfied.
    Intended for CI on every change. Exit 0 pass, 1 violation, 2 bad input.

``--check-publishable``
    Additionally require that the catalog is publishable *right now*. Intended
    for the release gate. Exits 3 while any precondition is unmet, which is the
    expected state until the external commercial work is done.

Fail-closed rules honoured here (see docs/BUSINESS_LINE_CLOSURE_MATRIX.md):
``NOT_CONFIGURED``, ``NOT_RUN``, ``UNSPECIFIED``, missing fields and unknown
enum values are never treated as success. This script produces no evidence; it
only refuses to accept unsupported claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CATALOG = Path("contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json")

# Field -> (accepted value, human-readable meaning of the accepted value)
PUBLICATION_PRECONDITIONS: dict[str, tuple[str, str]] = {
    "sellerLegalEntityStatus": ("CONFIGURED", "卖方经营主体已确定"),
    "taxStatus": ("CONFIGURED", "税务处理已确定"),
    "paymentStatus": ("CONFIGURED", "支付商户已开通"),
    "costValidationStatus": ("VALIDATED", "单位经济性已核算"),
}

REJECTED_TAX_PRESENTATION = "UNSPECIFIED"

FREE_TRIAL_PLAN_ID = "elmos-free-trial"
REQUIRED_PLAN_IDS = {FREE_TRIAL_PLAN_ID, "elmos-pro-monthly", "elmos-pro-annual"}

# D-01（2026-07-28）选择了中国大陆主体 + 支付宝/微信支付。
# 目录 Schema 目前仍把 paymentProvider 写成 const STRIPE_CHECKOUT，扩为 enum 的影响面
# 见 docs/commercialization/PAYMENT_CN_ADAPTER_SPEC.md 第 5 节。本脚本先行支持，
# 以便 Schema 与 Java/TS 契约改造期间目录不会被悄悄发布。
KNOWN_PAYMENT_PROVIDERS = {
    "STRIPE_CHECKOUT",       # 已实现，D-01 后不启用
    "ALIPAY_CHECKOUT",       # 待实现
    "WECHAT_PAY_NATIVE",     # 待实现
}
CHINA_MAINLAND_PROVIDERS = {"ALIPAY_CHECKOUT", "WECHAT_PAY_NATIVE"}


class Violation(Exception):
    """Raised for input that cannot be evaluated at all."""


def _load(path: Path) -> dict:
    if not path.is_file():
        raise Violation(f"catalog not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Violation(f"catalog is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise Violation("catalog root must be a JSON object")
    return data


def _parse_instant(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise Violation(f"{field} is not an ISO-8601 instant: {value!r}") from error
    if parsed.tzinfo is None:
        raise Violation(f"{field} must carry a timezone offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def structural_findings(catalog: dict) -> list[str]:
    """Consistency checks that must hold regardless of publication status."""
    findings: list[str] = []

    status = catalog.get("status")
    if status not in {"DRAFT", "PUBLISHED", "SUPERSEDED"}:
        findings.append(f"status 非法：{status!r}")

    for field in ("catalogVersion", "currency", "authoritativeSource", "paymentProvider"):
        if not isinstance(catalog.get(field), str) or not catalog[field]:
            findings.append(f"{field} 缺失或为空")

    for field in ("tokenClasses", "creditRates", "limitations"):
        if not isinstance(catalog.get(field), list) or not catalog[field]:
            findings.append(f"{field} 缺失或不是非空数组")

    plans = catalog.get("plans")
    if not isinstance(plans, list) or len(plans) != 3:
        findings.append("plans 必须恰好包含 3 个套餐")
        return findings

    # 逐项确认是对象。畸形输入必须得到明确的 INVALID 判定，
    # 不能是一段栈回溯 —— 门禁脚本自己崩掉等于没有门禁。
    malformed = [index for index, plan in enumerate(plans) if not isinstance(plan, dict)]
    if malformed:
        findings.append(f"plans 中第 {malformed} 项不是对象")
        return findings

    plan_ids = {plan.get("planId") for plan in plans}
    if plan_ids != REQUIRED_PLAN_IDS:
        findings.append(f"套餐集合不符：{sorted(str(p) for p in plan_ids)}")

    for plan in plans:
        plan_id = plan.get("planId", "<unknown>")
        price = plan.get("priceFen")
        if not isinstance(price, int) or price < 0:
            findings.append(f"{plan_id}: priceFen 必须为非负整数")
            continue
        if plan_id == FREE_TRIAL_PLAN_ID:
            if price != 0:
                findings.append(f"{plan_id}: 免费体验的 priceFen 必须为 0")
            if plan.get("trialEligibilityPolicy") != "ONE_PER_VERIFIED_ORGANIZATION":
                findings.append(
                    f"{plan_id}: trialEligibilityPolicy 必须为 ONE_PER_VERIFIED_ORGANIZATION"
                )
        else:
            if price <= 0:
                findings.append(f"{plan_id}: 付费套餐的 priceFen 必须大于 0")
            if plan.get("trialEligibilityPolicy") != "NOT_APPLICABLE":
                findings.append(f"{plan_id}: 付费套餐的 trialEligibilityPolicy 必须为 NOT_APPLICABLE")
        for quota in ("tokens", "credits", "activeProjects", "concurrentJobs",
                      "artifactRetentionDays"):
            if not isinstance(plan.get(quota), int) or plan[quota] < 0:
                findings.append(f"{plan_id}: {quota} 缺失或非法")

    if catalog.get("overagePolicy") != "HARD_STOP_NO_AUTOMATIC_CHARGE":
        findings.append(
            "overagePolicy 必须保持 HARD_STOP_NO_AUTOMATIC_CHARGE："
            "超额自动扣费需要独立的商业与合规决策"
        )

    return findings


def publication_findings(catalog: dict, now: datetime, evidence: dict) -> list[str]:
    """Preconditions that must hold before the catalog may claim PUBLISHED.

    ``evidence`` carries external commercial facts that the catalog schema cannot
    hold (ICP filing, invoicing capability). Absent evidence is never success.
    """
    findings: list[str] = []
    _external_evidence = evidence

    for field, (accepted, meaning) in PUBLICATION_PRECONDITIONS.items():
        actual = catalog.get(field)
        if actual != accepted:
            findings.append(f"{field}={actual!r}（需要 {accepted!r}：{meaning}）")

    presentation = catalog.get("taxPresentation")
    if presentation == REJECTED_TAX_PRESENTATION or not presentation:
        findings.append(
            f"taxPresentation={presentation!r}（必须明确 TAX_INCLUSIVE 或 TAX_EXCLUSIVE，"
            "含税与否是对客户的价格承诺）"
        )

    provider = catalog.get("paymentProvider")
    if provider not in KNOWN_PAYMENT_PROVIDERS:
        findings.append(
            f"paymentProvider={provider!r} 不在已知集合 {sorted(KNOWN_PAYMENT_PROVIDERS)}"
        )
    elif provider in CHINA_MAINLAND_PROVIDERS:
        # 大陆经营的两项硬前置，二者都不在目录 Schema 内，因此要求显式外部证据文件
        if presentation not in (None, REJECTED_TAX_PRESENTATION) and presentation != "TAX_INCLUSIVE":
            findings.append(
                f"taxPresentation={presentation!r}：大陆 B2C 标价为含税价，"
                "使用支付宝/微信收单时应为 TAX_INCLUSIVE"
            )
        for key, label in (("icpFiling", "ICP 备案"), ("invoiceCapability", "增值税发票能力")):
            if key not in _external_evidence:
                findings.append(f"{label}证据缺失（--commercial-evidence 中的 {key}）")
    elif provider == "STRIPE_CHECKOUT" and catalog.get("currency") == "CNY":
        findings.append(
            "paymentProvider=STRIPE_CHECKOUT 与 currency=CNY 组合需要境外经营主体；"
            "D-01 已选择大陆主体，此组合应改为 ALIPAY_CHECKOUT 或 WECHAT_PAY_NATIVE"
        )

    effective_from = catalog.get("effectiveFrom")
    if not isinstance(effective_from, str):
        findings.append("effectiveFrom 缺失")
    else:
        starts = _parse_instant(effective_from, "effectiveFrom")
        if starts > now:
            findings.append(f"effectiveFrom 尚未生效：{effective_from}")

    effective_until = catalog.get("effectiveUntil")
    if effective_until is not None:
        if not isinstance(effective_until, str):
            findings.append("effectiveUntil 必须为 ISO-8601 字符串或 null")
        else:
            ends = _parse_instant(effective_until, "effectiveUntil")
            if ends <= now:
                findings.append(f"effectiveUntil 已过期：{effective_until}")

    return findings


def evaluate(catalog: dict, now: datetime, require_publishable: bool,
             evidence: dict | None = None) -> tuple[str, list[str], int]:
    """Return (decision, findings, exit_code)."""
    structural = structural_findings(catalog)
    if structural:
        return "INVALID", structural, 1

    status = catalog["status"]
    blockers = publication_findings(catalog, now, evidence or {})

    if status == "PUBLISHED":
        if blockers:
            return "PUBLISHED_WITHOUT_EVIDENCE", blockers, 1
        return "PUBLISHED_OK", [], 0

    if status == "SUPERSEDED":
        return "SUPERSEDED", [], 0

    # DRAFT
    if not blockers:
        return "READY_TO_PUBLISH", [], 0
    if require_publishable:
        return "PUBLICATION_BLOCKED", blockers, 3
    return "DRAFT_NOT_PUBLISHABLE", blockers, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG,
                        help=f"pricing catalog path (default: {DEFAULT_CATALOG})")
    parser.add_argument("--check-publishable", action="store_true",
                        help="release-gate mode: exit 3 while the catalog is not yet publishable")
    parser.add_argument("--now", type=str, default=None,
                        help="ISO-8601 instant to evaluate against (default: current UTC time)")
    parser.add_argument("--commercial-evidence", type=Path, default=None,
                        help="JSON file carrying external commercial facts the catalog schema "
                             "cannot hold (icpFiling, invoiceCapability). Required when the "
                             "payment provider is a China-mainland one.")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable decision")
    args = parser.parse_args(argv)

    try:
        catalog = _load(args.catalog)
        evidence = _load(args.commercial_evidence) if args.commercial_evidence else {}
        now = _parse_instant(args.now, "--now") if args.now else datetime.now(timezone.utc)
        decision, findings, code = evaluate(catalog, now, args.check_publishable, evidence)
    except Violation as error:
        if args.json:
            print(json.dumps({"decision": "INVALID_INPUT", "findings": [str(error)]},
                             ensure_ascii=False))
        else:
            print(f"DECISION=INVALID_INPUT\n  - {error}")
        return 2

    if args.json:
        print(json.dumps({
            "decision": decision,
            "catalogVersion": catalog.get("catalogVersion"),
            "status": catalog.get("status"),
            "findings": findings,
            "evidenceProduced": False,
        }, ensure_ascii=False, indent=2))
        return code

    print(f"DECISION={decision}")
    print(f"  catalogVersion={catalog.get('catalogVersion')} status={catalog.get('status')}")
    if findings:
        print("  未满足的前置条件：")
        for finding in findings:
            print(f"    - {finding}")
    if decision == "DRAFT_NOT_PUBLISHABLE":
        print("  说明：DRAFT 且前置条件未满足是预期状态，付费入口保持禁用。")
    if decision == "PUBLISHED_WITHOUT_EVIDENCE":
        print("  说明：目录声称已发布，但商业前置条件未闭合。这是必须阻断的状态。")
    return code


if __name__ == "__main__":
    sys.exit(main())
