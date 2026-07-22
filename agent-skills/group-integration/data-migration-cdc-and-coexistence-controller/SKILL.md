---
name: data-migration-cdc-and-coexistence-controller
description: "Execute authoritative Batch 18 Skill 702 for 执行全量、增量、双运行和最终切换。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Data Migration Cdc And Coexistence Controller

## Operating contract

Apply authoritative Batch 18 Skill 702. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

执行全量、增量、双运行和最终切换。

## Hard Rules

* 每个数据域有权威写入者；
* 删除和撤销必须同步；
* CDC Position持久化；
* Backfill可恢复；
* Schema变化受控；
* 双写差异实时监控；
* Final Delta核对后才切换。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
