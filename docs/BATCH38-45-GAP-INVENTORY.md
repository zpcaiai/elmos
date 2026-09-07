# Batch 38–45 差距清单（gap inventory）

由 `scripts/mature_product_toolkit.py gaps` 确定性生成。本清单只是工作清单，**不授予任何状态、也不构成证据**。
认证路径与各产物的职责见 `docs/BATCH38-45-CERTIFICATION-PATH.md`。

## 总览

| 批次 | 主题 | Pack | 在范围 Skills | 阻塞项 | 待办项 |
|---|---|---|---|---|---|
| 38 | 企业部署矩阵与升级生命周期 | `elmos-platform-deployment-matrix` | 22 | 27 | 23 |
| 39 | 全球 SRE 运维 | `elmos-platform-sre-operations` | 22 | 27 | 23 |
| 40 | 安全供应链合规 | `elmos-platform-supply-chain` | 24 | 25 | 27 |
| 41 | 知识飞轮 | `elmos-platform-knowledge-flywheel` | 20 | 27 | 21 |
| 42 | Agent 工厂 | `elmos-platform-agent-factory` | 22 | 28 | 23 |
| 43 | 产品版本生命周期 / LTS | `elmos-platform-product-lifecycle` | 20 | 23 | 21 |
| 44 | FinOps 经济性 | `elmos-platform-finops` | 20 | 27 | 21 |
| 45 | 成熟产品综合认证 | `elmos-platform-production-readiness` | 22 | 40 | 24 |
| **合计** | | 8 个 pack | 172 | **224** | **183** |

## 按类别汇总

| 类别 | 条目数 | 含义 |
|---|---|---|
| 能力覆盖 (`coverage`) | 172 | 能力在支持矩阵中仍是 experimental 或无证据 |
| 指标 (`metric`) | 75 | 指标未测量或未达阈值 |
| 零容忍项 (`zero-tolerance`) | 67 | 零容忍项未评估或非零 |
| 证据 (`evidence`) | 37 | 证据清单/请求/签名或 claim 尚未产出 |
| 来源与摘要 (`provenance`) | 16 | artifact / environment 摘要仍是全零占位 |
| 语料 (`corpus`) | 16 | holdout / representative 语料为空 |
| 问责审批 (`approval`) | 8 | 无问责审批人 |
| 认证状态 (`status`) | 8 | 认证状态非 CERTIFIED |
| 跨批聚合 (`aggregate`) | 7 | batch45 依赖的下游批次门禁尚未认证 |
| claim 范围与局限 (`claim-scope`) | 1 | PASS 的 claim 没有陈述或没有声明局限性 |

## 已有真实证据的部分

**Batch 43 — `b43-schema-surface-compatibility`**：606 个 Schema 受检、527 个与基线逐字段比对、0 个破坏性变更。
关闭了 evidence 目录非空、claim 已声明并写明局限、`versionedSurfaceCoverage` 与 `unsupportedBreakingChangeCount` 已测量、`unannouncedBreakingChanges` 评估为 0。

**Batch 40 — 依赖清单与凭据扫描**：

- 依赖清单：86 个 Maven POM + 3 个 npm lock，493 个组件，437 个外部组件中 402 个版本可解析，`sbomCoverage = 0.9199`。剩余 35 个是 BOM 托管或属性不可静态解析的，工具明确标注而不猜测。
- 凭据扫描：33 个声明根、7800 个文件，**11 条可行动发现待分诊**，2615 条高熵命中列为咨询性（不参与门禁）。
- 因为 11 条尚未分诊，`b40-credential-scan-triage` 这条 claim 记为 `INCONCLUSIVE` 而不是 PASS 或 FAIL——判定它们是测试夹具还是真凭据，是仓库负责人的决定，不是工具的。

## 每批阻塞项明细

### Batch 38 — 企业部署矩阵与升级生命周期（`elmos-platform-deployment-matrix`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（5）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced
- evidence directory holds no artefacts
- evidence.json declares no claims

**指标**（9）

