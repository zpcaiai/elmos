---
name: elmos-bigdata-infra-deployment
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-infra-deployment. Source purpose: 生成本地开发、Docker、Kubernetes、Helm、Terraform、GitOps、存储网络和密钥部署方案。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-infra-deployment/SKILL.md"
  source_sha256: "sha256:f3c9be5330d5c8a4bf008b9b95e8edb673d8b3ed4a7b47d307703c5736f5513f"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_bigdata_infra_deployment"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 大数据基础设施、IaC 与多环境部署

## 目标

生成本地开发、Docker、Kubernetes、Helm、Terraform、GitOps、存储网络和密钥部署方案。

## 适用触发条件

- 生成可运行项目
- 云上/本地部署
- 多环境与 IaC

## 输入

- ArchitectureBaseline
- 容量成本
- 目标平台
- 安全网络

## 执行流程

1. **INFRA-001** — 生成最小本地栈和种子数据，明确与生产性能的差异。
2. **INFRA-002** — 生成 dev/test/staging/prod/dr 参数，不复制密钥或硬编码端点。
3. **INFRA-003** — 为状态组件设计存储类、反亲和、PDB、拓扑、资源、扩缩容和升级。
4. **INFRA-004** — 生成网络策略、服务身份、TLS、secrets broker、私有端点和 egress 边界。
5. **INFRA-005** — 生成 Helm/Terraform/GitOps、版本锁、可回滚部署、备份和灾备接口。
6. **INFRA-006** — 运行 lint、plan、dry-run、policy-as-code、smoke，并接入日志/指标/trace/audit/cost tag。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `infra/`
- `docker-compose.yml`
- `helm/`
- `terraform/`
- `environment-matrix.md`

## 验收标准

- 本地一键启动且标明生产差异。
- IaC 版本锁定、可审计、可回滚。
- 状态组件持久化/HA/升级完整。
- 密钥不入仓库日志。

## 失败、降级与恢复

目标平台能力未验证时生成 provider-neutral 接口和待实现适配器，不声称已部署。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **INFRA-007** — 输入和授权范围已固化为不可变快照。
- [ ] **INFRA-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **INFRA-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **INFRA-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **INFRA-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **INFRA-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-infra-deployment/SKILL.md`, and `sha256:f3c9be5330d5c8a4bf008b9b95e8edb673d8b3ed4a7b47d307703c5736f5513f`.
- Source group: `bigdata-core`. Dependencies: `["elmos-bigdata-pattern-selector", "elmos-ingestion-connector-planner", "elmos-cdc-event-backbone", "elmos-batch-processing-generator", "elmos-stream-processing-generator", "elmos-lakehouse-generator", "elmos-warehouse-olap-serving", "elmos-orchestration-backfill-replay"]`. Triggers: `["生成可运行项目", "云上/本地部署", "多环境与 IaC"]`. Declared outputs: `["infra/", "docker-compose.yml", "helm/", "terraform/", "environment-matrix.md"]`. Stable task IDs: `["INFRA-001", "INFRA-002", "INFRA-003", "INFRA-004", "INFRA-005", "INFRA-006", "INFRA-007", "INFRA-008", "INFRA-009", "INFRA-010", "INFRA-011", "INFRA-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_bigdata_infra_deployment` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
