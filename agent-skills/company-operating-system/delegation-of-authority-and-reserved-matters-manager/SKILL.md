---
name: delegation-of-authority-and-reserved-matters-manager
description: "Execute authoritative Batch 15 Skill 514 for 定义公司不同层级可批准的支出、招聘、合同、风险和战略事项。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Delegation Of Authority And Reserved Matters Manager

## Operating contract

Apply authoritative Batch 15 Skill 514. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

定义公司不同层级可批准的支出、招聘、合同、风险和战略事项。

## Authority Dimensions

```text
Spend
Contract
Hiring
Compensation
Pricing
Discount
Security Exception
Data Access
Product Release
Capital Investment
Debt
Equity
Acquisition
Litigation
```

## Authority Matrix

```yaml
authority:
  action: vendor-contract
  threshold: number
  approvers:
    - CFO
    - Legal
  board_reserved_above: number
```

## Reserved Matters

通常包括：

* 融资；
  -发股；
  -并购；
  -重大债务；
  -年度预算；
  -重大偏离预算；
  -高管任免；
  -重大诉讼；
  -公司出售；
  -重大安全风险接受。

具体范围由公司文件确定。

## Hard Rules

* 系统权限应映射授权矩阵；
* 金额拆分不能规避审批；
* 紧急支出需事后审批；
* 管理层权限需匹配责任；
* 董事会保留事项不能委托绕过；
* 权限变更需审计；
* 同一人不应完成所有高风险步骤。

## Acceptance Criteria

* 审批路径清晰；
* 决策速度合理；
* 越权操作被阻止；
* 金额和风险阈值生效；
* 董事会保留事项得到遵守；
* 审计完整。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
