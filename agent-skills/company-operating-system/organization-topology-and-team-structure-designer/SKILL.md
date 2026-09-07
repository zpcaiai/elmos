---
name: organization-topology-and-team-structure-designer
description: "Execute authoritative Batch 15 Skill 478 for 设计公司部门、团队、平台组、业务组和治理职能。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Organization Topology And Team Structure Designer

## Operating contract

Apply authoritative Batch 15 Skill 478. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

设计公司部门、团队、平台组、业务组和治理职能。

## Team Types

```text
Stream-aligned
Platform
Enabling
Complicated-subsystem
Functional Center
Regional Team
Customer-facing Pod
```

## Team Charter

```yaml
team:
  team_id: migration-engine
  mission: string
  customers: []
  outcomes: []
  responsibilities: []
  interfaces: []
  dependencies: []
```

## 管理跨度

需考虑：

* 工作复杂度；
  -人员成熟度；
  -管理者经验；
  -地域；
  -任务标准化；
  -协作密度；
  -变更速度。

## Hard Rules

* 无明确Mission的团队不得长期存在；
* 团队不能拥有无法控制的结果；
* 平台团队需有内部客户和SLO；
* 临时项目组需有结束条件；
* 管理层级不应超过必要数量；
* 地区团队与总部责任需明确；
* 重组需同步角色、预算和系统权限。

## Acceptance Criteria

* 组织图与真实工作一致；
* 每个团队有Charter；
* 依赖和接口清晰；
* 管理跨度合理；
* 平台和业务团队协作有效；
* 组织结构可随阶段演化。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
