---
name: industry-identity-role-and-authorization-model
description: "Execute authoritative Batch 17 Skill 601 for 定义行业Actor、职责分离、资源授权、紧急权限和委托。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Identity Role And Authorization Model

## Operating contract

Apply authoritative Batch 17 Skill 601. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

定义行业Actor、职责分离、资源授权、紧急权限和委托。

## Actor Examples

```text
Finance：Teller、Trader、Risk、Approver
Manufacturing：Operator、Engineer、Maintenance、Safety
Healthcare：Clinician、Nurse、Pharmacist、Patient
Government：Case Worker、Reviewer、Citizen、Auditor
```

## Authorization

支持：

* RBAC；
  -ABAC；
  -Resource Ownership；
  -Relationship；
  -Purpose of Use；
  -Tenant；
  -Location；
  -Shift；
  -Emergency；
  -Dual Approval。

## Hard Rules

* 通用Admin不能自动获得行业数据权限；
* 职责分离必须机器执行；
* Emergency Access需原因和审计；
* Delegation有期限；
* Agent权限不超过行业角色；
* 批量导出需额外控制；
* 授权测试覆盖拒绝路径。

## Acceptance Criteria

* 行业角色完整；
* 高风险操作职责分离；
* Emergency流程有效；
* 跨机构访问受控；
* Agent与Human权限一致；
* 权限证据可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
