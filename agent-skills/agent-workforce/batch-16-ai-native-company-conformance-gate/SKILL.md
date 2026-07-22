---
name: batch-16-ai-native-company-conformance-gate
description: "Execute authoritative Batch 16 Skill 592 for 综合AI战略、Agent Workforce、人机责任、模型风险、安全、组织转型和自主经营结果，判断公司是否达到AI原生经营标准。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Batch 16 Ai Native Company Conformance Gate

## Operating contract

Apply authoritative Batch 16 Skill 592. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

综合AI战略、Agent Workforce、人机责任、模型风险、安全、组织转型和自主经营结果，判断公司是否达到AI原生经营标准。

## 核心指标

```yaml
strategy:
  ai_strategy_approved: true
  ai_operating_principles_active: true
  prohibited_use_cases_defined: true

workforce:
  agent_charter_coverage: 1.00
  human_owner_coverage: 1.00
  redesigned_critical_role_coverage: number

governance:
  authority_envelope_coverage: 1.00
  high_risk_human_approval_coverage: 1.00
  kill_switch_test_rate: 1.00

evaluation:
  production_agent_eval_coverage: 1.00
  shadow_validation_coverage: 1.00
  critical_red_team_findings: 0

security:
  unauthorized_tool_calls: 0
  privilege_escalations: 0
  secret_exfiltration: 0
  cross_tenant_memory_leaks: 0

operations:
  action_provenance_coverage: 1.00
  agent_incident_detection: passed
  rollback_success_rate: 1.00

economics:
  agent_cost_visibility: 1.00
  cost_per_outcome_visibility: 1.00
  agent_value_review_coverage: 1.00

organization:
  workforce_transition_plans: complete
  high_impact_employee_ai_decisions_human_reviewed: 1.00
  ai_training_coverage: number
```

## Gate AI16-A：AI战略清晰

```yaml
ai_strategy: approved
priority_use_cases: defined
prohibited_use_cases: defined
risk_appetite: approved
investment_plan: funded
```

## Gate AI16-B：Agent Workforce可治理

```yaml
production_agent_inventory: complete
agent_charter_coverage: 1.00
human_owner_coverage: 1.00
agent_identity_coverage: 1.00
authority_envelope_coverage: 1.00
```

## Gate AI16-C：人机责任清晰

```yaml
critical_process_human_accountability: 1.00
high_risk_human_approval: 1.00
human_takeover: tested
employee_appeal_process: active
responsibility_gaps: 0
```

## Gate AI16-D：模型和Agent风险受控

```yaml
model_inventory: complete
critical_agent_eval_pass_rate: 1.00
red_team: passed
prompt_injection_controls: passed
privilege_escalation_controls: passed
memory_isolation: passed
```

## Gate AI16-E：自主执行安全

```yaml
transactional_actions: passed
rollback: passed
kill_switch: passed
loop_budget_enforcement: passed
anomaly_monitoring: active
critical_unreviewed_actions: 0
```

## Gate AI16-F：组织转型可持续

```yaml
critical_role_redesign: complete
workforce_transition_plan: approved
ai_capability_training: active
performance_incentive_alignment: passed
employee_trust_controls: passed
```

## Gate AI16-G：AI原生公司候选

```yaml
all_strategy_gates: passed
all_workforce_gates: passed
all_governance_gates: passed
all_model_risk_gates: passed
all_security_gates: passed
all_autonomous_operation_gates: passed
all_organization_transition_gates: passed
critical_open_ai_risks: 0
ai_native_evidence_pack: complete
```

## Blocking Conditions

* Agent没有Human Owner；
* Agent没有Charter；
* Agent使用员工共享Credential；
* Agent可以修改自身权限；
* Agent可以关闭审计；
* 高风险动作无人工审批；
* Agent未经评测直接进入生产；
* Shadow未通过仍提高自主权；
* Agent无法停止或回滚；
* 工具调用未进行Policy检查；
* Agent可以无限创建子Agent；
* Agent循环没有预算；
* Prompt Injection可以触发工具行动；
* Secret进入Agent Memory；
* 跨Tenant Context污染；
* 模型版本无法确定；
* Provider静默更新无法检测；
* Critical Red Team问题未关闭；
* Agent事故无证据；
* 人事高影响决定由Agent最终作出；
* 法律或财务承诺由Agent自主签署；
* 自动化收益只计算Token而忽略监督和事故；
* Workforce转型没有员工支持；
* AI增长造成员工信任严重下降；
* 董事会不了解重大AI风险；
* AI宪法可以被Agent绕过；
* Critical Open AI Risk无Owner。

## Final Result

```json
{
  "ai_native_operating_version": "ai-native-company-v1",
  "gate": "AI16-G",
  "status": "bounded-autonomous-company-ready",
  "supported_autonomy": [
    "assistant",
    "recommendation",
    "approval-gated-execution",
    "bounded-autonomous-execution",
    "closed-loop-low-risk-domains"
  ],
  "prohibited_state": "unbounded-autonomous-company",
  "open_non_blocking_items": []
}
```

## Hard Rules

* Agent数量不能代表AI原生程度；
* 自动化比例不能替代业务价值；
* 人类审批数量少不能自动视为更成熟；
* AI原生公司不等于无人公司；
* 融资、董事会、人事、法律和重大伦理责任不得转移给Agent；
* 自主经营必须有明确边界、证据、监督和停止机制；
* 只有AI16-G通过，公司才具备安全、可控和可持续的AI原生经营能力。

## Acceptance Criteria

* 公司战略和AI战略一致；
* 工作和岗位完成系统重构；
* Agent Workforce具备正式治理；
* Human与Agent责任清晰；
* 所有生产Agent持续评测；
* 工具、数据、预算和权限受到控制；
* 模型和Agent安全风险可管理；
* 人工接管和回滚有效；
* 员工获得转型和能力支持；
* 高管和董事会能够监督AI系统；
* 自主经营只发生在定义清晰、有界且可逆的领域。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
