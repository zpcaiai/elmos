---
name: elmos-bigdata-project-classifier
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-project-classifier. Source purpose: 从生命周期、架构模式、业务场景、存储范式和组织模型多维识别项目类型。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-project-classifier/SKILL.md"
  source_sha256: "sha256:87c6df69ff880b0aa1e8d04ea82c87fc2e022c1381d39ef5206c25ccd8442557"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_bigdata_project_classifier"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 大数据项目类型与价值流分类

## 目标

从生命周期、架构模式、业务场景、存储范式和组织模型多维识别项目类型。

## 适用触发条件

- 生成大数据项目
- 需求未指定技术
- 判断批流湖仓类型

## 输入

- WorkloadRequirementIR
- DataProfile
- 业务目标
- 平台边界

## 执行流程

1. **CLASS-001** — 按采集、存储、处理、治理、服务、可视化和反馈闭环拆解价值流。
2. **CLASS-002** — 识别离线数仓、实时计算、推荐、画像、风控、IoT、日志、搜索、ML、治理场景。
3. **CLASS-003** — 识别 OLTP、OLAP、HTAP、湖、仓、湖仓、联邦和派生存储角色。
4. **CLASS-004** — 识别 bounded/unbounded、事件时间、低延迟、回放和批流一致性。
5. **CLASS-005** — 识别集中平台、Data Mesh 领域所有权和 Data Fabric 元数据覆盖层。
6. **CLASS-006** — 允许多类型组合，输出主/次类型、组合原因和必需/可选/禁止能力。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `bigdata-project-classification.json`
- `scenario-map.md`
- `capability-needs.json`

## 验收标准

- 覆盖生命周期、架构、场景、存储、组织五维。
- Data Fabric 不被误当单一存储。
- 多场景有主次和边界。
- 结果可驱动模式选择。

## 失败、降级与恢复

目标不明确时基于 SLO 与数据流输出多场景候选，不强行归为单一类型。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **CLASS-007** — 输入和授权范围已固化为不可变快照。
- [ ] **CLASS-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **CLASS-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **CLASS-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **CLASS-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **CLASS-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-project-classifier/SKILL.md`, and `sha256:87c6df69ff880b0aa1e8d04ea82c87fc2e022c1381d39ef5206c25ccd8442557`.
- Source group: `bigdata-core`. Dependencies: `["elmos-data-requirement-intake", "elmos-workload-profiler"]`. Triggers: `["生成大数据项目", "需求未指定技术", "判断批流湖仓类型"]`. Declared outputs: `["bigdata-project-classification.json", "scenario-map.md", "capability-needs.json"]`. Stable task IDs: `["CLASS-001", "CLASS-002", "CLASS-003", "CLASS-004", "CLASS-005", "CLASS-006", "CLASS-007", "CLASS-008", "CLASS-009", "CLASS-010", "CLASS-011", "CLASS-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_bigdata_project_classifier` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
