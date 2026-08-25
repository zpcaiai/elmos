# Elmos 数据库事务、幂等、租约与恢复 Runbook

**适用范围：** 大型仓库完整项目生成、跨语言/跨框架/跨数据库转换、长时间验证与自动修复任务。  
**权威数据源：** PostgreSQL。  
**工作流协调：** Temporal。  
**大对象：** S3/MinIO 等内容寻址对象存储（CAS）。

本文件回答四个生产问题：

1. 一次请求怎样避免重复创建任务？
2. Worker 崩溃、网络断开或服务重启后怎样继续？
3. 已超时的旧 Worker 为什么不能覆盖新 Worker 的结果？
4. 外部副作用超时后怎样避免重复执行？

---

## 1. 事务边界总原则

Elmos 不采用“一个数据库事务包住整个几小时任务”。长任务被拆成许多短事务，每个事务只提交一个可验证事实。

```text
用户请求
  → 准入事务
  → Run 创建事务
  → Task Claim 事务
  → Attempt 执行（事务外）
  → Artifact Staging/Publish 事务
  → Attempt Finish 事务
  → Checkpoint Seal 事务
  → P05 Completion 事务
```

### 1.1 PostgreSQL 负责

- 请求幂等；
- 账号并发槽；
- Job/Run/Task/Attempt 当前状态；
- Lease 与 fencing generation；
- 追加式事件；
- Checkpoint manifest；
- Artifact/CAS 元数据；
- 外部副作用回执；
- 用量、成本、收入账本；
- Coverage/Evidence/Gate；
- Outbox/Inbox；
- 审计。

### 1.2 Temporal 负责

- 长时间等待；
- 定时器；
- Workflow/Activity 重试；
- 暂停与继续；
- 编排状态机；
- 跨服务控制流。

Temporal 的 Workflow History 不能代替业务数据库，因为用户查询、财务、P05 Gate、租户隔离和审计仍需 PostgreSQL 的稳定领域模型。

### 1.3 CAS 负责

- 仓库压缩包、源文件正文；
- AST、CFG、DFG、Call Graph、Semantic IR Shard；
- Build/Test 完整日志；
- 模型完整长输出；
- Patch、生成文件快照；
- Screenshot、Video；
- Evidence 原始内容。

数据库仅存哈希、URI、大小、媒体类型、状态和业务引用。

---

## 2. 请求幂等与准入

### 2.1 幂等键

客户端提交任务时必须携带：

```text
tenant_id
account_id
idempotency_key
request_hash
```

推荐 `idempotency_key` 生命周期为 24–72 小时；同一个账号与键只允许对应一个 `core.job_submission`。

### 2.2 同键同内容

当 `(tenant_id, account_id, idempotency_key)` 已存在且 `request_hash` 相同：

- 返回原 Job；
- 不再次占用并发槽；
- 不再次创建 Temporal Workflow；
- 返回相同的 API 语义。

### 2.3 同键不同内容

当键相同但 `request_hash` 不同：

- 返回 HTTP `409 Conflict`；
- 记录 `audit.audit_event`；
- 不修改原 Job；
- 不尝试“猜测用户想覆盖”。

### 2.4 并发槽不能 Count-Then-Start

错误方式：

```sql
SELECT count(*) FROM exec.run WHERE account_id = $1 AND status = 'running';
-- 两个请求都看见 count=2
-- 两个请求都启动，最终变成 4 个
```

正确方式：调用：

```sql
SELECT * FROM core.claim_account_slot(
  p_tenant_id      => :tenant_id,
  p_account_id     => :account_id,
  p_job_id         => :job_id,
  p_owner_token    => :owner_token,
  p_lease_seconds  => 60
);
```

`core.account_task_slot` 为每个账号预建 3 行；函数通过行锁原子选择可用槽，递增 `lease_generation` 并返回 fencing token。

### 2.5 准入事务建议

```text
BEGIN
  插入/读取 job_submission
  插入 job
  绑定 input revision
  Claim account slot
  插入 outbox: workflow.start.requested
COMMIT

Outbox relay
  → 启动 Temporal Workflow（使用 job_id 作为 Workflow ID）
```

这样即使 API 在 COMMIT 后、启动 Workflow 前崩溃，Outbox relay 仍会补发；Workflow ID 幂等可阻止重复 Workflow。

