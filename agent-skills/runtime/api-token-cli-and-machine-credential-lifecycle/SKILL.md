---
name: api-token-cli-and-machine-credential-lifecycle
description: "管理CLI、Automation和Service Principal的短期或可轮换凭证。"
---

# Credential类型

PERSONAL_API_TOKEN
SERVICE_PRINCIPAL
CLI_DEVICE_SESSION
AUTOMATION_TOKEN
WEBHOOK_SECRET
RUNNER_CERTIFICATE

## 原则

优先：

OIDC Device Flow
Short-lived Token
Workload Identity

避免长期PAT。

## Token字段

Credential ID
Owner
Tenant
Scope
Purpose
Issued At
Expiry
Last Used
Rotation
Status
Hash

数据库只保存Hash或Reference，不保存可直接使用的明文。

## Scope

Repository
Project
Read／Write
Artifact
Automation
Maximum Risk
Environment

## 状态

ACTIVE
EXPIRING
ROTATING
REVOKED
EXPIRED
COMPROMISED
UNUSED

## 泄露处理

Revoke
Terminate Sessions
Search Usage
Rotate Dependent Secret
Notify Owner
Create Security Event

## 验收标准

- Token只显示一次；
- Token具有Expiry；
- Scope不允许通配全企业高权限；
- CLI优先使用交互身份；
- Last Used可见；
- 过期和撤销实时生效；
- Token不进入日志和Evidence；
- 泄露有标准Incident流程。
