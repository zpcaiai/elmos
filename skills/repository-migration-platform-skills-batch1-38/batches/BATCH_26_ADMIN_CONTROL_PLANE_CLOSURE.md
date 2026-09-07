# Batch 26：Management Console与Control Plane Functional Closure

## Goal

把管理端从CRUD页面升级为完整的用户、租户、配置、任务、数据、发布、证书、成本、事故和退休控制面。

## Inputs

- Capability/business-line registries；
- Admin roles；
- Backend contracts；
- Operational workflows；

## Outputs

- Admin capability registry；
- Complete admin journeys；
- Permission matrix；
- Admin completeness score；

## Execution Flow

1. 盘点管理能力；
2. 为每项生成List/Search/Detail/Create/Edit/Enable/Disable/Bulk/Preview/Approval/Rollback；
3. 绑定Backend和Audit；
4. 验证错误/空/加载/权限状态；
5. 运行Admin Golden journeys；

## Verification

- Critical业务有管理入口；
- 危险操作有Preview和Approval；
- UI/API权限一致；
- Audit完整；

## Stop Conditions

- 管理功能仅有页面无后端；
- 批量操作无幂等；
- 管理员可绕过业务不变量；

## Gate

`Admin Closure Gate`

## Installable Skill

`agent-skills/runtime/b26-admin-control-plane-closure/SKILL.md`
