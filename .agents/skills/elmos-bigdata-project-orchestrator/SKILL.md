---
name: elmos-bigdata-project-orchestrator
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-project-orchestrator. Source purpose: 把需求、选型、架构、生成、测试、修复、成本、ETA 与交付编排为可恢复的 Elmos 长任务。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-project-orchestrator/SKILL.md"
  source_sha256: "sha256:a281d0aaec9a98f65c869d6771c6cd51a3b66b22fe12a44567f642b84478c621"
  source_group: "orchestration"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据库选型与大数据项目端到端编排

## 目标

把需求、选型、架构、生成、测试、修复、成本、ETA 与交付编排为可恢复的 Elmos 长任务。

## 适用触发条件

- 一键生成完整数据库/大数据项目
- 需求到可运行仓库
- 现有数据平台升级

## 输入

- 用户需求与文件
- 目标语言/框架/部署
- 租户与任务策略
- 模型路由预算

## 执行流程

1. **MASTER-001** — 创建不可变输入快照、授权范围、tenant_id、task_id、idempotency_key 和预算。
2. **MASTER-002** — 构建可恢复 DAG，受每账号最多 3 个并发任务约束；内容寻址缓存按租户隔离。
3. **MASTER-003** — 通过模型网关为提取/规划/编码/评审/修复选择性价比模型并记录 token/费用。
4. **MASTER-004** — 执行需求 IR、画像、硬过滤、排序、多模规划、ADR 和架构基线。
5. **MASTER-005** — 生成完整仓库、管道、IaC、测试、文档、图表、runbook、样例并自动修复回归。
6. **MASTER-006** — 异步持久化节点输入/输出/状态/日志/成本/恢复点，客户端断线不终止服务端任务。
7. **MASTER-007** — 分别报告系统自主 wall-clock ETA、人类等价工作量、HITL 等待，不能混为一项。
8. **MASTER-008** — 生成 E1–E5 证据、完成度、已验证范围、未覆盖风险和交付包。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `generated-project/`
- `architecture-and-decisions/`
- `evidence-bundle/`
- `cost-and-eta.json`
- `handoff/`

## 验收标准

- 任务可暂停恢复取消重试且幂等。
- 每账号并发≤3且租户隔离。
- 仓库含代码/配置/test/IaC/docs/monitor/runbook。
- 系统 ETA 与人类工作量分开。
- 能力只按证据等级标记完成。

## 失败、降级与恢复

阶段失败时保存稳定快照、缺陷和剩余 DAG，从最近幂等节点恢复，不重复不可逆副作用。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **MASTER-009** — 输入和授权范围已固化为不可变快照。
- [ ] **MASTER-010** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **MASTER-011** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **MASTER-012** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **MASTER-013** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **MASTER-014** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-project-orchestrator/SKILL.md`, and `sha256:a281d0aaec9a98f65c869d6771c6cd51a3b66b22fe12a44567f642b84478c621`.
- Source group: `orchestration`. Dependencies: `["elmos-data-requirement-intake", "elmos-workload-profiler", "elmos-database-capability-registry", "elmos-database-constraint-filter", "elmos-database-mcda-ranker", "elmos-polyglot-persistence-planner", "elmos-data-architecture-adr", "elmos-bigdata-project-classifier", "elmos-bigdata-pattern-selector", "elmos-ingestion-connector-planner", "elmos-cdc-event-backbone", "elmos-batch-processing-generator", "elmos-stream-processing-generator", "elmos-lakehouse-generator", "elmos-warehouse-olap-serving", "elmos-federated-query-data-fabric", "elmos-data-modeling-semantic-layer", "elmos-metadata-catalog-lineage", "elmos-data-quality-observability", "elmos-orchestration-backfill-replay", "elmos-feature-store-ml-pipeline", "elmos-bigdata-api-dashboard", "elmos-bigdata-infra-deployment", "elmos-bigdata-security-governance", "elmos-bigdata-test-validation", "elmos-bigdata-performance-chaos", "elmos-bigdata-cost-autotuning", "elmos-bigdata-auto-repair", "elmos-bigdata-evidence-certification"]`. Triggers: `["一键生成完整数据库/大数据项目", "需求到可运行仓库", "现有数据平台升级"]`. Declared outputs: `["generated-project/", "architecture-and-decisions/", "evidence-bundle/", "cost-and-eta.json", "handoff/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
