---
name: elmos-cdc-event-backbone
description: 生成日志型 CDC、Outbox、事件总线、Schema 演进、顺序、去重和消费语义。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-ingestion-connector-planner", "elmos-database-security-multitenancy"]
triggers: ["数据库变更实时传播", "事件驱动数据平台", "替代轮询或危险双写"]
outputs: ["cdc-topology.md", "event-contracts/", "topic-design.json", "replay-policy.json"]
---

# CDC、事件总线与数据契约

## 目标

生成日志型 CDC、Outbox、事件总线、Schema 演进、顺序、去重和消费语义。

## 适用触发条件

- 数据库变更实时传播
- 事件驱动数据平台
- 替代轮询或危险双写

## 输入

- IngestionPlan
- 源数据库能力
- 消费者
- 一致性/顺序/保留

## 执行流程

1. **CDC-001** — 在原生日志 CDC、Outbox、应用事件和轮询之间按可靠性与侵入性选择。
2. **CDC-002** — 定义 snapshot→streaming 一致水位、offset、复制槽/binlog 保留和恢复。
3. **CDC-003** — 设计 topic/stream、partition key、ordering domain、retention、compaction 和租户隔离。
4. **CDC-004** — 定义 event envelope、业务键、schema id、source position、event time、trace/idempotency id。
5. **CDC-005** — 设置 backward/forward/full 兼容和 CI 检查；处理重复、乱序、删除、DDL、事务边界和 DLQ。
6. **CDC-006** — 消费者采用事务、幂等 upsert 或去重；重放与重建按租户和范围受控。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `cdc-topology.md`
- `event-contracts/`
- `topic-design.json`
- `replay-policy.json`

## 验收标准

- snapshot 与增量无未解释缺口。
- 顺序、幂等、删除、演进明确。
- exactly-once 声明含 source/engine/sink 前提。
- 可安全重放。

## 失败、降级与恢复

无法保证端到端 exactly-once 时明确采用 at-least-once + 幂等，不做错误承诺。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **CDC-007** — 输入和授权范围已固化为不可变快照。
- [ ] **CDC-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **CDC-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **CDC-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **CDC-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **CDC-012** — 未验证能力未被标记为生产完成。
