---
name: elmos-data-quality-observability
description: 生成数据契约、质量测试、异常检测、freshness/volume/schema SLO、告警与根因线索。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-data-modeling-semantic-layer", "elmos-metadata-catalog-lineage"]
triggers: ["保证数据可信", "管道上线", "报表/模型异常"]
outputs: ["data-contracts/", "quality-tests/", "data-slos.json", "observability-dashboards/"]
---

# 数据质量、可观测性与 Data SLO

## 目标

生成数据契约、质量测试、异常检测、freshness/volume/schema SLO、告警与根因线索。

## 适用触发条件

- 保证数据可信
- 管道上线
- 报表/模型异常

## 输入

- DataModel
- Lineage
- 业务不变量
- 历史质量与运行指标

## 执行流程

1. **DQOBS-001** — 为源、事件、表、特征、指标和 API 定义 owner、schema、freshness、completeness、compatibility。
2. **DQOBS-002** — 生成 not-null、unique、referential、range、distribution、volume、freshness、业务不变量测试。
3. **DQOBS-003** — 区分阻断、隔离、告警和观察级，避免所有异常都停平台。
4. **DQOBS-004** — 监控 lag、watermark、checkpoint、row/bytes/files、schema drift 和成本。
5. **DQOBS-005** — 用季节性与业务日历做异常检测，同时保留确定性阈值。
6. **DQOBS-006** — 结合 lineage 做影响分析和根因排序，生成 quarantine、补数、重跑、回滚和通知。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `data-contracts/`
- `quality-tests/`
- `data-slos.json`
- `observability-dashboards/`

## 验收标准

- 核心资产有 owner/contract/test/SLO。
- 失败有明确处置。
- 异常可解释且有误报控制。
- 告警关联 lineage/运行/版本。

## 失败、降级与恢复

质量未知时标记 uncertified，不默认可信；自动修复前保留原始快照。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **DQOBS-007** — 输入和授权范围已固化为不可变快照。
- [ ] **DQOBS-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **DQOBS-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **DQOBS-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **DQOBS-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **DQOBS-012** — 未验证能力未被标记为生产完成。
