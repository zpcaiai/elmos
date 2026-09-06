# Batch 40 gap inventory

- Pack: `elmos-platform-supply-chain`
- Skills in scope: 24
- Blocking gaps: 14
- Open gaps: 13
- Repository-owned: 1 blocking / 12 open
- External gate: 13 blocking / 1 open

This inventory is a work list. It grants no status and is not evidence.

## Blocking

- [evidence / external-gate] evidence-manifest.json has not been produced
- [evidence / external-gate] certification-request.json has not been produced
- [evidence / external-gate] certification-request.sig has not been produced
- [metric / external-gate] independentAssessmentClosureRate has not been measured (threshold 1.0)
- [metric / external-gate] signatureVerificationRate has not been measured (threshold 1.0)
- [zero-tolerance / external-gate] unsignedProductionArtifacts has not been evaluated
- [zero-tolerance / external-gate] tamperedArtifactsAccepted has not been evaluated
- [zero-tolerance / repository] unresolvedLicenseBlocks observed 427, must be zero
- [zero-tolerance / external-gate] builderAttestationFailures has not been evaluated
- [zero-tolerance / external-gate] runnerDowngradeAcceptances has not been evaluated
- [zero-tolerance / external-gate] crossTenantEvidenceLeaks has not been evaluated
- [corpus / external-gate] holdout corpus is empty
- [corpus / external-gate] representative corpus is empty
- [approval / external-gate] no accountable approver is recorded on the certification

## Open

- [coverage / repository] b40-ai-model-supply-chain is only experimental in the support matrix
- [coverage / repository] b40-artifact-container-signing is only experimental in the support matrix
- [coverage / repository] b40-container-kubernetes-iac-scanning is only experimental in the support matrix
- [coverage / repository] b40-dast-iast-integration is only experimental in the support matrix
- [coverage / repository] b40-independent-security-assessment is only experimental in the support matrix
- [coverage / repository] b40-isolated-trusted-builder is only experimental in the support matrix
- [coverage / repository] b40-psirt-security-incident is only experimental in the support matrix
- [coverage / repository] b40-sast-integration is only experimental in the support matrix
- [coverage / repository] b40-secure-code-review-approval is only experimental in the support matrix
- [coverage / repository] b40-slsa-provenance is only experimental in the support matrix
- [coverage / repository] b40-vex-applicability is only experimental in the support matrix
- [metric / repository] vulnerabilitySlaCompliance is 0.9027, below the required 1.0
- [status / external-gate] certification status is NOT_RUN
