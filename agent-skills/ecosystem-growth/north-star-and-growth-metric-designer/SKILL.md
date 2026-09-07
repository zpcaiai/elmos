---
name: north-star-and-growth-metric-designer
description: "Execute authoritative Batch 14 Skill 402 for north star and growth metric designer. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# North Star And Growth Metric Designer

## Operating contract

Apply authoritative Batch 14 Skill 402. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

定义North Star、输入指标、结果指标和增长防护指标。

## Metric Layers

```text id="lqoafb"
North Star
├── Acquisition Drivers
├── Activation Drivers
├── Adoption Drivers
├── Retention Drivers
├── Expansion Drivers
└── Ecosystem Drivers
```

## Metric Definition

```yaml id="ajf9jj"
metric:
  metric_id: verified-migration-workspaces
  definition: string
  grain: workspace-month
  numerator: string
  denominator: null
  exclusions: []
  owner: growth-product
```

## Guardrail Metrics

* Security Incident；
  -跨Tenant错误；
  -支持工单；
  -失败Run；
  -模型成本；
  -退款；
  -低质量Lead；
  -Community Abuse；
  -Marketplace Malware；
  -Churn；
  -毛利。

## Hard Rules

* North Star必须反映客户价值；
* 不允许用模型调用量作为唯一成功；
* 每个指标必须有严格定义；
* 指标变更需版本化；
* 漏斗不同阶段不能使用不一致用户ID；
* Guardrail恶化时实验不得判定成功；
* 指标需能按Region和Segment拆分。

## Acceptance Criteria

* North Star可自动计算；
* Driver Tree完整；
* Guardrail可实时查询；
* 指标口径一致；
* 管理层和产品使用同一指标；
* 指标与续费和收入有相关证据。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

