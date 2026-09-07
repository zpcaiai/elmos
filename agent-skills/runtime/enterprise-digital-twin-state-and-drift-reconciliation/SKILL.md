---
name: enterprise-digital-twin-state-and-drift-reconciliation
description: "建立企业当前、声明、期望、批准、预测和模拟状态，并持续检测漂移。"
---

# Enterprise Digital Twin

## State类型

DECLARED
OBSERVED
DESIRED
APPROVED
SIMULATED
PREDICTED
MANUAL_OVERRIDE
UNKNOWN

## Twin Scope

Enterprise
Capability
Product
Application
Service
Data
Technology
Organization
Financial
Transformation
Industrial Site

## State字段

Value
Version
Authority
Confidence
Observed At
Valid Time
Expiry
Evidence

## Drift

DECLARED_OBSERVED
OBSERVED_DESIRED
APPROVED_EXECUTED
TARGET_REALITY
COST_PLAN_ACTUAL
ORGANIZATION_WORK
POLICY_RUNTIME

## Drift Decision

REMEDIATE_REALITY
UPDATE_DECLARATION
UPDATE_TARGET
CREATE_EXCEPTION
ACCEPT_TEMPORARILY
INVESTIGATE
IGNORE_APPROVED

## Twin Snapshot

必须包含：

Coverage
Freshness
Conflicts
Unknowns
Evidence Manifest
Graph Hash

## Twin限制

Twin不得：

- 直接成为生产控制接口；
- 把Desired视为Applied；
- 把Prediction视为Observation；
- 隐藏未知状态。

## 验收标准

- State类型严格分开；
- Twin有Authority；
- Snapshot不可变；
- Drift可定位；
- Unknown显式；
- Current与Target可比较；
- Twin变化触发Replan候选。
