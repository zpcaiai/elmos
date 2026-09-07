---
name: access-review-certification-and-entitlement-reconciliation
description: "定期复核用户、服务、供应商和高权限访问，并对账实际与批准权限。"
---

# Review Scope

Tenant Membership
Role
Repository Grant
Runner Administration
Agent Provider Access
Artifact Download
Billing
Privileged Access
API Token
Service Principal

## Review类型

PERIODIC
ROLE_CHANGE
OFFBOARDING
HIGH_RISK
INCIDENT_TRIGGERED
CONTRACT_EXPIRY
TENANT_REORGANIZATION

## Reviewer

Manager
Resource Owner
Tenant Admin
Security Owner
Application Owner
Vendor Owner

## Decision

KEEP
REMOVE
REDUCE_SCOPE
CHANGE_ROLE
SUSPEND
REQUEST_EVIDENCE

## Entitlement Reconciliation

Approved Grants
vs
Effective Grants
vs
External Directory
vs
Runtime Sessions

识别：

ORPHAN_GRANT
EXCESS_PRIVILEGE
UNKNOWN_OWNER
EXPIRED_GRANT
GROUP_MAPPING_DRIFT
UNUSED_HIGH_PRIVILEGE

## 验收标准

- 高权限定期复核；
- Reviewer不能无依据批量Keep；
- 过期Review产生Finding；
- 移除Decision自动传播；
- 外部组和内部权限可对账；
- 临时供应商权限按合同复核；
- Review证据可导出；
- 历史Certification不可覆盖。
