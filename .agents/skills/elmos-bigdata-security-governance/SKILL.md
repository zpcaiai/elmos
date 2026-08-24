---
name: elmos-bigdata-security-governance
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-security-governance. Source purpose: 跨湖、仓、流、消息、目录、BI 和 ML 实施分类、授权、脱敏、保留、审计和数据治理。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-security-governance/SKILL.md"
  source_sha256: "sha256:d9d67c94e5da147b2c74af27f37438143db400eb9c07f276ad393891c8657e27"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 大数据安全、治理、生命周期与合规

## 目标

跨湖、仓、流、消息、目录、BI 和 ML 实施分类、授权、脱敏、保留、审计和数据治理。

## 适用触发条件

- 企业大数据平台
- 敏感/受监管数据
- 数据产品治理

## 输入

- 数据分类
- Lineage/Catalog
- 身份租户
- 法规政策

## 执行流程

1. **GOV-001** — 建立组织级数据分类与自动标签，覆盖 source/topic/bucket/table/column/feature/dashboard/export。
2. **GOV-002** — 实施 RBAC/ABAC、purpose-based access、row/column policy、masking、tokenization。
3. **GOV-003** — 定义 consent、retention、legal hold、right-to-delete、归档和可验证删除传播。
4. **GOV-004** — 设计跨区域/跨云/跨域驻留、传输、egress 和审批。
5. **GOV-005** — 记录访问、变更、导出、模型使用、策略决策和管理员行为。
6. **GOV-006** — 建立 owner/steward、数据产品 SLA、认证/弃用/例外/复审和政策即代码测试。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `governance/`
- `classification-policy.json`
- `retention-policy.json`
- `access-review.md`

## 验收标准

- 策略覆盖复制和派生数据。
- 删除/保留/授权沿 lineage 传播。
- 权限复审并检测漂移。
- 合规结论绑定证据范围。

## 失败、降级与恢复

法规映射未验证时标记需合规确认，技术上先采用更严格最小权限。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **GOV-007** — 输入和授权范围已固化为不可变快照。
- [ ] **GOV-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **GOV-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **GOV-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **GOV-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **GOV-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-security-governance/SKILL.md`, and `sha256:d9d67c94e5da147b2c74af27f37438143db400eb9c07f276ad393891c8657e27`.
- Source group: `bigdata-core`. Dependencies: `["elmos-database-security-multitenancy", "elmos-metadata-catalog-lineage", "elmos-bigdata-infra-deployment"]`. Triggers: `["企业大数据平台", "敏感/受监管数据", "数据产品治理"]`. Declared outputs: `["governance/", "classification-policy.json", "retention-policy.json", "access-review.md"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
