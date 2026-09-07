---
name: multi-agent-team-and-organization-topology
description: "Execute authoritative Batch 16 Skill 537 for 设计Supervisor、Specialist、Verifier和Observer组成的Agent团队。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Multi Agent Team And Organization Topology

## Operating contract

Apply authoritative Batch 16 Skill 537. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

设计Supervisor、Specialist、Verifier和Observer组成的Agent团队。

## Agent Team模式

```text
Supervisor–Worker
Planner–Executor
Generator–Reviewer
Researcher–Synthesizer
Debate
Pipeline
Event-driven Specialists
```

## Team Record

```yaml
agent_team:
  team_id: sales-account-research
  human_manager: sales-operations

  agents:
    - research-agent
    - data-verification-agent
    - summary-agent

  shared_budget: {}
  shared_objective: string
```

## Hard Rules

* 多Agent仅在复杂度有真实收益时使用；
* Supervisor不能成为不可解释单点；
* Verifier需与Generator使用独立检查；
* Agent循环次数有限；
* 团队共享Memory需权限控制；
* Agent通信需要Schema；
* 失败传播需被隔离。

## Acceptance Criteria

* 团队结构与任务匹配；
* Agent通信可观测；
* 循环和成本受控；
* 验证角色独立；
* 结果优于单Agent基线；
* Human Manager可监督团队。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
