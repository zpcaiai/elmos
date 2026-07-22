---
name: private-runner-registration-lease-and-execution
description: "实现Private Runner注册、心跳、能力、任务租约、日志、结果和取消。"
---

# Runner State

REGISTERING
ONLINE
BUSY
DRAINING
OFFLINE
QUARANTINED
REVOKED

## Lease

- Tenant绑定；
- Runner绑定；
- Task绑定；
- 过期；
- 可续租；
- 单任务单Lease；
- 取消可传播。

## Runner Policy

Allowed Image
Allowed Network
Maximum Resource
Allowed Repository
Allowed Agent
Allowed Secret
Allowed Artifact

## 验收标准

- Runner仅Outbound连接；
- 双Runner不能执行同一Lease；
- Heartbeat丢失后任务进入Reconcile；
- Runner可Drain升级；
- Runner撤销后Credential失效；
- 本地策略可以拒绝任务。
