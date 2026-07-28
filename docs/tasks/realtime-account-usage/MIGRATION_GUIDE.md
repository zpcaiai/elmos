# 实时账户用量迁移与发布指南

## 1. 当前变更

本任务没有执行数据库 DDL，也没有修改已有 `usage_events`、`usage_ledger_entries`
或订阅表。受控本地 Runner 通过租户目录中的追加式 JSONL 账本提供真实运行读数：

```text
<meter-root>/tenants/<tenant-id>/usage/ledger.jsonl
```

生产 PostgreSQL/Neon 适配器仍为 `NOT_CONFIGURED`，不得以本地文件实现替代生产持久化证明。

## 2. 运行配置

可使用独立计量配置：

```text
ELMOS_USAGE_METER_ENABLED=true
ELMOS_USAGE_METER_ROOT=/absolute/approved/root
ELMOS_USAGE_METER_TENANT_ID=<authenticated-tenant>
ELMOS_USAGE_METER_ACTOR_ID=<authenticated-actor>
ELMOS_USAGE_METER_AUTH_TOKEN=<short-lived-secret>
ELMOS_USAGE_METER_AUTH_TOKEN_EXPIRES_AT=<canonical-UTC-ISO-8601>
ELMOS_USAGE_PLAN_ID=elmos-pro-monthly
ELMOS_USAGE_PERIOD_START=<canonical-UTC-ISO-8601>
ELMOS_USAGE_PERIOD_END=<canonical-UTC-ISO-8601>
```

本地 Runner 已配置时，可复用对应的 `ELMOS_LOCAL_RUNNER_*` 身份、根目录和令牌；
月度套餐在该模式下可自动使用当前 UTC 自然月。生产模式必须提供明确套餐和周期。

## 3. 账本导入

每行必须符合 `usage-ledger-event-v1.schema.json`：

1. 为每个提供方确认的 Token 或平台 Credit 事实生成唯一 `eventId` 和 `idempotencyKey`。
2. 仅把来源已确认且完成对账的事件标记为 `RECONCILED`。
3. 未确认结果标记为 `PENDING`，不得写成零数量。
4. 提供方拒绝的事件标记为 `REJECTED`，不得删除原事件。
5. 不得原地修改已写入行；纠正协议需要独立版本化事件，当前尚未实现并保持 `NOT_CONFIGURED`。

## 4. 发布顺序

1. 验证两份 JSON Schema 可解析。
2. 运行 Web TypeScript 与 Next.js 生产构建。
3. 运行 `usage-meter-ui.spec.ts` 的 API、身份隔离和实时刷新旅程。
4. 在受控环境配置短期凭证、套餐和周期。
5. 先接入测试账本，确认 `CURRENT`、`PARTIAL`、401、403、503 和过期凭证路径。
6. 生产切换前实现并验证 PostgreSQL/Neon 读模型、RLS、身份提供商和事件生产者。

## 5. 回退

UI 回退只需移除套餐页的 `UsageDashboard` 入口和 `/api/usage/current` 路由；
追加式账本不得删除或改写。回退后保留账本和契约，以便审计与重新发布。

## 6. 未完成外部门槛

- 生产身份与订阅绑定：`NOT_CONFIGURED`
- Neon/PostgreSQL 权威聚合：`NOT_CONFIGURED`
- 提供方 Token receipt 对账：`NOT_RUN`
- 生产负载、断线重连和多实例一致性：`NOT_RUN`
- 财务/计费认证：`NOT_CERTIFIED`
