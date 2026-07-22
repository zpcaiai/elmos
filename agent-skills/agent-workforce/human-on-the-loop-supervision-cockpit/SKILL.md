---
name: human-on-the-loop-supervision-cockpit
description: "Execute authoritative Batch 16 Skill 556 for 让人类监督大量有界自主Agent，而无需逐项审批。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Human On The Loop Supervision Cockpit

## Operating contract

Apply authoritative Batch 16 Skill 556. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

让人类监督大量有界自主Agent，而无需逐项审批。

## Cockpit Views

```text
Objectives
Active Agents
Current Actions
Budget
Exceptions
Risk
Policy Violations
Drift
Business Outcomes
Stop Controls
```

## Supervision Levels

* 实时；
  -异常驱动；
  -每日汇总；
  -周期Review；
  -随机抽检。

## Hard Rules

* 高自主Agent必须可实时停止；
* 关键异常主动推送；
* Dashboard不能只显示成功率；
* 人类需能钻取具体行动；
* Supervisory Span需有上限；
* Cockpit不可成为只读展示；
* Agent数量增加需增加监督容量。

## Acceptance Criteria

* 人类可监督Agent组合；
* 异常及时发现；
* Budget和风险透明；
* 可快速暂停；
* 抽检机制有效；
* 单个经理监督范围合理。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
