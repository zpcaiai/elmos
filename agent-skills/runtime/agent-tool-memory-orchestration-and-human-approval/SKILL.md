---
name: agent-tool-memory-orchestration-and-human-approval
description: 治理Agent指令、工具、权限、记忆、Handoff、步骤、预算、审批和外部副作用。
---

# Agent Runtime

## Agent对象

Instructions
Model Policy
Tools
Memory
Handoffs
Guardrails
Budget
Owner
Risk Tier

## Tool分类

READ_ONLY
REVERSIBLE_WRITE
FINANCIAL
COMMUNICATION
DATA_CHANGE
CODE_EXECUTION
INFRASTRUCTURE
SECURITY
EXTERNAL_SIDE_EFFECT

## Tool Contract

Name
Purpose
Input Schema
Output Schema
Identity
Permission
Idempotency
Timeout
Retry
Approval
Audit

## Permission

Agent权限必须：

- Agent身份绑定；
- Use Case绑定；
- Environment绑定；
- Tool绑定；
- Scope绑定；
- 时间绑定。

不能复用用户或管理员的无限权限Token。

## Human Approval

PRE_EXECUTION
POST_PLAN
HIGH_VALUE_ACTION
BATCH_APPROVAL
DUAL_APPROVAL
NO_APPROVAL

高风险操作例如：

- 付款；
- 删除；
- 发送外部邮件；
- 修改生产；
- 变更权限；
- 发布代码；

默认需要审批或严格Policy。

## Memory

SESSION
USER_PROFILE
TASK
LONG_TERM
ORGANIZATIONAL
NONE

Memory写入必须经过：

- 分类；
- 最小化；
- 过期；
- 删除；
- 来源；
- 用户可见性；
- 权限。

## Handoff

记录：

Source Agent
Target Agent
Reason
Transferred Context
Permission Change
Budget
Result

## Agent限制

Maximum Steps
Maximum Tool Calls
Maximum Tokens
Maximum Cost
Maximum Duration
Maximum Recursive Depth

## Compensation

可逆写操作必须定义：

Rollback
Compensation
Manual Recovery
Forward Fix

## 验收标准

- Agent与Model分开；
- Tool具有Schema和权限；
- 高风险Action可审批；
- Memory受生命周期治理；
- Handoff可追踪；
- 步骤和预算有上限；
- Side Effect能够恢复或升级人工处理。
