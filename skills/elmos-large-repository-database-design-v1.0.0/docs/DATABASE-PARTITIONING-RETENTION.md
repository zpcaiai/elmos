# Elmos PostgreSQL 分区、容量与数据保留策略

**目标：** 在百万文件、数千万符号、长时间 Session 和高频事件条件下，维持准入、任务 Claim、P05 Gate 和用户查询的稳定延迟。

---

## 1. 核心原则

1. **事务热点表保持小而可索引。** 账号槽、Run、Task、Lease、Gate 不与大日志混在一个访问路径。
2. **大正文外置 CAS。** PostgreSQL 保存引用、哈希、状态和摘要，不保存完整源码、AST/IR、Build stdout、Video 或模型长输出。
3. **事件按时间治理，实体按 Revision 治理。** Event/Ledger/Audit 适合时间分区和归档；Repository/Symbol/Capability 适合按 Revision 删除或归档。
4. **删除先断引用，后归档，最后物理回收。** 不能边跑任务边直接删除底层 CAS 对象。
5. **P05 Evidence、财务账本和审计保留级别高于普通临时运行数据。**

---

## 2. 表规模分级

| 级别 | 典型表 | 单 Run 预估 | 策略 |
|---|---|---:|---|
| T0 热事务 | `account_task_slot`, `run`, `task`, `execution_lease` | 10²–10⁵ 行 | 不按时间分区；强索引；频繁 VACUUM |
| T1 高频事件 | `run_event`, `session_event`, `outbox_event`, `audit_event` | 10⁴–10⁷ 行 | Hash + 时间生命周期；归档冷分区 |
| T2 仓库索引 | `repository_file`, `symbol_record`, `capability` | 10⁴–10⁸ 行 | 先 Hash；超大租户可独立库/子分区 |
| T3 生成/验证明细 | `generated_file`, `verification_result`, `behavior_observation` | 10³–10⁷ 行 | 按 Run/Revision 批量写和批量归档 |
| T4 财务/证据 | `cost_ledger`, `revenue_ledger`, `evidence_item`, `gate_evaluation` | 10²–10⁶ 行 | Append-only；长期保留；不可就地修改 |
| T5 缓存/临时 | `cache_access`, `staged_object`, `progress_snapshot` | 波动 | TTL/GC；不影响权威结果 |

---

## 3. 当前参考分区

迁移脚本为以下高写入表创建 16 个 Hash 分区：

- `exec.run_event`；
- `exec.session_event`；
- `analysis.repository_file`；
- `analysis.symbol_record`；
- `generation.generated_file`；
- `integration.outbox_event`；
- `audit.audit_event`。

Hash key 选择稳定的 tenant/run/revision 关联列，目标是：

- 降低单索引争用；
- 使同一 Run/Revision 查询尽量命中有限分区；
- 为后续二级时间分区或分库提供迁移边界。

### 3.1 为什么首版不同时做 Hash × Month

多层分区会增加：

- DDL 数量；
- Partition maintenance；
- ORM/迁移复杂度；
- 查询计划不确定性；
- 小规模部署运维成本。

首版先用 16 Hash，待单表达到阈值后再把每个 Hash 分区改为月分区或迁移到事件专库。

---

## 4. 何时需要二级时间分区

满足任一条件时评估：

- 单个父表超过 5–10 亿行；
- 单分区超过 100–200 GB；
- Autovacuum 无法在业务窗口内追上；
- 删除历史数据造成长时间 bloat；
- 时间范围查询占主导；
- 备份/恢复需要按时间切片；
- 归档需要 detach partition。

推荐：

```text
Hash 16
  └── Monthly RANGE(created_at)
```

对 `run_event/session_event/audit_event/outbox_event` 使用月分区；对高吞吐商业环境可按周。

---

## 5. Repository File 与 Symbol 的策略

### 5.1 Repository File

`analysis.repository_file` 只保存：

- relative path；
- language/type；
- size；
- content hash；
- module/build target；
- generated/vendor/binary 标记；
- CAS artifact 引用；
- scan status 与摘要。

