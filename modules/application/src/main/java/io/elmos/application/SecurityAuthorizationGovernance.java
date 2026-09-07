package io.elmos.application;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Read/evaluate-only governance. Scanner execution and formal authorization remain outside the control plane. */
public final class SecurityAuthorizationGovernance {
    public enum Decision { AUTHORIZED, AUTHORIZED_WITH_CONDITIONS, REASSESSMENT_REQUIRED, SUSPENDED, DENIED, EXPIRED }
    public record Evidence(
            String organizationId, String authorizationBoundaryId, String sourceCommit,
            String artifactDigest, String deploymentRevision, String evidenceManifestHash,
            boolean estateComplete, boolean threatModelCurrent, boolean coverageSufficient,
            boolean controlsSatisfied, boolean criticalRiskOpen, boolean expiredExceptionOpen,
            boolean activeIncident, boolean independentAssessment, boolean criticalSystem,
            String qualifiedHumanApprover, Instant validUntil, Map<String, String> conditions,
            List<String> evidenceRefs) {
        public Evidence {
            conditions = conditions == null ? Map.of() : Map.copyOf(conditions);
            evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs);
        }
    }
    public record Result(Decision decision, boolean releaseEligible, boolean internalDecisionOnly,
                         boolean externalCertificationGranted, List<String> blockers,
                         Map<String, String> conditions, String evidenceManifestHash) {}

    public Result evaluate(Evidence evidence, Instant now) {
        Objects.requireNonNull(evidence); Objects.requireNonNull(now);
        require(evidence.organizationId(), "organizationId"); require(evidence.authorizationBoundaryId(), "authorizationBoundaryId");
        require(evidence.sourceCommit(), "sourceCommit"); require(evidence.artifactDigest(), "artifactDigest");
        require(evidence.deploymentRevision(), "deploymentRevision"); require(evidence.evidenceManifestHash(), "evidenceManifestHash");
        List<String> blockers = new ArrayList<>(); Decision decision;
        if (evidence.validUntil() == null || !evidence.validUntil().isAfter(now)) {
            decision = Decision.EXPIRED; blockers.add("AUTHORIZATION_EXPIRED");
        } else if (evidence.activeIncident()) {
            decision = Decision.SUSPENDED; blockers.add("INCIDENT_REVIEW_REQUIRED");
        } else if (evidence.criticalRiskOpen()) {
            decision = Decision.DENIED; blockers.add("CRITICAL_VULNERABILITY_OPEN");
        } else {
            if (!evidence.estateComplete()) blockers.add("SECURITY_ESTATE_INCOMPLETE");
            if (!evidence.threatModelCurrent()) blockers.add("THREAT_MODEL_INCOMPLETE");
            if (!evidence.coverageSufficient()) blockers.add("SECURITY_COVERAGE_INSUFFICIENT");
            if (!evidence.controlsSatisfied()) blockers.add("CONTROL_NOT_IMPLEMENTED");
            if (evidence.expiredExceptionOpen()) blockers.add("EXCEPTION_EXPIRED");
            if (evidence.evidenceRefs().isEmpty()) blockers.add("SECURITY_EVIDENCE_MISSING");
            if (evidence.criticalSystem() && (!evidence.independentAssessment()
                    || evidence.qualifiedHumanApprover() == null || evidence.qualifiedHumanApprover().isBlank())) {
                blockers.add("CRITICAL_SYSTEM_INDEPENDENT_HUMAN_APPROVAL_REQUIRED");
            }
            if (!blockers.isEmpty()) decision = Decision.REASSESSMENT_REQUIRED;
            else if (!evidence.conditions().isEmpty()) decision = Decision.AUTHORIZED_WITH_CONDITIONS;
            else decision = Decision.AUTHORIZED;
        }
        boolean releaseEligible = (decision == Decision.AUTHORIZED || decision == Decision.AUTHORIZED_WITH_CONDITIONS)
                && !evidence.criticalRiskOpen();
        return new Result(decision, releaseEligible, true, false, List.copyOf(blockers),
                evidence.conditions(), evidence.evidenceManifestHash());
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
