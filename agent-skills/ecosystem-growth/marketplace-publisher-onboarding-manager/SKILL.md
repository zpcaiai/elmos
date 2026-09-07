---
name: marketplace-publisher-onboarding-manager
description: "Execute authoritative Batch 14 Skill 437 for marketplace publisher onboarding manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Marketplace Publisher Onboarding Manager

## Operating contract

Apply authoritative Batch 14 Skill 437. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

帮助Vendor、Partner、客户和社区开发者成为Marketplace发布者。

## Publisher Types

```text id="wxsnx0"
Vendor
Certified Partner
Enterprise Customer
Independent Developer
Open Source Maintainer
Internal Private Publisher
```

## Onboarding

* 身份验证；
  -协议；
  -税务；
  -付款；
  -License；
  -安全培训；
  -开发文档；
  -Sandbox；
  -发布权限；
  -支持责任。

## Publisher Profile

```yaml id="t9wqrh"
publisher:
  publisher_id: string
  verification: certified-partner
  regions: []
  support_contact: string
  payout_account: string
```

## Hard Rules

* 匿名发布者不能发布高风险可执行资产；
* 收款Publisher需完成财务验证；
* 客户私有Publisher默认不可公开；
* Publisher需接受内容和安全政策；
* 支持责任必须明确；
* 被暂停Publisher不能更新或新发资产；
* Publisher退出需处理已安装资产。

## Acceptance Criteria

* 发布者身份可信；
* 财务和License信息完整；
* 能使用Sandbox测试；
* 发布权限符合级别；
* 支持和更新责任明确；
* Onboarding转化可衡量。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

