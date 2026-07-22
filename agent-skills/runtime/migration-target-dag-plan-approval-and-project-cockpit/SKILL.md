---
name: migration-target-dag-plan-approval-and-project-cockpit
description: "生成目标版本、迁移DAG、风险、预算和PR波次，并提供基于Plan Hash的可审计审批。"
---

# Target Profile

Source Java
Target Java
Source Spring Boot
Intermediate Spring Boot
Target Spring Boot
Build Tool
Deployment Type
Runtime
Data Constraints
Repository Policy

## DAG

BUILD_FOUNDATION
JDK_UPGRADE
BOOT3_INTERMEDIATE
JAKARTA
SPRING_SECURITY
HIBERNATE
TESTING
BOOT4
CLEANUP

## Step

Step ID
Purpose
Dependencies
Automation Mode
Recipe
Expected Files
Risk
Verification
Rollback
Estimated Duration
Estimated Agent Budget

## Automation Mode

DETERMINISTIC
RULE_BASED
AGENT_ASSISTED
HUMAN_REQUIRED
BLOCKED

## Plan Version

每次修改生成：

Plan Version
Plan Hash
Twin／Snapshot ID
Recipe Catalog Version
Policy Bundle Version
Estimate Version

## Approval

仅当：

project.stage =
WAITING_FOR_PLAN_APPROVAL

且：

approval.plan_hash =
current_plan_hash

时有效。

## Cockpit必须显示

Target
Migration DAG
Changed Components
Expected File Count
Known Risk
Recipe License
Baseline Status
Verification Plan
Agent Budget
Human Tasks
Rollback
Plan Hash

## SSE Timeline

事件：

PlanGenerated
ApprovalRequested
ApprovalGranted
ApprovalRejected
PlanSuperseded
ExecutionStarted

支持：

Last-Event-ID
断线重连
Event ID去重

## UI状态

EMPTY
LOADING
READY
WAITING_APPROVAL
EXECUTING
ERROR
STALE
PARTIAL
UNAUTHORIZED

不得把API错误显示成空列表。

## 验收标准

- Plan生成前不能审批；
- Approval绑定Plan Hash；
- 修改Plan后旧Approval失效；
- 用户能看到风险和验证方案；
- Reject和Request Evidence可用；
- Timeline可断线重连；
- Stale Plan不能执行。
