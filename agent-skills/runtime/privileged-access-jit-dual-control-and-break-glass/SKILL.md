---
name: privileged-access-jit-dual-control-and-break-glass
description: "管理临时高权限、双人批准、紧急访问、录制和自动撤销。"
---

# Privileged Operation

Tenant Administration
Runner Approval
Policy Override
Evidence Legal Hold
Cross-region Recovery
Production Support
Security Incident Access

## JIT Request

Requester
Purpose
Resource
Requested Role
Start
Duration
Support Case／Incident
Risk
Approver

## 决策

APPROVED
APPROVED_WITH_CONDITIONS
DENIED
EXPIRED
REVOKED

## Dual Control

以下操作候选要求不同人员：

- Break-glass批准；
- Policy安全例外；
- 删除Legal Hold；
- 跨Tenant Support；
- 高风险Runner批准。

## Break-glass

只在：

Identity Provider Outage
Major Incident
Tenant Recovery
Security Incident

使用。

必须具备：

Strong Authentication
Short Duration
Restricted Scope
Session Recording
Immediate Alert
Post-use Review
Automatic Revocation

## 验收标准

- JIT权限自动到期；
- 请求人不能独自批准；
- Break-glass不等于永久Super Admin；
- 每次使用产生高优先级Audit；
- 访问范围绑定Incident；
- 事后Review必须完成；
- 未完成Review阻止再次使用候选。
