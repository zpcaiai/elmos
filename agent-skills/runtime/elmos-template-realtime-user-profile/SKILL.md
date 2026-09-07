---
name: elmos-template-realtime-user-profile
description: "Use for ELMOS database or Big Data work covered by elmos-template-realtime-user-profile. Source purpose: 生成多源身份合并、实时标签、历史画像、特征服务、低延迟 serving 和隐私治理。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-realtime-user-profile/SKILL.md"
  source_sha256: "sha256:d5cbd084897de82e627f11a031f92591e0c0817856ebcd5825b0bb9896cc2a09"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_template_realtime_user_profile"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/templates.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 实时用户画像与 Customer 360 模板

## 目标

生成多源身份合并、实时标签、历史画像、特征服务、低延迟 serving 和隐私治理。

## 适用触发条件

- 实时用户画像
- Customer 360
- 营销分群/个性化

## 输入

- 身份标识
- 事件与业务数据
- 标签特征
- 隐私同意

## 执行流程

1. **TPL360-001** — 设计 identity graph、主身份、设备合并、冲突和可撤销关联。
2. **TPL360-002** — 生成 CDC/事件采集、实时标签、离线历史回填和画像版本。
3. **TPL360-003** — 用权威历史层+低延迟 serving store 组合，明确缓存和重建。
4. **TPL360-004** — 定义标签、freshness、TTL、置信度和 owner。
5. **TPL360-005** — 实现 consent、purpose、删除传播、masking 和跨租户隔离。
6. **TPL360-006** — 验证误合并、迟到、重复、删除、实时/离线一致和查询延迟。

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

- 身份规则可解释可回滚。
- 标签有版本/freshness/owner。
- 删除/同意变化可传播。
- 实时历史可对账。

## 失败、降级与恢复

身份置信度不足时保持多候选或匿名，不强制合并。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPL360-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPL360-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPL360-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPL360-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPL360-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPL360-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-realtime-user-profile/SKILL.md`, and `sha256:d5cbd084897de82e627f11a031f92591e0c0817856ebcd5825b0bb9896cc2a09`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator", "elmos-feature-store-ml-pipeline"]`. Triggers: `["实时用户画像", "Customer 360", "营销分群/个性化"]`. Declared outputs: `["template-plan.json", "generated-project/"]`. Stable task IDs: `["TPL360-001", "TPL360-002", "TPL360-003", "TPL360-004", "TPL360-005", "TPL360-006", "TPL360-007", "TPL360-008", "TPL360-009", "TPL360-010", "TPL360-011", "TPL360-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_template_realtime_user_profile` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/templates.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
