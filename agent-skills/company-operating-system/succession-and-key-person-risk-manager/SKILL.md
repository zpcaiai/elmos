---
name: succession-and-key-person-risk-manager
description: "Execute authoritative Batch 15 Skill 490 for 识别关键岗位、单点人员风险和继任准备度。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Succession And Key Person Risk Manager

## Operating contract

Apply authoritative Batch 15 Skill 490. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

识别关键岗位、单点人员风险和继任准备度。

## Critical Role

```yaml
critical_role:
  role_id: chief-architect
  business_impact: critical
  current_holder: string
  ready_now_successors: []
  ready_later_successors: []
  continuity_plan: []
```

## Key-person Risk

包括：

* 单一创始人销售；
  -单一架构师；
  -唯一客户关系；
  -唯一模型工程师；
  -唯一安全管理员；
  -唯一财务签字人；
  -唯一生产权限持有人。

## Mitigation

```text
Documentation
Delegation
Cross-training
Successor
External Backup
Automation
Access Redundancy
Retention
Role Redesign
```

## Hard Rules

* 继任不是秘密替换计划；
* 关键知识必须制度化；
* 生产权限不能依赖单人；
* 创始人职责需逐步可复制；
* 无继任岗位需列为企业风险；
* 继任候选需发展计划；
* 董事会需了解CEO继任风险。

## Acceptance Criteria

* 关键岗位清单完整；
* 单点风险可见；
* 继任准备度明确；
* 知识转移执行；
* 关键权限有备份；
* 离职冲击降低。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
