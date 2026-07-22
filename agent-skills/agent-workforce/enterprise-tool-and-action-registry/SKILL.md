---
name: enterprise-tool-and-action-registry
description: "Execute authoritative Batch 16 Skill 541 for 登记Agent可调用的API、数据库查询、工作流、脚本和业务动作。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Enterprise Tool And Action Registry

## Operating contract

Apply authoritative Batch 16 Skill 541. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

登记Agent可调用的API、数据库查询、工作流、脚本和业务动作。

## Tool Record

```yaml
tool:
  tool_id: crm.create-follow-up
  owner: revenue-operations
  risk: low
  inputs_schema: {}
  outputs_schema: {}
  side_effect: true
  reversible: true
```

## Tool分类

```text
Read-only Query
Analysis
Draft
Write
Financial
Communication
Production
Security
Administrative
Destructive
```

## Hard Rules

* 未登记工具不得被生产Agent调用；
* 工具输入输出必须Schema化；
* Side Effect明确；
* 高风险工具需审批；
* 工具Owner负责可用性和变更；
* Deprecated工具及时移除；
* Tool Description不能夸大能力。

## Acceptance Criteria

* 工具资产完整；
* 风险和权限明确；
* Agent调用可验证；
* 输入错误可阻止；
* 工具变化触发Agent回归；
* 无影子工具。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
