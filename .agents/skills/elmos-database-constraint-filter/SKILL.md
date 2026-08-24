---
name: elmos-database-constraint-filter
description: "Use for ELMOS database or Big Data work covered by elmos-database-constraint-filter. Source purpose: 先用硬约束、兼容性和政策规则淘汰不可行候选，避免软评分掩盖不合格项。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-constraint-filter/SKILL.md"
  source_sha256: "sha256:5a3c579f5cc8766bbb2bdbc4b2c429008968604a7ec3462896fa1a6ec2a0f4cb"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 数据库硬约束过滤器

## 目标

先用硬约束、兼容性和政策规则淘汰不可行候选，避免软评分掩盖不合格项。

## 适用触发条件

- 已获得需求 IR 和注册表
- 需要候选集
- 存在合规或部署硬约束

## 输入

- WorkloadRequirementIR
- DataProfile
- Capability Registry
- 组织政策

## 执行流程

1. **FILTER-001** — 把驻留、许可证、部署、语言、事务、一致性、RPO/RTO 转为硬约束。
2. **FILTER-002** — 把容量、对象限制、分区键、索引、状态大小和类型兼容转为技术约束。
3. **FILTER-003** — 按 system-of-record、cache、search、analytics、lakehouse、graph、vector 分角色过滤。
4. **FILTER-004** — 用规则引擎或 CP-SAT 求解可行组合，而不是只选单个产品。
5. **FILTER-005** — 为淘汰项输出约束、证据和可解除条件；无解时生成最小冲突集合。
6. **FILTER-006** — 固定输入、规则和注册表快照，保证结果可重放。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `feasible-candidates.json`
- `rejected-candidates.json`
- `constraint-proof.json`

## 验收标准

- 所有候选通过硬约束。
- 拒绝项有具体原因。
- 无解时不静默放宽约束。
- 结果对同一快照确定。

## 失败、降级与恢复

无解时生成降级候选，但不得违反安全、合规或数据完整性要求。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **FILTER-007** — 输入和授权范围已固化为不可变快照。
- [ ] **FILTER-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **FILTER-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **FILTER-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **FILTER-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **FILTER-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-constraint-filter/SKILL.md`, and `sha256:5a3c579f5cc8766bbb2bdbc4b2c429008968604a7ec3462896fa1a6ec2a0f4cb`.
- Source group: `database-intelligence`. Dependencies: `["elmos-data-requirement-intake", "elmos-workload-profiler", "elmos-database-capability-registry"]`. Triggers: `["已获得需求 IR 和注册表", "需要候选集", "存在合规或部署硬约束"]`. Declared outputs: `["feasible-candidates.json", "rejected-candidates.json", "constraint-proof.json"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
