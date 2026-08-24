---
name: elmos-template-cdc-migration-modernization
description: "Use for ELMOS database or Big Data work covered by elmos-template-cdc-migration-modernization. Source purpose: 生成全量+增量复制、影子验证、湖仓/新库落地、渐进切流和回滚完整迁移工程。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-cdc-migration-modernization/SKILL.md"
  source_sha256: "sha256:1233ca6800df5f3e0fcbf9b58b1537a741efa9abd225576337a46ede46e2b379"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# CDC 迁移、实时复制与旧数据平台现代化模板

## 目标

生成全量+增量复制、影子验证、湖仓/新库落地、渐进切流和回滚完整迁移工程。

## 适用触发条件

- 旧数仓/数据库迁移
- 实时复制
- Hadoop/遗留 ETL 现代化

## 输入

- 源目标
- 历史与日志
- 停机一致性
- 应用报表依赖

## 执行流程

1. **TPLMIG-001** — 生成源盘点、DDL/SQL/作业/报表依赖和差异矩阵。
2. **TPLMIG-002** — 生成 snapshot、CDC、offset、水位、重放、断点和幂等。
3. **TPLMIG-003** — 建立旧新双运行、影子查询、行数/校验和/业务不变量/性能对比。
4. **TPLMIG-004** — 按表/域/租户/流量渐进切换并设置自动回滚阈值。
5. **TPLMIG-005** — 保留历史回填、schema 演进、删除传播和下游重建。
6. **TPLMIG-006** — 生成退役、归档、审计、成本和生产认证证据。

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

- 全量增量无缺口。
- 旧新行为性能有差分。
- 切流可回滚。
- 迁移可断点恢复。

## 失败、降级与恢复

不可转换语义隔离为定制适配任务，不静默丢失。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLMIG-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLMIG-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLMIG-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLMIG-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLMIG-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLMIG-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-cdc-migration-modernization/SKILL.md`, and `sha256:1233ca6800df5f3e0fcbf9b58b1537a741efa9abd225576337a46ede46e2b379`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator", "elmos-database-migration-modernization"]`. Triggers: `["旧数仓/数据库迁移", "实时复制", "Hadoop/遗留 ETL 现代化"]`. Declared outputs: `["template-plan.json", "generated-project/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
