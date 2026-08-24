---
name: elmos-template-log-observability
description: "Use for ELMOS database or Big Data work covered by elmos-template-log-observability. Source purpose: 生成高吞吐遥测采集、列式分析、保留分层、查询、告警和跨信号关联项目。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-log-observability/SKILL.md"
  source_sha256: "sha256:c7ca5cab14125a91d6ccd0d70e592a6e85968ff7b389c7734c8958ed3116f4f2"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 日志、指标、Trace 与安全分析模板

## 目标

生成高吞吐遥测采集、列式分析、保留分层、查询、告警和跨信号关联项目。

## 适用触发条件

- 日志平台
- 可观测性数据湖
- 安全分析/SIEM

## 输入

- 遥测源
- 摄取量保留
- 查询告警
- 敏感字段

## 执行流程

1. **TPLOBS-001** — 生成 OpenTelemetry/agent→buffer→stream→列式 OLAP/湖仓数据流。
2. **TPLOBS-002** — 规范 service、trace、span、host、tenant、severity 字段。
3. **TPLOBS-003** — 设计采样、动态采样、压缩、索引、分区、TTL 和冷热归档。
4. **TPLOBS-004** — 实现敏感字段过滤、tokenization、租户隔离和审计。
5. **TPLOBS-005** — 生成跨日志/指标/trace 查询、dashboard、告警和 incident link。
6. **TPLOBS-006** — 验证峰值摄取、查询并发、丢包、积压、成本和恢复。

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

- 峰值遥测不压垮业务。
- 保留/采样可解释。
- 跨信号关联可用。
- 敏感日志受控。

## 失败、降级与恢复

成本超界时优先动态采样和冷热分层，不静默丢高价值安全事件。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLOBS-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLOBS-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLOBS-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLOBS-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLOBS-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLOBS-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-log-observability/SKILL.md`, and `sha256:c7ca5cab14125a91d6ccd0d70e592a6e85968ff7b389c7734c8958ed3116f4f2`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator"]`. Triggers: `["日志平台", "可观测性数据湖", "安全分析/SIEM"]`. Declared outputs: `["template-plan.json", "generated-project/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
