# Batch-02 Skill Index

本索引包含 **21 个独立 Skills**。

## 依赖主线

```text
Portfolio Intake
→ Authorization
→ Immutable Snapshot
→ Multi-source Discovery
→ Canonical Inventory
→ Semantic and Runtime Analysis
→ Risk and Cloud Fit
→ Migration Candidates
→ Feasibility Probes
→ Prediction
→ Wave Plan
→ Assessment Certificate
```

## 01. `b02-assessment-orchestrator`

- 文件：`skills/01-assessment-orchestrator/SKILL.md`
- 层：`orchestrator`
- 风险：`critical`
- 目标：保证发现、架构恢复、风险分析、路线候选、探针、预测和证书围绕同一 Snapshot 与证据链运行。
- 主要输出：`assessment-run.json`, `assessment-report.json`, `assessment-certificate.json`, `assessment-evidence-bundle/`

## 02. `b02-portfolio-intake-and-scope`

- 文件：`skills/02-portfolio-intake-and-scope/SKILL.md`
- 层：`intake`
- 风险：`high`
- 目标：回答究竟评估哪些系统，并为覆盖率提供真实分母。
- 主要输出：`portfolio-intake-manifest.yaml`, `scope-boundary.json`, `expected-asset-register.json`, `exclusion-register.json`

## 03. `b02-assessment-access-and-data-governance`

- 文件：`skills/03-assessment-access-and-data-governance/SKILL.md`
- 层：`governance`
- 风险：`critical`
- 目标：确保评估只在被授权的数据和执行边界内运行。
- 主要输出：`access-grant-manifest.json`, `data-handling-plan.json`, `model-data-routing-policy.json`, `sandbox-execution-policy.json`

## 04. `b02-source-repository-discovery`

- 文件：`skills/04-source-repository-discovery/SKILL.md`
- 层：`discovery`
- 风险：`high`
- 目标：建立 Repository→Module→Build Root 的完整、可重放源码清单。
- 主要输出：`repository-inventory.json`, `repository-snapshot-manifest.json`, `module-root-map.json`, `repository-access-failures.json`

## 05. `b02-binary-and-artifact-discovery`

- 文件：`skills/05-binary-and-artifact-discovery/SKILL.md`
- 层：`discovery`
- 风险：`critical`
- 目标：发现生产中存在但源码中缺失或版本不一致的组件。
- 主要输出：`binary-artifact-inventory.json`, `container-image-inventory.json`, `source-binary-mapping.json`, `opaque-component-register.json`

## 06. `b02-infrastructure-runtime-document-ingestion`

- 文件：`skills/06-infrastructure-runtime-document-ingestion/SKILL.md`
- 层：`discovery`
- 风险：`critical`
- 目标：把代码以外的运行与组织证据纳入同一评估快照。
- 主要输出：`environment-inventory.json`, `deployment-topology.json`, `runtime-baseline.json`, `supporting-document-index.json`, `document-runtime-conflicts.json`

## 07. `b02-canonical-workload-inventory-builder`

- 文件：`skills/07-canonical-workload-inventory-builder/SKILL.md`
- 层：`normalization`
- 风险：`critical`
- 目标：建立 Source→Artifact→Deployment→Runtime 与业务系统层级的统一身份。
- 主要输出：`canonical-workload-inventory.json`, `workload-relationship-graph.json`, `entity-resolution-decisions.json`, `entity-review-queue.json`

## 08. `b02-assessment-evidence-quality-controller`

- 文件：`skills/08-assessment-evidence-quality-controller/SKILL.md`
- 层：`evidence`
- 风险：`critical`
- 目标：决定哪些 Finding、路线和证书结论具备足够证据。
- 主要输出：`evidence-quality-report.json`, `evidence-gap-register.json`, `evidence-conflict-groups.json`

## 09. `b02-semantic-source-indexer`

- 文件：`skills/09-semantic-source-indexer/SKILL.md`
- 层：`semantic-analysis`
- 风险：`critical`
- 目标：为架构、依赖和路线评估提供可查询的源语义基础。
- 主要输出：`semantic-index-manifest.json`, `symbol-index/`, `type-index/`, `semantic-diagnostics.json`

## 10. `b02-architecture-recovery-engine`

- 文件：`skills/10-architecture-recovery-engine/SKILL.md`
- 层：`architecture`
- 风险：`critical`
- 目标：生成当前架构、Drift、迁移单元候选和假设登记。
- 主要输出：`architecture-graph.json`, `architecture-views/`, `architecture-drift-report.json`, `migration-unit-candidates.json`

## 11. `b02-dependency-callgraph-impact-analyzer`

