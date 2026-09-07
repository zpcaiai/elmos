---
name: elmos-data-modeling-semantic-layer
description: "Use for ELMOS database or Big Data work covered by elmos-data-modeling-semantic-layer. Source purpose: 生成维度模型、Data Vault、明细/汇总层、SCD、指标口径和机器可读语义层。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-data-modeling-semantic-layer/SKILL.md"
  source_sha256: "sha256:c60009cff9b6c02de2b4ba7a2f78a3f4b44d6839596aeeab923c1958099648b0"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_data_modeling_semantic_layer"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据建模、分层与语义指标

## 目标

生成维度模型、Data Vault、明细/汇总层、SCD、指标口径和机器可读语义层。

## 适用触发条件

- 建设数仓或湖仓
- 统一指标口径
- 多域共享数据

## 输入

- 业务过程与实体
- 查询/报表
- 源 schema/事件
- 历史变更

## 执行流程

1. **MODEL-001** — 识别事实、维度、粒度、业务键、事件和度量，先定义业务语义。
2. **MODEL-002** — 按变化频率、审计和团队选择 3NF、星型、雪花、Data Vault、宽表或混合。
3. **MODEL-003** — 定义 SCD、有效/系统时间、迟到维度和回溯修正。
4. **MODEL-004** — 明确 raw/detail/summary/serving 责任，禁止无价值层级复制。
5. **MODEL-005** — 定义指标公式、维度、过滤、时间口径、owner、版本和测试。
6. **MODEL-006** — 生成 dbt/SQL/semantic model、字典、ER 图、lineage，并验证批流/API/BI 一致。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `data-model/`
- `metrics-catalog.json`
- `semantic-layer/`
- `modeling-adr.md`

## 验收标准

- 事实粒度唯一明确。
- 指标机器可读、版本化、有测试。
- 历史/迟到行为完整。
- 批流/API/BI 核心指标一致。

## 失败、降级与恢复

口径冲突时保留多个命名空间版本并标记 owner，不擅自合并。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **MODEL-007** — 输入和授权范围已固化为不可变快照。
- [ ] **MODEL-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **MODEL-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **MODEL-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **MODEL-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **MODEL-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-data-modeling-semantic-layer/SKILL.md`, and `sha256:c60009cff9b6c02de2b4ba7a2f78a3f4b44d6839596aeeab923c1958099648b0`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector", "elmos-database-schema-physical-design", "elmos-lakehouse-generator", "elmos-warehouse-olap-serving"]`. Triggers: `["建设数仓或湖仓", "统一指标口径", "多域共享数据"]`. Declared outputs: `["data-model/", "metrics-catalog.json", "semantic-layer/", "modeling-adr.md"]`. Stable task IDs: `["MODEL-001", "MODEL-002", "MODEL-003", "MODEL-004", "MODEL-005", "MODEL-006", "MODEL-007", "MODEL-008", "MODEL-009", "MODEL-010", "MODEL-011", "MODEL-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_data_modeling_semantic_layer` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
