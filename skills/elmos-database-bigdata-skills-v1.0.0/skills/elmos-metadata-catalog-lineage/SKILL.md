---
name: elmos-metadata-catalog-lineage
description: 生成技术/业务元数据、目录、运行血缘、列级血缘、影响分析和所有权体系。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-data-modeling-semantic-layer"]
triggers: ["数据治理/可发现", "多引擎多管道", "影响分析与审计"]
outputs: ["metadata-platform/", "lineage-policy.json", "ownership-map.json", "catalog-seed/"]
---

# 元数据、数据目录与端到端血缘

## 目标

生成技术/业务元数据、目录、运行血缘、列级血缘、影响分析和所有权体系。

## 适用触发条件

- 数据治理/可发现
- 多引擎多管道
- 影响分析与审计

## 输入

- DataModel
- pipeline DAG
- 数据库/BI 元数据
- 组织所有权

## 执行流程

1. **META-001** — 定义 dataset/job/run/column/dashboard/metric/model/owner 的稳定标识。
2. **META-002** — 采用 OpenLineage 等运行事件标准，接入 Spark/Flink/Airflow/Dagster/dbt/查询引擎。
3. **META-003** — 选择 OpenMetadata、DataHub、Atlas 或兼容目录并保留可替换接口。
4. **META-004** — 采集 schema、统计、标签、术语、质量、SLO、使用量、血缘和版本。
5. **META-005** — 实现表/列/跨系统和设计态/运行态血缘，建立 owner/steward/domain/认证/弃用。
6. **META-006** — 生成影响分析、通知、审批、审计和 lineage completeness 校验。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `metadata-platform/`
- `lineage-policy.json`
- `ownership-map.json`
- `catalog-seed/`

## 验收标准

- 关键资产和指标有 owner。
- 运行血缘可追输入、转换、输出、版本。
- 列级血缘覆盖敏感字段。
- 目录权限不泄漏元数据。

## 失败、降级与恢复

自动血缘不全时显示覆盖率并允许人工补充，不把推断标成已观测。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **META-007** — 输入和授权范围已固化为不可变快照。
- [ ] **META-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **META-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **META-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **META-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **META-012** — 未验证能力未被标记为生产完成。
