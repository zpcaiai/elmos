---
name: agent-plan-act-observe-loop-controller
description: "Execute authoritative Batch 16 Skill 547 for 控制Agent的目标分解、计划、行动、观察、验证和终止循环。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Plan Act Observe Loop Controller

## Operating contract

Apply authoritative Batch 16 Skill 547. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

控制Agent的目标分解、计划、行动、观察、验证和终止循环。

## Loop

```text
Goal
→ Plan
→ Validate Plan
→ Act
→ Observe
→ Evaluate
→ Continue / Stop / Escalate
```

## Loop Budget

```yaml
loop_budget:
  max_steps: 20
  max_tool_calls: 50
  max_tokens: integer
  max_wall_time: 30m
  max_cost: number
```

## Hard Rules

* 目标必须有完成条件；
* 计划需在行动前验证；
* 循环次数有限；
* 每步观察真实结果；
* 不允许仅根据自身文本判断成功；
* 无进展需停止；
* 预算耗尽不得继续。

## Acceptance Criteria

* Agent不会无限循环；
* 成功条件客观；
* 每步有观察证据；
* 无进展可发现；
* 成本受控；
* 终止状态明确。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
