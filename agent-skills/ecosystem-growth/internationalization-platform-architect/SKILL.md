---
name: internationalization-platform-architect
description: "Execute authoritative Batch 14 Skill 444 for internationalization platform architect. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Internationalization Platform Architect

## Operating contract

Apply authoritative Batch 14 Skill 444. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

建立语言、Locale、时区、文本方向和可扩展国际化架构。

## I18n Scope

```text id="tnr0ow"
Web UI
Admin Console
CLI
Developer Portal
Documentation
Emails
Notifications
Reports
PDF
Marketplace
Community
Support
Billing
Contracts
```

## Message Key

```yaml id="b7n2hv"
message:
  key: migration.run.status.failed
  default_locale: en-US
  context: string
  variables:
    - run_name
    - error_count
```

## 技术要求

* Unicode；
  -ICU Message；
  -Plural；
  -Gender；
  -Date；
  -Time；
  -Number；
  -Currency；
  -Timezone；
  -RTL；
  -Fallback；
  -Locale Negotiation；
  -Translation Version。

## Hard Rules

* 业务文本不能硬编码在代码中；
* 变量不得通过字符串拼接破坏语序；
* Locale Fallback必须可预测；
* 技术Error Code和本地化Message分开；
* 机器可读Artifact不得因UI语言改变；
* RTL布局需实际测试；
* API字段名不随Locale变化。

## Acceptance Criteria

* 产品界面可切换Locale；
* Plural和格式正确；
* RTL支持按计划；
* 翻译缺失可检测；
* CLI和报告可本地化；
* I18n不会改变技术契约。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

