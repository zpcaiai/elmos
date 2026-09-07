---
name: regional-market-entry-assessor
description: "Execute authoritative Batch 14 Skill 450 for regional market entry assessor. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Regional Market Entry Assessor

## Operating contract

Apply authoritative Batch 14 Skill 450. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

评估某地区是否值得进入，以及最适合的进入模式。

## Assessment Dimensions

```text id="f3xwxy"
Market Size
Legacy Modernization Demand
Language
Competitive Landscape
Cloud Adoption
Regulation
Data Residency
Enterprise Procurement
Partner Availability
Developer Community
Support Cost
Payment
Political and Operational Risk
```

## Entry Score

```yaml id="57cmbf"
region_score:
  region: japan
  opportunity: 85
  product_readiness: 70
  channel_readiness: 65
  compliance_readiness: 80
  overall: 75
```

## Entry Modes

```text id="dwxsda"
Remote Direct Sales
Local Sales
Partner-led
Cloud Marketplace
Distributor
Joint Venture
Dedicated Deployment
Community-first
```

## Hard Rules

* 市场规模不能单独决定进入；
* 缺少本地支持会降低高端企业可行性；
* 数据驻留Gap需提前解决；
* Partner存在不代表Partner有能力；
* 竞争环境需本地研究；
* 每个地区先设试点；
* Exit条件需提前定义。

## Acceptance Criteria

* 进入决策有数据；
* 产品和合规Gap明确；
* 进入模式合理；
* 预算和阶段清晰；
* 试点市场可选择；
* 高风险地区可暂缓。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

