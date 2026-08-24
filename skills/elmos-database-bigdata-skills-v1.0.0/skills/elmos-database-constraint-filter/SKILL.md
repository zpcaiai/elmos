---
name: elmos-database-constraint-filter
description: 先用硬约束、兼容性和政策规则淘汰不可行候选，避免软评分掩盖不合格项。
version: 1.0.0
group: database-intelligence
dependencies: ["elmos-data-requirement-intake", "elmos-workload-profiler", "elmos-database-capability-registry"]
triggers: ["已获得需求 IR 和注册表", "需要候选集", "存在合规或部署硬约束"]
outputs: ["feasible-candidates.json", "rejected-candidates.json", "constraint-proof.json"]
---

# 数据库硬约束过滤器

## 目标

先用硬约束、兼容性和政策规则淘汰不可行候选，避免软评分掩盖不合格项。

## 适用触发条件

- 已获得需求 IR 和注册表
- 需要候选集
- 存在合规或部署硬约束

## 输入

- WorkloadRequirementIR
- DataProfile
- Capability Registry
- 组织政策

## 执行流程

1. **FILTER-001** — 把驻留、许可证、部署、语言、事务、一致性、RPO/RTO 转为硬约束。
2. **FILTER-002** — 把容量、对象限制、分区键、索引、状态大小和类型兼容转为技术约束。
3. **FILTER-003** — 按 system-of-record、cache、search、analytics、lakehouse、graph、vector 分角色过滤。
4. **FILTER-004** — 用规则引擎或 CP-SAT 求解可行组合，而不是只选单个产品。
5. **FILTER-005** — 为淘汰项输出约束、证据和可解除条件；无解时生成最小冲突集合。
6. **FILTER-006** — 固定输入、规则和注册表快照，保证结果可重放。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `feasible-candidates.json`
- `rejected-candidates.json`
- `constraint-proof.json`

## 验收标准

- 所有候选通过硬约束。
- 拒绝项有具体原因。
- 无解时不静默放宽约束。
- 结果对同一快照确定。

## 失败、降级与恢复

无解时生成降级候选，但不得违反安全、合规或数据完整性要求。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **FILTER-007** — 输入和授权范围已固化为不可变快照。
- [ ] **FILTER-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **FILTER-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **FILTER-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **FILTER-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **FILTER-012** — 未验证能力未被标记为生产完成。
