---
name: enterprise-identity-access-engine-contract-and-worker
description: "实现企业身份、多租户和访问治理引擎的统一契约、Worker与Provider边界。"
---

# Capability

{
  "engine": "ELMOS_IDENTITY_ACCESS",
  "engineVersion": "1.0.0",
  "capabilities": [
    "OIDC",
    "SAML",
    "SCIM",
    "TENANT_HIERARCHY",
    "MEMBERSHIP",
    "RBAC",
    "ABAC",
    "RESOURCE_AUTHORIZATION",
    "WORKLOAD_IDENTITY",
    "PRIVILEGED_ACCESS",
    "ACCESS_REVIEW",
    "TENANT_ISOLATION"
  ]
}

## API

GET  /identity/v1/capabilities
POST /identity/v1/providers
POST /identity/v1/authenticate
POST /identity/v1/authorize
POST /identity/v1/provision
POST /identity/v1/access-reviews
POST /identity/v1/privileged-access
GET  /identity/v1/decisions/{decisionId}

## Worker职责

- 同步外部Directory；
- 处理SCIM变更；
- 运行Membership到期任务；
- 撤销Session和Credential；
- 执行Access Review；
- 对账Role和Group；
- 发布Identity事件。

## 默认禁止

- 自动授予Tenant Admin；
- 自动授予跨Tenant权限；
- 把外部组名直接映射为高权限角色；
- 自动批准Break-glass；
- 记录OIDC／SAML原始Secret；
- 删除Access Decision历史。

## 验收标准

- Identity Provider可替换；
- 人类与工作负载身份分开；
- 所有Decision具有输入Hash；
- Provider失效可降级为安全拒绝；
- 生命周期事件可重放；
- Evidence进入统一Contract。
