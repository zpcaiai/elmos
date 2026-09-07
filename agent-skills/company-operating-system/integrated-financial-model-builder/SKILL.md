---
name: integrated-financial-model-builder
description: "Execute authoritative Batch 15 Skill 493 for 建立收入、费用、现金流、资产负债和关键经营指标的综合财务模型。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Integrated Financial Model Builder

## Operating contract

Apply authoritative Batch 15 Skill 493. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立收入、费用、现金流、资产负债和关键经营指标的综合财务模型。

## Model Structure

```text
Assumptions
Revenue
Cost of Revenue
Gross Profit
Operating Expenses
EBITDA / Operating Result
Working Capital
Capital Expenditure
Cash Flow
Balance Sheet
Runway
KPIs
```

## Forecast Grain

建议：

* 未来二十四个月按月；
  -之后按季度或年度；
  -按产品、地区、渠道或业务线拆分；
  -可汇总公司整体。

## Hard Rules

* 模型需使用双录或校验机制；
* 收入确认与Bookings分开；
* Cash与利润分开；
* 公式不得被手工值覆盖而无说明；
* Assumption集中管理；
* 版本需锁定；
* 实际数据定期导入。

## Acceptance Criteria

* 三表或等价模型闭合；
* 现金可预测；
* 收入和成本驱动明确；
* 情景可快速切换；
* 董事会数字与财务数字一致；
* 模型可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
