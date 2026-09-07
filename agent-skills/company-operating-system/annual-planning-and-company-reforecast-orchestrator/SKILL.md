---
name: annual-planning-and-company-reforecast-orchestrator
description: "Execute authoritative Batch 15 Skill 523 for 统一管理战略、预算、OKR、Headcount和董事会批准版本。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Annual Planning And Company Reforecast Orchestrator

## Operating contract

Apply authoritative Batch 15 Skill 523. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

统一管理战略、预算、OKR、Headcount和董事会批准版本。

## Planning Versions

```text
Strategic Draft
Management Draft
Finance Baseline
Executive Approved
Board Approved
Reforecast 1
Reforecast 2
```

## Cross-checks

```text
Revenue Plan ↔ Sales Capacity
Service Revenue ↔ Delivery Capacity
Product Roadmap ↔ Engineering Capacity
Headcount ↔ Hiring Capacity
Expenses ↔ Cash
Strategy ↔ OKRs
Budget ↔ Capital
```

## Hard Rules

* 不允许不同部门使用不一致增长假设；
* Board-approved版本不可静默覆盖；
* Reforecast需保留原Budget；
* 计划需包含客户和市场风险；
* 资源不足需调整目标；
* 战略变更触发重新对齐；
* 年度规划流程需有截止时间。

## Acceptance Criteria

* 公司计划内部一致；
* 预算和OKR使用同一版本；
* 再预测可及时完成；
* 重大矛盾自动发现；
* 管理层和董事会批准清楚；
* 计划可用于实际经营。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
