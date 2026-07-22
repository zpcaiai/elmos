---
name: human-in-the-loop-workbench
description: "Execute authoritative Batch 16 Skill 555 for 为员工提供审查、修改、批准、拒绝和反馈Agent结果的工作台。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Human In The Loop Workbench

## Operating contract

Apply authoritative Batch 16 Skill 555. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

为员工提供审查、修改、批准、拒绝和反馈Agent结果的工作台。

## Workbench Components

```text
Task Context
Agent Proposal
Evidence
Confidence
Alternatives
Risk
Diff
Approval
Edit
Reject
Feedback
```

## UX原则

* 重点突出变化；
  -显示来源；
  -显示不确定性；
  -支持批量但限制风险；
  -减少重复审查；
  -记录人工修改；
  -解释为何需要审批。

## Hard Rules

* 不使用诱导性默认批准；
* 高风险操作不允许一键批量；
* Human Reviewer需看到完整影响；
* 修改后需重新验证；
* 审批者不能被大量低价值警报淹没；
* 用户反馈进入Eval；
* 无障碍和移动需求按岗位考虑。

## Acceptance Criteria

* 人工审查高效；
* 关键风险可见；
* 修改记录完整；
* Approval质量提升；
* 员工愿意使用；
* 自动化节省大于审查成本。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
