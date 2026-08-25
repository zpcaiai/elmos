# Elmos 大型仓库运行数据库参考实现

本目录提供 Elmos 在执行大型仓库完整项目生成、跨语言/框架/数据库转换、验证、自动修复、P05 完成与部署时的 PostgreSQL 参考模型。

## 入口

- `EXECUTIVE-SUMMARY.md`：核心表、状态、事务和上线顺序的决策摘要；
- `DB-1-MINIMUM-TABLE-SET.md`：首发最小强一致表集；
- `TABLE-CATALOG.md`：全量 136 张父表目录。

## 目录

```text
database/
├── migrations/          # V001–V090，136 张父表、事务函数、RLS 和读模型
├── queries/             # 运维、排障和容量查询
├── tests/               # 部署后数据库不变量检查
├── roles/               # FORCE RLS 下的 NOLOGIN function owner 与最小 EXECUTE Grant
├── mermaid/             # 核心 ERD 与运行时数据流
└── TABLE-CATALOG.md      # 全部父表职责、阶段、量级和保留等级
```

## 数据边界

```text
PostgreSQL
  Job/Run/Task/Attempt/Lease
  Event/Checkpoint/Artifact metadata
  Capability/Coverage/Evidence/Gate
  Usage/Cost/Revenue/ETA
  Outbox/Side effect/Audit

Temporal
  durable workflow / timer / retry / pause-resume

S3/MinIO CAS
  source repository / code body / AST / graph / IR
  build logs / model long output / patch / evidence media

Redis
  hot cache / rate limit / transient coordination only
```

Redis 和 Temporal 都不是任务准入、财务或 P05 完成的最终权威。

## Migration 顺序

| 文件 | 内容 |
|---|---|
| V001 | Extension、Schema、公共 helper |
| V010 | Tenant、Account、Project、Job、幂等和 3 槽准入 |
| V020 | Run、DAG、Attempt、Lease/Fence、Event、Session、Checkpoint |
| V030 | CAS Artifact、Manifest、Staging、Archive |
| V040 | Repository File/Symbol/Graph/Semantic IR/Capability |
| V045 | Requirement、Architecture、Generation、Transformation |
| V050 | Verification、Coverage、Evidence、P05 Gate、Repair |
| V060 | Model/Tool、Usage/Cost/Revenue、ETA、Cache |
| V070 | Outbox/Inbox、Side Effect、Learning、Benchmark、Deployment、Audit |
| V080 | Cross-link FK、RLS、security-invoker read models |
| V090 | 原子 Claim/Renew/Finish、Event Append、Checkpoint、P05/Deployment Gate |

## 执行

### Flyway

```bash
flyway \
  -url="$ELMOS_DATABASE_URL" \
  -locations="filesystem:database/migrations" \
  migrate
```

### psql 开发验证

```bash
for file in database/migrations/V*.sql; do
  psql "$ELMOS_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
done

psql "$ELMOS_DATABASE_URL" \
  -v ON_ERROR_STOP=1 \
  -f database/tests/invariants.sql
```

## 静态校验

```bash
python3 scripts/validate_database_design.py
```

静态校验会验证：

- migration 次序与事务边界；
- 无破坏性 DDL；
- FK 目标存在且引用 PK/UNIQUE；
- 13 个 Schema 和关键表；
- 所有租户表含 tenant_id；
- RLS/FORCE RLS；
- 3 槽与 fencing；
- append-only Event/Evidence/Ledger；
- P05 exact revision/evidence/side-effect gate；
- machine ETA、HITL wait 和 human-equivalent 分离；
- 禁止在数据库保存源码/AST/模型长输出/stdout 正文。

静态校验不能替代真实 PostgreSQL 执行。CI 必须在 PostgreSQL 16/17 上执行所有 migration 和 `database/tests/invariants.sql`。

## 分阶段上线

```text
DB-1 Durable Execution Core
  core + exec + artifact + integration + metering core + audit

DB-2 Repository Intelligence
  analysis + cache

DB-3 Generation/Transformation/P05
  generation + transform + verify

DB-4 Learning/Benchmark/Deployment Operations
  learning + ops + complete metering
```

完整项目生成和跨库转换对外 GA 前必须至少完成 DB-1、DB-2、DB-3。

## 生产约束

1. 应用不能直接将 Run 更新为 completed；只允许调用 `verify.complete_run_with_gate`。
2. 部署不能直接标记 completed；只允许调用 `ops.complete_deployment_with_gate`。
3. Worker 的所有权威写入必须携带当前 lease generation/fencing。
4. 每个账号最多 3 个槽，通过数据库行锁原子 Claim。
5. 外部副作用超时进入 `unknown_result`，先 reconciliation，禁止盲目重复。
6. Event、Evidence、Ledger、Audit 只追加；修正用新记录或 revocation/reversal。
7. 任何模型可见事实必须可由 Session Event 重建。
8. 任何大正文必须进入 CAS，仅在数据库保存 Artifact 引用。

## 参考文档

- `docs/DATABASE-DESIGN-LARGE-REPOSITORY-RUNS.md`
- `docs/DATABASE-TRANSACTION-AND-RECOVERY.md`
- `docs/DATABASE-PARTITIONING-RETENTION.md`
- `docs/DATABASE-SECURITY-RLS.md`
- `docs/DATABASE-MIGRATION-OPERATIONS.md`
- `database/TABLE-CATALOG.md`
- `database/DB-1-MINIMUM-TABLE-SET.md`：首发约 34 张强一致核心表与后续扩展边界。

## Read Model 与示例

- `schemas/large-run-read-model.schema.json`：面向 Control API/UI 的大型 Run 聚合读模型合同；
- `examples/large-run-read-model.example.json`：184k 文件、27k Capability 的示例；
- `queries/operator_queries.sql`：30 组运维/重对账查询；
- `tests/invariants.sql`：迁移后与部署后的 23 组不变量。

聚合 Read Model 不是新的事实源。它由规范化表和 security-invoker views 投影产生，不应被客户端回写。

## 完成权威

`verify.complete_run_with_gate()` 会重新计算 Coverage、检查 Evidence、新旧 Revision、未完成 Task、关键 Gap 和外部副作用，并只在当前 Run 仍为 Job 的 `current_run_id` 时关闭 Job。应用不得用普通 `UPDATE exec.run SET status='completed'` 替代该事务。
