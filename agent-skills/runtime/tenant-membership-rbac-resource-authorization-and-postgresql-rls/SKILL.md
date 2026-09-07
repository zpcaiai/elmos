---
name: tenant-membership-rbac-resource-authorization-and-postgresql-rls
description: "实现Tenant Membership、RBAC／ABAC、资源授权、数据库角色分离和全表行级隔离。"
---

# Authorization

## 角色

TENANT_ADMIN
MIGRATION_MANAGER
DEVELOPER
REVIEWER
SECURITY_REVIEWER
AUDITOR
READ_ONLY

## 资源

Organization
GitHub Installation
Repository
Migration Project
Runner
Snapshot
Artifact
Approval
Pull Request
Evidence Pack
Policy

## 数据库角色

elmos_migrator
- Schema Owner
- 运行Flyway
- 不用于业务请求

elmos_runtime
- 非Superuser
- 无BYPASSRLS
- 不是表Owner
- 仅必要CRUD

elmos_auditor
- 受限只读
- 不可修改业务记录

## Tenant Session

每个事务开始时设置：

app.tenant_id
app.subject_id
app.request_id

无Tenant Context时：

默认拒绝。

## RLS

所有包含tenant_id的表必须：

ENABLE ROW LEVEL SECURITY
FORCE ROW LEVEL SECURITY
CREATE tenant_isolation_policy

## 授权决策

ALLOW
DENY
REQUIRE_APPROVAL
READ_ONLY
MASK_FIELDS

## 验收标准

- Runtime Connection不是数据库超级用户；
- Runtime Connection不是业务表Owner；
- 所有Tenant业务表启用RLS；
- 跨租户UUID猜测失败；
- Background Worker也必须设置Tenant Context；
- Resource Authorization在Controller和Application层均执行；
- RLS攻击测试连接真实PostgreSQL执行。
