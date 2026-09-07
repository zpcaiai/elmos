---
name: batch-17-vertical-solution-conformance-gate
description: "Execute authoritative Batch 17 Skill 668 for 综合领域模型、监管控制、Recipe、评测、Reference Architecture、商业打包和渠道能力，决定行业版本是否可商业交付。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Batch 17 Vertical Solution Conformance Gate

## Operating contract

Apply authoritative Batch 17 Skill 668. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

综合领域模型、监管控制、Recipe、评测、Reference Architecture、商业打包和渠道能力，决定行业版本是否可商业交付。

## 核心指标

```yaml
domain:
  critical_entity_coverage: 1.00
  critical_workflow_coverage: 1.00
  critical_invariant_coverage: 1.00

controls:
  mandatory_control_model_coverage: 1.00
  control_crosswalk_coverage: 1.00
  evidence_automation_rate: number

recipes:
  production_recipe_test_coverage: 1.00
  industry_recipe_idempotency: passed
  unsupported_critical_patterns: 0

evaluation:
  critical_industry_case_pass_rate: 1.00
  security_and_safety_case_pass_rate: 1.00

commercial:
  design_partner_acceptance: passed
  poc_pack: complete
  pricing_and_sow: complete

channel:
  certified_partner_available: true
  regional_support_ready: true
```

## Gate V17-A：领域模型成熟

```yaml
domain_owner_approved: true
critical_entities: complete
critical_state_machines: complete
critical_invariants: complete
terminology_governed: true
```

## Gate V17-B：控制和证据完整

```yaml
applicable_control_inventory: complete
mandatory_control_crosswalk: 1.00
runtime_evidence_available: true
open_critical_control_gaps: 0
```

## Gate V17-C：行业Recipe可用

```yaml
industry_recipe_pack: complete
recipe_regression_pass: true
critical_dependency_mappings: complete
critical_framework_mappings: complete
agent_generated_unreviewed_recipes: 0
```

## Gate V17-D：行业验证可信

```yaml
industry_eval_corpus: complete
critical_business_invariants_pass: 1.00
critical_security_cases_pass: 1.00
critical_safety_cases_pass: 1.00
unknown_critical_differences: 0
```

Safety Case不适用的行业可标记为Not Applicable，但必须说明依据。

## Gate V17-E：行业架构和交付就绪

```yaml
reference_architecture: approved
deployment_profiles: tested
industry_poc: accepted
delivery_playbook: complete
industry_evidence_pack: complete
```

## Gate V17-F：行业渠道就绪

```yaml
industry_partner_capability_matrix: complete
certified_delivery_team: available
regional_overlay: approved
local_support: ready
local_case_or_design_partner: available
```

## Gate V17-G：垂直版本商业交付候选

```yaml
all_domain_gates: passed
all_control_gates: passed
all_recipe_gates: passed
all_evaluation_gates: passed
all_architecture_gates: passed
all_commercial_gates: passed
all_channel_gates: passed
critical_open_vertical_risks: 0
vertical_evidence_pack: complete
```

## Blocking Conditions

* 行业版本只有UI和营销差异；
* 无行业Domain Owner；
* 领域模型只是数据库表复制；
* 关键Invariant未建模；
* 监管适用范围不明确；
* 宣称自动实现法规合规；
* Mandatory Control无实现或证据；
* 地区Overlay未经专业Review；
* 关键行业数据未分类；
* 跨地区驻留错误；
* 行业角色权限不完整；
* Emergency Access无审计；
* 行业Recipe无Golden测试；
* 财务金额存在差异；
* 医疗患者关联错误；
* 制造Safety边界可被Agent绕过；
* 能源控制指令未经授权；
* 政务权益决定无依据；
* 电商出现超额退款或库存重复扣减；
* 通信Usage丢失或重复计费；
* Critical安全或Safety Case失败；
* POC无行业专家验收；
* Partner无行业认证；
* 地区渠道售卖未就绪Overlay；
* 行业版本成本和维护Owner不明确；
* Critical Open Vertical Risk无Owner。

## Final Result

```json
{
  "vertical_platform_version": "vertical-solution-factory-v1",
  "gate": "V17-G",
  "status": "vertical-commercial-delivery-ready",
  "supported_verticals": [
    "finance",
    "manufacturing",
    "energy",
    "healthcare",
    "government",
    "commerce",
    "telecom"
  ],
  "open_non_blocking_items": []
}
```

## Hard Rules

* 行业数量不能代表垂直能力成熟度；
* 监管条款数量不能代替控制有效性；
* 行业专家参与不能代替机器验证；
* 通用平台成功不能自动证明行业版本成功；
* 一个地区通过不能自动代表其他地区；
* Partner渠道增长不能降低行业Gate；
* 只有V17-G通过的行业和地区组合，才能作为正式商业Edition销售。

## Acceptance Criteria

* 七个行业使用共享平台内核；
* 每个行业拥有真实领域模型；
* 监管控制可追踪到技术和证据；
* 行业Recipe经过完整测试；
* 关键业务Invariant得到验证；
* Reference Architecture可以生产交付；
* 行业POC和报价标准化；
* 行业伙伴具备交付能力；
* 地区Overlay可以安全复制；
* 行业版本具备持续维护机制。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
