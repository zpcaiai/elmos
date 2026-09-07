# Elmos 大型仓库项目生成与跨库转换数据库设计

**版本：** 1.1.0（随 Elmos Deployment Guide v1.1.0 发布）  
**数据库：** PostgreSQL 16+，建议 PostgreSQL 17  
**适用场景：** 完整商业项目生成、整库多语言/多框架转换、Legacy modernization、长任务恢复、多 Agent 软件工厂、P05 Evidence Gate、成本和收益核算。

## 1. 设计结论

Elmos 的数据库不是“把 Agent 聊天记录存下来”，而是大型软件工程执行过程的**权威运行数据平面**。它必须回答：

1. 谁提交了什么任务，输入究竟是哪一个不可变版本；
2. 哪个 Run、Stage、Task、Attempt 正在运行；
3. 当前 Worker 是否仍拥有写入权，旧进程能否被 fencing 拒绝；
4. 大型仓库扫描到了哪些文件、模块、符号、运行界面和能力；
5. 项目生成/转换计划覆盖了哪些需求和源能力；
6. 代码、构建、测试、差分观察和修复产生了哪些版本；
7. 哪些证据证明当前 Target Revision 可以完成；
8. 外部副作用是否成功，还是处于 `UNKNOWN_RESULT`；
9. 消耗了多少 Token、计算、存储与费用，预计还需多少机器时间；
10. 哪些经过验证的经验可以进入 Elmos 自有知识与规则体系。

最重要的不变量：

```text
Agent says "Done"
        ≠
Run completed

Run completed
        ⇔
P05 对精确 Revision 集合生成 GateEvaluation=pass
+ Evidence Bundle 已 sealed 且未撤销/未过期
+ 无未完成任务
+ 无未知或高危语义缺口
+ 无未结算外部副作用
+ 数据库完成事务成功
```

## 2. PostgreSQL、Temporal、CAS 和 Redis 的边界

| 组件 | 权威职责 | 不应承担的职责 |
|---|---|---|
| PostgreSQL | 准入、状态、事件序列、租约、版本绑定、检查点索引、Coverage、Evidence、账本、审计 | 完整源码、大型 AST/IR、完整日志和视频正文 |
| Temporal | 长任务控制流、Timer、Retry、Pause/Resume、Workflow History | 业务财务事实、永久 Evidence、唯一并发准入依据 |
| S3/MinIO CAS | 源码包、文件内容、Graph/IR Shard、构建物、日志、Trace、截图/视频、证书 | 当前任务状态、并发槽、账本和 P05 完成裁决 |
| Redis | 热缓存、限流、短期协调、UI 推送辅助 | 唯一事实源、并发任务准入、恢复检查点和费用账本 |

### 2.1 PostgreSQL 中不保存的正文

以下内容只保存 CAS 地址、SHA-256、大小、类型和逻辑引用：

- 源代码全文和二进制文件；
- 完整 AST、CFG、DFG、Call Graph、Repository Graph；
- 完整 Semantic IR；
- 模型的原始长请求和长输出；
- 完整编译、测试、压力测试 stdout/stderr；
- Screenshot、Video、SBOM 和签名正文；
- Workspace 完整快照。

这样可以让 PostgreSQL 专注于**可恢复、可裁决、可计费、可查询**的数据，而不是退化为对象存储。

## 3. 权威身份链

```text
Tenant
  └─ Account
      └─ Project
          ├─ Repository
          │   └─ RepositoryRevision
          └─ Job
              └─ Run
                  ├─ RunAttempt
                  ├─ Stage
                  │   └─ Task DAG
                  │       └─ TaskAttempt
                  ├─ Session / SessionEvent
                  ├─ Checkpoint / Manifest / Artifact
                  ├─ AnalysisSnapshot / SemanticIR / Capability Ledger
                  ├─ GenerationPlan / TransformationPlan
                  ├─ TargetRevision / PatchSet
                  ├─ VerificationExecution / EvidenceBundle
                  └─ GateEvaluation
```

### 3.1 Job 与 Run 必须分开

- `Job` 是用户购买或提交的业务工作项。
- `Run` 是该 Job 的一次独立执行。
- 模型升级、人工重试、策略变化、灾难恢复后的重新执行均产生新 Run 或新 RunAttempt。
- 历史失败 Run 不得被后续成功 Run 覆盖。

