---
name: records-retention-and-legal-hold-integration
description: "Execute authoritative Batch 18 Skill 704 for 统一保留计划、诉讼保全、审计和销毁。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Records Retention And Legal Hold Integration

## Operating contract

Apply authoritative Batch 18 Skill 704. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

统一保留计划、诉讼保全、审计和销毁。

## Hard Rules

* 合并Retention不能简单取最短；
* Legal Hold优先；
* 被收购方历史记录可恢复；
* Backup进入保留范围；
* 退役系统前完成归档；
* 重复记录删除需审慎；
* 销毁产生证明。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
