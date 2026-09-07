---
name: elmos-bigdata-api-dashboard
description: 生成受控数据服务 API、指标查询、BI 模型、ECharts/Grafana/Superset 等可视化接口。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-warehouse-olap-serving", "elmos-data-modeling-semantic-layer"]
triggers: ["报表/大屏/嵌入分析/API", "分析结果业务应用", "实时监控"]
outputs: ["data-api/", "dashboards/", "bi-model/", "serving-contracts/"]
---

# 数据 API、BI、可视化与实时大屏

## 目标

生成受控数据服务 API、指标查询、BI 模型、ECharts/Grafana/Superset 等可视化接口。

## 适用触发条件

- 报表/大屏/嵌入分析/API
- 分析结果业务应用
- 实时监控

## 输入

- MetricsCatalog
- OLAP serving
- 用户权限
- 交互与新鲜度 SLO

## 执行流程

1. **SERVE-001** — 区分同步查询、异步导出、订阅推送、预计算和缓存路径。
2. **SERVE-002** — 生成 REST/GraphQL/SQL/semantic API 契约、分页、过滤、限流和版本。
3. **SERVE-003** — 在 ECharts、Superset、Grafana、Tableau、Power BI 等适配器中按场景选择。
4. **SERVE-004** — 图表绑定机器可读指标、新鲜度和最后更新时间。
5. **SERVE-005** — 实现租户/行列权限、masking、导出控制、审计、缓存键与失效。
6. **SERVE-006** — 测试正确性、并发、P95、权限、导出、空/错状态、时区、单位和回归。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `data-api/`
- `dashboards/`
- `bi-model/`
- `serving-contracts/`

## 验收标准

- API 与 BI 统一指标定义。
- 旧数据不伪装实时。
- 跨租户和敏感访问被阻断。
- 高成本查询有隔离。

## 失败、降级与恢复

实时数据不可用时显式降级并显示数据时间，不静默返回陈旧结果。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **SERVE-007** — 输入和授权范围已固化为不可变快照。
- [ ] **SERVE-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **SERVE-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **SERVE-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **SERVE-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **SERVE-012** — 未验证能力未被标记为生产完成。
