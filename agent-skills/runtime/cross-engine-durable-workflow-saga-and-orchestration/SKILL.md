---
name: cross-engine-durable-workflow-saga-and-orchestration
description: "编排跨Java、数据、云、ERP、主机、AI、OT和组织引擎的长运行工作流。"
---

# Cross-engine Orchestration

## Step类型

ENGINE_TASK
AGENT_TASK
HUMAN_TASK
POLICY_TASK
SIMULATION_TASK
WAIT_EVENT
WAIT_TIME
DECISION_GATE
VERIFY
COMPENSATE
RECONCILE

## Workflow要求

Versioned
Durable
Resumable
Idempotent
Observable
Cancelable
Compensatable

## 跨引擎模式

SEQUENTIAL
PARALLEL
FAN_OUT
FAN_IN
EVENT_DRIVEN
SAGA
HUMAN_GATE
CONDITIONAL
SUBWORKFLOW

## Version Pinning

每个Instance固定：

Workflow Version
Engine Contract
Agent Version
Tool Version
Policy Bundle
Schema Version

运行中不得静默升级。

## Long-running

支持：

Days
Months
Years
Human Approval
External Event
Business Window
Maintenance Window

## Saga

每个业务步骤定义：

Forward Action
Commit Point
Compensation
Reconciliation
Manual Recovery

## Failure

RETRYABLE
NON_RETRYABLE
POLICY_DENIED
HUMAN_REJECTED
UNKNOWN_RESULT
COMPENSATION_FAILED

## 验收标准

- Workflow持久化；
- Step版本固定；
- Human Wait可恢复；
- Saga不伪装ACID；
- Compensation可测试；
- Unknown Result可Reconcile；
- Worker崩溃后可继续。
