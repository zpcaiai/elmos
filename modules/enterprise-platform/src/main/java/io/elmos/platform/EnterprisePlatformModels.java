package io.elmos.platform;

import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable Batch 12 Enterprise Platform Control Model (EPCM). */
public final class EnterprisePlatformModels {
    private EnterprisePlatformModels() {}

    public enum DeploymentMode { SAAS_SHARED, SAAS_DEDICATED_RUNNER, HYBRID_PRIVATE_RUNNER, SELF_HOSTED, AIR_GAPPED }
    public enum IsolationLevel { LEVEL_1_SHARED, LEVEL_2_DATA_ISOLATED, LEVEL_3_NAMESPACE_RUNNER,
        LEVEL_4_DEDICATED_CLUSTER, LEVEL_5_DEDICATED_INSTALLATION, LEVEL_6_AIR_GAPPED }
    public enum Gate {
        BLOCKED(0), T_A(1), T_B(2), T_C(3), T_D(4), T_E(5), T_F(6), T_G(7);
        private final int level;
        Gate(int level) { this.level = level; }
        public int level() { return level; }
    }
    public enum RunStatus { INITIALIZED, TENANCY_IDENTITY_VALIDATED, AUTHORIZATION_AUDIT_VALIDATED,
        RUNNER_SECURITY_VALIDATED, MODEL_COST_GOVERNED, DATA_GOVERNED, DEPLOYMENT_MODES_VALIDATED,
        ENTERPRISE_DELIVERY_READY, BLOCKED, FAILED_SAFELY }
    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, BLOCKED, INCONCLUSIVE, NOT_APPLICABLE }

    public record Request(Path artifactWorkspace, Path platformRepositoryPath, String assessmentRunId,
                          PlatformArtifact platform, List<TenantProfile> tenants,
                          List<DeploymentProfile> deployments, List<CapabilityBinding> capabilities,
                          Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace"); required(platformRepositoryPath, "platformRepositoryPath");
            text(assessmentRunId, "assessmentRunId"); required(platform, "platform");
            tenants = copy(tenants); deployments = copy(deployments); capabilities = copy(capabilities);
            if (tenants.isEmpty() || deployments.isEmpty() || capabilities.isEmpty())
                throw new IllegalArgumentException("tenants, deployment profiles and capability bindings are required");
            required(policy, "policy"); required(observedAt, "observedAt");
            Path workspace = artifactWorkspace.toAbsolutePath().normalize();
            if (workspace.startsWith(platformRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("enterprise evidence workspace must be outside the platform repository");
        }
    }

    public record PlatformArtifact(String platformVersion, String artifactDigest, boolean immutable,
                                   boolean signed, String sbomRef, String provenanceRef,
                                   boolean batch1Through11ControlPlanesVerified,
                                   List<String> evidenceRefs) {
        public PlatformArtifact {
            text(platformVersion, "platformVersion"); digest(artifactDigest, "artifactDigest");
            text(sbomRef, "sbomRef"); text(provenanceRef, "provenanceRef");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record TenantProfile(String tenantId, String organizationId, IsolationLevel isolationLevel,
                                DeploymentMode deploymentMode, String dataRegion, String encryptionKeyRef,
                                String retentionPolicyId, boolean resourceOwnershipComplete,
                                boolean dedicatedDataKey, boolean runnerBoundaryDeclared,
                                boolean modelPolicyDeclared, boolean auditSinkConfigured,
                                boolean legalHoldPolicyConfigured, List<String> evidenceRefs) {
        public TenantProfile {
            text(tenantId, "tenantId"); text(organizationId, "organizationId");
            required(isolationLevel, "isolationLevel"); required(deploymentMode, "deploymentMode");
            text(dataRegion, "dataRegion"); text(encryptionKeyRef, "encryptionKeyRef");
            text(retentionPolicyId, "retentionPolicyId"); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record DeploymentProfile(String profileId, DeploymentMode mode, boolean required,
                                    boolean contractDeclared, boolean responsibilityMatrixComplete,
                                    boolean dataFlowApproved, List<String> evidenceRefs) {
        public DeploymentProfile {
            text(profileId, "profileId"); EnterprisePlatformModels.required(mode, "mode"); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record CapabilityBinding(String capabilityId, String component, String version,
                                    boolean available, boolean externalExecutionRequired,
                                    List<String> evidenceRefs) {
        public CapabilityBinding {
            text(capabilityId, "capabilityId"); text(component, "component"); text(version, "version");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record Policy(double requiredTenantOwnershipCoverage, double requiredKeyIsolationCoverage,
                         double requiredPermissionCoverage, double requiredPolicyCoverage,
                         double requiredApprovalCoverage, double requiredModelProvenanceCoverage,
                         double requiredAuditCoverage, double requiredClassificationCoverage,
                         double requiredRetentionCoverage, double requiredArtifactProvenanceCoverage,
                         long maximumDeprovisionSeconds, double maximumBillingDifference,
                         double requiredEvidenceTraceability) {
        public Policy {
            rate(requiredTenantOwnershipCoverage, "requiredTenantOwnershipCoverage");
            rate(requiredKeyIsolationCoverage, "requiredKeyIsolationCoverage");
            rate(requiredPermissionCoverage, "requiredPermissionCoverage");
            rate(requiredPolicyCoverage, "requiredPolicyCoverage");
            rate(requiredApprovalCoverage, "requiredApprovalCoverage");
            rate(requiredModelProvenanceCoverage, "requiredModelProvenanceCoverage");
            rate(requiredAuditCoverage, "requiredAuditCoverage");
            rate(requiredClassificationCoverage, "requiredClassificationCoverage");
            rate(requiredRetentionCoverage, "requiredRetentionCoverage");
            rate(requiredArtifactProvenanceCoverage, "requiredArtifactProvenanceCoverage");
            rate(requiredEvidenceTraceability, "requiredEvidenceTraceability");
            if (maximumDeprovisionSeconds < 0 || Double.isNaN(maximumBillingDifference) || maximumBillingDifference < 0)
                throw new IllegalArgumentException("enterprise platform policy limits are invalid");
        }
    }

    public interface EvidenceEnvelope {
        String assessmentRunId(); String platformVersion(); EvidenceStatus status();
        String authorityId(); Instant observedAt(); List<String> evidenceRefs();
    }

    public record TenancyIdentityEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                          double tenantOwnershipCoverage, int crossTenantDataLeaks,
                                          int crossTenantArtifactContamination, int crossTenantCacheContamination,
                                          double tenantKeyIsolationCoverage, boolean noisyNeighborControlsPassed,
                                          boolean oidcPassed, boolean samlPassed, boolean scimRequired,
                                          boolean scimPassed, boolean scimIdempotent,
                                          boolean sessionRevocationPassed, long deprovisionLatencySeconds,
                                          boolean mfaForSensitiveRoles, int wrongTenantIdentityBindings,
                                          boolean idpTenantBindingComplete, String authorityId,
                                          Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public TenancyIdentityEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            rate(tenantOwnershipCoverage, "tenantOwnershipCoverage");
            rate(tenantKeyIsolationCoverage, "tenantKeyIsolationCoverage");
            nonnegative(crossTenantDataLeaks, crossTenantArtifactContamination, crossTenantCacheContamination,
                    wrongTenantIdentityBindings);
            if (deprovisionLatencySeconds < 0) throw new IllegalArgumentException("deprovision latency cannot be negative");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record AuthorizationAuditEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                              double apiPermissionCoverage, double policyCoverage,
                                              double policyDecisionAuditCoverage, double highRiskApprovalCoverage,
                                              int selfApprovalEvents, int tenantAdminPlatformPrivilegeEvents,
                                              boolean separationOfDutiesPassed, boolean breakGlassDrillPassed,
                                              int unboundedBreakGlassEvents, double breakGlassAuditCoverage,
                                              double criticalAuditCoverage, boolean auditTamperDetectionPassed,
                                              int auditOverwriteEvents, String authorityId, Instant observedAt,
                                              List<String> evidenceRefs) implements EvidenceEnvelope {
        public AuthorizationAuditEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            rate(apiPermissionCoverage, "apiPermissionCoverage"); rate(policyCoverage, "policyCoverage");
            rate(policyDecisionAuditCoverage, "policyDecisionAuditCoverage");
            rate(highRiskApprovalCoverage, "highRiskApprovalCoverage");
            rate(breakGlassAuditCoverage, "breakGlassAuditCoverage"); rate(criticalAuditCoverage, "criticalAuditCoverage");
            nonnegative(selfApprovalEvents, tenantAdminPlatformPrivilegeEvents, unboundedBreakGlassEvents, auditOverwriteEvents);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record RunnerSecurityEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                         boolean workloadIdentityPassed, double attestationCoverage,
                                         int runnerIdentityCopyEvents, int crossTenantJobLeaks,
                                         int sandboxEscapeFindings, int unauthorizedEgressEvents,
                                         int secretLeakEvents, boolean shortLivedCredentialsPassed,
                                         boolean sourceStayLocalVerified, boolean artifactTransferIntegrityPassed,
                                         boolean tenantRunnerIsolationPassed, boolean leaseRecoveryPassed,
                                         int duplicateNonIdempotentExecutions, String authorityId,
                                         Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public RunnerSecurityEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            rate(attestationCoverage, "attestationCoverage");
            nonnegative(runnerIdentityCopyEvents, crossTenantJobLeaks, sandboxEscapeFindings,
                    unauthorizedEgressEvents, secretLeakEvents, duplicateNonIdempotentExecutions);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record ModelCostEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                    int modelGatewayBypassPaths, int modelDataPolicyViolations,
                                    int promptSecretLeaks, int crossTenantPromptCacheEvents,
                                    double modelProvenanceCoverage, int quotaBypassEvents,
                                    int duplicateMeterEvents, boolean usageLedgerIntegrityPassed,
                                    int historicalLedgerMutationEvents, double billingReconciliationDifference,
                                    int duplicateCharges, boolean fairSchedulingPassed, int starvationEvents,
                                    boolean budgetControlsPassed, boolean entitlementControlsPassed,
                                    String authorityId, Instant observedAt,
                                    List<String> evidenceRefs) implements EvidenceEnvelope {
        public ModelCostEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            rate(modelProvenanceCoverage, "modelProvenanceCoverage");
            if (Double.isNaN(billingReconciliationDifference) || billingReconciliationDifference < 0)
                throw new IllegalArgumentException("billing difference cannot be negative");
            nonnegative(modelGatewayBypassPaths, modelDataPolicyViolations, promptSecretLeaks,
                    crossTenantPromptCacheEvents, quotaBypassEvents, duplicateMeterEvents,
                    historicalLedgerMutationEvents, duplicateCharges, starvationEvents);
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record DataGovernanceEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                         double classificationCoverage, boolean residencyCompliancePassed,
                                         double retentionCoverage, boolean legalHoldPassed,
                                         int legalHoldDeletionEvents, boolean deletionCertificatePassed,
                                         int unexplainedResidualCopies, double tenantKeyIsolationCoverage,
                                         boolean keyRotationPassed, boolean backupKeyRestorePassed,
                                         boolean cmkFailureFailsClosed, double artifactProvenanceCoverage,
                                         boolean supportAccessControlled, String authorityId,
                                         Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public DataGovernanceEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            rate(classificationCoverage, "classificationCoverage"); rate(retentionCoverage, "retentionCoverage");
            rate(tenantKeyIsolationCoverage, "tenantKeyIsolationCoverage");
            rate(artifactProvenanceCoverage, "artifactProvenanceCoverage");
            nonnegative(legalHoldDeletionEvents, unexplainedResidualCopies); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record ModeResult(DeploymentMode mode, EvidenceStatus status, boolean topologyValidated,
                             boolean responsibilityMatrixComplete, boolean installationPassed,
                             int hiddenSaasDependencies, int unexpectedNetworkRequests,
                             boolean signedArtifactsPassed, boolean dependencyClosurePassed,
                             boolean localModelExecutionPassed, boolean modelLicensePassed,
                             boolean offlineLicensePassed, boolean offlineUpdatePassed,
                             boolean rollbackPassed, boolean haAndBackupRestorePassed,
                             List<String> evidenceRefs) {
        public ModeResult {
            required(mode, "mode"); required(status, "status");
            nonnegative(hiddenSaasDependencies, unexpectedNetworkRequests); evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record DeploymentEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                     List<ModeResult> modes, String authorityId, Instant observedAt,
                                     List<String> evidenceRefs) implements EvidenceEnvelope {
        public DeploymentEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            modes = copy(modes); if (modes.isEmpty()) throw new IllegalArgumentException("deployment mode evidence is required");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record EnterpriseAcceptanceEvidence(String assessmentRunId, String platformVersion, EvidenceStatus status,
                                               boolean controlPlaneHaPassed, boolean backupRestorePassed,
                                               boolean queueRecoveryNoLoss, boolean auditAndLedgerRestorePassed,
                                               boolean runnerReconnectNoDuplicate, boolean observabilityPassed,
                                               boolean administrationConsolePassed, boolean apiCliSdkPassed,
                                               boolean gitCiIntegrationPassed, boolean engineeringAccepted,
                                               boolean securityAccepted, boolean operationsAccepted,
                                               boolean businessAccepted, boolean contractCapabilitiesAligned,
                                               int criticalOpenRisks, boolean enterpriseEvidencePackComplete,
                                               double evidenceTraceability, String authorityId,
                                               Instant observedAt, List<String> evidenceRefs) implements EvidenceEnvelope {
        public EnterpriseAcceptanceEvidence {
            common(assessmentRunId, platformVersion, status, authorityId, observedAt);
            nonnegative(criticalOpenRisks); rate(evidenceTraceability, "evidenceTraceability");
            evidenceRefs = evidence(evidenceRefs);
        }
    }

    public record Metrics(double tenantOwnershipCoverage, int crossTenantLeaks,
                          double permissionCoverage, double policyCoverage,
                          double runnerAttestationCoverage, int runnerIsolationFailures,
                          int modelGatewayBypasses, int quotaBypasses, int duplicateMeterEvents,
                          double billingDifference, double auditCoverage,
                          double classificationCoverage, double retentionCoverage,
                          int legalHoldDeletionEvents, int offlineNetworkRequests,
                          int criticalOpenRisks, double evidenceTraceability) {}

    public record ModeConformance(DeploymentMode mode, Gate gate, boolean deliveryReady,
                                  List<String> blockers, List<String> evidenceRefs) {
        public ModeConformance { required(mode, "mode"); required(gate, "gate"); blockers = copy(blockers); evidenceRefs = copy(evidenceRefs); }
    }

    public record ConformanceReport(int batch, String assessmentRunId, String platformVersion,
                                    Gate gate, RunStatus status, List<ModeConformance> modes,
                                    List<String> blockers, List<String> restrictions, Metrics metrics,
                                    boolean externalEvidenceComplete, boolean enterpriseDeliveryReady,
                                    boolean productionOperationExecuted, Instant evaluatedAt,
                                    List<String> evidenceRefs) {
        public ConformanceReport {
            if (batch != 12) throw new IllegalArgumentException("batch must be 12");
            text(assessmentRunId, "assessmentRunId"); text(platformVersion, "platformVersion");
            required(gate, "gate"); required(status, "status"); modes = copy(modes);
            blockers = copy(blockers); restrictions = copy(restrictions); required(metrics, "metrics");
            required(evaluatedAt, "evaluatedAt"); evidenceRefs = copy(evidenceRefs);
            if (productionOperationExecuted) throw new IllegalArgumentException("Batch 12 control plane cannot execute production operations");
            if (enterpriseDeliveryReady && (gate != Gate.T_G || !externalEvidenceComplete
                    || !blockers.isEmpty() || modes.size() != DeploymentMode.values().length
                    || modes.stream().anyMatch(mode -> !mode.deliveryReady())))
                throw new IllegalArgumentException("enterprise delivery readiness requires T-G and all externally evidenced modes");
        }
    }

    public record Outcome(Request request, TenancyIdentityEvidence tenancyIdentity,
                          AuthorizationAuditEvidence authorizationAudit, RunnerSecurityEvidence runnerSecurity,
                          ModelCostEvidence modelCost, DataGovernanceEvidence dataGovernance,
                          DeploymentEvidence deployment, EnterpriseAcceptanceEvidence acceptance,
                          ConformanceReport report) {
        public Outcome { required(request, "request"); required(report, "report"); }
    }

    static <T> List<T> copy(Collection<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static void common(String run, String version, EvidenceStatus status, String authority, Instant observedAt) {
        text(run, "assessmentRunId"); text(version, "platformVersion"); required(status, "status");
        text(authority, "authorityId"); required(observedAt, "observedAt");
    }
    static List<String> evidence(List<String> refs) {
        List<String> result = copy(refs); if (result.isEmpty()) throw new IllegalArgumentException("evidence refs are required"); return result;
    }
    static void nonnegative(int... values) { if (Arrays.stream(values).anyMatch(value -> value < 0)) throw new IllegalArgumentException("counts cannot be negative"); }
    static void text(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    static void required(Object value, String name) { if (value == null) throw new IllegalArgumentException(name + " is required"); }
    static void digest(String value, String name) { text(value, name); if (!value.matches("[A-Fa-f0-9]{64}")) throw new IllegalArgumentException(name + " must be sha-256"); }
    static void rate(double value, String name) { if (Double.isNaN(value) || value < 0 || value > 1) throw new IllegalArgumentException(name + " must be between 0 and 1"); }
}
