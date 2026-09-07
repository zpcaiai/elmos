---
name: api-cli-and-sdk-developer-experience-manager
description: "Execute authoritative Batch 14 Skill 425 for api cli and sdk developer experience manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# API CLI And SDK Developer Experience Manager

## Operating contract

Apply authoritative Batch 14 Skill 425. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

优化API、CLI和SDK的可发现性、一致性、错误处理和示例。

## DX Requirements

* 快速认证；
  -明确错误；
  -幂等；
  -Pagination；
  -Async Job；
  -自动补全；
  -JSON输出；
  -SDK类型；
  -重试策略；
  -版本；
  -示例；
  -日志；
  -Dry Run。

## SDK Languages

优先：

```text id="m8jx8b"
TypeScript
Python
Java
C#
Go
```

根据客户和伙伴需求扩展。

## CLI Journeys

```text id="i53mjw"
login
repo connect
assessment create
migration run
status watch
artifact download
report export
marketplace install
runner register
```

## Hard Rules

* SDK行为需与API一致；
* CLI不得明文保存Token；
* 错误码稳定；
* 自动Retry只用于安全操作；
* SDK生成后需人工和集成测试；
* Breaking Change必须版本化；
* Offline CLI不依赖云端。

## Acceptance Criteria

* 开发者可通过API或CLI完成核心流程；
* SDK类型准确；
* 错误可操作；
* 示例可运行；
* Time to First API Call较短；
* API和SDK采用率可衡量。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

