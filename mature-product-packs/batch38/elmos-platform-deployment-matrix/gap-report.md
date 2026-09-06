# Batch 38 gap inventory

- Pack: `elmos-platform-deployment-matrix`
- Skills in scope: 22
- Blocking gaps: 27
- Open gaps: 23
- Repository-owned: 21 blocking / 22 open
- External gate: 6 blocking / 1 open

This inventory is a work list. It grants no status and is not evidence.

## Blocking

- [evidence / external-gate] evidence-manifest.json has not been produced
- [evidence / external-gate] certification-request.json has not been produced
- [evidence / external-gate] certification-request.sig has not been produced
- [provenance / repository] pack.json artifactDigest is still the zero digest
- [provenance / repository] pack.json environmentDigest is still the zero digest
- [metric / repository] airgapUpdatePassRate has not been measured (threshold 1.0)
- [metric / repository] drRecoveryPassRate has not been measured (threshold 1.0)
- [metric / repository] editionCoverage has not been measured (threshold 1.0)
- [metric / repository] evidenceTraceCoverage has not been measured (threshold 0.98)
- [metric / repository] mixedVersionCompatibilityPassRate has not been measured (threshold 1.0)
- [metric / repository] portableControlPlanePassRate has not been measured (threshold 1.0)
- [metric / repository] rollbackPassRate has not been measured (threshold 1.0)
- [metric / repository] tenantMigrationPassRate has not been measured (threshold 1.0)
- [metric / repository] zeroDowntimeUpgradePassRate has not been measured (threshold 1.0)
- [zero-tolerance / repository] criticalDataLoss has not been evaluated
- [zero-tolerance / repository] crossTenantAccess has not been evaluated
- [zero-tolerance / repository] unsignedUpdatesAccepted has not been evaluated
- [zero-tolerance / repository] unresolvedSchemaIncompatibilities has not been evaluated
- [zero-tolerance / repository] incompatibleRunnerLeases has not been evaluated
- [zero-tolerance / repository] orphanedWorkflows has not been evaluated
- [zero-tolerance / repository] residencyViolations has not been evaluated
- [zero-tolerance / repository] testIntegrityViolations has not been evaluated
- [corpus / external-gate] holdout corpus is empty
- [corpus / external-gate] representative corpus is empty
- [evidence / repository] evidence directory holds no artefacts
- [approval / external-gate] no accountable approver is recorded on the certification
- [evidence / repository] evidence.json declares no claims

## Open

- [coverage / repository] b38-air-gapped-edition is only experimental in the support matrix
- [coverage / repository] b38-customer-vpc-edition is only experimental in the support matrix
- [coverage / repository] b38-database-expand-contract-upgrade is only experimental in the support matrix
- [coverage / repository] b38-dedicated-saas-edition is only experimental in the support matrix
- [coverage / repository] b38-deployment-upgrade-gate is only experimental in the support matrix
- [coverage / repository] b38-edge-plant-restricted-edition is only experimental in the support matrix
- [coverage / repository] b38-edition-responsibility-matrix is only experimental in the support matrix
- [coverage / repository] b38-enterprise-deployment-upgrade-factory is only experimental in the support matrix
- [coverage / repository] b38-multiregion-active-active-edition is only experimental in the support matrix
- [coverage / repository] b38-multitenant-saas-edition is only experimental in the support matrix
- [coverage / repository] b38-offline-signed-update-bundle is only experimental in the support matrix
- [coverage / repository] b38-plane-topology-governance is only experimental in the support matrix
- [coverage / repository] b38-platform-version-compatibility is only experimental in the support matrix
- [coverage / repository] b38-portable-control-plane is only experimental in the support matrix
- [coverage / repository] b38-private-sovereign-cloud-edition is only experimental in the support matrix
- [coverage / repository] b38-recipe-pack-extension-upgrade is only experimental in the support matrix
- [coverage / repository] b38-runner-version-compatibility is only experimental in the support matrix
- [coverage / repository] b38-self-hosted-edition is only experimental in the support matrix
- [coverage / repository] b38-tenant-edition-migration is only experimental in the support matrix
- [coverage / repository] b38-upgrade-rollback-disaster-recovery is only experimental in the support matrix
- [coverage / repository] b38-workflow-version-long-run-recovery is only experimental in the support matrix
- [coverage / repository] b38-zero-downtime-upgrade is only experimental in the support matrix
- [status / external-gate] certification status is NOT_RUN
