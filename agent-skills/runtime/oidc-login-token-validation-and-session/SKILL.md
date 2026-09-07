---
name: oidc-login-token-validation-and-session
description: "实现OIDC授权码、PKCE、Token校验、Session、刷新、注销和撤销。"
---

# OIDC Flow

Authorization Code
+ PKCE
+ State
+ Nonce

## Token验证

Signature
Issuer
Audience
Authorized Party
Expiry
Not Before
Nonce
Algorithm Allowlist
Token Type

## Session

Session ID
Subject
Tenant候选
Authentication Time
Authentication Strength
Idle Expiry
Absolute Expiry
Device Context
Revocation Version

## Cookie

HttpOnly
Secure
SameSite
Host-only候选
Rotation
CSRF Protection

## Token处理

浏览器不得长期保存：

Access Token
Refresh Token
ID Token

优先使用：

Server-side Session
或
受保护的Backend-for-Frontend模式。

## Session状态

ACTIVE
IDLE_EXPIRED
ABSOLUTE_EXPIRED
REVOKED
STEP_UP_REQUIRED
IDENTITY_DISABLED

## 验收标准

- State和Nonce重放失败；
- 错误Issuer和Audience被拒绝；
- 登录后Session ID轮换；
- Logout后Session立即无效；
- Membership撤销传播到Session；
- Token不进入前端日志；
- 多Tenant切换需要重新授权检查。
