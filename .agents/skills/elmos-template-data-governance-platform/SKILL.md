---
name: elmos-template-data-governance-platform
description: "Use for ELMOS database or Big Data work covered by elmos-template-data-governance-platform. Source purpose: 生成元数据采集、目录、术语、所有权、质量、血缘、权限、数据产品和治理工作流。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-data-governance-platform/SKILL.md"
  source_sha256: "sha256:0ff46d62cc3de994d182586acac3b3cca182122e7a578215e3888df8ecdb740e"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 企业数据目录、质量、血缘与治理平台模板

## 目标

生成元数据采集、目录、术语、所有权、质量、血缘、权限、数据产品和治理工作流。

## 适用触发条件

- 数据治理平台
- Data Catalog/Data Fabric
- 数据产品/自助分析

## 输入

- 数据源组织
- 治理政策
- 目录血缘质量
- 身份系统

## 执行流程

1. **TPLGOV-001** — 生成 metadata ingestion、catalog、lineage、quality、glossary、ownership 服务。
2. **TPLGOV-002** — 建立 domain、data product、owner、steward、certification、deprecation。
3. **TPLGOV-003** — 接入数据库、湖仓、消息、管道、BI、ML、API 元数据。
4. **TPLGOV-004** — 生成 ABAC/RBAC、分类、masking、access request 和审计。
5. **TPLGOV-005** — 生成 SLO、质量、影响分析、变更通知和治理 dashboard。
6. **TPLGOV-006** — 验证元数据覆盖、血缘准确、权限和治理工作流。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `template-plan.json`
- `generated-project/`

## 验收标准

- 核心资产有 owner/认证。
- 血缘质量覆盖可量化。
- 权限请求可审计。
- Fabric 不绑定单一存储。

## 失败、降级与恢复

自动采集不足时显示缺口，不用空目录冒充治理完成。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLGOV-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLGOV-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLGOV-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLGOV-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLGOV-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLGOV-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-data-governance-platform/SKILL.md`, and `sha256:0ff46d62cc3de994d182586acac3b3cca182122e7a578215e3888df8ecdb740e`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator"]`. Triggers: `["数据治理平台", "Data Catalog/Data Fabric", "数据产品/自助分析"]`. Declared outputs: `["template-plan.json", "generated-project/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
