---
name: government-legacy-modernization-recipe-pack
description: "Execute authoritative Batch 17 Skill 644 for government legacy modernization recipe pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Government Legacy Modernization Recipe Pack

## Operating contract

Apply authoritative Batch 17 Skill 644. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Recipes

```text
Legacy Form Migration
Case Management
Document Workflow
Mainframe Adapter
Citizen Portal
Identity Federation
Records Export
Batch Benefit Processing
Permit Workflow
Government Payment
```

## Hard Rules

* 法定业务规则有来源；
* PDF/Form字段需语义映射；
* 大型Batch可Restart；
* 历史决定和文档不可丢失；
* 公共API兼容；
* Accessibility进入测试；
* 旧系统Read-only归档可查询。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
