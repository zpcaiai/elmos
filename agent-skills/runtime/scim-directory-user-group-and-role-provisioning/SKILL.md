---
name: scim-directory-user-group-and-role-provisioning
description: "使用SCIM同步企业用户、组、状态和Membership，并处理停用与对账。"
---

# SCIM对象

User
Group
Group Membership
Enterprise Extension
Provisioning Job
Provisioning Error

## 操作

Create
Read
Replace
Patch
Deactivate
Reactivate
Delete候选
Bulk候选
Filter
Pagination

## 用户状态

PROVISIONED
ACTIVE
SUSPENDED
DEACTIVATED
DELETED
CONFLICTED

## Group Mapping

External Group
→ Mapping Rule
→ ELMOS Role／Resource Scope

高权限映射需要：

Explicit Approval
Version
Owner
Review Date

## Deprovision

外部User变为inactive时：

- Membership暂停；
- Session撤销；
- API Token撤销；
- Privileged Grant撤销；
- Pending Approval重新分配；
- Audit保留。

## Reconciliation

定期比较：

External Directory
vs
ELMOS State

识别：

MISSING_USER
EXTRA_USER
GROUP_DRIFT
STATUS_DRIFT
IDENTITY_CONFLICT

## 验收标准

- SCIM Patch幂等；
- Deactivate快速传播；
- 删除不破坏历史Audit；
- 外部Group不直接拥有隐式超级权限；
- Group映射变化有影响分析；
- Provisioning失败可重试；
- 对账结果可人工处理。
