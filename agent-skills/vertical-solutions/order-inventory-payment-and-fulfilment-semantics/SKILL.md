---
name: order-inventory-payment-and-fulfilment-semantics
description: "Execute authoritative Batch 17 Skill 649 for order inventory payment and fulfilment semantics. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Order Inventory Payment And Fulfilment Semantics

## Operating contract

Apply authoritative Batch 17 Skill 649. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## 关键流程

```text
Browse
→ Cart
→ Price
→ Promotion
→ Inventory Reserve
→ Payment
→ Order Confirm
→ Fulfil
→ Ship
→ Deliver
→ Return/Refund
```

## Hard Rules

* Inventory Reserve与实际扣减区分；
* Price Snapshot保留；
* Promotion应用顺序明确；
* Payment Timeout后检查实际状态；
* Order Retry幂等；
* Shipment可分单；
* Refund和Return分开。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
