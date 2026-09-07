---
name: channel-attribution-and-incrementality-manager
description: "Execute authoritative Batch 14 Skill 415 for channel attribution and incrementality manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Channel Attribution And Incrementality Manager

## Operating contract

Apply authoritative Batch 14 Skill 415. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

估计内容、广告、伙伴、社区和产品渠道对Pipeline及Revenue的真实贡献。

## Attribution Models

```text id="8twmqb"
First Touch
Last Touch
Linear
Position Based
Time Decay
Account Based
Experiment Based Incrementality
```

## Enterprise Attribution

需要考虑：

* 多联系人；
  -多月周期；
  -内容多次接触；
  -Partner；
  -销售活动；
  -POC；
  -活动；
  -产品自助使用。

## Attribution Record

```yaml id="88rg5s"
touch:
  account_id: string
  contact_id: string
  channel: technical-content
  asset_id: string
  occurred_at: string
```

## Hard Rules

* Last-touch不能作为唯一真值；
* Direct流量需识别已有品牌影响；
* Partner和直销贡献需按规则分配；
* Bot流量排除；
* Cookie限制下使用合法方法；
* 增量实验优先于纯归因模型；
* 收入归因需避免重复计算。

## Acceptance Criteria

* 主要渠道可比较；
* 内容可关联Account和Pipeline；
* Partner贡献可识别；
* 渠道CAC和Revenue可计算；
* 归因不重复；
* 投资决策有依据。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

