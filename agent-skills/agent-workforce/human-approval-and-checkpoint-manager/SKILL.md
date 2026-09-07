---
name: human-approval-and-checkpoint-manager
description: "Execute authoritative Batch 16 Skill 544 for 在高风险、低置信度和不可逆步骤设置人工审批。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Human Approval And Checkpoint Manager

## Operating contract

Apply authoritative Batch 16 Skill 544. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

在高风险、低置信度和不可逆步骤设置人工审批。

## Approval Trigger

```text
金额超限
低置信度
政策冲突
高风险客户
不可逆动作
外部公开沟通
法律或人事动作
异常模式
模型变更
```

## Approval Package

```yaml
approval:
  action_summary: string
  proposed_action: {}
  evidence: []
  alternatives: []
  risks: []
  confidence: number
  rollback: {}
```

## Hard Rules

* 审批人必须有真实权限；
* 审批信息需足够判断；
* 不能只给“同意/拒绝”而无证据；
* 审批超时有明确处理；
* Agent不能审批自身；
* 批量审批需限制范围；
* Action变化使审批失效。

## Acceptance Criteria

* 高风险步骤正确拦截；
* 审批体验高效；
* 批准基于证据；
* 自我审批为0；
* 超时不会产生危险动作；
* 审批结果可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
