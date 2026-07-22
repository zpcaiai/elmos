---
name: marketplace-install-version-and-dependency-manager
description: "Execute authoritative Batch 14 Skill 440 for marketplace install version and dependency manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Marketplace Install Version And Dependency Manager

## Operating contract

Apply authoritative Batch 14 Skill 440. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

安全安装、升级、回滚和卸载Marketplace资产。

## Install Plan

```yaml id="14ekyp"
install_plan:
  asset_id: string
  version: string
  target_workspace: string

  dependencies: []
  permissions: []
  conflicts: []
  rollback: {}
```

## 安装前检查

* Compatibility；
  -Target Version；
  -Dependency；
  -License；
  -Permission；
  -Network；
  -Model；
  -Data；
  -Runner；
  -Collision；
  -Quota。

## Version策略

```text id="t27akd"
pin
compatible-range
auto-patch
manual-update
tenant-approved
```

企业默认建议Pin并受控升级。

## Hard Rules

* 资产安装必须经Policy；
* 不允许隐式安装未知依赖；
* 权限变化需重新审批；
* 自动升级不得包含Breaking Change；
* 卸载需检查使用中的Migration；
* 回滚包必须存在；
* 安装行为进入Provenance和审计。

## Acceptance Criteria

* 安装可预测；
* 依赖闭包完整；
* 升级和回滚成功；
* 权限透明；
* Workspace不被破坏；
* 资产使用可追踪。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

