---
name: agent-workflow-compiler
description: "Execute authoritative Batch 16 Skill 543 for 把业务目标、政策、流程和Agent角色编译为可执行、可验证工作流。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Workflow Compiler

## Operating contract

Apply authoritative Batch 16 Skill 543. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

把业务目标、政策、流程和Agent角色编译为可执行、可验证工作流。

## Workflow Definition

```yaml
workflow:
  workflow_id: customer-renewal-risk
  objective: 降低高价值客户流失

  steps:
    - collect-signals
    - compute-risk
    - generate-plan
    - human-review
    - execute-actions
    - monitor-result
```

## 编译结果

* 状态机；
  -Task；
  -Agent分配；
  -工具；
  -审批；
  -预算；
  -超时；
  -补偿；
  -观察点；
  -停止条件。

## Hard Rules

* 关键流程必须显式状态；
* 不允许隐藏无限循环；
* 每一步有输入输出Schema；
* 写动作需补偿或回滚策略；
* Workflow版本不可覆盖；
* 政策变化触发重新编译；
* 运行实例绑定Workflow版本。

## Acceptance Criteria

* 经营流程可执行；
* 状态清晰；
* Human Gate正确；
* 失败可恢复；
* Workflow可模拟；
* 多Agent协作可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
