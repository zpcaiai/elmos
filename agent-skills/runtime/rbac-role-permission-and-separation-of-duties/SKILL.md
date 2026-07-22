---
name: rbac-role-permission-and-separation-of-duties
description: "建立可版本化角色、权限、职责分离、角色模板和权限差异分析。"
---

# Role

TENANT_ADMIN
IDENTITY_ADMIN
MIGRATION_MANAGER
DEVELOPER
REVIEWER
SECURITY_REVIEWER
AUDITOR
BILLING_ADMIN
SUPPORT_ENGINEER
READ_ONLY

## Permission

Resource Type
Action
Risk Level
Conditions
Delegatable
Approval Required

## Action示例

repository.read
project.create
plan.approve
migration.execute
delivery.approve
runner.register
artifact.download
evidence.export
policy.override
billing.manage

## Separation of Duties

典型冲突：

CREATE_PLAN
+
APPROVE_PLAN

EXECUTE_MIGRATION
+
APPROVE_DELIVERY

CREATE_POLICY_EXCEPTION
+
APPROVE_POLICY_EXCEPTION

REGISTER_RUNNER
+
APPROVE_RUNNER

## Role模板

SYSTEM
ENTERPRISE_DEFAULT
TENANT_CUSTOM
PROJECT_CUSTOM

## 角色变化

保存：

Before
After
Reason
Approver
Effective Time
Affected Users
Affected Resources

## 验收标准

- Permission粒度达到资源动作；
- 高风险权限不通过通配符授予；
- SoD冲突可检测；
- 自定义Role不能突破Tenant Policy；
- Role修改不会覆盖历史版本；
- 用户权限可计算和解释；
- 角色继承无循环。
