---
name: elmos-bigdata-cost-autotuning
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-cost-autotuning. Source purpose: 基于运行证据优化计算、存储、文件、分区、查询、缓存、保留和调度，同时守住 SLO。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-cost-autotuning/SKILL.md"
  source_sha256: "sha256:d4f68966a41d2927496707540cb51d5c834cb300ce28934646ddd776311c43cd"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_bigdata_cost_autotuning"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 大数据成本优化与安全自动调优

## 目标

基于运行证据优化计算、存储、文件、分区、查询、缓存、保留和调度，同时守住 SLO。

## 适用触发条件

- 成本过高或性能低
- 自适应策略
- 长期优化

## 输入

- 成本/性能/质量指标
- 查询作业画像
- 容量包络
- 风险策略

## 执行流程

1. **OPT-001** — 分解计算、存储、网络、日志、备份、空闲、许可证和运维成本。
2. **OPT-002** — 识别 over-provision、重扫、低效 join、无效索引、过多副本、小文件和过长保留。
3. **OPT-003** — 生成 partition/sort/cluster/MV/cache/compaction/pushdown 优化。
4. **OPT-004** — 优化 autoscaling、spot、资源池、调度窗口和 workload priority。
5. **OPT-005** — 用 canary/shadow 验证，设置正确性和 SLO guardrail、上下限、冷却和回滚。
6. **OPT-006** — 记录基线、收益、置信度、潜在回归，并将验证结果版本化反馈选择器。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `optimization-plan.json`
- `tuning-policies/`
- `before-after-report.md`
- `rollback-thresholds.json`

## 验收标准

- 每项优化有基线/假设/验证/收益/回滚。
- 降本不牺牲正确性或关键 SLO。
- 自动调优受边界控制。
- 结果可复现回退。

## 失败、降级与恢复

证据不足时只生成实验建议，不自动修改生产配置。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **OPT-007** — 输入和授权范围已固化为不可变快照。
- [ ] **OPT-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **OPT-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **OPT-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **OPT-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **OPT-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-cost-autotuning/SKILL.md`, and `sha256:d4f68966a41d2927496707540cb51d5c834cb300ce28934646ddd776311c43cd`.
- Source group: `bigdata-core`. Dependencies: `["elmos-database-cost-capacity-planner", "elmos-data-quality-observability", "elmos-bigdata-performance-chaos"]`. Triggers: `["成本过高或性能低", "自适应策略", "长期优化"]`. Declared outputs: `["optimization-plan.json", "tuning-policies/", "before-after-report.md", "rollback-thresholds.json"]`. Stable task IDs: `["OPT-001", "OPT-002", "OPT-003", "OPT-004", "OPT-005", "OPT-006", "OPT-007", "OPT-008", "OPT-009", "OPT-010", "OPT-011", "OPT-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_bigdata_cost_autotuning` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