### 3.2 Run 与 RunAttempt 必须分开

一个 Run 可以因为：

- 服务重启；
- Worker 丢失；
- Temporal Continue-As-New；
- 人工 Resume；
- 自动 Retry；
- Reconciliation；

产生多个 `run_attempt`。Run 的产品身份保持不变，Attempt 记录本次进程级执行边界。

## 4. 不可变 Revision 绑定

每个 Run 在开始时固定：

```text
source_repository_revision
baseline_repository_revision
requirements_revision
policy_revision
workflow_revision
model_route_revision
toolchain_revision
environment_revision
project_archetype_revision
input_bundle_sha256
```

任何一个发生变化，都必须生成新 Revision，并通常进入新 Run/Execution Epoch。不得原地修改旧 Revision。

P05 Gate 必须重新绑定同一组 Revision；仅凭“测试刚刚通过”不能完成任务。

## 5. 13 个业务 Schema

| Schema | 主要职责 |
|---|---|
| `core` | Tenant、Account、Project、Repository、Job、Revision、并发槽 |
| `exec` | Run、Stage、Task DAG、Attempt、Lease、Workspace、Session、Event、Checkpoint |
| `artifact` | CAS 元数据、Artifact、Manifest、Staging、Archive |
| `analysis` | File/Module/Symbol 索引、Graph/IR Shard、Capability Ledger |
| `generation` | Requirement Graph、Archetype、Architecture、Generation Plan/Unit/File |
| `transform` | Transformation Plan/Unit、Mapping、Rule、Target Revision、Patch、Cutover |
| `verify` | Coverage、Test、Differential、Gap、Evidence、Gate、Repair、Certification |
| `metering` | Model/Tool/Resource Usage、Budget、Cost、Revenue、ETA |
| `cache` | 确定性缓存、依赖、访问收益、失效事实 |
| `integration` | Outbox/Inbox、外部副作用、补偿、对账 |
| `learning` | 验证后的转换案例、Repair Trace、Rule Promotion、Benchmark |
| `ops` | Release、Image Component、Migration、Health、Deployment Gate |
| `audit` | 不可变安全与操作审计 |

完整参考迁移包含 **136 张父表**。这代表商业产品全量目标模型，不是要求 MVP 一次启用全部能力。

## 6. 大型仓库运行阶段与保存点

### Phase A：提交、幂等和准入

```text
HTTP/API Request
  → core.job_submission
  → core.job
  → core.job_input_revision
  → exec.run
  → core.account_task_slot Claim
```

保存：

- 请求 SHA-256 与 idempotency key；
- Job 类型、优先级和业务状态；
- 每个输入的精确 Revision；
- Run 编号与 input bundle hash；
- 账号的三个固定并发槽；
- Slot lease generation、claim token 和 expiry。

严禁：

```text
SELECT count(active jobs)
if count < 3:
    start job
```

必须使用数据库行锁和固定 Slot：

```text
SELECT candidate slot
FOR UPDATE SKIP LOCKED
→ update slot claim + generation
→ bind run
→ commit
```

### Phase B：输入导入和仓库扫描

```text
RepositoryRevision
  → repository_scan
  → repository_file
  → module_record
  → build_target
  → dependency_record
```

数据库保存：

- 归一化路径、Path Hash、Content Hash、Semantic Hash；
- 文件类型、语言、框架、大小、行数；
- Generated/Vendor/Test 标记；
- Parser 与版本；
- 模块、Build Target 和依赖摘要。

CAS 保存：

- 文件正文；
- Source Manifest；
- 完整 File Catalog 导出。

### Phase C：语义分析和能力发现

```text
repository_file
  → symbol_record
  → runtime_surface
  → graph_shard
  → semantic_ir_revision / ir_shard
  → capability / capability_edge
  → unsupported_semantic
```

`runtime_surface` 专门记录容易被普通代码生成遗漏的能力：

- API/RPC；
- DB、Migration、Trigger、Stored Procedure；
- MQ Producer/Consumer 与 ACK 语义；
- Cron/Scheduled Job；
- Cache、Redis Lua；
- Security Rule、Filter、Interceptor；
- Feature Flag；
- WebSocket/SSE；
- 文件和外部 API 副作用；
- Observability 和配置语义。

