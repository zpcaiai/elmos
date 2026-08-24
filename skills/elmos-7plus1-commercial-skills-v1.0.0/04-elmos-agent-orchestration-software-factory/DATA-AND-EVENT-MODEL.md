# P04 数据与事件模型

## 1. 领域实体

| 实体 | 持久化建议 |
| --- | --- |
| IssueRecord | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| WorkflowStateMap | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| TaskNode | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| TaskDependency | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| RunAssignment | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| WorkspaceLease | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| AgentRole | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| AgentExecutionProfile | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| ResourceBudget | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| RetryPolicy | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| Workpad | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| FeedbackItem | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| ProofOfWork | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| HumanGate | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |
| RunDashboardSnapshot | Postgres metadata / content-addressed artifact / append log，按实体性质选择 |

## 2. 通用事件信封

```json
{
  "event_id": "01J...",
  "event_type": "issue.discovered",
  "event_version": 1,
  "occurred_at": "2026-08-21T08:00:00Z",
  "tenant_id": "t-001",
  "project_id": "p-001",
  "job_id": "j-001",
  "run_id": "r-001",
  "actor": {"kind": "agent", "id": "verifier-01"},
  "correlation_id": "c-001",
  "causation_id": "01J...",
  "policy_revision": "sha256:...",
  "source_revision": "git:...",
  "payload": {},
  "integrity": {"sha256": "...", "signature": null}
}
```

## 3. 事件词汇

- `issue.discovered`
- `issue.state.reconciled`
- `task.ready`
- `task.dispatched`
- `task.blocked`
- `task.retried`
- `workspace.created`
- `workspace.hook.failed`
- `agent.composed`
- `agent.stalled`
- `agent.escalated`
- `workpad.updated`
- `review.feedback.discovered`
- `review.feedback.resolved`
- `proof.assembled`
- `human.review.requested`
- `run.completed`
- `run.aborted`
- `workspace.removed`

## 4. 状态与事件原则

- 事件类型和 payload Schema 版本分离；消费者按兼容策略处理 optional 新字段。
- 未知 required event 必须拒绝/隔离；只有明确 `ignorable=true` 的扩展事件可以安全跳过。
- 顺序只在 aggregate/run/session 内承诺；跨 aggregate 通过 causation/correlation 和 outbox 对齐。
- 关键状态变更与 outbox 同事务提交；消费者幂等并记录最后处理 revision。
- 大输出、媒体、Trace、代码包和证据不嵌入事件；存内容 hash 与 artifact ref。

## 5. 保留与删除

- Session、代码、Trace、Evidence、计费和审计分别配置 retention；法规要求优先。
- 删除采用 tombstone + artifact lifecycle；需要保留的审计元数据不得包含原始敏感内容。
- P07 知识条目保存 scope/consent/derivation，支持撤销证据后的传播降级。

## 6. 数据库演进

- Schema migration 必须前向/回滚策略、备份点、数据量评估和 canary。
- 读路径先兼容新旧格式，再迁数据，再切写，最后清理旧字段。
- 长任务 Session/Event 格式变更优先提供 upgrader 或明确拒绝，不静默猜测。
