---
name: master-data-management-and-entity-resolution
description: "Execute authoritative Batch 18 Skill 700 for 合并客户、员工、供应商、产品和地点主数据。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Master Data Management And Entity Resolution

## Operating contract

Apply authoritative Batch 18 Skill 700. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

合并客户、员工、供应商、产品和地点主数据。

## Match类型

```text
Exact
Deterministic
Probabilistic
Manual
No-match
Conflict
```

## Hard Rules

* 自动Merge必须可撤销；
* Golden Record有来源；
* 冲突字段有规则；
* 隐私和Consent限制合并；
* 同名企业和个人谨慎处理；
* 历史ID保留；
* Merge和Unmerge均审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
