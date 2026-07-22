---
name: membership-invitation-lifecycle-and-offboarding
description: "管理邀请、成员加入、状态变化、供应商成员、到期和完整离场。"
---

# Membership

Subject
Tenant
Organization Scope
Membership Type
Roles
Start
Expiry
Sponsor
Status

## 类型

EMPLOYEE
CONTRACTOR
PARTNER
AUDITOR
SUPPORT
SERVICE_ACCOUNT_OWNER

## 状态

INVITED
PENDING_VERIFICATION
ACTIVE
SUSPENDED
EXPIRING
EXPIRED
REVOKED
OFFBOARDED

## Invitation

绑定：

Email候选
Tenant
Role候选
Scope
Inviter
Expiry
Nonce

邀请不应直接授予高权限，接受后仍需Membership Policy。

## Temporary Membership

必须具有：

Sponsor
Purpose
Expiry
Resource Scope
Review

## Offboarding

撤销：

Sessions
API Tokens
CLI Credentials
Runner Access
Agent Approval Rights
Privileged Grants
Download URLs
Repository Grants

同时处理：

Pending Approval
Owned Project
Open Incident
Evidence Ownership
Successor

## 验收标准

- Invitation只能使用一次；
- 邀请过期后不能接受；
- 临时成员自动过期；
- 离职事件撤销全部活动Credential；
- 离场不会删除历史操作；
- 无Owner资源自动进入治理队列；
- Offboarding可生成完成证据。
