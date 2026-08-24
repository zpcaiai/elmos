---
name: elmos-bigdata-performance-chaos
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-performance-chaos. Source purpose: 验证峰值、倾斜、背压、长尾、扩缩容、组件故障和灾难恢复下的平台行为。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-performance-chaos/SKILL.md"
  source_sha256: "sha256:7d22c1b87d4a5cdf84168d866b7f7306b7eaf8544db368d9d41d79a0e2987b2f"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  repository_runtime_binding: "BOUNDED_PLAN_SKELETON"
  repository_handler_id: "handle_elmos_bigdata_performance_chaos"
  repository_handler_path: "engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py"
  repository_handler_runtime_evidence: "NOT_RUN"
  whole_skill_implementation_effect: "NONE"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 性能、压力、容量与混沌验证

## 目标

验证峰值、倾斜、背压、长尾、扩缩容、组件故障和灾难恢复下的平台行为。

## 适用触发条件

- 性能容量验收
- 生产前压力
- 容错恢复验证

## 输入

- SLO
- CapacityPlan
- 部署环境
- 工作负载/故障模型

## 执行流程

1. **CHAOS-001** — 建立 steady、peak、burst、growth、backfill、disaster 六类负载。
2. **CHAOS-002** — 注入热点 key、倾斜、大消息、小文件、慢 sink、积压和高并发查询。
3. **CHAOS-003** — 注入 broker/worker/coordinator/catalog/object-store/network/disk/credential 故障。
4. **CHAOS-004** — 测量 time-to-insight、P95/P99、lag、backpressure、checkpoint、恢复和正确性。
5. **CHAOS-005** — 验证扩缩容、rebalance、state migration、compaction、限流与重试风暴。
6. **CHAOS-006** — 确定安全容量包络、熔断、降级、自动扩缩阈值和回归基线。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `performance-tests/`
- `chaos-scenarios.json`
- `capacity-envelope.json`
- `performance-report.md`

## 验收标准

- SLO 在容量包络内有证据。
- 故障期间正确性和恢复被验证。
- noisy-neighbor/重试风暴覆盖。
- 报告含环境版本原始指标。

## 失败、降级与恢复

测试环境差异大时只给趋势与风险，不外推绝对生产容量。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **CHAOS-007** — 输入和授权范围已固化为不可变快照。
- [ ] **CHAOS-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **CHAOS-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **CHAOS-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **CHAOS-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **CHAOS-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-performance-chaos/SKILL.md`, and `sha256:7d22c1b87d4a5cdf84168d866b7f7306b7eaf8544db368d9d41d79a0e2987b2f`.
- Source group: `bigdata-core`. Dependencies: `["elmos-database-benchmark-harness", "elmos-database-cost-capacity-planner", "elmos-bigdata-infra-deployment", "elmos-bigdata-test-validation"]`. Triggers: `["性能容量验收", "生产前压力", "容错恢复验证"]`. Declared outputs: `["performance-tests/", "chaos-scenarios.json", "capacity-envelope.json", "performance-report.md"]`. Stable task IDs: `["CHAOS-001", "CHAOS-002", "CHAOS-003", "CHAOS-004", "CHAOS-005", "CHAOS-006", "CHAOS-007", "CHAOS-008", "CHAOS-009", "CHAOS-010", "CHAOS-011", "CHAOS-012"]`.
- This normalized Skill is installed and invocable. The repository binds `handle_elmos_bigdata_performance_chaos` in `engines/database-bigdata-engine/src/elmos_database_bigdata/handlers/bigdata_core.py` as a bounded plan-skeleton entry point; the reviewed code declares no database, provider, network, deployment, benchmark, mutation, or certification operation.
- The plan skeleton makes every stable task ID, declared output, and missing evidence gate machine-readable. It does not implement the whole Skill, execute any source task, or generate the declared artifacts. `skill_implementation_state` therefore remains `DECLARED`, all runtime evidence remains `NOT_RUN`, and its whole-Skill implementation effect is `NONE`.
- The source package itself contains no per-Skill runtime handler, provider adapter, or project-generation assets; repository planner code is independently owned and must not execute package code.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant/project/actor/idempotency values accepted by the skeleton are caller-asserted and unverified. They are digest-bound only; no authentication binding, authorization decision, or replay store exists. Tenant, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
