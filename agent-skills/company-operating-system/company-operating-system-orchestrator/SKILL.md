---
name: company-operating-system-orchestrator
description: "Execute authoritative Batch 15 Skill 461 for 将战略、OKR、组织、预算、融资、风险和董事会流程编排为统一公司经营系统。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Company Operating System Orchestrator

## Operating contract

Apply authoritative Batch 15 Skill 461. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将战略、OKR、组织、预算、融资、风险和董事会流程编排为统一公司经营系统。

## Inputs

```yaml
company_operating_cycle:
  fiscal_year: string
  planning_horizon:
    strategy_years: 3
    forecast_months: 24

  company_stage:
    - pre-revenue
    - early-revenue
    - growth
    - scale
    - mature

  strategic_constraints:
    capital: number
    headcount: integer
    runway_months: number
```

## Workflow

1. 更新公司事实基线。
2. 执行战略诊断。
3. 更新长期战略。
4. 制定年度战略。
5. 建立财务情景。
6. 分配战略资源。
7. 生成公司OKR。
8. 生成部门和团队OKR。
9. 生成组织和Headcount计划。
10. 生成年度预算。
11. 获取管理层承诺。
12. 获取董事会审批。
13. 进入季度经营周期。
14. 执行月度和季度再预测。
15. 记录决策和行动。
16. 年度结束后复盘。

## Hard Rules

* 战略、OKR、预算和Headcount必须使用同一假设；
* 未获资金支持的战略不能标记Committed；
* 董事会批准版本必须锁定；
* 实际发生重大变化时必须再预测；
* 经营系统必须有明确Owner；
* 不能用会议代替决策；
* 所有重大决策必须进入Decision Log。

## Acceptance Criteria

* 年度经营周期完整；
* 战略与预算一致；
* OKR与战略一致；
* Headcount与预算一致；
* 董事会审批可追踪；
* 实际与计划可比较。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
