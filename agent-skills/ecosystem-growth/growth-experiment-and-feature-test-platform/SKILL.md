---
name: growth-experiment-and-feature-test-platform
description: "Execute authoritative Batch 14 Skill 412 for growth experiment and feature test platform. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Growth Experiment And Feature Test Platform

## Operating contract

Apply authoritative Batch 14 Skill 412. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

建立产品、内容、定价、Onboarding和渠道实验平台。

## Experiment Types

```text id="7dbp36"
A/B
Multivariate
Holdout
Feature Flag
Cohort Rollout
Geo Experiment
Channel Incrementality
Pricing Experiment
Onboarding Experiment
```

## Experiment Record

```yaml id="a6n5mq"
experiment:
  experiment_id: onboarding-target-selector
  hypothesis: string

  population: new-developer-users
  variants:
    - control
    - recommended-target

  primary_metric: assessment-completion
  guardrails:
    - support-ticket-rate
    - security-policy-error
```

## Assignment

必须稳定：

```text id="ob1c36"
user
workspace
tenant
region
```

企业Workspace功能实验需谨慎，避免同一团队体验不一致。

## Hard Rules

* 实验前必须定义Hypothesis；
* 指标和最小样本提前设定；
* 不允许反复查看数据后随意提前停止；
* Security、Billing和Data Retention不做无审批实验；
* 企业合同功能不得随机移除；
* 用户退出实验后行为需明确；
* 实验结果需保留负面结论。

## Acceptance Criteria

* 实验可稳定分组；
* Guardrail生效；
* 决策可审计；
* 无显著结果也被记录；
* 实验可安全停止；
* 成功实验可产品化。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

