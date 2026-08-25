# 将部署与数据库包合并到 Elmos 主仓库

## 1. 目标目录

建议把本包按原路径合并到 Elmos Monorepo，而不是复制到临时运维仓库：

```text
elmos/
├── apps/
├── workers/
├── packages/
├── database/
│   ├── migrations/
│   ├── queries/
│   ├── tests/
│   ├── schemas/
│   └── examples/
├── deploy/
│   ├── helm/elmos/
│   ├── local/
│   ├── environments/
│   └── migration-image/
├── docs/
├── scripts/
├── skills/
└── .github/workflows/
```

`database/` 应成为数据库合同的唯一来源。不要同时维护 `migrations/`、某个服务内部 migrations 和 Helm 内嵌 SQL 三套副本。

## 2. 推荐合并顺序

### PR-1：合同与静态验证

合并：

- `database/migrations/`
- `database/tests/`
- `database/queries/`
- `scripts/validate_database_design.py`
- `scripts/validate_bundle.py`
- `.github/workflows/database-ci.yml`

退出条件：PostgreSQL 16/17 空库迁移、Flyway validate、数据库不变量测试全部通过。

### PR-2：Control API 与领域写路径

实现并仅通过事务函数完成：

- Job 提交幂等；
- 账号 3 槽原子准入；
- Run 创建；
- Run/Session Event 追加；
- Task Claim/Renew/Finish；
- Checkpoint Seal；
- Side-effect Reservation；
- P05 完成事务。

应用角色不得直接更新高价值表来绕过状态机。

### PR-3：服务健康合同

所有部署服务实现：

```text
GET /livez
GET /readyz
GET /metrics
GET /version
```

并在 Helm、Compose、CI 和 P05 Deployment Gate 中使用同一合同。

### PR-4：应用镜像与迁移镜像

为每个物理服务提供：

- 多阶段 Dockerfile；
- 非 root runtime；
- SBOM；
- image digest；
- source SHA/provenance；
- `/version` 构建元数据；
- 数据库兼容范围。

迁移镜像只包含 versioned migration，不包含应用 Secret 或任意运维 shell。

### PR-5：Staging 发布与 P05 部署完成门

CI/CD 必须按以下顺序：

```text
validate contracts
→ test
→ build immutable images
→ scan/sign/SBOM
→ create release manifest
→ migrate
→ deploy canary
→ collect health/evidence
→ P05 deployment gate
→ mark deployment healthy
```

Helm release 成功不等于 Elmos Deployment 完成。只有 `ops.complete_deployment_with_gate()` 成功后，Control Plane 才对外标记为 `healthy`。

## 3. 合并时必须替换的占位符

- `registry.example.com/elmos`
- `CHANGE_ME_GIT_SHA`
- `CHANGE_ME_IMMUTABLE_SHA_OR_DIGEST`
- `CHANGE_ME_64_HEX_SHA256`
- OIDC、S3、Temporal、OTLP 地址；
- Secret 名称；
- 实际服务镜像名；
- 实际数据库 migration runner 命令。

生产流水线必须拒绝任何残留 `CHANGE_ME`、`latest` 或未解析 Secret 引用。

## 4. 数据库角色

建议至少分离：

| 角色 | 权限 |
|---|---|
| `elmos_migrator` | DDL、migration metadata；不处理用户请求 |
| `elmos_control_api` | 领域 API 所需表和高价值事务函数 |
| `elmos_scheduler` | Run/Task/Lease/Outbox 协调 |
| `elmos_worker` | 租户和 Run 范围内最小写权限 |
| `elmos_verifier` | Verify/Evidence 追加；不能直接完成 Run |
| `elmos_gate` | 调用 P05/Deployment Gate 事务函数 |
| `elmos_auditor` | 只读审计与 Evidence 导出 |
| `elmos_reconciler` | 恢复、Outbox/Inbox 和副作用重对账 |

每个连接事务必须设置 `app.tenant_id`、`app.actor_id`、`app.request_id`。平台级跨租户操作必须使用单独、短时、审计的角色。

## 5. Feature Flag 上线顺序

```text
DB-1 durable execution core
→ DB-2 repository intelligence
→ DB-3 generation/transformation + P05
→ DB-4 learning/benchmark/deployment operations
```

数据库可以先存在全量表，但应用写路径与 UI 必须按阶段开启。P07 在客户未授权时默认关闭。

## 6. 主仓库 CI 必须阻断的情况

- migration checksum 漂移；
- migration 命名或次序错误；
- destructive DDL；
- 新租户表缺少 `tenant_id` 或 FORCE RLS；
- 高价值函数仍可被 PUBLIC 执行；
- 运维查询引用不存在的列；
- Service 缺少四个健康/版本端点；
- Production values 使用 mutable tag；
- Release Manifest 未绑定 image digest、schema revision 和 gate policy；
- P05 Gate 证据缺失或 Revision 不一致。

## 7. 合并后第一条 Vertical Slice

推荐以一个 1,000–5,000 文件的中型仓库运行：

```text
submit Job
→ claim account slot
→ create Run
→ discover repository
→ create Task DAG
→ persist Session/Events
→ generate one target revision
→ run build/test
→ seal Evidence Bundle
→ P05 complete Run
→ release account slot
→ reconcile cost/ETA
```

该 Vertical Slice 必须能在任意 Worker 阶段被 kill，并从可信 Checkpoint 恢复，同时不重复外部副作用。
