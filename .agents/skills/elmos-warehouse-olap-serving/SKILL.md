---
name: elmos-warehouse-olap-serving
description: "Use for ELMOS database or Big Data work covered by elmos-warehouse-olap-serving. Source purpose: 生成云数仓、MPP/列式 OLAP、物化视图、语义层和服务查询架构。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-warehouse-olap-serving/SKILL.md"
  source_sha256: "sha256:b1f7aefbd7a6cbf5739b5b6fb932663a6170292a6d61e8d919e75b764b5f9a29"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_warehouse_olap_serving"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据仓库、实时 OLAP 与查询服务

## 目标

生成云数仓、MPP/列式 OLAP、物化视图、语义层和服务查询架构。

## 适用触发条件

- BI/即席/实时大屏
- 选择实时 OLAP/云数仓
- 湖仓查询服务

## 输入

- QueryProfile
- Lakehouse/warehouse 模型
- SLO
- 成本运维

## 执行流程

1. **OLAP-001** — 区分离线报表、交互 BI、实时分析、客户嵌入分析和高并发 API。
2. **OLAP-002** — 在云数仓、ClickHouse、Doris、StarRocks、Druid、Pinot、Trino 等角色中筛选。
3. **OLAP-003** — 设计星型/雪花/宽表/明细/聚合、物化视图和语义层。
4. **OLAP-004** — 规划 ingestion、更新删除、分区、排序/主键、分桶、副本和冷热层。
5. **OLAP-005** — 设计资源组、并发、超时、缓存和 noisy-neighbor 隔离。
6. **OLAP-006** — 用代表查询验证扫描、join、聚合、尾延迟、写查并发，并提供降级。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `analytics-serving/`
- `olap-model.json`
- `materialization-plan.md`
- `query-slo.json`

## 验收标准

- 引擎与查询模式和新鲜度匹配。
- 指标、语义层、权限一致。
- 写入与查询并发有基准。
- 高成本查询有预算边界。

## 失败、降级与恢复

达不到交互 SLO 时生成预聚合或异步路径，不以无限扩容掩盖模型问题。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **OLAP-007** — 输入和授权范围已固化为不可变快照。
- [ ] **OLAP-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **OLAP-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **OLAP-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **OLAP-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **OLAP-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-warehouse-olap-serving/SKILL.md`, and `sha256:b1f7aefbd7a6cbf5739b5b6fb932663a6170292a6d61e8d919e75b764b5f9a29`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector", "elmos-lakehouse-generator", "elmos-polyglot-persistence-planner"]`. Triggers: `["BI/即席/实时大屏", "选择实时 OLAP/云数仓", "湖仓查询服务"]`. Declared outputs: `["analytics-serving/", "olap-model.json", "materialization-plan.md", "query-slo.json"]`. Stable task IDs: `["OLAP-001", "OLAP-002", "OLAP-003", "OLAP-004", "OLAP-005", "OLAP-006", "OLAP-007", "OLAP-008", "OLAP-009", "OLAP-010", "OLAP-011", "OLAP-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_warehouse_olap_serving` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
