---
name: elmos-polyglot-persistence-planner
description: "Use for ELMOS database or Big Data work covered by elmos-polyglot-persistence-planner. Source purpose: 按业务域和访问路径规划最少必要的多模数据库组合、数据所有权、同步和一致性边界。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-polyglot-persistence-planner/SKILL.md"
  source_sha256: "sha256:10df4ac7c88ff794101ead739a6681e75a340619302c5b6ab557072bf7173585"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_polyglot_persistence_planner"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 多模数据库与数据所有权规划

## 目标

按业务域和访问路径规划最少必要的多模数据库组合、数据所有权、同步和一致性边界。

## 适用触发条件

- 单库无法满足全部角色
- 微服务或 DDD
- 需要缓存/搜索/分析旁路

## 输入

- CandidateRanking
- 业务域与实体
- 访问路径
- 团队运维能力

## 执行流程

1. **POLY-001** — 为每个 bounded context 指定唯一 system of record。
2. **POLY-002** — 把缓存、搜索、向量、图、时序、OLAP、湖仓定义为明确派生角色。
3. **POLY-003** — 优先一库多能力，只有 SLO/数据模型差异可量化时才新增技术。
4. **POLY-004** — 为派生存储设计 CDC/Outbox/事件/批同步，明确延迟、顺序、幂等、删除和重建。
5. **POLY-005** — 计算组合的运维复杂度、故障域、复制成本和一致性风险。
6. **POLY-006** — 生成缓存/搜索/分析故障时的降级路径和禁止的跨库事务模式。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `persistence-portfolio.json`
- `data-ownership-map.md`
- `synchronization-contracts.json`

## 验收标准

- 每份数据有唯一权威来源。
- 新增技术有量化必要性和重建策略。
- 同步具备幂等、删除和 schema 演进。
- 复杂度不超过团队约束。

## 失败、降级与恢复

无法证明新增数据库必要性时回退到更简单组合，并显式记录未满足 SLO。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **POLY-007** — 输入和授权范围已固化为不可变快照。
- [ ] **POLY-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **POLY-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **POLY-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **POLY-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **POLY-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-polyglot-persistence-planner/SKILL.md`, and `sha256:10df4ac7c88ff794101ead739a6681e75a340619302c5b6ab557072bf7173585`.
- Source group: `database-intelligence`. Dependencies: `["elmos-database-mcda-ranker"]`. Triggers: `["单库无法满足全部角色", "微服务或 DDD", "需要缓存/搜索/分析旁路"]`. Declared outputs: `["persistence-portfolio.json", "data-ownership-map.md", "synchronization-contracts.json"]`. Stable task IDs: `["POLY-001", "POLY-002", "POLY-003", "POLY-004", "POLY-005", "POLY-006", "POLY-007", "POLY-008", "POLY-009", "POLY-010", "POLY-011", "POLY-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_polyglot_persistence_planner` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
