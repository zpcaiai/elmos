---
name: master-data-distribution-and-synchronization
description: "Execute authoritative Batch 18 Skill 710 for 把集团主数据可靠分发至各应用。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Master Data Distribution And Synchronization

## Operating contract

Apply authoritative Batch 18 Skill 710. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

把集团主数据可靠分发至各应用。

## Hard Rules

* 主数据来源唯一；
* Consumer知道版本；
* 删除和失效传播；
* 离线系统支持缓冲；
* 数据域权限不扩大；
* 分发失败可重放；
* 旧同步方式有退出计划。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
