---
name: manufacturing-migration-recipe-pack
description: "Execute authoritative Batch 17 Skill 623 for manufacturing migration recipe pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Manufacturing Migration Recipe Pack

## Operating contract

Apply authoritative Batch 17 Skill 623. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Recipes

```text
C# HMI Modernization
Java MES Modernization
OPC UA Adapter
Tag Mapping
Alarm Migration
Historian Integration
Work Order Workflow
Recipe Management
Edge Service
Offline Synchronization
```

## Hard Rules

* Tag地址与业务名称分开；
* Alarm Priority和Ack语义保持；
* Recipe版本不可覆盖；
* 设备写入默认Disabled；
* Edge Store-and-forward可恢复；
* Vendor SDK封装在Compatibility Boundary；
* Factory Acceptance Test必须支持。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
