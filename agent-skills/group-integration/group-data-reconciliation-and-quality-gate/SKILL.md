---
name: group-data-reconciliation-and-quality-gate
description: "Execute authoritative Batch 18 Skill 706 for group data reconciliation and quality gate. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Data Reconciliation And Quality Gate

## Operating contract

Apply authoritative Batch 18 Skill 706. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Critical Gate

```text
Authoritative Record Coverage
Duplicate Rate
Unmatched Entity Rate
Financial Balance
Referential Integrity
CDC Lag
Deletion Consistency
Privacy Compliance
```

## Hard Rules

* 聚合相同不能掩盖明细错误；
* 金融和员工数据使用更严格门槛；
* 核对结果绑定Snapshot；
* Unknown差异不能算通过；
* 数据Owner正式签字；
* 差异有修复或接受流程；
* 结果进入集团控制塔。

---

# 八、接口与集成Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
