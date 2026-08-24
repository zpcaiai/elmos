---
name: elmos-bigdata-pattern-selector
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-pattern-selector. Source purpose: 根据处理语义、回放、延迟、团队和成本选择可组合的大数据架构模式。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-pattern-selector/SKILL.md"
  source_sha256: "sha256:54241ebe4cd315868c6ee9dc92b2b3eedf35f9d5188f0aedc5bf92a99ed508da"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Lambda、Kappa、统一流批、湖仓与联邦模式选择

## 目标

根据处理语义、回放、延迟、团队和成本选择可组合的大数据架构模式。

## 适用触发条件

- 已分类
- 确定宏观架构
- 比较 Lambda/Kappa/Unified/Lakehouse

## 输入

- ProjectClassification
- WorkloadRequirementIR
- 技术候选
- 团队与成本

## 执行流程

1. **PATTERN-001** — 批处理用于高吞吐、分钟至天级 SLA、复杂历史重算和稳定报表。
2. **PATTERN-002** — 流式用于持续事件、秒/亚秒响应、状态计算、CEP 和实时特征。
3. **PATTERN-003** — Kappa 只在日志可重放、流逻辑可表达历史且保留成本可接受时选择。
4. **PATTERN-004** — Lambda 只在批层与实时层确有不同语义且双维护成本可接受时选择。
5. **PATTERN-005** — 统一流批指同一语义处理 bounded/unbounded，仍需明确运行模式与 sink 语义。
6. **PATTERN-006** — 湖仓用于开放表和多引擎历史；联邦用于跨源/过渡；Data Fabric 可叠加任意模式。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `architecture-pattern-decision.json`
- `dataflow-architecture.md`
- `pattern-adr.md`

## 验收标准

- 模式由延迟、回放、语义、运维、成本共同驱动。
- 避免无依据 Lambda 双实现。
- 批流、状态、迟到、sink 语义明确。
- 有演进和复评触发器。

## 失败、降级与恢复

关键语义不能满足时输出混合模式和验证项，不用“Unified”掩盖差异。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **PATTERN-007** — 输入和授权范围已固化为不可变快照。
- [ ] **PATTERN-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **PATTERN-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **PATTERN-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **PATTERN-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **PATTERN-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-pattern-selector/SKILL.md`, and `sha256:54241ebe4cd315868c6ee9dc92b2b3eedf35f9d5188f0aedc5bf92a99ed508da`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-project-classifier", "elmos-database-capability-registry", "elmos-database-mcda-ranker"]`. Triggers: `["已分类", "确定宏观架构", "比较 Lambda/Kappa/Unified/Lakehouse"]`. Declared outputs: `["architecture-pattern-decision.json", "dataflow-architecture.md", "pattern-adr.md"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
