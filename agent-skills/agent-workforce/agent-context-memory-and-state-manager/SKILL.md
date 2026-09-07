---
name: agent-context-memory-and-state-manager
description: "Execute authoritative Batch 16 Skill 539 for 管理Agent会话上下文、工作记忆、长期记忆和业务状态。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Context Memory And State Manager

## Operating contract

Apply authoritative Batch 16 Skill 539. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理Agent会话上下文、工作记忆、长期记忆和业务状态。

## Memory Types

```text
Ephemeral Context
Task Memory
Working State
Case Memory
Organizational Knowledge
User Preference
Agent Learning
```

## Memory Record

```yaml
memory:
  memory_id: string
  agent_id: string
  scope: task
  source: string
  confidence: number
  expiry: string
  classification: confidential
```

## Memory治理

* 来源；
  -置信度；
  -版本；
  -权限；
  -保留；
  -更正；
  -删除；
  -引用；
  -污染检测。

## Hard Rules

* 模型输出不能自动成为可信长期记忆；
* Memory必须保留来源；
* 不同Tenant隔离；
* Secret不得进入长期Memory；
* 过期事实需失效；
* 用户可以纠正个人相关记忆；
* Memory Poisoning需检测。

## Acceptance Criteria

* Context最小充分；
* Memory可追溯；
* 错误事实可更正；
* 过期数据不再使用；
* 敏感信息受控；
* Agent重启可安全恢复任务状态。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
