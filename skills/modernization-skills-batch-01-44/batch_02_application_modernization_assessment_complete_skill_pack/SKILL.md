---
name: batch-02-application-modernization-automated-assessment
description: >
  从 Portfolio Intake、源码与二进制发现到架构、依赖、数据流、风险、云适配、候选路线、预测、波次和 Assessment Certificate。
version: 1.0.0
batch_id: batch-02
layer: assessment-and-planning
risk: critical
skill_count: 21
status: implementation-ready-specification
---

# Batch 2：应用现代化自动评估

## 0. Batch 定位

```yaml
batch:
  id: batch-02
  name: batch-02-application-modernization-automated-assessment
  version: 1.0.0
  status: implementation-ready-specification
  layer: assessment-and-planning
  risk: critical
  skill_count: 21
  depends_on:
    - batch-01-competitive-landscape-and-product-positioning
```

## 1. Primary Objective

对企业应用组合、源码、二进制、基础设施、运行环境、数据库、集成关系和业务约束进行自动化评估，建立可复现现状快照，生成证据化架构、风险、候选路线、区间预测、迁移波次和 Assessment Certificate。

## 2. Non-objectives

- 不直接修改生产代码或数据库。
- 不执行未经授权的二进制反编译。
- 不把源码扫描成功等同于应用可迁移。
- 不把编译成功等同于行为等价。
- 不输出没有置信区间的精确工期或成本承诺。
- 不把云适配建议等同于生产上线批准。

## 3. 可信链与总体架构

```text
Portfolio Intake and Governance
→ Immutable Assessment Snapshot
→ Source / Binary / Infrastructure / Runtime / Document Discovery
→ Canonical Workload Inventory
→ Evidence Quality
→ Semantic Index / Architecture / Dependency / Dataflow / Runtime
→ Technical Debt / Security / Cloud Fit
→ Migration Candidates
→ Sandbox Feasibility Probes
→ Calibrated Prediction
→ Portfolio Waves
→ Report and Assessment Certificate
```

## 4. 核心原则

- Snapshot First
- Evidence Before Inference
- Read-only by Default
- Static + Binary + Runtime + Documentation
- Build-aware Analysis
- Target-neutral Before Provider-specific
- Direction-specific Route Assessment
- Interval Prediction Instead of Point Promise
- Unknown Must Remain Unknown

## 5. 完整工作流

```text
Intake
→ Authorize
→ Snapshot
→ Collect
→ Normalize
→ Analyze
→ Generate Candidates
→ Probe
→ Estimate
→ Plan Waves
→ Review
→ Certify
```

## 6. 状态机

```text
created
→ scope-drafted
→ awaiting-authorization
→ authorized
→ snapshotting
→ collecting
→ inventory-ready
→ indexing
→ architecture-recovered
→ analyzing
→ candidates-generated
→ probing
→ estimating
→ planning
→ awaiting-review
→ report-issued
→ certified

exceptions:
partial
insufficient-evidence
access-denied
source-changed
unsafe-to-execute
conflicting-evidence
needs-human
cancelled
failed
stale
certificate-revoked
```

## 7. 核心数据契约

### AssessmentRequest

```yaml
assessment_id: uuid
tenant_id: uuid
purpose: modernization | cloud-migration | framework-upgrade | language-conversion | database-migration
scope:
  portfolio_ids: []
  repository_refs: []
  artifact_refs: []
  environments: []
business_context:
  business_criticality: string
  owners: []
  sla: string | null
  rto: duration | null
  rpo: duration | null
target_constraints: {}
execution_policy:
  source_read: boolean
  decompilation_allowed: boolean
  sandbox_build_allowed: boolean
  external_network_allowed: boolean
  runtime_telemetry_allowed: boolean
```

### AssessmentSnapshot

```yaml
snapshot_id: uuid
assessment_id: uuid
repositories:
  - repository_id: string
    branch: string
    commit_sha: string
    tree_digest: sha256
artifacts:
  - artifact_id: string
    digest: sha256
environments: []
documents: []
database_metadata: []
toolchain: {}
snapshot_merkle_root: sha256
```

