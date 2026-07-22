---
name: organization-tenant-hierarchy-and-delegated-administration
description: "建立企业、子组织、业务单元和项目空间的租户层级与委托管理。"
---

# Tenant层级

Enterprise Tenant
→ Business Unit
→ Organization Workspace
→ Project Space

## 继承

可继承：

Policy
Identity Provider
Approved Agent
Retention
Region
Recipe Catalog

不可默认继承：

Tenant Admin
Repository Access
Billing Write
Break-glass
Production Runner Access

## 委托管理员

Enterprise Admin
Organization Admin
Project Admin
Identity Admin
Billing Admin
Security Admin

## 管理边界

管理员只能在其授权Scope内：

- 邀请成员；
- 映射组；
- 分配角色；
- 注册Runner；
- 管理Repository；
- 查看审计。

## Tenant状态

PROVISIONING
ACTIVE
SUSPENDED
READ_ONLY
OFFBOARDING
TERMINATED
LEGAL_HOLD

## 验收标准

- 子组织不能提升到父级；
- Policy继承可追踪；
- 角色继承与资源授权分开；
- Tenant暂停后写操作停止；
- Offboarding保留Evidence；
- 委托管理员不能授予超出自身范围的权限；
- 层级变化有影响分析。
