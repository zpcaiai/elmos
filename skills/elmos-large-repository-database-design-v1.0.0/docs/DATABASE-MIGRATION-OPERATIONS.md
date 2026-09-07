# Elmos 数据库 Migration、发布与回滚操作指南

**目标：** 在 Elmos 长任务持续运行、多个服务并发部署、Evidence/账本不可变的情况下安全演进 PostgreSQL Schema。

---

## 1. 工具与版本

参考迁移采用 Flyway 风格命名：

```text
V001__...
V010__...
...
V090__...
```

可使用 Flyway、Liquibase 或内部 migrator，但必须满足：

- 单一迁移权威；
- migration history 表；
- checksum；
- 不允许修改已经在生产执行的 migration；
- migration Job 单实例；
- 失败可观察；
- 与 Release/Deployment/Gate 绑定。

推荐 PostgreSQL 16/17；CI 至少覆盖当前生产主版本和下一目标版本。

---

## 2. 迁移职责

| 组件 | 职责 |
|---|---|
| CI | 静态校验、临时数据库执行、升级/回滚兼容测试 |
| Release Pipeline | 生成镜像与 migration bundle，签名并记录 digest |
| Migration Job | 获取 advisory lock，执行迁移，写 `ops.migration_run` |
| Control API | 暴露 schema version；拒绝不兼容流量 |
| Deployment Gate | 检查 migration 成功与服务 health/version |
| DBA/Platform | 备份、容量、锁与复制延迟监控 |

应用启动时不得每个 Pod 都自动执行 DDL。

---

## 3. Expand / Migrate / Contract

### 3.1 Expand

只做向后兼容变更：

- 新表；
- nullable 新列；
- 有默认值但不立即 rewrite 的新列；
- 新索引 `CONCURRENTLY`；
- 新函数/视图；
- 双写能力。

### 3.2 Migrate

后台小批量 backfill：

- 有 checkpoint；
- 可暂停恢复；
- 按 tenant/revision/id 范围；
- 受限并发；
- 监控 WAL、锁和 replica lag；
- 每批幂等。

### 3.3 Contract

确认所有应用已停止读取/写入旧字段后：

- 增加 NOT NULL/constraint；
- 删除旧索引；
- 删除旧列/表；
- 删除兼容 trigger；
- 更新 contract version。

Contract 通常至少延迟一个或两个 Release，不与 Expand 同次执行。

---

## 4. 首次部署顺序

```text
1. 创建数据库与扩展许可
2. 执行 V001–V090
3. 创建应用数据库角色和 GRANT
4. 验证 RLS/FORCE RLS
5. 执行 invariant tests
6. 部署 Control Plane
7. 部署 Scheduler/Runtime/Router
8. 部署 Worker Controller/Workers
9. 运行 smoke run
10. P05 deployment gate
```

首次执行示例：

```bash
flyway \
  -url="$ELMOS_DATABASE_URL" \
  -user="$ELMOS_MIGRATOR_USER" \
  -password="$ELMOS_MIGRATOR_PASSWORD" \
  -locations="filesystem:database/migrations" \
  migrate
```

生产不得将密码写入命令历史；示例仅说明参数，实际使用 Secret injection。

---

## 5. Migration Advisory Lock

Migration Job 启动时获取稳定 advisory lock：

```sql
SELECT pg_advisory_lock(hashtextextended('elmos-schema-migration', 0));
```

完成或失败后释放。这样即使两个 Deployment Pipeline 同时启动，也只有一个执行 DDL。

同时在 `ops.migration_run` 记录：

- release_id；
- deployment_id；
- from/to version；
- migration digest；
- status；
- started/finished；
- applied versions；
- error artifact；
- operator/pipeline identity。

---

## 6. 锁风险控制

DDL 前必须评估：

- lock level；
- table size；
- rewrite；
- index build；
- FK validation；
- replica lag；
- active long transactions；
- autovacuum conflict。

### 6.1 生产 Session 参数

Migration Job 建议：

```sql
SET lock_timeout = '5s';
SET statement_timeout = '30min';
SET idle_in_transaction_session_timeout = '60s';
```

高风险语句单独设置，不能全局无限等待。

### 6.2 NOT NULL

大表安全路径：

