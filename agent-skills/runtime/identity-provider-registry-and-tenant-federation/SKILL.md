---
name: identity-provider-registry-and-tenant-federation
description: "管理不同Tenant的OIDC、SAML、Directory和身份域绑定及发现。"
---

# Identity Provider Registry

## Provider类型

OIDC
SAML
LOCAL_DEVELOPMENT
DIRECTORY
CUSTOM_FEDERATION

## Provider字段

Issuer
Metadata URL
Client ID
Allowed Algorithms
Claim Mapping
Group Mapping
Tenant Domain
Certificate
Key Rotation
Status
Owner

## Tenant发现

可依据：

- 企业专属登录入口；
- 已验证Email Domain；
- Tenant Slug；
- 邀请链接；
-显式组织选择。

不得仅依据未经验证Email字符串自动加入Tenant。

## 状态

DRAFT
VALIDATING
ACTIVE
DEGRADED
SUSPENDED
CERTIFICATE_EXPIRING
DISABLED

## Claim Mapping

Subject
Email
Display Name
Employee ID候选
Groups
Authentication Context
MFA Indicator

Claim Mapping必须版本化。

## Key Rotation

支持：

- 新旧Key重叠窗口；
- Metadata刷新；
- 失败告警；
- 缓存过期；
- 紧急撤销。

## 验收标准

- 一个Tenant可配置多个IdP；
- 一个IdP可绑定受控的多个Tenant；
- 未验证Domain不能自动建立Membership；
- Issuer和Tenant绑定明确；
- Key轮换不中断有效登录；
- IdP暂停后新登录被拒绝；
- 历史身份映射保持可审计。
