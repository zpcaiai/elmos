---
name: enterprise-modernization-control-tower-and-command-cockpit
description: "建立面向高管、架构、工程、运营和业务Owner的统一控制塔及Command视图。"
---

# Control Tower

## Persona

EXECUTIVE
PORTFOLIO
ARCHITECT
PRODUCT
ENGINEERING
OPERATIONS
SECURITY
FINANCE
TRANSFORMATION
SITE_OPERATOR

## 视图

Enterprise Twin
Capability Map
Portfolio
Plans
Scenarios
Decisions
Executions
Agents
Policies
Risks
Value
Platform Health

## Action Center

Decision Required
Policy Conflict
Execution Paused
Unknown Result
Benefit Gap
Evidence Stale
Agent Quarantined
DR Required

## Command Mode

用于：

Major Cutover
Cross-engine Failure
Control Tower Incident
Security Incident
Transformation Crisis
Industrial Site Event

## 数据状态

FRESH
DELAYED
PARTIAL
STALE
CONFLICTED
UNKNOWN

## Drill-down

Outcome
→ Plan
→ Workflow
→ Step
→ Engine
→ Agent / Tool
→ Evidence

## 重要限制

不得：

- 用单一总分隐藏Hard Blocker；
- 把Prediction显示成Observed；
- 隐藏数据过期；
- 允许无权限用户查看跨租户信息。

## 验收标准

- Persona视图独立；
- Action和Owner明确；
- Unknown显式；
- 可下钻至Evidence；
- Command View支持人工接管；
- Cockpit不手工复制数据；
- 数据新鲜度可见。
