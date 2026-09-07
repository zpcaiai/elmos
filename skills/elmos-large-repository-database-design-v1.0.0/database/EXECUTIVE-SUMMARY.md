# Elmos 大型仓库项目生成数据库设计执行摘要

## 1. 设计目标

本设计服务于以下长任务：

- 从需求生成完整商业项目；
- Java、Kotlin、Python、C#、Go、Rust、C++、PHP、TypeScript、JavaScript、Swift、Objective-C、Flutter 等项目的跨语言转换；
- Spring、ASP.NET、FastAPI、NestJS、Vue、React、Flutter、小程序等跨框架转换；
- 数据库、消息、缓存、权限、事务、定时任务和基础设施的跨栈迁移；
- 自动测试、差分验证、自动修复、P05 Evidence Gate 和发布部署。

数据库必须同时解决：

1. 数小时到数天任务的暂停、断线、进程崩溃与恢复；
2. 百万文件、千万 Symbol、数万 Capability 的可查询索引；
3. 多 Agent、多 Worker、多模型并行且不重复执行副作用；
4. 每账号最多 3 个运行任务的原子准入；
5. Token、资源、成本、收入和机器 ETA 对账；
6. 只有可信 Evidence 才能完成任务；
7. 每次已验证的转换和修复都可沉淀，但不得污染全局知识。

## 2. 四种存储的明确边界

| 存储 | 保存内容 | 禁止承担的职责 |
|---|---|---|
| PostgreSQL | Job/Run/Task、租约、关键事件、Checkpoint、Artifact 元数据、Coverage、Evidence、Gate、成本/收入、审计 | 不保存完整源码、完整 AST/IR、超长日志、视频 |
| Temporal | Workflow、Timer、Retry、Pause/Resume、Signal | 不是业务状态、财务账本或完成权威 |
| S3/MinIO CAS | 源码包、文件正文、Graph/IR Shard、Patch、构建物、日志、截图、视频、Evidence Payload | 不能替代可查询事务索引 |
| Redis | 热缓存、速率限制、短期协调 | 不能成为任务、租约、计费或完成的事实源 |

大型正文进入 CAS 后，PostgreSQL 只保存：

```text
artifact_id
sha256
media_type
size_bytes
storage_namespace
object_key
manifest_id
producer_attempt_id
retention_class
state
```

## 3. 权威对象链

```text
Tenant
  └─ Account
      └─ Project
          └─ Job
              └─ Run
                  ├─ RunAttempt
                  ├─ Stage
                  ├─ Task DAG
                  │   └─ TaskAttempt
                  │       ├─ ExecutionLease
                  │       ├─ Workspace
                  │       ├─ Session/Event
                  │       └─ Tool/Model Invocation
                  ├─ Checkpoint Manifest
                  ├─ Repository/IR/Capability Index
                  ├─ Generation/Transformation Plan
                  ├─ Verification/Evidence/Repair
                  └─ P05 GateEvaluation
```

`Job` 表示用户购买和查看的业务任务；`Run` 表示一次精确输入和规则 Revision 下的执行；`TaskAttempt` 表示一个 Worker 可以持有租约的最小执行单元。

## 4. DB-1A：34 张强一致核心表

首发不需要立即启用全量 136 张表。先上线 DB-1A：

- `core`：Tenant、Account、Project、Repository、Revision、Job、幂等提交、账号 3 槽；
- `exec`：Run、Stage、Task DAG、Attempt、Lease/Fence、Event、Session、Control、Recovery、Checkpoint；
- `artifact`：CAS Object、Artifact、Manifest、Manifest Entry、Staged Object。

DB-1A 必须证明：

```text
submit once or retry safely
→ atomically claim account slot
→ create run and DAG
→ claim/renew/finish task with fencing
→ append ordered events
→ publish CAS artifact atomically
→ seal checkpoint
→ kill worker
→ resume from checkpoint without duplicate side effects
```

完整清单见 `DB-1-MINIMUM-TABLE-SET.md`。

## 5. DB-1B：运营与商业闭环

DB-1A 稳定后增加：

