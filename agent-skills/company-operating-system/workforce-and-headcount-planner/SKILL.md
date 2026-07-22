---
name: workforce-and-headcount-planner
description: "Execute authoritative Batch 15 Skill 480 for 根据战略、产能、预算和组织结构制定Headcount计划。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Workforce And Headcount Planner

## Operating contract

Apply authoritative Batch 15 Skill 480. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

根据战略、产能、预算和组织结构制定Headcount计划。

## Workforce Plan

```yaml
headcount_plan:
  period: 2027
  function: engineering
  opening_headcount: 20
  hires: 12
  attrition: 3
  ending_headcount: 29
```

## Demand Drivers

* Roadmap；
  -销售Pipeline；
  -交付项目；
  -支持；
  -地区扩张；
  -监管；
  -平台可靠性；
  -管理跨度；
  -替补；
  -休假；
  -生产力假设。

## Supply Options

```text
Hire
Develop
Contract
Partner
Automate
Outsource
Stop Work
```

## Hard Rules

* Headcount不能只由部门愿望决定；
* 所有新增岗位需有业务驱动；
* 招聘成本和Ramp时间需进入模型；
* Contractor和Partner也需计入容量；
* 高增长计划需考虑管理者；
* 未获预算岗位不得发布；
* 招聘计划需按月更新。

## Acceptance Criteria

* Headcount与战略一致；
* Headcount与预算一致；
* 关键能力Gap明确；
* 招聘时间进入计划；
* 组织承载能力可见；
* 实际与计划持续比较。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
