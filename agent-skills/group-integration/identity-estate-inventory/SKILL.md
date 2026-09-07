---
name: identity-estate-inventory
description: "Execute authoritative Batch 18 Skill 691 for identity estate inventory. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Identity Estate Inventory

## Operating contract

Apply authoritative Batch 18 Skill 691. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

盘点：

```text
Directories
IdPs
SSO
MFA
HR Sources
Service Accounts
PAM
Certificates
API Keys
Groups
Roles
External Identities
```

## Hard Rules

* 人员账户和服务账户分开；
* 无Owner身份进入风险；
* 离职账户重点检查；
* 共享账号必须识别；
* 身份源系统明确；
* 实际登录数据用于确认；
* 高权限身份提前处理。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
