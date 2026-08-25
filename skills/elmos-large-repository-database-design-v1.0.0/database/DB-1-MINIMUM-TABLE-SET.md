# DB-1 最小上线表集合

全量参考模型包含 136 张父表。为避免第一版被“大而全”拖慢，建议拆成 DB-1A 与 DB-1B。

## DB-1A：34 张 Durable Execution Core

### core（10）

```text
core.tenant
core.account
core.project
core.repository
core.revision_snapshot
core.repository_revision
core.job
core.job_submission
core.job_input_revision
core.account_task_slot
```

### exec（19）

```text
exec.run
exec.run_attempt
exec.run_stage
exec.task
exec.task_dependency
exec.worker_node
exec.workspace
exec.task_attempt
exec.execution_lease
exec.run_event_cursor
exec.run_event
exec.run_progress_snapshot
exec.session
exec.session_event_cursor
exec.session_event
exec.run_control_request
exec.recovery_action
exec.checkpoint
exec.checkpoint_component
```

### artifact（5）

```text
artifact.object_blob
artifact.artifact
artifact.manifest
artifact.manifest_entry
artifact.staged_object
```

DB-1A 退出条件：

- 提交幂等；
- 每账号 3 个原子槽；
- Task DAG 可 Claim/Renew/Finish；
- Worker fencing 生效；
- Run/Session Event 可重放；
- Artifact 可原子发布；
- Checkpoint 可 sealed 并恢复；
- Kill Worker 后可继续。

## DB-1B：运营、安全与商业闭环

DB-1A 通过后立即增加：

```text
exec.context_epoch
exec.context_compaction
exec.workpad
exec.workpad_item
exec.approval_request
exec.approval_decision
exec.human_gate

artifact.artifact_link
artifact.run_archive

integration.outbox_event
integration.inbox_message
integration.side_effect_receipt
integration.compensation_action
integration.reconciliation_run
integration.reconciliation_issue

metering.price_snapshot
metering.model_invocation
metering.tool_invocation
metering.usage_ledger
metering.budget_reservation
metering.cost_ledger
metering.revenue_ledger
metering.resource_usage_aggregate
metering.eta_forecast

audit.audit_event
```

DB-1B 退出条件：

- 人工审批与暂停/恢复；
- Side Effect `UNKNOWN_RESULT` 重对账；
- Outbox/Inbox at-least-once 幂等；
- Token、资源、成本、收入和预算可对账；
- 机器 ETA 与人工等效工时分离；
- 安全与运营审计完整。

## 后续阶段

- DB-2：15 张 analysis + 4 张 cache；
- DB-3：12 张 generation + 7 张 transform + 23 张 verify；
- DB-4：9 张 learning + 7 张 ops。

完整项目生成/整库转换对外 GA 前，DB-2 与 DB-3 必须启用；DB-4 Learning 需要客户数据授权后再启用。
