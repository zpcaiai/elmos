---
name: telecom-domain-model
description: "Execute authoritative Batch 17 Skill 655 for telecom domain model. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Telecom Domain Model

## Operating contract

Apply authoritative Batch 17 Skill 655. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## 核心领域

```text
Customer
Subscriber
Account
SIM/eSIM
Device
Product
Offer
Service
Resource
Network Function
Session
Usage Record
Policy
Charge
Bill
Order
Trouble Ticket
Network Event
```

## Invariant

```text
Subscriber与服务关联有效
网络资源分配可追踪
Usage Record不重复不丢失
Charge和Tariff版本一致
Provisioning状态合法
订单、服务和资源保持关联
```

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
