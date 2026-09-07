---
name: agent-performance-and-digital-worker-scorecard
description: "Execute authoritative Batch 16 Skill 550 for 衡量Agent的质量、速度、成本、安全、采用和业务结果。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Performance And Digital Worker Scorecard

## Operating contract

Apply authoritative Batch 16 Skill 550. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

衡量Agent的质量、速度、成本、安全、采用和业务结果。

## Scorecard

```yaml
agent_scorecard:
  agent_id: string

  quality:
    accuracy: number
    verification_pass_rate: number

  operations:
    success_rate: number
    exception_rate: number
    override_rate: number

  economics:
    cost_per_outcome: number

  safety:
    policy_violations: integer
```

## 指标

* 任务成功率；
  -首次通过率；
  -人工修正率；
  -拒绝率；
  -升级率；
  -延迟；
  -成本；
  -业务Outcome；
  -用户信任；
  -安全事件；
  -稳定性。

## Hard Rules

* 完成任务数不能代表质量；
* 高自主率不一定更好；
* Agent与人工基线比较；
* 安全事件权重大于速度；
* Score需按任务难度调整；
* 指标不能诱导Agent隐藏例外；
* 低绩效Agent需降级或退役。

## Acceptance Criteria

* Agent价值可衡量；
* 质量和成本同时可见；
* 低质量Agent得到处理；
* 业务Outcome与Agent关联；
* Score可用于自主等级调整；
* 无虚荣指标驱动。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
