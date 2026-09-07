---
name: core-capability-and-moat-planner
description: "Execute authoritative Batch 15 Skill 467 for 识别公司必须独特掌握的能力，以及哪些能力可以购买、合作或外包。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Core Capability And Moat Planner

## Operating contract

Apply authoritative Batch 15 Skill 467. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

识别公司必须独特掌握的能力，以及哪些能力可以购买、合作或外包。

## Capability Categories

```text
Differentiating
Strategic
Enabling
Commodity
Outsourceable
```

## 平台公司的潜在核心能力

* 跨语言UIR；
  -语义验证；
  -迁移Recipe网络；
  -企业私有Runner；
  -行为等价验证；
  -迁移数据和知识；
  -Marketplace生态；
  -企业交付方法论。

## Capability Record

```yaml
capability:
  capability_id: semantic-migration-engine
  category: differentiating
  current_maturity: 3
  target_maturity: 5
  investment_required: number
```

## Hard Rules

* 核心能力不能完全依赖单一供应商；
* 商品化能力不应过度自研；
* 护城河需体现客户价值；
* 数据优势必须符合隐私；
* 核心能力需匹配招聘和投资；
* 能力成熟度需有证据；
* 每年重新评估Buy、Build或Partner。

## Acceptance Criteria

* 公司知道必须自建什么；
* 资本投入聚焦；
* 外包边界清晰；
* 单点供应商风险可见；
* 核心能力形成Roadmap；
* 护城河可通过客户结果验证。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
