---
name: trial-freemium-and-developer-plan-manager
description: "Execute authoritative Batch 14 Skill 409 for trial freemium and developer plan manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Trial Freemium And Developer Plan Manager

## Operating contract

Apply authoritative Batch 14 Skill 409. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

设计Trial、Free和Developer Plan的功能、配额、期限和升级策略。

## Plan Types

```text id="db593u"
Anonymous Demo
Free Assessment
Developer Free
Team Trial
Enterprise POC
Partner Sandbox
Education
Open Source Program
```

## Trial Entitlement

```yaml id="34p7rd"
trial:
  duration: 14d
  repositories: 3
  assessments: 10
  migration_runs: 2
  model_tokens: integer
  private_runner: false
```

## Trial Success

Trial不应只追求登录，而应推动：

* Assessment；
* Skeleton；
  -Build；
  -Invite；
  -Share；
  -POC请求。

## Hard Rules

* Trial不得无限重置；
* 高成本资源需限额；
* Trial到期不删除客户数据；
* Enterprise POC与普通Trial分开；
* Partner Sandbox不得访问客户数据；
* 免费开源计划需验证资格；
* Plan限制需透明。

## Acceptance Criteria

* Trial能够展示真实价值；
* 成本可控；
* 滥用率低；
* 到期和升级平滑；
* Trial-to-paid可衡量；
* 不同Trial类型用途清晰。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

