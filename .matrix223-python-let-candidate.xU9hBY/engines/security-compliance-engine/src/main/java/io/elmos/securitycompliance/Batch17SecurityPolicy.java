package io.elmos.securitycompliance;

import java.util.List;
import java.util.Set;

/** Deterministic policy kernel exercised by the Batch 17 acceptance scenarios. */
public final class Batch17SecurityPolicy {
    public String networkTrust(boolean locationOnly, boolean authenticatedIdentity) {
        return locationOnly && !authenticatedIdentity ? "IP_BASED_TRUST" : "IDENTITY_CONTEXT_REQUIRED";
    }
    public String privilegedIdentity(int consumers, boolean separateLeastPrivilege) {
        return consumers > 1 && !separateLeastPrivilege ? "SHARED_PRIVILEGED_IDENTITY" : "LEAST_PRIVILEGE_VERIFIED";
    }
    public String exposedSecret(boolean deletedFromSource, boolean revoked, boolean rotated) {
        return deletedFromSource && (!revoked || !rotated) ? "EXPOSED" : "REMEDIATED_PENDING_VERIFICATION";
    }
    public String certificate(int daysRemaining, boolean automaticRenewal) {
        return daysRemaining <= 14 && !automaticRenewal ? "CERTIFICATE_EXPIRING_HIGH" : "MONITORED";
    }
    public String sbom(boolean sourceDependencies, boolean osPackages, boolean deployedComponents) {
        return sourceDependencies && (!osPackages || !deployedComponents) ? "INCOMPLETE" : "COMPLETE_DECLARED_SCOPE";
    }
    public String provenance(boolean generated, boolean trustedBuilder, boolean isolatedBuilder) {
        return generated && (!trustedBuilder || !isolatedBuilder) ? "UNTRUSTED_BUILDER" : "PROVENANCE_VERIFIED";
    }
    public String vexNotAffected(boolean evidence, boolean reachabilityEvidence) {
        return !evidence || !reachabilityEvidence ? "VEX_EVIDENCE_INSUFFICIENT:UNDER_INVESTIGATION" : "NOT_AFFECTED_EVIDENCED";
    }
    public String staticCoverage(double parsedFraction, int findings) {
        return parsedFraction < 1.0 ? "COVERAGE_INSUFFICIENT" : findings == 0 ? "PASS" : "FAIL";
    }
    public int normalizedRootFindings(List<String> rootCauses) {
        return Set.copyOf(rootCauses).size();
    }
    public String activeTest(String environment, boolean approved) {
        return environment.equals("PRODUCTION") && !approved ? "SECURITY_TEST_AUTHORIZATION_REQUIRED" : "AUTHORIZED_PROFILE_REQUIRED";
    }
    public String crossTenant(boolean foreignTenantAccessible) {
        return foreignTenantAccessible ? "CROSS_TENANT_ACCESS:CRITICAL" : "TENANT_ISOLATION_VERIFIED";
    }
    public String businessLogic(boolean genericScanPassed, boolean duplicateRefund) {
        return genericScanPassed && duplicateRefund ? "BUSINESS_LOGIC_ABUSE" : "ABUSE_CASE_REQUIRED";
    }
    public String kev(boolean inDependencyTree, boolean packaged, boolean runtimeLoaded) {
        return inDependencyTree && !packaged && !runtimeLoaded ? "KEV_SIGNAL_NOT_DEPLOYED_EXPOSURE" : "KEV_EXPOSURE_REVIEW";
    }
    public String riskPriority(double cvss, boolean publicUnauthenticated, boolean restrictedData) {
        return cvss < 7 && publicUnauthenticated && restrictedData ? "CRITICAL_BUSINESS_RISK" : "CONTEXTUAL_RISK_REVIEW";
    }
    public String compensatingControl(boolean declared, boolean effectiveOnTarget) {
        return declared && !effectiveOnTarget ? "INEFFECTIVE" : "CONTROL_VERIFIED";
    }
    public String cloudIam(boolean wildcard, boolean broadResource) {
        return wildcard && broadResource ? "OVERPRIVILEGED_ROLE" : "LEAST_PRIVILEGE_CANDIDATE";
    }
    public String kubernetesPolicy(boolean manifestExists, boolean admissionEnforced) {
        return manifestExists && !admissionEnforced ? "NOT_IMPLEMENTED" : "ENFORCEMENT_VERIFIED";
    }
    public String runtimeProcess(Set<String> baseline, String process, boolean networkDownload) {
        return !baseline.contains(process) && process.equals("shell") && networkDownload ? "RUNTIME_SHELL_HIGH" : "BASELINE_MATCH";
    }
    public String masking(boolean uiMasked, boolean apiReturnsFullValue) {
        return uiMasked && apiReturnsFullValue ? "DATA_EXPOSURE_FINDING" : "MINIMIZATION_VERIFIED";
    }
    public String promptDlp(boolean personalData, boolean redacted) {
        return personalData && !redacted ? "PROMPT_DLP_BLOCK" : "PROMPT_POLICY_ALLOW";
    }
    public String deletion(boolean primaryDeleted, boolean trainingDataDeleted, boolean legalHold) {
        return primaryDeleted && !trainingDataDeleted && !legalHold ? "DELETION_CONTROL_FAILED" : "DELETION_LINEAGE_ACCOUNTED";
    }
    public String threatAssumption(boolean assumedInternal, boolean nowPublic) {
        return assumedInternal && nowPublic ? "REASSESSMENT_REQUIRED" : "ASSUMPTION_CURRENT";
    }
    public String crosswalk(double overlap) {
        return overlap > 0 && overlap < 1 ? "PARTIAL" : overlap == 1 ? "EQUIVALENT_REVIEW_REQUIRED" : "NOT_EQUIVALENT";
    }
    public String notApplicable(boolean evidence, boolean approved) {
        return !evidence || !approved ? "OTHER_THAN_SATISFIED" : "NOT_APPLICABLE";
    }
    public String oscalReference(boolean evidenceExists, boolean hashMatches) {
        return !evidenceExists || !hashMatches ? "REFERENCE_INTEGRITY_FAILED" : "PACKAGE_VERIFIED";
    }
    public String exception(boolean expired, boolean riskOpen) {
        return expired && riskOpen ? "REASSESSMENT_REQUIRED_OR_SUSPENDED" : "MONITOR";
    }
    public String authorizationBinding(String authorizedDigest, String deployedDigest) {
        return authorizedDigest.equals(deployedDigest) ? "BOUND" : "REASSESSMENT_REQUIRED";
    }
    public String criticalRiskAcceptance(boolean agent, boolean qualifiedHumanApprover) {
        return agent && !qualifiedHumanApprover ? "HUMAN_REVIEW_REQUIRED" : "HUMAN_DECISION_RECORDED";
    }
    public String managementClaim(boolean internalChecksPassed, boolean externalCertification) {
        return internalChecksPassed && !externalCertification ? "INTERNAL_CONTROL_ASSESSMENT_PASSED" : "EXTERNAL_CLAIM_REQUIRES_AUTHORITY";
    }
    public String incidentClosure(boolean incidentClosed, boolean buildChanged, boolean threatModelChanged) {
        return incidentClosed && (!buildChanged || !threatModelChanged) ? "ROOT_CAUSE_GOVERNANCE_OPEN" : "LEARNING_PROPAGATED";
    }
}
