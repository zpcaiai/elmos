---
name: oidc-authentication-session-and-tenant-context
description: "实现OIDC登录、Session、身份校验和不可伪造的Tenant Context。"
---

# Authentication

## 输入

OIDC Authorization Response
Issuer
Client ID
Redirect URI
Nonce
State
PKCE Verifier

## 输出

Authenticated Principal
Session
Subject ID
Issuer ID
Authentication Strength
Available Tenant Memberships

## Tenant Context

Tenant Context只能由：

Authenticated Subject
+
Active Tenant Membership
+
Selected Tenant
+
Resource Authorization

共同产生。

禁止直接信任：

X-Tenant-Id
tenantId Query Parameter
tenantId Request Body

## Session

HttpOnly
Secure
SameSite
Rotation
Idle Timeout
Maximum Lifetime
Logout
Revocation

## Token Validation

Issuer
Audience
Signature
Expiry
Not Before
Nonce
Authorized Party候选

## 状态

AUTHENTICATED
SESSION_ACTIVE
SESSION_EXPIRED
SESSION_REVOKED
IDENTITY_DISABLED
TENANT_SELECTION_REQUIRED

## 错误

OIDC_STATE_MISMATCH
OIDC_NONCE_MISMATCH
OIDC_ISSUER_DENIED
OIDC_TOKEN_EXPIRED
OIDC_SIGNATURE_INVALID
SESSION_FIXATION_DETECTED

## 验收标准

- 伪造X-Tenant-Id不能访问其他Tenant；
- Session建立后重新生成标识；
- 退出后Session立即失效；
- Identity被禁用后不能继续刷新；
- Tenant切换需要重新授权；
- 日志中不记录ID Token和Access Token。