不保存完整文件正文。

### 5.2 Symbol Record

`analysis.symbol_record` 保存可查询的语义索引，不保存完整 AST。对超大仓库：

- 使用 Copy/批量写；
- 每 5k–20k 行一个 batch；
- 禁止逐 Symbol 事务；
- 对 `revision_id + qualified_name`、`file_id + start_line` 建索引；
- 大字段（signature/doc summary）限制长度；
- 完整 symbol graph 存 `graph_shard` 对象。

### 5.3 超大规模降级

当 Symbol 超过 1,000 万：

```text
Level 0：模块/包/公开 API 全量索引
Level 1：业务代码全量 Symbol
Level 2：vendor/generated 仅摘要
Level 3：完整 Graph/IR 仅 CAS Shard
```

数据库记录降级策略和发现警告，P05 不得把降级误报为 100% 语义覆盖。

---

## 6. 仓库规模分层

| 规模 | 文件数 | 代码量 | 建议数据库模式 |
|---|---:|---:|---|
| S | < 20k | < 2M LOC | 单 PostgreSQL；普通索引 |
| M | 20k–100k | 2M–10M LOC | 批量写；16 Hash；独立 Worker pool |
| L | 100k–500k | 10M–50M LOC | 专用分析数据库资源；Graph/IR Shard；只读副本 |
| XL | > 500k | > 50M LOC | Tenant/Project 分片；分析专库；分级索引；独立 CAS 与队列 |

仓库大小不是唯一因子；构建目标数、语言数、Symbol 密度、生成文件比例、历史 Revision 数也影响容量。

---

## 7. 写入模式

### 7.1 Bulk First

适合批量写入的表：

- repository_file；
- symbol_record；
- capability；
- generated_file；
- verification_case/result；
- behavior_observation；
- usage ledger 聚合。

推荐：

1. Worker 先产生 batch manifest；
2. 写到临时 staging 表或 `COPY`；
3. 在短事务中 merge/upsert；
4. 写 batch-completed event；
5. Seal 对应 checkpoint component。

### 7.2 禁止超大事务

单事务建议上限：

- 5k–20k 行；或
- 16–64 MB WAL；或
- 2–10 秒；

超过任一阈值即切批。生产值应根据 IOPS/WAL/复制延迟 benchmark 调整。

### 7.3 COPY 与 Upsert

- 新 Revision 的 immutable 索引优先 `COPY`；
- 重复扫描或增量扫描用 staging + `INSERT ... ON CONFLICT`；
- 不对巨大目标表逐行 upsert；
- 使用 batch id 和 source revision 保证幂等。

---

## 8. 索引设计

### 8.1 热路径

必须重点优化：

```text
account → available slot
run → dashboard/current status
run → ready tasks
attempt → active lease
run → next event sequence
session → next event sequence
run → latest sealed checkpoint
run → completion readiness
run → model/tool/cost totals
run → unknown side effects
```

### 8.2 Partial Index

适合：

- active leases；
- queued/running tasks；
- unpublished outbox；
- unknown_result side effects；
- open critical semantic gaps；
- non-terminal runs；
- available artifacts；
- current/latest revisions。

### 8.3 JSONB

JSONB 只用于：

- provider-specific metadata；
-兼容扩展字段；
- 稀疏结果摘要；
- 非核心查询参数。

若某字段进入高频过滤、排序、唯一约束或 FK，应提升为普通列。不要把核心状态机藏进 JSONB。

### 8.4 GIN 使用边界

GIN 索引写放大明显。仅对稳定且有真实查询需求的 JSONB/数组字段建立；先用 `pg_stat_statements` 和慢查询证据证明必要。

---

## 9. Autovacuum 与 Fillfactor

### 9.1 高频更新表

以下表有较多状态更新：

- `exec.run`；
- `exec.task`；
- `exec.task_attempt`；
- `exec.execution_lease`；
- `exec.run_progress_snapshot`；
- `core.account_task_slot`；
- `integration.outbox_event`。

