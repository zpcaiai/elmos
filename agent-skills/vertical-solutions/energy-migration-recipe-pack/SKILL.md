---
name: energy-migration-recipe-pack
description: "Execute authoritative Batch 17 Skill 630 for energy migration recipe pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Energy Migration Recipe Pack

## Operating contract

Apply authoritative Batch 17 Skill 630. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Recipes

```text
SCADA Adapter
EMS/DMS Service Migration
Meter Data Management
Outage Management
DER Integration
Forecast Service
Market/Settlement Adapter
Historian Migration
Edge Gateway
```

## Hard Rules

* 控制面和分析面分开；
* 遥测丢失和质量差异可检测；
* 时序数据精度保持；
* 大规模数据迁移支持分区；
* 调度Algorithm需行为对比；
* OT Protocol通过受控Adapter；
* 不能将模拟结果直接替代现场验证。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