- airgapUpdatePassRate has not been measured (threshold 1.0)
- drRecoveryPassRate has not been measured (threshold 1.0)
- editionCoverage has not been measured (threshold 1.0)
- evidenceTraceCoverage has not been measured (threshold 0.98)
- mixedVersionCompatibilityPassRate has not been measured (threshold 1.0)
- portableControlPlanePassRate has not been measured (threshold 1.0)
- …另有 3 条同类项，见 `mature-product-packs/batch38/elmos-platform-deployment-matrix/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（8）

- criticalDataLoss has not been evaluated
- crossTenantAccess has not been evaluated
- unsignedUpdatesAccepted has not been evaluated
- unresolvedSchemaIncompatibilities has not been evaluated
- incompatibleRunnerLeases has not been evaluated
- orphanedWorkflows has not been evaluated
- …另有 2 条同类项，见 `mature-product-packs/batch38/elmos-platform-deployment-matrix/gap-report.md`

待办：22 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN

### Batch 39 — 全球 SRE 运维（`elmos-platform-sre-operations`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（5）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced
- evidence directory holds no artefacts
- evidence.json declares no claims

**指标**（9）

- evidenceTraceCoverage has not been measured (threshold 0.98)
- fairSchedulingPassRate has not been measured (threshold 1.0)
- incidentResponseExercisePassRate has not been measured (threshold 1.0)
- multiregionFailoverPassRate has not been measured (threshold 1.0)
- productionReadinessPassRate has not been measured (threshold 1.0)
- restorePassRate has not been measured (threshold 1.0)
- …另有 3 条同类项，见 `mature-product-packs/batch39/elmos-platform-sre-operations/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（8）

- unresolvedSev1Incidents has not been evaluated
- rpoBreaches has not been evaluated
- rtoBreaches has not been evaluated
- tenantStarvationEvents has not been evaluated
- unownedCriticalAlerts has not been evaluated
- missingCriticalRunbooks has not been evaluated
- …另有 2 条同类项，见 `mature-product-packs/batch39/elmos-platform-sre-operations/gap-report.md`

待办：22 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN

### Batch 40 — 安全供应链合规（`elmos-platform-supply-chain`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（3）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced

**指标**（8）

- auditEvidenceFreshnessRate has not been measured (threshold 1.0)
- evidenceTraceCoverage has not been measured (threshold 0.98)
- independentAssessmentClosureRate has not been measured (threshold 1.0)
- provenanceCoverage has not been measured (threshold 1.0)
- secureSdlcControlCoverage has not been measured (threshold 1.0)
- signatureVerificationRate has not been measured (threshold 1.0)
- …另有 2 条同类项，见 `mature-product-packs/batch40/elmos-platform-supply-chain/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（9）

- criticalOpenVulnerabilities has not been evaluated
- secretLeaks observed 11, must be zero
- unsignedProductionArtifacts has not been evaluated
- tamperedArtifactsAccepted has not been evaluated
- unresolvedLicenseBlocks has not been evaluated
- builderAttestationFailures has not been evaluated
- …另有 3 条同类项，见 `mature-product-packs/batch40/elmos-platform-supply-chain/gap-report.md`

待办：24 个能力在支持矩阵中仍为 experimental；sbomCoverage is 0.9199, below the required 1.0；certification status is NOT_RUN；claim b40-credential-scan-triage is INCONCLUSIVE

### Batch 41 — 知识飞轮（`elmos-platform-knowledge-flywheel`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（5）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced
- evidence directory holds no artefacts
- evidence.json declares no claims

**指标**（9）

- evidenceTraceCoverage has not been measured (threshold 0.98)
- forecastIntervalCoverage has not been measured (threshold 0.9)
- holdoutPassRate has not been measured (threshold 1.0)
- humanReviewClosureRate has not been measured (threshold 1.0)
- knowledgeLineageCoverage has not been measured (threshold 1.0)
- ontologyCoverage has not been measured (threshold 1.0)
- …另有 3 条同类项，见 `mature-product-packs/batch41/elmos-platform-knowledge-flywheel/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（8）

