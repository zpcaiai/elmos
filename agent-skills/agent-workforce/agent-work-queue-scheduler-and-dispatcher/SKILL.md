---
name: agent-work-queue-scheduler-and-dispatcher
description: "Execute authoritative Batch 16 Skill 538 for 根据目标、优先级、能力、风险、预算和SLA分配Agent工作。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Work Queue Scheduler And Dispatcher

## Operating contract

Apply authoritative Batch 16 Skill 538. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

根据目标、优先级、能力、风险、预算和SLA分配Agent工作。

## Job Schema

```yaml
agent_job:
  job_id: string
  objective_id: string
  required_capabilities: []
  risk_tier: medium
  budget: {}
  deadline: string
  approval_policy: string
```

## 调度因素

* 业务优先级；
  -Agent能力；
  -数据权限；
  -模型；
  -成本；
  -风险；
  -并发；
  -依赖；
  -人工可用性；
  -截止时间。

## Hard Rules

* Agent只能领取能力和权限匹配任务；
* 不可恢复任务不能重复执行；
* Job需幂等或有Execution Lock；
* 低优先级不能永久饥饿；
* 预算不足时暂停而非降低安全；
* Agent失败需重新调度或升级；
* 调度决定需可解释。

## Acceptance Criteria

* 工作正确分配；
* SLA可衡量；
* 重复执行受控；
* 成本和优先级平衡；
* 队列可监控；
* 异常任务可人工接管。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
