---
name: community-moderation-trust-and-safety-manager
description: "Execute authoritative Batch 14 Skill 432 for community moderation trust and safety manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Community Moderation Trust And Safety Manager

## Operating contract

Apply authoritative Batch 14 Skill 432. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

治理垃圾信息、骚扰、恶意代码、敏感数据和供应链攻击。

## Risk Types

```text id="jyxtfz"
Spam
Harassment
Phishing
Malware
Malicious Recipe
Secret Leak
Customer Code Leak
Impersonation
Fake Review
Astroturfing
Copyright Violation
Security Exploit
```

## Moderation Actions

```text id="xx5nr6"
warn
hide
quarantine
remove
restrict
suspend
ban
escalate-security
preserve-evidence
```

## Code和Recipe内容

需要：

* Static Scan；
  -Malware Scan；
  -Secret Scan；
  -License；
  -Sandbox；
  -人工Review；
  -报告机制。

## Hard Rules

* 严重安全内容立即隔离；
* Moderation需有申诉流程；
* 不允许员工操纵评价；
* 客户源码泄漏需启动Incident；
* 证据保存需符合隐私；
* 地区社区遵守本地法律；
* 高风险Marketplace内容与社区普通内容分开处理。

## Acceptance Criteria

* 举报处理及时；
* 恶意内容无法扩散；
* 误判可申诉；
* 社区信任度维持；
* 安全事件响应完整；
* Moderation可审计。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