`Capability Ledger` 是完整度计算的基础：

```text
DISCOVERED
→ CONFIRMED
→ MAPPED
→ GENERATED
→ VERIFIED

或
UNSUPPORTED / SEMANTIC_GAP / SUPERSEDED
```

### Phase D：需求扩展和完整项目规划

```text
requirement_set
  → requirement_node / edge
  → acceptance_criterion
  → archetype_selection
  → architecture_revision
  → project_generation_plan
  → generation_unit
```

用户只写“生成一个支付系统”时，Elmos 可以通过 Archetype Baseline 扩展：

- Idempotency；
- Webhook 签名与 Retry；
- Reconciliation；
- Partial Refund；
- Ledger；
- Audit；
- Risk Control；
- Key Rotation；
- Backup/DR；
- Observability；
- CI/CD；
- Security Boundary。

每一项必须形成 Requirement/Acceptance/Implementation/Test/Evidence 的闭环。

### Phase E：项目生成或跨库转换

项目生成：

```text
generation_unit
  → generation_iteration
  → generated_file
  → target_revision
```

跨库转换：

```text
transformation_plan
  → transformation_unit
  → mapping_decision
  → rule_application
  → patch_set
  → target_revision
```

每次迭代必须记录：

- 输入 Fingerprint；
- Trigger：initial、compile repair、test repair、gap repair 等；
- Agent/Model/TaskAttempt；
- Output Manifest；
- Target Revision；
- 生成文件的 Artifact/Hash/Origin；
- Mapping 的来源：Certified Rule、Trusted Rule、Model、Human、Fallback。

### Phase F：构建、验证、差分和修复

```text
verification_plan
  → suite
  → case
  → execution
  → result
  → behavior_observation
  → differential_mismatch
  → semantic_gap
  → repair_attempt
```

Differential Runtime 应比较：

```text
Response
Database state
Cache state
Message events
Filesystem state
Transaction outcome
Authorization outcome
Exception contract
Timing constraints
```

每次 Repair 都产生新的 Target Revision，禁止在 Evidence 已绑定的 Revision 上静默改代码。

### Phase G：Evidence 和 P05 Gate

```text
evidence_item
  → evidence_bundle_item
  → evidence_bundle(sealed)
  → gate_evaluation(pass/fail/blocked)
  → complete_run_with_gate()
```

`evidence_item` 必须包含：

- Run 和 Target Revision；
- Evidence Kind；
- Subject；
- Producer/TaskAttempt；
- Run Event Sequence；
- Artifact 和 SHA-256；
- Environment/Toolchain Revision；
- Freshness Deadline。

Evidence 不能原地删除或篡改。失效通过 `evidence_revocation` 新增事实表达。

### Phase H：学习与能力沉淀

只有满足：

```text
Gate=pass
+ DataAuthorization 允许
+ TargetRevision 精确
+ Evidence 可追溯
```

的记录才能进入：

- `transformation_case`；
- `repair_trace`；
- `rule_candidate`；
- `rule_validation`；
- `rule_release`；
- `benchmark_*`。

规则晋升：

```text
EXPERIMENTAL
→ CANDIDATE
→ VALIDATED
→ TRUSTED
→ CERTIFIED
→ DEPRECATED / REVOKED
```

一次 Repair 成功不能直接成为全局规则。

## 7. 状态表与事件流并存

Elmos 不应只使用 Event Sourcing，也不应只保留最终状态。

### 7.1 状态表

用于：

- 任务列表和 Dashboard；
- 调度；
- 当前状态查询；
- 限流和准入；
- 快速恢复入口。

代表：`run`、`task`、`task_attempt`、`run_progress_snapshot`。

### 7.2 Append-only 事件流

用于：

- 审计；
- Replay；
- 精确恢复；
- 判断状态如何形成；
- 生成统计和训练样本。

代表：`run_event`、`session_event`、`audit_event`、Ledger。

### 7.3 双写原则

业务状态更新与 Outbox 必须在同一 PostgreSQL 事务；Temporal Signal/外部消息由 Outbox Relay 异步发布。

