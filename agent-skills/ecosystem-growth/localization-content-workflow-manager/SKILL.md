---
name: localization-content-workflow-manager
description: "Execute authoritative Batch 14 Skill 445 for localization content workflow manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Localization Content Workflow Manager

## Operating contract

Apply authoritative Batch 14 Skill 445. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

管理产品、文档、网站、Marketplace和支持内容的翻译、Review和发布。

## Workflow

```text id="ja3a1s"
Source Created
→ Extract
→ Machine Translation Candidate
→ Human Translation
→ Technical Review
→ Linguistic QA
→ In-context QA
→ Publish
→ Monitor
```

## Content Priority

```text id="7bmbns"
Critical UI
Security
Billing
Onboarding
Documentation
Support
Website
Marketplace
Community
Long-tail Content
```

## Translation Status

```text id="8rzi2c"
untranslated
machine-draft
human-translated
technical-reviewed
approved
outdated
```

## Hard Rules

* Security和Billing内容必须人工Review；
* 机器翻译不能直接发布关键内容；
* Source更新需标记翻译过期；
* 截图和UI需In-context检查；
* 翻译不得包含客户私有内容；
* 不同地区同语言可有不同版本；
* Translation Vendor需保密协议和权限控制。

## Acceptance Criteria

* 核心内容翻译完整；
* Source和Translation版本关联；
* 技术术语准确；
* UI无截断和错位；
* 地区用户可理解；
* 更新延迟可监控。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

