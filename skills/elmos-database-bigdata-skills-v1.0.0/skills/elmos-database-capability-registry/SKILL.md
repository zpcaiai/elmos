---
name: elmos-database-capability-registry
description: 维护关系型、分布式 SQL、NoSQL、搜索、图、时序、向量、OLAP、湖仓、消息和查询引擎的能力目录。
version: 1.0.0
group: database-intelligence
dependencies: []
triggers: ["比较数据库或数据技术", "新增技术适配器", "能力或版本变化"]
outputs: ["database-capabilities.json", "technology-adapters.json", "evidence-index.json"]
---

# 数据库与数据技术能力注册表

## 目标

维护关系型、分布式 SQL、NoSQL、搜索、图、时序、向量、OLAP、湖仓、消息和查询引擎的能力目录。

## 适用触发条件

- 比较数据库或数据技术
- 新增技术适配器
- 能力或版本变化

## 输入

- 官方文档
- 内部基准
- 部署与许可证策略
- Elmos 适配器

## 执行流程

1. **REG-001** — 按 technology_kind、storage_model、workload_role、deployment_model 建立规范条目。
2. **REG-002** — 记录事务、一致性、索引、分区、扩缩容、备份、CDC、查询、生态和治理能力。
3. **REG-003** — 区分声明能力、已实现适配器、已验证版本和仅规划支持。
4. **REG-004** — 为能力记录官方证据、抓取日期、版本范围、置信度和过期时间。
5. **REG-005** — 记录许可证、托管/自建、区域、国产化、离线部署、运维复杂度和锁定风险。
6. **REG-006** — 支持离线快照、可插拔 provider、版本绑定和完整性/过期检查。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `database-capabilities.json`
- `technology-adapters.json`
- `evidence-index.json`

## 验收标准

- 候选有角色、能力、限制、证据和适配器状态。
- 未验证能力不进入强制推荐。
- 注册表可离线快照和确定性重放。
- 通过 catalog 校验。

## 失败、降级与恢复

证据过期或冲突时降低置信度并要求基准，不用模型记忆替代注册表。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **REG-007** — 输入和授权范围已固化为不可变快照。
- [ ] **REG-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **REG-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **REG-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **REG-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **REG-012** — 未验证能力未被标记为生产完成。
