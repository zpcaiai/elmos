---
name: growth-system-orchestrator
description: "Execute authoritative Batch 14 Skill 401 for growth system orchestrator. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Growth System Orchestrator

## Operating contract

Apply authoritative Batch 14 Skill 401. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

统一编排产品增长、内容、开发者、社区、Marketplace和区域复制。

## Inputs

```yaml id="czqaqv"
growth_program:
  target_segments: []
  target_regions: []
  product_motions:
    - self-service
    - sales-assisted
    - partner-led

  primary_goals:
    - acquisition
    - activation
    - expansion
```

## Workflow

1. 选择目标Segment。
2. 定义North Star和Guardrail。
3. 建立用户旅程。
4. 选择获客渠道。
5. 设计自助激活。
6. 建立内容主题。
7. 建立Developer Portal。
8. 建立社区和Marketplace。
9. 选择首批国际市场。
10. 执行实验。
11. 追踪Retention和Revenue。
12. 将成功策略固化为Playbook。

## Hard Rules

* 增长目标必须绑定业务价值；
* 不同Segment不能使用同一默认漏斗；
* 产品、销售和社区数据需使用统一身份；
* 新渠道必须有成本和质量评估；
* 增长实验不能绕过安全；
* 地区扩张必须有本地化和支持能力；
* 所有增长活动需有Owner和停止条件。

## Acceptance Criteria

* 增长域使用统一计划；
* 渠道和产品动作相互衔接；
* 增长结果可按Segment和Region分析；
* 成功策略可重复；
* 低质量增长可及时停止。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

