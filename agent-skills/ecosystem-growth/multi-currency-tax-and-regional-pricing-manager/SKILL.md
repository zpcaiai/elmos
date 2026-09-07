---
name: multi-currency-tax-and-regional-pricing-manager
description: "Execute authoritative Batch 14 Skill 449 for multi currency tax and regional pricing manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Multi Currency Tax And Regional Pricing Manager

## Operating contract

Apply authoritative Batch 14 Skill 449. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

支持区域价格、币种、税务、发票和购买力差异。

## Pricing Layers

```text id="48e8ah"
Global List Price
Regional List Price
Currency Conversion
Purchasing Power Adjustment
Channel Margin
Tax
Contract Override
```

## Price Record

```yaml id="iz8pqq"
regional_price:
  sku: enterprise-platform
  region: japan
  currency: JPY
  amount: number
  valid_from: string
```

## Tax

需支持：

* VAT；
  -GST；
  -Sales Tax；
  -Withholding；
  -Tax-exempt；
  -本地发票；
  -企业税号；
  -反向收费；
  -电子发票。

## Hard Rules

* 币种不能在账单后自动改；
* 汇率变化规则需明确；
* 区域价格不能引发套利而无策略；
* 税务由专业系统或服务处理；
* Partner Margin进入地区价格；
* 已签Quote锁定价格版本；
* 本地支付费用进入毛利。

## Acceptance Criteria

* 客户可用本地币种购买；
* 税额正确；
* 发票符合地区要求；
* 地区价格可审计；
* Partner报价一致；
* 区域毛利可计算。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

