---
name: elmos-feature-store-ml-pipeline
description: "Use for ELMOS database or Big Data work covered by elmos-feature-store-ml-pipeline. Source purpose: 生成离线/在线特征、point-in-time join、训练集、Feature Store、模型注册和推理数据路径。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-feature-store-ml-pipeline/SKILL.md"
  source_sha256: "sha256:de53d67aa759d96942251dbc6dafc675cd49171c8fc302bd3ebeaa0197af9efb"
  source_group: "bigdata-core"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 特征平台、训练数据与在线推理管道

## 目标

生成离线/在线特征、point-in-time join、训练集、Feature Store、模型注册和推理数据路径。

## 适用触发条件

- 推荐/风控/预测/ML
- 离在线特征一致
- 训练与推理数据管道

## 输入

- 标签与特征
- 历史事件实体
- 在线 SLO
- 模型接口

## 执行流程

1. **FEAST-001** — 定义 entity、event timestamp、feature view、label、freshness、owner 和版本。
2. **FEAST-002** — 生成 point-in-time correct join，防止未来信息泄漏和训练/服务偏差。
3. **FEAST-003** — 设计 offline store、online store、registry、materialization 和 feature service。
4. **FEAST-004** — 按延迟和一致性选择在线 serving store，权威历史保留在离线层。
5. **FEAST-005** — 生成批/流特征、回填、TTL、缺失和迟到修正，接入 Feast 或可替换接口。
6. **FEAST-006** — 测试质量、漂移、覆盖、freshness、离在线一致、性能和训练快照可重现性。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `feature-platform/`
- `feature-definitions/`
- `training-datasets/`
- `ml-data-tests/`

## 验收标准

- 训练集 point-in-time 正确。
- 离在线定义一致且版本化。
- 特征可追源与转换。
- 延迟/freshness/漂移有 SLO。

## 失败、降级与恢复

无法证明时间正确性时禁止用该训练集生成生产模型结论。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **FEAST-007** — 输入和授权范围已固化为不可变快照。
- [ ] **FEAST-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **FEAST-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **FEAST-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **FEAST-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **FEAST-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-feature-store-ml-pipeline/SKILL.md`, and `sha256:de53d67aa759d96942251dbc6dafc675cd49171c8fc302bd3ebeaa0197af9efb`.
- Source group: `bigdata-core`. Dependencies: `["elmos-data-modeling-semantic-layer", "elmos-orchestration-backfill-replay"]`. Triggers: `["推荐/风控/预测/ML", "离在线特征一致", "训练与推理数据管道"]`. Declared outputs: `["feature-platform/", "feature-definitions/", "training-datasets/", "ml-data-tests/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
