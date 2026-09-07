---
name: elmos-federated-query-data-fabric
description: 为异构数据源生成联邦查询、元数据驱动集成、策略下推和自助访问。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-bigdata-pattern-selector", "elmos-polyglot-persistence-planner", "elmos-database-capability-registry"]
triggers: ["数据不能集中", "跨源即席", "Data Fabric 或迁移过渡"]
outputs: ["federation-topology.md", "connector-catalog.json", "pushdown-policy.json", "fabric-services.md"]
---

# 联邦查询、数据虚拟化与 Data Fabric 覆盖层

## 目标

为异构数据源生成联邦查询、元数据驱动集成、策略下推和自助访问。

## 适用触发条件

- 数据不能集中
- 跨源即席
- Data Fabric 或迁移过渡

## 输入

- 数据源与所有权
- 查询需求
- 网络/驻留
- 元数据平台

## 执行流程

1. **FED-001** — 识别适合虚拟访问与必须物化的数据，避免把联邦查询当无限性能层。
2. **FED-002** — 选择 Trino/等价引擎并验证谓词、聚合、join、limit 下推和写能力。
3. **FED-003** — 设计 catalog、namespace、身份传递、行列权限、masking 和跨域审计。
4. **FED-004** — 建立缓存、物化、结果复用和异步导出，同时标明新鲜度。
5. **FED-005** — 估算跨源 join 的数据移动、网络、源端负载、失败和成本。
6. **FED-006** — 以 metadata/lineage/policy/discovery/quality/automation 构建 Data Fabric 覆盖层。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `federation-topology.md`
- `connector-catalog.json`
- `pushdown-policy.json`
- `fabric-services.md`

## 验收标准

- connector 下推与能力已验证。
- 跨源查询不绕过所有权/租户策略。
- 成本/新鲜度/源负载可见。
- Fabric 与存储解耦。

## 失败、降级与恢复

关键查询无法下推时生成物化或 CDC，不让源库承担不可控扫描。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **FED-007** — 输入和授权范围已固化为不可变快照。
- [ ] **FED-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **FED-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **FED-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **FED-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **FED-012** — 未验证能力未被标记为生产完成。
