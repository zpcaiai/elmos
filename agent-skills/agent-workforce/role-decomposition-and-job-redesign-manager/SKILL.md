---
name: role-decomposition-and-job-redesign-manager
description: "Execute authoritative Batch 16 Skill 530 for 将岗位拆解为Outcome、决策、任务、关系和能力，再重新组合人类与Agent工作。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Role Decomposition And Job Redesign Manager

## Operating contract

Apply authoritative Batch 16 Skill 530. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

将岗位拆解为Outcome、决策、任务、关系和能力，再重新组合人类与Agent工作。

## Role Decomposition

```text
Role Purpose
├── Outcomes
├── Decisions
├── Repeatable Tasks
├── Exceptions
├── Relationships
├── Knowledge
└── Accountability
```

## Job Redesign

```yaml
redesigned_role:
  role_id: customer-success-manager

  human_responsibilities:
    - executive-relationship
    - risk-negotiation
    - renewal-strategy

  agent_responsibilities:
    - usage-monitoring
    - health-summary
    - action-drafting
    - meeting-preparation
```

## Hard Rules

* 不能只把旧任务自动化后保留旧岗位；
* 责任和工作量变化需同步职级；
* 员工仍需理解Agent工作；
* Agent不能成为无人负责的“虚拟同事”；
* 岗位重构需考虑工作意义；
* 降低工时需有人员转型计划；
* 新岗位需重新定义能力和绩效。

## Acceptance Criteria

* 关键岗位完成拆解；
* 人类工作聚焦判断和关系；
* Agent工作边界明确；
* 岗位工作量重新估算；
* 职级和薪酬可更新；
* 员工获得转型路径。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
