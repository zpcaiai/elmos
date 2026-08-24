---
name: elmos-batch-processing-generator
description: "Use for ELMOS database or Big Data work covered by elmos-batch-processing-generator. Source purpose: 生成可增量、可回填、可测试的 Spark/Flink Batch/Beam/dbt 批处理工程。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-batch-processing-generator/SKILL.md"
  source_sha256: "sha256:18f4f4ae09de8192ea164d9800d65583203de8effa7fb75cb2abe8bc174fffb8"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 离线批处理与 ETL/ELT 项目生成

## 目标

生成可增量、可回填、可测试的 Spark/Flink Batch/Beam/dbt 批处理工程。

## 适用触发条件

- 离线数仓或历史重算
- 生成批处理代码
- 替换遗留 MapReduce

## 输入

- ArchitecturePattern
- SourceContracts
- DataModel
- SLA/容量

## 执行流程

1. **BATCH-001** — 选择 Spark SQL/DataFrame、Flink Batch、Beam 或数据库内 ELT；遗留 MapReduce 仅作兼容。
2. **BATCH-002** — 生成分层 pipeline、显式输入输出契约、分区裁剪、谓词下推和可复用转换。
3. **BATCH-003** — 为作业定义 full refresh、incremental、merge、watermark 和 backfill。
4. **BATCH-004** — 使用 staging、atomic commit、snapshot 或事务表格式保证幂等提交。
5. **BATCH-005** — 处理小文件、倾斜、shuffle、spill、资源隔离和并发调度。
6. **BATCH-006** — 生成质量、单元、集成、回归、性能、lineage、监控和失败恢复。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `pipelines/batch/`
- `batch-dag.json`
- `incremental-strategy.md`
- `batch-tests/`

## 验收标准

- 重复运行不产生重复或部分提交。
- 增量与全量在定义范围等价。
- 分区/倾斜/资源策略有验证。
- 代码、DAG、测试、文档齐全。

## 失败、降级与恢复

无法证明增量等价时保留全量校验路径并阻止直接替换生产基线。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **BATCH-007** — 输入和授权范围已固化为不可变快照。
- [ ] **BATCH-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **BATCH-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **BATCH-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **BATCH-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **BATCH-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-batch-processing-generator/SKILL.md`, and `sha256:18f4f4ae09de8192ea164d9800d65583203de8effa7fb75cb2abe8bc174fffb8`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector", "elmos-ingestion-connector-planner", "elmos-database-schema-physical-design"]`. Triggers: `["离线数仓或历史重算", "生成批处理代码", "替换遗留 MapReduce"]`. Declared outputs: `["pipelines/batch/", "batch-dag.json", "incremental-strategy.md", "batch-tests/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
