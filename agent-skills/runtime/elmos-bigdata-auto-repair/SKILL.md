---
name: elmos-bigdata-auto-repair
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-auto-repair. Source purpose: 从告警、血缘、运行和变更证据定位根因，执行低风险修复、验证与回滚。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-auto-repair/SKILL.md"
  source_sha256: "sha256:8b288354553d3863c7b3daee69acc294794e85d109a0f066b5e003047393da12"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 大数据故障诊断与受控自动修复

## 目标

从告警、血缘、运行和变更证据定位根因，执行低风险修复、验证与回滚。

## 适用触发条件

- 质量失败
- 性能退化
- 需要自动修复

## 输入

- 告警/日志/指标/trace/lineage
- 最近变更
- runbook/test
- 审批策略

## 执行流程

1. **REPAIR-001** — 关联 Data SLO、任务、组件、版本、schema、权限、成本和下游影响。
2. **REPAIR-002** — 按证据、时间、变更和反事实测试排序根因候选。
3. **REPAIR-003** — 优先无副作用诊断与低风险动作：幂等重试、扩容、切副本、隔离毒数据。
4. **REPAIR-004** — 回填、schema 回退、配置、切流和数据修正按风险设置审批。
5. **REPAIR-005** — 修复前创建快照/savepoint/备份，在 shadow/canary 验证。
6. **REPAIR-006** — 运行针对性与全量回归，确认正确性、SLO、成本、安全后逐步扩大。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `incident-bundle/`
- `root-cause-ranking.json`
- `repair-plan.json`
- `repair-evidence.md`

## 验收标准

- 根因与证据可追踪。
- 自动动作幂等可回滚且分级。
- 修复后回归。
- 高风险数据修改需审批。

## 失败、降级与恢复

无法证明安全时停止自动动作，保留诊断、隔离和人工决策包。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **REPAIR-007** — 输入和授权范围已固化为不可变快照。
- [ ] **REPAIR-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **REPAIR-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **REPAIR-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **REPAIR-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **REPAIR-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-auto-repair/SKILL.md`, and `sha256:8b288354553d3863c7b3daee69acc294794e85d109a0f066b5e003047393da12`.
- Source group: `bigdata-core`. Dependencies: `["elmos-data-quality-observability", "elmos-orchestration-backfill-replay", "elmos-bigdata-test-validation", "elmos-bigdata-performance-chaos", "elmos-bigdata-cost-autotuning"]`. Triggers: `["质量失败", "性能退化", "需要自动修复"]`. Declared outputs: `["incident-bundle/", "root-cause-ranking.json", "repair-plan.json", "repair-evidence.md"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
