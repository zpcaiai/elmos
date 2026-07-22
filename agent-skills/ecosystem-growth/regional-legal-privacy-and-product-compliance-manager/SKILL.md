---
name: regional-legal-privacy-and-product-compliance-manager
description: "Execute authoritative Batch 14 Skill 448 for regional legal privacy and product compliance manager. Use when Codex must design, operate, review, or verify this growth and ecosystem capability."
---

# Regional Legal Privacy And Product Compliance Manager

## Operating contract

Apply authoritative Batch 14 Skill 448. Read [the shared Batch 14 growth boundary](../references/batch-14-growth-evidence-boundary.md) before acting.

1. Pin the tenant, region, locale, persona, channel, campaign, source, consent state, product version, policy version, owner, and evidence window.
2. Confirm the required inputs and systems of record. Treat missing, stale, conflicting, cross-tenant, or unauthorized evidence as NOT_RUN, INCONCLUSIVE, or blocking.
3. Execute or evaluate the capability using the authoritative specification below. Keep product, content, community, Marketplace, localization, regional, security, privacy, quality, retention, and economics guardrails non-compensating.
4. Preserve failed and negative outcomes. Do not convert plans, drafts, simulations, generated artifacts, or repository tests into field success.
5. Record metric definitions, costs, quality signals, decisions, evidence references, stop conditions, and the next responsible owner.
6. Return the acceptance criteria as PASSED, FAILED, NOT_RUN, or INCONCLUSIVE; do not claim G14-G until Skill 460 passes with complete external evidence.

## Authoritative specification

## Description

识别并落实不同地区的隐私、合同、数据驻留、营销和软件交付要求。

## Compliance Areas

```text id="35rms5"
Privacy
Cookies
Marketing Consent
Data Residency
Cross-border Transfer
Retention
Deletion
Tax
Invoice
Electronic Contract
Export Control
Encryption
Open Source License
Marketplace
Consumer Protection
Employment
Partner Regulation
```

## Compliance Requirement

```yaml id="1gxdpm"
regional_requirement:
  region: string
  requirement: string
  affected_components: []
  mandatory: true
  evidence: []
```

## Hard Rules

* 合规判断需由合格专业人员确认；
* 产品不得仅通过翻译进入新地区；
* 数据处理位置必须真实；
* Marketing Consent按地区执行；
* Cookie策略按地区配置；
* Marketplace Publisher责任需本地审查；
* 不确定法规不得由产品团队猜测。

## Acceptance Criteria

* 上线地区有合规清单；
* Mandatory要求落实；
* 数据流和合同匹配；
* Consent和删除流程有效；
* 区域风险有Owner；
* 合规证据可导出。

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, guardrail results, and external_operation_executed=false for any control-plane-only evaluation.

