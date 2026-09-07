# Batch 27：Identity、Authorization、Approval与Audit Closure

## Goal

统一用户、服务、设备、Agent和委派身份，确保所有层默认拒绝、权限不扩大、Tenant隔离与审计不可变。

## Inputs

- Identity sources；
- Role/policy definitions；
- Resource catalog；
- Admin/tool/skill actions；

## Outputs

- Principal registry；
- Authorization policies/matrices；
- Approval workflows；
- Immutable audit；
- Identity certificates；

## Execution Flow

1. 统一身份模型；
2. 生成RBAC/ABAC/ReBAC；
3. 在API/DB/Message/Search/Object/Skill实施资源级授权；
4. 建立委派/Break-glass/双人审批；
5. 运行越权和Tenant矩阵；

## Verification

- Horizontal/vertical privilege findings为零；
- Service/User身份分离；
- Denied和Privileged action可审计；

## Stop Conditions

- Tenant来自不可信输入；
- 授权只在Gateway；
- 普通Admin可修改Audit；

## Gate

`Identity & Authorization Gate`

## Installable Skill

`agent-skills/runtime/b27-identity-authorization-audit/SKILL.md`
