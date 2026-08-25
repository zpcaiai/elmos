---
name: elmos-data-architecture-adr
description: "Use for ELMOS database or Big Data work covered by elmos-data-architecture-adr. Source purpose: 生成可审计的数据库和大数据架构 ADR，记录候选、权衡、证据、假设、回退和复评条件。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-data-architecture-adr/SKILL.md"
  source_sha256: "sha256:ba40f442a2f17ece63aa3365f6f358b4213b689d957f3e8bff401b507e701be6"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_data_architecture_adr"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据架构决策记录与证据

## 目标

生成可审计的数据库和大数据架构 ADR，记录候选、权衡、证据、假设、回退和复评条件。

## 适用触发条件

- 完成技术选型
- 架构评审
- 建立不可变生成基线

## 输入

- Decision IR
- 候选排序
- 成本/基准/风险
- 批准策略

## 执行流程

1. **ADR-001** — 记录问题、上下文、硬约束、软偏好、候选、选择和拒绝原因。
2. **ADR-002** — 引用注册表证据和基准快照，不复制未经验证的营销结论。
3. **ADR-003** — 记录数据流、所有权、一致性、故障域、RPO/RTO 和成本范围。
4. **ADR-004** — 列出假设、未知、验证任务、回退方案和重新评估触发器。
5. **ADR-005** — 生成机器可读 decision-ledger，绑定需求、规则、模型和代码版本。
6. **ADR-006** — 支持 supersede，保持历史决策不可变；进入生成前做 readiness check。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `ADR-data-architecture.md`
- `decision-ledger.json`
- `architecture-baseline.json`

## 验收标准

- 重大选择有替代方案和拒绝理由。
- 证据、假设、风险和回退完整。
- ADR 与机器基线一致。
- 历史版本可追踪。

## 失败、降级与恢复

关键证据缺失时状态为 proposed/conditional，不能标记 accepted 或 production-ready。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **ADR-007** — 输入和授权范围已固化为不可变快照。
- [ ] **ADR-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **ADR-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **ADR-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **ADR-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **ADR-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-data-architecture-adr/SKILL.md`, and `sha256:ba40f442a2f17ece63aa3365f6f358b4213b689d957f3e8bff401b507e701be6`.
- Source group: `database-intelligence`. Dependencies: `["elmos-polyglot-persistence-planner"]`. Triggers: `["完成技术选型", "架构评审", "建立不可变生成基线"]`. Declared outputs: `["ADR-data-architecture.md", "decision-ledger.json", "architecture-baseline.json"]`. Stable task IDs: `["ADR-001", "ADR-002", "ADR-003", "ADR-004", "ADR-005", "ADR-006", "ADR-007", "ADR-008", "ADR-009", "ADR-010", "ADR-011", "ADR-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_data_architecture_adr` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
