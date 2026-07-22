---
name: agent-identity-delegation-permission-budget-and-kill-switch
description: "管理Agent身份、委托链、最小权限、预算、最大自治范围和紧急停止。"
---

# Agent Authority

## Identity

Agent Workload Identity
Agent Version
Runtime Identity
User Delegation
Organization
Tenant
Environment

## Delegation

Delegator
Delegate
Purpose
Allowed Actions
Resources
Data
Maximum Risk
Budget
Expiry
Depth

## Authority状态

REQUESTED
GRANTED
ACTIVE
EXPIRED
REVOKED
DENIED
SUSPENDED

## 权限约束

Tool
Action
Resource
Field
Environment
Region
Time
Count
Amount
Purpose

## Budget

Tokens
Model Cost
Tool Cost
Compute
Steps
Duration
Tool Calls
External Side Effects

## Kill Switch

级别：

TASK
AGENT_VERSION
AGENT_TYPE
TENANT
TOOL
MODEL_PROVIDER
GLOBAL

## Kill行为

Stop New Tasks
Pause Current Task
Revoke Credential
Disable Tool
Isolate Runtime
Preserve Evidence
Trigger Reconciliation

## 重要规则

Agent不得：

- 委托超出自身权限的Authority；
- 绕过最大委托深度；
- 使用共享管理员Secret；
- 自行恢复被撤销权限。

## 验收标准

- 每个Agent拥有工作负载身份；
- Delegation链可审计；
- 权限按目的衰减；
- Budget实时执行；
- Kill Switch可演练；
- Credential自动撤销；
- 高风险行动需要独立批准。
