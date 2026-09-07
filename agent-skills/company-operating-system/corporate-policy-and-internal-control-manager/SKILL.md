---
name: corporate-policy-and-internal-control-manager
description: "Execute authoritative Batch 15 Skill 515 for 建立财务、安全、人事、采购、销售和信息管理政策及内部控制。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Corporate Policy And Internal Control Manager

## Operating contract

Apply authoritative Batch 15 Skill 515. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立财务、安全、人事、采购、销售和信息管理政策及内部控制。

## Policy Domains

```text
Finance
Procurement
Expense
Revenue
Security
Privacy
Access
Data
AI and Model Use
HR
Hiring
Compensation
Travel
Sales
Discount
Partner
Whistleblowing
Conflict of Interest
```

## Control Types

```text
Preventive
Detective
Corrective
Manual
Automated
Entity-level
Transaction-level
```

## Control Record

```yaml
control:
  control_id: vendor-payment-approval
  risk: unauthorized-payment
  owner: finance
  frequency: per-transaction
  evidence: []
```

## Hard Rules

* Policy需有Owner和Review Date；
* Control需关联风险；
* 关键控制失败需升级；
* 控制不能只存在文档；
* 自动控制需测试；
* Manual Control需保留证据；
* 例外需审批和期限。

## Acceptance Criteria

* 关键风险有控制；
* 政策已发布；
* 控制执行有证据；
* 例外可追踪；
* 审计发现可整改；
* 公司治理成熟度提高。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
