---
name: finance-domain-model
description: "Execute authoritative Batch 17 Skill 613 for finance domain model. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Finance Domain Model

## Operating contract

Apply authoritative Batch 17 Skill 613. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## 核心领域

```text
Party
Customer
Account
Balance
Ledger
Journal Entry
Payment
Transaction
Instrument
Position
Trade
Limit
Collateral
Risk
Settlement
Case
KYC
Approval
```

## 关键Bounded Context

```text
Customer and Identity
Accounts
Payments
Ledger
Trading
Risk
Compliance
Settlement
Reporting
```

## 核心Invariant

```text
账务借贷平衡
交易金额和币种一致
同一业务操作保持幂等
余额和Ledger可追溯
结算状态只能合法转换
审批人与发起人职责分离
```

## Hard Rules

* Ledger与可修改业务表分开；
* 金额使用明确Decimal；
* 币种和精度显式；
* Value Date、Trade Date和Posting Date分开；
* Reversal不能删除原交易；
* 外部Transaction ID稳定；
* 客户私有产品模型通过Extension扩展。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
