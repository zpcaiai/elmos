---
name: telecom-bss-oss-network-function-recipe-pack
description: "Execute authoritative Batch 17 Skill 658 for telecom bss oss network function recipe pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Telecom Bss Oss Network Function Recipe Pack

## Operating contract

Apply authoritative Batch 17 Skill 658. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Recipes

```text
CRM/Customer
Product Catalog
Order Management
Service Inventory
Resource Inventory
Provisioning
Mediation
Charging
Billing
Assurance
Trouble Ticket
5G SBA API Adapter
```

## Hard Rules

* BSS和OSS对象不可简单合并；
* Product、Service和Resource层次保持；
* Usage处理支持高吞吐和重放；
* Charging计算使用确定性规则；
* Network Function API需授权；
* Legacy Protocol通过Adapter；
* 业务和网络流程使用Saga或状态机。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