```text
BEGIN
  update state
  append run_event
  insert outbox_event
COMMIT

Outbox Relay
  → publish Temporal Signal / Kafka / WebSocket
```

禁止直接：

```text
update Postgres
call Temporal
```

因为进程可能在两者之间崩溃。

## 8. Task DAG、Attempt、Lease 和 Fencing

### 8.1 Task 是稳定工作单元

`task.id` 和 `task_key` 在 Run 内稳定，Retry 不创建新 Task，而是创建新 `task_attempt`。

### 8.2 Attempt 是执行尝试

保存：

- Worker；
- Workspace；
- Model Route/Toolchain；
- Attempt No；
- Input/Output Manifest；
- Checkpoint；
- Exit/Failure；
- Heartbeat；
- Fencing Token。

### 8.3 Lease Generation 防止旧 Worker 写回

```text
Attempt A generation=7
Worker lost
Lease expires
Attempt B generation=8

Worker A later returns result
→ generation/fencing mismatch
→ database rejects stale write
```

`finish_task_attempt()` 必须验证：

- task attempt id；
- lease token；
- lease generation；
- fencing token；
- lease 尚未过期。

### 8.4 一个资源只能有一个 Active Lease

迁移使用 Partial Unique Index：

```sql
UNIQUE (tenant_id, resource_kind, resource_id)
WHERE released_at IS NULL
```

过期 Lease 必须先写入 `released_at/release_reason`，再创建新 Generation。

## 9. Session、Context Epoch 和 Compaction

`session_event` 是 Agent 会话的可重放事实流。模型可见输入必须可由日志重建。

Context 不是一个不断原地修改的 system prompt，而是：

```text
Context Epoch
  ├─ immutable baseline system context
  ├─ context snapshot
  ├─ tool schema hash
  └─ mid-conversation durable updates
```

Compaction 保存：

- 前后 Token 数；
- 任务状态保留 Hash；
- Summary Artifact；
- Trigger/Kind；
- 新 Context Epoch。

压缩不能丢失：

- 当前 Task 状态；
- 已完成与待办；
- 修改文件；
- 重要架构决定；
- Blocker；
- Acceptance 和 Validation；
- 子 Agent 状态。

## 10. Artifact、Staging 和原子发布

生成文件不能直接写入最终 Target Tree。

```text
RESERVED
→ WRITING
→ SEALED
→ CAS_PROMOTED
→ TREE_INCLUDED
→ PUBLISHED
```

异常状态：`QUARANTINED`、`ABORTED`。

只有：

- Hash 完整；
- Object Blob Available；
- Manifest sealed；
- Writer Fencing Token 有效；

时才能进入 Target Revision。

## 11. Checkpoint 设计

Checkpoint 不是一个 JSON 字段，而是：

```text
checkpoint
  ├─ manifest
  ├─ source_event_seq
  ├─ execution_epoch
  ├─ resume_class
  └─ checkpoint_component[]
```

组件示例：

- Task DAG snapshot；
- Repository scan cursor；
- Graph/IR shard progress；
- Workspace tree；
- Session state；
- Tool background task registry；
- Verification plan and completed suites；
- Staged object manifest；
- Side-effect reconciliation cursor。

Resume Class：

| 值 | 含义 |
|---|---|
| `same_process` | 仅同进程可继续，商业生产尽量避免 |
| `same_worker` | 依赖本地 Worker 状态 |
| `same_environment` | 相同 Toolchain/Environment 可继续 |
| `portable` | 可在任意兼容 Worker 恢复 |
| `manual_only` | 必须人工恢复 |

## 12. 外部副作用与 Unknown Result

所有外部写操作先 `reserve_side_effect()`：

```text
(destination, idempotency_key, request_sha256)
```

如果同一 key 对应不同 request hash，数据库拒绝。

网络超时时不能简单记为 failed：

```text
Request sent
Network timeout
Unknown whether provider committed
→ status=UNKNOWN_RESULT
→ reconciliation
→ query provider by idempotency key/external id
→ succeeded / failed / compensate
```

存在以下状态时，P05 不能完成：

- `reserved`；
- `dispatching`；
- `unknown_result`；
- `reconciling`；
- `compensating`。

## 13. 成本、收入、预算和 ETA

