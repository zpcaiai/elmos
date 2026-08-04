---
name: batch-01-competitive-landscape-product-positioning-and-continuous-intelligence
description: >
  建立可重复、可审计、可持续更新的应用现代化竞争情报、能力比较、产品定位、Battlecard 与认证体系。
version: 1.0.0
batch_id: batch-01
layer: product-strategy-and-intelligence
risk: high
skill_count: 16
status: implementation-ready-specification
---

# Batch 1：竞争格局、产品定位与持续竞争情报

## 0. Batch 定位

```yaml
batch:
  id: batch-01
  name: batch-01-competitive-landscape-product-positioning-and-continuous-intelligence
  version: 1.0.0
  status: implementation-ready-specification
  layer: product-strategy-and-intelligence
  risk: high
  skill_count: 16
  depends_on:
    - none
```

## 1. Primary Objective

建立可重复、可审计、可持续更新的竞争情报与产品定位系统，为后续应用评估、迁移规划、代码转换、数据库迁移、验证、切换和商业化提供统一战略约束。

## 2. Non-objectives

- 不直接修改客户代码或数据库。
- 不根据厂商营销材料宣称实际转换成功率。
- 不把功能存在等同于生产成熟。
- 不把一次性调研当作持续竞争情报。
- 不使用违法、泄密或违反服务条款的资料。
- 不以未经证实的攻击性比较支持销售。

## 3. 可信链与总体架构

```text
Market Boundary
→ Competitor Discovery Registry
→ Evidence Harvester
→ Capability Taxonomy and Normalization
→ Lifecycle / Route / Database / Trust / Deployment / Economics Matrices
→ Claim Benchmark Verification
→ Gap and Opportunity Engine
→ Product Positioning and Boundary
→ Battlecards and Continuous Monitoring
→ Batch 1 Certification
```

## 4. 核心原则

- Evidence Before Scoring
- Capability Atomicity
- Direction-specific Route Analysis
- Workflow Continuity over Feature Count
- Trust Model over Marketing Correctness
- Cloud-neutral and Sovereignty-aware
- Cost per Verified Migrated Workload
- Unknown Must Remain Unknown

## 5. 完整工作流

```text
Scope
→ Discover
→ Collect Evidence
→ Normalize
→ Compare
→ Verify Claims
→ Identify Gaps
→ Position Product
→ Generate Battlecards
→ Monitor
→ Re-certify
```

## 6. 状态机

```text
created
→ scoped
→ discovering
→ evidence-collected
→ normalized
→ compared
→ positioned
→ reviewed
→ certified

exceptions:
insufficient-evidence
conflicting-evidence
needs-human
stale
blocked
cancelled
```

## 7. 核心数据契约

### CompetitorRecord

```yaml
competitor_id: string
legal_name: string
product_names: []
vendor_type: string
deployment_models: []
supported_workloads: []
supported_languages: []
supported_frameworks: []
supported_databases: []
lifecycle_stages: []
commercial_model: {}
maturity:
  status: announced | preview | ga | mature | unknown
  confidence: number
evidence_refs: []
last_verified_at: datetime
review_due_at: datetime
```

### CapabilityFact

```yaml
fact_id: string
competitor_id: string
capability_id: string
claim:
  statement: string
  claim_type: vendor-claim | documentation | demonstrated | independently-tested | customer-evidence | inferred
support_state: supported | partial | preview | services-only | partner-only | unsupported | unknown
constraints: {}
evidence: {}
confidence: number
expires_at: datetime
```

### ProductPositioningDecision

```yaml
decision_id: string
target_segment: string
buyer: string
primary_problem: string
category:
  current_category: application-modernization-platform
  category_to_create: verified-modernization-execution-os
differentiated_capabilities: []
proof_requirements: []
unsupported_claims: []
required_batches: []
owner: string
valid_until: datetime
```

## 8. 核心产物

- `market-definition.yaml`
- `competitor-registry.yaml`
- `capability-taxonomy.yaml`
- `competitor-capability-matrix.json`
- `workflow-stage-coverage.json`
- `route-coverage-matrix.json`
- `trust-verification-matrix.json`
- `deployment-sovereignty-matrix.json`
- `commercial-model-comparison.json`
- `claim-evidence-graph.json`
- `competitive-gap-map.json`
- `product-positioning.yaml`
- `product-boundary.yaml`
- `battlecards/`
- `batch-01-certification-report.json`

## 9. Skills

