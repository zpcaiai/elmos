# 持久化与 Artifact 模型

## 1. 原则

- PostgreSQL 保存可查询元数据、状态、索引和小型结构化摘要。
- 源码快照、IR 大块、日志、trace、测试结果、二进制、镜像和证据包存对象存储。
- 所有 artifact 内容寻址，数据库记录 URI、hash、size、schemaVersion。
- 状态事件 append-only；当前状态可由投影表加速。
- executor 提交必须验证 lease/fencing token。
- 每租户隔离，任务并发上限由控制面执行。

## 2. 核心实体

```text
modernization_job
repository_snapshot
execution_step
step_attempt
execution_checkpoint
artifact
evidence_node / evidence_edge
semantic_ir_chunk
endpoint_contract
transformation_unit
change_set
verification_run / observation / mismatch
repair_attempt
risk_item / unknown_semantic
gate_result / certification
cost_ledger / eta_estimate / cache_entry
```

## 3. Artifact 生命周期

```text
STAGED → VALIDATED → PUBLISHED → SUPERSEDED | RETAINED | DELETED
```

已被认证证据引用的 artifact 不得物理删除，只能按保留策略归档。

## 4. IR 分块

大型仓库 IR 按稳定边界分块：

- module；
- route cluster；
- view graph；
- state machine；
- side-effect sink；
- transformation unit。

每块有独立 hash，支持增量失效和并行。

## 5. Evidence Graph

PostgreSQL 只保存节点/边索引和摘要。证据正文可能是：

```text
git://repo@sha/path#Lx-Ly
artifact://...
trace://...
db-snapshot://...
decision://...
```

每个节点记录 tenant/repo/snapshot/environment/extractor/version/confidence。

## 6. 任务恢复

恢复算法：

1. 读取 job policy hash；
2. 验证 snapshot 和上游 artifact hash；
3. 找到最后一个 `COMMITTED` checkpoint；
4. 失效 policy/input/dependency hash 改变的子图；
5. 为待执行 step 发放新 lease/fencing；
6. 旧 attempt 即使返回，也因 fencing 失败不能发布。

## 7. 成本与 ETA

`cost_ledger` 按 step/attempt/model/tool 记录：

- input/output/cached token；
- CPU/GPU wall-clock；
- sandbox/container duration；
- storage bytes；
- network；
- external API；
- retry waste；
- cache savings。

`eta_estimate` 保存 P50/P80/P95 及模型版本，运行中滚动更新。

## 8. SQL

完整 DDL 见 `database/postgres-schema.sql`。
