---
name: elmos-template-realtime-analytics
description: 生成事件总线、实时流处理、实时 OLAP、大屏、告警、回放和低延迟验证项目。
version: 1.0.0
group: bigdata-templates
dependencies: ["elmos-bigdata-project-orchestrator"]
triggers: ["实时大屏", "实时指标", "秒级分析/监控"]
outputs: ["template-plan.json", "generated-project/"]
---

# 实时计算与实时分析模板

## 目标

生成事件总线、实时流处理、实时 OLAP、大屏、告警、回放和低延迟验证项目。

## 适用触发条件

- 实时大屏
- 实时指标
- 秒级分析/监控

## 输入

- 事件源
- 实时指标查询
- 延迟/吞吐 SLO
- 回放保留

## 执行流程

1. **TPLRT-001** — 生成 CDC/事件→Kafka/Pulsar→Flink/等价引擎→OLAP/cache→API/大屏。
2. **TPLRT-002** — 定义 event time、watermark、late data、dedup、state、checkpoint。
3. **TPLRT-003** — 生成实时/离线对账、重放和历史修正路径。
4. **TPLRT-004** — 生成物化/预聚合、查询并发和新鲜度显示。
5. **TPLRT-005** — 生成 lag/backpressure/checkpoint/query latency/cost 监控。
6. **TPLRT-006** — 测试峰值、乱序、重复、broker/worker 故障和恢复。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `template-plan.json`
- `generated-project/`

## 验收标准

- time-to-insight 达标。
- 乱序迟到正确。
- 重放不污染实时。
- 大屏显示新鲜度。

## 失败、降级与恢复

无法达到亚秒级时比较预聚合、缓存和异步降级。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLRT-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLRT-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLRT-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLRT-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLRT-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLRT-012** — 未验证能力未被标记为生产完成。
