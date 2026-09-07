---
name: elmos-data-requirement-intake
description: "Use for ELMOS database or Big Data work covered by elmos-data-requirement-intake. Source purpose: 把自然语言需求、PRD、现有仓库、样例数据和部署约束规范化为可验证的数据工作负载需求 IR。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-data-requirement-intake/SKILL.md"
  source_sha256: "sha256:f055eb74a7e7b357b8cf80ff9da36a2c469ec8077e508e206c373ddc116f4556"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_data_requirement_intake"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据需求摄取与 Workload Requirement IR

## 目标

把自然语言需求、PRD、现有仓库、样例数据和部署约束规范化为可验证的数据工作负载需求 IR。

## 适用触发条件

- 需要选择数据库
- 需要设计数据平台
- 收到数据项目需求或现有系统资料

## 输入

- 业务需求、PRD、代码与配置
- 数据源和消费者清单
- SLO/RPO/RTO
- 部署、预算、合规与租户约束

## 执行流程

1. **REQ-001** — 识别业务域、数据生产者、消费者、实体、事件、数据所有权和租户边界。
2. **REQ-002** — 量化 Volume、Velocity、Variety、Veracity、Value，记录当前值、峰值、增长率和置信区间。
3. **REQ-003** — 提取读写模式、事务边界、查询形态、热点、保留、归档和删除要求。
4. **REQ-004** — 显式记录 P50/P95/P99、吞吐、可用性、RPO、RTO、freshness、一致性和隔离级别。
5. **REQ-005** — 识别 PII、驻留、审计、预算、部署和运维约束；未知值标为 unknown/range/assumption。
6. **REQ-006** — 按 JSON Schema 输出 IR、冲突、缺口、保守假设和下一阶段输入。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `workload-requirements.json`
- `source-inventory.json`
- `assumptions-and-gaps.md`

## 验收标准

- 关键 SLO 为值、范围或 unknown，不能静默缺失。
- 来源、消费者、owner 和租户边界可追踪。
- 敏感值不进入生成物。
- 输出通过 schema 校验。

## 失败、降级与恢复

资料不足时生成带置信度的部分 IR 和阻断项，不得凭空补造规模、法规或预算。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **REQ-007** — 输入和授权范围已固化为不可变快照。
- [ ] **REQ-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **REQ-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **REQ-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **REQ-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **REQ-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-data-requirement-intake/SKILL.md`, and `sha256:f055eb74a7e7b357b8cf80ff9da36a2c469ec8077e508e206c373ddc116f4556`.
- Source group: `database-intelligence`. Dependencies: `[]`. Triggers: `["需要选择数据库", "需要设计数据平台", "收到数据项目需求或现有系统资料"]`. Declared outputs: `["workload-requirements.json", "source-inventory.json", "assumptions-and-gaps.md"]`. Stable task IDs: `["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005", "REQ-006", "REQ-007", "REQ-008", "REQ-009", "REQ-010", "REQ-011", "REQ-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_data_requirement_intake` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