```sql
ALTER TABLE t ADD CONSTRAINT t_col_not_null CHECK (col IS NOT NULL) NOT VALID;
ALTER TABLE t VALIDATE CONSTRAINT t_col_not_null;
ALTER TABLE t ALTER COLUMN col SET NOT NULL;
ALTER TABLE t DROP CONSTRAINT t_col_not_null;
```

### 6.3 Foreign Key

```sql
ALTER TABLE child
ADD CONSTRAINT child_parent_fk
FOREIGN KEY (...) REFERENCES parent(...) NOT VALID;

ALTER TABLE child VALIDATE CONSTRAINT child_parent_fk;
```

### 6.4 Index

大型生产表使用：

```sql
CREATE INDEX CONCURRENTLY ...;
```

注意 `CREATE INDEX CONCURRENTLY` 不能在普通事务块内；需放 repeatable/非事务 migration，并有失败索引清理策略。当前参考基础迁移用于新库，可在事务中创建普通索引；后续在线升级必须按表规模调整。

---

## 7. Backfill Worker

不要用一个 SQL 更新亿级行。推荐专用 Workflow：

```text
select next key range
→ claim range
→ update 1k–10k rows
→ commit
→ record cursor/checkpoint
→ sleep based on replica/WAL pressure
→ continue
```

记录：

- migration/backfill id；
- tenant/shard；
- cursor；
- rows scanned/updated/skipped/failed；
- rate；
- ETA；
- last error；
- pause reason。

Backfill 应可反复执行且结果一致。

---

## 8. 服务兼容性合同

每个服务 `/version` 返回：

```json
{
  "service": "elmos-control-api",
  "release": "1.1.0",
  "git_sha": "...",
  "image_digest": "sha256:...",
  "db_schema_min": 90,
  "db_schema_max": 110,
  "workflow_contract": "...",
  "event_contract": "..."
}
```

`/readyz` 必须检查当前 DB schema 是否位于服务支持区间。超出时返回 not ready，而不是带不兼容 Schema 提供服务。

---

## 9. 发布顺序

### 9.1 向后兼容发布

```text
备份/PITR 确认
→ Expand migration
→ Control API canary
→ Scheduler/Runtime canary
→ Worker canary
→ DB invariant tests
→ P02/P03/P05 benchmark
→ 部署 Gate
→ 全量
```

### 9.2 需要双写时

```text
Expand
→ 部署 dual-write app
→ 比较 old/new shadow reads
→ backfill
→ 切换 authoritative read
→ 观察
→ 停止旧写
→ Contract（后续发布）
```

---

## 10. Migration 与长任务

数据库升级时可能存在运行数小时的 Run。必须标注每个 migration 的运行兼容性：

| 类别 | 处理 |
|---|---|
| Compatible | 运行中 Run 无感继续 |
| New-attempt-only | 已运行 Attempt 继续，新 Attempt 用新结构 |
| Checkpoint-required | 先让活跃 Run 到安全 Checkpoint 再升级 |
| Drain-required | 停止新准入，等待/暂停活跃 Run |
| Breaking | 新版本并行环境 + 迁移演练，不直接原地升级 |

Session Event、Checkpoint、Semantic IR、Evidence Bundle 格式必须版本化。新服务不能静默读取无法完全解释的旧/未来格式。

---

## 11. 回滚原则

### 11.1 应用回滚优先

若 Expand migration 是向后兼容的：

- 回滚应用镜像；
- 保留新表/列；
- 不立即执行 destructive down migration。

### 11.2 数据回滚

只有在明确脚本和验证存在时执行。多数生产 Schema 回滚应通过 forward-fix，而非 DROP。

### 11.3 运行状态

回滚前：

- 暂停新准入；
- 形成 Checkpoint；
- 停止不兼容新 Attempt；
- 对账 Worker/Lease；
- 确认旧版本可读现存 Event/Checkpoint；
- 记录 deployment/release rollback。

### 11.4 Rule/Evidence

若新版本生成了错误 Evidence 或规则：

- 追加 evidence revocation；
- 使 Gate/Certification 失效；
- quarantine rule release；
- 重新运行受影响 benchmark；
- 不删除历史记录掩盖问题。

---

## 12. CI Migration Matrix

每个 PR 至少运行：

