---
name: elmos-cdc-event-backbone
description: "Use for ELMOS database or Big Data work covered by elmos-cdc-event-backbone. Source purpose: 生成日志型 CDC、Outbox、事件总线、Schema 演进、顺序、去重和消费语义。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-cdc-event-backbone/SKILL.md"
  source_sha256: "sha256:79405915ea7ca8d17827b19060f7e9adfb0e34aedf7eaa628d6efc2a340823fc"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_cdc_event_backbone"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# CDC、事件总线与数据契约

## 目标

生成日志型 CDC、Outbox、事件总线、Schema 演进、顺序、去重和消费语义。

## 适用触发条件

- 数据库变更实时传播
- 事件驱动数据平台
- 替代轮询或危险双写

## 输入

- IngestionPlan
- 源数据库能力
- 消费者
- 一致性/顺序/保留

## 执行流程

1. **CDC-001** — 在原生日志 CDC、Outbox、应用事件和轮询之间按可靠性与侵入性选择。
2. **CDC-002** — 定义 snapshot→streaming 一致水位、offset、复制槽/binlog 保留和恢复。
3. **CDC-003** — 设计 topic/stream、partition key、ordering domain、retention、compaction 和租户隔离。
4. **CDC-004** — 定义 event envelope、业务键、schema id、source position、event time、trace/idempotency id。
5. **CDC-005** — 设置 backward/forward/full 兼容和 CI 检查；处理重复、乱序、删除、DDL、事务边界和 DLQ。
6. **CDC-006** — 消费者采用事务、幂等 upsert 或去重；重放与重建按租户和范围受控。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `cdc-topology.md`
- `event-contracts/`
- `topic-design.json`
- `replay-policy.json`

## 验收标准

- snapshot 与增量无未解释缺口。
- 顺序、幂等、删除、演进明确。
- exactly-once 声明含 source/engine/sink 前提。
- 可安全重放。

## 失败、降级与恢复

无法保证端到端 exactly-once 时明确采用 at-least-once + 幂等，不做错误承诺。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **CDC-007** — 输入和授权范围已固化为不可变快照。
- [ ] **CDC-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **CDC-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **CDC-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **CDC-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **CDC-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-cdc-event-backbone/SKILL.md`, and `sha256:79405915ea7ca8d17827b19060f7e9adfb0e34aedf7eaa628d6efc2a340823fc`.
- Source group: `bigdata-core`. Dependencies: `["elmos-ingestion-connector-planner", "elmos-database-security-multitenancy"]`. Triggers: `["数据库变更实时传播", "事件驱动数据平台", "替代轮询或危险双写"]`. Declared outputs: `["cdc-topology.md", "event-contracts/", "topic-design.json", "replay-policy.json"]`. Stable task IDs: `["CDC-001", "CDC-002", "CDC-003", "CDC-004", "CDC-005", "CDC-006", "CDC-007", "CDC-008", "CDC-009", "CDC-010", "CDC-011", "CDC-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_cdc_event_backbone` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
