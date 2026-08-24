---
name: elmos-database-mcda-ranker
description: "Use for ELMOS database or Big Data work covered by elmos-database-mcda-ranker. Source purpose: 对可行候选做多准则决策、Pareto 分析、复杂度惩罚和不确定性敏感性分析。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-mcda-ranker/SKILL.md"
  source_sha256: "sha256:a21371edb409bab19e54df83454cb67796356822d8ac08be0609c371032ed043"
  source_group: "database-intelligence"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 多目标数据库排序与敏感性分析

## 目标

对可行候选做多准则决策、Pareto 分析、复杂度惩罚和不确定性敏感性分析。

## 适用触发条件

- 多个可行候选
- 需要解释推荐
- 调整性能/成本/运维偏好

## 输入

- FeasibleCandidates
- 需求权重
- 基准和成本
- 组织偏好

## 执行流程

1. **RANK-001** — 规范化性能、可靠性、成本、可运维性、生态、迁移难度和锁定风险。
2. **RANK-002** — 硬约束与软偏好分离；软权重来自项目类型和用户偏好并可审计。
3. **RANK-003** — 计算加权效用、Pareto 前沿和复杂度惩罚，防止无必要的多技术堆叠。
4. **RANK-004** — 缺失数据使用区间并传播到总分置信区间。
5. **RANK-005** — 运行权重扰动/蒙特卡洛敏感性，识别排名稳健度。
6. **RANK-006** — 输出 Top-N、角色、优势、风险、置信度和重新评估阈值。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `candidate-ranking.json`
- `pareto-frontier.json`
- `sensitivity-report.md`

## 验收标准

- 分数含权重、证据、区间和敏感性。
- 低稳健推荐被显式标记。
- 运维复杂度进入惩罚。
- 用户可重放调整权重。

## 失败、降级与恢复

证据不足时只输出候选区间和验证计划，不给伪确定的唯一最佳。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **RANK-007** — 输入和授权范围已固化为不可变快照。
- [ ] **RANK-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **RANK-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **RANK-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **RANK-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **RANK-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-database-mcda-ranker/SKILL.md`, and `sha256:a21371edb409bab19e54df83454cb67796356822d8ac08be0609c371032ed043`.
- Source group: `database-intelligence`. Dependencies: `["elmos-database-constraint-filter"]`. Triggers: `["多个可行候选", "需要解释推荐", "调整性能/成本/运维偏好"]`. Declared outputs: `["candidate-ranking.json", "pareto-frontier.json", "sensitivity-report.md"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
