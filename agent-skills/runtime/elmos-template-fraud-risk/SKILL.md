---
name: elmos-template-fraud-risk
description: "Use for ELMOS database or Big Data work covered by elmos-template-fraud-risk. Source purpose: 生成实时特征、规则、图关系、模型评分、决策审计、回放和低延迟高可用风控平台。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-fraud-risk/SKILL.md"
  source_sha256: "sha256:139f55546c30ff58d128e403bf82ff57dc6cbca824a4b5da47210b51d9135746"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 实时风控与反欺诈数据项目模板

## 目标

生成实时特征、规则、图关系、模型评分、决策审计、回放和低延迟高可用风控平台。

## 适用触发条件

- 反欺诈/交易风控
- 规则+模型+图谱
- 高审计

## 输入

- 交易身份事件
- 规则模型
- 决策延迟
- 误报漏报审计

## 执行流程

1. **TPLRISK-001** — 生成交易、身份、设备、账户、关系和决策事件契约。
2. **TPLRISK-002** — 设计实时窗口、velocity、黑白名单、图特征和历史特征。
3. **TPLRISK-003** — 组合规则引擎、模型评分、图查询和人工复核。
4. **TPLRISK-004** — 记录每次决策输入版本、规则、模型、解释和结果。
5. **TPLRISK-005** — 生成低延迟 serving、降级规则、熔断和高可用。
6. **TPLRISK-006** — 验证重放一致、时间穿越、重复交易、热点实体、回滚和权限。

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

- 决策可重放审计。
- 规则/模型可回滚。
- 延迟可用性有证据。
- 高风险变更需审批。

## 失败、降级与恢复

模型或图服务不可用时按批准的保守规则降级并记录影响。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLRISK-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLRISK-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLRISK-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLRISK-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLRISK-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLRISK-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-fraud-risk/SKILL.md`, and `sha256:139f55546c30ff58d128e403bf82ff57dc6cbca824a4b5da47210b51d9135746`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator", "elmos-feature-store-ml-pipeline"]`. Triggers: `["反欺诈/交易风控", "规则+模型+图谱", "高审计"]`. Declared outputs: `["template-plan.json", "generated-project/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
