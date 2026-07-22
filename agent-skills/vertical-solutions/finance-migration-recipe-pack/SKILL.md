---
name: finance-migration-recipe-pack
description: "Execute authoritative Batch 17 Skill 616 for finance migration recipe pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Finance Migration Recipe Pack

## Operating contract

Apply authoritative Batch 17 Skill 616. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Recipe Categories

```text
Legacy Batch to Modern Job
Mainframe Adapter
Ledger Mapping
Payment API
Message Queue
Account Service
Interest and Fee Calculation
Reconciliation
Customer/KYC
Audit
```

## 特殊要求

* Decimal；
  -Date；
  -Business Calendar；
  -Batch Restart；
  -Sequence；
  -Message Correlation；
  -Transaction Boundary；
  -Replay；
  -Data Masking。

## Hard Rules

* 财务计算Recipe需Golden；
* Interest和Fee不可仅靠模型生成；
* Batch重启点必须保持；
* Legacy Encoding明确；
* 外部清算边界使用Adapter；
* 业务规则有Owner；
* Agent Patch需增强审批。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
