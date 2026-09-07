# 实时账户用量数据库设计

当前权威设计见[自助计费数据库设计](../self-service-billing/DATABASE_DESIGN.md)。

实时快照来自 V49 扩展后的 `subscriptions`、`quota_allocations`、`usage_reservations`、
`usage_events` 和 `usage_ledger_entries`，不再把本地 JSONL 描述为生产数据库。
Neon 精确项目/分支/数据库迁移仍为 `NOT_RUN`。
