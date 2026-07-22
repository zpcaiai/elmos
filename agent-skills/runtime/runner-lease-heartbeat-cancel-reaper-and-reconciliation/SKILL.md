---
name: runner-lease-heartbeat-cancel-reaper-and-reconciliation
description: "建立可续租任务、Epoch、防双执行、取消、日志、Checkpoint、失联回收和未知结果对账。"
---

# Runner Task State

QUEUED
→ LEASED
→ ACKNOWLEDGED
→ RUNNING
→ VERIFYING
→ SUCCEEDED

异常：

CANCEL_REQUESTED
CANCELLED
FAILED
TIMED_OUT
LEASE_EXPIRED
UNKNOWN_RESULT
RECONCILING
MANUAL_RECOVERY
