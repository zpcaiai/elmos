---
name: exception-escalation-and-human-takeover-manager
description: "Execute authoritative Batch 16 Skill 545 for 识别Agent无法处理的例外，并将任务连同上下文移交给人类。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Exception Escalation And Human Takeover Manager

## Operating contract

Apply authoritative Batch 16 Skill 545. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

识别Agent无法处理的例外，并将任务连同上下文移交给人类。

## Escalation Conditions

* 置信度不足；
  -政策冲突；
  -未知状态；
  -工具失败；
  -重复失败；
  -客户投诉；
  -安全信号；
  -金额异常；
  -多Agent冲突；
  -目标不可满足。

## Handoff Package

```yaml
handoff:
  task_id: string
  summary: string
  actions_taken: []
  current_state: {}
  unresolved_issue: string
  recommended_options: []
  evidence: []
```

## Hard Rules

* 不允许只写“需要人工处理”；
* 已执行动作必须完整列出；
* 人类接管后Agent停止相关动作；
* 高风险升级需实时通知；
* Handoff必须保持任务状态；
* 人类结论需回写流程；
* 重复例外需推动流程重构。

## Acceptance Criteria

* 人工能快速接管；
* Context完整；
* 无重复执行；
* 例外有分类；
* 处理结果可学习；
* Escalation时延可衡量。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
