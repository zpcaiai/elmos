---
name: identity-audit-privacy-retention-and-incident-response
description: "审计身份与授权操作，执行数据最小化、保留、纠正和身份安全事件响应。"
---

# Audit Event

Authentication
Logout
Membership Change
Role Change
Grant Change
SCIM Change
Token Issue
Token Revoke
Privileged Access
Break-glass
Access Review
Authorization Deny
Cross-tenant Attempt
Service Identity Rotation

## Event字段

Actor
Subject
Tenant
Action
Resource
Decision
Policy Version
Request ID
Session ID
Time
Result
Reason
Evidence

## Privacy

收集最少必要：

Identity ID
Business Email候选
Display Name
Role
Membership
Audit

避免保存：

不必要私人资料
完整IdP Token
私人通信
非必要设备指纹
敏感属性

## Retention

Identity Record
Session
Authorization Decision
Privileged Access
Audit
SCIM Payload
Security Incident

分别制定Retention。

## Correction

用户可以请求纠正允许纠正的个人资料；
历史Audit不能被改写，但可添加Correction Record。

## Identity Incident

Compromised Token
Account Takeover
Malicious Admin
Cross-tenant Attempt
Runner Identity Theft
SCIM Misconfiguration
IdP Compromise

## 验收标准

- 所有高权限操作有Audit；
- Audit普通管理员不可删除；
- Token正文不进入Audit；
- Identity数据有Retention；
- Correction不改写历史事件；
- 安全事件可以批量撤销Credential；
- 身份Incident拥有Runbook；
- Audit支持客户导出。
