---
name: incident-command-communication-and-major-incident-orchestrator
description: 管理Incident声明、角色、技术恢复、沟通、时间线、升级、交接和Major Incident。
---

# Incident Management

## Severity

SEV0_CRISIS
SEV1_CRITICAL
SEV2_MAJOR
SEV3_MINOR
SEV4_INFORMATIONAL

具体含义由组织Profile定义。

## Impact

Users
Transactions
Revenue
Data
Safety
Region
Duration
Regulation
Supplier
Reputation

## Roles

INCIDENT_COMMANDER
OPERATIONS_LEAD
COMMUNICATIONS_LEAD
PLANNING_SCRIBE
SUBJECT_MATTER_EXPERT
BUSINESS_LIAISON
SECURITY_LIAISON
SUPPLIER_LIAISON

## Timeline Event

Detection
Declaration
Role Assignment
Hypothesis
Action
Change
Mitigation
Recovery
Communication
Handoff

## 行动状态

PROPOSED
AUTHORIZED
RUNNING
SUCCEEDED
FAILED
ROLLED_BACK
UNKNOWN_RESULT

## Communication

Internal Technical
Leadership
Service Desk
Customer
Status Page
Supplier
Regulatory Workflow

## Major Incident Trigger

- Critical SLO；
- 多服务；
- 数据风险；
- 安全；
- 人员安全；
- 重大客户；
- 不确定恢复时间；
- 高公众影响。

## Incident Handoff

必须记录：

Current State
Impact
Actions
Hypotheses
Open Risks
Next Steps
Command Transfer
Acknowledgement

## Closure

Incident只有满足以下条件才能Resolved：

- 服务稳定；
- 监控恢复；
- 用户影响停止；
- 临时控制明确；
- Problem候选建立；
- Evidence保存。

## 验收标准

- Incident角色清晰；
- 只有指定Ops人员执行变化；
- Timeline自动保存；
- Communication与技术操作分开；
- Handoff显式确认；
- 恢复优先于Root Cause；
- 重大Incident触发Postmortem。