| # | Skill | Layer | Risk | Objective |
|---:|---|---|---|---|
| 01 | `b01-competitive-landscape-orchestrator` | orchestrator | high | 把一次性竞品调研转化为可暂停恢复、可审计、可重复运行的竞争情报与产品定位系统。 |
| 02 | `b01-modernization-market-boundary` | strategy | medium | 建立统一市场边界，防止把云迁移、代码生成、咨询服务和完整现代化平台混为一谈。 |
| 03 | `b01-competitor-discovery-registry` | registry | medium | 维护唯一竞争对象注册表，解决产品更名、收购、开源核心、托管平台和服务能力重复计数问题。 |
| 04 | `b01-competitive-evidence-harvester` | evidence | high | 把营销描述拆分为可验证原子 Claim，并保存版本、范围、来源、摘要和过期时间。 |
| 05 | `b01-modernization-capability-taxonomy` | semantic-model | medium | 把发现、评估、转换、验证、切换、治理和持续现代化拆成可比较、可证据化的能力单元。 |
| 06 | `b01-competitor-capability-normalizer` | normalization | high | 避免因为术语相似或厂商动词模糊而错误认定能力等价。 |
| 07 | `b01-end-to-end-stage-coverage-analyzer` | analytics | medium | 识别功能存在但阶段断裂、资产无法连续传递或证据链中断的产品。 |
| 08 | `b01-language-framework-route-coverage` | analytics | high | 建立精确 Directional Route Matrix，防止把版本升级、文件级转换和仓库级迁移混为一谈。 |
| 09 | `b01-database-route-competitive-analyzer` | database-analysis | critical | 区分 Schema、SQL、Routine、Data、CDC、Dual Run、Cutover 和 Rollback，形成数据库路线竞争地图。 |
| 10 | `b01-verification-and-trust-model-analyzer` | trust | critical | 区分语法、构建、测试、差分行为、Dual Run、客户验收和形式证明。 |
| 11 | `b01-deployment-sovereignty-lockin-analyzer` | security | critical | 让客户明确源码去向、模型调用、遥测、密钥、网络出口、区域和退出成本。 |
| 12 | `b01-commercial-economics-analyzer` | economics | high | 用 Cost per Verified Migrated Workload 而不是生成代码行数评价经济性。 |
| 13 | `b01-competitive-claim-benchmark-verifier` | validation | critical | 避免无基线、无样本、只算生成时间或删除失败测试后的误导性指标。 |
| 14 | `b01-competitive-gap-opportunity-engine` | strategy | high | 区分短期功能空白和难以复制的系统性能力，形成产品机会优先级。 |
| 15 | `b01-product-positioning-and-boundary` | strategy | critical | 形成可验证的 Verified Modernization Execution OS 定位，明确服务谁、解决什么和不承诺什么。 |
| 16 | `b01-battlecard-and-continuous-intelligence-gate` | certification | critical | 让销售、产品和战略团队持续使用同一事实库，同时阻止过期或未经证实话术。 |

## 10. Certification Gate

### Required

- 市场边界已定义并批准。
- 主要竞争类别已覆盖。
- Capability Taxonomy 和 Normalization 通过测试。
- 关键 Claim 具有足够证据。
- 语言、框架和数据库路线按方向建模。
- Trust、Deployment、Economics 和 Positioning 已完成。
- 产品边界和 Reference Route 明确。
- 持续监测 Owner 和复核时间已登记。

### Blockers

- unsupported market leadership claim
- fabricated pricing
- vendor marketing treated as independent evidence
- preview treated as production certification
- schema conversion treated as full database migration
- compile success treated as behavior equivalence
- undifferentiated one-click conversion positioning
- no initial reference route

## 11. API Contract

```text
POST /v1/competitive-assessments
GET  /v1/competitive-assessments/{assessment_id}
POST /v1/competitors/discover
GET  /v1/competitors
POST /v1/evidence
GET  /v1/capability-matrix
GET  /v1/route-matrix
GET  /v1/trust-matrix
POST /v1/positioning-decisions
GET  /v1/battlecards/{competitor_id}
POST /v1/certificates/batch-01
```

## 12. Domain Events

```text
competitive.assessment.created
competitor.discovered
competitor.merged
evidence.collected
evidence.conflict-detected
evidence.stale
capability.normalized
route.coverage.changed
benchmark.claim.verified
positioning.review-required
battlecard.updated
batch01.certificate.issued
batch01.certificate.invalidated
```

## 13. 与后续 Batch 的依赖

- Batch 2 必须消费产品边界、目标客户、Capability Taxonomy 和 Reference Route。
- 后续转换与数据库 Batch 必须使用 Directional Route Policy。
- 验证 Batch 必须使用 Trust Level Model 和 Claim Evidence 规则。
- 任何销售承诺不得超出 Product Boundary 和当前证据。

## 14. 最终产品结论

Batch 1 建成后，平台拥有一套持续运行的竞争事实库与产品定位控制面。它不以功能数量或营销声量作结论，而以方向性路线、端到端连续性、验证可信度、部署主权、经济性和证据质量约束后续全部产品设计。