### 13.1 每轮 Model Invocation

保存：

- Provider/Endpoint/Model；
- Agent Role/Turn/Round Kind；
- Request/Response Hash 和 Artifact；
- Input/Output/Cached/Reasoning Tokens；
- First-token latency 和总时长；
- Reported/Calculated cost；
- Price Snapshot；
- Retry lineage。

### 13.2 Tool Invocation

保存：

- call/root/parent identity；
- sync/background/deferred/manual/subagent lifecycle；
- arguments/result hash；
- Approval；
- timeout/concurrency；
- pending/unknown result；
- 外部 Task ID。

### 13.3 不可变 Ledger

- `usage_ledger`：数量事实；
- `cost_ledger`：成本分录；
- `revenue_ledger`：收入/退款/分摊；
- 修正使用新的 Adjustment/Credit 行，不修改旧行。

### 13.4 ETA 必须分开

```text
machine_wall_clock_remaining_p50/p90
human_equivalent_hours_p50/p90
expected_hitl_wait_seconds
estimated_cost_p50/p90
```

Elmos 对外首先显示**系统自主执行的机器墙钟时间**，人工等效工时仅用于商业对比，人工审批等待单独显示。

## 14. Cache 数据模型

Cache Key 必须由稳定输入构造：

```text
namespace
+ input fingerprint
+ policy fingerprint
+ toolchain fingerprint
+ environment fingerprint
+ dependency hashes
```

记录：

- Entry/Artifact/Hash；
- Dependency；
- Hit/Miss/Read/Write；
- 避免 Token、计算时间和成本；
- Invalidation reason；
- TTL 与状态。

不得仅因路径和模型名相同就命中缓存。

## 15. P05 完成事务

`verify.complete_run_with_gate()` 的参考流程：

```text
lock run
load passing gate
verify exact revision binding
load sealed evidence bundle
verify bundle count
reject foreign/revoked/stale evidence
recompute requirement coverage
recompute capability coverage
verify critical requirements
verify every required suite has a passing execution
count unfinished tasks
count unknown/high/critical semantic gaps
count unresolved side effects
update run=completed
update job=completed
append run.completed event
insert outbox
release account slot
refresh projection
commit
```

其中任一检查失败，整个事务回滚。

## 16. 部署完成门

部署完成也不能仅因 Kubernetes Rollout 返回成功而通过。

数据库保存：

- Release、Git SHA、Image Manifest、SBOM、Signature；
- Release Component 及精确 Image Digest；
- Migration Run；
- 每个组件的 `/livez`、`/readyz`、`/metrics`、`/version` 快照；
- Smoke/Security/Rollback/P05 Check；
- Deployment Gate。

`ops.complete_deployment_with_gate()` 要求：

- Gate=pass；
- Release 匹配；
- 无 failed/blocked/not_run Check；
- 所有 required component 最新 Health 为 live+ready；
- 实际 Image Digest 等于 Release Component Digest；
- 必需 Migration 成功或明确 not_required。

## 17. 分区策略摘要

高写入表使用 Hash Partition：

- `exec.run_event`：按 `run_id`，16 分区；
- `exec.session_event`：按 `session_id`，16 分区；
- `analysis.repository_file`：按 `repository_revision_id`，16 分区；
- `analysis.symbol_record`：按 `repository_revision_id`，16 分区；
- `generation.generated_file`：按 `run_id`，16 分区；
- `integration.outbox_event`：按 `tenant_id`，16 分区；
- `audit.audit_event`：按 `tenant_id`，16 分区。

商业规模扩大后，可从 Hash 迁移到：

```text
tenant hash
  + monthly range
```

但不要在早期引入双层分区复杂度。

## 18. 大型仓库规模分层

| 级别 | 文件量 | Symbol 量 | 建议 |
|---|---:|---:|---|
| S | <50k | <1M | 完整 File/Symbol 入库 |
| M | 50k–250k | 1M–5M | 分区、批量 COPY、Graph/IR 外置 |
| L | 250k–1M | 5M–20M | Symbol 按 Module/Shard 分批；只保留热点与摘要 |
| XL | >1M | >20M | Catalog 分层；冷 Symbol/Edge 仅 CAS/专用检索，Postgres 保存 Shard Index |

