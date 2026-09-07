---
name: people-and-organization-analytics-manager
description: "Execute authoritative Batch 15 Skill 492 for 将Headcount、招聘、绩效、薪酬、流失和组织健康转化为经营分析。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# People And Organization Analytics Manager

## Operating contract

Apply authoritative Batch 15 Skill 492. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将Headcount、招聘、绩效、薪酬、流失和组织健康转化为经营分析。

## Metrics

```text
Headcount
Open Requisitions
Hiring Velocity
Attrition
Regrettable Attrition
Span of Control
Layer Count
Internal Mobility
Performance Distribution
Compensation Position
Engagement
Productivity Proxy
```

## Hard Rules

* 人才数据需保护隐私；
* 小团队不得过度细分；
* Productivity不能简单用代码行衡量；
* 相关性不能直接推断因果；
* 敏感属性分析需合法；
* 管理层只能查看必要范围；
* 指标需用于改善而非监控个体。

## Acceptance Criteria

* 人力成本可预测；
* 招聘和流失趋势可见；
* 组织失衡可识别；
* 薪酬公平可分析；
* 管理跨度可优化；
* 人才数据支持战略。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
