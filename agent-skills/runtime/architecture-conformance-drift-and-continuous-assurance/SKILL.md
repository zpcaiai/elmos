---
name: architecture-conformance-drift-and-continuous-assurance
description: 将原则、标准、Reference Architecture、ADR和Target State转为持续架构符合性检查。
---

# Architecture Conformance

## Conformance来源

Repository
Source Code
Dependency
IaC
Deployment
Runtime
Data
Security
Cost
Operations
Owner Declaration

## Conformance类型

PRINCIPLE
STANDARD
PATTERN
REFERENCE_ARCHITECTURE
DECISION
TARGET_STATE
EXCEPTION_CONDITION

## 状态

CONFORMANT
PARTIALLY_CONFORMANT
NON_CONFORMANT
EXCEPTED
NOT_APPLICABLE
NOT_ASSESSED
STALE
INCONCLUSIVE

## Drift

SOURCE_DRIFT
DEPENDENCY_DRIFT
RUNTIME_DRIFT
DATA_DRIFT
TECHNOLOGY_DRIFT
CONFIGURATION_DRIFT
OWNERSHIP_DRIFT
ROADMAP_DRIFT
DECISION_DRIFT

## 检查时间

DESIGN
PULL_REQUEST
BUILD
DEPLOYMENT
RUNTIME
PERIODIC
MILESTONE
INCIDENT_TRIGGERED

## 自动化

可以自动：

- 发现；
- 提醒；
- 阻止明确Hard Rule；
- 创建Remediation；
- 创建Exception Request。

不能自动：

- 接受重大架构风险；
- 修改业务Target；
- 删除生产系统；
- 改写历史Decision。

## Conformance Finding

Rule
Scope
Expected
Observed
Evidence
Severity
Owner
Exception
Due Date

## 架构腐化

若某个Target长期不符合现实：