### 18.1 写入方式

大批 File/Symbol：

- Worker 写本地 Parquet/JSONL；
- 上传 CAS；
- 通过 `COPY` 或批量加载进入 staging；
- 校验行数和 Hash；
- 原子发布 Scan/IR Snapshot；
- 避免逐行 ORM Insert。

## 19. 索引策略

必须有：

- Run/Task 状态队列 Partial Index；
- Heartbeat/Lease Expiry Index；
- File Path 和 Symbol Qualified Name `pg_trgm`；
- Capability/Gap/Coverage 状态索引；
- Event `(tenant, aggregate, seq)` 主键；
- Outbox pending index；
- Side Effect unresolved index；
- Financial Ledger `(tenant, run, occurred_at)`；
- Evidence subject/freshness；
- Target Revision latest index。

避免：

- 对大 JSONB 无差别 GIN；
- 对所有状态值建普通索引；
- 在高写事件表添加过多二级索引；
- 用随机 UUIDv4 作为唯一聚簇写入策略。应用优先使用 UUIDv7。

## 20. Retention 与归档

| 数据类型 | 热存建议 | 后续处理 |
|---|---:|---|
| Job/Run/Financial/Audit | 合同期 + 法规期 | 长期保留或合规归档 |
| Run/Session Event | 90–180 天热存 | CAS Archive + 冷库 |
| File/Symbol Index | Active Revision + 最近 N 个 | 旧 Revision 归档/重建 |
| Graph/IR | DB 仅索引 | CAS 生命周期管理 |
| Tool/Model Invocation | 90–365 天明细 | 日/周聚合后归档 |
| Verification/Evidence | 与交付物同寿命 | WORM/Object Lock |
| Workspace/Staging | Run 结束后短期 | 清理前必须确认 Manifest/Checkpoint |
| Cache | TTL/失效驱动 | 可重建、不可作为唯一事实 |

删除必须按 Tenant/Project Retention Policy 执行，并留下 Audit/Deletion Tombstone。

## 21. 多租户安全

所有租户表：

```text
ENABLE ROW LEVEL SECURITY
FORCE ROW LEVEL SECURITY
```

应用事务开始：

```sql
SET LOCAL app.tenant_id = '<tenant-uuid>';
SET LOCAL app.actor_id = '<actor>';
SET LOCAL app.request_id = '<request-id>';
```

角色分离：

- `elmos_app`：普通 RLS 访问；
- `elmos_scheduler`：仅调度函数；
- `elmos_worker`：仅 Worker 函数和受限读；
- `elmos_verifier`：Evidence/Gate；
- `elmos_reconciler`：受审计的跨状态修复；
- `elmos_migrator`：DDL；
- `elmos_auditor`：只读审计；
- 表 Owner 不能作为应用登录角色。

Security-definer Function 必须：

- 固定 `search_path`；
- `REVOKE EXECUTE FROM PUBLIC`；
- 显式检查 tenant/run/account；
- 不接受任意 SQL；
- 写 Audit。

详见 `DATABASE-SECURITY-RLS.md`。

## 22. 恢复矩阵

| 故障 | 权威恢复来源 | 处理 |
|---|---|---|
| 浏览器断线 | Run/Progress/Event | 服务端继续，客户端重连读取 |
| Control API 重启 | PostgreSQL + Temporal | 重建状态，无需重跑 Worker |
| Scheduler 重启 | Temporal + Task/Lease | Reconcile 后重新调度 |
| Worker 崩溃 | Heartbeat/Lease/Checkpoint | 标记 Attempt lost，Generation+1 重试 |
| Agent Session 崩溃 | Session Event/Context Epoch | 关闭 interrupted turn，Resume/Fork |
| Workspace 丢失 | Manifest/Checkpoint/CAS | 新 Worker 恢复 |
| 外部 API 超时 | SideEffectReceipt | UNKNOWN_RESULT → Reconciliation |
| DB Commit 成功、Signal 失败 | Outbox | Relay 重发 |
| Signal 成功、DB 未写 | Inbox/Idempotency | 重复消费被去重 |
| Evidence 失效 | EvidenceRevocation | Gate 不可复用，重新验证 |
| 规则发现错误 | Rule Release Revocation | Cache invalidation + Benchmark 回归 |

