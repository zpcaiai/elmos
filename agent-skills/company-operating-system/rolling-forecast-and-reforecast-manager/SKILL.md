---
name: rolling-forecast-and-reforecast-manager
description: "Execute authoritative Batch 15 Skill 499 for 基于实际经营、Pipeline、Hiring和成本持续更新未来预测。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Rolling Forecast And Reforecast Manager

## Operating contract

Apply authoritative Batch 15 Skill 499. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

基于实际经营、Pipeline、Hiring和成本持续更新未来预测。

## Forecast Horizon

建议保持：

```text
未来十八至二十四个月滚动预测
```

## Reforecast Triggers

* 重大赢单或输单；
  -客户流失；
  -融资；
  -招聘偏差；
  -成本激增；
  -产品延迟；
  -地区扩张；
  -重大事故；
  -汇率；
  -战略调整。

## Hard Rules

* Forecast不是修改预算历史；
* Actual、Budget和Forecast分开；
* 每次Forecast有Assumption变化；
* 管理层不得压制Downside；
* Pipeline需使用最新阶段；
* Hiring需考虑Start Date；
* Forecast变化需影响现金计划。

## Acceptance Criteria

* 公司始终有最新预测；
* 现金风险提前发现；
* 预算偏差可解释；
* 战略调整反映在数字中；
* 董事会获得真实展望；
* Forecast准确度可回测。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