- Context Epoch、Compaction、Workpad、Approval、Human Gate；
- Outbox/Inbox、Side Effect Receipt、Compensation、Reconciliation；
- Model/Tool Invocation、Usage/Cost/Revenue Ledger、Budget、ETA；
- Audit Event。

这部分解决多租户商业系统的可运营性，而不是转换算法本身。

## 6. DB-2：仓库智能与 Semantic IR

`analysis` Schema 只保存可查询索引和 Shard 坐标：

- Repository Inventory 与 Module；
- File Catalog 与文件版本摘要；
- Symbol、Reference、Call Edge；
- Runtime Surface：API、DB、MQ、Cache、Cron、Security、Config；
- Graph Snapshot 与 Shard；
- Semantic IR Revision 与 Shard；
- Capability Ledger 与 Capability Mapping；
- Semantic Gap。

文件正文、AST、CFG、DFG、Call Graph 大块和 IR 正文均进入 CAS。

对于百万文件仓库：

```text
PostgreSQL: one row per searchable file/symbol/capability metadata
CAS: compressed immutable shard bodies
Read model: aggregate counts and hot gaps
```

当 Symbol 达到千万级时，允许从逐 Symbol 全量索引降级为按 Module/Shard 摘要，但 Capability Ledger 和关键 Runtime Surface 不得降级。

## 7. DB-3A：完整项目生成

`generation` Schema 保存：

- Requirement Revision 与 Requirement Node；
- Acceptance Criterion；
- Project Archetype Revision；
- Architecture Revision、Component、Interface；
- Generation Plan 与 Generation Unit；
- Generated File Catalog；
- Dependency、Configuration、Infrastructure Plan；
- Target Revision Candidate。

每条需求必须能够闭合：

```text
Requirement
→ Architecture element
→ Generation unit
→ Generated artifact
→ Verification case
→ Evidence
```

生产级周边能力通过 Archetype/Capability Baseline 自动补齐，例如 RBAC、审计、幂等、限流、Secret、备份、可观测、CI/CD 和灾备。

## 8. DB-3B：跨库转换

`transform` Schema 保存：

- Transformation Plan；
- Transformation Unit；
- Source→Target Mapping；
- Rule Application；
- Patch Set 与 Patch；
- Target Repository Revision；
- Compatibility/Exception/Manual Review 状态。

一个转换单元不是简单“一个文件”，而应围绕可验证语义边界，例如：

```text
transaction boundary
message consumer
REST endpoint
authorization policy
scheduled job
UI route/state flow
schema migration
```

这样修复和差分验证能精确回写到 Capability 和 Rule。

## 9. DB-3C：P05 验证与证据

`verify` Schema 保存：

- Verification Plan、Suite、Case、Execution；
- Assertion 与 Failure；
- Requirement Coverage；
- Capability Coverage；
- Differential Observation；
- Invariant Evaluation；
- Semantic Gap 与 Risk Finding；
- Evidence、Evidence Bundle、Bundle Entry、Revocation；
- Repair Cycle、Diagnosis、Repair Attempt；
- Gate Policy、Gate Evaluation、Gate Check。

完成门绑定精确 Revision：

```text
source repository revision
baseline revision
target revision
requirements revision
policy revision
workflow revision
model route revision
toolchain revision
environment revision
archetype revision
```

任何 Revision 变化都会使旧 Evidence 失效或必须重新评估。

## 10. 原子 3 槽准入

禁止：

```text
SELECT count(*)
if count < 3:
  INSERT running task
```

因为并发请求会同时通过检查。

正确路径：

1. 每账号预建 `account_task_slot(slot_no=1..3)`；
2. `core.claim_account_slot()` 对候选槽 `FOR UPDATE SKIP LOCKED`；
3. Claim 产生 `claim_token + lease_generation + expires_at`；
4. 续租必须匹配 Run、Slot、Generation、Token；
5. 完成事务内释放槽；
6. 过期槽由 Reconciler 回收，但旧 Worker 不能再写。

## 11. Task Lease 与 Fencing

`execution_lease` 防止两个 Worker 同时认为自己拥有 Task；`fencing_token` 防止失去租约的旧 Worker 在稍后恢复网络后写入陈旧结果。