---

## 3. Job、Run、RunAttempt、TaskAttempt 的含义

### 3.1 Job

用户可见的业务目标。一个 Job 可因重试、切换策略或重新基线而包含多个 Run。

### 3.2 Run

绑定一组精确 Revision 的一次端到端执行：

- requirement revision；
- source repository revision；
- target revision；
- workflow revision；
- policy revision；
- model-route revision；
- toolchain/environment revision。

### 3.3 RunAttempt

端到端 Run 的调度尝试。适用于：

- Temporal Workflow 重建；
- 整体恢复；
- 灾难恢复后的继续；
- 运行时版本升级导致的 continuation。

### 3.4 TaskAttempt

某个稳定 Task 的一次 Worker 执行。编译失败后的修复重跑、Worker 崩溃重跑、资源不足重跑都会产生新的 Attempt，旧 Attempt 不覆盖。

---

## 4. Task DAG 与可执行条件

`exec.task` 是稳定 DAG 节点，`exec.task_dependency` 保存依赖边。

Task 只有在以下条件同时满足时才能 Claim：

- Run 仍为可执行状态；
- Task 状态为 `queued` 或可重试状态；
- 所有 hard dependencies 已完成；
- `not_before` 已到；
- 未超过最大 Attempt；
- 没有有效 active lease；
- Worker capability 满足 task requirement；
- Tenant/Account/Run 预算未冻结；
- 人工 Gate 已满足。

建议调度器把“可执行性”计算放入 SQL/事务函数，而不是在应用内先读后写。

---

## 5. Lease、Generation 与 Fencing

### 5.1 为什么仅有 `lease_expires_at` 不够

场景：

```text
Worker A claim generation=7
A 网络暂停
lease 超时
Worker B claim generation=8
A 恢复并写入旧结果
```

若只看 Task ID，A 会覆盖 B。

### 5.2 Fencing Token

每次新 Claim 都必须递增 generation：

```text
attempt_id
lease_id
lease_generation
owner_token
expires_at
```

所有会改变权威状态的写入必须携带 `lease_generation`，数据库函数只接受当前 generation。

### 5.3 Claim

```sql
SELECT * FROM exec.claim_ready_task(
  p_tenant_id     => :tenant_id,
  p_run_id        => :run_id,
  p_worker_id     => :worker_id,
  p_owner_token   => :owner_token,
  p_lease_seconds => 90
);
```

Claim 事务必须同时：

- 锁定 Task；
- 使旧过期 Lease 失效；
- 创建 TaskAttempt；
- 创建 ExecutionLease；
- 递增 generation；
- 更新 Task 当前状态；
- 追加 `task.claimed` 事件。

### 5.4 Renew

Worker 每 20–30 秒续租一次 90 秒 Lease；推荐满足：

```text
renew interval ≤ lease TTL / 3
```

续租必须校验：

- attempt_id；
- owner_token；
- generation；
- lease 尚未被 revoked；
- Run 未取消/暂停。

### 5.5 Finish

`exec.finish_task_attempt` 必须在同一事务中：

- 校验 fencing；
- 完成 Attempt；
- 更新 Task；
- 使 Lease 失效；
- 绑定输出 Manifest/Artifact；
- 追加事件；
- 写 Outbox；
- 更新 Progress Snapshot。

### 5.6 旧 Worker 写回

数据库返回稳定错误，例如：

```text
STALE_FENCE
LEASE_REVOKED
ATTEMPT_NOT_ACTIVE
RUN_NOT_EXECUTABLE
```

旧 Worker 收到后必须丢弃本地结果，不得自动重新 Claim 同一 Task。

---

## 6. 追加式事件与当前状态

Elmos 同时保存：

- 当前状态表，服务于高频查询；
- append-only event，服务于恢复、审计和分析。

### 6.1 Run Event

每个 Run 有独立序号：

```text
run_id + sequence_no
previous_event_hash
payload_hash
current_event_hash
```

`exec.append_run_event` 对 cursor 行加锁，原子分配序号并形成哈希链。

### 6.2 Session Event

Session Event 保存模型可见的事实、工具调用/结果、Context Epoch 和 compaction 边界。只要信息进入后续模型请求，就必须能够从 Session log 重建。

