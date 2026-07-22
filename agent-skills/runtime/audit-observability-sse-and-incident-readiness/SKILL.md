---
name: audit-observability-sse-and-incident-readiness
description: "提供跨控制面、Temporal、Runner、Sandbox、GitHub和Evidence的统一Timeline、审计与异常检测。"
---

# Observability

## Correlation

tenant_id
request_id
project_id
workflow_id
task_id
lease_id
runner_id
sandbox_id
snapshot_id
plan_id
recipe_run_id
delivery_id
evidence_pack_id

## Timeline Event

AUTHENTICATED
REPOSITORY_IMPORTED
RUNNER_ENROLLED
LEASE_CREATED
SANDBOX_STARTED
SNAPSHOT_CREATED
BASELINE_COMPLETED
PLAN_APPROVED
REWRITE_COMPLETED
VERIFICATION_COMPLETED
PR_PUBLISHED
EVIDENCE_SEALED

## SSE

支持：

Last-Event-ID
Reconnect
Tenant Authorization
Project Authorization
Heartbeat
Backpressure候选

## Audit

Actor
Authentication
Tenant
Action
Resource
Decision
Before／After Hash
Request
Time
Result

## Security Event

TENANT_ACCESS_ATTEMPT
RUNNER_IDENTITY_FAILURE
SANDBOX_ESCAPE_ATTEMPT
SECRET_ACCESS_ATTEMPT
NETWORK_POLICY_VIOLATION
ARTIFACT_INTEGRITY_FAILURE
WEBHOOK_SIGNATURE_FAILURE

## UI状态

EMPTY
LOADING
READY
PARTIAL
STALE
ERROR
UNAUTHORIZED
UNKNOWN

禁止把API错误显示成“暂无数据”。

## 验收标准

- Timeline跨服务可关联；
- SSE断线可恢复；
- 审计不可由普通用户删除；
- 日志不包含Token和Secret；
- Stale和Unknown显式；
- 安全事件触发Runner Quarantine候选；
- 所有高风险审批有Audit；
- 缺失Evidence产生Finding。
