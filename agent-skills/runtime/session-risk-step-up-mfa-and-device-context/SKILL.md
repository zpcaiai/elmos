---
name: session-risk-step-up-mfa-and-device-context
description: "根据操作风险、认证强度、会话状态和设备上下文要求重新认证或限制操作。"
---

# Risk Signal

Authentication Age
MFA Status
Network候选
Device Trust候选
Geographic Anomaly候选
Credential Type
Operation Risk
Resource Sensitivity
Session Behavior

不得使用未经批准的侵入式用户监控。

## Authentication Strength

PASSWORD_ONLY
MFA
PHISHING_RESISTANT
HARDWARE_BOUND
WORKLOAD_ATTESTED

## Step-up触发

Plan Approval
Delivery Approval
Runner Registration
Policy Override
Evidence Export
Break-glass
Billing Change
Tenant Admin Assignment

## Decision

ALLOW
STEP_UP_REQUIRED
REAUTHENTICATE
READ_ONLY
DENY
SESSION_REVOKE

## Session Binding

Session
Device Context候选
Tenant
Authentication Strength
Last Step-up
Risk State

## 验收标准

- 普通浏览和高风险审批采用不同认证要求；
- 旧Session不能无限执行高风险动作；
- Step-up成功后权限有短期有效窗口；
- 会话风险变化可撤销Session；
- 服务身份不使用人类MFA；
- 设备数据遵循最小化；
- Risk Decision可解释。
