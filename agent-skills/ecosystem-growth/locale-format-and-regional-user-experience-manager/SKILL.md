---
name: locale-format-and-regional-user-experience-manager
description: "Execute authoritative Batch 14 Skill 447 for locale format and regional user experience manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Locale Format And Regional User Experience Manager

## Operating contract

Apply authoritative Batch 14 Skill 447. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

适配日期、时间、数字、货币、姓名、地址、电话和区域工作方式。

## Locale Elements

```text id="u6p058"
Date
Time
Timezone
Number
Decimal
Currency
Percent
Name
Address
Phone
Postal Code
Tax ID
Paper Size
Week Start
Business Day
```

## Regional UX

还需考虑：

* 常用身份Provider；
  -Git平台；
  -支付方式；
  -采购流程；
  -合同语言；
  -支持时间；
  -沟通工具；
  -云Provider；
  -网络条件；
  -字体；
  -输入法；
  -本地技术术语。

## Hard Rules

* 数据库中核心时间使用明确Instant；
* 显示格式按Locale；
* 币种不能根据语言推断；
* 地址和姓名不能使用固定西式字段；
* 电话验证按地区；
* 本地工作日和节假日可配置；
* 地区体验不应改变权限和业务逻辑。

## Acceptance Criteria

* 格式符合地区习惯；
* 数据存储和显示分离；
* 多币种显示正确；
* 表单支持本地地址和姓名；
* 时区错误为0；
* 本地用户完成率提高。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

