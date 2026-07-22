---
name: self-service-signup-and-workspace-provisioner
description: "Execute authoritative Batch 14 Skill 406 for self service signup and workspace provisioner. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Self Service Signup And Workspace Provisioner

## Operating contract

Apply authoritative Batch 14 Skill 406. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

提供低摩擦但安全的自助注册、团队创建和Workspace Provisioning。

## Signup Modes

```text id="t0kkz2"
Email
GitHub
GitLab
Google
Microsoft
Enterprise SSO Invitation
CLI Device Login
```

## Signup Flow

1. 验证身份。
2. 接受条款。
3. 选择用途。
4. 创建个人或团队Workspace。
5. 配置默认Region。
6. 选择Repository Provider。
7. 设置Retention。
8. 开始Onboarding。

## Abuse Controls

* Email验证；
  -风险IP；
  -Rate Limit；
  -Captcha或风险挑战；
  -Disposable Email；
  -大量Workspace；
  -恶意Repository；
  -挖矿或资源滥用；
  -模型滥用。

## Hard Rules

* 自助用户不得创建Platform级资源；
* OAuth权限最小化；
* 默认Trial配额有限；
* 高风险任务需升级验证；
* Signup不能自动授权整个Git组织；
* 删除账户遵守Retention；
* 可疑用户不得获得高成本资源。

## Acceptance Criteria

* 注册流程顺畅；
* Workspace自动创建；
* OAuth权限最小；
* 滥用受控；
* 匿名和登录Journey可关联；
* Trial成本可管理。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