- privateKnowledgeLeaks has not been evaluated
- targetLeakageFindings has not been evaluated
- unattributedKnowledgeItems has not been evaluated
- uncalibratedP0Predictions has not been evaluated
- unsafeRecommendations has not been evaluated
- expiredCertifiedAssetsUsed has not been evaluated
- …另有 2 条同类项，见 `mature-product-packs/batch41/elmos-platform-knowledge-flywheel/gap-report.md`

待办：20 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN

### Batch 42 — Agent 工厂（`elmos-platform-agent-factory`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（5）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced
- evidence directory holds no artefacts
- evidence.json declares no claims

**指标**（9）

- adversarialEvalPassRate has not been measured (threshold 1.0)
- costBudgetCompliance has not been measured (threshold 1.0)
- evidenceTraceCoverage has not been measured (threshold 0.98)
- holdoutPassRate has not been measured (threshold 1.0)
- humanTakeoverPassRate has not been measured (threshold 1.0)
- killSwitchPassRate has not been measured (threshold 1.0)
- …另有 3 条同类项，见 `mature-product-packs/batch42/elmos-platform-agent-factory/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（9）

- crossTenantAccess has not been evaluated
- unauthorizedToolCalls has not been evaluated
- selfApprovedCriticalActions has not been evaluated
- unreplayedHarmfulActions has not been evaluated
- evidenceForgeryAcceptances has not been evaluated
- killSwitchFailures has not been evaluated
- …另有 3 条同类项，见 `mature-product-packs/batch42/elmos-platform-agent-factory/gap-report.md`

待办：22 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN

### Batch 43 — 产品版本生命周期 / LTS（`elmos-platform-product-lifecycle`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（3）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced

**指标**（8）

- backportValidationRate has not been measured (threshold 1.0)
- compatibilityMatrixPassRate has not been measured (threshold 1.0)
- deprecationOwnerCoverage has not been measured (threshold 1.0)
- evidenceTraceCoverage has not been measured (threshold 0.98)
- migrationGuideAccuracyRate has not been measured (threshold 1.0)
- mixedVersionPassRate has not been measured (threshold 1.0)
- …另有 2 条同类项，见 `mature-product-packs/batch43/elmos-platform-product-lifecycle/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（7）

- unsupportedVersionPromotions has not been evaluated
- irreversibleUpgradeWithoutApproval has not been evaluated
- runnerProtocolSafetyRegressions has not been evaluated
- schemaDataLoss has not been evaluated
- expiredFeatureFlags has not been evaluated
- unpatchedSupportedCriticalVulnerabilities has not been evaluated
- …另有 1 条同类项，见 `mature-product-packs/batch43/elmos-platform-product-lifecycle/gap-report.md`

待办：20 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN

### Batch 44 — FinOps 经济性（`elmos-platform-finops`）

**问责审批**（1）

- no accountable approver is recorded on the certification

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（5）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced
- evidence directory holds no artefacts
- evidence.json declares no claims

**指标**（9）