所有权威写入必须携带：

```text
task_attempt_id
lease_token
lease_generation
fencing_token
```

`exec.finish_task_attempt()` 在同一事务内：

- 锁定 Attempt/Lease；
- 验证四元组；
- 写入结果 Artifact/状态；
- 关闭 Attempt；
- 更新 Task；
- 释放 Lease；
- 追加 Run Event/Outbox；
- 刷新 Progress。

## 12. 事件流与 Checkpoint

Run Event 和 Session Event 均为 append-only、有序、带 Hash Chain 的事实流：

```text
cursor row FOR UPDATE
→ allocate seq
→ hash(previous_hash + event)
→ insert event
→ advance cursor
```

Checkpoint 不是一行 JSON 大包，而是：

```text
checkpoint
  ├─ checkpoint_component: task state
  ├─ checkpoint_component: workpad
  ├─ checkpoint_component: session boundary
  ├─ checkpoint_component: source/target manifest
  ├─ checkpoint_component: repository graph revision
  ├─ checkpoint_component: IR revision
  ├─ checkpoint_component: coverage snapshot
  └─ checkpoint_component: cost/ETA snapshot
```

只有所有组件已发布、Hash 匹配且状态可恢复时，`exec.seal_checkpoint()` 才能封存。

## 13. 外部副作用与 UNKNOWN_RESULT

Git Push、PR 创建、工单变更、部署、支付或数据库写入可能出现：请求已发送但响应丢失。

此时必须记录：

```text
side_effect_receipt.status = unknown_result
idempotency_key
provider_request_id
request_hash
reconciliation_strategy
```

系统先查询外部系统确认结果；禁止直接重试。未解决的关键 `UNKNOWN_RESULT` 会阻止 P05 完成。

## 14. 成本、收入和 ETA

分别记录：

- 每轮模型调用及缓存 Token；
- 每次 Tool 调用和后台/延迟任务；
- CPU、内存、GPU、存储、网络、Runner 时间；
- Budget Reservation；
- Cost Ledger；
- Revenue Ledger；
- Cache Savings；
- ETA Forecast。

ETA 至少包含：

```text
machine_wall_clock_p50/p90
hitl_wait_estimate
queue_wait_estimate
human_equivalent_effort
```

前端默认展示系统自主运行时间，不把人工人日混入机器 ETA。

## 15. P05 完成事务

`verify.complete_run_with_gate()` 必须在数据库事务中重新检查：

1. Gate Evaluation 属于当前 Run；
2. Revision 绑定完全一致；
3. Evidence Bundle 已 sealed；
4. Evidence 未撤销、未过期且 Artifact 可用；
5. Requirement/Capability Ledger 非空且达到阈值；
6. 无未结束 Task；
7. 无开放 Critical Semantic Gap/Risk；
8. 无未解决关键 Side Effect；
9. Run 仍是 Job 的 `current_run_id`。

通过后同一事务内：

```text
Run = completed
Job = completed (only current run)
release account slot
append completion event
insert outbox
seal archive/evidence reference
```

Agent 的自然语言 `Done` 不参与裁决。

## 16. 分区与保留

建议优先分区：

- `exec.run_event`、`exec.session_event`；
- Model/Tool Invocation；
- Usage/Cost/Revenue Ledger；
- Audit Event；
- 大规模 File/Symbol/Reference 表。

原则：

- 热数据按时间或 Tenant Hash 分区；
- Run 完成后生成 Archive Manifest；
- 过期细粒度事件先归档 CAS，再删除热分区；
- Evidence、财务和审计按法规保留；
- 删除租户时使用可证明的分阶段擦除，而不是一次巨大级联事务。

## 17. 推荐上线顺序

```text
DB-1A Durable Execution Core
→ DB-1B Commercial Operations
→ DB-2 Repository Intelligence
→ DB-3 Generation / Transformation / P05
→ DB-4 Learning / Benchmark / Deployment Operations
```

完整项目生成和跨库转换对外 GA 前，至少必须完成 DB-1A、DB-1B、DB-2、DB-3。
