---
name: day-one-day-hundred-plan-manager
description: "Execute authoritative Batch 18 Skill 672 for 建立Day 1、Day 30、Day 100和长期整合路线。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Day One Day Hundred Plan Manager

## Operating contract

Apply authoritative Batch 18 Skill 672. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

建立Day 1、Day 30、Day 100和长期整合路线。

## Day 1 Workstreams

```text
Legal Entity
Identity
Communications
Customer
Finance
Payroll
Security
IT Operations
Critical Applications
Supplier
Regulatory
```

## Plan Record

```yaml
integration_milestone:
  milestone: day-one
  outcome: employees-can-access-required-systems
  owner: string
  dependencies: []
  evidence: []
```

## Hard Rules

* Day 1不承担不必要系统重构；
* 每项Day 1任务有Fallback；
* Day 100目标应可衡量；
* 长期优化不能危害Day 1；
* Day 1假设在交割前演练；
* 未完成高风险事项需有TSA；
* Day 100变更需管理层批准。

## Acceptance Criteria

* Day 1关键业务可运行；
* 员工和客户获得清晰指引；
* Day 100结果可追踪；
* 临时措施有退出计划；
* 重大风险已升级。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
