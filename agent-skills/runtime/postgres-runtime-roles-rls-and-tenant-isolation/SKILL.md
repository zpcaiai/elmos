---
name: postgres-runtime-roles-rls-and-tenant-isolation
description: "分离迁移、运行、报表角色，为全部租户数据建立RLS和真实攻击测试。"
---

# Database Roles

## 角色

elmos_admin
仅用于数据库初始化和紧急管理

elmos_migrator
运行Flyway、创建Schema和Table

elmos_runtime
Control API运行时角色

elmos_reporting
受限报表只读角色

elmos_backup
备份恢复专用角色

## Runtime约束

elmos_runtime必须：

- NOSUPERUSER；
- NOBYPASSRLS；
- 不是业务表Owner；
- 无CREATE ROLE；
- 无CREATE DATABASE；
- 无TRUNCATE关键表；
- 只有批准Schema的CRUD权限。

## Tenant Session

每个业务事务开始：

SELECT set_config(
  'app.tenant_id',
  :tenantId,
  true
);

使用transaction-local，禁止使用跨事务残留的Session变量。

## RLS Policy

ALTER TABLE ... ENABLE ROW LEVEL SECURITY;
ALTER TABLE ... FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_policy
ON ...
USING (
  tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
  tenant_id = current_setting('app.tenant_id', true)::uuid
);

## 必须覆盖的表

Repository
Migration Project
Migration Event
Runner
Runner Task
Agent Run
Artifact
Evidence
Delivery
Policy Exception
Audit View
Outbox Event
Usage Record

全局配置表必须明确标记：

GLOBAL_NON_TENANT
或
TENANT_SCOPED

不得隐式混用。

## 连接池

- Tenant Context只能在事务中设置；
- 事务结束自动清除；
- 无Tenant Context时默认拒绝；
- Background Job也必须携带Tenant；
- 禁止共享跨Tenant事务。

## 安全测试

Tenant A读取Tenant B
Tenant A更新Tenant B
Tenant A通过Foreign Key猜测Tenant B
缺少Tenant Context
连接池复用
批量查询
Reporting Role
Migration Role

## 错误代码

TENANT_CONTEXT_MISSING
RLS_POLICY_MISSING
RUNTIME_ROLE_BYPASSRLS
RUNTIME_ROLE_TABLE_OWNER
CROSS_TENANT_REFERENCE
GLOBAL_TABLE_CLASSIFICATION_MISSING

## 验收标准

- Flyway和运行时使用不同账户；
- 运行时不是Superuser；
- 全部租户表启用RLS；
- 没有Tenant Context时返回零行或拒绝；
- 跨租户读写测试全部失败；
- 连接池复用不会泄漏Tenant Context；
- 数据库直接攻击测试进入CI。
