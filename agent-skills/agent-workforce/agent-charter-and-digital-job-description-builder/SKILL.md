---
name: agent-charter-and-digital-job-description-builder
description: "Execute authoritative Batch 16 Skill 533 for 为每个Agent建立正式数字岗位说明和运营章程。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Charter And Digital Job Description Builder

## Operating contract

Apply authoritative Batch 16 Skill 533. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

为每个Agent建立正式数字岗位说明和运营章程。

## Agent Charter

```yaml
agent_charter:
  agent_id: finance-reconciliation-agent
  purpose: 提高账务对账速度和准确性

  human_owner: finance-controller
  risk_tier: medium
  autonomy_level: A4

  allowed_tasks: []
  forbidden_tasks: []
  tools: []
  data_scopes: []
  budget: {}
  escalation: {}
  success_metrics: []
```

## Charter必须包含

* 目的；
  -用户；
  -输入；
  -输出；
  -决策；
  -工具；
  -数据；
  -权限；
  -预算；
  -SLA；
  -风险；
  -例外；
  -评测；
  -停止；
  -退役。

## Hard Rules

* 无Charter不得进入生产；
* Purpose不能只写“提高效率”；
* 禁止任务明确；
* Tool和Data必须Allowlist；
* 自主级别明确；
* Charter变更触发重新评测；
* Charter需Human Owner批准。

## Acceptance Criteria

* 所有生产Agent有Charter；
* 任务和权限一致；
* 禁止行为可执行；
* 指标可衡量；
* 例外和停止机制完整；
* 人类Owner正式接受责任。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
