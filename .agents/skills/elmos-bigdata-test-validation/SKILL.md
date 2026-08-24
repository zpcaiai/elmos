---
name: elmos-bigdata-test-validation
description: "Use for ELMOS database or Big Data work covered by elmos-bigdata-test-validation. Source purpose: 生成单元、契约、数据质量、集成、端到端、回放、恢复、安全和批流等价测试。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-test-validation/SKILL.md"
  source_sha256: "sha256:c490931fe7dd0f6d168686872d51f3c8b541f518d56b05065aba779d8bd6f586"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 大数据全栈测试与行为等价验证

## 目标

生成单元、契约、数据质量、集成、端到端、回放、恢复、安全和批流等价测试。

## 适用触发条件

- 代码已生成
- 迁移/替换
- 生产认证前

## 输入

- 需求与 DataProjectIR
- 代码
- 样例/合成数据
- SLO/策略/基线

## 执行流程

1. **TEST-001** — 从需求、契约、指标、SLO 和故障模型生成可追踪测试矩阵。
2. **TEST-002** — 执行转换单元、schema/contract compatibility、质量和业务不变量。
3. **TEST-003** — 执行 connector/broker/engine/catalog/warehouse/API/dashboard 集成。
4. **TEST-004** — 执行 batch vs stream、旧 vs 新、full vs incremental、replay vs live 差分。
5. **TEST-005** — 覆盖重复、乱序、迟到、删除、演进、回填、重试、恢复和部分失败。
6. **TEST-006** — 执行租户/权限/脱敏/导出/密钥/审计、安全和端到端 SLO/成本验证。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `tests/`
- `test-matrix.json`
- `validation-report.md`
- `defect-ledger.json`

## 验收标准

- 关键需求至少一项测试。
- 批流与迁移有差分证据。
- 失败与恢复覆盖。
- 未通过项阻止认证。

## 失败、降级与恢复

环境不能覆盖的项列为 evidence gap，不用静态检查替代运行证据。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TEST-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TEST-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TEST-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TEST-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TEST-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TEST-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-bigdata-test-validation/SKILL.md`, and `sha256:c490931fe7dd0f6d168686872d51f3c8b541f518d56b05065aba779d8bd6f586`.
- Source group: `bigdata-core`. Dependencies: `["elmos-batch-processing-generator", "elmos-stream-processing-generator", "elmos-lakehouse-generator", "elmos-warehouse-olap-serving", "elmos-data-quality-observability", "elmos-bigdata-infra-deployment", "elmos-bigdata-security-governance"]`. Triggers: `["代码已生成", "迁移/替换", "生产认证前"]`. Declared outputs: `["tests/", "test-matrix.json", "validation-report.md", "defect-ledger.json"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
