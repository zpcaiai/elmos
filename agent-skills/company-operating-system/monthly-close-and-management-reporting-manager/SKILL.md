---
name: monthly-close-and-management-reporting-manager
description: "Execute authoritative Batch 15 Skill 501 for 建立准确、及时的月度结账和管理报告。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Monthly Close And Management Reporting Manager

## Operating contract

Apply authoritative Batch 15 Skill 501. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立准确、及时的月度结账和管理报告。

## Close Activities

```text
Revenue
Expenses
Payroll
Accruals
Prepayments
Deferred Revenue
Accounts Receivable
Accounts Payable
Cash
Tax
Intercompany
Cap Table Events
```

## Management Pack

```text
Income Statement
Cash Flow
Balance Sheet
Budget Variance
Revenue Bridge
ARR
Gross Margin
Headcount
Cash and Runway
KPIs
Risks
Forecast
```

## Hard Rules

* 管理报告与财务账一致；
* 非GAAP指标需定义；
* 月度数据不能无限延迟；
* 手工Journal需审批；
* Revenue Recognition需一致；
* Close Checklist有Owner；
* 历史数字修改需审计。

## Acceptance Criteria

* 月度结账按时；
* 管理层获得可信报告；
* 现金和应收准确；
* 财务指标可追溯；
* 调整有审批；
* 董事会材料使用同一数据。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
