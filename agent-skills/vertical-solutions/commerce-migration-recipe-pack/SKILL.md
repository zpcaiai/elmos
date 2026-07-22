---
name: commerce-migration-recipe-pack
description: "Execute authoritative Batch 17 Skill 651 for commerce migration recipe pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Commerce Migration Recipe Pack

## Operating contract

Apply authoritative Batch 17 Skill 651. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Recipes

```text
Monolith to Modular Commerce
Catalog Migration
Price Engine
Promotion Rules
Inventory Service
Cart
Order Management
Payment Adapter
Fulfilment
Return/Refund
Search Index
```

## Hard Rules

* 业务规则先提升为Policy Model；
* Promotion Recipe需大量边界测试；
* 库存使用明确Consistency；
* Search是派生数据；
* 订单事件保持因果顺序；
* 支付Adapter隔离Provider；
* Flash Sale路径单独设计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
