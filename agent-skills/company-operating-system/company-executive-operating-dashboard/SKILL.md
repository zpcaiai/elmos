---
name: company-executive-operating-dashboard
description: "Execute authoritative Batch 15 Skill 522 for 为CEO、管理层和董事会提供统一的公司经营驾驶舱。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Company Executive Operating Dashboard

## Operating contract

Apply authoritative Batch 15 Skill 522. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

为CEO、管理层和董事会提供统一的公司经营驾驶舱。

## Dashboard Domains

```text
Strategy
OKR
Product
Sales
Revenue
Customer
Delivery
Growth
People
Financial
Cash
Risk
Board Actions
```

## Executive Metrics

例如：

```text
ARR / Revenue
Bookings
Pipeline
NRR
Gross Margin
Cash
Runway
Headcount
Hiring
Product Activation
Customer Health
Project Delivery
Critical Risks
```

## Metric状态

```text
On Track
At Risk
Off Track
Not Measured
Data Quality Issue
```

## Hard Rules

* Dashboard使用统一定义；
* 数据新鲜度显示；
* 平均值不能掩盖关键Segment；
* 财务和经营数据可钻取；
* 管理层不能手工改Actual；
* 红色指标需关联行动；
* 董事会看到的数字与内部一致。

## Acceptance Criteria

* 公司状态一目了然；
* 指标可追溯；
* 风险和现金可见；
* 决策围绕同一事实；
* 数据质量问题暴露；
* 驾驶舱支持月度和季度经营。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
