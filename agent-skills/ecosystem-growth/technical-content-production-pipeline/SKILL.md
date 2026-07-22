---
name: technical-content-production-pipeline
description: "Execute authoritative Batch 14 Skill 417 for technical content production pipeline. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Technical Content Production Pipeline

## Operating contract

Apply authoritative Batch 14 Skill 417. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

将工程知识、Recipe、项目经验和研究转化为高质量技术内容。

## Content Sources

```text id="fkykqw"
Engineering Design
Migration Recipe
Support Issue
POC Finding
Customer Case
Benchmark
Security Research
Community Question
Product Release
```

## Workflow

```text id="nlh9uw"
Idea
→ Brief
→ Technical Draft
→ Code Verification
→ Security Review
→ Editorial Review
→ Localization
→ Publish
→ Distribute
→ Measure
→ Update
```

## Content Artifact

```yaml id="a0kpj5"
content:
  content_id: string
  type: tutorial
  persona: java-architect
  funnel_stage: consideration
  source_evidence: []
  technical_reviewer: string
```

## Hard Rules

* 示例代码必须可运行；
* 基准测试需公开方法；
* 安全内容需安全Review；
* AI生成内容需事实验证；
* 客户信息必须获授权；
* 产品功能需对应实际版本；
* 过期版本内容需更新或标记。

## Acceptance Criteria

* 内容技术准确；
* 示例可重现；
* 发布周期可预测；
* 内容来源可追踪；
* 内容能产生目标用户行为；
* 高价值内容持续更新。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