## 23. 上线阶段

### DB-1：Durable Execution Core

约 35 张核心表，另加 8–10 张可选计量/P05表：

- Core Identity/Job/Revision/Slots；
- Run/Stage/Task/Attempt/Lease；
- Run Event/Progress；
- Workspace/Session/Checkpoint；
- Artifact/Manifest/Staging；
- Outbox/Inbox/Side Effect；
- 最小 Model/Tool/Cost/ETA；
- 最小 Evidence Bundle/Gate。

退出标准：断线、Scheduler/Worker 崩溃、重复提交和过期 Lease 全部可恢复。

### DB-2：Repository Intelligence

加入：

- File/Module/Build/Dependency；
- Symbol/Runtime Surface；
- Graph/IR Shard；
- Capability Ledger。

退出标准：大型仓库“未知遗漏”可被量化。

### DB-3：Generation/Transformation + P05

加入：

- Requirement Graph/Archetype/Architecture；
- Generation/Transformation Plan；
- Target Revision/Patch；
- Coverage/Differential/Gap/Repair；
- 全量 Evidence/Gate/Certification。

退出标准：项目生成/跨库转换能以 Evidence 完成，而非 Agent 自报。

### DB-4：Learning、Benchmark、Deployment Operations

加入：

- Repair/Transformation Corpus；
- Rule Promotion；
- Benchmark；
- Release/Health/Migration/Deployment Gate；
- 全量收入和商业分析。

退出标准：每次验证后的项目经验可安全反哺 Elmos。

## 24. 数据库 SLO

建议首个商业版本：

| 指标 | 目标 |
|---|---:|
| Job 提交幂等冲突判定 | P95 < 50 ms |
| Account Slot Claim | P95 < 100 ms |
| Task Claim | P95 < 150 ms |
| Event Append | P95 < 30 ms |
| Progress Read Model | P95 < 100 ms |
| Worker Lease Recovery | < 2 × lease TTL |
| Checkpoint RPO | 关键阶段 ≤ 1 分钟 |
| Event/Outbox 丢失 | 0 |
| Financial Ledger 重复计费 | 0 |
| 跨租户读取 | 0 |
| Stale Worker 成功写回 | 0 |
| 未经 P05 Gate 的 completed | 0 |

## 25. 验收用例

至少覆盖：

1. 同一 idempotency key + 相同请求返回同一 Job；
2. 同一 key + 不同请求拒绝；
3. 一个 Account 只能占用配置上限内的三个固定槽；
4. 并发 100 次 Claim 不超配；
5. Slot/Task Lease 过期后 Generation 增长；
6. 旧 Worker 写回被 fencing 拒绝；
7. Run Event/Session Event sequence 无断裂且 Hash Chain 正确；
8. Manifest 未 sealed 时不能 seal Checkpoint；
9. Evidence Artifact 不可用时拒绝 Evidence；
10. Evidence 撤销/过期后拒绝完成；
11. Gate Revision 与 Run 不一致时拒绝；
12. Coverage 报告与 Ledger 不一致时拒绝；
13. Required Verification Suite 无 PASS 时拒绝；
14. 存在未知/高危 Gap 时拒绝；
15. 存在 `UNKNOWN_RESULT` Side Effect 时拒绝；
16. 完成事务同时更新 Run/Job/Event/Outbox/Slot；
17. 任一写失败时整个完成事务回滚；
18. RLS 跨 Tenant 测试为零泄漏；
19. Migration/Health/Image Digest 不匹配时 Deployment Gate 拒绝；
20. Cost/Revenue Ledger 重放不重复。

## 26. 参考实现文件

```text
database/
├── migrations/V001...V090
├── queries/operator_queries.sql
├── tests/invariants.sql
├── mermaid/large-run-erd.mmd
├── TABLE-CATALOG.md
└── README.md

scripts/
└── validate_database_design.py
```

部署前执行：

```bash
python3 scripts/validate_database_design.py
python3 scripts/validate_bundle.py
```

静态校验不能替代真实 PostgreSQL Migration Test。CI 必须再创建临时 PostgreSQL 16/17 数据库，顺序执行全部迁移并运行 `database/tests/invariants.sql`。
