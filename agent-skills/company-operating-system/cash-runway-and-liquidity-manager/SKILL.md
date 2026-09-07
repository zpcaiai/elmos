---
name: cash-runway-and-liquidity-manager
description: "Execute authoritative Batch 15 Skill 496 for 预测现金收支、最低现金、Runway和流动性风险。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Cash Runway And Liquidity Manager

## Operating contract

Apply authoritative Batch 15 Skill 496. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

预测现金收支、最低现金、Runway和流动性风险。

## Cash Forecast

```text
Opening Cash
+ Customer Collections
+ Financing
- Payroll
- Vendor Payments
- Taxes
- Capex
- Debt Service
= Ending Cash
```

## Runway

需基于：

* 当前现金；
  -净Burn；
  -增长投资；
  -回款时间；
  -融资情景；
  -Downside；
  -最低运营现金。

## Liquidity Triggers

```text
18个月：启动融资或盈利计划
12个月：限制可选投资
9个月：强化现金管理
6个月：执行生存计划
```

具体阈值由公司阶段和融资环境决定。

## Hard Rules

* Runway不能只用过去一个月Burn；
* 需考虑应收回款延迟；
* 薪资、税和关键供应商优先；
* Restricted Cash需分开；
* 融资到账前不能视为现金；
* Downside Runway必须计算；
* 现金风险需及时通知董事会。

## Acceptance Criteria

* 每月现金可预测；
* 最低现金阈值明确；
* 融资时间窗口可判断；
* Downside生存计划存在；
* 应收和付款计划可管理；
* 无意外现金危机。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
