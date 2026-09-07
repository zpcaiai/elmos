---
name: oidc-tenant-membership-and-request-context
description: "用OIDC身份、Tenant Membership和资源授权替代X-Tenant-Id信任，建立请求级Tenant Context。"
---

# Authentication

## Token验证

必须验证：

- Signature；
- Issuer；
- Audience；
- Expiration；
- Not Before；
- Subject；
- Authorized Party候选；
- Token Type；
- Algorithm Allowlist。

## Tenant解析

禁止：

X-Tenant-Id
→ 直接成为Tenant Identity

正确流程：

Authenticated Subject
→ Tenant Membership
→ Requested Tenant候选
→ Membership Status
→ Role Assignment
→ Resource Authorization
→ Tenant Context

## Current Tenant

用户可选择当前Tenant，但选择结果必须满足：

- Membership为ACTIVE；
- Tenant未暂停；
- Role未过期；
- Resource Scope允许；
- Session／Token用途匹配。

## Principal

{
  "subjectId": "...",
  "issuer": "...",
  "tenantId": "...",
  "roles": [],
  "scopes": [],
  "sessionId": "...",
  "authenticationTime": "..."
}

## Authorization

分为：

Endpoint Authorization
Resource Authorization
Action Authorization
Tenant Boundary Authorization

例如：

MIGRATION_MANAGER
可以创建Migration Project

但只有Repository Scope包含目标Repository时才允许操作。

## Next.js

Browser
→ OIDC Session
→ Next.js Server Route
→ Bearer Token / Service Token
→ Control API

浏览器不得自行生成Tenant Header作为身份。

## 数据表

iam.identity_providers
iam.identities
iam.tenant_memberships
iam.roles
iam.role_assignments
iam.resource_grants
iam.sessions

## 错误代码

OIDC_ISSUER_UNTRUSTED
OIDC_AUDIENCE_INVALID
OIDC_TOKEN_EXPIRED
TENANT_MEMBERSHIP_NOT_FOUND
TENANT_MEMBERSHIP_SUSPENDED
RESOURCE_SCOPE_DENIED
ROLE_ASSIGNMENT_EXPIRED

## 验收标准

- 修改X-Tenant-Id不能访问其他Tenant；
- Token的Issuer和Audience均验证；
- 已移除成员立即失去访问；
- 同一用户可安全切换多个Tenant；
- Repository级授权可执行；
- Audit记录Subject、Tenant、Role和Action；
- 未认证请求默认拒绝。
