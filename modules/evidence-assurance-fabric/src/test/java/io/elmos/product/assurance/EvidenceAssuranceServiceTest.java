package io.elmos.product.assurance;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import static io.elmos.product.assurance.EvidenceAssuranceModels.*;
import static org.junit.jupiter.api.Assertions.*;

class EvidenceAssuranceServiceTest {
    private final EvidenceAssuranceService service = new EvidenceAssuranceService();

    @Test void rejectsSelfVerificationUnknownEvidenceAndRatioAveraging() {
        var request = request("judge", EvidenceState.UNKNOWN, false);
        var sameParty = new AdmissionRequest(request.organizationId(), request.evidencePackId(), request.subjectDigest(),
                request.contextSnapshotDigest(), "judge", "judge", request.evaluatedAt(), request.contentImmutable(),
                request.metadataVersioned(), request.attestationSigned(), request.attestationSchemaVerified(),
                request.trustRootVerified(), request.offlineVerificationComplete(), request.crossTenantDedupEnabled(),
                request.retentionExpired(), request.deletionRequested(), request.externalEvidence(), request.metrics(),
                request.lineageComplete(), request.evidenceCompletenessMultidimensional(), request.criticalFailureOpen(),
                request.controlPresenceOnly(), request.independentAssessment(), request.auditClaimIndependentlyVerified(),
                request.cacheTenantAuthorizationVersionBound(), request.narrativesEvidenceBound(), request.evidenceRefs());
        var result = service.evaluate(sameParty);
        assertEquals(Decision.BLOCKED, result.decision());
        assertTrue(result.blockers().contains("PRODUCER_VERIFIER_SEPARATION_REQUIRED"));
        assertTrue(result.blockers().stream().anyMatch(v -> v.endsWith("STATUS_UNKNOWN")));
        assertTrue(result.blockers().stream().anyMatch(v -> v.endsWith("RATIO_AVERAGING_FORBIDDEN")));
    }

    @Test void verifiedIndependentEvidenceOnlyReachesHumanDecision() {
        var result = service.evaluate(request("independent-judge", EvidenceState.VERIFIED, true));
        assertEquals(Decision.READY_FOR_HUMAN_DECISION, result.decision());
        assertFalse(result.approved()); assertFalse(result.externalOperationExecuted());
    }

    private static AdmissionRequest request(String verifier, EvidenceState state, boolean ratioReaggregated) {
        var external = new ExternalEvidence("jenkins-prod", "run-42", "c".repeat(64), "d".repeat(64),
                true, true, true, true, true, true, state);
        var metric = new MetricObservation("coverage-v3", "repository", BigDecimal.valueOf(91), BigDecimal.valueOf(100),
                true, Instant.parse("2026-07-22T00:00:00Z"), "source-cert", ratioReaggregated, state);
        return new AdmissionRequest("org", "pack", "a".repeat(64), "b".repeat(64), "producer", verifier,
                Instant.parse("2026-07-22T00:00:01Z"), true, true, true, true, true, true,
                false, false, false, List.of(external), List.of(metric), true, true, false,
                false, true, true, true, true, List.of("evidence://pack/manifest"));
    }
}
