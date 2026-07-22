---
name: agent-workforce-organization-model
description: "Execute authoritative Batch 16 Skill 532 for 把Agent作为受治理的数字岗位，纳入组织、成本、能力和绩效体系。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Workforce Organization Model

## Operating contract

Apply authoritative Batch 16 Skill 532. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

把Agent作为受治理的数字岗位，纳入组织、成本、能力和绩效体系。

## Agent Workforce层级

```text
Company Agent Portfolio
└── Function Agent Team
    ├── Supervisor Agent
    ├── Specialist Agent
    ├── Verification Agent
    └── Observer Agent
```

## Agent关系

每个Agent属于：

* 一个业务功能；
  -一个Human Manager；
  -一个Cost Center；
  -一个Risk Tier；
  -一个Agent Team；
  -一个生命周期状态。

## Agent状态

```text
draft
evaluating
shadow
approval-gated
bounded-autonomous
suspended
quarantined
deprecated
retired
```

## Hard Rules

* Agent数量不能成为AI成熟度指标；
* 每个Agent需有业务Outcome；
* 重复Agent需要合并；
* 不活跃Agent需退役；
* Supervisor不能无限创建子Agent；
* Agent Team需有总预算；
* Agent Portfolio定期复盘。

## Acceptance Criteria

* Agent Workforce可完整查询；
* Agent成本归属清晰；
* Agent组织和公司组织关联；
* 生命周期可治理；
* 重复和无价值Agent减少；
* Agent组合支持战略重点。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
