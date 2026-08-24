---
name: elmos-database-schema-physical-design
description: "Use for ELMOS database or Big Data work covered by elmos-database-schema-physical-design. Source purpose: 从领域模型和查询画像生成逻辑模型、物理 Schema、索引、分区、分片、压缩与演进策略。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-schema-physical-design/SKILL.md"
  source_sha256: "sha256:c61cfcc2aebbf9efd98801b3cc911a42c95e9b0b5815f4bb253caced361fa744"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_database_schema_physical_design"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Schema、索引、分区与物理设计生成

## 目标

从领域模型和查询画像生成逻辑模型、物理 Schema、索引、分区、分片、压缩与演进策略。

## 适用触发条件

- 数据库组合已确定
- 需要 DDL 或表设计
- 现有 schema 优化

## 输入

- PersistencePortfolio
- 实体与事件
- QueryProfile
- 能力限制

## 执行流程

1. **SCHEMA-001** — 建立领域模型、业务键、主键、唯一性、引用完整性和租户键。
2. **SCHEMA-002** — 按 OLTP、文档、时序、图、向量、搜索、OLAP 角色生成物理模型。
3. **SCHEMA-003** — 依据过滤、连接、排序、聚合和写放大设计索引、投影、物化视图。
4. **SCHEMA-004** — 依据规模、倾斜和局部性设计分区、分片、路由键与再平衡。
5. **SCHEMA-005** — 设计压缩、编码、文件大小、compaction、TTL、冷热分层和归档。
6. **SCHEMA-006** — 生成兼容 schema 演进、DDL、迁移、数据字典、图和 explain 校验。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `logical-model.json`
- `physical-schema/`
- `index-partition-plan.md`
- `schema-evolution-policy.json`

## 验收标准

- 关键查询可映射到索引/分区/扫描策略。
- 分片键避免明显倾斜与热点。
- 演进可回滚且有兼容窗口。
- DDL、字典和模型一致。

## 失败、降级与恢复

画像不足时生成保守基线和待验证索引，不一次性创建大量未经证明的索引。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **SCHEMA-007** — 输入和授权范围已固化为不可变快照。
- [ ] **SCHEMA-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **SCHEMA-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **SCHEMA-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **SCHEMA-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **SCHEMA-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-schema-physical-design/SKILL.md`, and `sha256:c61cfcc2aebbf9efd98801b3cc911a42c95e9b0b5815f4bb253caced361fa744`.
- Source group: `database-intelligence`. Dependencies: `["elmos-polyglot-persistence-planner"]`. Triggers: `["数据库组合已确定", "需要 DDL 或表设计", "现有 schema 优化"]`. Declared outputs: `["logical-model.json", "physical-schema/", "index-partition-plan.md", "schema-evolution-policy.json"]`. Stable task IDs: `["SCHEMA-001", "SCHEMA-002", "SCHEMA-003", "SCHEMA-004", "SCHEMA-005", "SCHEMA-006", "SCHEMA-007", "SCHEMA-008", "SCHEMA-009", "SCHEMA-010", "SCHEMA-011", "SCHEMA-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_database_schema_physical_design` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