### 6.3 状态与事件同事务

严禁：

```text
UPDATE task;
COMMIT;
-- 稍后再插 event
```

必须：

```text
BEGIN
  UPDATE task
  INSERT event
  INSERT outbox
COMMIT
```

否则数据库可能出现“状态已完成但审计中无完成事件”。

---

## 7. Checkpoint 与断点恢复

### 7.1 Checkpoint 内容

一个 Checkpoint 不复制所有数据，而保存一个 sealed manifest，描述：

- Run/Stage/Task 状态快照；
- Source/Target Revision；
- Repository Scan Revision；
- Semantic IR Revision；
- Requirement/Generation/Transformation Plan Revision；
- Workspace snapshot；
- Session sequence boundary；
- 已完成的副作用；
- Artifact manifest；
- Budget/usage cursor；
- 恢复兼容版本。

### 7.2 Seal

Checkpoint 仅在所有组件都 `available`、哈希匹配、manifest 已 sealed 后才能调用：

```sql
SELECT exec.seal_checkpoint(:checkpoint_id, :expected_revision);
```

### 7.3 Checkpoint 频率

建议：

- 每个 Stage 完成；
- 每 15–30 分钟；
- 每个高成本模型阶段后；
- 大规模文件生成批次完成后；
- 进入 P05 前；
- 人工审批前；
- 部署前。

### 7.4 恢复选择

恢复器选择：

1. 最新 sealed；
2. 未被 superseded；
3. 兼容当前 runtime/toolchain；
4. Artifact 全部可用；
5. Source/Target revision 与 Run 一致；
6. 无 unresolved unknown side effects。

不满足时回退到前一个 Checkpoint，而不是尝试修补不完整快照。

---

## 8. Workspace 恢复

`exec.workspace` 保存：

- workspace identity；
- backend/provider；
- sandbox mode；
- source/target roots；
- attached worker；
- snapshot artifact；
- lease/fence；
- cleanup state。

恢复顺序：

```text
验证 workspace lease
→ 从 snapshot 恢复
→ 校验 Git HEAD / file manifest
→ 校验 toolchain fingerprint
→ 重新建立 LSP/index
→ 继续 Task
```

如果 workspace 内容与 checkpoint manifest 不一致：

- 将 workspace 标为 `quarantined`；
- 新建 workspace；
- 从 sealed snapshot 恢复；
- 保留旧 workspace 供取证，不直接复用。

---

## 9. Artifact Staging 与原子发布

### 9.1 三阶段

```text
uploading → staged → available
```

1. Worker 将内容上传临时 key；
2. 计算 SHA-256、大小、媒体类型；
3. 插入 `artifact.staged_object`；
4. 服务端校验对象存在且 hash 相符；
5. CAS 原子 copy/rename 到最终 key；
6. 写 `artifact.object_blob` 和 `artifact.artifact`；
7. 标为 `available`。

### 9.2 数据库先写 available 的风险

若先写 `available` 再上传对象，消费者可能读取到不存在的对象。迁移中的触发器会拒绝没有可用 object blob 的 Artifact。

### 9.3 内容去重

`object_blob` 以 tenant + digest 为主要去重边界。跨租户物理去重可由存储层实现，但数据库和授权层不得暴露其他租户是否拥有相同内容。

---

## 10. 外部副作用与 Unknown Result

外部副作用包括：

- Git push/PR；
- Issue/Tracker 状态写入；
- 部署；
- DNS/云资源；
- 数据库 migration；
- 支付或计费动作；
- 通知。

### 10.1 Side-effect Key

每次副作用必须有稳定键：

```text
tenant_id
run_id
effect_type
idempotency_key
request_hash
```

先调用：

```sql
SELECT * FROM integration.reserve_side_effect(...);
```

### 10.2 状态

```text
reserved
sent
confirmed
failed
unknown_result
compensating
compensated
```

### 10.3 超时不等于失败

例如 GitHub API 超时，服务端可能已创建 PR。此时必须记为 `unknown_result`，进入 reconciliation；不得立即再次创建。

### 10.4 Reconciliation

Reconciler 使用 provider-native idempotency key、request hash、external reference 和查询 API 判断：

- 已成功：转 `confirmed`；
- 明确未执行：可重试；
- 状态矛盾：创建 `reconciliation_issue`，阻止 P05 完成；
- 需补偿：创建 `compensation_action`。

