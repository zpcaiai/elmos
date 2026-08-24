---
name: elmos-stream-processing-generator
description: "Use for ELMOS database or Big Data work covered by elmos-stream-processing-generator. Source purpose: 生成 Flink、Kafka Streams、Spark Structured Streaming 或 Beam 的状态化实时处理工程。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-stream-processing-generator/SKILL.md"
  source_sha256: "sha256:c09579a748bba1f4629c3b0431631157f8b2d0c0d1e4e0a8303fd6b346e17314"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_stream_processing_generator"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 实时流处理项目生成

## 目标

生成 Flink、Kafka Streams、Spark Structured Streaming 或 Beam 的状态化实时处理工程。

## 适用触发条件

- 秒级或亚秒实时
- CEP/画像/实时指标/告警
- 状态化流处理

## 输入

- EventContracts
- ArchitecturePattern
- SLO
- 状态与 sink 语义

## 执行流程

1. **STREAM-001** — 按延迟、状态、生态和团队选择 Flink、Kafka Streams、Structured Streaming 或 Beam runner。
2. **STREAM-002** — 定义 event/processing time、watermark、allowed lateness、窗口、触发器和迟到侧输出。
3. **STREAM-003** — 设计 keyed state、TTL、backend、checkpoint、savepoint、升级兼容和状态预算。
4. **STREAM-004** — 处理乱序、重复、重平衡、背压、热点 key、广播状态和外部维表。
5. **STREAM-005** — 为 sink 选择事务、两阶段提交、幂等 upsert 或去重。
6. **STREAM-006** — 生成重放、恢复、升级/回滚和覆盖水位、迟到、故障、批流对比的测试。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `pipelines/stream/`
- `state-and-watermark-design.md`
- `stream-tests/`
- `checkpoint-policy.json`

## 验收标准

- 时间、状态和 sink 语义完整。
- 恢复后不丢数据且重复符合声明。
- 迟到/乱序边界已测试。
- 升级回滚有 savepoint。

## 失败、降级与恢复

sink 不支持事务/幂等时降级为可证明 at-least-once，并提供去重与补偿。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **STREAM-007** — 输入和授权范围已固化为不可变快照。
- [ ] **STREAM-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **STREAM-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **STREAM-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **STREAM-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **STREAM-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-stream-processing-generator/SKILL.md`, and `sha256:c09579a748bba1f4629c3b0431631157f8b2d0c0d1e4e0a8303fd6b346e17314`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector", "elmos-cdc-event-backbone", "elmos-database-schema-physical-design"]`. Triggers: `["秒级或亚秒实时", "CEP/画像/实时指标/告警", "状态化流处理"]`. Declared outputs: `["pipelines/stream/", "state-and-watermark-design.md", "stream-tests/", "checkpoint-policy.json"]`. Stable task IDs: `["STREAM-001", "STREAM-002", "STREAM-003", "STREAM-004", "STREAM-005", "STREAM-006", "STREAM-007", "STREAM-008", "STREAM-009", "STREAM-010", "STREAM-011", "STREAM-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_stream_processing_generator` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
