---
name: cost-opex-and-investment-planner
description: "Execute authoritative Batch 15 Skill 495 for 规划Cost of Revenue、研发、销售、市场、管理和资本投入。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Cost Opex And Investment Planner

## Operating contract

Apply authoritative Batch 15 Skill 495. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

规划Cost of Revenue、研发、销售、市场、管理和资本投入。

## Cost Categories

```text
Cloud and Model
Runner
Support
Delivery
Partner Revenue Share
Engineering
Product
Sales
Marketing
People
Finance
Legal
Facilities
Insurance
Security
Travel
Capex
```

## Fixed与Variable

区分：

* 固定成本；
  -随收入变化；
  -随客户变化；
  -随使用量变化；
  -阶梯成本；
  -一次性投资。

## Hard Rules

* 模型和云成本不能只按历史平均；
* 支持和交付成本需关联客户；
* Contractor需进入人员成本；
* 资本化政策需统一；
* 预算不能隐藏在多个部门重复；
* 所有战略项目需有费用；
* 成本削减需评估战略影响。

## Acceptance Criteria

* 费用计划完整；
* 固定和变量成本清晰；
* 部门Budget可汇总；
* 战略投资可追踪；
* 毛利驱动可分析；
* 成本偏差可解释。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
