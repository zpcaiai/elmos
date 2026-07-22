---
name: lifecycle-messaging-and-in-product-guidance
description: "Execute authoritative Batch 14 Skill 410 for lifecycle messaging and in product guidance. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Lifecycle Messaging And In Product Guidance

## Operating contract

Apply authoritative Batch 14 Skill 410. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

根据用户Journey提供邮件、通知、Checklist、Tooltip和产品内指导。

## Lifecycle Stages

```text id="fqe6bj"
New
Activated
Stalled
Adopting
Power User
Expansion Candidate
At Risk
Churned
```

## Message Types

* Onboarding；
  -Assessment完成；
  -Build失败；
  -未完成步骤；
  -配额；
  -新Recipe；
  -安全更新；
  -Webinar；
  -成功案例；
  -邀请团队；
  -升级；
  -续费。

## Guidance Principles

* Contextual；
  -Actionable；
  -可关闭；
  -低频；
  -按Persona；
  -按Region；
  -按Language；
  -按权限。

## Hard Rules

* 不发送用户无权限操作；
* 不因用户查看敏感项目而发送不当邮件；
* Marketing和Transactional消息分开；
* 用户可管理偏好；
* 失败通知不能包含源码；
* 消息频率有上限；
* 生命周期状态由事实行为驱动。

## Acceptance Criteria

* 用户获得适时指导；
* 消息点击能转化为行动；
* 退订和偏好生效；
* 消息不会泄露项目；
* Stalled用户恢复率提高；
* 通知疲劳受控。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

