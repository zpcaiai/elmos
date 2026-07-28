# 实时账户用量架构

本任务已并入完整自助订阅与计量实现。当前架构、信任边界和数据流见
[自助计费架构](../self-service-billing/ARCHITECTURE.md)。

旧的本地 JSONL 计量只允许在 `ELMOS_LOCAL_RUNNER_ENABLED=true` 的受控开发模式使用；
生产路径使用认证 BFF、Commercial API 和 PostgreSQL 权威计量。
