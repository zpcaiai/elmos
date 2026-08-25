package io.elmos.securitycompliance;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static io.elmos.securitycompliance.SecurityModels.*;

public final class SecurityAuthorizationPolicy {
    private final Clock clock;

    public SecurityAuthorizationPolicy() { this(Clock.systemUTC()); }
    SecurityAuthorizationPolicy(Clock clock) { this.clock = clock; }

    public AuthorizationResult evaluate(AuthorizationRequest request) {
        require(request.organizationId(), "organizationId"); require(request.authorizationBoundaryId(), "authorizationBoundaryId");
        require(request.sourceCommit(), "sourceCommit"); require(request.artifactDigest(), "artifactDigest");
        require(request.deploymentRevision(), "deploymentRevision"); require(request.evidenceManifestHash(), "evidenceManifestHash");
        SecurityProfile profile;
        try { profile = SecurityProfile.valueOf(request.profile()); }
        catch (RuntimeException error) { throw new IllegalArgumentException("unknown security profile: " + request.profile()); }

        Instant now = clock.instant();
        List<String> reasons = new ArrayList<>();
        AuthorizationDecision decision;
        if (request.validUntil() == null || !request.validUntil().isAfter(now)) {
            decision = AuthorizationDecision.EXPIRED; reasons.add("AUTHORIZATION_EXPIRED");
        } else if (request.activeIncident()) {
            decision = AuthorizationDecision.SUSPENDED; reasons.add("INCIDENT_REVIEW_REQUIRED");
        } else if (request.criticalRiskOpen()) {
            decision = AuthorizationDecision.DENIED; reasons.add("CRITICAL_VULNERABILITY_OPEN");
        } else if (request.expiredExceptionOpen()) {
            decision = AuthorizationDecision.REASSESSMENT_REQUIRED; reasons.add("EXCEPTION_EXPIRED");
        } else if (!request.coverageSufficient()) {
            decision = AuthorizationDecision.REASSESSMENT_REQUIRED; reasons.add("SECURITY_COVERAGE_INSUFFICIENT");
        } else if (!request.controlAssessmentSatisfied()) {
            decision = AuthorizationDecision.REASSESSMENT_REQUIRED; reasons.add("CONTROL_NOT_IMPLEMENTED");
        } else if (request.evidenceRefs().isEmpty()) {
            decision = AuthorizationDecision.REASSESSMENT_REQUIRED; reasons.add("SECURITY_EVIDENCE_MISSING");
        } else if (profile == SecurityProfile.CRITICAL_SYSTEM
                && (!request.independentAssessment() || request.humanRiskApprover() == null || request.humanRiskApprover().isBlank())) {
            decision = AuthorizationDecision.REASSESSMENT_REQUIRED;
            reasons.add("CRITICAL_SYSTEM_INDEPENDENT_HUMAN_APPROVAL_REQUIRED");
        } else if (!request.conditions().isEmpty()) {
            decision = AuthorizationDecision.AUTHORIZED_WITH_CONDITIONS; reasons.add("INTERNAL_CONDITIONAL_AUTHORIZATION");
        } else {
            decision = AuthorizationDecision.AUTHORIZED; reasons.add("INTERNAL_CONTROL_ASSESSMENT_PASSED");
        }
        return new AuthorizationResult("1.0", "ELMOS_SECURITY_COMPLIANCE", decision,
                true, false, List.copyOf(reasons), request.conditions(), now, request.validUntil(),
                request.evidenceManifestHash(), request.evidenceRefs());
    }
}
