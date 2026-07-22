---
name: acquisition-channel-architecture-manager
description: "Execute authoritative Batch 14 Skill 404 for acquisition channel architecture manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Acquisition Channel Architecture Manager

## Operating contract

Apply authoritative Batch 14 Skill 404. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

设计、评估和治理Organic、Paid、Community、Partner和Product渠道。

## Channel Types

```text id="ct6y5q"
Organic Search
Technical Content
Open Source
GitHub
Developer Community
Events
Webinars
Analyst
PR
Paid Search
Paid Social
Outbound
Referral
Partner
Cloud Marketplace
Marketplace Internal
```

## Channel Record

```yaml id="palzsr"
channel:
  channel_id: organic-technical
  target_persona: migration-architect
  target_region: global
  cost_model: content-investment
  expected_outcome: qualified-assessment
```

## Channel Quality

不能只衡量：

* 点击；
  -访问；
  -注册。

还需衡量：

* Repository连接；
  -Assessment完成；
  -POC；
  -赢单；
  -毛利；
  -Retention；
  -Expansion。

## Hard Rules

* Paid渠道需有CAC上限；
* 低质量Lead不能被算作成功；
* Brand和Direct不能全部归给最后点击；
* Partner渠道需防重复归因；
* 每个渠道需有停止条件；
* 区域渠道需按本地采购行为调整；
* 渠道内容必须符合产品真实能力。

## Acceptance Criteria

* 每个渠道有目标Persona；
* 渠道质量可比较；
* CAC和转化可查询；
* 渠道归因不重复；
* 低效渠道及时优化；
* 渠道可与销售和产品数据关联。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

