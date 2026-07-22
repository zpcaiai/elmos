---
name: execution-transaction-idempotency-compensation-and-recovery
description: "管理跨引擎执行、幂等、租约、Commit Point、补偿、对账、暂停和人工恢复。"
---

# Execution Control

## Execution Step

Input
Precondition
Action
Idempotency Key
Target
Lease
Timeout
Commit Point
Verification
Compensation

## Delivery

AT_MOST_ONCE
AT_LEAST_ONCE
EFFECTIVELY_ONCE
MANUAL_CONTROLLED

不声称跨企业系统端到端Exactly Once。

## Commit Point

PREPARED
SIDE_EFFECT_STARTED
SIDE_EFFECT_COMMITTED
EXTERNALLY_VISIBLE
IRREVERSIBLE

## Result

SUCCEEDED
FAILED
PARTIAL
UNKNOWN_RESULT
TIMED_OUT
POLICY_REVOKED
HUMAN_PAUSED
COMPENSATED
MANUAL_RECOVERY

## Idempotency

Key绑定：

Plan
Step
Target
Parameters
Attempt Family

## Reconciliation

查询：

Actual State
Engine Receipt
External System
Audit
Business Result

## Compensation

AUTO
HUMAN_APPROVED
MANUAL
FORWARD_FIX
NOT_POSSIBLE

## Safe Stop

停止：

New Actions
Credential
Agent
Workflow Branch

保留：

Local Safety
Evidence
State
Recovery Access

## 验收标准

- 每步拥有幂等Key；
- Lease避免双执行；
- Commit Point明确；
- Unknown Result可对账；
- Compensation可测试；
- Partial不冒充成功；
- Manual Recovery正式化；
- Safe Stop不破坏本地安全。
