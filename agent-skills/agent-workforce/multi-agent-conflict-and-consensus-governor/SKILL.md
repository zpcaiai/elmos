---
name: multi-agent-conflict-and-consensus-governor
description: "Execute authoritative Batch 16 Skill 549 for 处理Agent之间事实、建议、计划和资源冲突。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Multi Agent Conflict And Consensus Governor

## Operating contract

Apply authoritative Batch 16 Skill 549. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

处理Agent之间事实、建议、计划和资源冲突。

## Conflict Types

```text
Fact Conflict
Policy Conflict
Goal Conflict
Resource Conflict
Prediction Conflict
Action Conflict
Ownership Conflict
```

## Resolution

```text
Source Priority
Independent Verification
Policy Precedence
Human Arbitration
Experiment
Defer
Stop
```

## Hard Rules

* 多数票不自动代表正确；
* Policy冲突优先停止；
* Fact冲突需比较来源；
* 高风险冲突交人类；
* Agent不能反复辩论无限消耗；
* 冲突和解决进入审计；
* 重复冲突需调整组织和Prompt。

## Acceptance Criteria

* 冲突被显式检测；
* 解决规则可解释；
* 高风险冲突不自动执行；
* 资源争夺受控；
* 冲突学习进入知识库；
* 不存在静默覆盖。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