1. 空库 `V001→latest`；
2. 上一个 GA schema → latest；
3. 当前生产 schema snapshot → latest；
4. 重复 migrate 无变化；
5. checksum 验证；
6. invariant SQL；
7. RLS 双租户测试；
8. stored function concurrency tests；
9. app `/readyz` 对兼容/不兼容 schema；
10. backup restore 后 migrate；
11. PostgreSQL 当前主版本；
12. 下一目标主版本。

建议 CI 容器：

```text
postgres:16
postgres:17
```

用真实 PostgreSQL 执行，而不是仅 SQL parser。

---

## 13. P05 部署完成门

`ops.complete_deployment_with_gate` 只有在以下条件满足时通过：

- 所有 required deployment checks 为 pass；
- 每个 required release component 有最新 health snapshot；
- 实际 image digest 与 release component 一致；
- 必需 migration 已成功；
- Smoke Run/DB invariants/RLS/P05 benchmark 已通过；
- 无 blocked/failed/not_run check。

通过后原子：

- deployment → completed；
- deployment_gate → pass；
- 写 audit/outbox；
- 记录 release component 与 schema version。

Agent/CI 文本输出“部署成功”不能代替数据库 Gate。

---

## 14. Kubernetes Migration Job

建议：

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: elmos-db-migrate-<release>
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: elmos-migrator
      containers:
        - name: migrate
          image: <immutable-migration-image@sha256:digest>
          envFrom:
            - secretRef:
                name: elmos-db-migrator
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
```

要求：

- migration image 与应用 release 同源构建并签名；
- Secret 仅该 Job 可读；
- NetworkPolicy 仅允许 PostgreSQL；
- Job 日志脱敏；
- 完成后凭据撤销/轮换；
- Helm/Argo 不因 hook 被删而丢失 `ops.migration_run` 记录。

---

## 15. Preflight 查询

长事务：

```sql
SELECT pid, usename, application_name, state,
       now() - xact_start AS xact_age,
       left(query, 200) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

未授权 schema 版本：

```sql
SELECT installed_rank, version, description, success
FROM flyway_schema_history
ORDER BY installed_rank DESC
LIMIT 20;
```

复制延迟：

```sql
SELECT application_name, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;
```

阻塞锁：

```sql
SELECT blocked.pid AS blocked_pid,
       blocking.pid AS blocking_pid,
       blocked.query AS blocked_query,
       blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_locks blocked_locks ON blocked_locks.pid = blocked.pid AND NOT blocked_locks.granted
JOIN pg_locks blocking_locks
  ON blocking_locks.locktype = blocked_locks.locktype
 AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
 AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
 AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
 AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
 AND blocking_locks.granted
JOIN pg_stat_activity blocking ON blocking.pid = blocking_locks.pid;
```

---

## 16. 发布验收清单

- [ ] Migration 文件未修改既有版本；
- [ ] 新 Migration 有 checksum；
- [ ] 空库/升级路径均通过；
- [ ] 无未经评估的 table rewrite；
- [ ] lock_timeout/statement_timeout 已设置；
- [ ] 大索引采用在线策略；
- [ ] 大 FK/constraint 分离 validate；
- [ ] Backfill 可暂停、恢复、幂等；
- [ ] 服务 schema compatibility 已声明；
- [ ] 活跃 Run 的兼容类别已评估；
- [ ] Backup/PITR 已确认；
- [ ] RLS/invariant tests 通过；
- [ ] `/version` 显示目标 schema；
- [ ] `ops.migration_run` 成功；
- [ ] Deployment Gate 通过；
- [ ] 回滚/forward-fix 路径已演练。

## 13. CI/CD 集成入口

- `.github/workflows/database-ci.yml`：PostgreSQL 16/17 真实迁移矩阵；
- `deploy/migration-image/Dockerfile`：只读复制 versioned migration 的 OCI 镜像；
- `deploy/helm/elmos/templates/migrate-job.yaml`：pre-install/pre-upgrade Hook；
- `deploy/helm/elmos/templates/deployment-gate-job.yaml`：post-install/post-upgrade P05 Gate；
- `scripts/migrate-local.sh`：本地 Flyway + invariants；
- `scripts/validate_database_design.py`：DDL、FK、RLS、事务函数和运维查询静态合同。

Helm Hook 成功只说明 Job 退出码为 0。最终 Deployment 状态必须由 `ops.complete_deployment_with_gate()` 写入。