---

## 11. Pause、Resume、Cancel

### 11.1 控制请求

用户动作先进入 `exec.run_control_request`，再由 Orchestrator 应用。

```text
requested → applying → applied / rejected / failed
```

API 不直接把 Run 状态改为 paused/cancelled。

### 11.2 Pause

- 停止新 Task Claim；
- 当前可安全中断的 Activity 形成 Checkpoint；
- 不能中断的外部副作用等待回执；
- 释放或缩短 Worker lease；
- Run 转 `paused`。

### 11.3 Resume

- 校验 Revision/Policy/Runtime 兼容；
- 重新获取账号并发槽；
- 选择 sealed Checkpoint；
- 重对账副作用；
- 重新调度未完成 Task。

### 11.4 Cancel

- 撤销所有 Lease；
- 向 Worker 发 cancellation；
- 对可补偿副作用创建补偿；
- 保留 Artifact/Evidence/Audit；
- 释放账号槽；
- 不删除历史。

---

## 12. 服务重启恢复

### 12.1 Control API 重启

无特殊恢复；从 PostgreSQL 读取当前状态。

### 12.2 Scheduler 重启

启动时：

1. 获取 scheduler shard/leader lease；
2. 扫描 expired execution leases；
3. 将对应 Attempt 标记为 interrupted/expired；
4. 重新排队可重试 Task；
5. 扫描 `outbox_event` 未发布项；
6. 对账 Temporal Workflow；
7. 更新 Progress Snapshot。

### 12.3 Worker Controller 重启

- 从 Worker runtime 查询现存 Pod/VM；
- 对账 `worker_node` 与 `workspace`；
- 已不存在的 Worker 对应 lease 等待过期或主动 revoke；
- 存在但 owner token 不匹配的 Worker 隔离并终止。

### 12.4 PostgreSQL 故障恢复

数据库恢复后必须执行：

```text
Job/Run 状态
↔ Temporal Workflow
↔ Execution Lease
↔ Worker/Workspace
↔ Session/Event cursor
↔ Artifact/CAS
↔ Side-effect receipt
↔ Usage/Cost ledger
↔ Evidence revision
```

详见 `docs/BACKUP-RESTORE.md`。

---

## 13. Outbox 与 Inbox

### 13.1 Outbox

所有必须可靠发送到外部的消息与领域状态在同一事务写入 `integration.outbox_event`。

Relay 使用：

```text
FOR UPDATE SKIP LOCKED
→ publish
→ provider acknowledgement
→ mark published
```

发布端使用 `event_id` 作为消息键。

### 13.2 Inbox

消费者在处理消息前插入 `integration.inbox_message`，唯一键阻止重复消费。业务更新与 Inbox 标记必须在同一事务。

### 13.3 At-least-once

消息系统采用 at-least-once；数据库模型通过幂等键、Inbox 和状态机把重复投递转为相同结果，而不是假设 exactly-once transport。

---

## 14. 财务账本恢复

`usage_ledger`、`cost_ledger`、`revenue_ledger` 只追加，不 UPDATE/DELETE。

修正方式：

```text
原分录
+ 反向冲销分录
+ 正确分录
```

模型调用即使失败也可能产生费用，因此：

- 调用开始保存 price snapshot；
- provider 回执保存 tokens/cost；
- 没有回执时标为 estimated/unknown；
- 后续根据 generation metadata 或账单 reconciliation 修正。

---

## 15. P05 完成事务

唯一合法入口：

```sql
SELECT verify.complete_run_with_gate(
  p_tenant_id          => :tenant_id,
  p_run_id             => :run_id,
  p_gate_evaluation_id => :gate_id,
  p_actor_id           => :actor_id
);
```

函数会重新校验：

- Gate 绑定的所有 Revision 与 Run 完全一致；
- Evidence Bundle 已 sealed；
- Evidence 没有 foreign/revoked/stale；
- Requirement/Capability coverage 是当前权威版本；
- 所有 critical requirement 已满足；
- required verification suite 已通过；
- 无未完成 Task；
- 无开放的 unknown/high/critical semantic gap；
- 无 `unknown_result` 或未结算外部副作用；
- Run 仍处于可完成状态。

随后在一个事务内：

