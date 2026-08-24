---
name: elmos-lakehouse-generator
description: "Use for ELMOS database or Big Data work covered by elmos-lakehouse-generator. Source purpose: 生成对象存储、开放表格式、Catalog、多引擎、压缩、compaction、时间旅行和治理完整湖仓。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-lakehouse-generator/SKILL.md"
  source_sha256: "sha256:ffd2c45df8a7310839912e641954c20a2c854492fce20e5b2b6582873ce1b4be"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
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

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-lakehouse-generator/SKILL.md`, and `sha256:ffd2c45df8a7310839912e641954c20a2c854492fce20e5b2b6582873ce1b4be`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector", "elmos-ingestion-connector-planner", "elmos-batch-processing-generator", "elmos-stream-processing-generator"]`. Triggers: `["数据湖或湖仓", "历史/回溯/多引擎", "开放表格式"]`. Declared outputs: `["lakehouse/", "table-layout-plan.json", "catalog-design.md", "maintenance-jobs/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
