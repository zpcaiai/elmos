---
name: batch-18-group-integration-conformance-gate
description: "Execute authoritative Batch 18 Skill 745 for 综合交易逻辑、Day 1、资产发现、应用去重、身份、数据、技术栈、TSA、协同收益和退役结果，判断集团整合是否达标。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Batch 18 Group Integration Conformance Gate

## Operating contract

Apply authoritative Batch 18 Skill 745. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

综合交易逻辑、Day 1、资产发现、应用去重、身份、数据、技术栈、TSA、协同收益和退役结果，判断集团整合是否达标。

## 核心指标

```yaml
portfolio:
  critical_application_discovery_rate: 1.00
  application_owner_coverage: 1.00
  disposition_coverage: 1.00

dependencies:
  critical_dependency_mapping_rate: 1.00
  hidden_critical_callers: 0

identity:
  active_identity_correlation_rate: 1.00
  unauthorized_access_expansion: 0
  high_privilege_recertification_rate: 1.00

data:
  authoritative_domain_coverage: 1.00
  critical_data_reconciliation_pass: true
  unresolved_critical_duplicates: 0

tsa:
  tsa_exit_plan_coverage: 1.00
  overdue_tsa_without_approval: 0

synergy:
  synergy_owner_coverage: 1.00
  finance_verified_synergy_rate: number
  untracked_stranded_cost: 0

retirement:
  legacy_business_traffic: 0
  unknown_dependencies: 0
  retirement_evidence_complete: true
```

## Gate M18-A：交易和Day 1准备完成

```yaml
deal_thesis_mapped_to_initiatives: true
day_one_critical_service_coverage: 1.00
clean_team_controls: passed
day_one_fallbacks: tested
critical_open_day_one_risks: 0
```

## Gate M18-B：集团资产和依赖透明

```yaml
critical_application_inventory: complete
critical_data_asset_inventory: complete
critical_identity_inventory: complete
critical_interface_inventory: complete
dependency_graph: validated
```

## Gate M18-C：目标状态和处置决策完整

```yaml
business_capability_map: approved
target_enterprise_architecture: approved
application_disposition_coverage: 1.00
technology_exception_governance: active
target_system_owner_coverage: 1.00
```

## Gate M18-D：身份和数据整合安全

```yaml
identity_federation_or_cutover: passed
privilege_expansion: 0
critical_data_reconciliation: passed
master_data_conflicts_critical: 0
privacy_and_residency_controls: passed
```

## Gate M18-E：整合Wave可生产运行

```yaml
wave_entry_gates: passed
build_and_behavior_validation: passed
business_readiness: accepted
rollback: tested
hypercare: passed
```

## Gate M18-F：TSA和旧系统可退出

```yaml
replacement_services_ready: true
tsa_exit_validation: passed
legacy_business_traffic: 0
legacy_writes: 0
archive_restore: passed
hidden_dependencies: 0
```

## Gate M18-G：协同收益已兑现

```yaml
synergy_baseline_finance_approved: true
synergy_initiative_linkage: 1.00
run_rate_synergy_verified: true
one_time_cost_reconciled: true
stranded_cost_action_coverage: 1.00
```

## Gate M18-H：集团整合正式完成

```yaml
all_day_one_gates: passed
all_portfolio_gates: passed
all_identity_data_gates: passed
all_wave_gates: passed
all_tsa_exit_gates: passed
all_synergy_gates: passed
critical_open_integration_risks: 0
group_integration_evidence_pack: complete
```

## Blocking Conditions

* 交易逻辑未转为整合计划；
* Day 1关键服务无Owner；
* Clean Team边界失效；
* 关键应用未盘点；
* 隐藏调用方未处理；
* 重复系统仅按名称判断；
* 应用无Disposition；
* 两个系统同时成为同一数据域权威；
* 身份合并导致权限扩大；
* 高权限账户未重新认证；
* 客户或员工实体错误合并；
* Critical数据核对失败；
* 跨境或Consent限制未处理；
* TSA无退出计划；
* TSA长期延期无审批；
* Shared Platform容量不足；
* 技术栈强制收敛造成业务风险；
* Wave无回滚能力；
* Day 100目标无证据；
* 应用退役后仍有真实流量；
* 数据未归档即删除系统；
* 供应商合同仍产生未知成本；
* 系统关闭但Stranded Cost未移除；
* Synergy重复计算；
* 收益未经财务确认；
* 人员和组织转型无方案；
* Carve-out残留访问未撤销；
* 集团治理无法解决跨公司冲突；
* Critical整合风险无Owner。

## Final Result

```json
{
  "integration_program_id": "group-integration-001",
  "gate": "M18-H",
  "status": "group-integration-completed",
  "day_one_continuity": true,
  "target_operating_model_active": true,
  "critical_tsa_exited": true,
  "legacy_retirement_complete": true,
  "synergy_finance_verified": true,
  "open_non_blocking_items": []
}
```

## Hard Rules

* 法律交割完成不等于整合完成；
* Day 1成功不等于协同兑现；
* 系统迁移完成不等于Stranded Cost消失；
* 应用数量减少不能替代业务能力改善；
* 技术栈统一不能以客户和员工体验下降为代价；
* Synergy必须由财务和业务共同确认；
* 只有M18-H通过，才能标记集团整合项目完成。

## Acceptance Criteria

* Day 1业务连续；
* 应用、数据和身份资产透明；
* 重复系统得到事实化处置；
* 目标技术和业务架构生效；
* 身份和数据安全合并；
* Wave迁移可复制；
* TSA按计划退出；
* 旧系统和成本真正退役；
* 协同收益得到财务确认；
* 集团治理和运营进入稳定状态。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
