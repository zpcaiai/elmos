---
name: automated-remediation-guardrail-verification-and-recovery
description: 管理受控自动修复策略、动作、Blast Radius、验证、回滚、Cooldown和人工升级。
---

# Automated Remediation

## 自动化等级

RECOMMEND_ONLY
HUMAN_APPROVED
AUTO_LOW_RISK
AUTO_REVERSIBLE
AUTO_WITH_SUPERVISION
PROHIBITED

## Action

RESTART
SCALE
FAILOVER
TRAFFIC_SHIFT
FEATURE_DISABLE
QUEUE_PAUSE
JOB_RETRY
CACHE_CLEAR
ROLLBACK
CERTIFICATE_ROTATE
ISOLATE
CUSTOM

## Policy

Trigger
Service
Environment
Precondition
Scope
Maximum Targets
Maximum Frequency
Cooldown
Approval
Verification
Rollback
Escalation

## Preconditions

- Incident状态；
- 无冲突Change；
- Error Budget；
- Current Topology；
- Resource；
- Dependency；
- Data；
- Safety；
- Security。

## Verification

Technical Symptom
SLI
Business KPI
Dependency
No New Error
Duration
Stability Window

## Result

SUCCEEDED
PARTIALLY_SUCCEEDED
FAILED
ROLLED_BACK
ABORTED
UNKNOWN_RESULT

## Loop保护

防止：
