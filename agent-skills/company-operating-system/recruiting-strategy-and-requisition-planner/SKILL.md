---
name: recruiting-strategy-and-requisition-planner
description: "Execute authoritative Batch 15 Skill 482 for 将Headcount计划转化为岗位优先级、招聘渠道和招聘周期。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Recruiting Strategy And Requisition Planner

## Operating contract

Apply authoritative Batch 15 Skill 482. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将Headcount计划转化为岗位优先级、招聘渠道和招聘周期。

## Requisition

```yaml
requisition:
  requisition_id: string
  role_id: string
  headcount_plan_id: string
  priority: critical
  target_start_date: string
  budget_range: {}
  hiring_manager: string
```

## 招聘优先级

```text
Critical-path
Revenue-enabling
Risk-reducing
Capacity
Replacement
Strategic Option
```

## Build、Buy、Borrow

对每项能力决定：

* 内部培养；
  -外部招聘；
  -顾问；
  -伙伴；
  -短期Contractor；
  -收购团队。

## Hard Rules

* 无批准Headcount不得开Req；
* 每个Req需有Scorecard；
* Hiring Manager必须投入时间；
* 关键岗位需有Sourcing策略；
* 招聘周期进入项目预测；
* 不能长期依赖招聘解决错误优先级；
* 关闭Req需记录原因。

## Acceptance Criteria

* 招聘与Headcount计划一致；
* 关键岗位优先；
* 渠道和预算明确；
* 时间预期合理；
* Hiring Manager责任清晰；
* 招聘Pipeline可预测。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
