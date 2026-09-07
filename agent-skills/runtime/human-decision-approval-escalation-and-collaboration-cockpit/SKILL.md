---
name: human-decision-approval-escalation-and-collaboration-cockpit
description: "为高风险计划和执行提供Decision Package、审批、异议、协作、升级与责任记录。"
---

# Human Decision

## Decision Package

Context
Objective
Current State
Options
Recommendation
Evidence
Risk
Cost
Value
Unknown
Policy
Simulation
Rollback
Needed By

## Decision类型

APPROVE
REJECT
APPROVE_WITH_CONDITIONS
MODIFY
REQUEST_EVIDENCE
ESCALATE
PAUSE
STOP
PIVOT

## Approval绑定

Plan Version
Step
Action
Parameters
Target
Policy Version
Expiry

## Approver

Business Owner
Technical Owner
Data Owner
Security
Finance
Safety
Regulatory
Operations
Executive

## 多方批准

SEQUENTIAL
PARALLEL
QUORUM
DUAL_CONTROL
UNANIMOUS
RISK_BASED

## Dissent

保存：

Concern
Alternative
Evidence
Residual Risk
Decision Response

不得删除不同意见。

## Rubber Stamp检查

- 审批量是否不现实；
- 是否缺少上下文；
- 是否没有拒绝权；
- 是否审批后参数变化；
- 是否存在利益冲突。

## 验收标准

- Decision Package完整；
- Approver有Decision Right；
- Approval绑定Hash；
- 参数变化触发重审；
- Dissent保留；
- Overdue可升级；
- Override可审计；
- 人类拥有真实控制权。
