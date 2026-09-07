---
name: runbook-knowledge-diagnostic-and-operational-readiness
description: 管理Runbook、诊断、操作、验证、知识、新服务上线和运行准备度。
---

# Runbook Management

## Runbook类型

DIAGNOSTIC
INCIDENT
RECOVERY
FAILOVER
CAPACITY
SECURITY
MAINTENANCE
CHANGE
CONTINUITY
DECOMMISSION

## Runbook内容

Purpose
Scope
Trigger
Precondition
Required Role
Required Access
Steps
Expected Result
Abort
Verification
Rollback
Escalation
Evidence

## Step类型

READ_ONLY_CHECK
QUERY
DECISION
MANUAL_ACTION
AUTOMATED_ACTION
APPROVAL
WAIT
VERIFY
ROLLBACK
ESCALATE

## 生命周期

DRAFT
REVIEWING
APPROVED
VALIDATED
ACTIVE
STALE
DEPRECATED
RETIRED

## Stale Trigger

Service Change
Tool Change
Command Change
Owner Change
Environment Change
Incident Failure
Time Expiry

## Operational Readiness

检查：

- Owner；
- SLO；
- Dashboard；
- Alert；
- Runbook；
- On-call；
- Capacity；
- Backup；
- Restore；
- Security；
- Deployment；
- Rollback；
- Supplier；
- Continuity。

## Knowledge

Problem
Known Error
FAQ
Architecture
Dependency
Incident
Recovery
Decision

## 验收标准

- Runbook版本化；
- Step有预期结果；
- Automation和Manual分开；
- Stale自动发现；
- 上线前执行Readiness；
- Runbook定期演练；
- Incident失败反馈Runbook。