- 文件：`skills/11-dependency-callgraph-impact-analyzer/SKILL.md`
- 层：`dependency-analysis`
- 风险：`critical`
- 目标：识别循环依赖、高中心性组件、动态调用和迁移顺序约束。
- 主要输出：`dependency-graph.json`, `call-graph.json`, `impact-radius.json`, `migration-order-constraints.json`

## 12. `b02-dataflow-state-integration-analyzer`

- 文件：`skills/12-dataflow-state-integration-analyzer/SKILL.md`
- 层：`data-analysis`
- 风险：`critical`
- 目标：建立应用与数据库联合迁移、差分验证和 Dual Run 所需的可观测面。
- 主要输出：`dataflow-graph.json`, `state-ownership-map.json`, `transaction-boundary-map.json`, `side-effect-register.json`, `future-equivalence-observable-surface.json`

## 13. `b02-runtime-topology-correlator`

- 文件：`skills/13-runtime-topology-correlator/SKILL.md`
- 层：`runtime-analysis`
- 风险：`high`
- 目标：识别静态与运行差异、Hot Path、采样限制和生产基线。
- 主要输出：`runtime-topology.json`, `static-runtime-correlation.json`, `performance-baseline.json`, `runtime-coverage-report.json`

## 14. `b02-technical-debt-maintainability-assessor`

- 文件：`skills/14-technical-debt-maintainability-assessor/SKILL.md`
- 层：`risk-analysis`
- 风险：`high`
- 目标：区分迁移前必须修复、迁移中处理和迁移后偿还的技术债。
- 主要输出：`technical-debt-findings.json`, `maintainability-scorecard.json`, `debt-remediation-phases.json`

## 15. `b02-security-supply-chain-compliance-assessor`

- 文件：`skills/15-security-supply-chain-compliance-assessor/SKILL.md`
- 层：`security`
- 风险：`critical`
- 目标：识别会阻断现代化路线或需要安全审批的风险，并避免把 CVE 列表冒充可利用结论。
- 主要输出：`security-supply-chain-findings.json`, `sbom.json`, `license-risk-report.json`, `security-route-blockers.json`

## 16. `b02-cloud-platform-fit-analyzer`

- 文件：`skills/16-cloud-platform-fit-analyzer/SKILL.md`
- 层：`target-assessment`
- 风险：`critical`
- 目标：防止先选云产品再反向制造需求，并量化 Lock-in 与退出成本。
- 主要输出：`cloud-fit-matrix.json`, `target-options.json`, `platform-blockers.json`, `portability-exit-cost.json`

## 17. `b02-migration-strategy-route-candidate-generator`

- 文件：`skills/17-migration-strategy-route-candidate-generator/SKILL.md`
- 层：`planning`
- 风险：`critical`
- 目标：输出 Pareto 候选，而不是单一 AI 推荐，并显式保留被淘汰方案。
- 主要输出：`migration-route-candidates.json`, `candidate-pareto-front.json`, `rejected-candidate-register.json`, `required-validation-plan.json`

## 18. `b02-feasibility-probe-and-baseline-runner`

- 文件：`skills/18-feasibility-probe-and-baseline-runner/SKILL.md`
- 层：`experimental-validation`
- 风险：`critical`
- 目标：用真实工具链证据校准候选，而不把探针通过冒充生产迁移成功。
- 主要输出：`feasibility-probe-results.json`, `build-baseline.json`, `test-baseline.json`, `probe-artifacts/`, `probe-evidence.json`

## 19. `b02-prediction-calibration-engine`

- 文件：`skills/19-prediction-calibration-engine/SKILL.md`
- 层：`prediction`
- 风险：`critical`
- 目标：以 P10/P50/P90、Out-of-distribution 和 Cohort 解释预测，禁止伪精确点估计。
- 主要输出：`prediction-estimates.json`, `calibration-report.json`, `ood-register.json`, `prediction-assumptions.json`

## 20. `b02-portfolio-prioritization-wave-planner`

- 文件：`skills/20-portfolio-prioritization-wave-planner/SKILL.md`
- 层：`portfolio-planning`
- 风险：`critical`
- 目标：让 Pilot、平台前置、共享数据库和高关键系统按依赖和学习价值排序。
- 主要输出：`portfolio-wave-plan.json`, `critical-path.json`, `capacity-plan.json`, `wave-sensitivity-analysis.json`

## 21. `b02-assessment-report-and-certificate-gate`

- 文件：`skills/21-assessment-report-and-certificate-gate/SKILL.md`
- 层：`certification`
- 风险：`critical`
- 目标：确保 Assessment Certificate 只证明评估覆盖与证据等级，不冒充迁移成功证书。
- 主要输出：`assessment-report.html`, `assessment-report.json`, `assessment-certificate.json`, `assessment-certificate.sig`
