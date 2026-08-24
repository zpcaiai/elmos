---
name: elmos-template-vector-knowledge-analytics
description: "Use for ELMOS database or Big Data work covered by elmos-template-vector-knowledge-analytics. Source purpose: 生成文档/多模态采集、解析、分块、嵌入、向量+关键词混检、元数据湖仓和评测。 Preserve exact data, tenant, runtime, and evidence boundaries; catalog entries and generated plans are not production proof."
metadata:
  source_package: "elmos-database-bigdata-skills"
  source_version: "1.0.0"
  source_path: "skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-vector-knowledge-analytics/SKILL.md"
  source_sha256: "sha256:78cae274aacd0fc3e8d6c3f3a78b53883e8bed25239f8c952b88b1de4d0eea2c"
  source_group: "bigdata-templates"
  normalized_namespace: "elmos-database-bigdata-v1"
  installation_state: "INSTALLED"
  skill_implementation_state: "DECLARED"
  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"
  provider_runtime_evidence: "NOT_RUN"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# 向量检索、知识与分析数据平台模板

## 目标

生成文档/多模态采集、解析、分块、嵌入、向量+关键词混检、元数据湖仓和评测。

## 适用触发条件

- RAG/知识库/语义检索
- 向量数据库选型
- 多模态知识分析

## 输入

- 文档多模态源
- 检索场景
- 更新删除权限
- 质量延迟 SLO

## 执行流程

1. **TPLVEC-001** — 生成 document/version/chunk/embedding/ACL/source-citation/delete 事件契约。
2. **TPLVEC-002** — 选择 pgvector、Milvus、Qdrant、Weaviate 或搜索引擎向量能力，并保留关键词检索。
3. **TPLVEC-003** — 设计解析、分块、去重、embedding 版本、增量更新和重建。
4. **TPLVEC-004** — 建立 vector、BM25、metadata filter、rerank、query rewrite 可替换管道。
5. **TPLVEC-005** — 确保 ACL 在检索前过滤，删除与权限变化传播到所有索引。
6. **TPLVEC-006** — 生成 relevance/recall/MRR/nDCG/citation/latency/cost/security 评测。

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

- 结果可追源和版本。
- 权限不可后置绕过。
- 向量可按模型版本重建。
- 混检/rerank 有评测。

## 失败、降级与恢复

评测集不足时不声称质量达标，只输出基线和采样计划。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLVEC-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLVEC-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLVEC-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLVEC-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLVEC-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLVEC-012** — 未验证能力未被标记为生产完成。

## Repository Integration Boundary

- Provenance is pinned to `elmos-database-bigdata-skills` `1.0.0`, source `skills/elmos-database-bigdata-skills-v1.0.0/skills/elmos-template-vector-knowledge-analytics/SKILL.md`, and `sha256:78cae274aacd0fc3e8d6c3f3a78b53883e8bed25239f8c952b88b1de4d0eea2c`.
- Source group: `bigdata-templates`. Dependencies: `["elmos-bigdata-project-orchestrator"]`. Triggers: `["RAG/知识库/语义检索", "向量数据库选型", "多模态知识分析"]`. Declared outputs: `["template-plan.json", "generated-project/"]`.
- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.
- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.
- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.
- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.
- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.
- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.
- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.
