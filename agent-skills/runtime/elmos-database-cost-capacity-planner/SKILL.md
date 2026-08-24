---
name: elmos-database-cost-capacity-planner
description: "Use for ELMOS database or Big Data work covered by elmos-database-cost-capacity-planner. Source purpose: 根据增长、SLO、复制、保留和运维模型计算容量、弹性范围与三年 TCO。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-cost-capacity-planner/SKILL.md"
  source_sha256: "sha256:7bd51dbff0e019c702c3a9f3d5d73115cd94dfc8023522423c4e3e45db6e038f"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_database_cost_capacity_planner"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 容量、TCO 与成本边界规划

## 目标

根据增长、SLO、复制、保留和运维模型计算容量、弹性范围与三年 TCO。

## 适用触发条件

- 需要预算或容量
- 比较自建与托管
- 生成生产规格

## 输入

- WorkloadProfile
- BenchmarkResults
- 价格清单
- 增长与保留

## 执行流程

1. **COST-001** — 计算热/温/冷数据及副本、索引、WAL、快照、临时空间和压缩后的容量。
2. **COST-002** — 按峰值、突发、重建、compaction、backfill、故障降级计算 CPU/内存/磁盘/网络。
3. **COST-003** — 区分 dev/test/staging/prod/dr，避免单环境成本冒充总成本。
4. **COST-004** — 比较托管、自建、云、混合和本地的人力、许可证、流量与机会成本。
5. **COST-005** — 建立基线、增长、峰值、灾难场景，计算每百万事件、每 TB、每查询、每租户成本。
6. **COST-006** — 设置预算 guardrail、自动扩缩上下限、异常告警和价格 as-of 时间。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `capacity-plan.json`
- `tco-scenarios.json`
- `cost-risk-report.md`

## 验收标准

- 容量含复制、索引、临时空间、备份和余量。
- TCO 含基础设施、软件、流量和运维。
- 结果含区间与敏感变量。
- 价格和基准有 as-of。

## 失败、降级与恢复

缺少价格或基准时输出参数化公式，不生成虚假金额。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **COST-007** — 输入和授权范围已固化为不可变快照。
- [ ] **COST-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **COST-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **COST-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **COST-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **COST-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-cost-capacity-planner/SKILL.md`, and `sha256:7bd51dbff0e019c702c3a9f3d5d73115cd94dfc8023522423c4e3e45db6e038f`.
- Source group: `database-intelligence`. Dependencies: `["elmos-database-mcda-ranker", "elmos-database-benchmark-harness"]`. Triggers: `["需要预算或容量", "比较自建与托管", "生成生产规格"]`. Declared outputs: `["capacity-plan.json", "tco-scenarios.json", "cost-risk-report.md"]`. Stable task IDs: `["COST-001", "COST-002", "COST-003", "COST-004", "COST-005", "COST-006", "COST-007", "COST-008", "COST-009", "COST-010", "COST-011", "COST-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_database_cost_capacity_planner` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/database_intelligence.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
