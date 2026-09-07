---
name: commerce-scale-and-business-rule-evaluation
description: "Execute authoritative Batch 17 Skill 652 for commerce scale and business rule evaluation. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Commerce Scale And Business Rule Evaluation

## Operating contract

Apply authoritative Batch 17 Skill 652. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Cases

```text
Flash Sale
Hot SKU
Duplicate Checkout
Payment Timeout
Inventory Race
Promotion Stacking
Partial Shipment
Partial Refund
Seller Conflict
Search Lag
```

## Critical Gate

```text
重复订单Effect = 0
超额退款 = 0
库存负数或丢失 = 0
错误支付状态 = 0
跨Seller数据泄漏 = 0
```

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
