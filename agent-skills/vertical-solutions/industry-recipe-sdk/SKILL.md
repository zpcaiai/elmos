---
name: industry-recipe-sdk
description: "Execute authoritative Batch 17 Skill 604 for 为行业专家和工程师提供开发领域Recipe、Validator、Collector和Adapter的SDK。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Recipe Sdk

## Operating contract

Apply authoritative Batch 17 Skill 604. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

为行业专家和工程师提供开发领域Recipe、Validator、Collector和Adapter的SDK。

## SDK Components

```text
Domain Matcher
Control Annotation
Recipe Definition
Schema Mapper
State Mapper
Test Generator
Evidence Collector
Policy Extension
Dashboard Metric
```

## Recipe Schema

```yaml
industry_recipe:
  recipe_id: finance.money-decimal-preservation
  domain_entities: []
  controls: []
  transformations: []
  required_tests: []
  evidence: []
```

## Hard Rules

* Recipe不得硬编码客户Secret；
* Recipe必须声明行业和版本；
* Control相关Recipe需安全Review；
* Recipe有反例和失败测试；
* 不兼容版本不得自动匹配；
* 客户私有Recipe默认不可公开；
* Agent生成Recipe只能为Candidate。

## Acceptance Criteria

* 行业Recipe开发标准化；
* Recipe可测试和签名；
* 领域和Control绑定；
* Marketplace可发布；
* 伙伴可在Sandbox开发；
* 共享内核无需Fork。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