建议：

```text
fillfactor 70–90
较低 autovacuum_vacuum_scale_factor
较低 autovacuum_analyze_scale_factor
提高 autovacuum_vacuum_cost_limit
```

具体参数必须在 Staging 用真实工作负载验证，不在通用迁移中硬编码集群级参数。

### 9.2 Append-only 表

Event/Ledger/Audit 主要 INSERT，重点是：

- analyze；
- index bloat；
- partition rotate；
- WAL/replication；
- 冷分区压缩/归档。

---

## 10. 数据保留等级

定义：

| 等级 | 意义 | 默认 |
|---|---|---|
| R0 | 瞬态/可重建 | 1–7 天 |
| R1 | 活跃运行支持 | 30 天 |
| R2 | 产品与排障 | 90–180 天 |
| R3 | 商业/证据 | 1–3 年 |
| R4 | 合规/财务/审计 | 依法规，常见 5–10 年 |

### 10.1 建议映射

| 数据 | 等级 | 说明 |
|---|---|---|
| staged objects、临时 workspace | R0 | 未被引用可快速 GC |
| cache access、详细 progress | R0/R1 | 可聚合后删除 |
|普通失败 build logs | R1/R2 | 先对象归档 |
| Run/Task/Attempt 元数据 | R2/R3 | 支持客户审计与问题复现 |
| Session Event | R2/R3 | 受客户数据策略控制 |
| Source/Target Artifact | R2/R3 | 企业私有部署可由客户决定 |
| Evidence Bundle/Gate/Certification | R3/R4 | 不得随普通 Run TTL 删除 |
| Cost/Revenue/Audit | R4 | 账务与合规 |
| Learning corpus | 授权决定 | 必须有 data_authorization |

---

## 11. 归档流程

```text
eligible
→ mark archive_pending
→ build run archive manifest
→ copy artifacts/events to cold CAS
→ verify digest and object lock
→ mark archived
→ detach/delete hot rows by retention policy
→ preserve tombstone/index
```

### 11.1 Run Archive

`artifact.run_archive` 应包含：

- Run metadata；
- event ranges；
- session ranges；
- task/attempt summary；
- artifact/evidence manifest；
- financial summary；
- policy/revision fingerprints；
- archive digest；
- retention class。

### 11.2 删除顺序

1. 证明 Run 不再活跃；
2. P05/财务/法律保留检查；
3. Learning authorization 检查；
4. Seal archive manifest；
5. 删除可重建明细；
6. 删除数据库引用；
7. CAS 引用计数归零后才 GC；
8. 写 audit event。

---

## 12. CAS 生命周期

### 12.1 引用状态

对象不能只靠 bucket lifecycle 直接删除。需要从数据库计算：

```text
active reference
archive reference
legal hold
learning authorization
pending upload
quarantine
```

### 12.2 Orphan GC

`staged_object` 超过 TTL 且没有 Artifact：

- 确认无活动上传；
- 删除临时对象；
- 标记 GC；
- 记录统计。

CAS 中存在但数据库无记录的对象进入 quarantine，不立即删除。

---

## 13. Event 归档与可查询性

热库保留最近 30–90 天完整 Event；更老 Event 可：

- 保留冷分区只读；
- 导出 Parquet 到对象存储；
- 建 ClickHouse/湖仓分析副本；
- 数据库仅留 event range、digest、archive URI。

权威恢复所需的当前活跃 Session/Run Event 必须留在 PostgreSQL 或可在 RTO 内回载。

---

## 14. Read Replica 与分析负载

以下查询优先走只读副本/分析仓：

- 跨租户运营报表；
- 历史成本趋势；
- 大范围 Event 分析；
- Benchmark 汇总；
- 规则成功率；
- 长期模型表现；
- 大规模符号搜索（如另有专门索引服务）。

不能走副本的强一致操作：

- Slot Claim/Renew/Release；
- Task Claim/Finish；
- Gate 完成；
- Budget reservation；
- Side-effect reservation；
- Outbox/InBox 提交；
- 最新 Evidence 绑定。