### MigrationCandidate

```yaml
candidate_id: uuid
workload_ids: []
strategy: retain | retire | replace | rehost | relocate | replatform | refactor | rearchitect | rewrite
route: {}
preconditions: []
hard_blockers: []
soft_blockers: []
required_manual_work: []
required_validation: []
rollback_requirements: []
confidence: number
evidence_refs: []
```

### AssessmentCertificate

```yaml
certificate_id: uuid
assessment_id: uuid
snapshot_id: uuid
level: A0 | A1 | A2 | A3 | A4 | A5
coverage: {}
primary_candidates: []
hard_blockers: []
unresolved_unknowns: []
explicit_limitations: []
issued_at: datetime
expires_at: datetime
signature: string
```

## 8. 核心产物

- `portfolio-intake-manifest.yaml`
- `assessment-snapshot.json`
- `source-repository-inventory.json`
- `binary-artifact-inventory.json`
- `canonical-workload-inventory.json`
- `evidence-graph.json`
- `architecture-graph.json`
- `dependency-graph.json`
- `call-graph.json`
- `dataflow-graph.json`
- `runtime-topology.json`
- `technical-debt-findings.json`
- `security-supply-chain-findings.json`
- `cloud-fit-matrix.json`
- `migration-route-candidates.json`
- `feasibility-probe-results.json`
- `prediction-estimates.json`
- `portfolio-wave-plan.json`
- `assessment-report.json`
- `assessment-certificate.json`

## 9. Skills

| # | Skill | Layer | Risk | Objective |
|---:|---|---|---|---|
| 01 | `b02-assessment-orchestrator` | orchestrator | critical | 保证发现、架构恢复、风险分析、路线候选、探针、预测和证书围绕同一 Snapshot 与证据链运行。 |
| 02 | `b02-portfolio-intake-and-scope` | intake | high | 回答究竟评估哪些系统，并为覆盖率提供真实分母。 |
| 03 | `b02-assessment-access-and-data-governance` | governance | critical | 确保评估只在被授权的数据和执行边界内运行。 |
| 04 | `b02-source-repository-discovery` | discovery | high | 建立 Repository→Module→Build Root 的完整、可重放源码清单。 |
| 05 | `b02-binary-and-artifact-discovery` | discovery | critical | 发现生产中存在但源码中缺失或版本不一致的组件。 |
| 06 | `b02-infrastructure-runtime-document-ingestion` | discovery | critical | 把代码以外的运行与组织证据纳入同一评估快照。 |
| 07 | `b02-canonical-workload-inventory-builder` | normalization | critical | 建立 Source→Artifact→Deployment→Runtime 与业务系统层级的统一身份。 |
| 08 | `b02-assessment-evidence-quality-controller` | evidence | critical | 决定哪些 Finding、路线和证书结论具备足够证据。 |
| 09 | `b02-semantic-source-indexer` | semantic-analysis | critical | 为架构、依赖和路线评估提供可查询的源语义基础。 |
| 10 | `b02-architecture-recovery-engine` | architecture | critical | 生成当前架构、Drift、迁移单元候选和假设登记。 |
| 11 | `b02-dependency-callgraph-impact-analyzer` | dependency-analysis | critical | 识别循环依赖、高中心性组件、动态调用和迁移顺序约束。 |
| 12 | `b02-dataflow-state-integration-analyzer` | data-analysis | critical | 建立应用与数据库联合迁移、差分验证和 Dual Run 所需的可观测面。 |
| 13 | `b02-runtime-topology-correlator` | runtime-analysis | high | 识别静态与运行差异、Hot Path、采样限制和生产基线。 |
| 14 | `b02-technical-debt-maintainability-assessor` | risk-analysis | high | 区分迁移前必须修复、迁移中处理和迁移后偿还的技术债。 |
| 15 | `b02-security-supply-chain-compliance-assessor` | security | critical | 识别会阻断现代化路线或需要安全审批的风险，并避免把 CVE 列表冒充可利用结论。 |
| 16 | `b02-cloud-platform-fit-analyzer` | target-assessment | critical | 防止先选云产品再反向制造需求，并量化 Lock-in 与退出成本。 |
| 17 | `b02-migration-strategy-route-candidate-generator` | planning | critical | 输出 Pareto 候选，而不是单一 AI 推荐，并显式保留被淘汰方案。 |
| 18 | `b02-feasibility-probe-and-baseline-runner` | experimental-validation | critical | 用真实工具链证据校准候选，而不把探针通过冒充生产迁移成功。 |
| 19 | `b02-prediction-calibration-engine` | prediction | critical | 以 P10/P50/P90、Out-of-distribution 和 Cohort 解释预测，禁止伪精确点估计。 |
| 20 | `b02-portfolio-prioritization-wave-planner` | portfolio-planning | critical | 让 Pilot、平台前置、共享数据库和高关键系统按依赖和学习价值排序。 |
| 21 | `b02-assessment-report-and-certificate-gate` | certification | critical | 确保 Assessment Certificate 只证明评估覆盖与证据等级，不冒充迁移成功证书。 |

