# 实时账户用量数据库设计

## 1. 当前持久化决策

本任务不新增数据库表。仓库已有：

- `usage_events`
- `usage_ledger_entries`
- `model_usage_records`
- `quota_allocations`
- `subscriptions`
- `subscription_items`
- `entitlement_limits`
- `entitlement_consumptions`

这些表当前使用通用 `payload jsonb`，尚未提供本功能所需的生产认证读模型、类型化计量列、
周期约束、RLS 和对账查询。因此，本次实现不会把这些通用表误报为已完成的生产计量数据库。

## 2. 本地逻辑模型

| 字段 | 类型 | 约束 |
|---|---|---|
| `eventId` | string | 全局唯一、不可复用 |
| `idempotencyKey` | string | 同租户内唯一；相同键只允许完全相同事件 |
| `tenantId` | string | 必须匹配认证租户和目录边界 |
| `actorId` | string | 事件生产者/用户身份 |
| `planId` | string | 必须匹配当前额度周期套餐 |
| `meterId` | enum | `model-token-v1` 或 `platform-credit-v1` |
| `quantity` | positive integer | 精确数量，不允许浮点或负数 |
| `occurredAt` | timestamptz | 决定额度周期归属 |
| `recordedAt` | timestamptz | 决定事件水位 |
| `reconciliationStatus` | enum | `RECONCILED`、`PENDING`、`REJECTED` |

快照是可重建读模型，不是新的使用事实。它由当前周期事件、套餐版本和周期边界计算，
并通过 SHA-256 `snapshotVersion` 绑定源内容与聚合上下文。

## 3. 生产目标模型

生产 PostgreSQL 适配器应在独立 Flyway 任务中实现以下类型化、追加式结构：

```text
usage_meter_events
├── usage_event_id
├── tenant_id
├── organization_id
├── actor_id
├── plan_id
├── meter_version
├── quantity_decimal
├── occurred_at
├── recorded_at
├── reconciliation_status
├── idempotency_key
├── provider_receipt_ref
└── integrity_hash
```

必须同时具备：

- Tenant/Organization 外键和 PostgreSQL RLS；
- `(tenant_id, idempotency_key)` 唯一约束；
- 事件时间与记录时间索引；
- 精确 decimal/integer 数量；
- 不允许 UPDATE/DELETE 历史事实的数据库权限；
- 纠正事件到原事件的不可变链；
- provider receipt、outbox、审计和对账状态；
- 按租户、套餐、周期和 meter version 的聚合索引或可重建物化读模型。

## 4. 查询语义

权威已用量仅聚合：

```text
tenant = authenticated tenant
AND plan = active plan
AND occurred_at >= period_start
AND occurred_at < period_end
AND reconciliation_status = RECONCILED
```

`PENDING` 数量单独返回并使快照成为 `PARTIAL`；缺失数据源返回 `NOT_CONFIGURED`，
不得使用 `COALESCE(..., 0)` 把未知数据转为零。

## 5. 数据库迁移状态

| 项目 | 状态 |
|---|---|
| 本地逻辑契约 | `IMPLEMENTED` |
| 新 Flyway DDL | `NOT_REQUIRED_FOR_LOCAL_RUNTIME` |
| Neon 应用 | `NOT_RUN` |
| RLS 验证 | `NOT_RUN` |
| 生产数据回填与对账 | `NOT_RUN` |
