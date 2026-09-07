---
name: growth-event-and-semantic-analytics-layer
description: "Execute authoritative Batch 14 Skill 414 for growth event and semantic analytics layer. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Growth Event And Semantic Analytics Layer

## Operating contract

Apply authoritative Batch 14 Skill 414. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

定义统一产品、内容、社区、Marketplace和渠道事件。

## Event Schema

```yaml id="5e837w"
growth_event:
  event_id: string
  actor_id: string | null
  anonymous_id: string | null
  tenant_id: string | null

  event_name: assessment.completed
  properties: {}

  occurred_at: string
  source: web
  schema_version: integer
```

## Event Domains

```text id="yb720f"
website
content
product
developer-portal
community
marketplace
sales
partner
support
billing
```

## Identity Resolution

关联：

* Anonymous Visitor；
  -Developer Account；
  -Enterprise User；
  -CRM Contact；
  -Workspace；
  -Tenant；
  -Partner；
  -Community Identity。

## Hard Rules

* Event名称和属性版本化；
* 不收集不必要源码信息；
* PII最小化；
* Anonymous合并需符合隐私；
* 不同Region遵守Consent；
* 迟到和重复事件需处理；
* 产品指标需基于语义层而非临时SQL。

## Acceptance Criteria

* Growth事件覆盖主要漏斗；
* Identity可安全解析；
* 指标可复现；
* 数据质量可监控；
* Region Consent生效；
* 事件可服务实验和归因。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