## 10. Certification Gate

### Required

- Scope、Authorization 和 Snapshot 已锁定。
- Expected Assets 已核对或分母明确为 unknown。
- Canonical Inventory、Architecture、Dependency 和 Dataflow 已生成。
- Technical Debt、Security 和 Cloud Fit 已完成。
- Migration Candidates、Prediction Intervals 和 Limitations 已生成。
- Source Snapshot 未变化。

### Blockers

- assessment-success-equals-migration-success
- compile-success-equals-behavior-equivalence
- missing-evidence-silently-ignored
- unknown-denominator-reported-as-full-coverage
- uncalibrated-point-estimate
- unauthorized-source-upload
- unauthorized-binary-decompilation
- stale-snapshot-certificate

## 11. API Contract

```text
POST /v1/assessments
GET /v1/assessments/{assessment_id}
POST /v1/assessments/{assessment_id}/scope
POST /v1/assessments/{assessment_id}/authorize
POST /v1/assessments/{assessment_id}/snapshot
POST /v1/assessments/{assessment_id}/start
GET /v1/assessments/{assessment_id}/inventory
GET /v1/assessments/{assessment_id}/architecture
GET /v1/assessments/{assessment_id}/findings
GET /v1/assessments/{assessment_id}/candidates
POST /v1/assessments/{assessment_id}/probes
GET /v1/assessments/{assessment_id}/estimates
POST /v1/assessments/{assessment_id}/certificate
```

## 12. Domain Events

```text
assessment.created
assessment.scope.approved
assessment.authorization.granted
assessment.snapshot.created
source.repository.discovered
source.artifact.discovered
inventory.completed
evidence.conflict-detected
architecture.recovered
dependency.graph.completed
dataflow.graph.completed
runtime.correlation.completed
migration.candidate.generated
probe.completed
prediction.generated
wave.plan.generated
assessment.certificate.issued
assessment.certificate.invalidated
```

## 13. 与后续 Batch 的依赖

- Batch 3 必须消费锁定 Snapshot、Workload Inventory、Build Context、Source/Binary Mapping 和 Assessment Certificate。
- 转换 Batch 必须消费候选路线、Hard Blocker、验证要求和预测假设。
- 数据库 Batch 必须消费数据库对象、事务、共享状态和 Dynamic SQL 分析。
- 差分与 Dual Run Batch 必须消费源基线、Observable Surface 和 Side-effect Register。

## 14. 最终产品结论

Batch 2 建成后，平台拥有一个只读优先、证据驱动、可复现、可增量更新的 Application Modernization Assessment Engine。它不输出虚假的单一成功率，而输出不可变快照、统一资产图谱、候选路线、可行性证据、区间预测、波次和有边界的 Assessment Certificate。
