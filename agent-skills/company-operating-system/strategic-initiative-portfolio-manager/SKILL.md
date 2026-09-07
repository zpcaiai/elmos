---
name: strategic-initiative-portfolio-manager
description: "Execute authoritative Batch 15 Skill 469 for 将年度战略转化为有限数量的跨部门战略项目。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Strategic Initiative Portfolio Manager

## Operating contract

Apply authoritative Batch 15 Skill 469. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将年度战略转化为有限数量的跨部门战略项目。

## Initiative

```yaml
strategic_initiative:
  initiative_id: repeatable-poc-factory
  annual_priority_id: string
  sponsor: string
  owner: string
  outcomes: []
  milestones: []
  budget: number
```

## Initiative Gate

```text
Proposed
Diagnosed
Approved
Funded
In Execution
At Risk
Completed
Stopped
Benefits Review
```

## Hard Rules

* 每个Initiative必须对应战略优先级；
* 不能将普通部门项目全部标成战略项目；
* Sponsor和Owner需分开；
* Initiative需有终止条件；
* 跨部门依赖必须明确；
* 完成项目不等于实现收益；
* Benefits需在完成后复盘。

## Acceptance Criteria

* 战略项目数量受控；
* 每项有资源和Owner；
* 里程碑可追踪；
* 风险及时升级；
* 完成后验证结果；
* 无战略关系项目不会占用战略预算。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
