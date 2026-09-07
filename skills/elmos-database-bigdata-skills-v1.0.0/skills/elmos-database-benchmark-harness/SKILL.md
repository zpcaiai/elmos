---
name: elmos-database-benchmark-harness
description: 用项目真实工作负载建立可复现的功能、性能、恢复和成本基准，而不是通用排行榜。
version: 1.0.0
group: database-intelligence
dependencies: ["elmos-workload-profiler", "elmos-database-capability-registry"]
triggers: ["候选差距小", "关键能力缺证据", "生产容量验证"]
outputs: ["benchmark-plan.json", "benchmark-results.json", "benchmark-report.md"]
---

# 数据库与数据引擎基准验证

## 目标

用项目真实工作负载建立可复现的功能、性能、恢复和成本基准，而不是通用排行榜。

## 适用触发条件

- 候选差距小
- 关键能力缺证据
- 生产容量验证

## 输入

- DataProfile
- 候选与版本
- 脱敏数据生成器
- SLO 和成本模型

## 执行流程

1. **BENCH-001** — 从真实查询、分布、热点、并发和增长模型生成 workload pack。
2. **BENCH-002** — 固定硬件、版本、配置、规模、预热、压缩和重复次数。
3. **BENCH-003** — 测量写入、点查、范围、连接、聚合、更新、删除、并发和混合负载。
4. **BENCH-004** — 记录 P50/P95/P99、吞吐、错误、资源、放大、恢复时间和单位成本。
5. **BENCH-005** — 注入节点、网络、磁盘、broker、checkpoint、元数据故障并验证语义。
6. **BENCH-006** — 检测缓存偏差、数据过小、索引/预聚合不等价；保留原始结果和置信区间。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `benchmark-plan.json`
- `benchmark-results.json`
- `benchmark-report.md`

## 验收标准

- 工作负载可重放且接近目标分布。
- 含尾延迟、资源、恢复和成本。
- 候选语义与配置等价。
- 环境和结果可审计。

## 失败、降级与恢复

环境不足时输出最小可行基准和未覆盖风险，不外推为生产结论。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **BENCH-007** — 输入和授权范围已固化为不可变快照。
- [ ] **BENCH-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **BENCH-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **BENCH-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **BENCH-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **BENCH-012** — 未验证能力未被标记为生产完成。
