---
name: itsm-cmdb-and-support-integration
description: "Execute authoritative Batch 18 Skill 722 for itsm cmdb and support integration. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Itsm Cmdb And Support Integration

## Operating contract

Apply authoritative Batch 18 Skill 722. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## 范围

```text
Asset
Configuration Item
Ticket
Incident
Problem
Change
Knowledge
Service Catalog
SLA
```

## Hard Rules

* 工单历史可查询；
* CMDB数据质量先评估；
* Service Owner统一；
* SLA变化通知客户；
* Day 1支持入口明确；
* 双Ticket系统期间有路由；
* 旧系统关闭前知识迁移。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
