---
name: workforce-transition-and-role-migration-manager
description: "Execute authoritative Batch 16 Skill 577 for 管理AI带来的岗位变化、人员转型、再培训和组织调整。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Workforce Transition And Role Migration Manager

## Operating contract

Apply authoritative Batch 16 Skill 577. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理AI带来的岗位变化、人员转型、再培训和组织调整。

## Transition Categories

```text
Task Augmentation
Role Redesign
Role Consolidation
New Role Creation
Reskilling
Redeployment
Natural Attrition
Role Elimination
```

## Transition Plan

```yaml
workforce_transition:
  role_family: support
  affected_people: integer
  future_roles: []
  training: []
  timeline: string
  employee_support: []
```

## Hard Rules

* 不把效率假设直接转化裁员；
* 实际工作量需验证；
* 员工提前获得清晰信息；
* 地区劳动法律需专业确认；
* 提供培训和内部流动；
* 人员决策必须由人类负责；
* 转型影响进入风险和文化管理。

## Acceptance Criteria

* 受影响岗位有计划；
* 员工知道未来能力要求；
* 转岗和培训可执行；
* 关键知识不丢失；
* 组织能力持续；
* 变革信任得到维护。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
