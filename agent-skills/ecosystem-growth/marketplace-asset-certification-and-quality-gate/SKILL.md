---
name: marketplace-asset-certification-and-quality-gate
description: "Execute authoritative Batch 14 Skill 438 for marketplace asset certification and quality gate. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Marketplace Asset Certification And Quality Gate

## Operating contract

Apply authoritative Batch 14 Skill 438. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

对Recipe、Adapter、Compatibility Runtime、模板和插件执行技术、安全和质量认证。

## Certification Levels

```text id="i5j301"
Community
Verified
Certified
Enterprise Certified
Vendor Maintained
```

## Review Dimensions

```text id="kqbcvj"
Correctness
Tests
Compatibility
Security
License
Documentation
Performance
Idempotency
Provenance
Support
Update Policy
```

## Asset Gate

```yaml id="0k9p10"
asset_gate:
  parse: passed
  test: passed
  security: passed
  license: passed
  sandbox: passed
  documentation: passed
```

## Hard Rules

* 可执行资产必须Sandbox测试；
* 未知License阻止公开发布；
* Secret和客户代码为0；
* Production Certified需有版本范围；
* Asset更新重新审核；
* Critical漏洞触发紧急撤销；
* Certification不能通过付费购买。

## Acceptance Criteria

* 资产质量透明；
* 企业用户可选择认证级别；
* 恶意或低质量资产被阻止；
* 更新兼容性可验证；
* 认证状态可审计；
* 质量门禁支持规模增长。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

