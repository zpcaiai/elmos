---
name: batch-15-company-operating-conformance-gate
description: "Execute authoritative Batch 15 Skill 525 for 综合战略、OKR、组织、人才、财务、融资、治理、风险和董事会结果，判断公司经营系统是否达到可规模化运行标准。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Batch 15 Company Operating Conformance Gate

## Operating contract

Apply authoritative Batch 15 Skill 525. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

综合战略、OKR、组织、人才、财务、融资、治理、风险和董事会结果，判断公司经营系统是否达到可规模化运行标准。

## 核心指标

```yaml
strategy:
  mission_vision_approved: true
  annual_priorities_defined: true
  priorities_with_owner_and_budget: 1.00
  strategic_initiative_alignment: 1.00

okr:
  company_okr_measurement_coverage: 1.00
  kr_with_baseline_and_target: 1.00
  cross_function_dependency_coverage: 1.00

organization:
  team_charter_coverage: 1.00
  critical_role_charter_coverage: 1.00
  headcount_budget_alignment: passed

talent:
  critical_requisition_scorecard_coverage: 1.00
  performance_review_completion: 1.00
  succession_coverage_for_critical_roles: number

finance:
  integrated_model: passed
  monthly_close: passed
  forecast_updated: true
  downside_runway_calculated: true

fundraising:
  fundraising_readiness: assessed
  cap_table_accuracy: passed
  data_room_completeness: number

governance:
  delegation_matrix: approved
  policy_control_coverage: number
  board_actions_overdue: number

risk:
  top_risk_owner_coverage: 1.00
  zero_tolerance_risk_breaches: 0
  business_continuity_drills: passed
```

## Gate C15-A：战略清晰

```yaml
mission_and_vision: approved
multi_year_strategy: approved
annual_priorities: "3-to-5"
priority_owner_coverage: 1.00
priority_budget_coverage: 1.00
explicit_non_priorities: defined
```

## Gate C15-B：执行系统一致

```yaml
company_okr_alignment: passed
functional_okr_alignment: passed
quarterly_plan_approved: true
operating_cadence_running: true
decision_log_coverage: passed
```

## Gate C15-C：组织与人才可承载

```yaml
organization_supports_strategy: passed
critical_role_charters: complete
headcount_plan_funded: true
critical_hiring_scorecards: complete
key_person_risk_plan: passed
```

## Gate C15-D：财务和现金可控

```yaml
integrated_financial_model: passed
annual_budget: approved
monthly_close_current: true
rolling_forecast_current: true
downside_runway_above_minimum_or_plan_active: true
```

## Gate C15-E：融资和资本可治理

```yaml
capital_allocation_portfolio: approved
fundraising_strategy: current
cap_table: reconciled
equity_approvals: complete
investor_material_consistency: passed
```

## Gate C15-F：治理、风险和董事会有效

```yaml
governance_documents: current
delegation_of_authority: active
critical_control_coverage: passed
top_risk_owner_coverage: 1.00
board_calendar: active
board_action_closure: within-policy
```

## Gate C15-G：公司级规模化经营候选

```yaml
all_strategy_gates: passed
all_execution_gates: passed
all_organization_gates: passed
all_financial_gates: passed
all_capital_gates: passed
all_governance_gates: passed
critical_open_enterprise_risks: 0
company_operating_evidence_pack: complete
```

## Blocking Conditions

* 公司没有清晰战略选择；
* 年度优先级过多且无取舍；
* 战略无预算或Owner；
* OKR只是任务列表；
* 部门目标相互冲突；
* Headcount计划与预算不一致；
* 关键角色责任不清；
* 关键人员无替代方案；
* 招聘无Scorecard；
* 绩效标准因人而异；
* 薪酬和股权记录不准确；
* 财务模型不闭合；
* Cash和利润混淆；
* 无Downside Runway；
* 融资金额与里程碑不匹配；
* Cap Table不准确；
* 融资材料数字不一致；
* 管理层绕过董事会保留事项；
* 高风险操作无授权矩阵；
* 关键内控仅存在于文档；
* Top Risk无Owner；
* 零容忍风险被普通Waive；
* Crisis Plan未演练；
* 董事会材料长期延迟；
* 董事会决议无行动闭环；
* 董事会数字与管理层数字不一致；
* Critical经营风险无处升级。

## Final Result

```json
{
  "company_operating_version": "company-operations-v1",
  "gate": "C15-G",
  "status": "company-scale-operating-ready",
  "operating_cycles": [
    "annual-strategy",
    "quarterly-okr",
    "monthly-business-review",
    "rolling-forecast",
    "board-governance"
  ],
  "open_non_blocking_items": []
}
```

## Hard Rules

* 收入增长不能替代公司治理成熟；
* 完成OKR不能掩盖现金风险；
* 融资成功不能替代商业模式；
* 组织扩张不能超过管理能力；
* 董事会不能成为形式会议；
* 财务预测不能只服务融资叙事；
* 只有C15-G通过，公司才具备可持续规模化经营能力。

## Acceptance Criteria

* 战略选择清晰；
* 资源配置与战略一致；
* OKR推动真实结果；
* 组织和人才支撑增长；
* 现金和Runway可控；
* 融资和股权准确；
* 治理和风险体系有效；
* 董事会能够监督并改善公司；
* 公司经营不依赖少数人的临时协调。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
