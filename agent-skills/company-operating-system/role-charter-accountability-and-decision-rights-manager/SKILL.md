---
name: role-charter-accountability-and-decision-rights-manager
description: "Execute authoritative Batch 15 Skill 479 for 定义岗位存在的目的、结果、责任、权限和关键合作关系。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Role Charter Accountability And Decision Rights Manager

## Operating contract

Apply authoritative Batch 15 Skill 479. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

定义岗位存在的目的、结果、责任、权限和关键合作关系。

## Role Charter

```yaml
role:
  role_id: vp-product
  purpose: string
  outcomes: []
  responsibilities: []
  decision_rights: []
  reserved_decisions: []
  interfaces: []
  success_metrics: []
```

## Accountabilities

应描述：

* 负责的结果；
  -控制的资源；
  -可以做的决策；
  -需升级的决策；
  -必须合作的角色；
  -失败时承担的责任。

## Hard Rules

* 职位描述不能只是任务列表；
* 双重Accountability需谨慎；
* 责任必须匹配决策权；
* 无预算权却负责预算结果需解决；
* 角色变化需更新权限；
* 代理责任需有期限；
* 关键角色需得到管理层确认。

## Acceptance Criteria

* 关键角色责任清晰；
* 决策权匹配责任；
* 重叠和空白减少；
* 招聘和绩效使用同一Charter；
* 跨部门冲突减少；
* 权限系统可映射Role。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
