---
name: saml-sso-and-enterprise-federation
description: "支持企业SAML SSO、Metadata、证书轮换、Assertion校验和Single Logout候选。"
---

# SAML

## 配置

Entity ID
SSO URL
SLO URL候选
Metadata
Signing Certificate
Encryption Certificate候选
NameID Format
Attribute Mapping
Clock Skew
Tenant Binding

## Assertion验证

Signature
Issuer
Audience
Recipient
Destination
InResponseTo
NotBefore
NotOnOrAfter
Subject Confirmation
Replay ID

## 属性

Subject ID
Email
Display Name
Group
Employee ID候选
Authentication Context

## Replay防护

保存：

Assertion ID
Response ID
Expiry
Tenant

相同Assertion不得重复建立Session。

## 证书轮换

支持双证书重叠期及Metadata更新。

## 验收标准

- 未签名或错误签名Assertion被拒绝；
- 错误Audience和Recipient被拒绝；
- Assertion Replay失败；
- 时钟偏差在批准范围内处理；
- IdP证书轮换可平滑完成；
- SAML属性不直接授予高权限；
- SAML与OIDC身份可按批准Crosswalk关联。
