package io.elmos.securitycompliance;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;

class Batch17AcceptanceScenariosTest {
    private final Batch17SecurityPolicy policy = new Batch17SecurityPolicy();

    @Test void scenario01_internalNetworkIsNotIdentity() { assertEquals("IP_BASED_TRUST", policy.networkTrust(true, false)); }
    @Test void scenario02_sharedDatabaseAdminIsPrivilegedRisk() { assertEquals("SHARED_PRIVILEGED_IDENTITY", policy.privilegedIdentity(3, false)); }
    @Test void scenario03_deletedSecretRemainsExposedUntilRevokedAndRotated() { assertEquals("EXPOSED", policy.exposedSecret(true, false, false)); }
    @Test void scenario04_expiringCertificateRaisesHighRisk() { assertEquals("CERTIFICATE_EXPIRING_HIGH", policy.certificate(10, false)); }
    @Test void scenario05_sourceSbomDoesNotCoverRuntime() { assertEquals("INCOMPLETE", policy.sbom(true, false, false)); }
    @Test void scenario06_untrustedBuilderInvalidatesAssuranceClaim() { assertEquals("UNTRUSTED_BUILDER", policy.provenance(true, false, false)); }
    @Test void scenario07_unsupportedVexBecomesInvestigation() { assertEquals("VEX_EVIDENCE_INSUFFICIENT:UNDER_INVESTIGATION", policy.vexNotAffected(false, false)); }
    @Test void scenario08_parseErrorsPreventPass() { assertEquals("COVERAGE_INSUFFICIENT", policy.staticCoverage(.70, 0)); }
    @Test void scenario09_scannerEvidenceDeduplicatesByRootCause() { assertEquals(1, policy.normalizedRootFindings(List.of("sql-path-1", "sql-path-1", "sql-path-1"))); }
    @Test void scenario10_unapprovedProductionDastIsBlocked() { assertEquals("SECURITY_TEST_AUTHORIZATION_REQUIRED", policy.activeTest("PRODUCTION", false)); }
    @Test void scenario11_crossTenantAccessIsCritical() { assertEquals("CROSS_TENANT_ACCESS:CRITICAL", policy.crossTenant(true)); }
    @Test void scenario12_genericDastCannotHideDuplicateRefund() { assertEquals("BUSINESS_LOGIC_ABUSE", policy.businessLogic(true, true)); }
    @Test void scenario13_unpackedKevIsNotDeclaredProductionExposure() { assertEquals("KEV_SIGNAL_NOT_DEPLOYED_EXPOSURE", policy.kev(true, false, false)); }
    @Test void scenario14_lowCvssPublicDataExportIsCriticalBusinessRisk() { assertEquals("CRITICAL_BUSINESS_RISK", policy.riskPriority(5.0, true, true)); }
    @Test void scenario15_bypassedWafIsIneffective() { assertEquals("INEFFECTIVE", policy.compensatingControl(true, false)); }
    @Test void scenario16_wildcardCloudRoleIsOverprivileged() { assertEquals("OVERPRIVILEGED_ROLE", policy.cloudIam(true, true)); }
    @Test void scenario17_unenforcedKubernetesPolicyIsNotImplemented() { assertEquals("NOT_IMPLEMENTED", policy.kubernetesPolicy(true, false)); }
    @Test void scenario18_unknownShellRaisesRuntimeDetection() { assertEquals("RUNTIME_SHELL_HIGH", policy.runtimeProcess(Set.of("java"), "shell", true)); }
    @Test void scenario19_frontendMaskDoesNotProtectApi() { assertEquals("DATA_EXPOSURE_FINDING", policy.masking(true, true)); }
    @Test void scenario20_personalPromptDataIsBlockedOrRedacted() { assertEquals("PROMPT_DLP_BLOCK", policy.promptDlp(true, false)); }
    @Test void scenario21_deletionMustReachTrainingData() { assertEquals("DELETION_CONTROL_FAILED", policy.deletion(true, false, false)); }
    @Test void scenario22_publicExposureInvalidatesInternalAssumption() { assertEquals("REASSESSMENT_REQUIRED", policy.threatAssumption(true, true)); }
    @Test void scenario23_partialCrosswalkIsNotEquivalent() { assertEquals("PARTIAL", policy.crosswalk(.60)); }
    @Test void scenario24_notApplicableRequiresEvidenceAndApproval() { assertEquals("OTHER_THAN_SATISFIED", policy.notApplicable(false, false)); }
    @Test void scenario25_brokenOscalReferenceBlocksPackage() { assertEquals("REFERENCE_INTEGRITY_FAILED", policy.oscalReference(false, false)); }
    @Test void scenario26_expiredExceptionForcesReassessment() { assertEquals("REASSESSMENT_REQUIRED_OR_SUSPENDED", policy.exception(true, true)); }
    @Test void scenario27_newArtifactInvalidatesOldAuthorization() { assertEquals("REASSESSMENT_REQUIRED", policy.authorizationBinding("sha256:old", "sha256:new")); }
    @Test void scenario28_agentCannotAcceptCriticalRisk() { assertEquals("HUMAN_REVIEW_REQUIRED", policy.criticalRiskAcceptance(true, false)); }
    @Test void scenario29_internalChecksDoNotClaimCertification() { assertEquals("INTERNAL_CONTROL_ASSESSMENT_PASSED", policy.managementClaim(true, false)); }
    @Test void scenario30_incidentClosureMustFeedDevelopment() { assertEquals("ROOT_CAUSE_GOVERNANCE_OPEN", policy.incidentClosure(true, false, false)); }
}
