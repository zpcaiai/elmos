---
name: elmos-data-architecture-adr
description: 生成可审计的数据库和大数据架构 ADR，记录候选、权衡、证据、假设、回退和复评条件。
version: 1.0.0
group: database-intelligence
dependencies: ["elmos-polyglot-persistence-planner"]
triggers: ["完成技术选型", "架构评审", "建立不可变生成基线"]
outputs: ["ADR-data-architecture.md", "decision-ledger.json", "architecture-baseline.json"]
---

# 数据架构决策记录与证据

## 目标

生成可审计的数据库和大数据架构 ADR，记录候选、权衡、证据、假设、回退和复评条件。

## 适用触发条件

- 完成技术选型
- 架构评审
- 建立不可变生成基线

## 输入

- Decision IR
- 候选排序
- 成本/基准/风险
- 批准策略

## 执行流程

1. **ADR-001** — 记录问题、上下文、硬约束、软偏好、候选、选择和拒绝原因。
2. **ADR-002** — 引用注册表证据和基准快照，不复制未经验证的营销结论。
3. **ADR-003** — 记录数据流、所有权、一致性、故障域、RPO/RTO 和成本范围。
4. **ADR-004** — 列出假设、未知、验证任务、回退方案和重新评估触发器。
5. **ADR-005** — 生成机器可读 decision-ledger，绑定需求、规则、模型和代码版本。
6. **ADR-006** — 支持 supersede，保持历史决策不可变；进入生成前做 readiness check。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `ADR-data-architecture.md`
- `decision-ledger.json`
- `architecture-baseline.json`

## 验收标准

- 重大选择有替代方案和拒绝理由。
- 证据、假设、风险和回退完整。
- ADR 与机器基线一致。
- 历史版本可追踪。

## 失败、降级与恢复

关键证据缺失时状态为 proposed/conditional，不能标记 accepted 或 production-ready。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **ADR-007** — 输入和授权范围已固化为不可变快照。
- [ ] **ADR-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **ADR-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **ADR-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **ADR-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **ADR-012** — 未验证能力未被标记为生产完成。
