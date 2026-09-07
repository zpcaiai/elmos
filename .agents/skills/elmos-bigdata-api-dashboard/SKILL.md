---
name: elmos-bigdata-api-dashboard
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-api-dashboard. Source purpose: 生成受控数据服务 API、指标查询、BI 模型、ECharts/Grafana/Superset 等可视化接口。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-api-dashboard/SKILL.md"
  source_sha256: "sha256:2ad9414663070ea221ddf89e8f5714d456f9ef1fcd5f1a7506f196833f3052dc"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_bigdata_api_dashboard"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
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

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-api-dashboard/SKILL.md`, and `sha256:2ad9414663070ea221ddf89e8f5714d456f9ef1fcd5f1a7506f196833f3052dc`.
- Source group: `bigdata-core`. Dependencies: `["elmos-warehouse-olap-serving", "elmos-data-modeling-semantic-layer"]`. Triggers: `["报表/大屏/嵌入分析/API", "分析结果业务应用", "实时监控"]`. Declared outputs: `["data-api/", "dashboards/", "bi-model/", "serving-contracts/"]`. Stable task IDs: `["SERVE-001", "SERVE-002", "SERVE-003", "SERVE-004", "SERVE-005", "SERVE-006", "SERVE-007", "SERVE-008", "SERVE-009", "SERVE-010", "SERVE-011", "SERVE-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_bigdata_api_dashboard` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
