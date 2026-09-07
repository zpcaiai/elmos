---
name: elmos-lakehouse-generator
description: 生成对象存储、开放表格式、Catalog、多引擎、压缩、compaction、时间旅行和治理完整湖仓。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-bigdata-pattern-selector", "elmos-ingestion-connector-planner", "elmos-batch-processing-generator", "elmos-stream-processing-generator"]
triggers: ["数据湖或湖仓", "历史/回溯/多引擎", "开放表格式"]
outputs: ["lakehouse/", "table-layout-plan.json", "catalog-design.md", "maintenance-jobs/"]
---

# 数据湖与湖仓一体项目生成

## 目标

生成对象存储、开放表格式、Catalog、多引擎、压缩、compaction、时间旅行和治理完整湖仓。

## 适用触发条件

- 数据湖或湖仓
- 历史/回溯/多引擎
- 开放表格式

## 输入

- ArchitecturePattern
- 数据模型与生命周期
- 批流作业
- 对象存储/引擎

## 执行流程

1. **LAKE-001** — 在 Iceberg、Delta Lake、Hudi 中按引擎生态、更新模式和治理要求选择。
2. **LAKE-002** — 设计 object store、catalog、namespace、warehouse、权限和多环境隔离。
3. **LAKE-003** — 采用 Parquet/ORC/Avro，设计文件大小、排序、分区、聚簇和统计。
4. **LAKE-004** — 定义 append/upsert/merge/delete、snapshot、time travel、branch/tag 和并发提交。
5. **LAKE-005** — 生成 compaction、小文件重写、元数据清理、过期快照和 orphan file 清理。
6. **LAKE-006** — 支持批回填和流写入，验证多引擎兼容、分层、质量、血缘、安全和恢复。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `lakehouse/`
- `table-layout-plan.json`
- `catalog-design.md`
- `maintenance-jobs/`

## 验收标准

- 表格式与目标引擎兼容。
- 分区/文件/maintenance 有容量依据。
- 批流并发与演进已测试。
- 不存在无治理数据沼泽。

## 失败、降级与恢复

多引擎写兼容未验证时限制为单写多读，并显式记录边界。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **LAKE-007** — 输入和授权范围已固化为不可变快照。
- [ ] **LAKE-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **LAKE-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **LAKE-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **LAKE-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **LAKE-012** — 未验证能力未被标记为生产完成。
