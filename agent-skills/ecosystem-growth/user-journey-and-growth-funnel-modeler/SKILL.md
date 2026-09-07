---
name: user-journey-and-growth-funnel-modeler
description: "Execute authoritative Batch 14 Skill 403 for user journey and growth funnel modeler. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# User Journey And Growth Funnel Modeler

## Operating contract

Apply authoritative Batch 14 Skill 403. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

建模开发者、架构师、企业管理员、伙伴和Marketplace发布者的不同旅程。

## Personas

```text id="up4jdi"
Individual Developer
Migration Engineer
Architect
Engineering Manager
Security Admin
Enterprise Buyer
Partner Consultant
Marketplace Publisher
Community Contributor
```

## Developer Funnel

```text id="s25m1j"
Content Visit
→ Documentation
→ Signup
→ Connect Repository
→ Assessment
→ Review Findings
→ Generate Skeleton
→ Build Green
→ Invite Team
```

## Enterprise Funnel

```text id="1d93pc"
Research
→ Demo
→ Assessment
→ POC
→ Security Review
→ Contract
→ Onboarding
→ Production Migration
```

## Funnel Event

```yaml id="35zluh"
funnel_event:
  actor_id: string
  journey: developer-self-service
  step: assessment-completed
  occurred_at: string
  source_channel: organic-search
```

## Hard Rules

* 不同Persona漏斗分开；
* 匿名到登录身份需安全合并；
* Sales-assisted和Self-service需识别；
* 用户跳过步骤不能错误算流失；
* Partner参与需纳入Journey；
* 漏斗事件必须幂等；
* 隐私政策限制用户追踪。

## Acceptance Criteria

* 主要Persona有Journey；
* 每个阶段有事件；
* 流失点可分析；
* Sales和Product漏斗可以关联；
* Journey可以驱动个性化引导。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

