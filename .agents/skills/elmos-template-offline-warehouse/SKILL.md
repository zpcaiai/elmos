---
name: elmos-template-offline-warehouse
description: "Use for ELMOS database or Big Data work covered by elmos-template-offline-warehouse. Source purpose: 生成源采集、湖仓/数仓分层、批处理、语义指标、BI、质量、血缘和调度完整项目。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-offline-warehouse/SKILL.md"
  source_sha256: "sha256:b4dd5b602873b18c3d667b036cb10e8a83788a5d32f6b368bca9a6b2eeffd0ee"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_template_offline_warehouse"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/templates.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 离线企业数仓项目模板

## 目标

生成源采集、湖仓/数仓分层、批处理、语义指标、BI、质量、血缘和调度完整项目。

## 适用触发条件

- 离线数仓
- 经营分析/BI
- 日批或小时批

## 输入

- 源系统/报表/指标
- 批次 SLA
- 历史保留
- 目标部署

## 执行流程

1. **TPLDW-001** — 生成 source→raw→clean/detail→summary/serving 数据流与业务粒度。
2. **TPLDW-002** — 默认评估对象存储+开放表+Spark/dbt+Trino/OLAP，不强制固定产品。
3. **TPLDW-003** — 生成增量抽取、SCD、历史回填、分区和小文件维护。
4. **TPLDW-004** — 生成指标目录、语义层、BI 模型和经营报表样例。
5. **TPLDW-005** — 生成质量、血缘、调度、成本、权限和审计。
6. **TPLDW-006** — 执行全量/增量等价、批次 SLA、恢复和数据正确性验证。

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

- 批次 SLA 可验证。
- 指标口径统一。
- 全量/增量可对账。
- 有本地和生产配置。

## 失败、降级与恢复

源增量不可用时生成受控全量策略和源端负载保护。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLDW-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLDW-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLDW-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLDW-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLDW-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLDW-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-offline-warehouse/SKILL.md`, and `sha256:b4dd5b602873b18c3d667b036cb10e8a83788a5d32f6b368bca9a6b2eeffd0ee`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator"]`. Triggers: `["离线数仓", "经营分析/BI", "日批或小时批"]`. Declared outputs: `["template-plan.json", "generated-project/"]`. Stable task IDs: `["TPLDW-001", "TPLDW-002", "TPLDW-003", "TPLDW-004", "TPLDW-005", "TPLDW-006", "TPLDW-007", "TPLDW-008", "TPLDW-009", "TPLDW-010", "TPLDW-011", "TPLDW-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_template_offline_warehouse` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/templates.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