- billingReconciliationRate has not been measured (threshold 1.0)
- budgetGuardrailPassRate has not been measured (threshold 1.0)
- costAllocationReconciliationRate has not been measured (threshold 1.0)
- customerValueEvidenceCoverage has not been measured (threshold 0.95)
- evidenceTraceCoverage has not been measured (threshold 0.98)
- forecastIntervalCoverage has not been measured (threshold 0.9)
- …另有 3 条同类项，见 `mature-product-packs/batch44/elmos-platform-finops/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（8）

- duplicateMeterEvents has not been evaluated
- unallocatedMaterialCosts has not been evaluated
- nonzeroBillingReconciliationDifference has not been evaluated
- securityGateBypassesForCost has not been evaluated
- unapprovedNegativeMarginDeals has not been evaluated
- customerDataLossFromBudgetStops has not been evaluated
- …另有 2 条同类项，见 `mature-product-packs/batch44/elmos-platform-finops/gap-report.md`

待办：20 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN

### Batch 45 — 成熟产品综合认证（`elmos-platform-production-readiness`）

**跨批聚合**（7）

- Batch 38 has no certified domain gate to aggregate
- Batch 39 has no certified domain gate to aggregate
- Batch 40 has no certified domain gate to aggregate
- Batch 41 has no certified domain gate to aggregate
- Batch 42 has no certified domain gate to aggregate
- Batch 43 has no certified domain gate to aggregate
- …另有 1 条同类项，见 `mature-product-packs/batch45/elmos-platform-production-readiness/gap-report.md`

**问责审批**（1）

- no accountable approver is recorded on the certification

**claim 范围与局限**（1）

- claim local-engineering-runtime-operability passes with no statement in claims.json

**语料**（2）

- holdout corpus is empty
- representative corpus is empty

**证据**（4）

- evidence-manifest.json has not been produced
- certification-request.json has not been produced
- certification-request.sig has not been produced
- evidence directory holds no artefacts

**指标**（13）

- certifiedRouteClaimAccuracy has not been measured (threshold 1.0)
- customerOutcomePassRate has not been measured (threshold 1.0)
- deploymentMatrixPassRate has not been measured (threshold 1.0)
- developerExperiencePassRate has not been measured (threshold 1.0)
- economicsPassRate has not been measured (threshold 1.0)
- ecosystemPassRate has not been measured (threshold 1.0)
- …另有 7 条同类项，见 `mature-product-packs/batch45/elmos-platform-production-readiness/gap-report.md`

**来源与摘要**（2）

- pack.json artifactDigest is still the zero digest
- pack.json environmentDigest is still the zero digest

**零容忍项**（10）

- criticalOpenProductRisks has not been evaluated
- unsupportedMarketingClaims has not been evaluated
- unknownP0Correctness has not been evaluated
- criticalSecurityFindings has not been evaluated
- unrecoveredDrFailures has not been evaluated
- unacceptedCustomerP0Differences has not been evaluated
- …另有 4 条同类项，见 `mature-product-packs/batch45/elmos-platform-production-readiness/gap-report.md`

待办：22 个能力在支持矩阵中仍为 experimental；certification status is NOT_RUN；claim field-production-maturity is NOT_RUN

## 收敛顺序

Batch 45 的聚合门禁要求 Batch 38–44 全部产出 `status=CERTIFIED` 且 `eligible=true` 的域门禁，因此顺序固定：

1. **每批各自解阻塞** —— 真实 artifact/environment 摘要、非空 holdout 与代表性语料、evidence.json 的实际 claims。
2. **补齐可测量指标与零容忍项** —— 写进 `metrics.json` 与 `zero-tolerance.json`，每个数字都要绑定证据引用。
3. **接入外部信任链** —— `manifest` 与 `request` 子命令生成，独立验证人复现，离线密钥签名。
4. **支持矩阵升级** —— 172 个能力逐个从 experimental 升到有证据支撑的 limited/certified。
5. **最后跑 Batch 45 聚合门禁** —— 另需 ≥2 份客户证据与 ≥1 份独立第三方评审。

## 工具链自身的测试

差距清单只有在生成它的工具可信时才有意义，因此这些命令本身也有测试（共 94 项）：

- `tests/mature_product_toolkit_extensions_test.py` —— 25 项：score / gaps / manifest / request
- `tests/batch43_schema_compatibility_test.py` —— 20 项：8 类破坏性变更、4 类必须判兼容的变更、运行上下文
- `tests/batch40_supply_chain_test.py` —— 26 项：版本解析的六种情形、凭据规则精度、豁免生命周期、分片合并
- `tests/mature_product_gate_test.py` —— 7 项：带签名的 CERTIFIED 全通路径
- `tests/batch{38..45}/test_toolkit.py` —— 32 项：每批的契约与伪认证拒绝

## 复现命令

```bash
make batch40-evidence PACK=elmos-platform-supply-chain
make batch43-evidence PACK=elmos-platform-product-lifecycle
make batch40-gaps PACK=elmos-platform-supply-chain
make mature-product-toolchain-test
```
