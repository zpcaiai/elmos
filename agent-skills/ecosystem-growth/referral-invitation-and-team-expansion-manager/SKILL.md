---
name: referral-invitation-and-team-expansion-manager
description: "Execute authoritative Batch 14 Skill 411 for referral invitation and team expansion manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Referral Invitation And Team Expansion Manager

## Operating contract

Apply authoritative Batch 14 Skill 411. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

通过邀请、分享报告、内部推荐和客户推荐推动团队扩散。

## Viral Loops

```text id="6mtae9"
Assessment Report Share
Invite Reviewer
Invite Architect
Invite Security Admin
Invite Project Team
Share Marketplace Asset
Refer Another Company
```

## Invite Record

```yaml id="5ak6q2"
invitation:
  inviter: string
  workspace_id: string
  role: reviewer
  expires_at: string
```

## Safety

* 邀请Role最小；
  -Tenant和Domain限制；
  -外部协作者显著标识；
  -邀请过期；
  -禁止开放链接泄露源码；
  -报告分享可脱敏。

## Hard Rules

* 邀请者不能授予超过自身权限的Role；
* 外部分享需项目Policy允许；
* Referral奖励不能诱导垃圾注册；
* 企业内部邀请需尊重Domain策略；
* 分享报告默认不包含源码；
* 邀请和接受都需审计；
* 用户删除后邀请失效。

## Acceptance Criteria

* 团队邀请流程顺畅；
* 权限安全；
* Invite-to-active可衡量；
* Share带来协作；
* 滥用和垃圾推荐受控；
* 企业Workspace自然扩散。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

