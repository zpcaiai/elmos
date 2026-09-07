---
name: elmos-ingestion-connector-planner
description: "Use for ELMOS database or Big Data work covered by elmos-ingestion-connector-planner. Source purpose: 为数据库、文件、日志、API、SaaS、消息、IoT 和对象存储生成可靠采集方案。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-ingestion-connector-planner/SKILL.md"
  source_sha256: "sha256:8938752437b635b9e68a6a8dce4a3ad7c3086c9a622e9f515277251328e59cab"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_ingestion_connector_planner"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 多源数据采集与连接器规划

## 目标

为数据库、文件、日志、API、SaaS、消息、IoT 和对象存储生成可靠采集方案。

## 适用触发条件

- 接入数据源
- 生成 ETL/ELT 或流采集
- 评估连接器

## 输入

- SourceInventory
- ArchitecturePattern
- 源系统限制
- 数据契约

## 执行流程

1. **INGEST-001** — 为每个源选择 snapshot、incremental、CDC、polling、webhook、stream、file-drop 或 API。
2. **INGEST-002** — 评估源端负载、限流、窗口、分页、断点、日志保留和 schema 获取。
3. **INGEST-003** — 选择 Debezium、Kafka Connect、Flink CDC、DataX、SeaTunnel、NiFi 或定制适配器。
4. **INGEST-004** — 定义 offset、水位、幂等键、文件原子性、重复检测和断点续传。
5. **INGEST-005** — 定义 Avro/Protobuf/JSON/Parquet、压缩和 Schema Registry 策略。
6. **INGEST-006** — 生成 quarantine、DLQ、回放、审计、租户隔离、健康检查和故障测试。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `ingestion-plan.json`
- `connector-matrix.json`
- `source-contracts/`

## 验收标准

- 每个源有模式、offset、幂等、schema 和故障策略。
- 不以高频轮询压垮源端。
- 凭据最小权限。
- 采集可回放且不静默丢数。

## 失败、降级与恢复

源缺可靠增量能力时明确全量窗口和一致性风险，不伪装为无损 CDC。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **INGEST-007** — 输入和授权范围已固化为不可变快照。
- [ ] **INGEST-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **INGEST-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **INGEST-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **INGEST-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **INGEST-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-ingestion-connector-planner/SKILL.md`, and `sha256:8938752437b635b9e68a6a8dce4a3ad7c3086c9a622e9f515277251328e59cab`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector"]`. Triggers: `["接入数据源", "生成 ETL/ELT 或流采集", "评估连接器"]`. Declared outputs: `["ingestion-plan.json", "connector-matrix.json", "source-contracts/"]`. Stable task IDs: `["INGEST-001", "INGEST-002", "INGEST-003", "INGEST-004", "INGEST-005", "INGEST-006", "INGEST-007", "INGEST-008", "INGEST-009", "INGEST-010", "INGEST-011", "INGEST-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_ingestion_connector_planner` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
