---
name: experiment-statistics-and-decision-controller
description: "Execute authoritative Batch 14 Skill 413 for experiment statistics and decision controller. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Experiment Statistics And Decision Controller

## Operating contract

Apply authoritative Batch 14 Skill 413. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

对实验结果进行统计判断、业务判断和长期影响判断。

## Decision Inputs

* Primary Metric；
  -Guardrail；
  -Sample Size；
  -Effect Size；
  -Confidence或Posterior；
  -Novelty Effect；
  -长期Retention；
  -Segment Difference；
  -成本；
  -实施复杂度。

## Decision States

```text id="w0awoe"
ship
ship-to-segment
continue
iterate
stop-no-effect
stop-harmful
inconclusive
```

## Hard Rules

* 统计显著不等于业务有意义；
* Primary Metric改善但Retention下降不能直接发布；
* Segment效果相反需分析；
* 多重比较需控制；
* 实验污染需标记无效；
* 价格实验需满足法律和商业政策；
* 长周期行为需有后续验证。

## Acceptance Criteria

* 实验决策有证据；
* Effect Size清晰；
* Guardrail风险可见；
* Segment决策可执行；
* 负面实验避免重复；
* 决策进入知识库。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

