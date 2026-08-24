---
name: elmos-database-security-multitenancy
description: "Use for ELMOS database or Big Data work covered by elmos-database-security-multitenancy. Source purpose: 设计身份、授权、租户隔离、加密、审计、密钥、脱敏和安全运维边界。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-security-multitenancy/SKILL.md"
  source_sha256: "sha256:c00d6f2a8a91517238612c8928045f2fd3b4f630907cd97448dfe07f783caf25"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据库安全与多租户隔离

## 目标

设计身份、授权、租户隔离、加密、审计、密钥、脱敏和安全运维边界。

## 适用触发条件

- 多租户系统
- 敏感数据
- 生产数据库设计

## 输入

- 租户模型与分类
- PersistencePortfolio
- 身份权限
- 合规审计

## 执行流程

1. **DBSEC-001** — 比较数据库/schema/table/row/column/encryption-domain 隔离级别。
2. **DBSEC-002** — 按租户规模、噪声邻居、迁移和成本选择共享库、独立 schema、独立库或混合模式。
3. **DBSEC-003** — 定义服务身份、最小权限、短期凭据、轮换、break-glass 和 secrets broker。
4. **DBSEC-004** — 实现传输、静态、备份和字段级加密、tokenization、masking。
5. **DBSEC-005** — 定义 RLS/ABAC/RBAC、管理面/数据面隔离和跨租户查询禁止规则。
6. **DBSEC-006** — 验证注入、越权、旁路连接、备份泄漏、缓存和统计侧信道。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `database-security-model.md`
- `tenant-isolation-policy.json`
- `access-matrix.csv`
- `security-test-plan.json`

## 验收标准

- 跨租户访问在应用、数据库、测试层均阻断。
- 凭据不进入代码、日志、缓存或模型上下文。
- 高权限操作可审计。
- 覆盖正常与旁路路径。

## 失败、降级与恢复

无法证明隔离时选择更强隔离或阻止生产认证，不以应用过滤替代数据库边界。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **DBSEC-007** — 输入和授权范围已固化为不可变快照。
- [ ] **DBSEC-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **DBSEC-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **DBSEC-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **DBSEC-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **DBSEC-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-security-multitenancy/SKILL.md`, and `sha256:c00d6f2a8a91517238612c8928045f2fd3b4f630907cd97448dfe07f783caf25`.
- Source group: `database-intelligence`. Dependencies: `["elmos-data-requirement-intake", "elmos-polyglot-persistence-planner"]`. Triggers: `["多租户系统", "敏感数据", "生产数据库设计"]`. Declared outputs: `["database-security-model.md", "tenant-isolation-policy.json", "access-matrix.csv", "security-test-plan.json"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