---

## 15. 分库与租户隔离升级路径

### Level 1：共享库、共享 Schema、RLS

适合早期多租户。

### Level 2：共享控制库 + 分析专库

把 repository_file/symbol/graph/IR 索引移到分析数据库，核心 Run/Task/Gate 留控制库。

### Level 3：Tenant/Region Shard

路由键：

```text
tenant_home_region + tenant_shard
```

跨 shard 只通过 API/Event，不建立跨数据库 FK。

### Level 4：客户 VPC Data Plane

控制面只保存：

- Job/Run/Policy/Cost/Evidence 摘要；
- 客户侧 Worker/Artifact 的 opaque references；

源码、Workspace、详细 IR/Evidence 留客户环境。

---

## 16. 容量估算公式

### 16.1 文件索引

```text
repository_file_bytes
≈ file_count × (row + indexes)
```

初步可按每行 0.5–1.5 KB 估算，具体取决于 path、metadata 和索引。

### 16.2 Symbol

```text
symbol_bytes
≈ symbol_count × 0.8–2.5 KB
```

千万 Symbol 可能需要 8–25 GB 数据加相近或更高索引空间。

### 16.3 Event

```text
event_bytes/day
≈ runs/day × events/run × average_event_row
```

Payload 只保存摘要与引用时，平均 0.5–4 KB；禁止把完整 Tool 输出放 payload。

### 16.4 WAL

保守估算：

```text
WAL ≈ logical write volume × 1.5–4
```

大量索引、full-page writes、replication 和 upsert 会放大。容量规划必须测真实 WAL。

---

## 17. 告警阈值

- 数据盘 > 70% warning，> 85% critical；
- WAL/replication slot > 30 分钟滞后；
- Autovacuum oldest xid 接近风险阈值；
- active lease 表 bloat > 30%；
- outbox oldest unpublished > 60 秒；
- event sequence gap > 0；
- orphan staged object 超过基线；
- hot partition 超过目标大小；
- query p95 超过 SLO；
- connection pool 等待 > 1 秒；
- checkpoint seal failure rate 上升；
- archive backlog > 24 小时。

---

## 18. 生产维护任务

每日：

- 过期 Lease/Slot reconciliation；
- staged-object GC；
- outbox/inbox backlog；
- unknown side effects；
- replication/WAL；
- backup verification。

每周：

- bloat/top tables；
- missing/unused indexes；
- slow queries；
- partition size；
- archive backlog；
- CAS orphan report。

每月：

- 创建未来分区；
- 归档过期分区；
- 恢复演练；
- retention/legal hold 审计；
- 容量预测；
- RLS 隔离测试。

---

## 19. 禁止事项

- 不在 PostgreSQL 保存完整 Git 仓库；
- 不将完整 AST/Graph/IR 塞入一个 JSONB 行；
- 不把 stdout/stderr 无上限保存为 TEXT；
- 不用 Redis 作为唯一 Run/Task/Lease 状态；
- 不按 `DELETE WHERE created_at < ...` 直接删除十亿级 Event；
- 不在活动 Revision 上逐行 UPDATE 数千万 Symbol；
- 不让 BI 查询打到主库强一致热路径；
- 不依据对象存储 lifecycle 绕过数据库引用和 legal hold；
- 不把未知语义降级隐藏起来以降低数据量。

---

## 20. 验收指标

| 指标 | 初始目标 |
|---|---:|
| Slot Claim p95 | < 100 ms |
| Task Claim p95 | < 200 ms |
| Event Append p95 | < 100 ms |
| Dashboard p95 | < 500 ms |
| P05 completion transaction p95 | < 2 s |
| Outbox publish lag p95 | < 5 s |
| Replica lag p95 | < 10 s |
| Sealed checkpoint lookup p95 | < 200 ms |
| Archive verification success | 100% |
| Event sequence/hash corruption | 0 |

这些是研发目标，必须用真实项目和部署规格校准。