```text
Run → completed
Job → completed（若为当前权威 Run）
追加 run.completed 事件
写 completion Outbox
释放账号并发槽
```

任何一项失败均整体回滚。

---

## 16. 典型故障矩阵

| 故障 | 数据库事实 | 自动动作 | 是否允许 P05 完成 |
|---|---|---|---|
| 浏览器断开 | Run 不变 | 服务端继续 | 是，满足证据后 |
| Worker 进程崩溃 | Lease 过期、Attempt interrupted | 新 Attempt | 否，直到收敛 |
| Scheduler 重启 | Workflow/DB 仍在 | 扫描和重对账 | 否，恢复期间 |
| LLM 请求超时 | model_invocation timeout/unknown | 按策略重试或换路由 | 否，若 Task 未完成 |
| Tool 重复调用 | idempotency key 已存在 | 返回原结果 | 视结果而定 |
| Git push 超时 | side effect unknown_result | Provider reconciliation | 否 |
| Artifact 上传中断 | staged_object 未 available | GC 或续传 | 否，若被引用 |
| Session 写入中断 | Event cursor/hash 链可检测 | 从最后 durable seq 恢复 | 否，直到平衡 |
| Checkpoint 不完整 | 未 sealed | 回退前一个 | 否，不能以其恢复 |
| 数据库主备切换 | 事务回滚或提交 | 应用重试幂等事务 | 取决于恢复状态 |
| Evidence 被撤销 | evidence_revocation | Gate 失效/重新验证 | 否 |
| 旧 Worker 回写 | STALE_FENCE | 丢弃旧结果 | 不受污染 |

---

## 17. CI 必跑事务测试

至少覆盖：

1. 100 个并发请求对一个账号 Claim，最多 3 个成功；
2. 同一幂等键并发提交只产生一个 Job；
3. Lease 过期后 generation 递增；
4. 旧 generation 完成 Attempt 被拒绝；
5. 同一个 Run Event 并发追加得到连续序号；
6. Event UPDATE/DELETE 被拒绝；
7. Artifact 未 available 时无法被 sealed Manifest 引用；
8. Checkpoint 缺组件时无法 seal；
9. Side-effect `unknown_result` 阻止完成；
10. Evidence 被撤销后旧 Gate 无法完成 Run；
11. Coverage 变化后旧 Gate 无法完成；
12. P05 完成事务同步释放账号槽；
13. Outbox 重复发布不重复产生外部业务结果；
14. PostgreSQL failover 后幂等重试得到同一结果。

参考 SQL：`database/tests/invariants.sql`。

---

## 18. 运行时错误处理规范

应用必须按 SQLSTATE 或稳定业务错误码分类：

| 类别 | 处理 |
|---|---|
| serialization/deadlock | 带抖动重试短事务 |
| unique violation | 按幂等/冲突语义读取现有记录 |
| stale fence | 永不重试写回；终止旧 Worker |
| budget exhausted | 暂停或终止 Run |
| gate rejected | 产生 findings，不重试相同 Gate |
| transient connection | 重连并以幂等键重试 |
| constraint violation | 视为代码/数据错误，告警 |

重试必须有上限；不可对整个任意 SQL 块无差别重放。

---

## 19. 运维查询

查看过期 Lease：

```sql
SELECT * FROM exec.v_stalled_task_attempts
ORDER BY lease_expires_at;
```

查看无法完成的 Run：

```sql
SELECT *,
       (unfinished_task_count = 0
        AND critical_gap_count = 0
        AND unresolved_side_effect_count = 0
        AND latest_passing_gate_id IS NOT NULL) AS mechanically_ready
FROM verify.v_completion_readiness
WHERE unfinished_task_count > 0
   OR critical_gap_count > 0
   OR unresolved_side_effect_count > 0
   OR latest_passing_gate_id IS NULL
ORDER BY run_id;
```

查看未知副作用：

```sql
SELECT tenant_id, run_id, effect_type, idempotency_key, status, updated_at
FROM integration.side_effect_receipt
WHERE status = 'unknown_result'
ORDER BY updated_at;
```

查看槽位泄漏：

```sql
SELECT * FROM core.v_account_slot_usage
WHERE occupied_slots > active_runs;
```

更多查询见 `database/queries/operator_queries.sql`。
