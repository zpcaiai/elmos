---
name: elmos-database-migration-modernization
description: "Use for ELMOS database or Big Data work covered by elmos-database-migration-modernization. Source purpose: 生成可恢复迁移 DAG，覆盖 schema、数据、CDC、应用改造、影子验证、切流和回滚。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-migration-modernization/SKILL.md"
  source_sha256: "sha256:2a750c3da6cbd577f7eadb028c9ffe9eb0d13f73f02033c51d409915ca11e994"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_database_migration_modernization"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据库迁移、分拆与现代化

## 目标

生成可恢复迁移 DAG，覆盖 schema、数据、CDC、应用改造、影子验证、切流和回滚。

## 适用触发条件

- 数据库迁移或替换
- 单体拆分
- 上云/国产化/湖仓升级

## 输入

- 源目标数据库
- schema 与规模
- 应用依赖
- 一致性与停机

## 执行流程

1. **MIG-001** — 盘点 DDL、SQL、存储过程、触发器、扩展、字符集、时间语义和驱动依赖。
2. **MIG-002** — 生成类型、DDL、查询与行为差异映射，标记不可自动转换项。
3. **MIG-003** — 设计全量快照、增量 CDC、校验水位、重放、幂等和断点续传。
4. **MIG-004** — 优先 Outbox/CDC/双读或影子流量，避免不可控应用双写。
5. **MIG-005** — 执行行数、校验和、业务不变量、结果、性能和故障语义差分。
6. **MIG-006** — 按租户/表/分片/流量渐进切换，保存节点进度、成本、证据和回退点。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `migration-dag.json`
- `cutover-plan.md`
- `rollback-plan.md`
- `migration-evidence/`

## 验收标准

- DAG 可暂停恢复且副作用幂等。
- 数据/schema/行为/性能有差分证据。
- 切流分阶段且有回滚阈值。
- 退役前清理依赖与审计。

## 失败、降级与恢复

任何不可逆步骤前创建恢复点；验证失败时停止扩流并回到稳定状态。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **MIG-007** — 输入和授权范围已固化为不可变快照。
- [ ] **MIG-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **MIG-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **MIG-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **MIG-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **MIG-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-migration-modernization/SKILL.md`, and `sha256:2a750c3da6cbd577f7eadb028c9ffe9eb0d13f73f02033c51d409915ca11e994`.
- Source group: `database-intelligence`. Dependencies: `["elmos-polyglot-persistence-planner", "elmos-database-schema-physical-design", "elmos-database-ha-dr", "elmos-database-security-multitenancy"]`. Triggers: `["数据库迁移或替换", "单体拆分", "上云/国产化/湖仓升级"]`. Declared outputs: `["migration-dag.json", "cutover-plan.md", "rollback-plan.md", "migration-evidence/"]`. Stable task IDs: `["MIG-001", "MIG-002", "MIG-003", "MIG-004", "MIG-005", "MIG-006", "MIG-007", "MIG-008", "MIG-009", "MIG-010", "MIG-011", "MIG-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_database_migration_modernization` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
