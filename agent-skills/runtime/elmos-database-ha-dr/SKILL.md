---
name: elmos-database-ha-dr
description: "Use for ELMOS database or Big Data work covered by elmos-database-ha-dr. Source purpose: 生成 HA 拓扑、备份、PITR、跨区域灾备、恢复演练与完整性验证。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-ha-dr/SKILL.md"
  source_sha256: "sha256:c8fee0eb1d6f790e98089bdae75f43c51ab382060e2e331b6155d0c58502e2e7"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据库高可用、备份与灾难恢复

## 目标

生成 HA 拓扑、备份、PITR、跨区域灾备、恢复演练与完整性验证。

## 适用触发条件

- 生产设计
- 存在 RPO/RTO
- 备份恢复或跨区容灾

## 输入

- PersistencePortfolio
- RPO/RTO
- 区域与故障模型
- 成本边界

## 执行流程

1. **HADR-001** — 为每个数据角色定义副本、共识、故障转移和读写路由语义。
2. **HADR-002** — 区分同 AZ、跨 AZ、跨区域、离线备份和逻辑错误恢复。
3. **HADR-003** — 设计全量、增量、WAL/binlog、快照、PITR、对象锁和备份加密。
4. **HADR-004** — 定义 failover/failback、split-brain 防护、fencing 和连接切换。
5. **HADR-005** — 定期 restore drill，验证行数、校验和、业务不变量和下游重建。
6. **HADR-006** — 为缓存、搜索、湖仓元数据和流状态分别生成恢复 runbook。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `ha-dr-topology.md`
- `backup-policy.json`
- `restore-runbook.md`
- `dr-test-plan.json`

## 验收标准

- 每个关键存储有可执行恢复路径。
- RPO/RTO 通过演练证据验证。
- 覆盖误删、区域故障、凭据泄漏。
- 恢复后校验数据和下游。

## 失败、降级与恢复

未完成恢复演练前不得声称满足 RPO/RTO，只能标记设计值。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **HADR-007** — 输入和授权范围已固化为不可变快照。
- [ ] **HADR-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **HADR-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **HADR-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **HADR-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **HADR-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-ha-dr/SKILL.md`, and `sha256:c8fee0eb1d6f790e98089bdae75f43c51ab382060e2e331b6155d0c58502e2e7`.
- Source group: `database-intelligence`. Dependencies: `["elmos-polyglot-persistence-planner"]`. Triggers: `["生产设计", "存在 RPO/RTO", "备份恢复或跨区容灾"]`. Declared outputs: `["ha-dr-topology.md", "backup-policy.json", "restore-runbook.md", "dr-test-plan.json"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
