---
name: erp-and-group-finance-integration
description: "Execute authoritative Batch 18 Skill 718 for erp and group finance integration. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Erp And Group Finance Integration

## Operating contract

Apply authoritative Batch 18 Skill 718. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## 范围

```text
Chart of Accounts
General Ledger
AP
AR
Treasury
Fixed Assets
Consolidation
Tax
Expense
Procurement
```

## Hard Rules

* Day 1财务和付款连续；
* 科目映射由财务批准；
* 历史账务不删除；
* 法人账簿保持；
* Intercompany交易明确；
* Cutover配合财务期；
* 财务核对差异为0或正式接受。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
