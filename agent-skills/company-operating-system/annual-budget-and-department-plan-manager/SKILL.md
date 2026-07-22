---
name: annual-budget-and-department-plan-manager
description: "Execute authoritative Batch 15 Skill 498 for 将战略、Headcount和财务模型转化为年度预算。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Annual Budget And Department Plan Manager

## Operating contract

Apply authoritative Batch 15 Skill 498. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将战略、Headcount和财务模型转化为年度预算。

## Budget Components

```text
Revenue Budget
Headcount Budget
Operating Expense
Capital Expenditure
Strategic Initiatives
Contingency
Cash
Department Budgets
```

## Budget Process

1. 发布战略和假设。
2. 建立Top-down边界。
3. 部门提出Bottom-up计划。
4. 财务整合。
5. 管理层权衡。
6. 情景测试。
7. 董事会批准。
8. 发布预算。
9. 月度追踪。

## Hard Rules

* 预算不是历史成本加百分比；
* 每项新增投入需关联战略；
* 部门不能重复计算共享成本；
* Headcount和薪酬需匹配；
* 未批准预算不得承诺外部支出；
* Contingency使用需审批；
* 预算调整保留版本。

## Acceptance Criteria

* 预算与战略一致；
* 预算与Headcount一致；
* 现金满足安全要求；
* 部门知道可用资源；
* 董事会批准；
* 实际可按月比较。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
